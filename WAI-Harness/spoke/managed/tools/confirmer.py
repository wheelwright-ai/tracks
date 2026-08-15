#!/usr/bin/env python3
"""Wheelwright v5 Implementation Reviewer / Confirmer — Phase 3 (review).

This module is built ALONGSIDE the v4 lug tooling and the Phase-1/Phase-2 v5
tools (lug_v5.py, lug_lifecycle.py). Per docs/wheelwright-v5-control-plane-
directive.md Part IV Doctrine 2 (strangler cutover — a mechanism is fully old
or fully new, flipped by a recorded transition receipt; no dual-read window,
no silent fallback), NOTHING in this module is wired into any v4 read/write
path. It is proven by its own tests only. No existing tool imports this
module; no existing lug is advanced on disk by it.

Phase 1 built the SHAPE. Phase 2 built the ENGINE that moves a v5 lug through
that shape. Phase 3 builds the REVIEW that stands between a lug being
written and a lug being built (directive §9, §27, Ruling 6):

    Implementation-side contract: does this proposed implementation
    correctly express what the parent intended?
    (Distinct from verification: did the resulting implementation actually
    satisfy what was intended? — that is a separate, later-phase concern.)

Design constraints this module is held to (directive §40, task brief):

  - No LLM call per state change. This runs on every READY_TO_REVIEW lug, so
    every check that CAN be made deterministic IS deterministic: schema
    validity, presence of a drafted effort forecast, existence of every
    declared dependency (when a registry is supplied), completeness of the
    nine required model_profile fields, non-emptiness of descendant_prompt
    when the lug declares children, presence of a verify block.
  - Where genuine judgement is unavoidable (goal alignment, scope drift,
    missing edge cases, implementation traps, descendant-prompt quality,
    model-profile *suitability* as opposed to completeness, verify-block
    *executability* as opposed to presence), this module does NOT pretend a
    heuristic is judgement. It runs a narrow, named signal and — if that
    signal fires — emits a FLAGGED FINDING for a human or a model to resolve.
    A flagged finding is advisory: it can push the outcome to RECOMMEND, it
    never manufactures a fabricated APPROVE or RETURN on its own authority.
  - Exactly three outcomes (directive §9): APPROVE (the transition to
    READY_TO_BUILD), RETURN (rework, with a named directive-§34 cause), or
    RECOMMEND (non-blocking findings attached; the lug's state does not
    change — there is no legal "approved with comments" state in
    lug_v5.TRANSITIONS, so RECOMMEND simply does not move the lug forward or
    backward until the findings are addressed or someone with standing
    overrides them).
  - It MUST NOT silently rewrite the lug (directive §9). review() is a pure
    read-only evaluation; confirm() performs only the state transitions
    lug_v5.apply_transition()/lug_lifecycle.enter_rework() already allow, and
    every function here returns a NEW dict — the input lug is never mutated.
  - Its review is attributed and durable, appended to the lug's history like
    any other transition (directive §9, §28) — via a new append-only
    `confirmer_reviews` list on the lug (parallel in spirit to
    lug_lifecycle's `rework_log`/`escalations`; both are additionalProperties
    the base schema already permits).
"""
from __future__ import annotations

import copy
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import lug_v5  # noqa: E402 — schema validation + the single transition table
import lug_lifecycle  # noqa: E402 — enter_rework() for the RETURN outcome

# --------------------------------------------------------------------------
# Outcomes (directive §9 — exactly three)
# --------------------------------------------------------------------------

OUTCOMES = frozenset({"APPROVE", "RETURN", "RECOMMEND"})

# States review() is willing to evaluate. A lug arrives at READY_TO_REVIEW
# from Planner; confirm() enters IMPLEMENTATION_REVIEW on its behalf if it
# is not there already (directive §9's "READY_TO_REVIEW lug" framing, made
# to agree with lug_v5.TRANSITIONS which only allows the outcome-transitions
# FROM IMPLEMENTATION_REVIEW).
_REVIEWABLE_STATES = frozenset({"READY_TO_REVIEW", "IMPLEMENTATION_REVIEW"})

