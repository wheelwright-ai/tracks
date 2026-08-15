#!/usr/bin/env python3
"""path_claims.py — record which paths each session writes, and measure real collision rate.

STEP 0 OF change-isolation-is-a-value-curve-not-a-coexistence-switch-v1. This tool is
DELIBERATELY OBSERVE-ONLY: it records and it reports, and it gates NOTHING. Nothing here can
refuse a write, create a worktree, or change what any session is allowed to do.

WHY OBSERVE FIRST, at length, because the temptation to skip this step is the whole risk:

  wai-enter.sh isolates a session when `_LANE_LIVE >= 1` — when ANOTHER SESSION IS OPEN, not
  when another session touches the same files. Measured 2026-08-06: 56 of the last 200 commits
  on main were merges. 28% of main's traffic is the cost of that rule.

  The obvious fix is to isolate only on real overlap. But NOBODY KNOWS THE OVERLAP RATE. If
  concurrent sessions collide constantly, the current rule is roughly right and merges are the
  honest price. If they almost never collide, the rule is burning a quarter of main's history
  on nothing. Those two worlds demand opposite gates, and picking between them by intuition
  means guessing at whether main is safe.

  So: record first, gate later, and let the number set the tier boundaries.

WHAT IT RECORDS. One JSONL line per observation: session id, wall time, and the sorted set of
repo-relative paths that session has touched (uncommitted edits, untracked files, plus
anything it has committed since its own first observation). Append-only, so a crashed session
loses nothing, and two writers cannot lose each other's line to a read-modify-write race.

WHAT `report` ANSWERS. Over every pair of sessions whose observation windows OVERLAPPED IN
TIME — the pairs the current rule would have isolated — how many actually shared a path? That
ratio is the number the curve gets built on. A pair that overlapped in time but not in paths
is a merge that never needed to exist.

Usage:
    python3 path_claims.py --base BASE observe [--session-id ID] [--root .]
    python3 path_claims.py --base BASE claims [--json]
    python3 path_claims.py --base BASE report [--json]
Exit: 0 always for observe (a recorder must never break the session it observes) | 2 on a
usage error for the read commands.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys

STORE_REL = "runtime/path-claims.jsonl"

# Paths that say nothing about what a session is BUILDING. Recording them would make every
# pair of sessions look collided, because every session writes its own track and runtime
# state. That noise would drown the exact signal this tool exists to measure.
IGNORED_PREFIXES = (
    "WAI-Harness/spoke/local/runtime/",
    "WAI-Harness/spoke/local/sessions/",
    "WAI-Harness/hub/local/ap-runs/",
    ".git/",
)


def _store_path(base: str) -> str:
    return os.path.join(base, STORE_REL)


def _git(root: str, *args) -> str:
    try:
        proc = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=30)
        return proc.stdout if proc.returncode == 0 else ""
    except Exception:  # noqa: BLE001 -- a recorder never raises into its caller
        return ""


def _interesting(path: str) -> bool:
    return bool(path) and not path.startswith(IGNORED_PREFIXES)


def touched_paths(root: str, since_sha: str = "") -> list:
    """Repo-relative paths this working tree has touched.

    Uncommitted + untracked covers work in flight. `since_sha..HEAD` covers work the session
    has already committed — without it, a tidy session that commits as it goes would look
    like it touched nothing, which is the same class of bug as the delta ceremony reading the
    working tree and calling a six-commit session conversation-only.
    """
    paths = set()
    for line in _git(root, "diff", "--name-only", "HEAD").splitlines():
        paths.add(line.strip())
    for line in _git(root, "ls-files", "--others", "--exclude-standard").splitlines():
        paths.add(line.strip())
    if since_sha:
        for line in _git(root, "diff", "--name-only", f"{since_sha}..HEAD").splitlines():
            paths.add(line.strip())
    return sorted(p for p in paths if _interesting(p))


def _resolve_session_id(base: str, cc_session_id: str = "") -> str:
    """Which WAI session is writing right now.

    Resolution order, most authoritative first:

      1. runtime/sessions-live.json `lanes.<cc_sid>.wai_session` -- the launcher registers
         the mapping at t=0, so it is a statement rather than an inference.
      2. The single live lane, when there is exactly one. Unambiguous by construction.
      3. Newest-written track file, as a last resort.

    Newest-track USED to be the only rule, and it is wrong often enough to matter: this
    spoke had EIGHT session dirs written on one evening, most of them one line long, while
    exactly one lane was actually live. Attributing observations by mtime picked a dead
    stub over the running session -- and a collision report built on misattributed paths
    measures nothing at all.
    """
    live = os.path.join(base, "runtime", "sessions-live.json")
    try:
        reg = json.load(open(live, encoding="utf-8"))
        lanes = reg.get("lanes") or {}
        if cc_session_id and cc_session_id in lanes:
            sid = (lanes[cc_session_id] or {}).get("wai_session")
            if sid:
                return sid
        if len(lanes) == 1:
            sid = (next(iter(lanes.values())) or {}).get("wai_session")
            if sid:
                return sid
    except Exception:  # noqa: BLE001 -- fall through to the weaker signal
        pass

    import glob as _glob
    tracks = _glob.glob(os.path.join(base, "sessions", "session-*", "track.jsonl"))
    if not tracks:
        return ""
    newest = max(tracks, key=lambda t: os.path.getmtime(t))
    return os.path.basename(os.path.dirname(newest))


def _read_lines(base: str) -> list:
    path = _store_path(base)
    if not os.path.isfile(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001 -- one torn line must not blind the whole report
                continue
    return out


def observe(base: str, session_id: str, root: str = ".") -> dict:
    """Append one observation. Never raises; a recorder that breaks writes is worse than none."""
    prior = [r for r in _read_lines(base) if r.get("session_id") == session_id]
    # The session's own first observation pins its baseline sha, so `since` is stable even as
    # the session commits. Re-deriving it each time would make committed work vanish from the
    # window the moment HEAD moved.
    since = prior[0].get("base_sha", "") if prior else _git(root, "rev-parse", "HEAD").strip()

    record = {
        "session_id": session_id,
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "base_sha": since,
        "paths": touched_paths(root, since),
    }
    store = _store_path(base)
    os.makedirs(os.path.dirname(store), exist_ok=True)
    # Append-only, one line, opened per call: two concurrent sessions cannot clobber each
    # other the way a read-modify-write of a JSON object would.
    with open(store, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


def claims(base: str) -> dict:
    """Latest known path set per session, newest observation wins."""
    latest = {}
    for rec in _read_lines(base):
        sid = rec.get("session_id")
        if not sid:
            continue
        if sid not in latest or rec.get("ts", "") >= latest[sid].get("ts", ""):
            latest[sid] = rec
    return {
        "sessions": len(latest),
        "claims": [
            {"session_id": s, "ts": r.get("ts"), "path_count": len(r.get("paths") or []),
             "paths": r.get("paths") or []}
            for s, r in sorted(latest.items())
        ],
    }


def report(base: str) -> dict:
    """The measurement: of session pairs that overlapped IN TIME, how many shared a path?

    Time-overlap is what the current rule reacts to, so it is the correct denominator. Every
    time-overlapping pair with an empty path intersection is a worktree and a merge the curve
    would have avoided.
    """
    windows = {}
    for rec in _read_lines(base):
        sid = rec.get("session_id")
        ts = rec.get("ts", "")
        if not sid or not ts:
            continue
        w = windows.setdefault(sid, {"first": ts, "last": ts, "paths": set()})
        w["first"] = min(w["first"], ts)
        w["last"] = max(w["last"], ts)
        w["paths"].update(rec.get("paths") or [])

    ids = sorted(windows)
    concurrent, collided, detail = 0, 0, []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            wa, wb = windows[a], windows[b]
            # Half-open overlap: touching endpoints are not concurrency.
            if not (wa["first"] < wb["last"] and wb["first"] < wa["last"]):
                continue
            concurrent += 1
            shared = sorted(wa["paths"] & wb["paths"])
            if shared:
                collided += 1
            detail.append({"a": a, "b": b, "collided": bool(shared),
                           "shared_paths": shared[:20], "shared_count": len(shared)})

    rate = (collided / concurrent) if concurrent else None
    return {
        "sessions_observed": len(ids),
        "concurrent_pairs": concurrent,
        "collided_pairs": collided,
        "collision_rate": rate,
        "needless_isolations": concurrent - collided,
        "verdict": (
            "insufficient data — no time-overlapping session pairs observed yet"
            if not concurrent else
            f"{collided}/{concurrent} time-overlapping pairs actually shared a path "
            f"({rate:.0%}); the other {concurrent - collided} would have been isolated for nothing"
        ),
        "pairs": detail,
    }


def main(argv=None):
    # --json on a shared parent so it is accepted on EITHER side of the subcommand. Same
    # reasoning as savepoint_claim.py: `... report --json` is the order every caller reaches
    # for first, and a usage error there reads as a broken tool.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true")

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], parents=[common])
    ap.add_argument("--base", required=True, help="spoke local base (the {BASE} the ceremony resolves)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_obs = sub.add_parser("observe", parents=[common],
                           help="append one observation (records only; gates nothing)")
    p_obs.add_argument("--session-id", default="")
    p_obs.add_argument("--root", default=".")
    p_obs.add_argument("--cc-session-id", default="",
                       help="Claude Code session id, for authoritative lane resolution")
    sub.add_parser("claims", parents=[common], help="latest path set per session")
    sub.add_parser("report", parents=[common],
                   help="measured collision rate across time-overlapping pairs")
    args = ap.parse_args(argv)

    if args.cmd == "observe":
        sid = args.session_id
        if not sid:
            # Prefer the WAI SESSION DIR over runtime/session-guard.json. That guard is a
            # long-lived file no session resets: MEASURED 2026-08-06 it still carried
            # session_id "mario-2026-04-14-164612" from APRIL, so every session on this
            # spoke would have recorded its paths under one shared identity -- and a
            # collision report where every session is the same session measures nothing.
            sid = _resolve_session_id(args.base, args.cc_session_id)
            if not sid:
                guard = os.path.join(args.base, "runtime", "session-guard.json")
                try:
                    sid = json.load(open(guard, encoding="utf-8")).get("session_id", "")
                except Exception:  # noqa: BLE001
                    sid = ""
        if not sid:
            return 0  # nothing to attribute an observation to; stay silent, never fail a write
        try:
            rec = observe(args.base, sid, args.root)
        except Exception as exc:  # noqa: BLE001 -- observation must never break the session
            print(f"path_claims: observe skipped — {exc}", file=sys.stderr)
            return 0
        if args.json:
            print(json.dumps(rec, indent=2))
        return 0

    if args.cmd == "claims":
        rep = claims(args.base)
        if args.json:
            print(json.dumps(rep, indent=2))
        else:
            print(f"path claims: {rep['sessions']} session(s) observed")
            for c in rep["claims"]:
                print(f"  {c['session_id']}  {c['path_count']} path(s)  @{c['ts']}")
        return 0

    rep = report(args.base)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    print(f"collision report: {rep['verdict']}")
    print(f"  sessions observed:   {rep['sessions_observed']}")
    print(f"  concurrent pairs:    {rep['concurrent_pairs']}")
    print(f"  collided pairs:      {rep['collided_pairs']}")
    print(f"  needless isolations: {rep['needless_isolations']}")
    for p in rep["pairs"]:
        if p["collided"]:
            print(f"  [collide] {p['a']} x {p['b']} — {p['shared_count']} shared path(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
