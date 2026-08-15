#!/usr/bin/env python3
"""bursar.py — the Bursar role (directive §18, renamed per Ruling 5; contract
"Bursar"). The capacity-ALLOCATION advisor: it turns Spoke Advisor recommendations,
goals, endorsement, initiative impact, ready-backlog demand, forecasts, urgency,
dependencies, policy, availability, budget and execution windows into capacity
allotments across spokes / groups / initiatives / work classes / execution windows.

THE SEPARATION THAT MATTERS MOST (directive §17/§18, Ruling 5, design assertion 10):
  - Ozi REQUESTS and manages capacity locally, within whatever it is given here.
    This module never talks to Ozi and never dispatches anything.
  - The Spoke Advisor (spoke_advisor.py) EVALUATES whether a spoke's need is
    justified and hands this module a verdict. This module NEVER re-derives that
    verdict itself — it only consumes VERDICTS strings and applies the policy
    multiplier for each. A spoke doing badly does not get more capacity here
    because the advisor already said so upstream; the Bursar's only lever on
    that finding is to honor it (OFF_TARGET spokes get zero ordinary allotment).
  - The Bursar ALLOCATES. It never selects a provider or model recipe — that is
    the Alchemist's job (Phase 6); this module has no provider/model vocabulary
    in its allocation math (model_fit only appears read-only, inside the
    demand-model breakdown, as a description of what the backlog needs — never
    as a routing decision).
  - Conductor is untouched. This module is never imported by any dispatch path
    (see test_bursar.py::test_no_dispatch_path_imports_bursar for the standing
    proof) and it performs no dispatch of its own.

DETERMINISM (§40): compute_ready_backlog() and allocate() are pure functions of
their inputs — arithmetic and sorted iteration only. No LLM call, no randomness,
no wall-clock branching inside the pure core. Same inputs -> byte-identical
allocation, every time; that is what makes the allocation auditable.

RESERVES (§42): allocate() ALWAYS reserves capacity for verification, maintenance,
enablement, experiments and urgent blockers before a single unit reaches ordinary
backlog work, and it never lets ordinary backlog consume 100% of capacity merely
because ready work exists for all of it — the reserve is carved out first and is
not backfilled by excess backlog demand.

GLOBAL PRIORITISATION ORDER (§22) — visible in code, not implied:
    GROUP GOALS -> SPOKE GOALS -> INITIATIVE IMPACT -> READY LUG IMPACT -> EFFORT
    -> CAPACITY DEMAND
See PRIORITY_ORDER / PRIORITY_WEIGHTS below; the composite score is built by
iterating PRIORITY_ORDER in this exact sequence, so the ordering cannot silently
drift out of sync with the constant.
"""
from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import spoke_advisor  # only for the VERDICTS vocabulary — never calls evaluate()

SCHEMA = "bursar-allocation-v1"
BACKLOG_SCHEMA = "ready-backlog-demand-v1"

# --- §22 global prioritisation order, in the exact required sequence ------------
PRIORITY_ORDER: List[str] = [
    "group_goals", "spoke_goals", "initiative_impact",
    "ready_lug_impact", "effort", "capacity_demand",
]
# Strictly decreasing weights so the order above is enforced arithmetically, not
# just by convention: each earlier factor outweighs the sum of everything after it
# (32 > 16+8+4+2+1=31), which is the standard way to encode a lexicographic
# priority as a single weighted score without losing continuity between spokes
# that tie on the top factor.
PRIORITY_WEIGHTS: Dict[str, float] = {
    "group_goals": 32.0, "spoke_goals": 16.0, "initiative_impact": 8.0,
    "ready_lug_impact": 4.0, "effort": 2.0, "capacity_demand": 1.0,
}
assert list(PRIORITY_WEIGHTS.keys()) == PRIORITY_ORDER  # order and weights must never drift apart

# --- §42 mandatory reserve classes — never fully drained by ordinary backlog ----
RESERVE_CLASSES: List[str] = ["verification", "maintenance", "enablement", "experiments", "urgent_blockers"]
DEFAULT_RESERVE_FRACTIONS: Dict[str, float] = {
    "verification": 0.06, "maintenance": 0.05, "enablement": 0.04,
    "experiments": 0.03, "urgent_blockers": 0.05,
}  # sums to 0.23 — reserved off the top regardless of backlog size

