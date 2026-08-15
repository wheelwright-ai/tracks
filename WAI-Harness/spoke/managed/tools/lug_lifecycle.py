#!/usr/bin/env python3
"""Wheelwright v5 lug lifecycle engine — Phase 2 (lifecycle engine).

This module is built ALONGSIDE the v4 lug tooling and Phase-1's lug_v5.py.
Per docs/wheelwright-v5-control-plane-directive.md Part IV Doctrine 2
(strangler cutover — a mechanism is fully old or fully new, flipped by a
recorded transition receipt; no dual-read window, no silent fallback),
NOTHING in this module is wired into any v4 read/write path. It is proven
by its own tests only. No existing tool imports this module; no existing
lug is migrated or advanced on disk by it.

Phase 1 built the SHAPE (schemas/lug-v5.schema.json, tools/lug_v5.py).
Phase 2 builds the ENGINE that moves a v5 lug through that shape:

  - The legal-transition table lives ONLY in lug_v5.TRANSITIONS. This
    module never redefines it — it imports and calls
    lug_v5.can_transition() / lug_v5.apply_transition() for every state
    change. Two transition tables that can disagree is a bug waiting to
    happen (task brief); there is exactly one.
  - Every transition is durable and attributed (directive S28) — this is
    inherited for free from lug_v5.apply_transition(), which appends a
    {from, to, at, by, reason} record to lug["history"] and never mutates
    an existing record.
  - Rework (directive S34) is a distinct, named-cause path: REWORK_CAUSES
    enumerates the seven failure classes named in the directive, each
    routes through REWORK to a specific legal target state
    (REWORK_ROUTES), and each cycle is appended to lug["rework_log"] —
    append-only, like everything else here.
  - Retry/rework ceilings (directive S32/S41) are enforced locally and
    deterministically: once a lug's rework_log reaches `ceiling` entries,
    further rework attempts stop cycling and escalate to BLOCKED instead,
    recorded in lug["escalations"]. No unbounded loop is possible — BLOCKED
    is not a legal source state for REWORK in lug_v5.TRANSITIONS, so the
    engine cannot cycle a lug past its ceiling even if called forever.
  - Events (directive S29) are declared data on the lug
    (lug["events"][event_name] -> [descendant_id, ...]); the engine
    resolves which descendants to activate when an event fires. A
    COMPLETED (or any other) lug does not carry logic for how to activate
    its descendants — it only names them; `advance()` / `activate_event()`
    do the resolving, given a registry of {id: lug}.
  - No LLM call anywhere in this module (directive S40). Every function
    here is a pure, deterministic, in-memory dict transform: no disk I/O,
    no clock reads (callers supply `at`), no network calls. Safe to call
    thousands of times per second on a laptop.
"""
from __future__ import annotations

import copy
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import lug_v5  # noqa: E402  — the single source of truth for transition legality

# --------------------------------------------------------------------------
# Events (directive S29)
# --------------------------------------------------------------------------

# The subset of directive-S29 events that correspond directly to a lifecycle
# state change, and the state change that fires each one. Keyed by the
# *target* state of a transition (the exception is on_validation_fail,
# which additionally requires the transition to have originated at
# VALIDATING — see _event_for_transition()).
_EVENT_FOR_TARGET_STATE = {
    "READY_TO_BUILD": "on_ready_to_build",
    "READY_TO_TEST": "on_build_complete",
    "VALIDATING": "on_ready_to_test",
    "COMPLETE": "on_validation_pass",
}

# Directive S29 also names events with no single corresponding lifecycle
# transition (on_effort_variance, on_dependency_complete, on_schedule,
# on_provider_capacity_available) — these are fired explicitly via
# fire_event()/activate_event() by callers outside the plain state machine.
EVENT_NAMES = frozenset(
    {
        "on_ready_to_build",
        "on_build_complete",
        "on_ready_to_test",
        "on_validation_pass",
        "on_validation_fail",
        "on_effort_variance",
        "on_dependency_complete",
        "on_schedule",
        "on_provider_capacity_available",
    }
)


def _event_for_transition(from_state: str, to_state: str) -> str | None:
    """Return the S29 event name that fires for this transition, or None."""
    if from_state == "VALIDATING" and to_state == "REWORK":
        return "on_validation_fail"
    return _EVENT_FOR_TARGET_STATE.get(to_state)


def declared_event_targets(lug: dict, event_name: str) -> list[str]:
    """Return the descendant lug ids this lug declares under `event_name`.

    Pure read. A lug with no `events` field, or no entry for this event,
    declares no descendants — returns [].
    """
    events = lug.get("events") or {}
    targets = events.get(event_name) or []
    return list(targets)


