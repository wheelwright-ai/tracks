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

# Re-export everything from the primary module
SPEC_REL = validate_canonical_primary.SPEC_REL
MANAGED_SPEC_FROM_ROOT = validate_canonical_primary.MANAGED_SPEC_FROM_ROOT
OPEN_STATUSES = validate_canonical_primary.OPEN_STATUSES
INPROGRESS_STATUSES = validate_canonical_primary.INPROGRESS_STATUSES
DONE_STATUSES = validate_canonical_primary.DONE_STATUSES
MODEL_FITS = validate_canonical_primary.MODEL_FITS
_base = validate_canonical_primary._base
_load_json = validate_canonical_primary._load_json
SPEC_SUFFIX = validate_canonical_primary.SPEC_SUFFIX
_lugs_root = validate_canonical_primary._lugs_root
_spec_path = validate_canonical_primary._spec_path
_all_lug_ids = validate_canonical_primary._all_lug_ids
_active_spec_ids = validate_canonical_primary._active_spec_ids
_nonempty = validate_canonical_primary._nonempty
validate_lug = validate_canonical_primary.validate_lug
validate_track = validate_canonical_primary.validate_track
validate_spec = validate_canonical_primary.validate_spec
run = validate_canonical_primary.run
main = validate_canonical_primary.main

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
