#!/usr/bin/env python3
"""Did the work cost what we said it would? Measured, never self-reported.

WHY
---
Every lug declares `effort_score` and `model_fit` at author time. Nothing ever
looked back. Across 2,551 lugs those numbers have never once been checked against
what the work actually cost, so they cannot improve — they are guesses that have
been recycling since the schema was written.

The autopilot activity log already records the truth per execution: lug_id,
model_fit, tokens_used, duration, outcome, commit_sha. Joining that to the lug's
declared fields closes the loop. Idea imported from Adeptly (ShopDevX/adeptlydev),
which meters every CLI call and shows estimate against actual.

HOW THE CALIBRATION WORKS, AND WHY IT IS NOT INVENTED
-----------------------------------------------------
There is no a-priori "an effort_score of 3 costs N tokens" table, and writing one
would be fiction dressed as measurement. Instead the bands are DERIVED: for each
effort_score present in the data, take the median measured tokens. A run's error
is its deviation from its own class median.

That yields two honest outputs:

  calibration   how tight each effort class is (a wide class is a score that
                is not predicting anything)
  monotonicity  does effort 4 actually cost more than effort 2? If the medians
                are not ordered, the SCALE ITSELF is not predictive — which is a
                finding about the schema, not about any one lug.

Nothing here is sourced from a model's opinion. Every field comes from a receipt.

USAGE
    python3 cost_ledger.py [--spoke-root .] [--report] [--json]

Exit: 0 always for --report (this is an instrument, not a gate).
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

ACTIVITY_LOG = Path("WAI-Harness/spoke/advisors/autopilot/activity-log.jsonl")
LUG_ROOT = Path("WAI-Harness/spoke/local/lugs/bytype")
LEDGER = Path("WAI-Harness/spoke/local/cost-ledger.jsonl")

TIER_ORDER = {"haiku": 1, "sonnet": 2, "opus": 3}


def read_activity(root):
    """Execution records only — rows that actually measured something."""
    p = root / ACTIVITY_LOG
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue  # a malformed line is not a reason to lose the rest
        if r.get("lug_id") and r.get("tokens_used"):
            rows.append(r)
    return rows


def index_lugs(root):
    """lug_id -> declared fields, wherever the lug currently sits."""
    out = {}
    base = root / LUG_ROOT
    if not base.is_dir():
        return out
    for p in base.rglob("*.json"):
        try:
            d = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        lid = d.get("id")
        if lid:
            out[lid] = {
                "effort_score": d.get("effort_score"),
                "model_fit": d.get("model_fit"),
                "impact": d.get("impact"),
                "status": d.get("status"),
                "path": str(p.relative_to(root)),
            }
    return out


def build_rows(root):
    acts = read_activity(root)
    lugs = index_lugs(root)
    rows = []
    for a in acts:
        lug = lugs.get(a["lug_id"], {})
        declared_tier = lug.get("model_fit")
        run_tier = a.get("model_fit")
        rows.append({
            # identity — makes the ledger idempotent without a sequence number
            "key": f"{a.get('run_id','?')}::{a['lug_id']}::{a.get('ts','?')}",
            "ts": a.get("ts"),
            "lug_id": a["lug_id"],
            "lug_known": bool(lug),
            "declared_effort_score": lug.get("effort_score"),
            "declared_model_fit": declared_tier,
            "run_model_fit": run_tier,
            "tier_drift": bool(declared_tier and run_tier and declared_tier != run_tier),
            "tokens_used": a.get("tokens_used"),
            "duration_seconds": a.get("duration_seconds"),
            "outcome": a.get("outcome"),
            "commit_sha": a.get("commit_sha") or "",
            "predicted_roi": a.get("predicted_roi"),
        })
    return rows


def calibrate(rows):
    """Derive the effort->tokens bands from the data itself."""
    by_score = {}
    for r in rows:
        s = r["declared_effort_score"]
        if s is None or not r["tokens_used"]:
            continue
        by_score.setdefault(s, []).append(r["tokens_used"])

    bands = {}
    for s, toks in sorted(by_score.items()):
        med = statistics.median(toks)
        bands[s] = {
            "n": len(toks),
            "median_tokens": round(med),
            "min": min(toks),
            "max": max(toks),
            # spread relative to the median: a class that predicts nothing is wide
            "spread_ratio": round((max(toks) - min(toks)) / med, 2) if med else None,
        }

    # per-row error against its own class median
    errors = []
    for r in rows:
        s, t = r["declared_effort_score"], r["tokens_used"]
        if s in bands and t:
            med = bands[s]["median_tokens"]
            r["class_median"] = med
            r["error_ratio"] = round(t / med, 2) if med else None
            errors.append(abs(t - med) / med if med else 0)

    ordered_scores = sorted(bands)
    medians = [bands[s]["median_tokens"] for s in ordered_scores]
    monotonic = all(a <= b for a, b in zip(medians, medians[1:]))

    return {
        "bands": bands,
        "mean_abs_error_ratio": round(statistics.mean(errors), 2) if errors else None,
        "monotonic": monotonic,
        "monotonicity_note": (
            "effort_score medians rise with the score — the scale predicts cost"
            if monotonic else
            "effort_score medians are NOT ordered: a higher score does not mean more "
            "tokens, so the scale is not predicting anything and the schema needs the fix, "
            "not any individual lug"
        ),
    }


def report(root):
    rows = build_rows(root)
    cal = calibrate(rows)

    spend_no_artifact = [r for r in rows if r["tokens_used"] and not r["commit_sha"]]
    tier_drift = [r for r in rows if r["tier_drift"]]
    unknown_lug = [r for r in rows if not r["lug_known"]]

    scored = [r for r in rows if r.get("error_ratio")]
    worst_over = sorted(scored, key=lambda r: -r["error_ratio"])[:5]
    worst_under = sorted(scored, key=lambda r: r["error_ratio"])[:5]

    return {
        "runs_measured": len(rows),
        "total_tokens": sum(r["tokens_used"] or 0 for r in rows),
        "calibration": cal,
        "spend_without_artifact": {
            "count": len(spend_no_artifact),
            "tokens": sum(r["tokens_used"] or 0 for r in spend_no_artifact),
            "note": "tokens spent on runs that recorded no commit_sha",
        },
        "tier_drift": {
            "count": len(tier_drift),
            "examples": [{"lug_id": r["lug_id"], "declared": r["declared_model_fit"],
                          "ran_as": r["run_model_fit"]} for r in tier_drift[:5]],
        },
        "runs_for_unknown_lugs": len(unknown_lug),
        "worst_overspend": [{"lug_id": r["lug_id"], "effort": r["declared_effort_score"],
                             "tokens": r["tokens_used"], "x_median": r["error_ratio"]}
                            for r in worst_over],
        "worst_underspend": [{"lug_id": r["lug_id"], "effort": r["declared_effort_score"],
                              "tokens": r["tokens_used"], "x_median": r["error_ratio"]}
                             for r in worst_under],
        "rows": rows,
    }


def write_ledger(root, rows):
    """Append-only, keyed, and idempotent: re-running never double-counts."""
    p = root / LEDGER
    p.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    if p.exists():
        for line in p.read_text(errors="replace").splitlines():
            try:
                seen.add(json.loads(line).get("key"))
            except json.JSONDecodeError:
                continue
    added = 0
    with p.open("a") as fh:
        for r in rows:
            if r["key"] in seen:
                continue
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            added += 1
    return added


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spoke-root", default=".")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", action="store_true",
                    help="append new rows to the cost ledger (idempotent)")
    a = ap.parse_args()

    root = Path(a.spoke_root).resolve()
    if not root.is_dir():
        sys.stderr.write(f"not a directory: {root}\n")
        return 2

    res = report(root)

    if a.write:
        res["ledger_rows_added"] = write_ledger(root, res["rows"])

    if a.json:
        out = dict(res)
        out.pop("rows", None)
        print(json.dumps(out, indent=2))
        return 0

    cal = res["calibration"]
    print(f"cost ledger — {res['runs_measured']} measured run(s), "
          f"{res['total_tokens']:,} tokens")
    print("\n  effort_score -> measured tokens (bands derived from the data):")
    for s, b in cal["bands"].items():
        print(f"    score {s}: n={b['n']:3d}  median={b['median_tokens']:>7,}  "
              f"range {b['min']:,}-{b['max']:,}  spread x{b['spread_ratio']}")
    print(f"\n  mean absolute error vs class median: {cal['mean_abs_error_ratio']}")
    print(f"  monotonic: {cal['monotonic']} — {cal['monotonicity_note']}")

    s = res["spend_without_artifact"]
    print(f"\n  spend without artifact: {s['count']} run(s), {s['tokens']:,} tokens")
    print(f"  tier drift (declared != ran as): {res['tier_drift']['count']}")
    for e in res["tier_drift"]["examples"]:
        print(f"    - {e['lug_id']}: declared {e['declared']}, ran as {e['ran_as']}")
    print(f"  runs for lugs no longer on disk: {res['runs_for_unknown_lugs']}")

    print("\n  worst overspend vs its own effort class:")
    for r in res["worst_overspend"]:
        print(f"    {r['x_median']:>5}x  effort {r['effort']}  {r['tokens']:>7,}  {r['lug_id']}")
    if a.write:
        print(f"\n  ledger rows added: {res['ledger_rows_added']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
