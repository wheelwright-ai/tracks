#!/usr/bin/env python3
"""Wheelwright v5 verification objects — Phase 4 (verification architecture).

This module is built ALONGSIDE the v4 prose-verify-block-on-a-lug convention.
Per docs/wheelwright-v5-control-plane-directive.md Part IV Doctrine 2
(strangler cutover — a mechanism is fully old or fully new, flipped by a
recorded transition receipt; no dual-read window, no silent fallback),
NOTHING in this module is wired into any v4 read/write path. It is proven by
its own tests only. No existing tool imports this module; no existing lug is
migrated to disk by it (migrate_v4_verify is pure, in-memory only).

Measured baseline motivating this phase: 366 lugs on this wheel carry
prose-only verify blocks no machine can execute (directive S10-S15). Today a
"verify" is prose owned by the implementation lug it lives inside. This
module makes verification an independent object class:

  - verification        (S10/S11/S12) — independently addressable, references
                          the work it covers, carries a maintenance schedule
  - validation_setup     (S13) — reusable seed data / fixtures / environment
  - execution_result     (S14) — an attributable child result of actually
                          running a verification

THE HONESTY RULE (Phase-4 mandate, directive Doctrine 1 "admission by
evidence, not declaration"): a prose-only v4 verify block does not become an
executable oracle just because it was moved into this schema. migrate_v4_verify
marks such records executability=UNEXECUTABLE, with an explicit
unexecutable_reason, and NEVER invents commands from prose. compute_coverage
only counts EXECUTABLE verifications toward a target's coverage — an
UNEXECUTABLE verification can reference a lug without making it "covered".
This is enforced here, not left to convention, because the failure mode this
phase exists to prevent is exactly "prose got laundered into evidence".

Provides:
  - load_schema() / validate_verification_object(obj) -> structural
    validation against schemas/verification-v5.schema.json (oneOf across the
    three object kinds)
  - SCHEDULE_KINDS, SCHEDULE_TRIGGERS -> directive S12 schedule vocabulary
  - compute_coverage() / find_uncovered() / find_weakly_covered() /
    find_redundantly_covered() -> directive S11 coverage queries
  - migrate_v4_verify(lug_dict) -> verification_object -> pure v4 verify ->
    v5 verification lifter (S36/S37 + the honesty rule above)
  - apply_retention() -> pure directive S15 retention policy application
    over a list of execution_result records
"""
from __future__ import annotations

import copy
import json
import os
import re
from datetime import datetime, timezone

try:
    import jsonschema
except ImportError:  # pragma: no cover - exercised only in environments without jsonschema
    jsonschema = None

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCHEMA_PATH = os.path.normpath(
    os.path.join(_HERE, "..", "schemas", "verification-v5.schema.json")
)

# --------------------------------------------------------------------------
# Schema load / validate
# --------------------------------------------------------------------------


