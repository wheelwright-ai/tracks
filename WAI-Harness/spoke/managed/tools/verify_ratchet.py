#!/usr/bin/env python3
"""verify_ratchet.py — the executable-verify ratio, measured, and a floor that only rises.

WHY THIS EXISTS
---------------
Ruling 21 (operator, s140): "must mandate repeatable checks going forward a machine can
run." A mandate that is only written down decays. This is the instrument that makes it
observable and irreversible.

Two jobs:

  1. MEASURE. Walk the real lug corpus, run each verify block through the same classifier
     the v5 migration uses, and report how many are machine-runnable. Measured at
     ratification: 236 of 1842 (12.8%). The figure previously in circulation was "366
     prose-only lugs" -- an undercount by more than four times, because it was a sample
     that had been treated as a total. Nobody had run the measurement.

  2. RATCHET. Store the high-water mark. If the ratio falls below it, exit non-zero. A
     number that can go down quietly is a number nobody defends; a floor that only rises
     turns it into something people protect. The floor moves up on its own and never down
     -- there is deliberately no flag to lower it, because the only honest way to lower
     this number is to delete work.

WHAT IT IS NOT
--------------
Not a quality measure. An executable check can still be a bad check. This counts whether
a claim CAN be re-tested, not whether it is true -- that is the reconciler's job
(Ruling 20). Conflating the two would be exactly the Goodhart failure this whole
initiative exists to avoid.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
BASE = REPO / "WAI-Harness/spoke/local"
STATE = BASE / "archeologist/verify-ratchet.json"

sys.path.insert(0, str(REPO / "WAI-Harness/spoke/managed/tools"))

_ACTOR = {"model": "ratchet", "provider": "deterministic"}
# Fixed timestamp: the classification must be a pure function of the corpus, so two runs
# over an unchanged tree produce an identical answer. A clock read here would make the
# ratchet's own output non-deterministic.
_AT = "2026-01-01T00:00:00+00:00"


def measure(root: Path) -> dict:
    import verification_objects as vo

    executable, unexecutable, errored = [], [], []
    for f in glob.glob(str(root / "lugs/bytype/*/*/*.json")):
        try:
            d = json.loads(Path(f).read_text())
        except Exception:
            continue
        if not isinstance(d, dict) or "verify" not in d:
            continue
        lug_id = d.get("id") or Path(f).stem
        try:
            v = vo.migrate_v4_verify(d, _ACTOR, _AT)
        except Exception as exc:
            errored.append({"id": lug_id, "error": type(exc).__name__})
            continue
        (executable if v.get("executability") == "EXECUTABLE" else unexecutable).append(lug_id)

    total = len(executable) + len(unexecutable)
    ratio = (len(executable) / total) if total else 0.0
    return {
        "total_with_verify": total,
        "executable": len(executable),
        "unexecutable": len(unexecutable),
        "errored": len(errored),
        "ratio": round(ratio, 4),
        "pct": round(ratio * 100, 1),
        "executable_ids_sample": sorted(executable)[:10],
    }


def load_floor() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {"floor_ratio": 0.0, "history": []}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=str(BASE))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--set-floor", action="store_true",
                    help="raise the stored floor to the measured ratio (never lowers it)")
    args = ap.parse_args(argv)

    m = measure(Path(args.base))
    state = load_floor()
    floor = state.get("floor_ratio", 0.0)
    regressed = m["ratio"] < floor

    if args.set_floor and m["ratio"] > floor:
        state["floor_ratio"] = m["ratio"]
        state.setdefault("history", []).append(
            {"ratio": m["ratio"], "executable": m["executable"], "total": m["total_with_verify"]}
        )
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, indent=2))
        floor = m["ratio"]

    out = {**m, "floor_ratio": floor, "floor_pct": round(floor * 100, 1), "regressed": regressed}

    if args.json:
        print(json.dumps(out, indent=2, sort_keys=True))
    else:
        print(f"[verify-ratchet] machine-runnable checks: {m['executable']}/{m['total_with_verify']} "
              f"({m['pct']}%)   floor {out['floor_pct']}%")
        if regressed:
            print(f"  REGRESSED — the ratio fell below the floor. New work shipped a verify a "
                  f"machine cannot run, which Ruling 21 forbids.")
        if m["errored"]:
            print(f"  {m['errored']} lug(s) could not be classified at all — investigate, do not ignore.")

    return 1 if regressed else 0


if __name__ == "__main__":
    raise SystemExit(main())
