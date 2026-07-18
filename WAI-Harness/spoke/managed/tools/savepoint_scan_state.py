#!/usr/bin/env python3
"""savepoint_scan_state.py — scan the lug locks + paper trail a savepoint records.

Extracted from wai-savepoint.md's sub-agent prompt, steps 2 (SCAN LUG LOCKS) and 3
(SCAN PAPER TRAIL) (2026-07-14). They were two inline `python3 -c "..."` blocks totalling
~48 lines, which is precisely the cost initiative-optimize-ceremonies-v1 P0-P2 set out to
remove ("extract ~459L of inline Python to tools"): a ceremony is loaded into the model's
context every time it runs, so its length IS a per-run token cost.

WHY THIS EXTRACTION, RATHER THAN RAISING THE BUDGET: ceremony_token_budget.py exists, in its
own words, "so the next edit can't silently re-bloat the ceremony back to the 1455L closeout",
and it says to "ratchet down, never up without cause". wai-savepoint.md had crept to 439
against a 430 ceiling. Raising the ceiling would have surrendered to the exact re-bloat the
guard was built to catch. This mirrors the sibling extraction closeout_session_status.py.

Behaviour is preserved VERBATIM from the two inline blocks, including their deliberately
lenient semantics:
  - every per-file read is best-effort (a malformed lug is skipped, never fatal)
  - a lug with no 'id' falls back to its basename for lug_locks, and to '' for the
    paper trail (matching the original `d.get('id','')`)
  - when the worktree guard has no resolvable started_at, the window falls back to
    "the last 4 hours" exactly as the inline block did
  - the paper trail is best-effort by contract: empty lists are an acceptable result

Usage:
    python3 savepoint_scan_state.py --base <spoke_local_base>
Emits JSON on stdout: {"lug_locks": [...], "paper_trail": {"completed": [...], "opened": [...]}}
Exit: 0 ok | 2 error
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import sys


def scan_lug_locks(base: str) -> list:
    """Every lug currently held in_progress — the locks this savepoint must declare."""
    lug_locks = []
    for f in sorted(glob.glob(f"{base}/lugs/bytype/*/in_progress/*.json")):
        try:
            d = json.load(open(f))
            lug_locks.append(d.get("id", os.path.basename(f).replace(".json", "")))
        except Exception:
            pass
    return lug_locks


def _session_started_at(base: str) -> datetime.datetime:
    """Session start per the worktree guard; falls back to now-4h (verbatim from the
    inline block — a savepoint must never fail because the guard is unreadable)."""
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        from worktree_guard import resolve_guard_path  # noqa: PLC0415

        guard_path = resolve_guard_path(base, os.environ.get("CLAUDE_CODE_SESSION_ID"))
        return datetime.datetime.fromisoformat(
            json.load(open(guard_path)).get("started_at", "").replace("Z", "+00:00")
        )
    except Exception:
        return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=4)


def _ts(value: str):
    """Parse an ISO-8601 stamp; None when absent/unparseable (best-effort, as before)."""
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except Exception:
        return None


def scan_paper_trail(base: str) -> dict:
    """Lugs completed and opened since this session started — the savepoint's paper trail."""
    started = _session_started_at(base)
    completed, opened = [], []
    for f in glob.glob(f"{base}/lugs/bytype/*/completed/*.json"):
        try:
            d = json.load(open(f))
            ts = _ts(d.get("completed_at", ""))
            if ts and ts >= started:
                completed.append(d.get("id", ""))
        except Exception:
            pass
    for f in glob.glob(f"{base}/lugs/bytype/*/open/*.json") + glob.glob(
        f"{base}/lugs/bytype/*/in_progress/*.json"
    ):
        try:
            d = json.load(open(f))
            ts = _ts(d.get("created_at", ""))
            if ts and ts >= started:
                opened.append(d.get("id", ""))
        except Exception:
            pass
    return {"completed": completed, "opened": opened}


def run(base: str) -> int:
    print(json.dumps({"lug_locks": scan_lug_locks(base), "paper_trail": scan_paper_trail(base)}))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True, help="spoke local base (the {BASE} the ceremony resolves)")
    a = ap.parse_args(argv)
    try:
        return run(a.base)
    except Exception as e:  # never a silent failure — the savepoint must SEE this
        print(f"savepoint_scan_state: ERROR {type(e).__name__}: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
