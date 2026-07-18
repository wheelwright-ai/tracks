#!/usr/bin/env python3
"""contract_router — B3 tier router. Routes B2 typed events (blocks / contract
events) to Tier A / B / C using thresholds loaded from contract-routing.yaml
(DATA, never hardcoded Python literals).

route(event: dict) -> {"tier": "A"|"B"|"C", "action": str, "detail": str}

event shape (all keys optional except component / clause_or_block_class which
should be present for anything meaningful to route):
  {
    "component": str,                 # the object/component this event is about
    "clause_or_block_class": str,     # e.g. one of capgraph_blocks.VALID_CLASSES
    "occurrence_count": int,          # how many times this signature has fired
    "invariant_breach": bool,
    "goodhart_flag": bool,
    "current_tier": "A"|"B"|"C"|None, # where this event currently sits (default A)
    "slo": {"cadence": str, "grace": str} | None,   # grace like "24h" / "3d" / "30m"
    "last_emitted_at": float|str|None,              # epoch seconds or ISO8601
  }

Ladder (first applicable wins, mirrors contract-routing.yaml's straight_to_c /
tiers / slo_aging keys -- see that file for the actual numbers):
  1. invariant_breach or goodhart_flag -> straight to Tier C, any occurrence_count.
  2. current_tier == "B" and occurrence_count >= tiers.B.max_occurrence -> Tier C.
  3. aging: unresolved past slo.grace at current_tier B or C -> escalate per
     slo_aging.escalation_map (B -> C, C -> C / re-notify).
  4. current_tier == "A" (or unset) and occurrence_count >= tiers.A.max_occurrence
     -> Tier B.
  5. current_tier == "B" (not yet escalated by 2/3) -> stays Tier B.
  6. current_tier == "C" (not yet re-escalated by 3) -> stays Tier C.
  7. default -> Tier A.

Tier A is a THIN POINTER: contract_router does not import the lug object or call
goal_planner.replan_on_block() itself -- the caller (B5's evaluator / circuit_monitor
path) performs that invocation. Tier B and Tier C DO perform their reused action
directly (conductor.emit_feedback / OPERATOR-ASKS.md append + sandboxed stamp) --
see _tier_b_apply / _tier_c_apply below.

No enforcement consumer for the sandboxed:true stamp exists yet -- that is an
explicit non-goal of this lug (impl-spine-b3-tier-router-v1 naive_reader lens),
not an oversight.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

_THIS_DIR = Path(__file__).resolve().parent          # .../WAI-Harness/spoke/managed/tools
_HARNESS_DIR = _THIS_DIR.parents[2]                   # .../WAI-Harness

CONTRACT_ROUTING_YAML = _THIS_DIR.parent / "config" / "contract-routing.yaml"
DEFAULT_CONTRACTS_PATH = _HARNESS_DIR / "hub" / "local" / "contracts" / "object-contracts.json"
CONDUCTOR_SCRIPTS_DIR = _HARNESS_DIR / "hub" / "local" / "scripts"

_GRACE_SUFFIX_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def _load_thresholds(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load contract-routing.yaml (or a fixture at `path`). Reused by both the
    module-level default load and by tests proving pure-data thresholds."""
    p = Path(path) if path else CONTRACT_ROUTING_YAML
    with open(p) as f:
        return yaml.safe_load(f) or {}


# Load once at import time -- no thresholds duplicated as Python literals.
THRESHOLDS = _load_thresholds()


def _import_conductor():
    scripts_dir = str(CONDUCTOR_SCRIPTS_DIR)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import conductor  # noqa: E402  (import kept local -- conductor.py is heavy)
    return conductor


def _parse_grace_seconds(grace: Any) -> Optional[float]:
    """'24h' / '3d' / '30m' / '90s' -> seconds. Bare numbers are already seconds."""
    if grace is None:
        return None
    if isinstance(grace, (int, float)):
        return float(grace)
    s = str(grace).strip().lower()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    unit = s[-1]
    if unit in _GRACE_SUFFIX_SECONDS and s[:-1]:
        try:
            return float(s[:-1]) * _GRACE_SUFFIX_SECONDS[unit]
        except ValueError:
            return None
    return None


