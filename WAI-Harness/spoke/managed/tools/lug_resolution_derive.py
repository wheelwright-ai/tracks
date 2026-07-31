#!/usr/bin/env python3
"""lug_resolution_derive.py — derive a completed lug's resolution FROM ITS EVIDENCE.

spec-canonical-lug-vocabulary-v1. Operator, 2026-07-31: "I'd suggest you not assume
it — a simple validation is worth it considering the importance of this spoke being
our harness."

He was right, and the data says so. Surveying completed lugs before writing this:

    type            88%      completed_at    70%      verify          69%
    file_targets    17%      resolution      13%      superseded_by    1%
    certification    0%      done_list        0%      measured_outcome 0%

Only 17% carry the declared outputs, and almost none carry a certification. So
backfilling 3,513 lugs as `implemented` would have been a GUESS on the large
majority of them — a bulk assumption written into the harness's own history, where
it would then read as fact to every future session.

WHAT COUNTS AS EVIDENCE HERE, in strict order:

  1. an existing `resolution`      already answered; never overwritten
  2. `superseded_by`               explicit, unambiguous
  3. `file_targets` THAT EXIST     the lug named outputs and they are on disk
  4. lug TYPE for non-build work   a spec/decision/review that completed was
                                   DECIDED, not built — the artifact IS the decision
  5. anything else                 UNRESOLVED. Reported, parked, never guessed.

Rule 3 is the one that does real work, and it is checked rather than trusted: a
lug claiming outputs that are not on disk does NOT count as implemented. That is
the same say-do check the completion certifier applies, reused here.

READ-ONLY unless --apply, and --apply writes `resolution` plus
`resolution_derived_from` so every value can be traced back to what justified it.

Usage:
    lug_resolution_derive.py                # report the distribution
    lug_resolution_derive.py --sample 12    # show worked examples
    lug_resolution_derive.py --apply        # write only the evidenced ones
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import sys

# Types whose completion IS a decision rather than a build. A completed spec did
# not ship code; treating it as unresolved would park thousands of lugs whose
# meaning is perfectly clear from what they are.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from routing_vocab import CANONICAL_RESOLUTION as _CANON  # noqa: E402

_DECISION_TYPES = {"spec", "decision", "review", "notation", "hypothesis",
                   "session-summary", "foundation", "idea", "ask"}
_RECORD_TYPES = {"upgrade-report", "signal", "receipt", "notice"}


def derive(lug, root="."):
    """Return (resolution, evidence) or (None, why_not). Never guesses."""
    # resolution_class is the CONTROLLED field; `resolution` is pre-existing prose
    # and is never read as an answer or written over. See routing_vocab's note.
    if lug.get("resolution_class"):
        return str(lug["resolution_class"]).strip().lower(), "already classified"
    existing = lug.get("resolution")
    if existing:
        # `resolution` is ALREADY used inconsistently in the wild — some lugs store
        # a plain string, others a whole dict of narrative. That is the same
        # fragmentation this canon exists to end, so a non-string value is not
        # treated as an answer; it is surfaced for a human like any other
        # unresolved case rather than being coerced into one.
        if isinstance(existing, str) and existing.strip().lower() in _CANON:
            return existing.strip().lower(), "existing `resolution` is already canonical"
        # Narrative or structured prose: an explanation a human wrote, not a class.
        # It is NOT an answer and must NOT be replaced.
        return None, ("`resolution` holds pre-existing %s (%d chars) — an "
                      "explanation, not a class; left untouched"
                      % (type(existing).__name__,
                         len(existing) if isinstance(existing, str) else 0))
    if lug.get("superseded_by"):
        return "superseded", "superseded_by: %s" % str(lug["superseded_by"])[:60]

    targets = [t for t in (lug.get("file_targets") or []) if isinstance(t, str)]
    if targets:
        present = [t for t in targets
                   if os.path.exists(os.path.join(root, t.lstrip("./")))]
        if present:
            return "implemented", ("%d/%d declared file_target(s) exist on disk"
                                   % (len(present), len(targets)))
        # CLAIMED OUTPUTS THAT ARE NOT THERE. Not evidence of implementation, and
        # worth surfacing rather than smoothing over.
        return None, ("declares %d file_target(s), NONE of which exist — "
                      "cannot be called implemented" % len(targets))

    t = str(lug.get("type") or "").lower()
    if t in _DECISION_TYPES:
        return "decided", "type=%s — completion of this type is a decision" % t
    if t in _RECORD_TYPES:
        return "delivered", "type=%s — a record, delivered rather than built" % t

    return None, "no file_targets, no superseded_by, and type=%s is a build type" % (t or "?")


def scan(root=".", apply=False):
    res = collections.Counter()
    why = collections.Counter()
    samples = collections.defaultdict(list)
    written = 0
    for p in glob.glob(os.path.join(root, "WAI-Harness/spoke/local/lugs/bytype/**/*.json"),
                       recursive=True):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if d.get("status") != "completed":
            continue
        r, ev = derive(d, root)
        key = r or "UNRESOLVED"
        res[key] += 1
        if r is None:
            why[ev.split("—")[0].strip()[:60]] += 1
        if len(samples[key]) < 4:
            samples[key].append("%s  [%s]" % (str(d.get("id", "?"))[:52], ev[:70]))
        if apply and r and not d.get("resolution_class"):
            d["resolution_class"] = r
            d["resolution_derived_from"] = ev
            try:
                open(p, "w", encoding="utf-8").write(json.dumps(d, indent=2) + "\n")
                written += 1
            except OSError:
                pass
    return {"counts": dict(res.most_common()), "unresolved_reasons": dict(why.most_common()),
            "samples": {k: v for k, v in samples.items()}, "written": written,
            "total": sum(res.values())}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rep = scan(a.root, apply=a.apply)

    if a.json:
        print(json.dumps(rep, indent=2))
        return 0

    print("RESOLUTION DERIVED FROM EVIDENCE — %d completed lug(s)%s"
          % (rep["total"], "  (APPLIED)" if a.apply else "  (read-only)"))
    for k, v in rep["counts"].items():
        mark = "  <- parked, needs a human" if k == "UNRESOLVED" else ""
        print("   %-14s %5d%s" % (k, v, mark))
    if rep["unresolved_reasons"]:
        print()
        print("  why unresolved:")
        for k, v in rep["unresolved_reasons"].items():
            print("      %-58s %4d" % (k, v))
    if a.sample:
        print()
        for k, rows in rep["samples"].items():
            print("  %s:" % k)
            for r in rows[:a.sample]:
                print("      %s" % r)
    if a.apply:
        print()
        print("  wrote resolution on %d lug(s); every one carries "
              "resolution_derived_from" % rep["written"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
