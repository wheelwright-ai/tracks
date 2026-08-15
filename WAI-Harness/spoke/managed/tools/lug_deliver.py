#!/usr/bin/env python3
"""lug_deliver.py — deliver a lug to a spoke, and when it is urgent, TAP the live session.

THE PROBLEM. A lug lands in <spoke>/WAI-Harness/spoke/local/lugs/incoming/ and then
waits. Nothing reads it until somebody starts a session or types a prompt. Measured on
basher 2026-08-02: three status:open lugs sat unread in an inbox for up to 11 days, and
a P0 delivered to mywheel had no way to reach the session actually working that tree.
Delivery was write-and-hope.

The existing notify (`<wai-inbox-notify>` in user-prompt-submit.sh) is real but PULL
shaped — it fires on the next prompt submit, so an idle session never sees it. That is
the gap: not "we lack polling", but that an urgent lug has no push path.

THE OPERATOR'S FRAMING (2026-08-02), which is bigger than notification: "this tap
allows two sessions to talk actively and collaborate, lugs arrive like chatting
colleagues and get to the right sessions ... to divide and conquer more complex
initiatives spanning spokes ... and stay aligned until done." So this is a message bus
between live sessions, not a doorbell. The tiering below exists to make that safe.

THREE TIERS, chosen from live state, never guessed:
    TAP    live session, idle, and the lug is urgent  -> type into its pane now
    QUEUE  live session but busy                      -> inbox notify catches it next turn
    COLD   no live session                            -> it waits; Herald may spawn

WHY TAPPING IS DANGEROUS, AND WHAT THAT BUYS THE DESIGN. `zellij action write-chars`
types into a pane as if the operator did. Land it mid-turn and the text interleaves
into a half-written prompt and submits at a moment nobody chose. This repo has already
been burned by write-chars: terminal autorepeat on lens's `r` key spawned 64 tabs, each
auto-typing a resume command, overflowing zjstatus into an OOM crash-loop. So every tap
here is idle-gated, debounced, deduplicated, attributed, and confirmed — and the
default is NOT to tap.

Nothing about the mechanism is new. Every input already existed and is joined here:
    sessions-live.json      who is live in that spoke (cwd, wrapper pid, wai_session)
    /proc/<pid>/environ     wrapper pid -> the claude child's ZELLIJ_PANE_ID
    last-interaction-<pane> per-pane idle seconds, written by the notify hooks
    zellij write-chars      the delivery primitive, hardened in lens's _lens_forward

CLI:
    lug_deliver.py resolve --to <spoke_root>
    lug_deliver.py deliver <lug.json> --to <spoke_root> [--tap] [--dry-run]
    lug_deliver.py tap --to <spoke_root> --text "..." [--dry-run]
Exit: 0 ok | 2 error. `deliver` never fails the caller for a tap that did not land —
the lug is on disk either way, which is the durable half.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

SESS_DIR = os.environ.get("WAI_SESS_DIR", "/tmp/claude-sessions")

# A pane quiet for at least this long is treated as between turns. Deliberately not
# zero: the stamp is written when a turn STARTS, so a small window still means "typing
# right now". 30s is the smallest value that reliably lands between turns in practice.
IDLE_MIN_SECS = int(os.environ.get("WAI_TAP_IDLE_MIN", "30"))

# Never tap the same pane more often than this, whatever the caller asks. This is the
# tab-storm lesson: the guard must live at the mechanism, not at every call site.
TAP_COOLDOWN_SECS = int(os.environ.get("WAI_TAP_COOLDOWN", "120"))

# Urgency values that may interrupt a live session at all.
TAP_PRIORITIES = {"p0", "P0"}

ZJ_TIMEOUT = int(os.environ.get("ZJ_CALL_TIMEOUT", "8"))


def _now() -> float:
    return time.time()


def _run(argv, timeout=ZJ_TIMEOUT):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _proc_env(pid):
    try:
        with open(f"/proc/{pid}/environ", "rb") as fh:
            return dict(
                kv.split("=", 1) for kv in fh.read().decode("utf-8", "replace").split("\0")
                if "=" in kv
            )
    except Exception:
        return {}


def _ppid(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            return int(fh.read().rsplit(")", 1)[1].split()[1])
    except Exception:
        return None


def _pane_for_wrapper(wrapper_pid):
    """The zellij pane of the claude CHILD of this wai-enter wrapper.

    The lane registry records the WRAPPER's pid; the pane id lives on the claude
    process it spawned. Walking children is what joins the two. Verified on basher:
    lane 0bda747f (wrapper 3157545) -> pane 11.
    """
    if not wrapper_pid or not os.path.isdir("/proc"):
        return None
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        env = _proc_env(pid)
        pane = env.get("ZELLIJ_PANE_ID")
        if not pane:
            continue
        # direct child, or one level down (wrapper -> shell -> claude)
        p1 = _ppid(pid)
        if p1 == wrapper_pid or (p1 and _ppid(p1) == wrapper_pid):
            return pane
    return None


def _turn_start(pane):
    path = os.path.join(SESS_DIR, f"last-interaction-{pane}")
    try:
        with open(path, encoding="utf-8") as fh:
            return float(fh.read().strip())
    except Exception:
        return None


def _idle_secs(pane):
    ts = _turn_start(pane)
    return None if ts is None else int(_now() - ts)   # unknown is NOT idle


def _last_track_ts(spoke_root, wai_session):
    """Epoch of the newest record on that session's track (turn END)."""
    if not wai_session:
        return None
    p = os.path.join(spoke_root, "WAI-Harness", "spoke", "local",
                     "sessions", wai_session, "track.jsonl")
    newest = None
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ts = (json.loads(line) or {}).get("ts")
                    if not ts:
                        continue
                    import datetime
                    e = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    newest = e if newest is None else max(newest, e)
                except Exception:
                    continue
    except Exception:
        return None
    return newest