# --------------------------------------------------------------------------
# Deterministic checks -> directive-§34 rework cause, when a check is BOTH
# deterministic and blocking. Order matters: it is the priority order used
# to pick a single rework cause when more than one blocking check fails
# (enter_rework() takes exactly one cause; every failing check is still
# recorded in full in the review's `findings`, nothing is dropped).
# --------------------------------------------------------------------------

_CHECK_REWORK_CAUSE = {
    "schema_valid": "bad_direction",
    "directions_present": "bad_direction",
    "acceptance_criteria_present": "insufficient_acceptance_criteria",
    "effort_forecast_present": "incorrect_forecast",
    "effort_plausible": "incorrect_forecast",
    "dependencies_resolved": "missing_setup",
    "model_profile_complete": "insufficient_model_profile",
    "descendant_prompt_present_if_children": "bad_direction",
    "verify_present": "insufficient_acceptance_criteria",
}

# Priority order for picking the single rework cause when several blocking
# checks fail at once (first failure in this order wins the cause; every
# failure is still recorded). More specific checks are listed BEFORE
# schema_valid: a missing model_profile field, for instance, also makes the
# lug schema-invalid, but "insufficient_model_profile" names the actual
# problem far better than the catch-all "bad_direction" schema_valid maps
# to — schema_valid is the fallback for whatever the named checks below did
# not already explain, so it goes last.
_CHECK_PRIORITY = (
    "directions_present",
    "acceptance_criteria_present",
    "effort_forecast_present",
    "effort_plausible",
    "dependencies_resolved",
    "model_profile_complete",
    "descendant_prompt_present_if_children",
    "verify_present",
    "schema_valid",
)

REQUIRED_MODEL_PROFILE_FIELDS = (
    "class",
    "reasoning_requirement",
    "coding_capability",
    "tool_capability",
    "context_requirement",
    "latency_tolerance",
    "quality_floor",
    "effort_budget",
    "acceptable_fallback_class",
)

_LOW_POWER_CLASSES = frozenset({"haiku", "local"})

_VERIFY_EXECUTABLE_MARKERS = (
    "pytest", "python3", "python ", "./", "npm ", "npm run", "bash ", "sh ",
    ".py", "test_", "assert ", "cargo ", "go test", "make test",
    "make check", "make build", "node ", "jest", "vitest", "rspec",
    "curl ", "docker ",
)

_WORD_RE = re.compile(r"[a-z0-9]{4,}")


def _check(name: str, status: str, detail: str, blocking: bool) -> dict:
    return {"name": name, "status": status, "detail": detail, "blocking": blocking}


def _pass(name: str, detail: str, blocking: bool = True) -> dict:
    return _check(name, "pass", detail, blocking)


def _fail(name: str, detail: str, blocking: bool = True) -> dict:
    return _check(name, "fail", detail, blocking)


def _skip(name: str, detail: str) -> dict:
    return _check(name, "skip", detail, blocking=False)


def _flag(category: str, detail: str, requires: str = "human_or_model") -> dict:
    """A judgement-required finding. Never blocking on its own; it is a
    signal that a heuristic surfaced, not a verdict a heuristic reached."""
    return {"category": category, "detail": detail, "requires": requires}


# --------------------------------------------------------------------------
# Individual deterministic checks. Each takes (lug, registry) and returns a
# single check dict. Pure — no mutation, no I/O, no clock.
# --------------------------------------------------------------------------


def _check_schema_valid(lug: dict, registry) -> dict:
    result = lug_v5.validate_lug_v5(lug)
    if result["ok"]:
        return _pass("schema_valid", "lug validates against lug-v5.schema.json")
    return _fail(
        "schema_valid",
        "schema violations: " + "; ".join(result["failures"]),
    )


