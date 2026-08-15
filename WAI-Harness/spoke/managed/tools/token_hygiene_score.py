#!/usr/bin/env python3
"""Was the work done the cheap way? Scored from receipts, never from opinion.

WHY
---
This harness is thorough about "is it correct" and silent about "was it cheap".
lug_gate already forces a justified `model_fit` at author time, but nothing ever
checked whether a completed run honoured that choice, or whether the tokens it
burned produced anything. Idea imported from Adeptly (ShopDevX/adeptlydev), which
scores a plan against named efficiency practices.

DESIGN CONSTRAINTS, LEARNED THE HARD WAY HERE
---------------------------------------------
1. Only rules DECIDABLE FROM A RECEIPT. No rule may ask a model whether the work
   felt efficient. Every finding carries an evidence pointer back to the log row
   that produced it.
2. ADVISORY IN V1. The score gates nothing. A score that gates becomes a target,
   and a target gets optimised for instead of the thing it proxies — this repo has
   found enough unearned-green mechanisms already without minting another.
3. Misses are per-run and named. An aggregate percentage with no offender list is
   a number to feel good about, not a lever.

RULES
  tier-honoured      the run used the tier the lug declared
  tier-proportionate a low-effort lug did not consume a top tier
  produced-artifact  tokens were spent AND a commit_sha was recorded
  outcome-clean      the run did not end in needs_attention after real spend
  roi-declared       the run carried a predicted_roi, so it can be scored later

USAGE
    python3 token_hygiene_score.py [--spoke-root .] [--json] [--run-id ID]

Exit: 0 always. This is a lens, not a gate.
"""

import argparse
import json
import sys
from pathlib import Path

ACTIVITY_LOG = Path("WAI-Harness/spoke/advisors/autopilot/activity-log.jsonl")
LUG_ROOT = Path("WAI-Harness/spoke/local/lugs/bytype")

TIER_RANK = {"haiku": 1, "sonnet": 2, "opus": 3}
# Below this, a run is a probe or a no-op; scoring it as waste would be noise.
MEANINGFUL_TOKENS = 2000
# An effort_score at or under this should not need the top tier.
LOW_EFFORT = 2


def load(root):
    p = root / ACTIVITY_LOG
    rows = []
    if p.exists():
        for line in p.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("lug_id") and r.get("tokens_used"):
                rows.append(r)

    lugs = {}
    base = root / LUG_ROOT
    if base.is_dir():
        for f in base.rglob("*.json"):
            try:
                d = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if d.get("id"):
                lugs[d["id"]] = d
    return rows, lugs


def score_run(a, lug):
    """Return (per-rule results, evidence) for one execution record."""
    rules = []
    tokens = a.get("tokens_used") or 0
    declared = (lug or {}).get("model_fit")
    ran = a.get("model_fit")
    effort = (lug or {}).get("effort_score")

    # tier-honoured
    if declared and ran:
        ok = declared == ran
        rules.append(("tier-honoured", ok,
                      f"declared {declared}, ran as {ran}" if not ok else f"ran as {ran}"))

    # tier-proportionate
    if effort is not None and ran in TIER_RANK:
        ok = not (effort <= LOW_EFFORT and TIER_RANK[ran] >= TIER_RANK["opus"])
        rules.append(("tier-proportionate", ok,
                      f"effort {effort} run on {ran}"))

    # produced-artifact
    if tokens >= MEANINGFUL_TOKENS:
        ok = bool(a.get("commit_sha"))
        rules.append(("produced-artifact", ok,
                      f"{tokens:,} tokens, commit_sha "
                      f"{'recorded' if ok else 'EMPTY'}"))

    # outcome-clean
    if tokens >= MEANINGFUL_TOKENS:
        ok = a.get("outcome") not in ("needs_attention", "failed")
        rules.append(("outcome-clean", ok,
                      f"outcome {a.get('outcome')} after {tokens:,} tokens"))

    # roi-declared
    rules.append(("roi-declared", a.get("predicted_roi") is not None,
                  f"predicted_roi {a.get('predicted_roi')}"))

    return rules


def run(root, run_id=None):
    rows, lugs = load(root)
    if run_id:
        rows = [r for r in rows if r.get("run_id") == run_id]

    per_rule = {}
    findings = []
    scored = 0
    total_ok = 0
    total_rules = 0

    for a in rows:
        results = score_run(a, lugs.get(a["lug_id"]))
        if not results:
            continue
        scored += 1
        for name, ok, evidence in results:
            agg = per_rule.setdefault(name, {"pass": 0, "fail": 0})
            agg["pass" if ok else "fail"] += 1
            total_rules += 1
            total_ok += 1 if ok else 0
            if not ok:
                findings.append({
                    "rule": name,
                    "lug_id": a["lug_id"],
                    "run_id": a.get("run_id"),
                    "ts": a.get("ts"),
                    "tokens_used": a.get("tokens_used"),
                    # the evidence pointer: every miss says where to look
                    "evidence": evidence,
                })

    return {
        "runs_scored": scored,
        "score": round(100 * total_ok / total_rules) if total_rules else None,
        "checks_passed": total_ok,
        "checks_total": total_rules,
        "per_rule": per_rule,
        "findings": findings,
        "advisory": True,
        "note": ("Advisory by design. A hygiene score that gates becomes a target, "
                 "and a target gets optimised for instead of the thing it proxies."),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spoke-root", default=".")
    ap.add_argument("--run-id")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    root = Path(a.spoke_root).resolve()
    if not root.is_dir():
        sys.stderr.write(f"not a directory: {root}\n")
        return 2

    res = run(root, a.run_id)

    if a.json:
        print(json.dumps(res, indent=2))
        return 0

    print(f"token hygiene — {res['runs_scored']} run(s) scored, "
          f"{res['checks_passed']}/{res['checks_total']} checks pass "
          f"({res['score']}%)  [advisory]")
    print("\n  per rule:")
    for name, agg in sorted(res["per_rule"].items()):
        n = agg["pass"] + agg["fail"]
        print(f"    {name:20s} {agg['pass']:3d}/{n:<3d} pass"
              + (f"   {agg['fail']} miss" if agg["fail"] else ""))
    if res["findings"]:
        print(f"\n  misses (each names its evidence):")
        for f in res["findings"][:12]:
            print(f"    [{f['rule']}] {f['lug_id']}  — {f['evidence']}")
        if len(res["findings"]) > 12:
            print(f"    ... and {len(res['findings']) - 12} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