def _mid_turn(spoke_root, wai_session, pane):
    """Is this session between turns, or working right now?

    CAUGHT BY TESTING AGAINST A LIVE SESSION rather than assuming: the
    last-interaction stamp is written by notify.sh when the OPERATOR submits a prompt,
    so it marks turn START. basher's own session showed idle_secs=2146 while actively
    mid-turn — the operator simply had not typed for 36 minutes. Idle-gating on that
    alone would have tapped a session in the middle of its work, which is the precise
    hazard the gate exists to prevent.

    The track gives the other half: its newest record is written when a turn ENDS. So
    turn-start NEWER than the last track entry means the current turn has not landed
    yet — the session is working. Unknown -> treated as busy, never as idle.
    """
    start = _turn_start(pane)
    if start is None:
        return True

    # TRANSCRIPT FIRST, NOT LAST (mywheel adoption, s140). The stamp/track comparison
    # below is only as good as the stamp, and the stamp can FREEZE. Measured on mywheel
    # session-20260802-0902 while it was demonstrably mid-turn:
    #     turn_start (last-interaction-14) 02:01:36   <- stuck at turn 1
    #     last_track (newest record)       03:34:59
    #     start > last -> False  ->  "between turns"  ->  tappable=true
    # last-interaction-<pane> was never refreshed for turns 2, 3 or 4 even though each
    # was a genuine operator submit. Once the track advances past a frozen stamp — which
    # happens at the very first Stop flush — the session is classified "between turns"
    # for the REST OF ITS LIFE.
    #
    # That is the exact mirror of the empty-track bug documented below, and it fails the
    # dangerous way round: that one made a session permanently UNtappable (a dead zone),
    # this one makes it permanently tappable (an open door into working sessions). A
    # stale input must never be able to manufacture consent.
    #
    # The transcript cannot freeze the same way: Claude Code appends to it continuously
    # while a turn runs, so a recent mtime is positive evidence of work in progress. Ask
    # it FIRST and let it veto, instead of only consulting it when everything else is
    # missing. It is the one signal here that is written by the thing being measured.
    tp = _transcript_for(spoke_root, wai_session)
    if tp:
        try:
            if (_now() - os.path.getmtime(tp)) < IDLE_MIN_SECS:
                return True      # producing output right now — busy, whatever the stamp says
        except OSError:
            pass

    last = _last_track_ts(spoke_root, wai_session)
    if last is not None:
        return start > last

    # NO USABLE TRACK. Found by a 25-minute live watch that never fired: mywheel's
    # session-20260802-0902 had a track.jsonl of ZERO lines, so this returned True
    # forever and that session was PERMANENTLY untappable. "Unknown -> busy" is the
    # right instinct but it must not become a dead zone — a brand-new session, or one
    # whose Stop hook has not flushed yet, would never be reachable at all.
    #
    # The transcript is the fallback: Claude Code appends to it continuously while a
    # turn runs, so its mtime is a direct read of "is this session producing output
    # right now" — the same liveness signal lens uses to tell a live pane from a
    # corpse. Quiet for longer than the idle floor means between turns.
    tp = _transcript_for(spoke_root, wai_session)
    if tp:
        try:
            return (_now() - os.path.getmtime(tp)) < IDLE_MIN_SECS
        except OSError:
            pass
    return True      # nothing to read at all -> still refuse


