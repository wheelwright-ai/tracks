#!/usr/bin/env python3
"""ap_review.py -- what did the last AP rounds actually produce?

The review half of run/review/learn/evolve/repeat (operator, 2026-08-14). A round's
own completion count is the claim the productiveness gate exists to distrust, so this
reads the MEASURED verdicts ozi_autopilot writes to
`WAI-Harness/spoke/local/maintenance/ap-runs.jsonl` -- one line per round, one verdict
per dispatch -- and answers three questions a human would otherwise have to reconstruct
from scrollback:

  1. what fraction of dispatches produced anything, per spoke
  2. which lugs came back unproductive, and for what stated reason
  3. did any round halt on the 3-strike gate

Reads only. Writes nothing. Reports UNKNOWN rather than 0 for a spoke that has no
record file, because "never recorded a round" and "ran a round that produced nothing"
are different findings and collapsing them hides the first.

CLI:
    python3 ap_review.py                          # every registry spoke with a record
    python3 ap_review.py --spoke /path/to/spoke   # one spoke (repeatable)
    python3 ap_review.py --rounds 5               # last N rounds per spoke (default 5)
    python3 ap_review.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

RECORD_REL = Path("WAI-Harness") / "spoke" / "local" / "maintenance" / "ap-runs.jsonl"
DEFAULT_REGISTRY = (
    Path(__file__).resolve().parents[4] / "WAI-Harness" / "hub" / "local" / "hub-registry.json"
)
# Statuses whose spokes are meant to be doing work. Anything else is not a finding
# when it has no rounds.
ACTIVE_STATUSES = {"active", "dogfood"}


def _read_rounds(spoke_root: Path, limit: int) -> List[Dict[str, Any]]:
    path = spoke_root / RECORD_REL
    if not path.exists():
        return []
    rounds: List[Dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rounds.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue          # a torn line must not hide the good ones
    except OSError:
        return []
    return rounds[-limit:] if limit > 0 else rounds


def _summarise(name: str, spoke_root: Path, limit: int) -> Dict[str, Any]:
    rounds = _read_rounds(spoke_root, limit)
    if not rounds:
        return {"spoke": name, "path": str(spoke_root), "state": "UNRECORDED",
                "rounds": 0, "dispatched": 0, "productive": 0, "unproductive": 0,
                "halted": 0, "tokens": 0, "unproductive_reasons": []}

    dispatched = sum(int(r.get("dispatched") or 0) for r in rounds)
    productive = sum(int(r.get("productive") or 0) for r in rounds)
    halted = sum(1 for r in rounds if r.get("halted_unproductive"))
    tokens = sum(int(r.get("tokens_used") or 0) for r in rounds)

    reasons: List[Dict[str, str]] = []
    for r in rounds:
        for v in r.get("verdicts") or []:
            if not v.get("productive"):
                reasons.append({
                    "lug_id": str(v.get("lug_id", "?")),
                    "model": str(v.get("model", "?")),
                    "why": str(v.get("why", "")),
                })

    return {
        "spoke": name,
        "path": str(spoke_root),
        "state": "RECORDED",
        "rounds": len(rounds),
        "dispatched": dispatched,
        "productive": productive,
        "unproductive": dispatched - productive,
        "halted": halted,
        "tokens": tokens,
        "unproductive_reasons": reasons,
    }


def _registry_spokes(registry: Path) -> List[Dict[str, str]]:
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for w in data.get("wheels", []) or []:
        status = str(w.get("status", "")).lower()
        path = w.get("path")
        if not path or status not in ACTIVE_STATUSES:
            continue
        out.append({"name": w.get("wheel_id") or Path(path).name, "path": path})
    return out


def _rate(part: int, whole: int) -> str:
    return f"{(100.0 * part / whole):.0f}%" if whole else "--"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spoke", action="append", default=[],
                    help="spoke root to review; repeatable. Default: active registry spokes")
    ap.add_argument("--rounds", type=int, default=5,
                    help="how many most-recent rounds per spoke (0 = all; default 5)")
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--reasons", type=int, default=6,
                    help="max unproductive reasons to print per spoke (default 6)")
    args = ap.parse_args(argv)

    if args.spoke:
        # resolve() so `--spoke .` reports the directory's real name, not ""
        targets = [{"name": Path(s).resolve().name, "path": s} for s in args.spoke]
    else:
        targets = _registry_spokes(Path(args.registry))
        if not targets:
            print(f"no active spokes found in {args.registry}", file=sys.stderr)
            return 1

    rows = [_summarise(t["name"], Path(t["path"]), args.rounds) for t in targets]

    if args.json:
        print(json.dumps({"rounds_per_spoke": args.rounds, "spokes": rows}, indent=2))
        return 0

    recorded = [r for r in rows if r["state"] == "RECORDED"]
    unrecorded = [r for r in rows if r["state"] == "UNRECORDED"]

    d = sum(r["dispatched"] for r in recorded)
    p = sum(r["productive"] for r in recorded)
    print(f"AP review -- last {args.rounds or 'all'} round(s) per spoke")
    print(f"  {len(recorded)} spoke(s) with records, {len(unrecorded)} never recorded a round")
    print(f"  {p}/{d} dispatches produced something ({_rate(p, d)}); "
          f"{sum(r['halted'] for r in recorded)} round(s) halted on the gate")
    print()

    if recorded:
        print(f"{'spoke':<28} {'rnds':>4} {'disp':>5} {'prod':>5} {'unprod':>6} {'rate':>5} {'halt':>4}")
        for r in sorted(recorded, key=lambda x: -x["dispatched"]):
            print(f"{r['spoke']:<28} {r['rounds']:>4} {r['dispatched']:>5} "
                  f"{r['productive']:>5} {r['unproductive']:>6} "
                  f"{_rate(r['productive'], r['dispatched']):>5} {r['halted']:>4}")
        print()

    for r in recorded:
        if not r["unproductive_reasons"]:
            continue
        print(f"unproductive in {r['spoke']}:")
        for item in r["unproductive_reasons"][: args.reasons]:
            print(f"  - {item['lug_id']} [{item['model']}] {item['why']}")
        extra = len(r["unproductive_reasons"]) - args.reasons
        if extra > 0:
            print(f"  ... and {extra} more")
        print()

    if unrecorded:
        print("no round recorded (UNKNOWN, not zero):")
        for r in unrecorded:
            print(f"  - {r['spoke']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
