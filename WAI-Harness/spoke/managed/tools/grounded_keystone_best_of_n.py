#!/usr/bin/env python3
"""grounded_keystone_best_of_n.py — best-of-N for KEYSTONE lugs, selected by MEASURED movement.

ComPilot's best-of-N, made honest and made cheap:

  * honest — "best" is NOT a judge's opinion. It is the largest MEASURED movement of the
    lug's own declared metric_target, computed by the deterministic oracle bound in
    grounded_oracle_map and stamped by grounded_loop_gate.close_gate. If no HARD oracle
    can measure an attempt, this module refuses to invent a winner: it falls back to the
    first attempt and labels the result soft (never a hard green).

  * cheap — best-of-N only runs for KEYSTONE lugs. Every other lug takes the bypass path
    and the attempt runner is invoked EXACTLY ONCE, so wiring this in fleet-wide costs
    nothing beyond a dict lookup. That cost guard is proven by test, not asserted.

This is a thin SELECTOR, not a new judge engine. The attempt/judge plumbing is reused from
the existing Assessor-fusion substrate at WAI-Harness/hub/managed/fusion (see
fusion_attempt_runner); fusion decides HOW an attempt is produced, this module decides
WHICH attempt won — and it decides that by measurement alone.

  best_of_n(lug, n=5, runner=..., initiative=None) ->
    {"chosen_attempt": any, "chosen_index": int, "metric_movements": [...],
     "keystone": bool, "bypassed": bool, "attempts_run": int,
     "selection_basis": str, "soft": bool, "any_moved": bool, "reason": str}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Sibling tools importable regardless of how this module is loaded.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TOOLS = Path(__file__).resolve().parent          # spoke/managed/tools
_REPO = _TOOLS.parents[3]                          # repo root (…/mywheel)
FUSION_DIR = _REPO / "WAI-Harness" / "hub" / "managed" / "fusion"
_INITIATIVES = _REPO / "WAI-Harness" / "spoke" / "local" / "initiatives" / "bytype" / "initiative"

DEFAULT_N = 5


# ---------------------------------------------------------------------------
# keystone detection (the cost guard's predicate)
# ---------------------------------------------------------------------------

def _initiative_marks_keystone(lug_id: str, initiative: Dict[str, Any]) -> bool:
    if not isinstance(initiative, dict) or not lug_id:
        return False
    if initiative.get("keystone_lug") == lug_id:
        return True
    keystones = initiative.get("keystone_lugs")
    return isinstance(keystones, list) and lug_id in keystones


def _load_initiative(initiative_id: str, root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Find an initiative json by id under initiatives/bytype/initiative/<state>/."""
    if not initiative_id:
        return None
    base = (Path(root) / "WAI-Harness" / "spoke" / "local" / "initiatives"
            / "bytype" / "initiative") if root else _INITIATIVES
    if not base.is_dir():
        return None
    for path in base.glob(f"*/{initiative_id}.json"):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def is_keystone(lug: Dict[str, Any], initiative: Optional[Dict[str, Any]] = None,
                root: Optional[Path] = None) -> bool:
    """True when this lug is a keystone. Sources, in order of authority:
      1. explicit lug flag        lug.keystone / lug.is_keystone == True
      2. contract flag            lug.grounded_loop.keystone == True
      3. injected initiative      initiative.keystone_lug (or keystone_lugs[])
      4. initiative on disk       resolved from lug.initiative_id
    Anything else is NOT a keystone — the default is the cheap path."""
    if not isinstance(lug, dict):
        return False
    if lug.get("keystone") is True or lug.get("is_keystone") is True:
        return True
    gl = lug.get("grounded_loop")
    if isinstance(gl, dict) and gl.get("keystone") is True:
        return True
    lug_id = lug.get("id") or ""
    if _initiative_marks_keystone(lug_id, initiative or {}):
        return True
    if initiative is None:
        loaded = _load_initiative(lug.get("initiative_id") or "", root=root)
        if loaded and _initiative_marks_keystone(lug_id, loaded):
            return True
    return False