def _check_directions_present(lug: dict, registry) -> dict:
    directions = lug.get("directions")
    if isinstance(directions, str) and directions.strip():
        return _pass("directions_present", "directions is non-empty")
    return _fail("directions_present", "directions field is missing or empty")


def _check_acceptance_criteria_present(lug: dict, registry) -> dict:
    ac = lug.get("acceptance_criteria")
    if isinstance(ac, list) and len(ac) >= 1:
        return _pass(
            "acceptance_criteria_present", f"{len(ac)} acceptance_criteria entr(y/ies)"
        )
    return _fail(
        "acceptance_criteria_present",
        "acceptance_criteria is missing or empty — a build with nothing to "
        "check against cannot be confirmed",
    )


def _drafted_effort_record(lug: dict):
    return (lug.get("effort") or {}).get("drafted")


def _check_effort_forecast_present(lug: dict, registry) -> dict:
    drafted = _drafted_effort_record(lug)
    if not drafted:
        return _fail(
            "effort_forecast_present",
            "effort.drafted is absent — no forecast was ever recorded",
        )
    if drafted.get("value_unknown"):
        return _fail(
            "effort_forecast_present",
            "effort.drafted is explicitly value_unknown — no usable forecast",
        )
    return _pass("effort_forecast_present", f"effort.drafted={drafted.get('value')!r}")


def _check_effort_plausible(lug: dict, registry) -> dict:
    drafted = _drafted_effort_record(lug)
    if not drafted or drafted.get("value_unknown"):
        # already covered by effort_forecast_present; nothing new to say here
        return _skip("effort_plausible", "no usable forecast to assess plausibility of")
    value = drafted.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _fail(
            "effort_plausible", f"effort.drafted.value is not numeric: {value!r}"
        )
    if not (value > 0):
        return _fail(
            "effort_plausible", f"effort.drafted.value must be > 0, got {value!r}"
        )
    return _pass("effort_plausible", f"effort.drafted.value={value!r} is a plausible positive figure")


def _check_dependencies_resolved(lug: dict, registry) -> dict:
    blocked_by = (lug.get("relationships") or {}).get("blocked_by") or []
    if not blocked_by:
        return _pass("dependencies_resolved", "no declared dependencies")
    if registry is None:
        return _skip(
            "dependencies_resolved",
            f"{len(blocked_by)} dependency id(s) declared but no registry was "
            "supplied to confirm they exist",
        )
    missing = [dep for dep in blocked_by if dep not in registry]
    if missing:
        return _fail(
            "dependencies_resolved",
            f"declared dependency id(s) not found in registry: {missing}",
        )
    return _pass(
        "dependencies_resolved", f"all {len(blocked_by)} dependency id(s) exist in registry"
    )


def _check_model_profile_complete(lug: dict, registry) -> dict:
    profile = lug.get("model_profile")
    if not isinstance(profile, dict):
        return _fail(
            "model_profile_complete",
            "model_profile is absent — required before promotion to "
            "READY_TO_BUILD (directive S8)",
        )
    missing = [f for f in REQUIRED_MODEL_PROFILE_FIELDS if f not in profile]
    if missing:
        return _fail(
            "model_profile_complete",
            f"model_profile is missing required field(s): {missing}",
        )
    if not isinstance(profile.get("effort_budget"), (int, float)) or isinstance(
        profile.get("effort_budget"), bool
    ):
        return _fail(
            "model_profile_complete",
            f"model_profile.effort_budget must be numeric, got "
            f"{profile.get('effort_budget')!r}",
        )
    if not isinstance(profile.get("acceptable_fallback_class"), list):
        return _fail(
            "model_profile_complete",
            "model_profile.acceptable_fallback_class must be a list",
        )
    return _pass(
        "model_profile_complete",
        f"all {len(REQUIRED_MODEL_PROFILE_FIELDS)} required model_profile fields present",
    )


