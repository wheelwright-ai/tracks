#!/usr/bin/env python3
"""converge_closeout.py — CSRP P6: convergent (lane-aware) savepoint/closeout.

When a session savepoints/closes, it becomes a candidate LEAD: detect competitor
lanes, reconcile their committed work into ONE tree, cooperatively converge idle
lanes, RE-VERIFY the unified tree, then hand back so the caller closes normally.

Pure orchestration over existing primitives (worktree_guard lanes + worktrees,
lug_status_reconcile, db_writer). Fail-safe: the merge-lock is lease-based and
auto-expires, so a crashed lead never deadlocks the fleet.

Contract — the guarantee, not just the motion (PEV / unify-then-VERIFY):
  * exactly one lead at a time (atomic lease lock; steals an expired lease),
  * ACTIVE competitors are reconciled (committed work merged) but NEVER force-closed,
  * IDLE/STALE competitors are signalled to self-converge; DEAD ones are committed-to-
    branch then reaped — no uncommitted work is ever discarded,
  * the unified HEAD is RE-TESTED before convergence is declared done; a red union
    blocks (lock retained for fix-forward), it does not silently ship,
  * single-session is a zero-cost no-op.

CLI:
  status        --base B --session-id SID [--repo R] [--active-window S]
  acquire-lock  --base B --session-id SID [--lease-seconds S]
  release-lock  --base B --session-id SID
  signal        --base B --target SID [--from SID] [--kind converge_request]
  drain-signals --base B --session-id SID
  reconcile-lane --repo R --name WT [--no-verify] [--test-cmd CMD]
  converge      --base B --session-id SID --repo R [--my-worktree NAME]
                [--no-verify] [--test-cmd CMD] [--active-window S] [--lease-seconds S]
Exit: 0 ok | 1 not-lead/verify-failed/error (see JSON 'ok').
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import worktree_guard as wg  # noqa: E402

ACTIVE_WINDOW_S = 300          # last_seen within this -> ACTIVE (mid-turn); else IDLE
DEFAULT_LEASE_S = 900          # merge-lock lease; auto-expires so a dead lead can't deadlock


# ── merge-lock (atomic, lease-based) ────────────────────────────────────────

def _lock_path(base):
    return os.path.join(wg._canonical_base(base), "runtime", "converge.lock")


def _read_lock(base):
    try:
        return json.loads(Path(_lock_path(base)).read_text())
    except Exception:
        return None


def _lease_live(lock, now):
    exp = wg._parse_iso((lock or {}).get("lease_expires", ""))
    return bool(exp and exp > now)


def _mirror_registry_lock(base, lock):
    reg = wg._load_registry(base)
    if lock is None:
        reg.pop("converge_lock", None)
    else:
        reg["converge_lock"] = lock
    wg._save_registry(base, reg)


def acquire_lock(base, session_id, lease_seconds=DEFAULT_LEASE_S):
    """Atomically acquire the convergence merge-lock. Returns {acquired, holder, lock}.
    Uses O_CREAT|O_EXCL as the true mutex; steals a lease that has expired (crashed lead)."""
    now = wg._utcnow()
    path = _lock_path(base)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock = {"holder_sid": session_id, "acquired_at": wg._iso(now),
            "lease_expires": wg._iso(now + timedelta(seconds=lease_seconds))}
    payload = (json.dumps(lock) + "\n").encode()
    for attempt in (1, 2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
            _mirror_registry_lock(base, lock)
            return {"acquired": True, "holder": session_id, "lock": lock}
        except FileExistsError:
            cur = _read_lock(base)
            if cur and cur.get("holder_sid") == session_id:
                # re-entrant: refresh our own lease
                Path(path).write_bytes(payload)
                _mirror_registry_lock(base, lock)
                return {"acquired": True, "holder": session_id, "lock": lock, "reentrant": True}
            if not _lease_live(cur, now) and attempt == 1:
                # expired lease -> steal it, then retry the exclusive create
                try:
                    os.unlink(path)
                except OSError:
                    pass
                continue
            return {"acquired": False, "holder": (cur or {}).get("holder_sid"), "lock": cur}
    return {"acquired": False, "holder": (_read_lock(base) or {}).get("holder_sid")}


def release_lock(base, session_id):
    cur = _read_lock(base)
    if cur and cur.get("holder_sid") != session_id:
        return {"released": False, "reason": "not holder", "holder": cur.get("holder_sid")}
    try:
        os.unlink(_lock_path(base))
    except OSError:
        pass
    _mirror_registry_lock(base, None)
    return {"released": True}


# ── per-lane converge mailbox ───────────────────────────────────────────────

def _inbox_path(base, cc_sid):
    return os.path.join(base, wg.LANES_DIR, cc_sid, "converge-inbox.jsonl")


def signal(base, target_sid, from_sid="", kind="converge_request"):
    """Append a cooperative converge request to the target lane's mailbox (and, best
    effort, the durable event journal for audit). The target acts on it at next stop."""
    p = _inbox_path(base, target_sid)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    ev = {"ts": wg._iso(), "type": kind, "from": from_sid, "to": target_sid}
    with open(p, "a") as f:
        f.write(json.dumps(ev) + "\n")
    try:  # best-effort durable audit; never fatal
        import db_writer
        db_writer.enqueue_event({"ts": ev["ts"], "session": target_sid, "actor": "converge_closeout",
                                 "type": kind, "subject_ref": from_sid, "status": "requested"})
    except Exception:
        pass
    return {"signalled": target_sid, "kind": kind}


def drain_signals(base, cc_sid):
    """Read and CLEAR this lane's converge requests (the stop-hook calls this)."""
    p = _inbox_path(base, cc_sid)
    if not os.path.exists(p):
        return {"requests": []}
    reqs = []
    for ln in Path(p).read_text().splitlines():
        ln = ln.strip()
        if ln:
            try:
                reqs.append(json.loads(ln))
            except Exception:
                pass
    try:
        os.unlink(p)
    except OSError:
        pass
    return {"requests": reqs, "count": len(reqs)}


