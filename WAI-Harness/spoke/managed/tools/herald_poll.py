#!/usr/bin/env python3
"""Herald — active cross-spoke comms daemon (MVP, file-queue fallback).

Herald is the wheel's nerve for active synchronization: it turns the passive
"drop a lug in incoming/ and hope someone wakes the spoke" model into an active
service. A spoke's Herald polls its inbox for pending messages addressed to it
and, for each, spawns a single-shot headless Claude session (`claude -p`) in the
spoke directory to act on the message, then marks it responded.

This MVP uses a FILE queue (no Supabase): messages are JSON files under
  <local>/runtime/herald/{inbox,processed,expired,responses}/
which keeps Herald sovereign and dependency-free. The agent_messages Supabase
table (spec-intra-agent-comms-v1) is a later swap behind the same CLI.

Because `claude -p` responds and exits by design, Herald needs no session-startup
auto-exit wiring for the MVP — single-shot is inherent. A WAI_HERALD_SPAWN=1 env
marker is set so a future hook can suppress full wakeup/chain-claiming.

Canonical home: WAI-Harness/spoke/managed/tools/ (Basher-distributed).
Runtime/config: WAI-Harness/spoke/local/runtime/herald/ (gitignored, per-spoke).

Subcommands:
  send    enqueue a message into a target spoke's inbox  (the cross-spoke link)
  poll    run ONE poll cycle (spawn responders for pending messages)
  run     loop poll + sleep(poll_interval_seconds)
  inbox   list pending messages for this spoke
  status  print herald.json config + queue counts

Spec: spec-herald-daemon-v1, spec-intra-agent-comms-v1.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

# --- path resolution (reuse the canonical resolver; degrade gracefully) --------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import wai_paths  # type: ignore
except Exception:  # pragma: no cover - resolver should always be a sibling
    wai_paths = None
try:
    import worktree_guard  # type: ignore — authoritative live-lane registry
except Exception:  # pragma: no cover
    worktree_guard = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def runtime_dir(spoke_root: str) -> str:
    """Resolve <active-base>/runtime for the spoke, harness-mode aware."""
    if wai_paths is not None:
        base, mode = wai_paths.resolve_wai_root(spoke_root)
        if base:
            return os.path.join(base, "runtime")
    # fallback: prefer v4 layout, else v3
    v4 = os.path.join(spoke_root, "WAI-Harness", "spoke", "local")
    if os.path.isdir(v4):
        return os.path.join(v4, "runtime")
    return os.path.join(spoke_root, "WAI-Spoke", "runtime")


def herald_dir(spoke_root: str) -> str:
    return os.path.join(runtime_dir(spoke_root), "herald")


def _dirs(spoke_root: str):
    h = herald_dir(spoke_root)
    d = {
        "root": h,
        "inbox": os.path.join(h, "inbox"),
        "processed": os.path.join(h, "processed"),
        "expired": os.path.join(h, "expired"),
        "responses": os.path.join(h, "responses"),
    }
    for p in d.values():
        os.makedirs(p, exist_ok=True)
    return d


# --- config -------------------------------------------------------------------
DEFAULT_CONFIG = {
    "wheel_id": None,
    # OPT-IN by default: a spoke runs Herald only after it's deliberately enabled.
    # This makes the fleet-distributed SessionStart hook safe — `start` no-ops on
    # every spoke that hasn't opted in, so no surprise daemon / paid spawns fleet-wide.
    "enabled": False,
    "poll_interval_seconds": 30,
    "max_concurrent_spawns": 1,
    "response_timeout_seconds": 600,
    # spawn_command_template: shell string with {prompt_file},{message_id},{thread_id}.
    # When null, Herald spawns argv [claude, -p, <prompt>] (no shell).
    "spawn_command_template": None,
    "spoke_directory": None,
    "last_poll_at": None,
    "poll_success_count": 0,
    "poll_failure_count": 0,
    "spawns_succeeded": 0,
    "spawns_failed": 0,
}


def _config_path(spoke_root: str) -> str:
    return os.path.join(herald_dir(spoke_root), "herald.json")


def _guess_wheel_id(spoke_root: str):
    """Best-effort wheel_id: WAI-State id field -> hub-registry path match -> basename.

    The hub-registry fallback is what makes worktrees resolve correctly: a worktree
    under <registered_path>/.worktrees/<name> matches the registered wheel by path
    prefix, so it inherits the canonical wheel_id rather than the worktree basename.
    """
    for rel in (
        os.path.join("WAI-Harness", "spoke", "local", "WAI-State.json"),
        os.path.join("WAI-Spoke", "WAI-State.json"),
    ):
        p = os.path.join(spoke_root, rel)
        try:
            st = json.load(open(p))
            for k in ("wheel_id", "spoke_id", "project_id", "project"):
                if st.get(k):
                    return str(st[k])
        except Exception:
            continue
    abspath = os.path.abspath(spoke_root)
    for rel in (
        os.path.join("WAI-Harness", "hub", "local", "hub-registry.json"),
        os.path.join("hub", "local", "hub-registry.json"),
        os.path.join("hub", "hub-registry.json"),
    ):
        try:
            reg = json.load(open(os.path.join(spoke_root, rel)))
        except Exception:
            continue
        best = None
        for w in reg.get("wheels", []):
            wp = w.get("path")
            if wp and w.get("wheel_id") and (abspath == os.path.abspath(wp)
                                             or abspath.startswith(os.path.abspath(wp) + os.sep)):
                # longest matching path wins (most specific spoke)
                if best is None or len(wp) > len(best[1]):
                    best = (w["wheel_id"], wp)
        if best:
            return str(best[0])
    return os.path.basename(abspath)


def load_config(spoke_root: str) -> dict:
    _dirs(spoke_root)
    p = _config_path(spoke_root)
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(p):
        try:
            cfg.update(json.load(open(p)))
        except Exception:
            pass
    if not cfg.get("wheel_id"):
        cfg["wheel_id"] = _guess_wheel_id(spoke_root)
    if not cfg.get("spoke_directory"):
        cfg["spoke_directory"] = os.path.abspath(spoke_root)
    return cfg


def save_config(spoke_root: str, cfg: dict) -> None:
    json.dump(cfg, open(_config_path(spoke_root), "w"), indent=2, ensure_ascii=False)


# --- message model ------------------------------------------------------------
def _new_message(to_spoke, from_spoke, kind, subject, body, ref, ttl_seconds, thread_id):
    mid = uuid.uuid4().hex[:12]
    created = _now()
    expires = _iso(created.fromtimestamp(created.timestamp() + ttl_seconds, tz=timezone.utc)) if ttl_seconds else None
    return {
        "id": mid,
        "thread_id": thread_id or uuid.uuid4().hex[:12],
        "from_spoke": from_spoke,
        "to_spoke": to_spoke,
        "kind": kind,
        "subject": subject,
        "body": body,
        "ref": ref,
        "created_at": _iso(created),
        "expires_at": expires,
        "status": "pending",
    }


def _resolve_target_root(to_spoke, explicit_root, spoke_root):
    """Resolve the filesystem root of the target spoke for a send()."""
    if explicit_root:
        return os.path.abspath(explicit_root)
    # try hub-registry lookups relative to this spoke
    candidates = []
    for rel in (
        os.path.join("WAI-Harness", "hub", "local", "hub-registry.json"),
        os.path.join("hub", "local", "hub-registry.json"),
        os.path.join("hub", "hub-registry.json"),
    ):
        candidates.append(os.path.join(spoke_root, rel))
    for p in candidates:
        try:
            reg = json.load(open(p))
        except Exception:
            continue
        for w in reg.get("wheels", []):
            if str(w.get("wheel_id", "")).lower() == to_spoke.lower() and w.get("path"):
                return os.path.abspath(w["path"])
    return None


# --- send (the cross-spoke link) ----------------------------------------------
def cmd_send(args) -> int:
    spoke_root = args.spoke_root
    cfg = load_config(spoke_root)
    from_spoke = args.from_spoke or cfg["wheel_id"]
    target_root = _resolve_target_root(args.to, args.target_root, spoke_root)
    if not target_root or not os.path.isdir(target_root):
        print(f"herald send: cannot resolve target spoke root for '{args.to}' "
              f"(pass --target-root)", file=sys.stderr)
        return 2
    ref = None
    if args.ref:
        ref = {"lug_id": args.ref} if not args.ref.strip().startswith("{") else json.loads(args.ref)
    msg = _new_message(args.to, from_spoke, args.kind, args.subject, args.body,
                       ref, args.ttl_seconds, args.thread)
    # deliver into the TARGET spoke's inbox (sanctioned cross-spoke comms write)
    tgt_inbox = _dirs(target_root)["inbox"]
    dest = os.path.join(tgt_inbox, msg["id"] + ".json")
    json.dump(msg, open(dest, "w"), indent=2, ensure_ascii=False)
    print(f"herald: delivered message {msg['id']} -> {args.to}:{dest}")
    print(f"  thread={msg['thread_id']} kind={args.kind} subject={args.subject!r}")
    return 0


# --- poll ---------------------------------------------------------------------
def _load_msg(path):
    try:
        return json.load(open(path))
    except Exception:
        return None


def _build_prompt(msg: dict) -> str:
    ref = ""
    if msg.get("ref"):
        ref = "\nReference: " + json.dumps(msg["ref"])
    return (
        "[HERALD MESSAGE — single-shot responder; do not run full wakeup, do not claim chains]\n"
        f"From spoke: {msg.get('from_spoke')}\n"
        f"Kind: {msg.get('kind')}\n"
        f"Subject: {msg.get('subject')}\n"
        f"Thread: {msg.get('thread_id')}  Message: {msg.get('id')}{ref}\n\n"
        f"{msg.get('body','')}\n\n"
        "Act on this message in THIS spoke's tree, then summarize what you did in one paragraph and exit."
    )


def _target_contended(cwd: str) -> bool:
    """CSRP pre-spawn read: True if the target spoke tree has other live lanes.
    Best-effort — on any failure assume idle (the responder prompt still carries the
    CSRP-aware default posture, so a false-negative never causes a blind commit)."""
    wg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worktree_guard.py")
    base = os.path.join(cwd, "WAI-Harness", "spoke", "local")
    if not (os.path.isfile(wg) and os.path.isdir(base)):
        return False
    try:
        out = subprocess.run([sys.executable, wg, "lanes", "--base", base],
                             capture_output=True, text=True, timeout=10)
        return int(json.loads(out.stdout or "{}").get("count", 0)) > 0
    except Exception:
        return False


def _spawn(cfg: dict, msg: dict, dirs: dict, cwd=None, model=None, prompt=None) -> tuple[int, str]:
    prompt = prompt or _build_prompt(msg)
    cwd = cwd or cfg.get("spoke_directory") or os.getcwd()
    # cost-aware: responders run a cheaper model by default (auto-answer work is
    # bounded). The lug's own model_fit wins; else config responder_model; else sonnet.
    model = model or cfg.get("responder_model") or "claude-sonnet-4-6"
    env = dict(os.environ)
    env["WAI_HERALD_SPAWN"] = "1"
    env["WAI_HERALD_MESSAGE_ID"] = msg["id"]
    env["WAI_HERALD_THREAD_ID"] = msg["thread_id"]
    timeout = int(cfg.get("response_timeout_seconds") or 600)

    # CSRP pre-spawn policy: if the target tree is contended (other live lanes),
    # flag the responder so it isolates / scope-commits — never blind-commits a
    # shared tree. Idle target -> normal posture. (The default responder posture is
    # scoped-commit, no chain claims, no -A regardless.)
    if _target_contended(cwd):
        env["WAI_HERALD_CONTENDED"] = "1"
        prompt = (prompt or "") + (
            "\n\n[CSRP — TARGET TREE CONTENDED: other live sessions are working this "
            "spoke. Do NOT `git add -A` and do NOT merge to main. Isolate in a worktree "
            "OR commit ONLY your scoped files via commit-mine.sh, then push your own "
            "session/herald branch.]"
        )

    tmpl = cfg.get("spawn_command_template")
    if tmpl:
        prompt_file = os.path.join(dirs["responses"], msg["id"] + ".prompt.txt")
        open(prompt_file, "w").write(prompt)
        cmd = tmpl.format(prompt_file=prompt_file, message_id=msg["id"],
                          thread_id=msg["thread_id"], model=model)
        proc = subprocess.run(cmd, shell=True, cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=timeout)
    else:
        cmd = ["claude", "-p", "--model", model]
        if cfg.get("responder_autonomous"):
            cmd.append("--dangerously-skip-permissions")  # operator-authorized autonomous commit
        elif cfg.get("responder_permission_mode"):
            cmd += ["--permission-mode", str(cfg.get("responder_permission_mode"))]
        cmd.append(prompt)
        proc = subprocess.run(cmd, cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=timeout)
    out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
    return proc.returncode, out


def _responder_protocol(wid: str, key: str, lug: dict, origin: str) -> str:
    """The full responder contract: assess -> (refine-back | execute) -> verify ->
    CSRP-scoped commit + push own branch (never main) -> confirm back to origin.
    This is what closes the loop so the originating session can continue/test."""
    title = lug.get("title", "")
    return (
        "[HERALD RESPONDER — single-shot. Do NOT run full wakeup; do NOT claim chains.]\n"
        f"A timely lug is in {wid}'s incoming/: {key}\n"
        f"Title: {title}\nOriginating spoke (confirm back here): {origin or '?'}\n\n"
        "PROTOCOL:\n"
        "1. ASSESS definition. If under-specified (no clear PEV / acceptance), do NOT guess: "
        "deliver a refinement-request lug back to the originating spoke's lugs/incoming/ "
        "(type:refinement, the specific questions), mark this lug blocked:needs-refinement, exit.\n"
        "2. EXECUTE the lug's plan in this spoke's tree.\n"
        "3. VERIFY — run the lug's verify / acceptance tests. If they fail, mark "
        "needs-attention and report the failure back to the originator; do not mark complete.\n"
        "4. COMMIT — CSRP-aware: read this spoke's live-lane state; if contended, isolate in a "
        "worktree or scope the add (never git add -A on a shared tree). PUSH your OWN session/herald "
        "branch only — never push to main; main-merge stays gated.\n"
        "5. CONFIRM — deliver a completion lug back to the originator's incoming/ (verdict, "
        "tests-passed, commit sha, branch) so that session is acknowledged and can pull/test.\n"
        "6. Move this lug to processed/ and exit."
    )


def poll_once(spoke_root: str, max_spawns=None, force=False) -> dict:
    cfg = load_config(spoke_root)
    dirs = _dirs(spoke_root)
    result = {"polled_at": _iso(_now()), "wheel_id": cfg["wheel_id"],
              "expired": 0, "responded": 0, "failed": 0, "skipped": 0, "pending_seen": 0}

    if not cfg.get("enabled") and not force:
        result["skipped"] = "disabled"
        return result

    limit = max_spawns if max_spawns is not None else int(cfg.get("max_concurrent_spawns") or 1)
    now = _now()
    pending = []
    for fn in sorted(os.listdir(dirs["inbox"])):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(dirs["inbox"], fn)
        msg = _load_msg(path)
        if not msg or msg.get("status") != "pending":
            continue
        # address filter: deliver-to-this-spoke (accept if to_spoke matches or unset)
        to = (msg.get("to_spoke") or "").lower()
        if to and to != str(cfg["wheel_id"]).lower():
            continue
        # TTL check
        exp = _parse_iso(msg.get("expires_at"))
        if exp and exp <= now:
            msg["status"] = "expired"
            json.dump(msg, open(os.path.join(dirs["expired"], fn), "w"), indent=2, ensure_ascii=False)
            os.remove(path)
            result["expired"] += 1
            continue
        pending.append((path, msg))

    result["pending_seen"] = len(pending)
    spawned = 0
    for path, msg in pending:
        if spawned >= limit:
            break
        spawned += 1
        try:
            rc, out = _spawn(cfg, msg, dirs)
        except subprocess.TimeoutExpired:
            rc, out = 124, "[herald] spawn timed out"
        json.dump({"message_id": msg["id"], "thread_id": msg["thread_id"],
                   "returncode": rc, "at": _iso(_now()), "output": out},
                  open(os.path.join(dirs["responses"], msg["id"] + ".json"), "w"),
                  indent=2, ensure_ascii=False)
        if rc == 0:
            msg["status"] = "responded"
            msg["responded_at"] = _iso(_now())
            json.dump(msg, open(os.path.join(dirs["processed"], os.path.basename(path)), "w"),
                      indent=2, ensure_ascii=False)
            os.remove(path)
            result["responded"] += 1
            cfg["spawns_succeeded"] = int(cfg.get("spawns_succeeded") or 0) + 1
        else:
            # leave pending for retry; record last error
            msg["last_error"] = f"rc={rc}"
            msg["last_attempt_at"] = _iso(_now())
            json.dump(msg, open(path, "w"), indent=2, ensure_ascii=False)
            result["failed"] += 1
            cfg["spawns_failed"] = int(cfg.get("spawns_failed") or 0) + 1

    cfg["last_poll_at"] = result["polled_at"]
    if result["failed"]:
        cfg["poll_failure_count"] = int(cfg.get("poll_failure_count") or 0) + 1
    else:
        cfg["poll_success_count"] = int(cfg.get("poll_success_count") or 0) + 1
    save_config(spoke_root, cfg)
    return result


def cmd_poll(args) -> int:
    res = poll_once(args.spoke_root, max_spawns=args.max, force=args.force)
    print(json.dumps(res, indent=2))
    return 0


# --- watch: the active pickup layer over each spoke's existing lugs/incoming/ ---
# Spokes do NOT learn a new channel or "hit" Herald. They keep delivering lugs to
# lugs/incoming/ exactly as today; Herald (hub/Basher-hosted) watches every spoke's
# incoming/ and auto-fires a responder when a lug arrives.
#
# Action vs over-reaction: Herald does NOT spawn on every incoming item — most are
# informational (notice/report/signal) and should accumulate for the spoke's next
# session. It fires ONLY on items the SENDER marked for active handling
# (herald_active:true OR delivery_mode:"active"), plus any kinds the operator opted
# into via config auto_fire_kinds (default none). Default-absent flag = passive =
# zero behavior change. The sender, who knows urgency, owns the action/quiet choice.

def _hub_registry(basher_root: str, cfg: dict):
    """Resolve the hub-registry (all spoke paths). Configurable, else search the
    canonical hub location (co-located with the master)."""
    cand = []
    if cfg.get("hub_registry_path"):
        cand.append(cfg["hub_registry_path"])
    cand += [
        os.path.join(basher_root, "WAI-Harness", "hub", "local", "hub-registry.json"),
        "/home/mario/projects/wheelwright/mywheel/WAI-Harness/hub/local/hub-registry.json",
        os.path.join(basher_root, "hub", "local", "hub-registry.json"),
    ]
    for p in cand:
        try:
            return json.load(open(p)).get("wheels", [])
        except Exception:
            continue
    return []


def _fired_path(basher_root: str) -> str:
    return os.path.join(herald_dir(basher_root), "fired.json")


def _load_fired(basher_root: str) -> dict:
    try:
        return json.load(open(_fired_path(basher_root)))
    except Exception:
        return {}


def _incoming_dir(wheel_path: str) -> str:
    return os.path.join(wheel_path, "WAI-Harness", "spoke", "local",
                        "lugs", "incoming")


# Priority is INFERRED from fields lugs already carry — no new schema. A lug is
# "timely" when its priority is high+ OR its impact clears a threshold. (An explicit
# herald_active/delivery_mode:active is still honored as an optional escape hatch,
# but nothing is required to set it.)
_PRIORITY_RANK = {"low": 1, "medium": 2, "normal": 2, "high": 3, "urgent": 4, "critical": 5}


def _priority_rank(lug: dict) -> int:
    return _PRIORITY_RANK.get(str(lug.get("priority", "")).lower(), 0)


def _is_timely(lug: dict, cfg: dict) -> bool:
    if _priority_rank(lug) >= int(cfg.get("priority_min_rank", 3)):  # high+
        return True
    try:
        if int(lug.get("impact", 0)) >= int(cfg.get("priority_impact_min", 8)):
            return True
    except (TypeError, ValueError):
        pass
    if lug.get("herald_active") is True or str(lug.get("delivery_mode", "")).lower() == "active":
        return True
    return False


def _cooldown_ok(last_iso, hours) -> bool:
    last = _parse_iso(last_iso)
    if not last:
        return True
    return (_now() - last).total_seconds() >= hours * 3600


def watch_once(basher_root: str, force=False) -> dict:
    """Scan every (enabled) spoke's lugs/incoming/. Two triggers, both idempotent:
      1. TIMELY  — fire a responder per high-priority/high-impact lug (inferred,
         no new fields) so work the user needs *now* (because of what they're doing
         in another session) gets actioned promptly.
      2. HYGIENE — if a spoke's incoming backlog (any priority) crosses a threshold,
         fire ONE responder (on a cooldown) to drain/triage it, keeping queues clean.
    This is an auto-answer / action daemon: timely work acted on, low-priority swept."""
    cfg = load_config(basher_root)
    res = {"watched_at": _iso(_now()), "spokes_scanned": 0, "fired": 0,
           "hygiene_fired": 0, "skipped_low": 0, "already_fired": 0, "items": []}
    if not cfg.get("enabled") and not force:
        res["skipped"] = "disabled"
        return res
    only = set(cfg.get("watch_spokes") or [])  # empty = all
    fired = _load_fired(basher_root)
    dirs = _dirs(basher_root)
    limit = int(cfg.get("max_concurrent_spawns") or 1)
    backlog_threshold = int(cfg.get("hygiene_backlog_threshold", 10))
    hygiene_cooldown_h = float(cfg.get("hygiene_cooldown_hours", 6))
    spawned = 0

    def _fire(wid, wpath, kind, subject, body, ref, model=None):
        nonlocal spawned
        spawned += 1
        msg = {"id": ref, "thread_id": ref, "from_spoke": "herald", "to_spoke": wid,
               "kind": kind, "subject": subject[:120], "body": body, "ref": {"key": ref}}
        try:
            rc, _ = _spawn(cfg, msg, dirs, cwd=wpath, model=model, prompt=body)
        except subprocess.TimeoutExpired:
            rc = 124
        fired[ref] = {"fired_at": _iso(_now()), "rc": rc, "kind": kind}
        res["items"].append({"key": ref, "kind": kind, "rc": rc})
        return rc

    for w in _hub_registry(basher_root, cfg):
        wid, wpath = w.get("wheel_id"), w.get("path")
        if not wid or not wpath or (only and wid not in only):
            continue
        # Active-collaboration watch = the LIVE fleet. Skip archived/graveyard spokes:
        # they don't collaborate and their stale lugs must never fire a responder.
        if str(w.get("status", "")).lower() == "archived" \
                or "/_archive/" in wpath or "/.archive/" in wpath:
            res["skipped_archived"] = res.get("skipped_archived", 0) + 1
            continue
        inbox = _incoming_dir(wpath)
        if not os.path.isdir(inbox):
            continue
        res["spokes_scanned"] += 1
        pending = []
        for fn in sorted(os.listdir(inbox)):
            if fn.endswith(".json"):
                lug = _load_msg(os.path.join(inbox, fn))
                if lug:
                    pending.append((fn, lug))

        # 1. timely (priority-inferred) — fire each, idempotent
        fired_here = 0
        for fn, lug in pending:
            if spawned >= limit:
                break
            if not _is_timely(lug, cfg):
                res["skipped_low"] += 1
                continue
            key = f"{wid}:{lug.get('id', fn)}"
            if key in fired:
                # Re-pick on RE-DELIVERY: a refinement round-trip rewrites the lug
                # (the originator answered the questions and re-delivered it). If the
                # file changed after we last fired, clear the fired-set entry so Herald
                # re-fires the now-complete lug instead of skipping it as already-fired.
                _last = _parse_iso(fired[key].get("fired_at"))
                try:
                    _mtime = datetime.fromtimestamp(
                        os.path.getmtime(os.path.join(inbox, fn)), timezone.utc)
                except OSError:
                    _mtime = None
                if _last and _mtime and _mtime > _last:
                    del fired[key]
                    res["repicked"] = res.get("repicked", 0) + 1
                else:
                    res["already_fired"] += 1
                    continue
            origin = lug.get("source_spoke") or lug.get("from_spoke") or "?"
            rc = _fire(wid, wpath, "priority:" + str(lug.get("type", "?")),
                       lug.get("title", ""),
                       _responder_protocol(wid, key, lug, origin),
                       key, model=lug.get("model_fit"))  # lug's model_fit wins, else sonnet
            if rc == 0:
                res["fired"] += 1
                fired_here += 1

        # 2. hygiene — backlog of (mostly low-priority) lugs over threshold, on cooldown
        if spawned < limit and fired_here == 0 and len(pending) >= backlog_threshold:
            hkey = f"{wid}:__hygiene__"
            if _cooldown_ok(fired.get(hkey, {}).get("fired_at"), hygiene_cooldown_h):
                rc = _fire(wid, wpath, "hygiene",
                           f"drain backlog ({len(pending)} pending)",
                           (f"Your incoming/ has {len(pending)} pending lugs — a backlog. "
                            "Triage and process/close what you can to keep the queue clean "
                            "(hygiene sweep). Low-priority is fine to batch. Respect CSRP."),
                           hkey)
                if rc == 0:
                    res["hygiene_fired"] += 1

    json.dump(fired, open(_fired_path(basher_root), "w"), indent=2, ensure_ascii=False)
    return res


def cmd_watch(args) -> int:
    print(json.dumps(watch_once(args.spoke_root, force=args.force), indent=2))
    return 0


# --- session-lifecycle binding ------------------------------------------------
# Herald is only useful while a live CC session could be messaging another. So it
# is NOT a standing cron: SessionStart fires `start` (idempotent detached launch),
# and Herald SELF-REAPS when the authoritative live-lane count (worktree_guard's
# sessions-live.json registry, the same signal CSRP uses) drops to zero. No stop
# hook needed — the daemon outlives no session it isn't serving.

def active_session_count(spoke_root: str) -> int:
    """Authoritative count of live CC sessions for this spoke (after reap).

    Prefers worktree_guard.live_lanes (handles TTL + transcript-gone + persists the
    reap). Falls back to counting lane dirs with a fresh .hb heartbeat mtime.
    Returns -1 if liveness cannot be determined (treated as 'stay alive')."""
    base = runtime_dir(spoke_root).rsplit(os.sep + "runtime", 1)[0]
    if worktree_guard is not None:
        try:
            return len(worktree_guard.live_lanes(base))
        except Exception:
            pass
    lanes = os.path.join(runtime_dir(spoke_root), "lanes")
    if not os.path.isdir(lanes):
        return -1
    ttl = 12 * 3600
    now = time.time()
    n = 0
    for d in os.listdir(lanes):
        hb = os.path.join(lanes, d, ".hb")
        try:
            if now - os.path.getmtime(hb) <= ttl:
                n += 1
        except OSError:
            continue
    return n


def _pid_path(spoke_root: str) -> str:
    return os.path.join(herald_dir(spoke_root), "herald.pid")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False
    except PermissionError:
        return True


def _read_pid(spoke_root: str):
    try:
        return int(open(_pid_path(spoke_root)).read().strip())
    except Exception:
        return None


def _acquire_lock(spoke_root: str) -> bool:
    """Atomically claim the singleton lock. Steals a stale (dead-PID) lock."""
    _dirs(spoke_root)
    path = _pid_path(spoke_root)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        existing = _read_pid(spoke_root)
        if existing and existing != os.getpid() and _pid_alive(existing):
            return False
        # stale lock — steal it
        try:
            with open(path, "w") as f:
                f.write(str(os.getpid()))
            return True
        except Exception:
            return False


def _release_lock(spoke_root: str) -> None:
    if _read_pid(spoke_root) == os.getpid():
        try:
            os.remove(_pid_path(spoke_root))
        except OSError:
            pass


def cmd_run(args) -> int:
    cfg = load_config(args.spoke_root)
    interval = args.interval or int(cfg.get("poll_interval_seconds") or 30)
    until_idle = getattr(args, "until_idle", False)
    idle_ticks_needed = max(1, getattr(args, "idle_ticks", 2) or 2)

    if not _acquire_lock(args.spoke_root):
        print(f"herald: already running (pid {_read_pid(args.spoke_root)}) — not starting a second")
        return 0

    # graceful SIGTERM: raise so the finally releases the lock (default handler would
    # kill mid-sleep and leak the pidfile)
    import signal

    def _term(_signum, _frame):
        raise SystemExit(0)

    try:
        signal.signal(signal.SIGTERM, _term)
    except (ValueError, OSError):  # not in main thread (e.g. tests) — fine
        pass

    mode = "until-idle (self-reaps when no live session)" if until_idle else "forever (Ctrl-C)"
    print(f"herald: poll loop for {cfg['wheel_id']} every {interval}s — {mode}")
    idle = 0
    do_watch = cfg.get("watch_incoming", True)
    try:
        while True:
            res = poll_once(args.spoke_root, max_spawns=args.max, force=args.force)
            if res.get("pending_seen") or res.get("expired"):
                print(json.dumps(res))
            if do_watch:  # central pickup over each spoke's lugs/incoming/
                wres = watch_once(args.spoke_root, force=args.force)
                if wres.get("fired") or wres.get("items"):
                    print(json.dumps(wres))
            if until_idle:
                n = active_session_count(args.spoke_root)
                if n == 0:
                    idle += 1
                    if idle >= idle_ticks_needed:
                        print(f"herald: {idle} idle ticks, no live session — exiting")
                        return 0
                else:
                    idle = 0
            time.sleep(interval)
    finally:
        _release_lock(args.spoke_root)


def cmd_start(args) -> int:
    """Idempotent detached launch — what SessionStart calls. No-op if disabled or up.

    The opt-in gate is what makes a fleet-distributed SessionStart hook safe: on a
    spoke that hasn't set herald.json enabled:true, start does nothing — no daemon,
    no spawns. Only deliberately-enabled spokes participate.
    """
    cfg = load_config(args.spoke_root)
    if not cfg.get("enabled") and not getattr(args, "force", False):
        print(f"herald: disabled for {cfg['wheel_id']} (set herald.json enabled:true to opt in) — not starting")
        return 0
    existing = _read_pid(args.spoke_root)
    if existing and _pid_alive(existing):
        print(f"herald: already running (pid {existing})")
        return 0
    log = os.path.join(herald_dir(args.spoke_root), "herald.log")
    cmd = [sys.executable, os.path.abspath(__file__), "--spoke-root",
           os.path.abspath(args.spoke_root), "run", "--until-idle"]
    if args.interval:
        cmd += ["--interval", str(args.interval)]
    lf = open(log, "a")
    subprocess.Popen(cmd, stdout=lf, stderr=lf, stdin=subprocess.DEVNULL,
                     start_new_session=True, close_fds=True)
    print(f"herald: started (detached, until-idle) — log {log}")
    return 0


def cmd_stop(args) -> int:
    pid = _read_pid(args.spoke_root)
    if not pid or not _pid_alive(pid):
        print("herald: not running")
        if pid:  # clear a stale pidfile
            try:
                os.remove(_pid_path(args.spoke_root))
            except OSError:
                pass
        return 0
    try:
        os.kill(pid, 15)
    except OSError as e:
        print(f"herald: could not stop pid {pid}: {e}", file=sys.stderr)
        return 1
    # wait briefly for graceful exit; clean the pidfile if the daemon didn't
    for _ in range(20):
        if not _pid_alive(pid):
            break
        time.sleep(0.1)
    if _read_pid(args.spoke_root) == pid:
        try:
            os.remove(_pid_path(args.spoke_root))
        except OSError:
            pass
    print(f"herald: stopped pid {pid}")
    return 0


def cmd_inbox(args) -> int:
    dirs = _dirs(args.spoke_root)
    cfg = load_config(args.spoke_root)
    rows = []
    for fn in sorted(os.listdir(dirs["inbox"])):
        if fn.endswith(".json"):
            m = _load_msg(os.path.join(dirs["inbox"], fn)) or {}
            rows.append(m)
    print(f"herald inbox for {cfg['wheel_id']}: {len(rows)} pending")
    for m in rows:
        print(f"  - {m.get('id')} [{m.get('kind')}] from={m.get('from_spoke')} "
              f"subject={m.get('subject')!r} expires={m.get('expires_at')}")
    return 0


def status_oneline(spoke_root: str) -> str:
    """Stable one-line status contract for tool-wrapper banners (wai-enter.sh).
    `<state> | <inbox> queued` where state in {running, enabled-idle, inactive}.
    Wrappers consume THIS, not the pidfile/json internals, so the banner survives
    Herald runtime refactors."""
    cfg = load_config(spoke_root)
    pid = _read_pid(spoke_root)
    inbox = len([f for f in os.listdir(_dirs(spoke_root)["inbox"]) if f.endswith(".json")])
    if pid and _pid_alive(pid):
        state = "running"
    elif cfg.get("enabled"):
        state = "enabled-idle"
    else:
        state = "inactive"
    return f"{state} | {inbox} queued"


def cmd_status(args) -> int:
    if getattr(args, "oneline", False):
        print(status_oneline(args.spoke_root))  # single stable line; exit 0 always
        return 0
    cfg = load_config(args.spoke_root)
    dirs = _dirs(args.spoke_root)
    counts = {k: len([f for f in os.listdir(dirs[k]) if f.endswith(".json")])
              for k in ("inbox", "processed", "expired")}
    print(json.dumps({"config": cfg, "queue": counts}, indent=2))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Herald — active cross-spoke comms daemon (MVP).")
    ap.add_argument("--spoke-root", default=".", help="spoke root dir (default cwd)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("send", help="enqueue a message into a target spoke's inbox")
    s.add_argument("--to", required=True, help="target wheel_id")
    s.add_argument("--target-root", help="target spoke filesystem root (else hub-registry lookup)")
    s.add_argument("--from", dest="from_spoke", help="sender wheel_id (default: this spoke)")
    s.add_argument("--kind", default="message", help="message kind (e.g. canon-sync, consult, handoff)")
    s.add_argument("--subject", default="", help="short subject")
    s.add_argument("--body", default="", help="message body / instruction")
    s.add_argument("--ref", help="referenced lug id, or a JSON object")
    s.add_argument("--ttl-seconds", type=int, default=0, help="TTL (0 = no expiry)")
    s.add_argument("--thread", help="thread id (default: new)")
    s.set_defaults(func=cmd_send)

    p = sub.add_parser("poll", help="run one poll cycle (herald inbox)")
    p.add_argument("--max", type=int, help="max spawns this cycle")
    p.add_argument("--force", action="store_true", help="poll even if disabled")
    p.set_defaults(func=cmd_poll)

    wp = sub.add_parser("watch", help="one scan of every spoke's lugs/incoming/ — fire on active-flagged lugs")
    wp.add_argument("--force", action="store_true", help="watch even if disabled")
    wp.set_defaults(func=cmd_watch)

    r = sub.add_parser("run", help="loop poll + sleep (foreground)")
    r.add_argument("--interval", type=int, help="seconds between polls")
    r.add_argument("--max", type=int, help="max spawns per cycle")
    r.add_argument("--force", action="store_true")
    r.add_argument("--until-idle", action="store_true",
                   help="self-reap when no live CC session remains (session-bound mode)")
    r.add_argument("--idle-ticks", type=int, default=2,
                   help="consecutive idle polls before exit (default 2)")
    r.set_defaults(func=cmd_run)

    st2 = sub.add_parser("start", help="idempotent detached launch (SessionStart calls this)")
    st2.add_argument("--interval", type=int, help="seconds between polls")
    st2.add_argument("--force", action="store_true", help="start even if not opted in")
    st2.set_defaults(func=cmd_start)

    sp = sub.add_parser("stop", help="stop the running daemon")
    sp.set_defaults(func=cmd_stop)

    i = sub.add_parser("inbox", help="list pending messages")
    i.set_defaults(func=cmd_inbox)

    st = sub.add_parser("status", help="print config + queue counts")
    st.add_argument("--oneline", action="store_true",
                    help="one stable line for wrapper banners: <state> | <inbox> queued")
    st.set_defaults(func=cmd_status)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