def _check_descendant_prompt_present_if_children(lug: dict, registry) -> dict:
    events = lug.get("events") or {}
    declares_children = any(bool(targets) for targets in events.values())
    if not declares_children:
        return _pass(
            "descendant_prompt_present_if_children",
            "lug declares no descendants — no descendant_prompt required",
        )
    dp = lug.get("descendant_prompt") or {}
    text = dp.get("text")
    if isinstance(text, str) and text.strip():
        return _pass(
            "descendant_prompt_present_if_children",
            "lug declares descendants and carries a non-empty descendant_prompt",
        )
    return _fail(
        "descendant_prompt_present_if_children",
        "lug declares descendant(s) via events but descendant_prompt is "
        "missing or empty — descendants would inherit nothing (directive S4)",
    )


def _verify_payload(lug: dict):
    evidence = lug.get("evidence") or {}
    for field in ("verify", "acceptance_evidence", "done_list"):
        if evidence.get(field):
            return field, evidence[field]
    return None, None


def _check_verify_present(lug: dict, registry) -> dict:
    field, payload = _verify_payload(lug)
    if field is None:
        return _fail(
            "verify_present",
            "no evidence.verify/acceptance_evidence/done_list found — "
            "nothing names how this lug's completion will be checked",
        )
    return _pass("verify_present", f"evidence.{field} is present")


_DETERMINISTIC_CHECKS = (
    _check_schema_valid,
    _check_directions_present,
    _check_acceptance_criteria_present,
    _check_effort_forecast_present,
    _check_effort_plausible,
    _check_dependencies_resolved,
    _check_model_profile_complete,
    _check_descendant_prompt_present_if_children,
    _check_verify_present,
)


# --------------------------------------------------------------------------
# Judgement-required signals (directive §40: flagged, never auto-decided).
# Each returns a flagged-finding dict, or None if its narrow signal did not
# fire. Pure — no mutation, no I/O, no clock, and critically NO LLM call:
# these are cheap lexical/structural signals whose only job is to decide
# whether a human or a model needs to look, not to reach the judgement
# themselves.
# --------------------------------------------------------------------------


def _words(text: str) -> set:
    return set(_WORD_RE.findall((text or "").lower()))


def _signal_goal_alignment(lug: dict) -> dict | None:
    lineage = lug.get("lineage") or {}
    inherited_goals = lineage.get("inherited_goals") or []
    initiative_id = lineage.get("initiative_id")
    if inherited_goals or initiative_id:
        return None
    return _flag(
        "goal_alignment",
        "no inherited_goals and no initiative_id on lineage — goal "
        "alignment cannot be traced from this record alone; needs a "
        "reviewer who knows the parent's intent",
    )


def _signal_scope_drift(lug: dict) -> dict | None:
    lineage = lug.get("lineage") or {}
    inherited_directions = lineage.get("inherited_directions") or []
    if not inherited_directions:
        return None
    inherited_words = set()
    for text in inherited_directions:
        inherited_words |= _words(text)
    if not inherited_words:
        return None
    own_words = _words(lug.get("directions", ""))
    if own_words & inherited_words:
        return None
    return _flag(
        "scope_drift",
        "no lexical overlap between this lug's directions and its "
        "lineage.inherited_directions — may have drifted from the parent's "
        "intent, or may simply be phrased differently; needs a reviewer to "
        "confirm which",
    )


def _signal_edge_case_coverage(lug: dict) -> dict | None:
    ac = lug.get("acceptance_criteria") or []
    if len(ac) >= 2:
        return None
    return _flag(
        "edge_case_coverage",
        f"only {len(ac)} acceptance_criteria entr(y/ies) — thin coverage is "
        "a common precursor to missed edge cases; needs a reviewer to "
        "confirm nothing is missing rather than merely unwritten",
    )