# ---------------------------------------------------------------------------
# measurement — the ONLY thing selection is allowed to key on
# ---------------------------------------------------------------------------

def _signed_magnitude(before: Any, after: Any, direction: str) -> Optional[float]:
    """How FAR the metric moved in the contracted direction. Positive = progress.
    None when either reading is missing or non-comparable."""
    if before is None or after is None:
        return None
    if direction == "becomes_true":
        try:
            return 1.0 if (bool(float(after)) and not bool(float(before))) else 0.0
        except (TypeError, ValueError):
            return 1.0 if (bool(after) and not bool(before)) else 0.0
    try:
        b, a = float(before), float(after)
    except (TypeError, ValueError):
        return None
    return (b - a) if direction == "down" else (a - b)


def measure_attempt(lug: Dict[str, Any], before: Any, after: Any) -> Dict[str, Any]:
    """Measure one attempt against the lug's declared metric_target.

    Returns {moved, magnitude, kind, soft, verdict, metric, direction, before, after, detail}.
    magnitude is populated ONLY for a HARD oracle on a non-soft contract — a soft/unbound
    oracle produces no number to rank on, by design."""
    from grounded_loop_gate import close_gate
    from grounded_oracle_map import get_oracle, run_oracle

    mt = ((lug.get("grounded_loop") or {}).get("metric_target") or {}) if isinstance(lug, dict) else {}
    loop_type = mt.get("oracle")
    direction = mt.get("direction", "up")
    entry = get_oracle(loop_type)
    res = run_oracle(loop_type, before, after, direction)
    gate = close_gate(lug, before, after)

    hard = entry.get("kind") == "hard" and mt.get("soft") is not True and res.get("moved") is not None
    return {
        "metric": mt.get("name"),
        "oracle": loop_type,
        "direction": direction,
        "before": before,
        "after": after,
        "kind": entry.get("kind"),
        "moved": res.get("moved"),
        "magnitude": _signed_magnitude(before, after, direction) if hard else None,
        "soft": not hard,
        "verdict": gate.get("verdict"),
        "detail": res.get("detail", ""),
        "soft_limits": res.get("soft_limits") or mt.get("soft_limits") or "",
    }


# ---------------------------------------------------------------------------
# attempt runners
# ---------------------------------------------------------------------------

def capture_reading(lug: Dict[str, Any]) -> Any:
    """Take a live reading of the lug's declared oracle (None if unmeasurable)."""
    from grounded_oracle_map import get_oracle

    mt = ((lug.get("grounded_loop") or {}).get("metric_target") or {}) if isinstance(lug, dict) else {}
    try:
        return get_oracle(mt.get("oracle"))["capture"]()
    except Exception:
        return None


def fusion_attempt_runner(strategy: str = "fusion-eask", mock: bool = True,
                          work_category: str = "general") -> Callable[[Dict[str, Any], int], Dict[str, Any]]:
    """Build an attempt runner backed by the EXISTING Assessor-fusion substrate
    (WAI-Harness/hub/managed/fusion). Fusion produces the attempt; this module still
    selects on measured movement, so no fusion judge score is ever consulted here.

    Readings are captured around the attempt via the lug's own oracle, so the returned
    attempt is directly rankable."""
    def _run(lug: Dict[str, Any], index: int) -> Dict[str, Any]:
        sys.path.insert(0, str(FUSION_DIR))
        from model_router import ModelRouter  # noqa: E402  (hub fusion substrate)
        from orchestrator import run_strategy  # noqa: E402

        task = lug.get("summary") or lug.get("title") or lug.get("id") or "untitled"
        before = capture_reading(lug)
        record = run_strategy(strategy, task, router=ModelRouter(force_mock=mock),
                              work_category=work_category, seq=index, persist=False)
        after = capture_reading(lug)
        return {"attempt_index": index, "before": before, "after": after,
                "fusion_run_id": record.get("run_id"), "fusion_run": record}

    return _run


# ---------------------------------------------------------------------------
# the selector
# ---------------------------------------------------------------------------

def _readings(attempt: Any) -> tuple:
    if isinstance(attempt, dict):
        return attempt.get("before"), attempt.get("after")
    return None, None