# ── classification ──────────────────────────────────────────────────────────

def _lane_open(meta, now, open_window=ACTIVE_WINDOW_S):
    """Is the session that opened this lane actually OPEN right now? A live session
    beats its lane heartbeat periodically, so 'open' == alive AND last_seen within the
    open window. A lane that hasn't beat inside the window is NOT open -- its opening
    session has ended/stalled -- and is therefore a candidate for ABSORPTION (operator
    rule, s134). Stricter than the 12h reap TTL: we don't wait half a day to absorb a
    session that simply isn't there anymore."""
    if not wg._lane_alive(meta, now):
        return False
    last = wg._parse_iso(meta.get("last_seen", ""))
    return bool(last and (now - last).total_seconds() <= open_window)


def _classify_lane(meta, now, active_window=ACTIVE_WINDOW_S):
    if not wg._lane_alive(meta, now):
        return "dead"
    if _lane_open(meta, now, active_window):
        return "active"
    return "idle"


def _is_self(sid, meta, session_id):
    """Is this lane the CALLER's own lane?

    Identity here has two spellings and they are not interchangeable: the lane
    registry keys on the Claude session UUID, while every ceremony passes
    --session-id as the wai-session NAME (`session-YYYYMMDD-HHMM`, the sessions/
    dir). A bare `sid == session_id` therefore never matched, so a session
    counted itself as a competitor — and once its own heartbeat aged past the
    active window it became an absorption candidate OF ITSELF, letting converge
    unregister the live lane it was running in. Match on either spelling.
    """
    if not session_id:
        return False
    if sid == session_id:
        return True
    return bool(meta) and meta.get("wai_session") == session_id