def _signal_implementation_traps(lug: dict) -> dict | None:
    directions = (lug.get("directions") or "").strip()
    if len(directions) >= 40:
        return None
    return _flag(
        "implementation_traps",
        f"directions is only {len(directions)} character(s) — short "
        "directions are where implementation traps (unstated constraints, "
        "unhandled negative paths) tend to hide; needs a reviewer read",
    )


def _signal_model_profile_suitability(lug: dict) -> dict | None:
    profile = lug.get("model_profile")
    if not isinstance(profile, dict):
        return None
    reasoning = profile.get("reasoning_requirement")
    quality_floor = profile.get("quality_floor")
    cls = profile.get("class")
    if reasoning == "high" and cls in _LOW_POWER_CLASSES:
        return _flag(
            "model_profile_suitability",
            f"reasoning_requirement=high but requested class={cls!r} — a "
            "low-power class rarely satisfies a high reasoning requirement; "
            "needs Alchemist/reviewer confirmation this is intentional",
        )
    if quality_floor == "critical" and cls in _LOW_POWER_CLASSES:
        return _flag(
            "model_profile_suitability",
            f"quality_floor=critical but requested class={cls!r} — needs "
            "confirmation the low-power class can actually meet a critical "
            "quality floor",
        )
    return None


def _signal_descendant_prompt_quality(lug: dict) -> dict | None:
    dp = lug.get("descendant_prompt")
    if not dp:
        return None
    text = (dp.get("text") or "").strip()
    if len(text) >= 15:
        return None
    return _flag(
        "descendant_prompt_quality",
        f"descendant_prompt.text is only {len(text)} character(s) — too "
        "short to plausibly carry real instruction to descendants; needs a "
        "reviewer to confirm it is not a placeholder",
    )


def _signal_verify_executability(lug: dict) -> dict | None:
    field, payload = _verify_payload(lug)
    if field is None:
        return None  # already a blocking finding via verify_present
    candidates = payload if isinstance(payload, list) else [payload]
    for item in candidates:
        haystack = item if isinstance(item, str) else str(item)
        haystack_lower = haystack.lower()
        if isinstance(item, dict) and ({"command", "script", "cmd"} & set(item)):
            return None
        if any(marker in haystack_lower for marker in _VERIFY_EXECUTABLE_MARKERS):
            return None
    return _flag(
        "verify_executability",
        f"evidence.{field} is present but does not obviously name an "
        "executable command (no recognized markers like pytest/python3/"
        "a script path) — may be prose-only; needs a reviewer to confirm "
        "it can actually be run (Ruling 20: a verify block that cannot "
        "execute cannot be reconciled)",
    )


_JUDGEMENT_SIGNALS = (
    _signal_goal_alignment,
    _signal_scope_drift,
    _signal_edge_case_coverage,
    _signal_implementation_traps,
    _signal_model_profile_suitability,
    _signal_descendant_prompt_quality,
    _signal_verify_executability,
)


# --------------------------------------------------------------------------
# review() — pure evaluation. Does not transition state, does not mutate
# the input lug, makes no LLM call.
# --------------------------------------------------------------------------