def best_of_n(lug: Dict[str, Any], n: int = DEFAULT_N,
              runner: Optional[Callable[[Dict[str, Any], int], Any]] = None,
              initiative: Optional[Dict[str, Any]] = None,
              root: Optional[Path] = None) -> Dict[str, Any]:
    """Run N attempts for a KEYSTONE lug and choose the one whose declared metric moved
    MOST (largest measured magnitude in the contracted direction). Ties break to the
    lowest attempt index, so the choice is reproducible.

    Non-keystone lugs BYPASS: the runner is invoked exactly once and that single attempt
    is returned unchanged. That is the cost guard.

    `runner(lug, index)` returns the attempt; a dict carrying `before`/`after` readings is
    rankable. Defaults to fusion_attempt_runner() (the hub fusion substrate)."""
    if runner is None:
        runner = fusion_attempt_runner()
    keystone = is_keystone(lug, initiative=initiative, root=root)

    if not keystone:
        attempt = runner(lug, 0)
        before, after = _readings(attempt)
        movement = measure_attempt(lug, before, after)
        movement["attempt_index"] = 0
        return {
            "keystone": False,
            "bypassed": True,
            "attempts_run": 1,
            "n_requested": n,
            "chosen_index": 0,
            "chosen_attempt": attempt,
            "metric_movements": [movement],
            "selection_basis": "bypass-non-keystone",
            "soft": bool(movement["soft"]),
            "any_moved": movement["moved"] is True,
            "reason": "non-keystone lug: single attempt, best-of-N skipped (cost guard)",
        }

    n = max(1, int(n))
    attempts: List[Any] = []
    movements: List[Dict[str, Any]] = []
    for i in range(n):
        attempt = runner(lug, i)
        attempts.append(attempt)
        before, after = _readings(attempt)
        movement = measure_attempt(lug, before, after)
        movement["attempt_index"] = i
        movements.append(movement)

    ranked = [m for m in movements if m["magnitude"] is not None]
    if ranked:
        winner = max(ranked, key=lambda m: (m["magnitude"], -m["attempt_index"]))
        chosen_index = winner["attempt_index"]
        basis = "measured-movement"
        soft = False
        reason = (f"attempt #{chosen_index} moved '{winner['metric']}' "
                  f"{winner['magnitude']} in direction '{winner['direction']}' — "
                  f"the largest MEASURED movement of {len(ranked)} measurable attempt(s)")
    else:
        chosen_index = 0
        basis = "fallback-first-no-hard-measurement"
        soft = True
        reason = ("no attempt could be measured by a hard oracle; fell back to attempt #0 and "
                  "labeled soft — a best-of-N with no measurement is never a hard green")

    return {
        "keystone": True,
        "bypassed": False,
        "attempts_run": len(attempts),
        "n_requested": n,
        "chosen_index": chosen_index,
        "chosen_attempt": attempts[chosen_index],
        "metric_movements": movements,
        "selection_basis": basis,
        "soft": soft,
        "any_moved": any(m["moved"] is True for m in movements),
        "reason": reason,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="best-of-N over a keystone lug, selected by measured metric movement")
    ap.add_argument("lug", help="path to a lug json")
    ap.add_argument("-n", type=int, default=DEFAULT_N)
    ap.add_argument("--strategy", default="fusion-eask")
    ap.add_argument("--live", action="store_true", help="use live providers (default: keyless mock)")
    ap.add_argument("--keystone-only-check", action="store_true",
                    help="report the keystone verdict without running any attempt")
    args = ap.parse_args(argv)

    lug = json.loads(Path(args.lug).read_text(encoding="utf-8"))
    if args.keystone_only_check:
        print(json.dumps({"id": lug.get("id"), "keystone": is_keystone(lug)}, indent=2))
        return 0

    res = best_of_n(lug, n=args.n,
                    runner=fusion_attempt_runner(strategy=args.strategy, mock=not args.live))
    res.pop("chosen_attempt", None)  # full fusion chain is large; keep CLI output readable
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