def _parse_ts_seconds(ts: Any) -> Optional[float]:
    """Accept epoch seconds (int/float) or an ISO8601 string; return epoch seconds."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    try:
        return float(ts)
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.timestamp()
    except ValueError:
        return None


def _aged_past_grace(current_tier: str, slo: Optional[Dict[str, Any]], last_emitted_at: Any, now: Optional[float]) -> bool:
    if not slo:
        return False
    grace_s = _parse_grace_seconds(slo.get("grace"))
    if grace_s is None:
        return False
    last_s = _parse_ts_seconds(last_emitted_at)
    if last_s is None:
        return False
    now_s = now if now is not None else time.time()
    return (now_s - last_s) > grace_s


def _decide(event: Dict[str, Any], cfg: Dict[str, Any], now: Optional[float] = None) -> Dict[str, Any]:
    """Pure tier decision -- no side effects. route() wraps this with the Tier
    B / Tier C reused-action side effects."""
    occurrence_count = int(event.get("occurrence_count") or 0)
    invariant_breach = bool(event.get("invariant_breach"))
    goodhart_flag = bool(event.get("goodhart_flag"))
    current_tier = event.get("current_tier") or "A"
    slo = event.get("slo")
    last_emitted_at = event.get("last_emitted_at")
    component = event.get("component", "unknown")

    tiers_cfg = cfg.get("tiers", {})
    a_max = tiers_cfg.get("A", {}).get("max_occurrence")
    b_max = tiers_cfg.get("B", {}).get("max_occurrence")
    straight_to_c = cfg.get("straight_to_c", {})
    slo_aging = cfg.get("slo_aging", {})
    escalation_map = slo_aging.get("escalation_map", {})

    # 1. Straight to C overrides everything, any occurrence_count.
    if straight_to_c.get("on_invariant_breach") and invariant_breach:
        return {
            "tier": "C", "action": "operator_asks_sandboxed",
            "detail": f"straight_to_c.on_invariant_breach: component={component} invariant_breach=True -- "
                      "writes OPERATOR-ASKS.md and stamps sandboxed:true",
        }
    if straight_to_c.get("on_goodhart_flag") and goodhart_flag:
        return {
            "tier": "C", "action": "operator_asks_sandboxed",
            "detail": f"straight_to_c.on_goodhart_flag: component={component} goodhart_flag=True -- "
                      "writes OPERATOR-ASKS.md and stamps sandboxed:true",
        }

    # 2. Occurrence-based escalation B -> C.
    if current_tier == "B" and b_max is not None and occurrence_count >= b_max:
        return {
            "tier": "C", "action": "operator_asks_sandboxed",
            "detail": f"occurrence_count={occurrence_count} >= tiers.B.max_occurrence({b_max}) at B -- "
                      "writes OPERATOR-ASKS.md and stamps sandboxed:true",
        }

    # 3. Aging re-escalation (slo.grace) -- governed entirely by escalation_map.
    if slo_aging.get("reescalate_past_grace") and current_tier in escalation_map:
        if _aged_past_grace(current_tier, slo, last_emitted_at, now):
            next_tier = escalation_map[current_tier]
            if next_tier == "C":
                return {
                    "tier": "C", "action": "operator_asks_sandboxed",
                    "detail": f"aging: unresolved at {current_tier} past slo.grace -> escalate to C "
                              "(slo_aging.escalation_map) -- writes OPERATOR-ASKS.md and stamps sandboxed:true",
                }
            if next_tier == "B":
                return {
                    "tier": "B", "action": "conductor_emit_feedback",
                    "detail": f"aging: unresolved at {current_tier} past slo.grace -> escalate to B "
                              "(slo_aging.escalation_map) -- calls conductor.emit_feedback(record, harness_gap=True)",
                }

    # 4. Occurrence-based escalation A -> B.
    if current_tier == "A" and a_max is not None and occurrence_count >= a_max:
        return {
            "tier": "B", "action": "conductor_emit_feedback",
            "detail": f"occurrence_count={occurrence_count} >= tiers.A.max_occurrence({a_max}) at A -- "
                      "calls conductor.emit_feedback(record, harness_gap=True)",
        }

    # 5 / 6. Stay at current tier if already escalated (B or C) and not re-escalated above.
    if current_tier == "B":
        return {
            "tier": "B", "action": "conductor_emit_feedback",
            "detail": "remains at B pending resolution -- calls conductor.emit_feedback(record, harness_gap=True)",
        }
    if current_tier == "C":
        return {
            "tier": "C", "action": "operator_asks_sandboxed",
            "detail": "remains at C pending resolution -- writes OPERATOR-ASKS.md and stamps sandboxed:true",
        }

    # 7. Default: Tier A, point at goal_planner's ladder. contract_router does NOT
    # call goal_planner.replan_on_block() itself -- the caller invokes it.
    return {
        "tier": "A", "action": "goal_planner_ladder",
        "detail": f"occurrence_count={occurrence_count} below tiers.A.max_occurrence({a_max}), no breach flags -- "
                  "caller should invoke goal_planner.replan_on_block(lug, block_class, reason, ...) "
                  "(contract_router names the integration point, it does not call it)",
    }


def _tier_b_apply(event: Dict[str, Any], detail: str, conductor_module=None) -> None:
    """Tier B reused action: conductor.emit_feedback(record, harness_gap=True)."""
    conductor_module = conductor_module or _import_conductor()
    record = {
        "spoke": event.get("component", "unknown"),
        "reason": detail,
        "clause_or_block_class": event.get("clause_or_block_class"),
        "occurrence_count": event.get("occurrence_count"),
        "tier": "B",
    }
    conductor_module.emit_feedback(record, harness_gap=True)


def _tier_c_apply(
    event: Dict[str, Any],
    detail: str,
    operator_asks_path: Optional[Path] = None,
    contracts_path: Optional[Path] = None,
    conductor_module=None,
) -> None:
    """Tier C reused action: append to OPERATOR-ASKS.md (reusing conductor's
    OPERATOR_ASKS path/format, no second hardcoded path string) AND stamp the
    component's object-contracts.json entry sandboxed:true."""
    conductor_module = conductor_module or _import_conductor()
    asks_path = Path(operator_asks_path) if operator_asks_path else conductor_module.OPERATOR_ASKS
    component = event.get("component", "unknown")
    ts = datetime.now(timezone.utc).isoformat()
    block = f"\n## contract_router Tier C -- {component} ({ts})\n{detail}\n"
    asks_path.parent.mkdir(parents=True, exist_ok=True)
    existing = asks_path.read_text() if asks_path.exists() else ""
    asks_path.write_text(existing + block)
    _stamp_sandboxed(component, contracts_path)


