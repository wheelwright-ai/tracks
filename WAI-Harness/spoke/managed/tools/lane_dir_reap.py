#!/usr/bin/env python3
"""lane_dir_reap.py — remove stale runtime/lanes/<cc_sid>/ directories.

WHY THIS EXISTS (bug-track-records-zero-turns-and-mints-a-session-per-turn-v1,
MEASURED 2026-08-06): 1065 lane directories had accumulated under
WAI-Harness/spoke/local/runtime/lanes/, one per CC session id ever seen, going
back weeks. `worktree_guard.py lane-reap` (the `_cmd_lane_reap` CLI) only prunes
DEAD ENTRIES FROM THE REGISTRY (runtime/sessions-live.json) — it has never
touched the on-disk directories themselves. Nothing else does either. A
directory holds only ops bookkeeping (guard.json, .hb heartbeat, autosave/,
track-cursor.json) — no durable record worth archiving the way session_reaper.py
archives sessions/ (which hold track.jsonl, a real memory of what happened).
Once a lane's cc_sid is gone from the registry and its dir is old, the
directory is pure debris.

FLOORS (mirrors session_reaper.py's protections, same rationale):
  1. Never a lane still present in the LIVE registry (runtime/sessions-live.json
     `lanes` key) — that is an actually-live or recently-live session.
  2. Never a lane still present in the registry's `identity` map — a resumed
     conversation re-adopts by cc_sid (see worktree_guard._identity), so an
     identity-mapped cc_sid must survive even if its liveness lane was reaped.
  3. Never younger than --age-days (mtime of the directory itself — these dirs
     have no track.jsonl to cross-check against, unlike session_reaper's dirs).
  4. A cc_sid this run cannot read/parse safely is skipped, never guessed at.

Dry-run is the DEFAULT. Nothing is deleted unless --apply is passed. This is
plain filesystem debris (git-ignored, 0 files ever tracked) — no git operation
is involved, so there is nothing to preserve in history.

CLI:
    python3 lane_dir_reap.py --base WAI-Harness/spoke/local [--age-days 3] [--apply]
Exit: 0 on a clean run; 2 on an internal error.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import worktree_guard  # noqa: E402

DEFAULT_AGE_DAYS = 3


def _protected_cc_sids(base: str) -> set:
    reg = worktree_guard._load_registry(base)
    protected = set(reg.get("lanes", {}).keys()) | set(reg.get("identity", {}).keys())
    return protected


def plan(base: str, age_days: int = DEFAULT_AGE_DAYS):
    lanes_dir = os.path.join(base, "runtime", "lanes")
    if not os.path.isdir(lanes_dir):
        return {"lanes_dir": lanes_dir, "total": 0, "reap": [], "kept_live": [], "kept_young": []}

    protected = _protected_cc_sids(base)
    now = time.time()
    cutoff = now - age_days * 86400

    reap, kept_live, kept_young = [], [], []
    for name in sorted(os.listdir(lanes_dir)):
        p = os.path.join(lanes_dir, name)
        if not os.path.isdir(p):
            continue
        if name in protected:
            kept_live.append(name)
            continue
        try:
            mt = os.path.getmtime(p)
        except OSError:
            continue
        if mt >= cutoff:
            kept_young.append(name)
            continue
        reap.append(name)

    return {"lanes_dir": lanes_dir, "total": len(reap) + len(kept_live) + len(kept_young),
            "reap": reap, "kept_live": kept_live, "kept_young": kept_young}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True, help="data base, e.g. WAI-Harness/spoke/local")
    ap.add_argument("--age-days", type=int, default=DEFAULT_AGE_DAYS)
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry-run)")
    a = ap.parse_args(argv)

    try:
        p = plan(a.base, a.age_days)
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        return 2

    deleted = []
    if a.apply:
        for name in p["reap"]:
            target = os.path.join(p["lanes_dir"], name)
            try:
                shutil.rmtree(target)
                deleted.append(name)
            except OSError as e:
                print(json.dumps({"warn": f"could not remove {name}: {e}"}), file=sys.stderr)

    print(json.dumps({
        "lanes_dir": p["lanes_dir"],
        "total_dirs": p["total"],
        "kept_live_or_identity": len(p["kept_live"]),
        "kept_younger_than_days": {"days": a.age_days, "count": len(p["kept_young"])},
        "reap_candidates": len(p["reap"]),
        "applied": a.apply,
        "deleted": len(deleted),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