def absorption_candidates(base, session_id, open_window=ACTIVE_WINDOW_S):
    """Competitor lanes whose opening session is NOT open -> absorption candidates.
    A lane is a candidate the moment its opener is gone (heartbeat stale beyond the
    open window, transcript gone, or past TTL), with or without a worktree."""
    now = wg._utcnow()
    out = []
    for sid, m in wg.live_lanes(base).items():
        if _is_self(sid, m, session_id):
            continue
        if _lane_open(m, now, open_window):
            continue
        out.append({"sid": sid, "wai_session": m.get("wai_session"),
                    "last_seen": m.get("last_seen"),
                    "worktree": m.get("worktree") or m.get("wai_session"),
                    "liveness": _classify_lane(m, now, open_window),
                    "reason": "opening session not open (heartbeat stale / ended)"})
    return out


def _cand_sid(cand):
    """Session id of an absorption candidate — the key the operator confirms by."""
    return cand.get("sid") if isinstance(cand, dict) else cand


def _match_lane(wt_name, lanes):
    """Best-effort map a worktree to its owning lane: lane wai_session == worktree name,
    or the worktree-name appears in the lane's transcript/worktree hint."""
    for sid, m in lanes.items():
        if m.get("wai_session") == wt_name or m.get("worktree") == wt_name:
            return sid, m
        if wt_name and wt_name in (m.get("transcript") or ""):
            return sid, m
    return None, None


def worktree_absorption_candidates(base, session_id, root, my_worktree=None,
                                   open_window=ACTIVE_WINDOW_S):
    """Parked-fork WORKTREES that converge would mutate, keyed by worktree name.

    The lane-based gate was not enough, and the hole ran the wrong way round.
    absorption_candidates() enumerates live_lanes() only, so a fork whose lane
    has aged past LANE_TTL_SECONDS yields NO candidate at all — converge then
    classifies its worktree 'dead', auto-commits its uncommitted work via
    _commit_dirty_lane() and finishes it. That exempted precisely the oldest,
    most deliberately-parked forks: age was buying LESS protection instead of
    more, and 'age is not a retire verdict' (operator, standing rule).

    A dirty worktree is unlanded operator work however its lane aged, so it
    needs the same consent as a live-lane fork. Confirm by worktree NAME (or by
    its session id, when one can still be matched).

    Deliberately NOT candidates:
      * clean worktrees — finishing a clean, merged lane is the safe reap this
        tool exists to do; gating it would mean convergence never tidies up.
      * worktrees whose lane is still OPEN — converge never force-closes a live
        peer (it merges committed work only, and skips that too when dirty).
    """
    lanes = wg.live_lanes(base)
    now = wg._utcnow()
    lane_sids = {c.get("sid") for c in absorption_candidates(base, session_id, open_window)}
    out = []
    for w in wg.session_worktrees(root):
        if my_worktree and w["name"] == my_worktree:
            continue
        if not w.get("dirty"):
            continue
        sid, meta = _match_lane(w["name"], lanes)
        if _is_self(sid, meta, session_id):
            continue
        if meta and _lane_open(meta, now, open_window):
            continue                      # live peer — converge leaves it alone
        if sid and sid in lane_sids:
            continue                      # already surfaced as a lane candidate
        out.append({"sid": sid, "worktree": w["name"], "branch": w["branch"],
                    "dirty": True, "ahead": w.get("ahead", 0),
                    "liveness": _classify_lane(meta, now, open_window) if meta else "no-lane",
                    "reason": "parked fork with uncommitted work and no open lane; "
                              "converge would auto-commit it"})
    return out


def absorb_consent_required(base, session_id, root, my_worktree=None,
                            open_window=ACTIVE_WINDOW_S):
    """Everything converge would absorb or mutate that needs operator consent:
    the union of stale LANES and dirty parked WORKTREES, deduped so one fork is
    never asked about twice. Each entry carries `confirm_keys` — any one of them
    satisfies --confirm-absorb for that fork."""
    out = []
    for c in absorption_candidates(base, session_id, open_window):
        keys = {c.get("sid"), c.get("worktree"), c.get("wai_session")}
        out.append({**c, "kind": "lane",
                    "confirm_keys": sorted(k for k in keys if k)})
    for c in worktree_absorption_candidates(base, session_id, root, my_worktree, open_window):
        keys = {c.get("sid"), c.get("worktree")}
        out.append({**c, "kind": "worktree",
                    "confirm_keys": sorted(k for k in keys if k)})
    return out


