#!/usr/bin/env python3
"""Wheelwright v5 lug schema tooling — Phase 1 (architecture and schema).

This module is built ALONGSIDE the v4 lug tooling (validate_lug_v4.py). Per
docs/wheelwright-v5-control-plane-directive.md Part IV Doctrine 2 (strangler
cutover — a mechanism is fully old or fully new, flipped by a recorded
transition receipt; no dual-read window, no silent fallback), NOTHING in this
module is wired into any v4 read/write path. It is proven by its own tests
only. No existing tool imports this module; no existing lug is migrated to
disk by it.

Provides:
  - load_schema() / validate_lug_v5(lug) -> structural validation against
    schemas/lug-v5.schema.json
  - TRANSITIONS, can_transition(), apply_transition() -> the S7 lifecycle
    legal-transition table, enforced as a pure function (illegal transitions
    are rejectable without any LLM/disk/clock involvement)
  - set_value() -> append-only value-triple writer; structurally refuses to
    overwrite an occupied slot (S5)
  - migrate_v4_lug(dict) -> dict -> pure v4->v5 shape converter (S36/S37).
    Never touches disk, never reads the clock, never reads randomness; the
    caller supplies `now` and `migrated_by` explicitly so output is
    reproducible for identical inputs.
"""
from __future__ import annotations

import copy
import json
import os

try:
    import jsonschema
except ImportError:  # pragma: no cover - exercised only in environments without jsonschema
    jsonschema = None

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCHEMA_PATH = os.path.normpath(
    os.path.join(_HERE, "..", "schemas", "lug-v5.schema.json")
)

# --------------------------------------------------------------------------
# Schema load / validate
# --------------------------------------------------------------------------