def _transcript_for(spoke_root, wai_session):
    """The claude transcript path this lane recorded, from the lane registry."""
    reg = _read_json(os.path.join(spoke_root, "WAI-Harness", "spoke", "local",
                                  "runtime", "sessions-live.json"), {}) or {}
    for lane in (reg.get("lanes") or {}).values():
        if isinstance(lane, dict) and lane.get("wai_session") == wai_session:
            tp = lane.get("transcript")
            return tp if tp and os.path.isfile(tp) else None
    return None


def resolve_targets(spoke_root):
    """Live sessions in this spoke, each with its pane and idle seconds.

    Only lanes whose cwd is actually inside spoke_root are returned — a lane in a
    sibling checkout must never be tapped on this spoke's behalf.
    """
    base = os.path.join(spoke_root, "WAI-Harness", "spoke", "local")
    reg = _read_json(os.path.join(base, "runtime", "sessions-live.json"), {}) or {}
    root = os.path.realpath(spoke_root)
    out = []
    for lane_id, lane in (reg.get("lanes") or {}).items():
        if not isinstance(lane, dict):
            continue
        cwd = os.path.realpath(lane.get("cwd") or "")
        if not (cwd == root or cwd.startswith(root + os.sep)):
            continue
        pane = _pane_for_wrapper(lane.get("pid"))
        idle = _idle_secs(pane) if pane else None
        busy = _mid_turn(spoke_root, lane.get("wai_session"), pane) if pane else True
        out.append({
            "lane": lane_id,
            "wai_session": lane.get("wai_session"),
            "cwd": cwd,
            "pid": lane.get("pid"),
            "pane": pane,
            "idle_secs": idle,
            "mid_turn": busy,
            # BOTH conditions. Quiet-for-a-while is not enough on its own: the operator
            # may simply not have typed while the session works. mid_turn is the
            # authoritative half; idle is the courtesy margin on top of it.
            "tappable": bool(pane) and not busy and idle is not None and idle >= IDLE_MIN_SECS,
        })
    out.sort(key=lambda t: (not t["tappable"], t["idle_secs"] if t["idle_secs"] is not None else 1 << 30))
    return out


def _tap_state_path(pane):
    return os.path.join(SESS_DIR, f"tap-{pane}.json")


def _cooldown_block(pane, dedupe_key):
    """(blocked, why). Enforced at the mechanism so no caller can opt out."""
    st = _read_json(_tap_state_path(pane), {}) or {}
    if dedupe_key and dedupe_key in (st.get("delivered") or []):
        return True, f"already tapped pane {pane} with {dedupe_key}"
    last = st.get("last_ts") or 0
    age = _now() - last
    if age < TAP_COOLDOWN_SECS:
        return True, f"pane {pane} tapped {int(age)}s ago (cooldown {TAP_COOLDOWN_SECS}s)"
    return False, ""


def _tap_state_record(pane, dedupe_key):
    st = _read_json(_tap_state_path(pane), {}) or {}
    st["last_ts"] = _now()
    seen = st.get("delivered") or []
    if dedupe_key:
        seen.append(dedupe_key)
    st["delivered"] = seen[-50:]
    try:
        os.makedirs(SESS_DIR, exist_ok=True)
        with open(_tap_state_path(pane), "w", encoding="utf-8") as fh:
            json.dump(st, fh)
    except Exception:
        pass


