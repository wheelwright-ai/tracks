#!/usr/bin/env python3
"""tastegraph_promote.py — the inferred -> verified promotion rule, enforced.

WHY
---
Measured 2026-08-17: tastegraph.json holds 58 prefs with confidence in
{verified 26, inferred 27, stated 5} — an evidence tier with NO promotion
rule. Nothing said when `inferred` may become `verified`, so the tiers were
decorative: any pref could be re-labelled by hand and no tool would notice.

THE RULE
--------
`inferred` -> `verified` requires ONE of:

  1. N = 3 INDEPENDENT observations. N=3 because one observation is an
     anecdote, two can be the same session context read twice, and three is
     the smallest count that survives one misread. Local precedent: the
     operator's own candidate-pattern convention runs at "observation 1 of 3"
     (exec/reflection bifurcation). INDEPENDENT = distinct session ids (or
     distinct dates when no session is named) — the same session twice is one
     observation, and counting it as two is the arithmetic certify.py exists
     to keep honest.
  2. An explicit operator ratification, naming who ratified.

Either way the promotion is recorded in a `promotion` field with its basis —
a silent re-labelling is exactly what this rule exists to refuse. Only the
inferred -> verified transition is governed: `stated` is the operator's own
word and needs no observations, and re-labelling a `verified` pref is not a
promotion.

ENFORCEMENT POINT: the act of promotion is the only place a promotion rule
can bite. This tool REFUSES a basis-less promotion; it does not scan history
for past hand edits (no transition history exists to scan).

VERBS
-----
  promote PREF_ID --observations S1,S2,S3 [--tastegraph PATH] [--write]
  promote PREF_ID --operator-ratified --by WHO [--tastegraph PATH] [--write]
      Dry-run by default: prints the decision, mutates nothing without --write.
      Exit 1 on refusal.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys

TOOL_VERSION = "1.0.0"
REQUIRED_OBSERVATIONS = 3

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_TASTEGRAPH = os.path.abspath(os.path.join(
    _HERE, "..", "..", "local", "tastegraph.json"))


def _find_prefs(doc):
    """All preference dicts wherever the levels structure nests them."""
    prefs = []

    def walk(x):
        if isinstance(x, dict):
            if "confidence" in x and "value" in x and "id" in x:
                prefs.append(x)
            else:
                for v in x.values():
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(doc)
    return prefs


def independence_key(obs):
    """One observation = one session, or one date when no session is named."""
    if isinstance(obs, dict):
        return str(obs.get("session") or obs.get("date") or "").strip()
    return str(obs).strip()


def evaluate_promotion(pref, observations=(), operator_ratified=False,
                       ratified_by=""):
    """Pure decision. Returns (ok: bool, basis_or_reason: str)."""
    conf = pref.get("confidence")
    if conf != "inferred":
        return False, ("not governed: confidence is {!r}, only inferred -> "
                       "verified is a promotion".format(conf))
    if operator_ratified:
        who = (ratified_by or "").strip()
        if not who:
            return False, "operator ratification must name who ratified"
        return True, "explicit operator ratification by {}".format(who)
    keys = {k for k in (independence_key(o) for o in observations) if k}
    if len(keys) >= REQUIRED_OBSERVATIONS:
        return True, "{} independent observations: {}".format(
            len(keys), ", ".join(sorted(keys)))
    return False, ("{} independent observation(s) < {} required; one is an "
                   "anecdote, two can be the same session read twice".format(
                       len(keys), REQUIRED_OBSERVATIONS))


def promote(doc, pref_id, observations=(), operator_ratified=False,
            ratified_by="", now=None):
    """Apply the rule to a loaded tastegraph document. Returns (pref, basis).
    Raises ValueError on refusal — a basis-less promotion is refused, never
    warned-through."""
    pref = next((p for p in _find_prefs(doc)
                 if p.get("id") == pref_id or p.get("key") == pref_id), None)
    if pref is None:
        raise ValueError("no pref named {!r}".format(pref_id))
    ok, basis = evaluate_promotion(pref, observations, operator_ratified,
                                   ratified_by)
    if not ok:
        raise ValueError("promotion REFUSED for {}: {}".format(pref_id, basis))
    at = (now or _dt.datetime.now(_dt.timezone.utc)).isoformat()
    pref["promotion"] = {
        "from": "inferred", "to": "verified", "at": at, "basis": basis,
        "observations": [independence_key(o) for o in observations
                         if independence_key(o)],
    }
    if operator_ratified:
        pref["promotion"]["ratified_by"] = ratified_by.strip()
    pref["confidence"] = "verified"
    pref["last_verified"] = at
    return pref, basis


def main(argv=None):
    ap = argparse.ArgumentParser(description="governed inferred -> verified promotion")
    ap.add_argument("verb", choices=["promote"])
    ap.add_argument("pref_id")
    ap.add_argument("--observations", default="",
                    help="comma-separated session ids or dates")
    ap.add_argument("--operator-ratified", action="store_true")
    ap.add_argument("--by", default="", help="who ratified (required with --operator-ratified)")
    ap.add_argument("--tastegraph", default=_DEFAULT_TASTEGRAPH)
    ap.add_argument("--write", action="store_true",
                    help="mutate the tastegraph (default: dry-run)")
    args = ap.parse_args(argv)
    with open(args.tastegraph, encoding="utf-8") as f:
        doc = json.load(f)
    observations = [o for o in args.observations.split(",") if o.strip()]
    try:
        pref, basis = promote(doc, args.pref_id, observations,
                              args.operator_ratified, args.by)
    except ValueError as e:
        print(str(e))
        return 1
    print("PROMOTE {} -> verified".format(args.pref_id))
    print("  basis: {}".format(basis))
    if args.write:
        tmp = args.tastegraph + ".tmp-tastegraph-promote"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")
        os.replace(tmp, args.tastegraph)
        print("  written to {}".format(args.tastegraph))
    else:
        print("  dry-run — pass --write to record it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