def _stamp_sandboxed(component: str, contracts_path: Optional[Path] = None) -> None:
    path = Path(contracts_path) if contracts_path else DEFAULT_CONTRACTS_PATH
    if not path.exists():
        return
    data = json.loads(path.read_text())
    changed = False
    for entry in data.get("contracts", []):
        if entry.get("object") == component:
            entry["sandboxed"] = True
            changed = True
    if changed:
        path.write_text(json.dumps(data, indent=2))


def route(
    event: Dict[str, Any],
    *,
    thresholds: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
    operator_asks_path: Optional[Path] = None,
    contracts_path: Optional[Path] = None,
    conductor_module=None,
    apply_side_effects: bool = True,
) -> Dict[str, Any]:
    """route(event) -> {tier, action, detail}.

    `thresholds` lets a caller (tests) prove routing is pure-data by loading a
    fixture contract-routing.yaml via _load_thresholds() and passing it here --
    no code change required to alter the decision. Defaults to the module-level
    THRESHOLDS loaded once at import time from contract-routing.yaml.

    Tier B and Tier C perform their reused side effect (conductor.emit_feedback /
    OPERATOR-ASKS.md append + sandboxed stamp) unless apply_side_effects=False.
    Tier A never has a side effect here -- it only names the integration point.
    """
    cfg = thresholds if thresholds is not None else THRESHOLDS
    decision = _decide(event, cfg, now=now)

    if apply_side_effects:
        if decision["tier"] == "B":
            _tier_b_apply(event, decision["detail"], conductor_module=conductor_module)
        elif decision["tier"] == "C":
            _tier_c_apply(
                event, decision["detail"],
                operator_asks_path=operator_asks_path,
                contracts_path=contracts_path,
                conductor_module=conductor_module,
            )

    return decision


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="contract_router -- route a B2 event to Tier A/B/C (demo/inspect)")
    ap.add_argument("--event-json", required=True, help="JSON-encoded event dict")
    ap.add_argument("--dry-run", action="store_true", help="decide only, skip Tier B/C side effects")
    args = ap.parse_args()
    ev = json.loads(args.event_json)
    result = route(ev, apply_side_effects=not args.dry_run)
    print(json.dumps(result, indent=2))