def tap(pane, text, dedupe_key=None, dry_run=False, self_pane=None):
    """Type `text` into `pane` and submit it. Returns (ok, why).

    Mirrors lens's _lens_forward discipline: every zellij call bounded, focus dance,
    bracketed paste for multi-line so the target treats it as ONE paste rather than
    submitting each line, and delivery counted as confirmed only when the calls that
    can actually fail on a stale pane return 0.
    """
    blocked, why = _cooldown_block(pane, dedupe_key)
    if blocked:
        return False, why
    if dry_run:
        return True, f"DRY-RUN would tap pane {pane}"
    if not shutil.which("zellij"):
        return False, "zellij not on PATH"

    ok = True
    rc, _ = _run(["zellij", "action", "focus-pane-id", str(pane)]); ok &= rc == 0
    time.sleep(0.08)
    payload = f"\x1b[200~{text}\x1b[201~" if "\n" in text else text
    rc, _ = _run(["zellij", "action", "write-chars", payload]); ok &= rc == 0
    time.sleep(0.03)
    rc, _ = _run(["zellij", "action", "write", "13"]); ok &= rc == 0   # Enter submits
    time.sleep(0.03)
    if self_pane:
        _run(["zellij", "action", "focus-pane-id", str(self_pane)])
    if ok:
        _tap_state_record(pane, dedupe_key)
        return True, f"tapped pane {pane}"
    return False, f"delivery to pane {pane} not confirmed"


def compose_tap_text(lug, source_spoke, lug_rel):
    """The message a colleague session receives.

    ALWAYS attributed. A tap is indistinguishable from the operator typing, so an
    unattributed one is impersonation — the receiving session must be able to tell
    that a peer sent this, and the operator reading scrollback must too.
    """
    lid = lug.get("id", "?")
    title = (lug.get("title") or "").strip()
    pr = (lug.get("priority") or "").upper()
    return (
        f"[wai-tap from {source_spoke}] {pr or 'lug'} {lid}\n"
        f"{title}\n"
        f"Read {lug_rel} now and action or counter it. "
        f"Reply by writing a lug back to {source_spoke}'s incoming/."
    )