# Advisor-verdict -> allocation multiplier. This is the ONLY place a Spoke
# Advisor verdict touches the allocation math, and it is a lookup, not a
# re-evaluation: OFF_TARGET spokes get zero ordinary allotment (§17) no matter
# how large their backlog is; NEEDS_CAPACITY spokes get a boost; INVESTIGATE
# spokes get a minimal hold rather than being either starved or rewarded.
VERDICT_MULTIPLIER: Dict[str, float] = {
    "ON_TARGET": 1.0, "NEEDS_CAPACITY": 1.35, "OFF_TARGET": 0.0, "INVESTIGATE": 0.35,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# READY BACKLOG AS A DEMAND MODEL (§21)
# =============================================================================

@dataclass
class ReadyBacklogDemand:
    count: int
    total_effort: float
    weighted_impact: float
    blocked_effort: float
    forecast_confidence: float          # 0..1, data-completeness proxy (see docstring below)
    avg_age_days: float
    max_age_days: float
    model_requirements: Dict[str, int]  # model_fit -> count, READ-ONLY description, never routing
    effort_variance: float              # population variance of ready-lug effort estimates
    by_initiative: Dict[str, Dict[str, float]] = field(default_factory=dict)


def _lug_age_days(created_at: Optional[str], now: datetime) -> Optional[float]:
    if not created_at:
        return None
    try:
        ts = created_at.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return round((now - dt).total_seconds() / 86400.0, 2)
    except Exception:
        return None


def _effort_of(rec: Dict[str, Any]) -> float:
    for key in ("effort_score", "effort"):
        v = rec.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def iter_lug_records(lugs_root: Path, statuses: Optional[List[str]] = None):
    """Yield (path, record dict) for every lug JSON under bytype/*/<status>/.

    statuses=None walks every status directory found; pass an explicit list to
    restrict (e.g. ["open"]). Malformed JSON is skipped, not fatal — the demand
    model must survive one bad file in a corpus of thousands.
    """
    bytype = lugs_root / "bytype"
    if not bytype.is_dir():
        return
    for type_dir in sorted(bytype.iterdir()):
        if not type_dir.is_dir():
            continue
        for status_dir in sorted(type_dir.iterdir()):
            if not status_dir.is_dir():
                continue
            if statuses is not None and status_dir.name not in statuses:
                continue
            for f in sorted(status_dir.glob("*.json")):
                try:
                    rec = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                yield f, rec


def compute_ready_backlog(lugs_root: Path, now: Optional[datetime] = None) -> ReadyBacklogDemand:
    """The capacity DEMAND model (§21) — a real computation over the local lug
    corpus, not a stub. "Ready" = status open with no unresolved blockers listed
    in blocked_by. Lugs with a non-empty blocked_by are counted toward
    blocked_effort instead, since capacity aimed at them would sit idle.

    forecast_confidence is a data-completeness proxy: the fraction of ready lugs
    that carry BOTH an effort figure and an impact figure (the two numbers this
    demand model actually consumes). The corpus records no forecast-vs-actual
    effort field yet (checked: zero lugs carry actual_effort/effort_actual), so
    confidence is grounded in what is actually measurable today rather than
    invented. This is documented so a future forecast-tracking lug can replace
    it without silently changing behaviour.
    """
    now = now or datetime.now(timezone.utc)
    ready: List[Dict[str, Any]] = []
    blocked_effort = 0.0
    for _path, rec in iter_lug_records(lugs_root, statuses=["open"]):
        blockers = rec.get("blocked_by") or []
        eff = _effort_of(rec)
        if blockers:
            blocked_effort += eff
        else:
            ready.append(rec)

    count = len(ready)
    total_effort = round(sum(_effort_of(r) for r in ready), 2)
    weighted_impact = 0.0
    ages: List[float] = []
    model_requirements: Dict[str, int] = {}
    complete = 0
    by_initiative: Dict[str, Dict[str, float]] = {}
    efforts: List[float] = []

    for r in ready:
        eff = _effort_of(r)
        impact = r.get("impact")
        urgency = r.get("urgency")
        efforts.append(eff)
        if isinstance(impact, (int, float)):
            urgency_weight = 0.5 + 0.5 * (min(max(urgency, 0), 10) / 10.0) if isinstance(urgency, (int, float)) else 0.5
            weighted_impact += float(impact) * urgency_weight
        if isinstance(impact, (int, float)) and eff:
            complete += 1
        mf = r.get("model_fit")
        if mf:
            model_requirements[mf] = model_requirements.get(mf, 0) + 1
        age = _lug_age_days(r.get("created_at"), now)
        if age is not None:
            ages.append(age)
        init_id = r.get("initiative_id") or "_none"
        bucket = by_initiative.setdefault(init_id, {"count": 0, "effort": 0.0, "weighted_impact": 0.0})
        bucket["count"] += 1
        bucket["effort"] += eff
        if isinstance(impact, (int, float)):
            bucket["weighted_impact"] += float(impact)

    forecast_confidence = round(complete / count, 4) if count else 0.0
    effort_variance = round(statistics.pvariance(efforts), 4) if len(efforts) >= 1 else 0.0
    avg_age = round(sum(ages) / len(ages), 2) if ages else 0.0
    max_age = round(max(ages), 2) if ages else 0.0

    return ReadyBacklogDemand(
        count=count, total_effort=total_effort, weighted_impact=round(weighted_impact, 2),
        blocked_effort=round(blocked_effort, 2), forecast_confidence=forecast_confidence,
        avg_age_days=avg_age, max_age_days=max_age, model_requirements=model_requirements,
        effort_variance=effort_variance, by_initiative=by_initiative,
    )


# =============================================================================
# ALLOCATION (§18, §22, §42)
# =============================================================================

@dataclass
class SpokeDemand:
    """One spoke's slice of demand as seen by the Bursar. group_goal_score and
    spoke_goal_score are 0..1 evidence-of-alignment figures (directive §16's
    goals, reduced to a number here only for the composite score — the goal
    TEXT itself lives on the wheel/group record, not here). advisor_verdict
    MUST be one of spoke_advisor.VERDICTS and is consumed as-is (see module
    docstring) — this dataclass carries no field that would let the Bursar
    recompute it.
    """
    spoke_id: str
    group_id: Optional[str] = None
    group_goal_score: float = 0.0
    spoke_goal_score: float = 0.0
    initiative_impact: float = 0.0
    ready_lug_impact: float = 0.0
    effort: float = 0.0
    advisor_verdict: str = "ON_TARGET"


@dataclass
class Policy:
    reserve_fractions: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_RESERVE_FRACTIONS))
    verdict_multiplier: Dict[str, float] = field(default_factory=lambda: dict(VERDICT_MULTIPLIER))


