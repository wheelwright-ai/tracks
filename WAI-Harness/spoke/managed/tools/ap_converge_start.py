#!/usr/bin/env python3
"""ap_converge_start.py -- absorb dangling lanes BEFORE a round dispatches anything.

OPERATOR RULING 2026-08-15: "each AP [should] start with absorbing a converge of
dangling branches ... ozi always tries to converge on wakeup, cleaning up our
codebase."

WHY AT THE START AND NOT THE END. Convergence was only ever referenced at the end of
a session -- closeout, savepoint, /wai-converge. Nothing absorbed at the START, so a
round would dispatch onto a tree that still had another lane's committed work sitting
outside it, and the new work forked around the old. converge_gate.py named this hole
on 2026-07-22 and stayed READ-ONLY on purpose: for a human session, announcing is the
right behaviour because a gate that merged on its own would be a silent writer.

An AP round is not a human session. It is unattended, it is about to dispatch workers
that write, and nobody is watching the tree it writes into. So here the gate ACTS --
and where it cannot act, the round REFUSES rather than dispatching onto a contested
tree. That is the difference the ruling turns on.

Measured 2026-08-15 across 14 active spokes: 7 unmerged lanes in 3 spokes
(basher 4, keeping-open-lines 2, pathfinder 1). Small today, and it only grows in
the direction of harder merges.

Order of operations, cheapest first:
  1. detect  -- converge_gate.unmerged_lanes(): local lane branches not reachable
                from main. Read-only, never wrong about the direction of the
                question.
  2. absorb  -- converge_closeout.py reconcile-lane per lane. The real ceremony,
                with its lease and its test gate. This tool does not merge by hand;
                hand-rolled merges are how the lanes got stranded in the first place.
  3. verdict -- lanes still outside main after the attempt mean the tree is
                contested. Return blocked; the caller must not dispatch.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

try:
    import converge_gate
    _GATE = True
except ImportError:
    _GATE = False


def _reconcile(repo: Path, lane: str, base: str, timeout: int = 900) -> Dict[str, Any]:
    """Run the real ceremony for one lane. Never merges by hand."""
    tool = TOOLS / "converge_closeout.py"
    if not tool.is_file():
        return {"lane": lane, "ok": False, "reason": "converge_closeout.py not present"}
    try:
        cp = subprocess.run(
            [sys.executable, str(tool), "reconcile-lane", "--repo", str(repo),
             "--name", lane, "--base", base],
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"lane": lane, "ok": False, "reason": f"{type(exc).__name__}: {exc}"}
    return {
        "lane": lane,
        "ok": cp.returncode == 0,
        "reason": "" if cp.returncode == 0 else (cp.stderr or cp.stdout).strip()[:400],
    }


def converge_at_start(
    repo: Path, base: str, current_branch: str = "", dry_run: bool = False
) -> Dict[str, Any]:
    """Absorb dangling lanes. Returns a verdict dict the caller records verbatim.

    verdict:
      clean    -- nothing was outside main; dispatch freely
      absorbed -- lanes existed and are now in main; dispatch freely
      blocked  -- lanes remain outside main; the caller MUST NOT dispatch
      unknown  -- the gate could not answer; treated as clean, said out loud,
                  because refusing every round on a missing tool would idle the
                  fleet over a packaging problem rather than a real conflict
    """
    if not _GATE:
        return {"verdict": "unknown", "reason": "converge_gate unavailable",
                "lanes_before": [], "attempts": [], "lanes_after": []}

    before = converge_gate.unmerged_lanes(Path(repo), current_branch)
    if not before:
        return {"verdict": "clean", "reason": "", "lanes_before": [],
                "attempts": [], "lanes_after": []}

    names = [l["branch"] for l in before]
    if dry_run:
        return {"verdict": "blocked", "reason": "dry-run: would absorb but did not",
                "lanes_before": before, "attempts": [], "lanes_after": before}

    attempts = [_reconcile(Path(repo), n, base) for n in names]
    after = converge_gate.unmerged_lanes(Path(repo), current_branch)

    if not after:
        return {"verdict": "absorbed", "reason": "",
                "lanes_before": before, "attempts": attempts, "lanes_after": []}

    failed = [a for a in attempts if not a["ok"]]
    reason = (
        f"{len(after)} lane(s) still outside main after absorbing "
        f"{len(before) - len(after)} of {len(before)}"
        + (f"; first failure: {failed[0]['lane']} -- {failed[0]['reason']}" if failed else "")
    )
    return {"verdict": "blocked", "reason": reason, "lanes_before": before,
            "attempts": attempts, "lanes_after": after}


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", required=True, help="spoke local base (WAI-Harness/spoke/local)")
    ap.add_argument("--current-branch", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    res = converge_at_start(Path(args.repo), args.base, args.current_branch, args.dry_run)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"converge-at-start: {res['verdict'].upper()}"
              + (f" -- {res['reason']}" if res["reason"] else ""))
        for l in res["lanes_before"]:
            print(f"  before: {l['branch']} (+{l['commits_ahead']})")
        for a in res["attempts"]:
            print(f"  absorb: {a['lane']} {'ok' if a['ok'] else 'FAILED: ' + a['reason']}")
    # blocked is a real verdict, not a crash: exit 2 so a caller can branch on it
    return 2 if res["verdict"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