def activate_event(
    registry: dict, source_lug_id: str, event_name: str, by: dict, at: str
) -> tuple[dict, list[str]]:
    """Resolve `event_name` fired by `registry[source_lug_id]` against the
    graph and activate eligible descendants.

    This is the mechanism behind directive S29's "a COMPLETED lug does not
    need to know how to activate its descendants — the Hub resolves the
    graph": the source lug only *names* its descendants
    (lug["events"][event_name]); this function decides HOW to activate them
    (CREATED -> READY_TO_REVIEW is the only state in which an un-started
    descendant is eligible for automatic activation; anything already in
    motion, blocked, or terminal is left untouched).

    Pure: returns a NEW registry dict (shallow copy at the top, with only
    activated entries replaced) and the list of descendant ids actually
    activated. Does not mutate the input registry or any lug in it.

    Unknown descendant ids (declared but not present in `registry`) are
    skipped, not errors — the graph may be partially materialized.
    """
    source = registry.get(source_lug_id)
    if source is None:
        raise KeyError(f"unknown source lug id: {source_lug_id!r}")

    new_registry = dict(registry)
    activated: list[str] = []
    for target_id in declared_event_targets(source, event_name):
        target = registry.get(target_id)
        if target is None:
            continue
        if target.get("state") != "CREATED":
            continue
        activated_lug = lug_v5.apply_transition(
            target,
            "READY_TO_REVIEW",
            by,
            at,
            reason=f"activated by {event_name} from {source_lug_id}",
        )
        new_registry[target_id] = activated_lug
        activated.append(target_id)
    return new_registry, activated


def advance(
    registry: dict, lug_id: str, to_state: str, by: dict, at: str, reason: str = ""
) -> tuple[dict, str | None, list[str]]:
    """The main engine entrypoint: transition `registry[lug_id]` to
    `to_state`, then resolve and fire whichever S29 event that transition
    corresponds to (if any), activating eligible descendants.

    Legality is decided ENTIRELY by lug_v5.can_transition()/apply_transition
    — this function does not duplicate or second-guess that table. Raises
    ValueError (propagated from lug_v5.apply_transition) on an illegal
    transition; the registry is untouched in that case.

    Returns (new_registry, fired_event_name_or_None, activated_descendant_ids).
    Pure: does not mutate the input registry or any lug in it.
    """
    lug = registry[lug_id]  # KeyError is the correct failure for an unknown id
    from_state = lug.get("state")
    new_lug = lug_v5.apply_transition(lug, to_state, by, at, reason=reason)

    new_registry = dict(registry)
    new_registry[lug_id] = new_lug

    event_name = _event_for_transition(from_state, to_state)
    activated: list[str] = []
    if event_name is not None:
        new_registry, activated = activate_event(new_registry, lug_id, event_name, by, at)

    return new_registry, event_name, activated


def fire_event(
    registry: dict, source_lug_id: str, event_name: str, by: dict, at: str
) -> tuple[dict, list[str]]:
    """Explicitly fire an S29 event that has no single corresponding
    lifecycle transition (on_effort_variance, on_dependency_complete,
    on_schedule, on_provider_capacity_available). Thin, validated wrapper
    around activate_event() for callers outside the state machine.
    """
    if event_name not in EVENT_NAMES:
        raise ValueError(f"unknown event: {event_name!r} (known: {sorted(EVENT_NAMES)})")
    return activate_event(registry, source_lug_id, event_name, by, at)


# --------------------------------------------------------------------------
# Rework (directive S34) with hard retry/rework ceilings (directive S32/S41)
# --------------------------------------------------------------------------

# The seven failure classes directive S34 requires the system to
# distinguish. A rework that does not name one of these teaches nothing
# (task brief) — enter_rework() rejects any other cause.
REWORK_CAUSES = frozenset(
    {
        "implementation_defect",
        "bad_direction",
        "insufficient_acceptance_criteria",
        "incorrect_forecast",
        "missing_setup",
        "insufficient_model_profile",
        "environment_deficiency",
    }
)

# Where REWORK routes back to, by cause (directive S34: "rework returns
# through the appropriate path" — not always the same path). Every target
# here is a legal destination from REWORK per lug_v5.TRANSITIONS["REWORK"].
REWORK_ROUTES: dict[str, str] = {
    # The spec/build-readiness was fine; the build itself was wrong.
    # Redo the build, no need to re-review direction.
    "implementation_defect": "READY_TO_BUILD",
    # The parent's intent was wrong or unclear — needs re-specification.
    "bad_direction": "READY_TO_REVIEW",
    # The spec was incomplete — acceptance criteria must be redefined.
    "insufficient_acceptance_criteria": "READY_TO_REVIEW",
    # Direction and criteria were right; the effort/impact estimate was
    # wrong — re-review, not re-specify from scratch.
    "incorrect_forecast": "IMPLEMENTATION_REVIEW",
    # Spec and profile were fine; a fixture/dependency/setup was missing.
    "missing_setup": "READY_TO_BUILD",
    # The requested model profile (directive S8) was insufficient — needs
    # a new profile before rebuilding.
    "insufficient_model_profile": "READY_TO_BUILD",
    # Tooling/environment failure unrelated to spec or model choice.
    "environment_deficiency": "READY_TO_BUILD",
}

