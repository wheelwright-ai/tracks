#!/usr/bin/env python3
"""ceremony_token_budget.py — performance guard for the WAI ceremonies (P4 of
initiative-optimize-ceremonies-v1).

Ceremonies are loaded into the model's context every time they run, so their size
IS a per-run token cost. P0-P2 cut that cost (canonicalize, shared-lib, extract
~459L of inline Python to tools). This guard LOCKS IN those gains: each ceremony
has a line budget (a ceiling), and the cut/CI fails if a ceremony grows past it —
so the next edit can't silently re-bloat the ceremony back to the 1455L closeout.

Budgets are deliberate ceilings a bit above the post-optimization size; lowering a
budget after a real reduction is encouraged (ratchet down, never up without cause).

CLI:
  python3 ceremony_token_budget.py --commands DIR [--json]
Exit: 0 all within budget | 1 over budget | 2 error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# line-count ceilings (post-P0-P2). Ratchet DOWN as ceremonies shrink further.
#
# WHAT THIS BUDGET IS FOR, and what it is NOT for (operator-stated 2026-07-19,
# after a session compressed the savepoint protocol twice to fit and lost real
# content both times): the ceiling exists to stop ceremonies ACCRETING —
# restating themselves, keeping dead steps, inlining scripts that belong in
# tools. It does NOT license removing content a resuming session needs.
#
# A ceremony doc is a durable protocol, not a message. Terseness in a record
# costs a future session the reasoning it needs to act correctly. So when a
# genuinely necessary step will not fit:
#   1. Extract its mechanics into a tool (the fix that took closeout 1389 -> 1299).
#   2. Delete anything the doc says twice.
#   3. Only then raise the ceiling, and record why beside the number.
# Never trade protocol correctness for line count.
BUDGETS = {
    "wai.md": 720,
    "wai-full.md": 500,
    "wai-full-slim.md": 60,
    "wai-reference.md": 360,
    "wai-reference-slim.md": 80,
    # 430 -> 470 (2026-07-19). Was 426 with four lines of headroom, so the resume
    # guarantee could not land at all without a raise.
    #
    # Raised TWICE: first to 440 by compressing Step 0.9 to fit, which silently
    # dropped the precondition framing ("--verify CLEAN is required for a valid
    # savepoint", the orphan-thread rationale, and where to source the thread ids).
    # The operator caught it. Those lines are what make a resuming agent enforce
    # the step rather than skim past it, so they were restored and the ceiling
    # moved to fit the protocol instead of the protocol trimmed to fit the ceiling.
    # Mechanics are already extracted into thread_materialize.py; what remains here
    # is contract and rationale, which is exactly what must not be compressed.
    "wai-savepoint.md": 470,
    # 1300 -> 1330 (2026-07-19). The file sat at 1299 with ONE line of headroom, so
    # any new step broke the guard regardless of merit.
    #
    # First raised to 1305 by squeezing the operator-blocked handoff down to three
    # lines, which dropped why the step exists (nothing carried the operator's
    # blocking set across sessions), what the field actually contains, and the
    # instruction to record UNKNOWN rather than omit when the tool is missing. A
    # resuming agent needs all three to execute the step correctly instead of
    # skimming it. Restored, and the ceiling moved to fit.
    #
    # Mechanics are already extracted into work_split.py --write-handoff; what lives
    # here is contract and rationale, which is what must never be compressed.
    # 1330 -> 1370 and 320 -> 336 (2026-07-22). The EXIT SAFETY VERDICT step
    # (impl-exitclarity-2-ceremony-verdict-wiring-v1) is a MANDATORY final step:
    # the ceremony may not report itself complete until the verdict resolves, so
    # the operator never has to infer from scattered git state whether walking
    # away is safe. A new mandatory step legitimately changes the ceiling.
    #
    # The block WAS compressed first, not raised first — the {SESSION_ID} recipe
    # was cut in favour of a pointer to Step 11.5, and the loop prose was more
    # than halved. What is left is the contract: which findings are in scope,
    # the 2-iteration cap, the never-report-safe-on-NOT_SAFE rule, and the push
    # rule that keeps concurrent sessions from racing. Same judgement recorded
    # twice above: compress mechanics, never the rationale, then move the ceiling
    # to fit the protocol rather than trimming the protocol to fit the ceiling.
    "wai-closeout.md": 1370,
    "wai-closeout-slim.md": 336,
    "wai-closeout-reference.md": 140,
}


def check(commands_dir: str) -> dict:
    over, ok, missing = [], [], []
    for name, budget in sorted(BUDGETS.items()):
        path = os.path.join(commands_dir, name)
        if not os.path.isfile(path):
            missing.append(name)
            continue
        with open(path) as fh:
            n = sum(1 for _ in fh)
        entry = {"file": name, "lines": n, "budget": budget, "headroom": budget - n}
        (over if n > budget else ok).append(entry)
    return {
        "ok": not over,
        "over": over, "within": ok, "missing": missing,
        "summary": f"{len(ok)} within budget, {len(over)} OVER, {len(missing)} missing",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Guard ceremony line budgets (token cost).")
    ap.add_argument("--commands", default="WAI-Harness/spoke/managed/.claude/commands")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rep = check(args.commands)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0 if rep["ok"] else 1
    if rep["ok"]:
        print(f"ceremony token budget: OK — {rep['summary']}")
        for e in sorted(rep["within"], key=lambda x: x["headroom"]):
            print(f"  {e['file']:28} {e['lines']:>5}/{e['budget']:<5} (headroom {e['headroom']})")
        return 0
    print(f"ceremony token budget: OVER — {rep['summary']}")
    for e in rep["over"]:
        print(f"  OVER {e['file']:24} {e['lines']}/{e['budget']} (+{-e['headroom']}) — trim or extract to a tool")
    return 1


if __name__ == "__main__":
    sys.exit(main())
