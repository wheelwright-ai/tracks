#!/usr/bin/env python3
"""converge_gate.py — ask "is there anything to reconcile?" BEFORE this session forks.

THE HOLE THIS FILLS (operator directive, 2026-07-22):
"First session to do work should attempt the converge if needed. This way we are
always reconciling before we create our own branch."

Convergence was only ever referenced at the END of a session — /wai-converge,
closeout, savepoint, the stop-savepoint guard. Nothing asked the question at the
START, so a session would fork its own branch off a tree that still had another
lane's committed work sitting outside it. That is how session-20260719-work-split
sat unmerged for three days while later sessions branched around it, and how the
circle audit ended up reporting UNMERGED_LANE as a standing finding rather than a
transient one.

This gate is READ-ONLY and always exits 0. It answers one question and prints one
line. It never merges: reconciling is a ceremony with a lease, a test gate and a
safety triple (/wai-converge). Announcing is not doing, and a gate that acted on
its own would be a silent writer at the least examined moment of a session.

Signals, cheapest first:
  1. git — a local branch that is NOT an ancestor of main is unmerged work.
     This is the same condition circle_audit calls UNMERGED_LANE.
  2. converge_closeout.py candidates — idle competitor lanes holding committed
     work (CSRP P6). Only consulted when the tool is present.

Exit code is always 0: a session must never fail to start because the gate could
not answer.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# A lane branch, by our naming conventions. Anything else (feature work, a fork
# of main someone is nursing) is deliberately NOT flagged: this gate speaks about
# session lanes, and crying wolf about every branch would train people to ignore it.
_LANE_PREFIXES = ("session/", "session-", "herald/", "lane/")


def _git(root: Path, *args: str, timeout: int = 10) -> str:
    try:
        out = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True, timeout=timeout)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def unmerged_lanes(root: Path, current_branch: str = "") -> list:
    """Local lane branches whose tip is not reachable from main.

    Uses `git branch --no-merged main`, which is exactly "has commits main does
    not have". The session's OWN branch is excluded — a session is allowed to be
    ahead of main; that is what a lane IS. What it must not do is fork while
    SOMEONE ELSE's lane is still outside main.
    """
    raw = _git(root, "branch", "--no-merged", "main", "--format=%(refname:short)")
    if not raw:
        return []
    lanes = []
    for name in raw.splitlines():
        name = name.strip()
        if not name or name == current_branch or name == "main":
            continue
        if not name.startswith(_LANE_PREFIXES):
            continue
        ahead = _git(root, "rev-list", "--count", f"main..{name}") or "0"
        lanes.append({"branch": name, "commits_ahead": int(ahead) if ahead.isdigit() else 0})
    return lanes


def idle_lane_candidates(root: Path, base: str, session_id: str) -> list:
    """CSRP P6 competitors: other lanes' committed work, per converge_closeout."""
    tool = root / "WAI-Harness" / "spoke" / "managed" / "tools" / "converge_closeout.py"
    if not tool.is_file():
        return []
    try:
        out = subprocess.run(
            [sys.executable, str(tool), "candidates", "--base", base,
             "--session-id", session_id, "--json"],
            capture_output=True, text=True, timeout=30)
        if out.returncode != 0 or not out.stdout.strip():
            return []
        data = json.loads(out.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    cands = data.get("candidates") if isinstance(data, dict) else data
    if not isinstance(cands, list):
        return []
    return [c for c in cands if isinstance(c, dict) and c.get("state") == "idle"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--session-id", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    base = "WAI-Harness/spoke/local"
    if not (root / base).is_dir():
        base = "WAI-Spoke"                       # v3 coexist spokes only
    if not (root / base).is_dir():
        return 0                                 # not a spoke; say nothing

    current = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    lanes = unmerged_lanes(root, current)
    idle = idle_lane_candidates(root, base, args.session_id) if args.session_id else []

    result = {"needed": bool(lanes or idle), "unmerged_lanes": lanes, "idle_lanes": idle,
              "current_branch": current}
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    if not result["needed"]:
        return 0                                  # silent when clean — cost nothing, say nothing

    names = ", ".join(l["branch"] for l in lanes[:3])
    extra = f" +{len(lanes) - 3} more" if len(lanes) > 3 else ""
    parts = []
    if lanes:
        parts.append(f"{len(lanes)} unmerged lane(s): {names}{extra}")
    if idle:
        parts.append(f"{len(idle)} idle lane(s) holding committed work")
    print(f"[CONVERGENCE] {'; '.join(parts)} — reconcile BEFORE this session forks "
          f"its own branch: /wai-converge")
    return 0


if __name__ == "__main__":
    sys.exit(main())