def status(base, session_id, repo=".", active_window=ACTIVE_WINDOW_S):
    lanes = wg.live_lanes(base)
    competitors = []
    for sid, m in lanes.items():
        if _is_self(sid, m, session_id):
            continue
        competitors.append({"sid": sid, "wai_session": m.get("wai_session"),
                            "last_seen": m.get("last_seen"),
                            "liveness": _classify_lane(m, wg._utcnow(), active_window)})
    wts = wg.session_worktrees(repo)
    lock = _read_lock(base)
    cands = absorption_candidates(base, session_id, active_window)
    return {"session_id": session_id, "competitors": competitors,
            "worktrees": wts, "lead_eligible": bool(competitors) or len(wts) > 0,
            "absorption_candidates": cands,
            "lock_held_by": (lock or {}).get("holder_sid")}


# ── unified-tree re-verification (the gate the operator demanded) ───────────

def _detect_test_cmd(repo):
    """The closeout-style test gate. WHEEL RULE (Mario, 2026-07-01): a spoke's
    tests/critical_paths.sh, when present, IS the gate — it takes priority over
    generic pytest-dir detection (reference implementation: pathfinder's
    tests/critical_paths.sh, 81 real deterministic tests). Falls back to an
    explicit harness test dir when the spoke hasn't adopted the gate yet."""
    cp = os.path.join(repo, "tests", "critical_paths.sh")
    if os.path.isfile(cp):
        return ["bash", cp]
    for rel in ("WAI-Harness/spoke/managed/tests", "tests"):
        if os.path.isdir(os.path.join(repo, rel)):
            return [sys.executable, "-m", "pytest", rel, "-q", "-p", "no:cacheprovider"]
    return None


def verify_unified(repo, test_cmd=None):
    """Re-run the test gate on the UNIFIED HEAD. unify-then-VERIFY, never -trust.
    Returns {ok, ran, status, detail}. No tests detected -> ok=False/ran=False with
    status 'no-tests' (HONEST: an unverifiable union is NOT a green union)."""
    cmd = test_cmd or _detect_test_cmd(repo)
    if not cmd:
        return {"ok": False, "ran": False, "status": "no-tests",
                "detail": "no test suite detected — unified tree is UNVERIFIED (not a pass)"}
    if isinstance(cmd, str):
        cmd = cmd.split()
    r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
    ok = r.returncode == 0
    tail = (r.stdout or r.stderr or "").splitlines()[-1:] or [""]
    return {"ok": ok, "ran": True, "status": "green" if ok else "RED",
            "returncode": r.returncode, "detail": tail[0][:200]}


# ── lane reconciliation ─────────────────────────────────────────────────────