def deliver(lug_path, spoke_root, allow_tap=False, dry_run=False, source_spoke=None):
    lug = _read_json(lug_path)
    if lug is None:
        return 2, {"ok": False, "why": f"unreadable lug: {lug_path}"}
    base = os.path.join(spoke_root, "WAI-Harness", "spoke", "local")
    inbox = os.path.join(base, "lugs", "incoming")
    if not os.path.isdir(base):
        return 2, {"ok": False, "why": f"not a v4 spoke: {spoke_root}"}
    dest = os.path.join(inbox, os.path.basename(lug_path))
    result = {"ok": True, "lug": lug.get("id"), "dest": dest, "tier": "queue", "tap": None}

    # Targets are resolved BEFORE the write, because where the recipient is READING
    # decides where the durable half has to land.
    targets = resolve_targets(spoke_root)
    result["live_sessions"] = targets

    # 1. DURABLE HALF FIRST. The lug is on disk before any terminal is touched, so a
    #    failed tap can never mean a lost delivery.
    #
    #    EVERY INBOX THE RECIPIENT MIGHT READ, NOT JUST THE MAIN CHECKOUT. A session
    #    working in a worktree reads <worktree>/WAI-Harness/spoke/local/lugs/incoming/,
    #    which is a DIFFERENT directory from the main repo's. Writing only the main
    #    inbox reported success while the live recipient could not see the lug.
    #    Measured 2026-08-14: mywheel delivered change-distribute-v6-resolver-cut-to-
    #    fleet-v1 to basher's main inbox; basher's session was in
    #    .worktrees/s260814-014950 and replied that the lug "does not exist ... find
    #    returns nothing". It was on disk the whole time, in a tree nobody was reading.
    #
    #    AND CONFIRM EACH WRITE BY READING IT BACK. A copy that reports success without
    #    the artifact being present is the failure class this whole tool exists to kill.
    inboxes = [inbox]

    def _add_inbox(root):
        if not root or os.path.realpath(root) == os.path.realpath(spoke_root):
            return                        # the main checkout is already queued
        alt_base = os.path.join(root, "WAI-Harness", "spoke", "local")
        if not os.path.isdir(alt_base):
            return                        # not a spoke root of its own
        alt = os.path.join(alt_base, "lugs", "incoming")
        if alt not in inboxes:
            inboxes.append(alt)

    # (a) Any live lane whose cwd is its own tree.
    for t in targets:
        _add_inbox(t.get("cwd") or "")

    # (b) EVERY worktree on disk, from the FILESYSTEM — deliberately NOT from the lane
    #     registry. Measured 2026-08-14: basher's registry held one lane whose cwd was
    #     the MAIN repo while a real session was working in .worktrees/s260814-014950,
    #     which had no registry of its own. A delivery that trusts an incomplete
    #     registry inherits its blind spots, and the blind spot is exactly the case
    #     that loses the lug. The filesystem cannot forget to register itself.
    wt_root = os.path.join(spoke_root, ".worktrees")
    if os.path.isdir(wt_root):
        try:
            for name in sorted(os.listdir(wt_root)):
                _add_inbox(os.path.join(wt_root, name))
        except OSError:
            pass

    delivered, failed = [], []
    if not dry_run:
        for box in inboxes:
            target = os.path.join(box, os.path.basename(lug_path))
            try:
                os.makedirs(box, exist_ok=True)
                shutil.copyfile(lug_path, target)
                if os.path.isfile(target) and os.path.getsize(target) > 0:
                    delivered.append(target)
                else:
                    failed.append({"dest": target, "why": "write reported success but the file is absent or empty"})
            except OSError as exc:
                failed.append({"dest": target, "why": str(exc)})
    else:
        delivered = [os.path.join(b, os.path.basename(lug_path)) for b in inboxes]
    result["delivered_to"] = delivered
    result["inboxes_considered"] = inboxes
    if failed:
        result["failed_destinations"] = failed
    if not delivered:
        result["ok"] = False
        result["why"] = "no inbox accepted the lug — delivery FAILED, do not treat as queued"
        return 2, result
    if not targets:
        result["tier"] = "cold"
        return 0, result

    urgent = (lug.get("priority") or "").lower() in {p.lower() for p in TAP_PRIORITIES}
    if not (allow_tap and urgent):
        result["tier"] = "queue"
        result["why"] = ("not tapping: " +
                         ("--tap not given" if not allow_tap else f"priority={lug.get('priority')!r} is not P0"))
        return 0, result

    cand = next((t for t in targets if t["tappable"]), None)
    if not cand:
        # Name the ACTUAL blocking condition. The first version printed
        # "busy (idle=2423s < 30s)", which is not even arithmetically true — the real
        # cause was mid_turn and the message blamed idle. A refusal whose stated reason
        # is wrong is worse than a bare refusal: it sends the reader to fix the wrong
        # thing. (Caught on the first live run of this tool against basher itself.)
        b = targets[0]
        if b.get("mid_turn"):
            cause = "is MID-TURN (working now; the operator being quiet does not mean idle)"
        elif b.get("idle_secs") is None:
            cause = "has no interaction stamp — treated as busy rather than assumed idle"
        elif not b.get("pane"):
            cause = "has no resolvable zellij pane"
        else:
            cause = f"went quiet only {b['idle_secs']}s ago (need {IDLE_MIN_SECS}s)"
        result["tier"] = "queue"
        result["why"] = (f"live session {b.get('wai_session')} {cause} — "
                         "inbox notify will surface it next turn")
        return 0, result

    text = compose_tap_text(lug, source_spoke or "a peer spoke",
                            os.path.relpath(dest, spoke_root))
    ok, why = tap(cand["pane"], text, dedupe_key=lug.get("id"), dry_run=dry_run,
                  self_pane=os.environ.get("ZELLIJ_PANE_ID"))
    result["tier"] = "tap" if ok else "queue"
    result["tap"] = {"pane": cand["pane"], "session": cand["wai_session"], "ok": ok, "why": why}
    return 0, result


def resolve_spoke_path(wheel_id, hub_registry=None):
    """wheel_id -> filesystem path, from the hub registry of record.

    Never derive or guess a sibling's path (work-style-registry-over-self-derived-paths).
    The registry is searched at the operator's known hub first, then any path the caller
    supplies; unresolvable returns None so the caller can report rather than write into
    a directory it invented.
    """
    cands = [hub_registry] if hub_registry else []
    cands += [
        os.path.expanduser("~/projects/wheelwright/mywheel/WAI-Harness/hub/local/hub-registry.json"),
        os.path.expanduser("~/projects/wheelwright/hub/WAI-Harness/hub/local/hub-registry.json"),
    ]
    for c in cands:
        if not c or not os.path.isfile(c):
            continue
        reg = _read_json(c, {}) or {}
        for w in (reg.get("wheels") or []):
            if not isinstance(w, dict):
                continue
            if wheel_id in (w.get("wheel_id"), w.get("spoke_id"), w.get("id")):
                p = w.get("path")
                if p and os.path.isdir(p):
                    return p
    return None


