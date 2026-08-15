#!/usr/bin/env python3
"""spoke_advisor.py — the Spoke Advisor role (directive §17, contract "SpokeAdvisor").

ONE JOB, deliberately narrow: given a spoke's own visible state (goals, backlog,
capacity, burn, forecast, endorsement, completion history), decide whether its
resource *need* is justified. It does NOT allocate anything — allocation across
the Wheel is the Bursar's job (directive §18; see bursar.py). This module never
imports bursar.py and never writes a capacity number anywhere; it only produces a
verdict + evidence + a recommendation that MAY be enablement work instead of more
capacity. That "may recommend enablement instead of capacity" clause (§17) is the
entire reason this role exists apart from Ozi (which just spends what it's given)
and apart from the Bursar (which decides how much every spoke gets): a spoke that
is asking for capacity because it is performing badly should get advice, not fuel.

Determinism (§40): evaluate() is pure arithmetic over the SpokeSnapshot fields.
No LLM call, no randomness, no wall-clock-dependent branching. Same snapshot in
-> same verdict out, always.

Verdicts (exactly four, per the SpokeAdvisor contract):
    ON_TARGET       — performing within its allocation; no change recommended.
    NEEDS_CAPACITY  — performing well AND capacity-constrained; recommend more.
    OFF_TARGET      — performing poorly; recommend enablement, NOT more capacity.
    INVESTIGATE     — genuinely insufficient evidence to call it either way.
                       Reserved for real ambiguity (contract success_conditions);
                       must never be used to dodge a hard ON_TARGET/OFF_TARGET call.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "spoke-advisor-v1"

VERDICTS = ("ON_TARGET", "NEEDS_CAPACITY", "OFF_TARGET", "INVESTIGATE")

# Endorsement lifecycle states, directive §19. Not owned by this module (that is a
# separate endorsement engine) — we only read the state as one evidence input.
ENDORSEMENT_STATES = (
    "PROPOSED", "ONBOARDING", "ENDORSEMENT_PENDING", "ACTIVE", "TRUSTED",
    "DEGRADED", "REVIEW",
)
_ENDORSEMENT_MODIFIER = {
    "TRUSTED": 1.0, "ACTIVE": 0.9,
    "ENDORSEMENT_PENDING": 0.6, "ONBOARDING": 0.6, "PROPOSED": 0.55,
    "DEGRADED": 0.2, "REVIEW": 0.15,
}

# Thresholds — named constants so the decision boundary is auditable, not buried
# in an expression. Tune here only; evaluate() must stay a pure read of these.
_PERFORMANCE_OFF_TARGET = 0.45     # below this: OFF_TARGET regardless of utilization
_PERFORMANCE_GOOD = 0.60           # at/above this: eligible for NEEDS_CAPACITY
_UTILIZATION_CONSTRAINED = 0.85    # at/above this: genuinely capacity-bound
_MIN_EVIDENCE_FIELDS = 2           # below this many known signals -> INVESTIGATE


@dataclass
class SpokeSnapshot:
    """Everything the Spoke Advisor is allowed to look at — the spoke's own
    visible state (directive §16). No wheel-level capacity contention here;
    that escalates to Bursar/Analyst per the contract's `escalation` clause.
    """
    spoke_id: str
    goals_declared: bool = False
    goal_alignment: Optional[float] = None       # 0..1, evidence the spoke is working its goals
    ready_count: int = 0
    ready_effort: float = 0.0
    blocked_effort: float = 0.0
    capacity_allocated: Optional[float] = None    # current allotment (units match effort)
    capacity_used: Optional[float] = None
    burn_ratio: Optional[float] = None            # spend / budget, 1.0 == on-budget edge
    forecast_confidence: Optional[float] = None    # 0..1, from the ready-backlog demand model
    variance: Optional[float] = None               # forecast-vs-actual effort variance, lower=better
    endorsement_state: Optional[str] = None
    completion_rate: Optional[float] = None        # 0..1, recent window: completed / (completed+abandoned)


@dataclass
class Verdict:
    spoke_id: str
    verdict: str
    performance_score: Optional[float]
    utilization: Optional[float]
    evidence: List[str] = field(default_factory=list)
    gap: Optional[str] = None                  # required on NEEDS_CAPACITY (contract success_conditions)
    recommendation: str = ""                    # may be enablement work, per §17
    recommend_capacity_change: bool = False      # advisory only — Bursar decides (§18)


def _utilization(snap: SpokeSnapshot) -> Optional[float]:
    if not snap.capacity_allocated or snap.capacity_allocated <= 0:
        return None
    if snap.capacity_used is None:
        return None
    return round(snap.capacity_used / snap.capacity_allocated, 4)


def _performance_score(snap: SpokeSnapshot) -> Optional[float]:
    """Composite 0..1. Every component that is unknown is simply omitted from
    the average rather than defaulted — an unmeasured spoke must not silently
    read as mediocre; it reads as evidence-thin, which routes to INVESTIGATE.
    """
    parts: List[float] = []
    if snap.completion_rate is not None:
        parts.append(max(0.0, min(1.0, snap.completion_rate)))
    if snap.variance is not None:
        # variance is unbounded-above effort-units; fold into 0..1 via a soft cap.
        parts.append(max(0.0, 1.0 - min(1.0, snap.variance / 10.0)))
    if snap.burn_ratio is not None:
        # 1.0 = exactly on budget. Under budget is fine (no penalty); over budget
        # degrades linearly and caps at 0 by 2x burn.
        parts.append(max(0.0, 1.0 - max(0.0, snap.burn_ratio - 1.0)))
    if snap.endorsement_state:
        parts.append(_ENDORSEMENT_MODIFIER.get(snap.endorsement_state, 0.5))
    if snap.goal_alignment is not None:
        parts.append(max(0.0, min(1.0, snap.goal_alignment)))
    if not parts:
        return None
    return round(sum(parts) / len(parts), 4)


def _evidence_count(snap: SpokeSnapshot) -> int:
    fields = (snap.goal_alignment, snap.capacity_allocated, snap.capacity_used,
              snap.burn_ratio, snap.forecast_confidence, snap.variance,
              snap.endorsement_state, snap.completion_rate)
    return sum(1 for f in fields if f is not None) + (1 if snap.goals_declared else 0)


def evaluate(snap: SpokeSnapshot) -> Verdict:
    """Pure function: SpokeSnapshot -> Verdict. No I/O, no LLM, deterministic."""
    utilization = _utilization(snap)
    perf = _performance_score(snap)
    evidence: List[str] = []

    if snap.goals_declared:
        evidence.append("goals_declared=true")
    else:
        evidence.append("goals_declared=false")
    if snap.ready_count or snap.ready_effort:
        evidence.append(f"ready_backlog(count={snap.ready_count}, effort={snap.ready_effort})")
    if snap.blocked_effort:
        evidence.append(f"blocked_effort={snap.blocked_effort}")
    if utilization is not None:
        evidence.append(f"utilization={utilization}")
    if perf is not None:
        evidence.append(f"performance_score={perf}")
    if snap.forecast_confidence is not None:
        evidence.append(f"forecast_confidence={snap.forecast_confidence}")
    if snap.endorsement_state:
        evidence.append(f"endorsement_state={snap.endorsement_state}")

    # INVESTIGATE — genuine ambiguity ONLY: too little evidence to call it, or a
    # performance score that lands exactly on the boundary between OFF_TARGET and
    # NEEDS_CAPACITY-eligible while the data backing it is itself thin. This must
    # stay narrow — the contract forbids using INVESTIGATE to avoid a hard call.
    thin_evidence = _evidence_count(snap) < _MIN_EVIDENCE_FIELDS
    if thin_evidence:
        return Verdict(
            spoke_id=snap.spoke_id, verdict="INVESTIGATE",
            performance_score=perf, utilization=utilization, evidence=evidence,
            gap=None,
            recommendation=("Insufficient recorded evidence (goals/backlog/capacity/burn/"
                             "forecast) to issue a verdict — instrument the spoke before "
                             "either capacity or enablement work is justified."),
        )

    boundary_ambiguous = (
        perf is not None
        and (_PERFORMANCE_OFF_TARGET <= perf < _PERFORMANCE_GOOD)
        and (snap.forecast_confidence is None or snap.forecast_confidence < 0.4)
    )
    if boundary_ambiguous:
        return Verdict(
            spoke_id=snap.spoke_id, verdict="INVESTIGATE",
            performance_score=perf, utilization=utilization, evidence=evidence,
            gap=None,
            recommendation=(f"performance_score={perf} sits in the ambiguous band and "
                             f"forecast_confidence={snap.forecast_confidence} is too low to "
                             "trust the call — re-evaluate once more forecast data lands."),
        )

    # OFF_TARGET — poor performance. §17 is explicit: this spoke does NOT
    # automatically receive more resources, even if it is also capacity-starved.
    if perf is not None and perf < _PERFORMANCE_OFF_TARGET:
        return Verdict(
            spoke_id=snap.spoke_id, verdict="OFF_TARGET",
            performance_score=perf, utilization=utilization, evidence=evidence,
            gap=f"performance_score={perf} below floor {_PERFORMANCE_OFF_TARGET}",
            recommendation=("Enablement work, not capacity: address the weakest measured "
                             "input (completion_rate/variance/burn_discipline/endorsement) "
                             "before any capacity increase is considered."),
            recommend_capacity_change=False,
        )

    # NEEDS_CAPACITY — good performance AND genuinely capacity-bound.
    if (perf is not None and perf >= _PERFORMANCE_GOOD
            and utilization is not None and utilization >= _UTILIZATION_CONSTRAINED):
        gap_effort = round(max(snap.blocked_effort, snap.ready_effort - (snap.capacity_allocated or 0)), 4)
        return Verdict(
            spoke_id=snap.spoke_id, verdict="NEEDS_CAPACITY",
            performance_score=perf, utilization=utilization, evidence=evidence,
            gap=(f"utilization={utilization} >= {_UTILIZATION_CONSTRAINED} floor; "
                 f"blocked_effort={snap.blocked_effort}; capacity-attributable gap ~{gap_effort}"),
            recommendation="Recommend Bursar increase this spoke's allotment on the next cycle.",
            recommend_capacity_change=True,
        )

    # ON_TARGET — everything else: adequate performance, not capacity-bound.
    return Verdict(
        spoke_id=snap.spoke_id, verdict="ON_TARGET",
        performance_score=perf, utilization=utilization, evidence=evidence,
        gap=None,
        recommendation="No change recommended.",
        recommend_capacity_change=False,
    )


# ---------------------------------------------------------------------------
# CLI — reads a snapshot JSON (or a directory of snapshots) and prints verdicts.
# Building the snapshot from live corpus state is deliberately left to callers
# (e.g. bursar.py's demand model or a future Ozi report) rather than duplicated
# here, keeping this module's only job "evaluate a snapshot".
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_snapshot(d: Dict[str, Any]) -> SpokeSnapshot:
    known = set(SpokeSnapshot.__dataclass_fields__.keys())
    return SpokeSnapshot(**{k: v for k, v in d.items() if k in known})


def render(v: Verdict) -> str:
    lines = [f"── Spoke Advisor: {v.spoke_id} → {v.verdict}"]
    if v.performance_score is not None:
        lines.append(f"   performance_score={v.performance_score}  utilization={v.utilization}")
    for e in v.evidence:
        lines.append(f"   · {e}")
    if v.gap:
        lines.append(f"   gap: {v.gap}")
    lines.append(f"   → {v.recommendation}")
    return "\n".join(lines)


def _main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(description="Spoke Advisor — evaluate one spoke's resource need")
    p.add_argument("--snapshot", required=True, help="path to a spoke-snapshot JSON file")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    raw = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    snap = _load_snapshot(raw)
    verdict = evaluate(snap)
    out = {"schema": SCHEMA, "generated_at": _now_iso(), **asdict(verdict)}
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(render(verdict))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