def review(lug: dict, at: str, by: dict, registry: dict | None = None) -> dict:
    """Evaluate `lug` (a READY_TO_REVIEW/IMPLEMENTATION_REVIEW v5 lug) and
    return a review report. Pure: reads `lug` and `registry`, never writes
    either; performs no state transition (that is confirm()'s job) and no
    LLM call (directive §40).

    `registry` is an optional {id: lug} map used only to check that declared
    dependencies (relationships.blocked_by) actually exist; when omitted,
    the dependency check degrades to a skip rather than a false pass/fail.

    Report shape:
      {
        "lug_id", "at", "by",
        "outcome": "APPROVE" | "RETURN" | "RECOMMEND",
        "checks": [ {name, status, detail, blocking}, ... ],   # deterministic
        "findings": [ ...blocking checks that failed... ],
        "flagged_findings": [ {category, detail, requires}, ... ],  # judgement
        "rework_cause": str | None,      # set iff outcome == RETURN
        "follow_up_suggestions": [str, ...],
        "reason": str,
      }
    """
    if lug.get("state") not in _REVIEWABLE_STATES:
        raise ValueError(
            f"confirmer.review() cannot evaluate a lug in state "
            f"{lug.get('state')!r} (reviewable states: {sorted(_REVIEWABLE_STATES)})"
        )

    checks = [fn(lug, registry) for fn in _DETERMINISTIC_CHECKS]
    findings = [c for c in checks if c["blocking"] and c["status"] == "fail"]

    flagged_findings = [
        finding
        for finding in (signal(lug) for signal in _JUDGEMENT_SIGNALS)
        if finding is not None
    ]

    follow_up_suggestions = []
    for finding in flagged_findings:
        follow_up_suggestions.append(
            f"consider a follow-up lug addressing {finding['category']}: {finding['detail']}"
        )

    if findings:
        outcome = "RETURN"
        rework_cause = None
        for name in _CHECK_PRIORITY:
            if any(f["name"] == name for f in findings):
                rework_cause = _CHECK_REWORK_CAUSE[name]
                break
        reason = (
            f"{len(findings)} blocking check(s) failed: "
            + "; ".join(f"{f['name']} — {f['detail']}" for f in findings)
        )
    elif flagged_findings:
        outcome = "RECOMMEND"
        rework_cause = None
        reason = (
            f"all deterministic checks pass; {len(flagged_findings)} "
            "judgement-required finding(s) attached for a human or a model "
            "to resolve: "
            + "; ".join(f"{f['category']} — {f['detail']}" for f in flagged_findings)
        )
    else:
        outcome = "APPROVE"
        rework_cause = None
        reason = "all deterministic checks pass; no judgement-required signals fired"

    return {
        "lug_id": lug.get("id"),
        "at": at,
        "by": dict(by),
        "outcome": outcome,
        "checks": checks,
        "findings": findings,
        "flagged_findings": flagged_findings,
        "rework_cause": rework_cause,
        "follow_up_suggestions": follow_up_suggestions,
        "reason": reason,
    }


# --------------------------------------------------------------------------
# confirm() — the only function in this module that changes lug state. It
# performs exactly the transition report["outcome"] calls for, using
# lug_v5.apply_transition / lug_lifecycle.enter_rework — never anything the
# transition table (lug_v5.TRANSITIONS) does not already allow, and never
# by editing directions/acceptance_criteria/effort/descendant_prompt content
# (directive §9: the Confirmer must not silently rewrite work).
# --------------------------------------------------------------------------


def _attach_review_record(lug: dict, report: dict) -> dict:
    """Return a NEW lug with `report` appended to the append-only
    `confirmer_reviews` list (directive §9/§28: attributed and durable,
    never edited or removed once written). Does not mutate `lug`."""
    new_lug = copy.deepcopy(lug)
    new_lug.setdefault("confirmer_reviews", [])
    new_lug["confirmer_reviews"] = list(new_lug["confirmer_reviews"]) + [
        copy.deepcopy(report)
    ]
    return new_lug


