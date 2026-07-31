#!/usr/bin/env python3
"""Tally — custody of the PROOF half of every lug.

THE PROBLEM THIS EXISTS FOR (measured 2026-07-30, mywheel).
An autopilot round handed six completed lugs to an isolated certifier holding
Read and Bash. It returned 0 certified, 0 failed, 13 UNCHECKABLE, and every lug
escalated with "N verify step(s) could not be decided by any certifier". The
gate was not rejecting bad work — it had never rendered a verdict at all.

The cause is upstream. Of 732 open lugs, 567 carried a verify field and only 201
contained anything runnable. The other 366 read like "pytest: parametrized
round-trip green for every type dir present in bytype/" — which DESCRIBES a
check without being one. A certifier can run a command. It cannot run a
sentence, so it correctly abstains, and correct work is parked forever.

WHAT TALLY DOES, AND DELIBERATELY DOES NOT DO.
It derives a runnable check ONLY from what a lug already declares about itself —
its own file_targets, its own test paths, a command already written into its own
acceptance criteria. It never invents an oracle. Where nothing can be derived
without judgement it says so and stops, because a derived check that passes
without proving the acceptance criterion is worse than no check: it converts an
honest abstention into a false confirmation.

THE GOODHART TRAP, NAMED SO IT STAYS NAMED.
The measured number here is "share of open lugs with an executable verify step".
That number is trivially gameable — `test -d .` passes in every repo and proves
nothing. Three defences, all structural rather than advisory:
  1. Derived checks may only reference paths the lug ITSELF declares.
  2. Every derived check carries its derivation rule and a STRENGTH, so an
     artifact-exists check can never be mistaken for a behavioural one.
  3. Derived and hand-authored counts are reported separately, and the report
     states plainly that the number to watch downstream is certified_checks on
     an autopilot round — not this one.
Raising the provable share while certified_checks stays zero is check-padding.
The report says so in those words.

STRENGTH LADDER (recorded on every derived check):
  behavioural  a test or command that exercises the change      (strongest)
  artifact     the declared target exists / contains a marker
  none         nothing derivable — flagged for a human          (not written)
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

# A verify step counts as runnable if a shell holding Read+Bash could execute it.
# Deliberately conservative and deliberately the SAME shape validate_savepoint.py
# uses for evidence — a gate that accepts what the auditor rejects manufactures
# records that look valid and audit as empty.
#
# STRICTNESS IS THE WHOLE POINT. The first cut of this pattern matched the verb
# anywhere in the string, which counted "pytest: parametrized round-trip green for
# every type dir present in bytype/" as runnable — the exact prose that made the
# certifier abstain. It reported 59% provable against a hand count of 35% and would
# have declared the problem half-solved before a line was written.
#
# A step is runnable only if a shell could execute it VERBATIM: the command verb
# starts the step (optionally after `$ ` or a backtick), and is followed by an
# argument or flag rather than by prose punctuation. Backticked commands anywhere
# in the step also count — that is an author writing a real command inline.
_VERB = r"(?:pytest|python3?|bash|sh|node|npm|cargo|go|git|jq|grep|rg|test|ls|find|diff|\./\S+)"
RUNNABLE = re.compile(
    r"^\s*(?:\$\s*)?`?" + _VERB + r"\s+[-\w./\"'\[$(]",   # command at the start of the step
    re.I,
)
_BACKTICKED = re.compile(r"`\s*(?:\$\s*)?" + _VERB + r"\s+[-\w./\"'\[$(][^`\n]*`", re.I)

TEST_PATH = re.compile(r"(?:^|/)(?:test_[\w./-]+\.py|[\w./-]+_test\.py)$", re.I)
# A command already embedded in prose, e.g. in backticks.
EMBEDDED = re.compile(r"`([^`\n]{6,200})`")


def _steps(lug, field):
    v = lug.get(field)
    if v is None:
        return []
    return [str(x) for x in v] if isinstance(v, list) else [str(v)]


def is_runnable(s: str) -> bool:
    """A shell holding Read+Bash could execute this string verbatim."""
    return bool(RUNNABLE.search(s) or _BACKTICKED.search(s))


def has_runnable(lug) -> bool:
    return any(is_runnable(s) for s in _steps(lug, "verify"))


def derive(lug, root: Path):
    """Return (check_str, rule, strength) or None. Derives ONLY from the lug's
    own declarations — never from the tool's imagination."""
    targets = [t for t in (lug.get("file_targets") or []) if isinstance(t, str)]

    # R1 — a declared test file is the strongest honest derivation: running it
    # exercises the behaviour the lug claims, and the lug itself named it.
    for t in targets:
        if TEST_PATH.search(t) and (root / t).exists():
            return (f"python3 -m pytest {t} -q", "R1:declared-test-path", "behavioural")

    # R2 — a command the AUTHOR already wrote into acceptance criteria or verify
    # prose. Extracting it is not invention; it is honouring what they meant.
    for field in ("verify", "acceptance_criteria"):
        for s in _steps(lug, field):
            for m in EMBEDDED.finditer(s):
                cand = m.group(1).strip()
                if is_runnable(cand) or RUNNABLE.search(cand):
                    return (cand, f"R2:embedded-command-in-{field}", "behavioural")

    # R3 — the lug's own declared targets must exist. Weaker: existence is not
    # correctness. Recorded as `artifact` strength precisely so nobody reads it
    # as proof of behaviour.
    real = [t for t in targets if not t.endswith("/") and (root / t).exists()]
    if real:
        picked = real[:3]
        expr = " && ".join(f"test -e {t}" for t in picked)
        return (expr, "R3:declared-file-targets-exist", "artifact")

    return None