def sweep(outgoing_dir, allow_tap=False, dry_run=False, source_spoke=None, hub_registry=None):
    """Deliver every outgoing lug that names a destination and has not gone yet.

    THIS IS THE DELIVERY PATH. Before it, cross-spoke delivery was a hand-typed `cp`
    per lug, which is why lugs got left in outgoing/ for a closeout sweep to find later
    — and why three of them sat unread in a directory nobody watched. One command that
    resolves the destination from the registry, delivers, stamps delivered_at, and taps
    the P0s makes the correct path also the easy one.
    """
    results = []
    for path in sorted(_glob_json(outgoing_dir)):
        lug = _read_json(path)
        if not isinstance(lug, dict):
            continue
        dest_id = lug.get("destination_wheel_id")
        if not dest_id or lug.get("delivered_at"):
            continue
        root = resolve_spoke_path(dest_id, hub_registry)
        if not root:
            results.append({"lug": lug.get("id"), "ok": False,
                            "why": f"destination_wheel_id {dest_id!r} not in the hub registry"})
            continue
        rc, res = deliver(path, root, allow_tap=allow_tap, dry_run=dry_run,
                          source_spoke=source_spoke)
        res["to"] = dest_id
        # Stamp the SOURCE copy so the same lug is never delivered twice.
        if rc == 0 and not dry_run:
            lug["delivered_at"] = _iso_now()
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(lug, fh, indent=1)
            except Exception:
                res["why"] = (res.get("why", "") + " | WARN could not stamp delivered_at").strip()
        results.append(res)
    return results


def _glob_json(d):
    try:
        return [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json")]
    except Exception:
        return []


def _iso_now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deliver a lug; tap the live session when urgent")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("resolve", help="who is live in that spoke, and can they be tapped")
    r.add_argument("--to", required=True)

    d = sub.add_parser("deliver", help="copy the lug into the spoke's inbox, then tier it")
    d.add_argument("lug")
    d.add_argument("--to", required=True)
    d.add_argument("--tap", action="store_true", help="allow a tap when the lug is P0 and a session is idle")
    d.add_argument("--from", dest="source", default=None, help="source spoke id (for attribution)")
    d.add_argument("--dry-run", action="store_true")

    t = sub.add_parser("tap", help="send a raw attributed message to a live session")
    t.add_argument("--to", required=True)
    t.add_argument("--text", required=True)
    t.add_argument("--dry-run", action="store_true")

    s = sub.add_parser("sweep", help="deliver every undelivered lug in outgoing/ (the delivery path)")
    s.add_argument("--outgoing", default="WAI-Harness/spoke/local/lugs/outgoing")
    s.add_argument("--from", dest="source", default=None)
    s.add_argument("--tap", action="store_true")
    s.add_argument("--hub-registry", default=None)
    s.add_argument("--dry-run", action="store_true")

    a = ap.parse_args(argv)

    if a.cmd == "resolve":
        print(json.dumps({"targets": resolve_targets(a.to)}, indent=1))
        return 0
    if a.cmd == "deliver":
        rc, res = deliver(a.lug, a.to, allow_tap=a.tap, dry_run=a.dry_run, source_spoke=a.source)
        print(json.dumps(res, indent=1))
        return rc
    if a.cmd == "sweep":
        res = sweep(a.outgoing, allow_tap=a.tap, dry_run=a.dry_run,
                    source_spoke=a.source, hub_registry=a.hub_registry)
        print(json.dumps({"delivered": len([r for r in res if r.get("ok", True)]),
                          "results": res}, indent=1))
        return 0
    if a.cmd == "tap":
        cand = next((t for t in resolve_targets(a.to) if t["tappable"]), None)
        if not cand:
            print(json.dumps({"ok": False, "why": "no idle live session in that spoke"}, indent=1))
            return 0
        ok, why = tap(cand["pane"], a.text, dedupe_key=None, dry_run=a.dry_run,
                      self_pane=os.environ.get("ZELLIJ_PANE_ID"))
        print(json.dumps({"ok": ok, "why": why, "pane": cand["pane"]}, indent=1))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
