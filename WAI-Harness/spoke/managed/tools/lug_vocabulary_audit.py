#!/usr/bin/env python3
"""lug_vocabulary_audit.py — what a canonical-status migration would actually do.

spec-canonical-lug-vocabulary-v1. Operator ruling 2026-07-31: "Wheelwright must be
canonical so no disagreement over status values or expected locations and
behaviors."

READ-ONLY BY DESIGN, AND THAT IS THE POINT. The migration touches thousands of
lugs, and the dangerous half is not the mechanical rename — it is the lugs whose
meaning nobody can recover. "done" says a lug stopped without saying whether it was
built, decided or abandoned; mapping it to `implemented` is a GUESS about work
someone else did. So this reports three buckets and changes nothing:

  CLEAN       already canonical, nothing to do
  MAPPABLE    a historical value with an unambiguous canonical equivalent
  NEEDS HUMAN a value that maps to a status but NOT to a resolution, or maps to
              nothing at all — these must be parked and asked about, never guessed

A migration is only safe to write once this report shows how big the third bucket
is. Running it first is the difference between a rename and a silent rewrite of
the operator's history.

Usage:
    lug_vocabulary_audit.py                 # this spoke
    lug_vocabulary_audit.py --fleet         # every active spoke in the registry
    lug_vocabulary_audit.py --json
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from routing_vocab import (CANONICAL_RESOLUTION, CANONICAL_STATUS,  # noqa: E402
                           canonicalise)


def audit_spoke(root="."):
    base = os.path.join(root, "WAI-Harness/spoke/local/lugs/bytype")
    clean = mappable = needs_human = needs_backfill = 0
    raw = collections.Counter()
    unmapped = collections.Counter()
    ambiguous = collections.Counter()
    backfill = collections.Counter()
    examples = collections.defaultdict(list)

    for p in glob.glob(os.path.join(base, "**", "*.json"), recursive=True):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        s = d.get("status")
        if not s:
            continue
        raw[str(s)] += 1
        cs, res = canonicalise(s)
        if cs is None:
            unmapped[str(s)] += 1
            needs_human += 1
            if len(examples["unmapped"]) < 3:
                examples["unmapped"].append(f"{d.get('id','?')}: status={s}")
            continue
        if str(s) in CANONICAL_STATUS and (
                str(s) != "completed" or d.get("resolution") in CANONICAL_RESOLUTION):
            clean += 1
        elif str(s) == "completed":
            # ALREADY IN THE RIGHT PLACE, just missing the new field. Counting these
            # with the genuinely ambiguous ones inflated "needs human" from ~950 to
            # 4,465 and would have made a bulk backfill look like 3,513 individual
            # judgements. A number that frightens the operator out of a safe change
            # is as much a reporting failure as one that hides a risk.
            backfill[str(s)] += 1
            needs_backfill += 1
        elif res is None:
            # the STATUS ITSELF is ambiguous — this is the real judgement work
            ambiguous[str(s)] += 1
            needs_human += 1
            if len(examples["ambiguous"]) < 3:
                examples["ambiguous"].append(f"{d.get('id','?')}: status={s}")
        else:
            mappable += 1

    return {"root": root, "total": sum(raw.values()),
            "clean": clean, "mappable": mappable, "needs_human": needs_human,
            "needs_backfill": needs_backfill, "backfill": dict(backfill),
            "distinct_values": len(raw),
            "raw": dict(raw.most_common()),
            "unmapped": dict(unmapped), "ambiguous": dict(ambiguous),
            "examples": dict(examples)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--fleet", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    roots = [a.root]
    if a.fleet:
        reg = os.path.join(a.root, "WAI-Harness/hub/local/hub-registry.json")
        try:
            wheels = json.load(open(reg)).get("wheels", [])
            roots = [w["path"] for w in wheels
                     if (w.get("status") or "active") == "active"
                     and w.get("path") and os.path.isdir(w["path"])]
        except Exception:  # noqa: BLE001
            pass

    reports = [audit_spoke(r) for r in roots]
    tot = {k: sum(r[k] for r in reports)
           for k in ("total", "clean", "mappable", "needs_human", "needs_backfill")}
    allraw = collections.Counter()
    for r in reports:
        allraw.update(r["raw"])

    if a.json:
        print(json.dumps({"totals": tot, "distinct": len(allraw),
                          "raw": dict(allraw.most_common()),
                          "spokes": reports}, indent=2))
        return 0

    print("LUG VOCABULARY AUDIT — %d lug(s) across %d spoke(s), %d distinct status values"
          % (tot["total"], len(reports), len(allraw)))
    print("   clean (already canonical)   %5d" % tot["clean"])
    print("   mappable (safe rename)      %5d" % tot["mappable"])
    print("   backfill (completed, no resolution) %5d   <- ONE bulk decision"
          % tot["needs_backfill"])
    print("   NEEDS HUMAN                 %5d   <- must be parked, never guessed"
          % tot["needs_human"])
    print()
    amb = collections.Counter()
    unm = collections.Counter()
    for r in reports:
        amb.update(r["ambiguous"])
        unm.update(r["unmapped"])
    if amb:
        print("  ambiguous (status recoverable, RESOLUTION is not):")
        for k, v in amb.most_common():
            print("      %-18s %5d" % (k, v))
    if unm:
        print("  unmapped (no canonical equivalent at all):")
        for k, v in unm.most_common():
            print("      %-18s %5d" % (k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
