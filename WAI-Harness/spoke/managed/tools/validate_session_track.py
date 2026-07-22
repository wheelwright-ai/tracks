"""Validate session track entries against the canonical schema.

Session track entries written by ozi_autopilot and other execution modes must
maintain a strict schema to prevent silent data loss (regression: tokens_used
field dropped to null). This validator enforces the schema.

PROVENANCE + SCOPE (absorbed into master 2026-07-22)
Authored on the pathfinder spoke and contributed back through
harness_converge.py; it arrived under .claude/hooks/ there, and was placed in
tools/ here because it is a library plus CLI that nothing binds — shipping it in
the hooks directory would deploy an unbound file to every spoke and read as an
orphan to the circle audit.

It validates AUTOPILOT-shaped turn entries: the required set includes lug_id,
lug_title, tokens_used and commit_sha, and VALID_SOURCES covers the machine
writers only. An interactive session's track (source="model", judgment fields
instead of lug fields) is a DIFFERENT shape and will fail every check here — that
is scope, not a bug. Point this at AP tracks; widening it to cover both shapes is
a deliberate change, not a config tweak.

Usage:
  Standalone (audit an existing track file):
    python3 validate_session_track.py /path/to/track.jsonl

  In Python (validate a single entry before writing):
    from validate_session_track import validate_entry
    result = validate_entry(entry_dict, context="writing turn entry")
    if not result['ok']:
        raise ValueError(f"Track entry validation failed: {result['errors']}")
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Any


REQUIRED_FIELDS = {
    "event",
    "turn",
    "source",
    "session_id",
    "ts",
    "lug_id",
    "lug_title",
    "lug_type",
    "model_fit",
    "tokens_used",
    "outcome",
    "commit_sha",
}

VALID_SOURCES = {"autopilot", "transcript-synth", "sdk-synth", "stop-hook-transcript"}
# Expanded to include all observed lug types in historical data for backward compatibility.
VALID_LUG_TYPES = {
    "implementation", "feature", "spec", "bugfix", "refactor", "chore", "research",
    "signal", "task", "other", "session-summary", "epic", "notice", "needs-you", "needs_you"
}
# Model fits: accept both lowercase and uppercase for backward compatibility.
VALID_MODEL_FITS = {"haiku", "sonnet", "opus", "fable", "human",
                    "HAIKU", "SONNET", "OPUS", "FABLE", "HUMAN"}
VALID_OUTCOMES = {"completed", "error", "stalled"}


def validate_entry(entry: Dict[str, Any], context: str = "") -> Dict[str, Any]:
    """Validate a single track entry. Returns {'ok': bool, 'errors': [str], 'warnings': [str]}."""
    errors = []
    warnings = []

    if not isinstance(entry, dict):
        errors.append(f"Entry is not a dict: {type(entry).__name__}")
        return {"ok": False, "errors": errors, "warnings": warnings}

    event = entry.get("event")

    # Skip validation for non-turn events (session_start, run_summary, etc).
    if event != "turn":
        return {"ok": True, "errors": [], "warnings": []}

    # Check all required fields are present and non-null.
    for field in REQUIRED_FIELDS:
        if field not in entry:
            errors.append(f"MISSING required field: {field}")
        elif entry[field] is None:
            errors.append(f"NULL required field: {field}")
        elif isinstance(entry[field], str) and not entry[field].strip():
            # commit_sha is allowed to be empty (backfilled after git commit in ozi_autopilot)
            if field != "commit_sha":
                errors.append(f"EMPTY required field: {field}")

    # Type and value checks for critical fields.
    if "turn" in entry and entry["turn"] is not None:
        if not isinstance(entry["turn"], int) or entry["turn"] < 1:
            errors.append(f"turn must be int >= 1, got: {entry['turn']}")

    if "source" in entry and entry["source"] is not None:
        if entry["source"] not in VALID_SOURCES:
            errors.append(
                f"source must be one of {VALID_SOURCES}, got: {entry['source']!r}"
            )

    if "lug_type" in entry and entry["lug_type"] is not None:
        if entry["lug_type"] not in VALID_LUG_TYPES:
            errors.append(
                f"lug_type must be one of {VALID_LUG_TYPES}, got: {entry['lug_type']!r}"
            )

    if "model_fit" in entry and entry["model_fit"] is not None:
        if entry["model_fit"] not in VALID_MODEL_FITS:
            errors.append(
                f"model_fit must be one of {VALID_MODEL_FITS}, got: {entry['model_fit']!r}"
            )

    if "tokens_used" in entry and entry["tokens_used"] is not None:
        if not isinstance(entry["tokens_used"], int) or entry["tokens_used"] < 0:
            errors.append(
                f"tokens_used must be int >= 0, got: {entry['tokens_used']!r} (type: {type(entry['tokens_used']).__name__})"
            )

    if "outcome" in entry and entry["outcome"] is not None:
        if entry["outcome"] not in VALID_OUTCOMES:
            errors.append(
                f"outcome must be one of {VALID_OUTCOMES}, got: {entry['outcome']!r}"
            )

    # Conditional checks: error_code required when outcome=error.
    if entry.get("outcome") == "error" and not entry.get("error_code"):
        warnings.append("outcome=error but error_code is missing/empty")

    # Conditional checks: reason required when outcome=stalled.
    if entry.get("outcome") == "stalled" and not entry.get("reason"):
        warnings.append("outcome=stalled but reason is missing/empty")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def validate_track_file(track_path: Path) -> Dict[str, Any]:
    """Validate all turn entries in a track.jsonl file.

    Returns: {
        'ok': bool,
        'total_entries': int,
        'valid_entries': int,
        'invalid_entries': int,
        'issues': [{line_no, entry, errors, warnings}]
    }
    """
    issues = []
    total_entries = 0
    valid_entries = 0

    try:
        lines = track_path.read_text().splitlines()
    except Exception as e:
        return {
            "ok": False,
            "total_entries": 0,
            "valid_entries": 0,
            "invalid_entries": 0,
            "read_error": str(e),
            "issues": [],
        }

    for line_no, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            issues.append({
                "line_no": line_no,
                "error": f"Invalid JSON: {e}",
                "entry": line[:100],
            })
            total_entries += 1
            continue

        total_entries += 1

        # Skip non-turn events.
        if entry.get("event") != "turn":
            valid_entries += 1
            continue

        result = validate_entry(entry)
        if result["ok"] and not result["warnings"]:
            valid_entries += 1
        else:
            issues.append({
                "line_no": line_no,
                "entry_id": entry.get("lug_id", "?"),
                "errors": result["errors"],
                "warnings": result["warnings"],
            })

    return {
        "ok": len([i for i in issues if i.get("errors")]) == 0,
        "total_entries": total_entries,
        "valid_entries": valid_entries,
        "invalid_entries": total_entries - valid_entries,
        "issues": issues,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Usage: validate_session_track.py <track_path>",
            "usage": "Audits all turn entries in a session track.jsonl file"
        }))
        sys.exit(1)

    track_path = Path(sys.argv[1])
    if not track_path.exists():
        print(json.dumps({
            "error": f"Track file not found: {track_path}",
        }))
        sys.exit(1)

    result = validate_track_file(track_path)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
