#!/usr/bin/env python3
"""session_fork.py — branch one session into separately attributable threads.

THE PROBLEM. The operator moves between topics inside a single session; that is
his stated working style, encoded as `work-style-operator-multithreads-topics`.
The wheel did not absorb it. One session produced ONE track, ONE savepoint chain
and ONE focus lock, so several topics blurred into a record no resume could
attribute to a thread — and a resume that cannot tell which thread it belongs to
has to re-read everything to find out.

WHAT WAS ALREADY THERE, AND WHAT WAS NOT. `worktree_guard.py` lanes already give
ISOLATION: two sessions cannot stomp each other's files. What was missing is
ATTRIBUTION: a lane carries no topic, no parent, and no per-thread track. So this
tool deliberately does NOT re-implement isolation. It adds the thread record on
top of the lane substrate.

WHY A FORK IS NOT A NEW SESSION. A Claude Code session id is minted by the host,
not by us — we cannot conjure one. So a fork here is a THREAD: its own directory,
track, savepoint chain and focus lock, parented to the session that spawned it.
That is what makes forking cheaper than restarting, which is the entire
justification for the feature: the child inherits the parent's wakeup, so the
wakeup ceremony is paid once rather than once per topic.

WHAT THIS TOOL WILL NOT DO. It never merges, absorbs, or reaps anything. Joining
a fork closes its RECORD and says so; reconciling git lives in
`converge_closeout.py`, behind the consent gate added alongside this work
(`risk-tolerance-never-absorb-a-fork-silently`). A parked fork is the operator's
work, and nothing here reclaims it.

Usage:
    session_fork.py fork --label "oracle coverage" [--parent SESSION_ID]
    session_fork.py list [--json]
    session_fork.py join --fork FORK_ID [--outcome TEXT]
    session_fork.py active
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import worktree_guard as wg  # noqa: E402

FORKS_DIR = "runtime/forks"          # fork manifests, relative to spoke local base
SESSIONS_DIR = "sessions"
ACTIVE_POINTER = "runtime/active-fork.json"


# ---- paths ------------------------------------------------------------------

def _base(base):
    return wg._canonical_base(base)


def _forks_dir(base):
    return os.path.join(_base(base), FORKS_DIR)


def _fork_path(base, fork_id):
    return os.path.join(_forks_dir(base), f"{fork_id}.json")


def _session_dir(base, sid):
    return os.path.join(_base(base), SESSIONS_DIR, sid)


def _slug(label):
    """Stable, filesystem-safe topic slug. Short on purpose — it lands in a path."""
    s = re.sub(r"[^a-z0-9]+", "-", (label or "").lower()).strip("-")
    return "-".join(s.split("-")[:5]) or "thread"


# ---- fork -------------------------------------------------------------------

def fork(base, parent_session_id, label, now_iso=None):
    """Create a child thread of `parent_session_id`.

    Idempotent on (parent, slug): forking the same topic twice returns the
    existing thread rather than splitting the record a second time. Re-forking a
    topic is nearly always a mistake by an agent that lost its place, and
    silently creating `topic`, `topic-2`, `topic-3` is how a record becomes
    unreadable.
    """
    if not parent_session_id:
        return {"ok": False, "reason": "no-parent-session"}
    if not (label or "").strip():
        return {"ok": False, "reason": "no-label",
                "advice": "a fork without a topic label defeats the purpose — it is what "
                          "makes the thread attributable later"}

    now = now_iso or wg._iso()
    slug = _slug(label)
    fork_id = f"{parent_session_id}--{slug}"

    os.makedirs(_forks_dir(base), exist_ok=True)
    path = _fork_path(base, fork_id)
    if os.path.exists(path):
        existing = json.load(open(path))
        return {"ok": True, "reason": "already-forked", "fork": existing,
                "advice": "this topic already has a thread; continuing it rather than "
                          "splitting the record again"}

    sess_dir = _session_dir(base, fork_id)
    os.makedirs(sess_dir, exist_ok=True)

    rec = {
        "fork_id": fork_id,
        "parent_session_id": parent_session_id,
        "fork_label": label.strip(),
        "slug": slug,
        "status": "open",
        "created_at": now,
        "joined_at": None,
        "outcome": None,
        "track_path": os.path.join(sess_dir, "track.jsonl"),
        # Inheriting the parent's wakeup is the whole point: a fork must be
        # cheaper than a restart, or the operator will just restart.
        "inherits_wakeup_from": parent_session_id,
        "savepoints": [],
    }
    with open(path, "w") as fh:
        json.dump(rec, fh, indent=2, ensure_ascii=False)

    # Seed the child track with a backref so an entry is attributable on its own,
    # without needing the fork manifest to interpret it.
    seed = {"event": "fork_opened", "ts": now, "source": "session_fork",
            "fork_id": fork_id, "parent_session_id": parent_session_id,
            "fork_label": label.strip(),
            "note": "thread opened from parent session; wakeup inherited, not re-run"}
    with open(rec["track_path"], "a") as fh:
        fh.write(json.dumps(seed, ensure_ascii=False) + "\n")

    _set_active(base, fork_id)
    return {"ok": True, "reason": "forked", "fork": rec}


# ---- active pointer ---------------------------------------------------------

def _set_active(base, fork_id):
    p = os.path.join(_base(base), ACTIVE_POINTER)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        json.dump({"active_fork": fork_id, "ts": wg._iso()}, fh, indent=2)


def active(base):
    p = os.path.join(_base(base), ACTIVE_POINTER)
    if not os.path.exists(p):
        return {"ok": True, "active_fork": None}
    try:
        return {"ok": True, **json.load(open(p))}
    except (json.JSONDecodeError, OSError):
        return {"ok": True, "active_fork": None, "note": "active pointer unreadable"}


# ---- list -------------------------------------------------------------------

def list_forks(base, parent_session_id=None):
    """All threads, newest first. Open threads are PARKED WORK, never litter."""
    d = _forks_dir(base)
    out = []
    if os.path.isdir(d):
        for name in sorted(os.listdir(d)):
            if not name.endswith(".json"):
                continue
            try:
                rec = json.load(open(os.path.join(d, name)))
            except (json.JSONDecodeError, OSError):
                continue
            if parent_session_id and rec.get("parent_session_id") != parent_session_id:
                continue
            tp = rec.get("track_path") or ""
            rec["track_entries"] = sum(1 for _ in open(tp)) if os.path.exists(tp) else 0
            out.append(rec)
    out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    act = active(base).get("active_fork")
    return {"ok": True, "active_fork": act, "count": len(out),
            "open": [r for r in out if r.get("status") == "open"],
            "joined": [r for r in out if r.get("status") == "joined"],
            "forks": out}


# ---- join -------------------------------------------------------------------

def join(base, fork_id, outcome=None, now_iso=None):
    """Close a thread's RECORD.

    Explicitly NOT a git merge and NOT an absorption. This marks the thread
    finished and records what came of it; reconciling branches stays in
    converge_closeout.py behind its consent gate. Keeping those separate is what
    stops "I'm done with this topic" from ever meaning "reclaim my work".
    """
    path = _fork_path(base, fork_id)
    if not os.path.exists(path):
        return {"ok": False, "reason": "unknown-fork", "fork_id": fork_id}
    rec = json.load(open(path))
    if rec.get("status") == "joined":
        return {"ok": True, "reason": "already-joined", "fork": rec}

    rec["status"] = "joined"
    rec["joined_at"] = now_iso or wg._iso()
    rec["outcome"] = outcome
    with open(path, "w") as fh:
        json.dump(rec, fh, indent=2, ensure_ascii=False)

    tp = rec.get("track_path")
    if tp:
        with open(tp, "a") as fh:
            fh.write(json.dumps({"event": "fork_joined", "ts": rec["joined_at"],
                                 "source": "session_fork", "fork_id": fork_id,
                                 "outcome": outcome}, ensure_ascii=False) + "\n")

    if active(base).get("active_fork") == fork_id:
        _set_active(base, rec.get("parent_session_id"))
    return {"ok": True, "reason": "joined", "fork": rec,
            "note": "record closed. Branch reconciliation, if any, is a separate "
                    "explicit step in converge_closeout.py"}


# ---- cli --------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Branch a session into attributable threads")
    ap.add_argument("--base", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fork")
    f.add_argument("--label", required=True, help="topic label — what this thread is about")
    f.add_argument("--parent", default=os.environ.get("WAI_SESSION_ID", ""))

    ls = sub.add_parser("list")
    ls.add_argument("--parent", default=None)
    ls.add_argument("--json", action="store_true")

    j = sub.add_parser("join")
    j.add_argument("--fork", required=True)
    j.add_argument("--outcome", default=None)

    sub.add_parser("active")
    args = ap.parse_args(argv)

    if args.cmd == "fork":
        out = fork(args.base, args.parent, args.label)
    elif args.cmd == "list":
        out = list_forks(args.base, args.parent)
        if not args.json:
            print(f"Threads: {out['count']} ({len(out['open'])} open, {len(out['joined'])} joined)")
            for r in out["forks"]:
                mark = "*" if r["fork_id"] == out["active_fork"] else " "
                print(f" {mark} [{r['status']:6s}] {r['fork_label']:32s} "
                      f"{r['track_entries']:3d} entries  {r['fork_id']}")
            if out["open"]:
                print("\nOpen threads are PARKED WORK, not litter — nothing here reclaims them.")
            return 0
    elif args.cmd == "join":
        out = join(args.base, args.fork, args.outcome)
    else:
        out = active(args.base)

    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
