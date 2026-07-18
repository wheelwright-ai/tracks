#!/usr/bin/env python3
"""closeout_session_status.py — complete this session's savepoint + mark the session clean.

Extracted from wai-closeout.md step 10d (2026-07-14). It was a 97-line inline
`python3 - <<'PYEOF'` heredoc, which is precisely the cost initiative-optimize-ceremonies-v1
P0-P2 set out to remove ("extract ~459L of inline Python to tools"): a ceremony is loaded
into the model's context every time it runs, so its length IS a per-run token cost.

WHY THIS EXTRACTION, RATHER THAN RAISING THE BUDGET: ceremony_token_budget.py exists, in its
own words, "so the next edit can't silently re-bloat the ceremony back to the 1455L closeout".
wai-closeout.md had crept to 1389 against a 1300 ceiling and the guard had been red for weeks
while the cut only PRINTED a warning. Raising the ceiling would have surrendered to the exact
re-bloat the guard was built to catch.

Behaviour is preserved verbatim from the heredoc, including the hard-stop semantics:
  - a lug_locks conflict with an ACTIVE savepoint exits 1 (hard stop)
  - a conflict with a PENDING savepoint auto-resolves (git history is truth) and is recorded

Usage:
    python3 closeout_session_status.py --base <spoke_local_base>
Exit: 0 ok | 1 conflict hard-stop | 2 error
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import shutil
import sys
from pathlib import Path


def _current_session_id(base: str) -> str:
    """Resolve this session's id via the worktree guard; '' when unresolvable."""
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        from worktree_guard import resolve_guard_path  # noqa: PLC0415

        guard_path = resolve_guard_path(base, os.environ.get("CLAUDE_CODE_SESSION_ID"))
        return json.load(open(guard_path)).get("session_id", "")
    except Exception:
        return ""


def _savepoint_files(base: str):
    return [
        f
        for f in sorted(glob.glob(f"{base}/initiatives/savepoints/**/*.json", recursive=True))
        if "completed" not in Path(f).parts
    ]


def run(base: str) -> int:
    state_path = f"{base}/WAI-State.json"
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with open(state_path) as f:
        state = json.load(f)

    current_session_id = _current_session_id(base)
    sp_files = _savepoint_files(base)

    my_sp_path, my_sp = None, None
    for f in sp_files:
        try:
            d = json.load(open(f))
            if current_session_id and (
                d.get("session_id") == current_session_id
                or d.get("claiming_session_id") == current_session_id
            ):
                my_sp_path, my_sp = f, d
                break
        except Exception:
            pass

    if my_sp:
        my_locks = set(my_sp.get("lug_locks", []))
        if my_locks:
            for f in sp_files:
                if f == my_sp_path:
                    continue
                try:
                    other = json.load(open(f))
                    if other.get("status") not in ("pending", "active"):
                        continue
                    conflicts = my_locks & set(other.get("lug_locks", []))
                    if not conflicts:
                        continue
                    if other.get("status") == "active":
                        print(
                            f"CONFLICT HARD-STOP: lug(s) {conflicts} also held by active "
                            f"savepoint {other['id']} (session {other.get('claiming_session_id','?')})"
                        )
                        print(
                            "Resolve: either complete the other session's savepoint first, or "
                            "remove the conflicting lug from lug_locks manually."
                        )
                        return 1
                    # Pending (unclaimed) — auto-resolve; git history is truth.
                    print(
                        f"  Conflict note: lug(s) {conflicts} also in pending savepoint "
                        f"{other['id']} — auto-resolved (git history is truth)"
                    )
                    my_sp.setdefault("conflicts", []).append(
                        {"sp_id": other["id"], "lugs": list(conflicts), "resolution": "auto_git"}
                    )
                except Exception:
                    pass

        my_sp["status"] = "completed"
        my_sp["completed_at"] = ts
        dest_dir = os.path.join(os.path.dirname(my_sp_path), "completed")
        dest = os.path.join(dest_dir, os.path.basename(my_sp_path))
        os.makedirs(dest_dir, exist_ok=True)
        with open(my_sp_path, "w") as f:
            json.dump(my_sp, f, indent=2)
        shutil.move(my_sp_path, dest)
        print(f"  Savepoint completed: {my_sp['id']} → {dest_dir}/")

        active_ids = [x for x in state.get("_savepoint", {}).get("active_ids", []) if x != my_sp["id"]]
        state["_savepoint"] = {"active_ids": active_ids, "count": len(active_ids)}
    elif sp_files:
        print(
            f"  No savepoint for session {current_session_id} — "
            f"{len(sp_files)} other savepoint(s) untouched"
        )
    else:
        state["_savepoint"] = {"active_ids": [], "count": 0}

    status = state.setdefault("_session_status", {})
    status["status"] = "clean"
    status["clean_at"] = ts
    status["interrupted_at"] = status.get("interrupted_at")
    status["interrupted_session"] = None
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    print(f"_session_status.status = clean @ {ts}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="spoke local base (the {BASE} the ceremony resolves)")
    a = ap.parse_args(argv)
    try:
        return run(a.base)
    except Exception as e:  # never a silent failure — closeout must SEE this
        print(f"closeout_session_status: ERROR {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