def load_schema(schema_path: str = _SCHEMA_PATH) -> dict:
    """Load and return the v5 lug JSON Schema document."""
    with open(schema_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_lug_v5(lug: dict, schema: dict | None = None) -> dict:
    """Validate `lug` against the v5 schema.

    Returns {"ok": bool, "failures": [str, ...]}.
    """
    if jsonschema is None:  # pragma: no cover
        return {"ok": False, "failures": ["jsonschema package not available"]}
    if schema is None:
        schema = load_schema()
    validator_cls = jsonschema.Draft202012Validator
    validator = validator_cls(schema)
    failures = sorted(
        (f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}")
        for e in validator.iter_errors(lug)
    )
    return {"ok": not failures, "failures": failures}


# --------------------------------------------------------------------------
# Lifecycle transitions (directive S7)
# --------------------------------------------------------------------------

STATES = frozenset(
    {
        "CREATED",
        "READY_TO_REVIEW",
        "IMPLEMENTATION_REVIEW",
        "READY_TO_BUILD",
        "IN_BUILD",
        "READY_TO_TEST",
        "VALIDATING",
        "COMPLETE",
        "BLOCKED",
        "REWORK",
        "CANCELLED",
    }
)

# Legal-transition table. Keys are the FROM state; values are the set of
# legal TO states. This is the single source of truth for lifecycle legality
# — a pure lookup, no side effects, no I/O.
TRANSITIONS: dict[str, frozenset[str]] = {
    "CREATED": frozenset({"READY_TO_REVIEW", "BLOCKED", "CANCELLED"}),
    "READY_TO_REVIEW": frozenset(
        {"IMPLEMENTATION_REVIEW", "BLOCKED", "REWORK", "CANCELLED"}
    ),
    "IMPLEMENTATION_REVIEW": frozenset(
        {"READY_TO_BUILD", "REWORK", "BLOCKED", "CANCELLED"}
    ),
    "READY_TO_BUILD": frozenset({"IN_BUILD", "BLOCKED", "REWORK", "CANCELLED"}),
    "IN_BUILD": frozenset({"READY_TO_TEST", "BLOCKED", "REWORK", "CANCELLED"}),
    "READY_TO_TEST": frozenset({"VALIDATING", "BLOCKED", "REWORK", "CANCELLED"}),
    "VALIDATING": frozenset({"COMPLETE", "REWORK", "BLOCKED", "CANCELLED"}),
    "COMPLETE": frozenset(set()),  # terminal
    "BLOCKED": frozenset(
        {
            "CREATED",
            "READY_TO_REVIEW",
            "IMPLEMENTATION_REVIEW",
            "READY_TO_BUILD",
            "IN_BUILD",
            "READY_TO_TEST",
            "VALIDATING",
            "CANCELLED",
        }
    ),  # unblocks back to the state it was blocked from, or is cancelled
    "REWORK": frozenset(
        {"READY_TO_REVIEW", "IMPLEMENTATION_REVIEW", "READY_TO_BUILD", "CANCELLED"}
    ),
    "CANCELLED": frozenset(set()),  # terminal
}


def can_transition(from_state: str, to_state: str) -> bool:
    """Pure legality check. Unknown states are always illegal."""
    if from_state not in STATES or to_state not in STATES:
        return False
    return to_state in TRANSITIONS.get(from_state, frozenset())


def apply_transition(lug: dict, to_state: str, by: dict, at: str, reason: str = "") -> dict:
    """Return a NEW lug dict with the transition applied and appended to
    history. Raises ValueError on an illegal transition. Pure: does not
    mutate the input dict, does not read the clock (caller supplies `at`).

    `by` must be a {"model": ..., "provider": ...} attribution ref.
    """
    from_state = lug.get("state")
    if not can_transition(from_state, to_state):
        raise ValueError(
            f"illegal transition: {from_state!r} -> {to_state!r} "
            f"(legal targets from {from_state!r}: {sorted(TRANSITIONS.get(from_state, []))})"
        )
    new_lug = copy.deepcopy(lug)
    record = {"from": from_state, "to": to_state, "at": at, "by": dict(by)}
    if reason:
        record["reason"] = reason
    new_lug.setdefault("history", [])
    new_lug["history"] = list(new_lug["history"]) + [record]
    new_lug["state"] = to_state
    return new_lug


# --------------------------------------------------------------------------
# Value triples (directive S5) — append-only, overwrite-proof
# --------------------------------------------------------------------------

_VALUE_SLOTS = ("drafted", "ready", "actual")


def set_value(
    triple: dict,
    slot: str,
    value,
    recorded_by: dict,
    recorded_at: str,
    value_unknown: bool = False,
    note: str | None = None,
) -> dict:
    """Return a NEW value_triple dict with `slot` appended to history.

    Structurally refuses to overwrite an occupied slot: if `slot` already
    has an entry in triple["history"], raises ValueError rather than
    replacing it. This is the mechanism that makes overwriting impossible
    rather than merely discouraged — every caller in this codebase (and any
    future one) is forced through this function to get a v5-shaped value
    triple, and this function will not perform the overwrite.

    Pure: does not mutate `triple`, does not read the clock.
    """
    if slot not in _VALUE_SLOTS:
        raise ValueError(f"slot must be one of {_VALUE_SLOTS}, got {slot!r}")
    history = list((triple or {}).get("history", []))
    if any(rec.get("slot") == slot for rec in history):
        raise ValueError(
            f"value slot {slot!r} is already recorded — value triples are "
            "append-only (directive S5); earlier values are never overwritten"
        )
    record = {
        "slot": slot,
        "value": value,
        "recorded_at": recorded_at,
        "recorded_by": dict(recorded_by),
    }
    if value_unknown:
        record["value_unknown"] = True
    if note:
        record["note"] = note
    new_history = history + [record]
    new_triple = {"history": new_history}
    # derived projections: first (i.e. only, since append-only+one-per-slot)
    # record found for each slot
    for s in _VALUE_SLOTS:
        for rec in new_history:
            if rec.get("slot") == s:
                new_triple[s] = rec
                break
    return new_triple


def unknown_value_triple(recorded_by: dict, recorded_at: str, note: str | None = None) -> dict:
    """A value_triple with an explicit 'we do not know this value' drafted
    marker — never a fabricated zero (directive S37)."""
    return set_value(
        {"history": []},
        "drafted",
        None,
        recorded_by,
        recorded_at,
        value_unknown=True,
        note=note or "unknown at migration — v4 source carried no value",
    )


# --------------------------------------------------------------------------
# v4 -> v5 migration (directive S36/S37) — pure, in-memory only
# --------------------------------------------------------------------------

# v4 fields that map directly/verbatim onto v5 fields carried forward as-is.
_V4_RELATIONSHIP_FIELDS = (
    "blocked_by",
    "spec_id",
    "initiative_id",
    "source_spoke",
    "routed_to",
    "gt_convoy_hint",
    "execution_mode",
    "execution_substrate",
)


def migrate_v4_lug(v4_lug: dict, migrated_by: dict, migrated_at: str) -> dict:
    """Convert a v4 lug dict to v5 shape, purely in memory.

    Contract (directive S36/S37, and the Phase-1 task brief):
      - preserves id, timestamps, ownership, evidence, relationships, and the
        existing perceive/execute/verify content
      - maps v4 effort_score/effort/effort_drafted to the DRAFTED slot of the
        v5 effort value triple; ready and actual are left absent
      - never invents a value the v4 lug did not carry (impact/effort with no
        v4 source become an explicit value_unknown marker, not zero)
      - pure: same input always yields the same output; caller supplies
        `migrated_by` and `migrated_at` so no clock/disk/randomness is
        touched internally

    Does NOT write anything to disk. Does NOT mutate v4_lug.
    """
    if not isinstance(v4_lug, dict):
        raise TypeError("v4_lug must be a dict")

    v5 = {}

    # --- identity -----------------------------------------------------
    v5["id"] = v4_lug.get("id")
    v5["lug_type"] = "implementation" if v4_lug.get("type") in (None, "impl", "implementation") else v4_lug.get("type")
    if v4_lug.get("title") is not None:
        v5["title"] = v4_lug["title"]

    # --- directions (S2: perceive/execute prose -> DIRECTIONS) --------
    directions_parts = []
    for field in ("perceive", "execute"):
        v = v4_lug.get(field)
        if isinstance(v, list):
            directions_parts.extend(str(x) for x in v)
        elif isinstance(v, str) and v:
            directions_parts.append(v)
    v5["directions"] = "\n".join(directions_parts)

    if v4_lug.get("acceptance_criteria") is not None:
        v5["acceptance_criteria"] = v4_lug["acceptance_criteria"]

    # --- descendant_prompt (S4) ----------------------------------------
    dp = v4_lug.get("descendant_prompt")
    if dp:
        v5["descendant_prompt"] = {
            "text": dp,
            "set_at": v4_lug.get("created_at") or migrated_at,
            "set_by": (
                {"model": "unknown", "provider": "unknown"}
                if not v4_lug.get("created_by")
                else {"model": str(v4_lug["created_by"]), "provider": "unknown"}
            ),
        }

    # --- evidence (preserve verbatim — verify block + evidence-shaped fields)
    evidence = {}
    for field in ("verify", "evidence", "done_list", "acceptance_evidence"):
        if field in v4_lug:
            evidence[field] = v4_lug[field]
    if evidence:
        v5["evidence"] = evidence

    # --- relationships (preserve verbatim) -----------------------------
    relationships = {
        f: v4_lug[f] for f in _V4_RELATIONSHIP_FIELDS if f in v4_lug
    }
    if relationships:
        v5["relationships"] = relationships

    # --- lineage (S4) ----------------------------------------------------
    parent_id = v4_lug.get("parent_id") or v4_lug.get("parent") or None
    v5["lineage"] = {
        "parent_id": parent_id,
        "ancestors": list(v4_lug.get("ancestors", [])) if v4_lug.get("ancestors") else [],
        "originating_spoke": v4_lug.get("source_spoke"),
        "originating_group": v4_lug.get("source_group"),
        "initiative_id": v4_lug.get("initiative_id"),
    }

    # --- attribution (S28) — preserve what v4 carried, never fabricate --
    created_by = v4_lug.get("created_by")
    created_at = v4_lug.get("created_at")
    v5["attribution"] = {
        "created_by": created_by if created_by is not None else "unknown",
        "created_at": created_at if created_at is not None else "unknown",
        "created_by_model": {"model": "unknown", "provider": "unknown"},
        "owner": v4_lug.get("owner") or created_by or "unknown",
        "last_modified_by": v4_lug.get("_migrated_by") or created_by or "unknown",
        "last_modified_at": v4_lug.get("_migrated_at") or created_at or "unknown",
        "last_modified_by_model": {"model": "unknown", "provider": "unknown"},
    }

    # --- lifecycle state — map v4 status (dir-as-status) to v5 state ----
    v4_status = v4_lug.get("status")
    v5["state"] = _V4_STATUS_TO_V5_STATE.get(v4_status, "CREATED")
    v5["history"] = []

    # --- value triples: effort (S5/S6) -----------------------------------
    effort_drafted = v4_lug.get("effort_drafted", v4_lug.get("effort", v4_lug.get("effort_score")))
    if effort_drafted is not None:
        v5["effort"] = set_value(
            {"history": []},
            "drafted",
            effort_drafted,
            migrated_by,
            migrated_at,
            note="migrated from v4 effort/effort_drafted/effort_score",
        )
    else:
        v5["effort"] = unknown_value_triple(migrated_by, migrated_at, note="v4 lug carried no effort value")

    # --- value triples: impact (S5) ---------------------------------------
    impact_val = v4_lug.get("impact")
    if impact_val is not None:
        v5["impact"] = set_value(
            {"history": []},
            "drafted",
            impact_val,
            migrated_by,
            migrated_at,
            note="migrated from v4 impact",
        )
    else:
        v5["impact"] = unknown_value_triple(migrated_by, migrated_at, note="v4 lug carried no impact value")

    # --- model profile (S8) — v4 model_fit is a single hint, not a full
    # profile; do not fabricate a profile the v4 lug did not carry. -------
    model_fit = v4_lug.get("model_fit")
    if model_fit:
        v5.setdefault("legacy_model_hint", model_fit)  # informational, not a v5 model_profile

    # --- legacy provenance (S37) -------------------------------------------
    # v5 fields with no v4 equivalent at all: made explicit rather than
    # silently absent, never fabricated.
    unknown_fields = ["model_profile"]

    v5["legacy"] = {
        "migrated_from_schema": "v4",
        "migrated_from_id": v4_lug.get("id", "unknown"),
        "migration_note": "produced by lug_v5.migrate_v4_lug — in-memory only, not written to disk",
        "unknown_fields": unknown_fields,
    }

    return v5


_V4_STATUS_TO_V5_STATE = {
    "open": "READY_TO_REVIEW",
    "draft": "CREATED",
    "in_progress": "IN_BUILD",
    "completed": "COMPLETE",
    "deferred": "BLOCKED",
    "needs_attention": "BLOCKED",
    "cancelled": "CANCELLED",
}


def main(argv):  # pragma: no cover - thin CLI wrapper
    if not argv:
        print("usage: lug_v5.py validate <lug.json>", file=__import__("sys").stderr)
        return 2
    if argv[0] == "validate" and len(argv) > 1:
        lug = json.load(open(argv[1]))
        result = validate_lug_v5(lug)
        if result["ok"]:
            print(f"OK — valid v5 lug: {argv[1]}")
            return 0
        print(f"FAIL — v5 schema NOT satisfied ({len(result['failures'])} issue(s)):")
        for f in result["failures"]:
            print(f"  - {f}")
        return 1
    print("usage: lug_v5.py validate <lug.json>")
    return 2


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main(sys.argv[1:]))
