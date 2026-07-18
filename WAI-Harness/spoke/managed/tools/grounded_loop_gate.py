#!/usr/bin/env python3
"""grounded_loop_gate.py — the loop-close gate.

The mechanical expression of "we don't move forward unless we do what we say": a loop only
earns a hard 'completed' when its declared metric actually moved as contracted. Otherwise it
is 'flagged' (advisory, non-destructive) with a human-readable reason naming the metric and
its before/after. Reverting is OFF by default and only available behind an explicit flag.

Backward compatible by construction: a lug with NO grounded_loop contract passes straight
through as 'completed', so wiring this into autopilot cannot regress existing work.

  close_gate(lug, before, after, allow_revert=False) ->
    {"verdict": "completed"|"flagged"|"reverted",
     "reason": str, "metric": str|None, "soft": bool, "before": any, "after": any}
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

# Make sibling tools importable regardless of how this module is loaded.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _passthrough(before: Any, after: Any, reason: str) -> Dict[str, Any]:
    return {"verdict": "completed", "reason": reason, "metric": None,
            "soft": False, "before": before, "after": after}


def close_gate(lug: Dict[str, Any], before: Any, after: Any, allow_revert: bool = False) -> Dict[str, Any]:
    gl = lug.get("grounded_loop") if isinstance(lug, dict) else None
    if not isinstance(gl, dict) or not isinstance(gl.get("metric_target"), dict):
        return _passthrough(before, after, "no grounded_loop contract (backward-compatible pass-through)")

    mt = gl["metric_target"]
    metric = mt.get("name") or "unnamed metric"
    loop_type = mt.get("oracle")
    direction = mt.get("direction", "up")

    try:
        from grounded_oracle_map import get_oracle, run_oracle
    except Exception as exc:  # oracle map missing -> degrade to soft, never a false green
        return {"verdict": "completed", "reason": f"soft: oracle map unavailable ({exc})",
                "metric": metric, "soft": True, "before": before, "after": after}

    entry = get_oracle(loop_type)
    res = run_oracle(loop_type, before, after, direction)
    moved = res.get("moved")

    # Soft outcome (explicitly soft contract, soft oracle, or unmeasurable) -> completed
    # BUT labeled soft; it is never presented as a hard green.
    if mt.get("soft") is True or entry.get("kind") == "soft" or moved is None:
        limits = res.get("soft_limits") or mt.get("soft_limits") or ""
        return {"verdict": "completed", "soft": True, "metric": metric,
                "reason": f"soft metric '{metric}': {res.get('detail','')} — {limits}".strip(),
                "before": before, "after": after}

    if moved:
        return {"verdict": "completed", "soft": False, "metric": metric,
                "reason": f"metric '{metric}' moved {direction}: {res.get('detail','')}",
                "before": before, "after": after}

    # Declared metric did NOT move.
    verdict = "reverted" if allow_revert else "flagged"
    return {"verdict": verdict, "soft": False, "metric": metric,
            "reason": (f"metric '{metric}' did NOT move {direction} "
                       f"(before={before!r}, after={after!r}); {res.get('detail','')}"),
            "before": before, "after": after}


if __name__ == "__main__":
    import json
    lug = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(close_gate(lug, None, None), indent=2))
