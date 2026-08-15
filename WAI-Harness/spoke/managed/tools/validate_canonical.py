"""Re-export wrapper for validate_canonical.

This module is a thin wrapper that imports and re-exports validate_canonical
from the canonical location (tools/validate_canonical.py). This consolidation
eliminates code duplication and ensures all consumers use the single source of
truth for lug validation.

All validation logic, helper functions, and constants are defined in the
primary tools/validate_canonical.py module. This wrapper simply re-exports
them for backwards compatibility with code that imports from managed/tools/.

Canonical consumers include:
  - spoke_expediter.py — uses validate_lug() as completeness gate
  - wai_assurance.py — schedules validate_canonical as quality verifier
  - test suite — validate_canonical_v4_paths, v3noop_sweep_v4_paths
"""
import sys
import importlib.util
from pathlib import Path

# Locate the primary tools module (one level up from spoke/managed/tools)
# Traverse: managed/tools -> managed -> spoke -> . (root) -> tools/
root = Path(__file__).resolve().parent.parent.parent.parent.parent
tools_module_path = root / "tools" / "validate_canonical.py"

if not tools_module_path.exists():
    raise ImportError(f"Primary validate_canonical module not found at {tools_module_path}")

# Import the primary module directly by file path to avoid circular imports
spec = importlib.util.spec_from_file_location("validate_canonical_primary", tools_module_path)
validate_canonical_primary = importlib.util.module_from_spec(spec)
sys.modules["validate_canonical_primary"] = validate_canonical_primary
spec.loader.exec_module(validate_canonical_primary)

# Re-export everything from the primary module.
#
# Guarded, because a bare `module.ATTR` here is a silent kill switch. Every name
# below is resolved against whatever primary the SPOKE happens to carry, and
# those primaries drift: a spoke whose tools/validate_canonical.py predates
# MANAGED_SPEC_FROM_ROOT raised AttributeError at IMPORT time, so canonical
# object validation did not run at all on that spoke — no error surfaced to the
# operator, lugs simply stopped being validated. That is the suspected upstream
# of the 114 "repairable" lugs found on track-prompt-lab: the gate meant to
# reject incomplete lugs at creation was raising instead of validating.
#
# So: never crash at import. Resolve what exists, record what does not, and make
# any attempt to USE a missing symbol fail loudly with the version mismatch
# named. A missing gate must announce itself; it must never read as a pass.

_REEXPORTS = (
    "SPEC_REL", "MANAGED_SPEC_FROM_ROOT", "OPEN_STATUSES", "INPROGRESS_STATUSES",
    "DONE_STATUSES", "MODEL_FITS", "_base", "_load_json", "SPEC_SUFFIX",
    "_lugs_root", "_spec_path", "_all_lug_ids", "_active_spec_ids", "_nonempty",
    "validate_lug", "validate_track", "validate_spec", "run", "main",
)

#: Names this shim expected but the local primary does not define. Empty on a
#: levelled spoke. Read by callers that want to report drift rather than guess.
MISSING_FROM_PRIMARY = []

_SENTINEL = object()


def _version_mismatch(name):
    """Build a callable that refuses, explaining exactly what is out of date."""
    def _refuse(*_args, **_kwargs):
        raise ImportError(
            "validate_canonical: %r cannot run — this spoke's primary is out of "
            "date.\n"
            "  primary: %s\n"
            "  missing: %s\n"
            "The managed shim expects those names, so canonical validation is "
            "NOT running on this spoke.\n"
            "Fix: level this spoke's tools/validate_canonical.py to the current "
            "harness cut, or vendor the primary into managed/."
            % (name, tools_module_path, ", ".join(MISSING_FROM_PRIMARY) or name)
        )
    _refuse.__name__ = name
    _refuse.missing_from_primary = True
    return _refuse


for _name in _REEXPORTS:
    _value = getattr(validate_canonical_primary, _name, _SENTINEL)
    if _value is _SENTINEL:
        MISSING_FROM_PRIMARY.append(_name)
        _value = _version_mismatch(_name)
    globals()[_name] = _value

# A missing CONSTANT cannot announce itself the way a missing function can — it
# would just be None threaded into a path join, which is the silent degradation
# this guard exists to end. So if ANYTHING is missing, the entry points refuse,
# even the ones that resolved fine. Partial validation reported as validation is
# worse than no validation: it is a green light nobody earned.
if MISSING_FROM_PRIMARY:
    for _name in ("validate_lug", "validate_track", "validate_spec", "run", "main"):
        globals()[_name] = _version_mismatch(_name)

del _name, _value, _SENTINEL

__all__ = [
    'SPEC_REL',
    'MANAGED_SPEC_FROM_ROOT',
    'OPEN_STATUSES',
    'INPROGRESS_STATUSES',
    'DONE_STATUSES',
    'MODEL_FITS',
    '_base',
    '_load_json',
    'SPEC_SUFFIX',
    '_lugs_root',
    '_spec_path',
    '_all_lug_ids',
    '_active_spec_ids',
    '_nonempty',
    'validate_lug',
    'validate_track',
    'validate_spec',
    'run',
    'main',
]