def confirm(
    lug: dict, by: dict, at: str, registry: dict | None = None
) -> dict:
    """Run review() and then apply exactly the transition its outcome
    licenses. Pure: never mutates the input `lug`; returns a NEW lug plus
    the review report.

    - READY_TO_REVIEW input is first advanced to IMPLEMENTATION_REVIEW
      (directive §9's framing of "a READY_TO_REVIEW lug", reconciled with
      lug_v5.TRANSITIONS which only licenses the outcome-transitions FROM
      IMPLEMENTATION_REVIEW) — this hop is definitional entry into review,
      not a content rewrite.
    - APPROVE  -> IMPLEMENTATION_REVIEW -> READY_TO_BUILD.
    - RETURN   -> routed through lug_lifecycle.enter_rework() using the
      report's rework_cause (directive §34); subject to the same rework
      ceiling as any other rework path (directive §32/§41) — enter_rework()
      itself decides ceiling-exceeded escalation to BLOCKED, this function
      does not special-case it.
    - RECOMMEND -> no state transition. There is no legal "approved with
      comments" state, so the lug is left exactly where review() found it
      (IMPLEMENTATION_REVIEW); only the durable review record is attached.

    Returns {"lug": <new lug dict>, "report": <review report dict>}.
    """
    entering = lug
    if lug.get("state") == "READY_TO_REVIEW":
        entering = lug_v5.apply_transition(
            lug, "IMPLEMENTATION_REVIEW", by, at, reason="entering implementation review"
        )

    report = review(entering, at, by, registry=registry)

    if report["outcome"] == "APPROVE":
        transitioned = lug_v5.apply_transition(
            entering, "READY_TO_BUILD", by, at, reason="confirmer: approved"
        )
    elif report["outcome"] == "RETURN":
        transitioned = lug_lifecycle.enter_rework(
            entering,
            cause=report["rework_cause"],
            evidence=report["findings"],
            reason=report["reason"],
            owner=by.get("model", "confirmer"),
            by=by,
            at=at,
        )
    else:  # RECOMMEND — no state change
        transitioned = copy.deepcopy(entering)

    new_lug = _attach_review_record(transitioned, report)
    return {"lug": new_lug, "report": report}


# --------------------------------------------------------------------------
# Follow-up lug construction (directive §9: "may create follow-ups"). Pure
# builder — never writes to disk, never auto-attaches itself to anything;
# the caller decides whether/where to persist it.
# --------------------------------------------------------------------------


def make_follow_up_lug(
    parent_lug: dict,
    follow_up_id: str,
    directions: str,
    by: dict,
    at: str,
    lug_type: str = "implementation",
) -> dict:
    """Build a new CREATED-state v5 lug stub addressing a Confirmer finding,
    lineage-linked to `parent_lug`. Pure: does not mutate `parent_lug`, does
    not write to disk, does not register itself anywhere — materializing and
    linking it into the graph is the caller's responsibility."""
    parent_lineage = parent_lug.get("lineage") or {}
    ancestors = list(parent_lineage.get("ancestors") or [])
    if parent_lug.get("id"):
        ancestors = ancestors + [parent_lug["id"]]
    return {
        "id": follow_up_id,
        "lug_type": lug_type,
        "state": "CREATED",
        "directions": directions,
        "attribution": {
            "created_by": by.get("model", "confirmer"),
            "created_at": at,
            "created_by_model": dict(by),
            "owner": by.get("model", "confirmer"),
            "last_modified_by": by.get("model", "confirmer"),
            "last_modified_at": at,
            "last_modified_by_model": dict(by),
        },
        "lineage": {
            "parent_id": parent_lug.get("id"),
            "ancestors": ancestors,
            "originating_spoke": parent_lineage.get("originating_spoke"),
            "originating_group": parent_lineage.get("originating_group"),
            "initiative_id": parent_lineage.get("initiative_id"),
        },
        "effort": lug_v5.unknown_value_triple(by, at, note="follow-up created by confirmer — effort not yet estimated"),
        "impact": lug_v5.unknown_value_triple(by, at, note="follow-up created by confirmer — impact not yet estimated"),
        "history": [],
    }


def main(argv):  # pragma: no cover - thin CLI wrapper
    import json

    if len(argv) >= 2 and argv[0] == "review":
        lug = json.load(open(argv[1]))
        by = {"model": "confirmer-cli", "provider": "local"}
        at = "1970-01-01T00:00:00+00:00"
        report = review(lug, at, by)
        print(json.dumps(report, indent=2, default=str))
        return 0 if report["outcome"] != "RETURN" else 1
    print("usage: confirmer.py review <lug.json>", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
