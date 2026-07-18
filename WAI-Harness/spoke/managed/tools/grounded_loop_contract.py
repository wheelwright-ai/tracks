#!/usr/bin/env python3
"""grounded_loop_contract.py — the GroundedLoop contract: schema + validator.

A GroundedLoop is a work item's contract for *measured* completion. It separates two
gates that are usually conflated:

  1. legality_gate  — is the work well-posed (well_formed / self_contained / verifiable)?
  2. metric_target  — a NAMED signal + the ORACLE that measures it + the DIRECTION it
                      must move. This is what the close-gate checks before stamping a
                      loop 'completed'.

Honesty rule (enforced here, not just in the schema): a soft outcome (metric_target.soft
== true) MUST carry non-empty soft_limits. An unverifiable claim that hides its limits is
exactly the say-do gap this whole subsystem exists to close.

Pure over an injected dict; no I/O beyond loading the sibling schema. Uses jsonschema when
importable, else a stdlib required-field fallback (no new dependency).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "grounded_loop.schema.json"
_VALID_DIRECTIONS = ("up", "down", "becomes_true")


def load_schema() -> Dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text())


def _fallback_validate(gl: Dict[str, Any]) -> List[str]:
    """Minimal required-field check when jsonschema is unavailable."""
    errors: List[str] = []
    if not isinstance(gl, dict):
        return ["grounded_loop must be an object"]
    mt = gl.get("metric_target")
    if not isinstance(mt, dict):
        return ["metric_target is required and must be an object"]
    for field in ("name", "oracle", "direction"):
        if not mt.get(field):
            errors.append(f"metric_target.{field} is required and must be non-empty")
    if mt.get("direction") and mt["direction"] not in _VALID_DIRECTIONS:
        errors.append(f"metric_target.direction must be one of {_VALID_DIRECTIONS}")
    return errors


def validate_contract(gl: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Return (ok, errors). Structural check via jsonschema (or fallback) PLUS the
    explicit soft->soft_limits honesty rule."""
    errors: List[str] = []
    try:
        import jsonschema  # type: ignore

        validator = jsonschema.Draft7Validator(load_schema())
        errors = [e.message for e in sorted(validator.iter_errors(gl), key=lambda e: list(e.path))]
    except Exception:
        errors = _fallback_validate(gl)

    # Honesty rule (belt-and-suspenders; independent of schema conditionals):
    mt = gl.get("metric_target") if isinstance(gl, dict) else None
    if isinstance(mt, dict) and mt.get("soft") is True:
        if not str(mt.get("soft_limits", "")).strip():
            errors.append("metric_target.soft is true but soft_limits is empty (a soft outcome must state its limits)")

    return (len(errors) == 0, errors)


def attach_default_contract(lug: Dict[str, Any]) -> Dict[str, Any]:
    """Attach a conservative default grounded_loop to a lug that has none, so an
    un-annotated loop is treated as SOFT (labeled, never a hard green) rather than
    silently trusted. Idempotent — never overwrites an existing contract."""
    if not isinstance(lug, dict):
        return lug
    if isinstance(lug.get("grounded_loop"), dict) and lug["grounded_loop"].get("metric_target"):
        return lug
    lug["grounded_loop"] = {
        "legality_gate": {"well_formed": True, "self_contained": True, "verifiable": False},
        "metric_target": {
            "name": "unclassified outcome",
            "oracle": "unknown",
            "direction": "becomes_true",
            "soft": True,
            "soft_limits": (
                "No deterministic oracle was declared for this loop; completion is asserted by the "
                "executor, not measured. Treated as soft — labeled, never counted as a hard green."
            ),
        },
    }
    return lug


if __name__ == "__main__":
    import sys

    data = json.loads(Path(sys.argv[1]).read_text()) if len(sys.argv) > 1 else {}
    gl = data.get("grounded_loop", data)
    ok, errs = validate_contract(gl)
    print(json.dumps({"ok": ok, "errors": errs}, indent=2))
    sys.exit(0 if ok else 1)