def scan(root: Path, apply: bool, limit: int | None):
    lugs = sorted((root / "WAI-Harness/spoke/local/lugs/bytype").glob("*/open/*.json"))
    tot = withv = runnable = derived = flagged = 0
    by_rule: dict[str, int] = {}
    flags = []

    for f in lugs:
        try:
            lug = json.loads(f.read_text())
        except Exception:
            continue
        tot += 1
        if not _steps(lug, "verify"):
            continue
        withv += 1
        if has_runnable(lug):
            runnable += 1
            continue

        d = derive(lug, root)
        if not d:
            flagged += 1
            if len(flags) < 40:
                flags.append({"id": lug.get("id"), "why": "no declared target, test path or embedded command"})
            continue

        check, rule, strength = d
        by_rule[rule] = by_rule.get(rule, 0) + 1
        derived += 1
        if apply and (limit is None or derived <= limit):
            steps = _steps(lug, "verify")
            steps.append(check)
            lug["verify"] = steps
            lug.setdefault("_tally", {})[check] = {
                "rule": rule,
                "strength": strength,
                "derived_by": "tally",
                "note": (
                    "Derived from this lug's OWN declarations, not invented. "
                    + (
                        "Artifact-strength: proves the declared target exists, NOT that the "
                        "acceptance criterion is met — do not read a pass here as behavioural proof."
                        if strength == "artifact"
                        else "Behavioural: exercises the change the lug claims."
                    )
                ),
            }
            f.write_text(json.dumps(lug, indent=2))

    return {
        "open_lugs": tot,
        "with_verify": withv,
        "already_runnable": runnable,
        "derived": derived,
        "flagged_for_human": flagged,
        "by_rule": by_rule,
        "provable_before": runnable,
        "provable_after": runnable + (derived if apply else 0),
        "share_before": round(100 * runnable / withv) if withv else 0,
        "share_after": round(100 * (runnable + (derived if apply else 0)) / withv) if withv else 0,
        "flags_sample": flags,
    }


def main():
    ap = argparse.ArgumentParser(description="Tally — make lug proofs executable, or say they are not.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--apply", action="store_true", help="write derived checks onto lugs")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    r = scan(Path(a.root).resolve(), a.apply, a.limit)
    if a.json:
        print(json.dumps(r, indent=2))
        return 0

    print(f"TALLY {'— APPLIED' if a.apply else '— dry run'}")
    print(f"  open lugs                : {r['open_lugs']}")
    print(f"  with a verify field      : {r['with_verify']}")
    print(f"  already runnable         : {r['already_runnable']}  ({r['share_before']}%)")
    print(f"  derived a check          : {r['derived']}")
    for k, v in sorted(r["by_rule"].items()):
        print(f"      {v:4d}  {k}")
    print(f"  flagged for a human      : {r['flagged_for_human']}")
    print(f"  provable share {'now' if a.apply else 'would be'}: {r['share_after']}%  (was {r['share_before']}%)")
    print()
    print("  This number is NOT the goal. The goal is certified_checks > 0 on an")
    print("  autopilot round — a provable share that rises while that stays zero")
    print("  is check-padding, not proof.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