def _normalize(values: Dict[str, float]) -> Dict[str, float]:
    peak = max(values.values()) if values else 0.0
    if peak <= 0:
        return {k: 0.0 for k in values}
    return {k: v / peak for k, v in values.items()}


def allocate(total_capacity: float, demands: List[SpokeDemand],
             policy: Optional[Policy] = None,
             windows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Pure function: (capacity, demand list, policy, windows) -> allocation.

    No timestamps, no I/O, no randomness in this function — determinism (§40)
    depends on that. Callers that want a stamped report wrap this output (see
    render_report()).
    """
    policy = policy or Policy()
    for d in demands:
        if d.advisor_verdict not in spoke_advisor.VERDICTS:
            raise ValueError(f"unknown advisor verdict {d.advisor_verdict!r} for spoke {d.spoke_id}")

    # --- §42: reserve first, unconditionally, regardless of how much backlog exists.
    reserved = {cls: round(total_capacity * policy.reserve_fractions.get(cls, 0.0), 6)
                for cls in RESERVE_CLASSES}
    total_reserved = round(sum(reserved.values()), 6)
    allocatable = max(0.0, round(total_capacity - total_reserved, 6))

    # --- §22 composite score, iterating PRIORITY_ORDER in its declared sequence.
    raw = {
        "group_goals": {d.spoke_id: d.group_goal_score for d in demands},
        "spoke_goals": {d.spoke_id: d.spoke_goal_score for d in demands},
        "initiative_impact": {d.spoke_id: d.initiative_impact for d in demands},
        "ready_lug_impact": {d.spoke_id: d.ready_lug_impact for d in demands},
        "effort": {d.spoke_id: d.effort for d in demands},
        "capacity_demand": {d.spoke_id: d.effort for d in demands},  # demand pressure == effort awaiting capacity
    }
    normalized = {factor: _normalize(vals) for factor, vals in raw.items()}

    weight_sum = sum(PRIORITY_WEIGHTS.values())
    scores: Dict[str, float] = {}
    for d in demands:
        composite = 0.0
        for factor in PRIORITY_ORDER:  # order enforced by iteration, not just by weight value
            composite += PRIORITY_WEIGHTS[factor] * normalized[factor].get(d.spoke_id, 0.0)
        composite /= weight_sum
        composite *= policy.verdict_multiplier.get(d.advisor_verdict, 0.0)
        scores[d.spoke_id] = composite

    score_total = sum(scores.values())

    # --- proportional share, capped at each spoke's own effort (never allocate
    # more than a spoke has ready work for), with a single deterministic
    # water-filling redistribution pass for capacity freed by caps.
    demand_by_id = {d.spoke_id: d for d in demands}
    remaining_pool = allocatable
    fixed: Dict[str, float] = {}
    floating_ids = [d.spoke_id for d in demands]

    for _pass in range(len(demands) + 1):
        if not floating_ids or remaining_pool <= 0 or score_total <= 0:
            break
        floating_score_total = sum(scores[i] for i in floating_ids)
        if floating_score_total <= 0:
            break
        newly_fixed = []
        pool_this_pass = remaining_pool
        shares = {i: pool_this_pass * (scores[i] / floating_score_total) for i in floating_ids}
        for i in floating_ids:
            cap = demand_by_id[i].effort
            if shares[i] > cap + 1e-9:
                fixed[i] = round(cap, 6)
                remaining_pool = round(remaining_pool - fixed[i], 6)
                newly_fixed.append(i)
        if not newly_fixed:
            for i in floating_ids:
                fixed[i] = round(shares[i], 6)
            remaining_pool = 0.0
            floating_ids = []
            break
        floating_ids = [i for i in floating_ids if i not in newly_fixed]

    for d in demands:
        fixed.setdefault(d.spoke_id, 0.0)

    spoke_allocations = {
        d.spoke_id: {
            "allocated": fixed[d.spoke_id],
            "advisor_verdict": d.advisor_verdict,
            "score": round(scores[d.spoke_id], 6),
            "group_id": d.group_id,
        }
        for d in demands
    }

    by_group: Dict[str, float] = {}
    for d in demands:
        if d.group_id:
            by_group[d.group_id] = round(by_group.get(d.group_id, 0.0) + fixed[d.spoke_id], 6)

    allocated_total = round(sum(fixed.values()), 6)
    unallocated = round(allocatable - allocated_total, 6)

    result = {
        "schema": SCHEMA,
        "total_capacity": total_capacity,
        "reserved": reserved,
        "total_reserved": total_reserved,
        "allocatable": allocatable,
        "spokes": spoke_allocations,
        "by_group": by_group,
        "allocated_total": allocated_total,
        "unallocated": unallocated,
        "priority_order": list(PRIORITY_ORDER),
    }

    if windows:
        window_total = sum(w.get("capacity", 0.0) for w in windows) or 1.0
        result["windows"] = [
            {
                "window_id": w.get("window_id"),
                "capacity": w.get("capacity", 0.0),
                "share_of_allocated": {
                    sid: round(alloc["allocated"] * (w.get("capacity", 0.0) / window_total), 6)
                    for sid, alloc in spoke_allocations.items()
                },
            }
            for w in windows
        ]
    return result


# =============================================================================
# CLI — real-corpus wiring
# =============================================================================

def _spoke_paths(root: Path) -> Path:
    return root / "WAI-Harness" / "spoke" / "local"


def render_backlog(demand: ReadyBacklogDemand) -> str:
    lines = [
        "── Ready Backlog Demand Model",
        f"   count={demand.count}  total_effort={demand.total_effort}  "
        f"weighted_impact={demand.weighted_impact}",
        f"   blocked_effort={demand.blocked_effort}  forecast_confidence={demand.forecast_confidence}",
        f"   age: avg={demand.avg_age_days}d max={demand.max_age_days}d  "
        f"effort_variance={demand.effort_variance}",
        f"   model_requirements={demand.model_requirements}",
        f"   initiatives={len(demand.by_initiative)}",
    ]
    return "\n".join(lines)


def _main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="Bursar — capacity-allocation advisor (§18)")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("backlog", help="compute the ready-backlog demand model over a local lug corpus")
    b.add_argument("--root", default=".")
    b.add_argument("--json", action="store_true")

    args = p.parse_args(argv)
    root = Path(args.root).resolve()

    if args.cmd == "backlog":
        lugs_root = _spoke_paths(root) / "lugs"
        demand = compute_ready_backlog(lugs_root)
        out = {"schema": BACKLOG_SCHEMA, "generated_at": _now_iso(), **asdict(demand)}
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(render_backlog(demand))
        return 0
    return 1


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