def _main_clean_on_main(root):
    cur = wg._git_out(root, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = wg._git_out(root, "status", "--porcelain", "--untracked-files=no")
    return cur == "main" and not dirty


# ── P5 collapse safety guards (impl-converge-safe-merge-guards-v1) ───────────

HARNESS_MASTER_REL = "WAI-Harness/.harness-master"


def _has_upstream(root):
    return wg._git(root, "rev-parse", "--abbrev-ref", "@{upstream}").returncode == 0


def _collapse_precheck(root, base=None, session_id=None):
    """Refuse a P5 collapse that would clobber active main. Reuses worktree_guard's
    clean-main notion (main must be clean AND on main). Additionally refuses when main is
    AHEAD of origin AND another lane is live — another session's in-flight work — but NOT
    ahead alone (a dogfood main is routinely ahead of origin). Defer, never force-merge."""
    if not _main_clean_on_main(root):
        return {"ok": False, "reason": "main is dirty or not on main; deferring collapse"}
    if base is not None and _has_upstream(root):
        ahead = wg._git_out(root, "rev-list", "--count", "@{upstream}..HEAD") or "0"
        if ahead != "0":
            others = [s for s in wg.live_lanes(base) if s != session_id]
            if others:
                return {"ok": False, "reason": f"main is ahead of origin ({ahead}) with "
                        f"{len(others)} live lane(s); deferring to avoid clobbering active work",
                        "ahead": int(ahead), "live_lanes": others}
    return {"ok": True}


def _assert_harness_master_untracked(root):
    """The per-machine master pin must NEVER be tracked on main (fix-harness-master-pin-
    untrack-v1). If a merged lane re-introduced it as a tracked file, drop it from the index
    and commit the removal so the collapse doesn't propagate the regression fleet-wide."""
    if wg._git(root, "ls-files", "--error-unmatch", HARNESS_MASTER_REL).returncode != 0:
        return {"was_tracked": False}
    wg._git(root, "rm", "--cached", "--quiet", HARNESS_MASTER_REL)
    wg._git(root, "commit", "-m",
            "converge: untrack per-machine .harness-master pin (never track on main) "
            "(impl-converge-safe-merge-guards-v1)")
    return {"was_tracked": True, "untracked": True}


def _archive_tag_lane(root, branch):
    """Durably preserve a lane that failed to collapse as an archive/* tag BEFORE any
    cleanup, so its auto-committed work can never be lost to the conflict."""
    sha = wg._git_out(root, "rev-parse", branch)
    if not sha:
        return None
    tag = "archive/collapse-conflict-" + branch.replace("/", "-")
    wg._git(root, "tag", "-f", tag, sha)
    return tag


def _merge_branch_only(root, branch):
    """Merge a committed branch into main WITHOUT removing its worktree (for an ACTIVE
    competitor that keeps running). Guarded: main must be clean + on main."""
    if not _branch_into_main_safe(root, branch):
        return {"ok": False, "error": "main not clean/on-main or branch missing"}
    if branch in wg._git_out(root, "branch", "--merged", "main"):
        return {"ok": True, "merged": False, "reason": "already merged"}
    r = wg._git(root, "merge", "--no-ff", "-m", f"converge {branch}", branch)
    if r.returncode != 0:
        wg._git(root, "merge", "--abort")
        return {"ok": False, "error": f"merge conflict: {r.stderr.strip()[:160]}"}
    return {"ok": True, "merged": True}


def _branch_into_main_safe(root, branch):
    return _main_clean_on_main(root) and wg._branch_exists(root, branch)


def _commit_dirty_lane(wt_path, branch):
    """Commit a stale/dead lane's uncommitted work to its branch so reaping loses nothing."""
    if not wg._git_out(wt_path, "status", "--porcelain"):
        return {"committed": False, "reason": "clean"}
    wg._git(wt_path, "add", "-A")
    r = wg._git(wt_path, "commit", "-m", f"converge: auto-commit stale lane {branch}")
    return {"committed": r.returncode == 0}


def _reconcile_lugs(repo):
    """Best-effort lug set-union on the unified tree (runs in the merged repo)."""
    tool = _HERE / "lug_status_reconcile.py"
    if not tool.exists():
        return {"ran": False}
    try:
        r = subprocess.run([sys.executable, str(tool), "--apply", "--json",
                            "--session", "converge", "--root", str(repo)],
                           cwd=repo, capture_output=True, text=True, timeout=120)
        return {"ran": True, "rc": r.returncode}
    except Exception as e:
        return {"ran": False, "error": str(e)}


def reconcile_lane(repo, name, verify=True, test_cmd=None, base=None, session_id=None):
    """P5 single-lane collapse: merge one worktree's committed branch into main, then
    re-verify the unified tree. Returns a structured report.

    Safe under concurrency (impl-converge-safe-merge-guards-v1): pre-checks that main is
    clean and not clobbering another live lane's in-flight work; on merge conflict the
    shared checkout is aborted clean, the lane is archive-tagged, and a notice is routed;
    a re-tracked per-machine .harness-master pin is dropped before the collapse ships."""
    root = wg.repo_root(repo)
    branch = f"{wg.WORKTREE_BRANCH_PREFIX}{name}"
    pre = _collapse_precheck(root, base, session_id)
    if not pre["ok"]:
        return {"name": name, "branch": branch, "ok": False, "deferred": True, "precheck": pre}
    fin = wg.session_worktree_finish(root, name, merge=True)
    rep = {"name": name, "branch": branch, "merge": fin}
    if not fin.get("ok"):
        rep["ok"] = False
        if fin.get("conflict"):
            # merge already aborted in worktree_guard (no MERGE_HEAD left); durably preserve
            # the lane, then route a notice so the conflict is surfaced, never swallowed.
            rep["conflict_abort"] = {"lane_preserved": True,
                                     "archive_tag": _archive_tag_lane(root, branch)}
            if base:
                rep["notice"] = signal(base, session_id or "converge", from_sid="converge",
                                       kind="collapse_conflict")
        return rep
    rep["harness_master"] = _assert_harness_master_untracked(root)
    rep["lugs"] = _reconcile_lugs(root)
    if verify:
        rep["verify"] = verify_unified(root, test_cmd)
        rep["ok"] = bool(rep["verify"]["ok"])
    else:
        rep["ok"] = True
    return rep


# ── the lead loop ───────────────────────────────────────────────────────────

def converge(base, session_id, repo=".", my_worktree=None, verify=True,
             test_cmd=None, active_window=ACTIVE_WINDOW_S, lease_seconds=DEFAULT_LEASE_S,
             confirm_absorb=None):
    """Converge competitor lanes into one tree.

    CONSENT GATE (risk-tolerance-never-absorb-a-fork-silently). A parked lane is
    the operator's FORKED WORK, not litter to reclaim. He reported in s138 that
    forks were being absorbed back without his interaction, and he was right: the
    savepoint ceremony ran this function on its exit-10 path with no consent step.

    Ceremony prose alone is not a gate — a prose instruction is advice a future
    agent can skip, and this one had been skipped for months. So the refusal
    lives HERE, where it fails closed regardless of who calls it.

    `confirm_absorb` must name the session ids being absorbed (or the sentinel
    "ALL"). Without it, this returns a refusal listing the candidates and changes
    nothing. Absorption is not reversible by checkout; keeping a lane parked
    always is.
    """
    root = wg.repo_root(repo)
    lanes = wg.live_lanes(base)
    competitors = {s: m for s, m in lanes.items() if not _is_self(s, m, session_id)}
    others_wts = [w for w in wg.session_worktrees(root) if w["name"] != my_worktree]

    # 1. zero-cost common path: nobody to converge with.
    if not competitors and not others_wts:
        return {"ok": True, "lead": False, "reason": "no-competitors", "converged": []}

    # 2. CONSENT GATE — refuse to absorb anything the operator has not named.
    # Covers stale LANES *and* dirty parked WORKTREES. Gating lanes alone left the
    # oldest forks unprotected: once a lane aged past its TTL it stopped being a
    # candidate, and its worktree fell through to auto-commit + finish untouched
    # by any consent step. See worktree_absorption_candidates().
    cands = absorb_consent_required(base, session_id, root, my_worktree, active_window)
    if cands:
        approved = set(confirm_absorb or [])
        if "ALL" not in approved:
            unapproved = [c for c in cands if not (set(c["confirm_keys"]) & approved)]
            if unapproved:
                return {
                    "ok": False,
                    "lead": False,
                    "reason": "absorb-not-confirmed",
                    "candidates": unapproved,
                    "advice": (
                        "These are PARKED FORKS, not litter — absorbing one destroys a thread "
                        "the operator intended to return to. Surface them as a choice and "
                        "re-run with --confirm-absorb <session-id|worktree-name> (repeatable) "
                        "for each fork he approves, or leave them parked. Keeping a fork parked "
                        "is always safe; absorbing is not reversible by checkout — a 'worktree' "
                        "candidate holds UNCOMMITTED work that converge would commit for it."),
                }

    # 2. exactly-one-lead gate.
    lk = acquire_lock(base, session_id, lease_seconds)
    if not lk["acquired"]:
        return {"ok": True, "lead": False, "reason": "not-lead", "lock_held_by": lk.get("holder"),
                "advice": "another lead is converging; close your OWN lane only (commit-mine scoped)."}

    report = {"ok": True, "lead": True, "converged": [], "reconciled_active": [],
              "signalled": [], "reaped": [], "absorbed_laneonly": [], "verify": None}
    now = wg._utcnow()
    handled_sids = set()
    try:
        for w in others_wts:
            sid, meta = _match_lane(w["name"], competitors)
            if sid:
                handled_sids.add(sid)
            live = _classify_lane(meta, now, active_window) if meta else "dead"
            branch = w["branch"]
            if live == "active":
                # never force-close a live session: merge its COMMITTED work, leave it running
                if w["ahead"] and not w["dirty"]:
                    m = _merge_branch_only(root, branch)
                    report["reconciled_active"].append({"name": w["name"], "sid": sid, "merge": m})
                if sid:
                    signal(base, sid, from_sid=session_id, kind="main_advanced")
                    report["signalled"].append(sid)
                continue
            # idle / stale / dead / unmatched -> cooperatively converge into main
            if w["dirty"]:
                _commit_dirty_lane(w["path"], branch)
                w = next((x for x in wg.session_worktrees(root) if x["name"] == w["name"]), w)
            fin = wg.session_worktree_finish(root, w["name"], merge=True)
            report["converged"].append({"name": w["name"], "sid": sid, "liveness": live, "merge": fin})
            if fin.get("ok"):
                report["reaped"].append(w["name"])
            if sid:
                signal(base, sid, from_sid=session_id, kind="converge_request")
                wg.lane_unregister(base, sid)

        # Absorb worktree-LESS competitor lanes whose opener is not open: nothing to
        # merge (no worktree/branch), but the stale registry entry must be cleared so it
        # stops counting as a live competitor and blocking future leads. ACTIVE (beating)
        # lanes are left untouched.
        for sid, meta in competitors.items():
            if sid in handled_sids:
                continue
            if _lane_open(meta, now, active_window):
                continue
            wg.lane_unregister(base, sid)
            report["absorbed_laneonly"].append({"sid": sid, "wai_session": meta.get("wai_session"),
                                                "reason": "opening session not open; no worktree to merge"})

        # NB: no blanket session_worktree_reap here — idle/dead lanes are finished
        # inline above, and a blanket reap would also remove an ACTIVE competitor's
        # worktree (its branch is now merged + clean), force-closing a live session.
        # A merged lane may have carried a tracked per-machine pin; drop it before shipping
        # so the collapse never re-tracks .harness-master on main. (impl-converge-safe-merge-guards-v1)
        report["harness_master"] = _assert_harness_master_untracked(root)
        report["lugs"] = _reconcile_lugs(root)

        # 3. unify-then-VERIFY: re-test the merged tree before declaring done.
        if verify:
            v = verify_unified(root, test_cmd)
            report["verify"] = v
            if not v["ok"]:
                # RED union: hold the lock for fix-forward; DO NOT release/ship.
                report["ok"] = False
                report["lead_must_fix"] = (
                    "Unified tree failed verification — merge-lock RETAINED. Fix-forward on main, "
                    "then re-run converge. (Lease auto-expires so this cannot deadlock the fleet.)")
                return report
        release_lock(base, session_id)
        return report
    except Exception as e:  # never strand the lock on an unexpected error
        release_lock(base, session_id)
        return {"ok": False, "lead": True, "error": str(e), "partial": report}


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description="CSRP P6 convergent closeout")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_base(p, sid=True):
        p.add_argument("--base", required=True)
        if sid:
            p.add_argument("--session-id", required=True)

    s = sub.add_parser("status"); add_base(s); s.add_argument("--repo", default="."); s.add_argument("--active-window", type=int, default=ACTIVE_WINDOW_S)
    cd = sub.add_parser("candidates"); add_base(cd); cd.add_argument("--active-window", type=int, default=ACTIVE_WINDOW_S)
    cd.add_argument("--repo", default="."); cd.add_argument("--my-worktree", default=None)
    a = sub.add_parser("acquire-lock"); add_base(a); a.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_S)
    r = sub.add_parser("release-lock"); add_base(r)
    sg = sub.add_parser("signal"); sg.add_argument("--base", required=True); sg.add_argument("--target", required=True); sg.add_argument("--from", dest="frm", default=""); sg.add_argument("--kind", default="converge_request")
    ds = sub.add_parser("drain-signals"); add_base(ds)
    rl = sub.add_parser("reconcile-lane"); rl.add_argument("--repo", default="."); rl.add_argument("--name", required=True); rl.add_argument("--no-verify", action="store_true"); rl.add_argument("--test-cmd", default=None); rl.add_argument("--base", default=None); rl.add_argument("--session-id", default=None)
    cv = sub.add_parser("converge"); add_base(cv); cv.add_argument("--repo", default="."); cv.add_argument("--my-worktree", default=None); cv.add_argument("--no-verify", action="store_true"); cv.add_argument("--test-cmd", default=None); cv.add_argument("--active-window", type=int, default=ACTIVE_WINDOW_S); cv.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_S)
    cv.add_argument("--confirm-absorb", action="append", default=None, metavar="SESSION_ID|WORKTREE",
                    help="operator-confirmed fork to absorb, named by session id OR worktree name "
                         "(repeatable; 'ALL' to confirm every candidate). REQUIRED when candidates "
                         "exist — a parked lane or dirty worktree is a fork, not litter, and "
                         "absorbing it is not reversible by checkout.")

    args = ap.parse_args(argv)
    if args.cmd == "candidates":
        root = wg.repo_root(args.repo)
        lane_c = absorption_candidates(args.base, args.session_id, args.active_window)
        wt_c = worktree_absorption_candidates(args.base, args.session_id, root,
                                              args.my_worktree, args.active_window)
        print(json.dumps({"absorption_candidates": lane_c,
                          "parked_worktrees": wt_c,
                          "count": len(lane_c) + len(wt_c)}, indent=2))
        # 10 = something needs consent before converge may run; 0 = nothing to absorb.
        # Parked worktrees count: reporting 0 while converge would auto-commit them is
        # exactly the false all-clear this gate exists to end.
        return 10 if (lane_c or wt_c) else 0
    if args.cmd == "status":
        out = status(args.base, args.session_id, args.repo, args.active_window)
    elif args.cmd == "acquire-lock":
        out = acquire_lock(args.base, args.session_id, args.lease_seconds)
    elif args.cmd == "release-lock":
        out = release_lock(args.base, args.session_id)
    elif args.cmd == "signal":
        out = signal(args.base, args.target, args.frm, args.kind)
    elif args.cmd == "drain-signals":
        out = drain_signals(args.base, args.session_id)
    elif args.cmd == "reconcile-lane":
        out = reconcile_lane(args.repo, args.name, verify=not args.no_verify,
                             test_cmd=args.test_cmd, base=args.base, session_id=args.session_id)
    elif args.cmd == "converge":
        out = converge(args.base, args.session_id, args.repo, args.my_worktree,
                       verify=not args.no_verify, test_cmd=args.test_cmd,
                       active_window=args.active_window, lease_seconds=args.lease_seconds,
                       confirm_absorb=args.confirm_absorb)
    else:
        ap.error("unknown command")
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