assert REWORK_CAUSES == frozenset(REWORK_ROUTES)  # every cause routes somewhere

# directive S41: "retry and validation-loop maxima ... repeated-failure
# circuit breaker ... no unbounded recursive work loops". This is the
# default hard ceiling; callers may pass a tighter one per lug/policy.
DEFAULT_REWORK_CEILING = 3


def enter_rework(
    lug: dict,
    cause: str,
    evidence,
    reason: str,
    owner: str,
    by: dict,
    at: str,
    estimated_additional_effort=None,
    revised_effort=None,
    downstream_consequences=None,
    ceiling: int = DEFAULT_REWORK_CEILING,
) -> dict:
    """Return a NEW lug dict describing one rework cycle (directive S34),
    subject to a hard rework ceiling (directive S32/S41).

    Normal path (rework_log has fewer than `ceiling` entries):
      1. transition current_state -> REWORK (durable, attributed, via
         lug_v5.apply_transition — raises ValueError if that hop is illegal
         from the lug's current state)
      2. append a durable rework record to lug["rework_log"] naming cause,
         evidence, reason, originating lug, owner, estimated additional
         effort, revised effort, downstream consequences, and which state
         it is being routed back to
      3. transition REWORK -> REWORK_ROUTES[cause] (durable, attributed)

    Ceiling path (rework_log already has >= `ceiling` entries): the engine
    STOPS cycling and ESCALATES instead of returning to REWORK — it
    transitions to BLOCKED (or, if already BLOCKED from a prior escalation,
    leaves state untouched) and appends a durable escalation record to
    lug["escalations"]. Because BLOCKED is not a legal source state for
    REWORK in lug_v5.TRANSITIONS, no amount of further enter_rework() calls
    can move an escalated lug back into the rework loop — the ceiling is
    enforced by the transition table itself, not merely by a counter this
    function promises to check.

    Pure: does not mutate the input `lug`. Raises ValueError for an unknown
    cause, or if the underlying transition(s) are illegal from the lug's
    current state (only possible on the non-ceiling path, since BLOCKED is
    always a legal target from any non-terminal state).
    """
    if cause not in REWORK_CAUSES:
        raise ValueError(f"unknown rework cause: {cause!r} (known: {sorted(REWORK_CAUSES)})")

    rework_log = list(lug.get("rework_log", []))
    cycle_count = len(rework_log)

    if cycle_count >= ceiling:
        if lug.get("state") == "BLOCKED":
            new_lug = copy.deepcopy(lug)
        else:
            new_lug = lug_v5.apply_transition(
                lug,
                "BLOCKED",
                by,
                at,
                reason=(
                    f"rework ceiling ({ceiling}) exceeded after {cycle_count} cycle(s) — "
                    f"escalating instead of cycling further; latest cause={cause}"
                ),
            )
            new_lug = copy.deepcopy(new_lug)
        new_lug.setdefault("escalations", [])
        new_lug["escalations"] = list(new_lug["escalations"]) + [
            {
                "at": at,
                "by": dict(by),
                "cause": cause,
                "reason": reason,
                "evidence": evidence,
                "cycle_count": cycle_count,
                "ceiling": ceiling,
            }
        ]
        return new_lug

    target_state = REWORK_ROUTES[cause]
    staged = lug_v5.apply_transition(lug, "REWORK", by, at, reason=f"rework: {cause}")
    staged = copy.deepcopy(staged)
    record = {
        "cause": cause,
        "evidence": evidence,
        "reason": reason,
        "originating_lug": lug.get("id"),
        "owner": owner,
        "estimated_additional_effort": estimated_additional_effort,
        "revised_effort": revised_effort,
        "downstream_consequences": downstream_consequences or [],
        "at": at,
        "by": dict(by),
        "routed_to": target_state,
        "cycle_number": cycle_count + 1,
    }
    staged.setdefault("rework_log", [])
    staged["rework_log"] = list(staged["rework_log"]) + [record]

    routed = lug_v5.apply_transition(staged, target_state, by, at, reason=f"rework routed: {cause}")
    return routed


def rework_cycle_count(lug: dict) -> int:
    """Number of completed rework cycles recorded on this lug. Pure read."""
    return len(lug.get("rework_log", []))


def is_escalated(lug: dict) -> bool:
    """True once a lug has hit its rework ceiling and stopped cycling."""
    return bool(lug.get("escalations"))