def load_schema(schema_path: str = _SCHEMA_PATH) -> dict:
    """Load and return the v5 verification-object JSON Schema document."""
    with open(schema_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate_verification_object(obj: dict, schema: dict | None = None) -> dict:
    """Validate `obj` (a verification | validation_setup | execution_result
    dict) against the v5 verification schema.

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
        for e in validator.iter_errors(obj)
    )
    return {"ok": not failures, "failures": failures}


def _validate_conditional_rules(obj: dict) -> list[str]:
    """Conditional rules the schema itself cannot express (analogous to
    lug_v5's lifecycle-legality-depends-on-current-value gap):

      - a `verification` with executability=UNEXECUTABLE MUST carry
        unexecutable_reason and MUST NOT carry `oracle`.
      - a `verification` with executability=EXECUTABLE MUST carry `oracle`.
      - an `execution_result` whose verification was UNEXECUTABLE can only
        legally record result=UNEXECUTABLE (checked by the caller passing
        the parent verification via validate_execution_against_verification).

    Returns a list of human-readable failure strings (empty = ok).
    """
    failures = []
    if obj.get("object_type") == "verification":
        executability = obj.get("executability")
        if executability == "UNEXECUTABLE":
            if not obj.get("unexecutable_reason"):
                failures.append(
                    "unexecutable_reason: required when executability=UNEXECUTABLE"
                )
            if obj.get("oracle") is not None:
                failures.append(
                    "oracle: must be absent when executability=UNEXECUTABLE "
                    "(no oracle is ever fabricated for a prose-only verify)"
                )
        elif executability == "EXECUTABLE":
            if not obj.get("oracle"):
                failures.append("oracle: required when executability=EXECUTABLE")
    return failures


def validate_verification_full(obj: dict, schema: dict | None = None) -> dict:
    """Structural schema validation + the conditional rules above, combined.
    This is the function callers should use to fully validate a verification
    record; validate_verification_object() alone only covers what JSON
    Schema can express."""
    result = validate_verification_object(obj, schema)
    extra_failures = _validate_conditional_rules(obj)
    failures = list(result["failures"]) + extra_failures
    return {"ok": not failures, "failures": failures}


def validate_execution_against_verification(execution: dict, verification: dict) -> dict:
    """Cross-object honesty check (the heart of the Phase-4 mandate): an
    execution_result against an UNEXECUTABLE verification can only ever be
    recorded as result=UNEXECUTABLE. It is illegal for such a run to claim
    PASS/FAIL/ERROR/SKIPPED — those imply something actually ran.

    Returns {"ok": bool, "failures": [str, ...]}.
    """
    failures = []
    if execution.get("verification_id") != verification.get("id"):
        failures.append("verification_id does not match verification.id")
    if verification.get("executability") == "UNEXECUTABLE":
        if execution.get("result") != "UNEXECUTABLE":
            failures.append(
                "result: an execution_result against an UNEXECUTABLE verification "
                f"must record result=UNEXECUTABLE, got {execution.get('result')!r}"
            )
    return {"ok": not failures, "failures": failures}


# --------------------------------------------------------------------------
# Maintenance schedules (directive S12)
# --------------------------------------------------------------------------

SCHEDULE_KINDS = frozenset(
    {
        "ON_CHANGE",
        "DEPENDENCY_CHANGE",
        "DAILY",
        "WEEKLY",
        "MONTHLY",
        "RELEASE",
        "MANUAL",
    }
)

# Canonical default trigger list implied by each schedule kind (directive
# S12: "plus the trigger list each implies"). A schedule_entry.triggers value
# may narrow or extend this default explicitly; this dict is the fallback
# used by default_schedule_entry() and by migrate_v4_verify().
SCHEDULE_TRIGGERS: dict[str, tuple[str, ...]] = {
    "ON_CHANGE": ("source_file_changed", "lug_reached_ready_to_test"),
    "DEPENDENCY_CHANGE": ("dependency_version_changed", "upstream_verification_failed"),
    "DAILY": ("daily_cron",),
    "WEEKLY": ("weekly_cron",),
    "MONTHLY": ("monthly_cron",),
    "RELEASE": ("release_cut", "version_tag_created"),
    "MANUAL": ("operator_invoked",),
}


def default_schedule_entry(schedule: str) -> dict:
    """A schedule_entry using the canonical default trigger list for
    `schedule`. Raises ValueError for an unknown schedule kind."""
    if schedule not in SCHEDULE_KINDS:
        raise ValueError(f"unknown schedule kind: {schedule!r}")
    return {"schedule": schedule, "triggers": list(SCHEDULE_TRIGGERS[schedule])}


# --------------------------------------------------------------------------
# Coverage queries (directive S11)
# --------------------------------------------------------------------------


def _target_key(kind: str, ref: str) -> str:
    return f"{kind}:{ref}"


def compute_coverage(
    verifications: list[dict],
    targets: list[dict],
    redundant_at: int = 2,
) -> dict:
    """Directive S11: explicit, measurable coverage. For each target
    ({"kind":..., "ref":...}) determine how many EXECUTABLE verifications
    reference it via their `coverage` array, and classify:

      - UNCOVERED           executable_covering_count == 0
      - WEAKLY_COVERED       0 < executable_covering_count < redundant_at
      - REDUNDANTLY_COVERED  executable_covering_count >= redundant_at

    THE HONESTY RULE: only verifications with executability=="EXECUTABLE"
    are counted toward executable_covering_count. A verification that
    references a target but is UNEXECUTABLE still shows up in
    `unexecutable_covering_ids` for visibility, but never moves a target out
    of UNCOVERED — an unexecutable verification cannot make its target
    appear covered (Phase-4 mandate, directive Doctrine 1).

    Returns a dict keyed by "{kind}:{ref}" ->
      {
        "kind": ..., "ref": ...,
        "executable_covering_count": int,
        "executable_covering_ids": [verification id, ...],
        "unexecutable_covering_ids": [verification id, ...],
        "status": "UNCOVERED" | "WEAKLY_COVERED" | "REDUNDANTLY_COVERED",
      }

    Pure: does not mutate inputs, does no I/O.
    """
    if redundant_at < 1:
        raise ValueError("redundant_at must be >= 1")

    by_key = {}
    for t in targets:
        key = _target_key(t["kind"], t["ref"])
        by_key[key] = {
            "kind": t["kind"],
            "ref": t["ref"],
            "executable_covering_count": 0,
            "executable_covering_ids": [],
            "unexecutable_covering_ids": [],
        }

    for v in verifications:
        if v.get("object_type") != "verification":
            continue
        executable = v.get("executability") == "EXECUTABLE"
        for c in v.get("coverage", []):
            key = _target_key(c.get("kind"), c.get("ref"))
            if key not in by_key:
                continue
            if executable:
                by_key[key]["executable_covering_count"] += 1
                by_key[key]["executable_covering_ids"].append(v.get("id"))
            else:
                by_key[key]["unexecutable_covering_ids"].append(v.get("id"))

    for key, entry in by_key.items():
        count = entry["executable_covering_count"]
        if count == 0:
            entry["status"] = "UNCOVERED"
        elif count < redundant_at:
            entry["status"] = "WEAKLY_COVERED"
        else:
            entry["status"] = "REDUNDANTLY_COVERED"

    return by_key


def find_uncovered(verifications: list[dict], targets: list[dict], **kwargs) -> list:
    coverage = compute_coverage(verifications, targets, **kwargs)
    return [v for v in coverage.values() if v["status"] == "UNCOVERED"]


def find_weakly_covered(verifications: list[dict], targets: list[dict], **kwargs) -> list:
    coverage = compute_coverage(verifications, targets, **kwargs)
    return [v for v in coverage.values() if v["status"] == "WEAKLY_COVERED"]


def find_redundantly_covered(verifications: list[dict], targets: list[dict], **kwargs) -> list:
    coverage = compute_coverage(verifications, targets, **kwargs)
    return [v for v in coverage.values() if v["status"] == "REDUNDANTLY_COVERED"]


# --------------------------------------------------------------------------
# v4 verify -> v5 verification migration (directive S36/S37 + honesty rule)
# --------------------------------------------------------------------------

# A verify-item is treated as a real, machine-executable oracle command only
# if it starts with a recognizable command token. Anything else — including
# a command-shaped sentence with trailing prose, e.g. "Valid currency
# accepted; unknown rejected" — is prose. This is intentionally
# conservative: false negatives (a real command misclassified as prose,
# landing as UNEXECUTABLE) are the SAFE failure mode here; false positives
# (prose misclassified as a command) are exactly what the honesty rule
# forbids.
_EXECUTABLE_PREFIX_RE = re.compile(
    r"^\s*("
    r"pytest\b|python3?\b|bash\b|sh\b|cmd:|grep\b|curl\b|npm\b|npx\b|node\b|"
    r"\./|test\s+-[fdez]|git\b|make\b|docker\b|jq\b|diff\b"
    r")"
)


def _looks_executable(item) -> bool:
    if not isinstance(item, str):
        return False
    return bool(_EXECUTABLE_PREFIX_RE.match(item))


def _normalize_v4_verify(v4_verify) -> list:
    """v4 verify blocks are observed as a list[str], a bare str, or absent.
    Normalize to a list[str] without altering content."""
    if v4_verify is None:
        return []
    if isinstance(v4_verify, str):
        return [v4_verify] if v4_verify.strip() else []
    if isinstance(v4_verify, list):
        return [x for x in v4_verify if isinstance(x, str) and x.strip()]
    # Unknown shape (e.g. dict) — preserved verbatim in legacy.raw_v4_verify
    # by the caller, but not treated as command items here.
    return []


def migrate_v4_verify(lug_dict: dict, migrated_by: dict, migrated_at: str) -> dict:
    """Lift a v4 lug's `verify` block into an independent v5 `verification`
    object, purely in memory (directive S36/S37).

    THE HONESTY RULE: a prose-only (or empty, or mixed prose+command) v4
    verify block is marked executability=UNEXECUTABLE with an explicit
    unexecutable_reason. Only a verify block whose EVERY item looks like a
    real command is marked EXECUTABLE, and even then the commands are
    carried forward VERBATIM — never rewritten, never guessed at. This
    function never fabricates an oracle for prose; doing so would launder an
    unverified claim into the v5 graph, which is the single worst outcome
    this phase exists to prevent.

    Contract:
      - coverage: exactly one coverage_target {"kind": "lug", "ref": <lug id>}
        — a v4 verify block, embedded in the lug, covered only that lug.
      - schedule: a single MANUAL entry with the canonical default trigger
        list — v4 had no schedule concept, so nothing beyond "someone ran it"
        can be honestly asserted.
      - legacy.raw_v4_verify preserves the original verify content verbatim.
      - pure: same input always yields the same output; caller supplies
        `migrated_by`/`migrated_at` so no clock/disk/randomness is touched.

    Does NOT write anything to disk. Does NOT mutate lug_dict.
    """
    if not isinstance(lug_dict, dict):
        raise TypeError("lug_dict must be a dict")

    lug_id = lug_dict.get("id", "unknown")
    raw_verify = lug_dict.get("verify")
    items = _normalize_v4_verify(raw_verify)

    unknown_fields = []
    if not items:
        executability = "UNEXECUTABLE"
        unexecutable_reason = (
            "v4 lug carried no usable verify content — nothing to execute"
        )
        oracle = None
        unknown_fields.append("oracle")
    elif all(_looks_executable(item) for item in items):
        executability = "EXECUTABLE"
        unexecutable_reason = None
        oracle = {"type": "shell_commands", "commands": list(items)}
    else:
        executability = "UNEXECUTABLE"
        unexecutable_reason = (
            "v4 verify block is prose (not a machine-executable command) for "
            "at least one item — migrating it into a nicer schema does not "
            "make it executable; no oracle was fabricated from the prose "
            "(Phase-4 honesty rule)"
        )
        oracle = None
        unknown_fields.append("oracle")

    v5 = {
        "object_type": "verification",
        "id": f"verification-migrated-{lug_id}",
        "title": f"Migrated verify for {lug_id}",
        "coverage": [{"kind": "lug", "ref": lug_id}],
        "schedule": [default_schedule_entry("MANUAL")],
        "executability": executability,
        "attribution": {
            "created_by": migrated_by.get("model", "unknown") if isinstance(migrated_by, dict) else "unknown",
            "created_at": migrated_at,
            "created_by_model": dict(migrated_by) if isinstance(migrated_by, dict) else {"model": "unknown", "provider": "unknown"},
        },
        "legacy": {
            "migrated_from_schema": "v4",
            "migrated_from_id": lug_id,
            "migration_note": "produced by verification_objects.migrate_v4_verify — in-memory only, not written to disk",
            "raw_v4_verify": raw_verify,
            "unknown_fields": unknown_fields,
        },
    }
    if unexecutable_reason:
        v5["unexecutable_reason"] = unexecutable_reason
    if oracle:
        v5["oracle"] = oracle

    return v5


# --------------------------------------------------------------------------
# Retention (directive S15)
# --------------------------------------------------------------------------


def _parse_iso(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _age_days(ts: str, now: str) -> float:
    return (_parse_iso(now) - _parse_iso(ts)).total_seconds() / 86400.0


def apply_retention(
    execution_results: list[dict],
    policy: dict,
    now: str,
) -> dict:
    """Directive S15: durable definitions persist forever; recent evidence
    stays detailed; older evidence compresses to aggregates; expired
    evidence is deleted or archived by policy.

    This function operates ONLY on execution_result records — it never
    receives and never touches `verification`/`validation_setup` definition
    objects, which is how "durable definitions persist forever" is
    guaranteed: the function's input type makes it structurally impossible
    to retire a definition.

    policy: {"hot_days": N, "aggregate_after_days": M, "expire_after_days": K,
              "archive_on_expire": bool (default False)}
    Requires hot_days <= aggregate_after_days <= expire_after_days.

    Ages are computed as (now - finished_at), falling back to started_at if
    finished_at is absent.

    Returns:
      {
        "definitions_preserved": True,   # constant marker — see docstring
        "hot": [execution_result, ...],           # unchanged, full detail
        "aggregated": [aggregate_summary, ...],    # grouped by (verification_id, result)
        "expired": [{"id":..., "verification_id":..., "disposition": "archived"|"deleted", "age_days": ...}, ...],
      }

    Pure: does not mutate inputs, does not read the clock (caller supplies
    `now`).
    """
    hot_days = policy["hot_days"]
    aggregate_after_days = policy["aggregate_after_days"]
    expire_after_days = policy["expire_after_days"]
    archive_on_expire = policy.get("archive_on_expire", False)

    if not (hot_days <= aggregate_after_days <= expire_after_days):
        raise ValueError(
            "policy must satisfy hot_days <= aggregate_after_days <= expire_after_days, "
            f"got {hot_days} <= {aggregate_after_days} <= {expire_after_days}"
        )

    hot = []
    to_aggregate = []
    expired = []

    for r in execution_results:
        ts = r.get("finished_at") or r.get("started_at")
        age = _age_days(ts, now)
        if age < aggregate_after_days:
            hot.append(copy.deepcopy(r))
        elif age < expire_after_days:
            to_aggregate.append((r, age))
        else:
            expired.append(
                {
                    "id": r.get("id"),
                    "verification_id": r.get("verification_id"),
                    "disposition": "archived" if archive_on_expire else "deleted",
                    "age_days": age,
                }
            )

    # Group the aggregate bucket by (verification_id, result).
    groups: dict[tuple, dict] = {}
    for r, age in to_aggregate:
        key = (r.get("verification_id"), r.get("result"))
        g = groups.setdefault(
            key,
            {
                "verification_id": r.get("verification_id"),
                "result": r.get("result"),
                "count": 0,
                "earliest": None,
                "latest": None,
                "sample_execution_ids": [],
            },
        )
        g["count"] += 1
        ts = r.get("finished_at") or r.get("started_at")
        if g["earliest"] is None or ts < g["earliest"]:
            g["earliest"] = ts
        if g["latest"] is None or ts > g["latest"]:
            g["latest"] = ts
        if len(g["sample_execution_ids"]) < 3:
            g["sample_execution_ids"].append(r.get("id"))

    aggregated = list(groups.values())

    return {
        "definitions_preserved": True,
        "hot": hot,
        "aggregated": aggregated,
        "expired": expired,
    }


def main(argv):  # pragma: no cover - thin CLI wrapper
    if not argv:
        print("usage: verification_objects.py validate <obj.json>", file=__import__("sys").stderr)
        return 2
    if argv[0] == "validate" and len(argv) > 1:
        obj = json.load(open(argv[1]))
        result = validate_verification_full(obj)
        if result["ok"]:
            print(f"OK — valid v5 verification object: {argv[1]}")
            return 0
        print(f"FAIL — v5 schema NOT satisfied ({len(result['failures'])} issue(s)):")
        for f in result["failures"]:
            print(f"  - {f}")
        return 1
    print("usage: verification_objects.py validate <obj.json>")
    return 2


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main(sys.argv[1:]))
