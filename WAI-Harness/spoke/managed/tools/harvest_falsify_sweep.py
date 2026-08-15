#!/usr/bin/env python3
"""Re-run the falsifiability gate over every rewrite that was accepted before it existed.

Every rewrite stored before 2026-08-14 passed a gate that asked only whether the command
DECIDES. This asks the question that gate could not: can it be made to decide otherwise?

REPORTS, DOES NOT MUTATE. An unfalsifiable rewrite is not automatically reverted, because
`revert` requires saying what was wrong with the command and that sentence is a human's.
The sweep's job is to hand over the list with the evidence attached.

DO NOT RUN THIS ALONGSIDE THE TEST SUITE. It executes corpus commands; harvest.probe
carries the same warning for the same measured reason.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from kernel import clock, harvest, place as place_mod, store, work  # noqa: E402


def sweep(root: str = ".", timeout: int = 60) -> dict:
    place = place_mod.find(root)
    tracked = harvest.tracked_files(place.root)
    by_name = harvest._index(tracked)
    rows, counts = [], {}
    for item in work.all_work(place):
        current = set(item.get("verify") or [])
        for proof in item.get("verify_proofs") or []:
            now, was = proof.get("now"), proof.get("was")
            # Only proofs describing a step that is STILL THERE. The log is append-only,
            # so a rewrite already withdrawn leaves its record behind forever and
            # re-auditing it would raise an alarm somebody already handled.
            if not now or now not in current or proof.get("reverting"):
                continue
            cls = harvest.rewrite_class(was or "")
            sorted_step = harvest.classify_step(was or "", tracked, by_name, False)
            verdict = harvest.falsifiable(place.root, now,
                                          sorted_step.get("artefact", ""), cls,
                                          timeout=timeout)
            counts[verdict["verdict"]] = counts.get(verdict["verdict"], 0) + 1
            if verdict["verdict"] == "unfalsifiable":
                rows.append({"id": item.get("id", ""), "was": was, "now": now,
                             "class": cls, "why": verdict["why"]})
    return {"counts": counts, "unfalsifiable": rows, "at": clock.stamp(),
            "verdict": (f"{counts.get('falsifiable', 0)} proven falsifiable, "
                        f"{counts.get('unfalsifiable', 0)} cannot be made to fail, "
                        f"{counts.get('unproven', 0)} could not be tested "
                        "(reason recorded per row -- no cheap counterfactual, the claim "
                        "is not true yet, or the command reads outside this tree)")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args()
    report = sweep(args.root, args.timeout)
    # WRITTEN WHERE THE KERNEL LOOKS, every run. A sweep whose result only ever reaches a
    # terminal is a one-time act, and the finding decays the moment the session ends.
    place = place_mod.find(args.root)
    store.write_json(place.runtime / "harvest-falsifiability-sweep.json", report,
                     writer="harvest_falsify_sweep")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(report["verdict"])
        for row in report["unfalsifiable"]:
            print(f"\n  {row['id']}  [{row['class']}]")
            print(f"    was: {row['was'][:110]}")
            print(f"    now: {row['now'][:110]}")
            print(f"    {row['why']}")
    # Findings are a report, not a failure: exit 1 only when something cannot be falsified,
    # so a caller can gate on it without the sweep pretending a clean corpus is an error.
    return 1 if report["unfalsifiable"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
