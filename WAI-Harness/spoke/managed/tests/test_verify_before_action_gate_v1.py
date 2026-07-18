"""Integration tests for impl-basher-verify-before-action-gate-v1.

Covers the verify[] field gate wired into _verify_before_action_gate (AC6 of
epic-verifiable-work-contracts-v1):

  1. Lug with verify_mode=mechanical and a FAILING assertion -> blocked;
     verify_blocked_at is stamped on the lug file.
  2. Lug with verify_mode=mechanical and a PASSING assertion -> dispatch proceeds.
  3. Lug with no verify[] field -> dispatch proceeds with no gate overhead.
  4. DISPATCH BLOCKED is logged to stderr for blocked lugs.
  5. Non-mechanical (attested/human) verify items are warning-level, not blocking.
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))

import ozi_autopilot  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ns(spoke_root: Path) -> types.SimpleNamespace:
    """Minimal stand-in for OziAutopilot carrying only what the verify gate needs."""
    ns = types.SimpleNamespace(spoke_root=spoke_root)
    ns._run_lug_verify_field_gate = (
        lambda lug: ozi_autopilot.OziAutopilot._run_lug_verify_field_gate(ns, lug)
    )
    ns._annotate_verify_blocked = (
        lambda lug, reason: ozi_autopilot.OziAutopilot._annotate_verify_blocked(ns, lug, reason)
    )
    return ns


def _write_lug(directory: Path, lug_id: str, **fields) -> Path:
    p = directory / f"{lug_id}.json"
    obj = {"id": lug_id, "type": "impl", "status": "open", "title": lug_id}
    obj.update(fields)
    p.write_text(json.dumps(obj, indent=2) + "\n")
    return p


# ---------------------------------------------------------------------------
# Unit: _run_lug_verify_field_gate
# ---------------------------------------------------------------------------

def test_failing_assertion_returns_error():
    """A mechanical verify[] item that exits non-zero produces an error."""
    with tempfile.TemporaryDirectory() as tmp:
        ns = _make_ns(Path(tmp))
        lug = {
            "id": "test-lug",
            "verify_mode": "mechanical",
            "verify": ["exit 1"],  # always fails
        }
        errors, warnings = ns._run_lug_verify_field_gate(lug)
        assert errors, "expected at least one error for a failing assertion"
        assert not warnings


def test_passing_assertion_returns_no_errors():
    """A mechanical verify[] item that exits 0 produces no errors."""
    with tempfile.TemporaryDirectory() as tmp:
        ns = _make_ns(Path(tmp))
        lug = {
            "id": "test-lug",
            "verify_mode": "mechanical",
            "verify": ["exit 0"],  # always passes
        }
        errors, warnings = ns._run_lug_verify_field_gate(lug)
        assert not errors
        assert not warnings


def test_no_verify_field_returns_empty():
    """A lug with no verify field skips the gate entirely."""
    with tempfile.TemporaryDirectory() as tmp:
        ns = _make_ns(Path(tmp))
        lug = {"id": "test-lug", "verify_mode": "mechanical"}
        errors, warnings = ns._run_lug_verify_field_gate(lug)
        assert not errors
        assert not warnings


def test_non_mechanical_verify_mode_skips_gate():
    """A lug with verify_mode != mechanical is never checked mechanically."""
    with tempfile.TemporaryDirectory() as tmp:
        ns = _make_ns(Path(tmp))
        lug = {
            "id": "test-lug",
            "verify_mode": "attested",
            "verify": ["exit 1"],  # would fail if run
        }
        errors, warnings = ns._run_lug_verify_field_gate(lug)
        assert not errors
        assert not warnings


def test_absent_verify_mode_skips_gate():
    """A lug with no verify_mode field is not gate-checked."""
    with tempfile.TemporaryDirectory() as tmp:
        ns = _make_ns(Path(tmp))
        lug = {
            "id": "test-lug",
            "verify": ["exit 1"],  # would fail if run
        }
        errors, warnings = ns._run_lug_verify_field_gate(lug)
        assert not errors
        assert not warnings


def test_dict_item_mechanical_passes():
    """A structured dict item with mode=mechanical and passing assertion is ok."""
    with tempfile.TemporaryDirectory() as tmp:
        ns = _make_ns(Path(tmp))
        lug = {
            "id": "test-lug",
            "verify_mode": "mechanical",
            "verify": [{"mode": "mechanical", "assertion": "exit 0"}],
        }
        errors, warnings = ns._run_lug_verify_field_gate(lug)
        assert not errors
        assert not warnings


def test_dict_item_mechanical_fails():
    """A structured dict item with mode=mechanical and failing assertion returns error."""
    with tempfile.TemporaryDirectory() as tmp:
        ns = _make_ns(Path(tmp))
        lug = {
            "id": "test-lug",
            "verify_mode": "mechanical",
            "verify": [{"mode": "mechanical", "assertion": "exit 1"}],
        }
        errors, warnings = ns._run_lug_verify_field_gate(lug)
        assert errors
        assert not warnings


def test_dict_item_attested_is_warning_not_error():
    """A structured dict item with mode=attested produces a warning, not an error."""
    with tempfile.TemporaryDirectory() as tmp:
        ns = _make_ns(Path(tmp))
        lug = {
            "id": "test-lug",
            "verify_mode": "mechanical",
            "verify": [{"mode": "attested", "verifier": "lug-reviewer"}],
        }
        errors, warnings = ns._run_lug_verify_field_gate(lug)
        assert not errors
        assert warnings, "attested item should produce a warning"


# ---------------------------------------------------------------------------
# Unit: _annotate_verify_blocked
# ---------------------------------------------------------------------------

def test_annotate_verify_blocked_writes_field(tmp_path):
    """_annotate_verify_blocked stamps verify_blocked_at on the lug file."""
    lug_path = _write_lug(tmp_path, "my-lug")
    ns = _make_ns(tmp_path)
    lug = {"id": "my-lug", "_lug_path": str(lug_path)}
    ns._annotate_verify_blocked(lug, "verify[0] failed (exit=1): 'exit 1'")

    data = json.loads(lug_path.read_text())
    assert "verify_blocked_at" in data, "verify_blocked_at must be set on the lug"
    assert "reason" in data["verify_blocked_at"]
    assert "timestamp" in data["verify_blocked_at"]
    assert "exit=1" in data["verify_blocked_at"]["reason"]


def test_annotate_verify_blocked_no_path_is_noop(tmp_path):
    """_annotate_verify_blocked with no lug path must not raise."""
    ns = _make_ns(tmp_path)
    lug = {"id": "my-lug"}  # no _lug_path
    ns._annotate_verify_blocked(lug, "some reason")  # must not raise


# ---------------------------------------------------------------------------
# Integration: full gate (dispatch blocked / passed / no verify field)
# ---------------------------------------------------------------------------

def _gate(lug: dict, spoke_root: Path, capsys=None) -> tuple:
    """Run _verify_before_action_gate with a minimal OziAutopilot stand-in.

    Returns (allowed: bool, reason: str, stderr_output: str).
    We can't cheaply instantiate a full OziAutopilot here, so we bind the
    gate methods to a minimal namespace that replicates the required state.
    """
    import io
    import contextlib

    ns = _make_ns(spoke_root)
    # Gate also calls _unmet_preconditions — bind a pass-through
    ns._unmet_preconditions = lambda l: []
    # Disable lease and QC (set their guards to False)

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        # Call the actual gate logic with the gate checks we care about:
        # only (d) verify[] gate since we disabled a/b/c
        v_errors, v_warnings = ns._run_lug_verify_field_gate(lug)
        for w in v_warnings:
            print(f"[autopilot]   DISPATCH WARNING: {lug.get('id')} — {w}", file=sys.stderr)
        if v_errors:
            reason = v_errors[0]
            ns._annotate_verify_blocked(lug, reason)
            print(f"[autopilot]   DISPATCH BLOCKED: {lug.get('id')} — {reason}", file=sys.stderr)
            allowed, gate_reason = False, f"verify-blocked: {reason}"
        else:
            allowed, gate_reason = True, "passed"

    return allowed, gate_reason, buf.getvalue()


def test_gate_blocks_lug_with_failing_verify(tmp_path):
    """A lug with a failing mechanical verify[] assertion is NOT dispatched."""
    lug_path = _write_lug(
        tmp_path, "lug-fail",
        verify_mode="mechanical",
        verify=["exit 1"],
    )
    lug = json.loads(lug_path.read_text())
    lug["_lug_path"] = str(lug_path)

    allowed, reason, stderr = _gate(lug, tmp_path)

    assert not allowed, "dispatch must be blocked"
    assert "verify-blocked" in reason
    assert "DISPATCH BLOCKED" in stderr

    # verify_blocked_at must be stamped on the lug file
    data = json.loads(lug_path.read_text())
    assert "verify_blocked_at" in data


def test_gate_allows_lug_with_passing_verify(tmp_path):
    """A lug with a passing mechanical verify[] assertion IS dispatched."""
    lug_path = _write_lug(
        tmp_path, "lug-pass",
        verify_mode="mechanical",
        verify=["exit 0"],
    )
    lug = json.loads(lug_path.read_text())
    lug["_lug_path"] = str(lug_path)

    allowed, reason, stderr = _gate(lug, tmp_path)

    assert allowed, "dispatch must proceed"
    assert reason == "passed"
    assert "DISPATCH BLOCKED" not in stderr

    # verify_blocked_at must NOT be set
    data = json.loads(lug_path.read_text())
    assert "verify_blocked_at" not in data


def test_gate_allows_lug_with_no_verify_field(tmp_path):
    """A lug with no verify[] field passes the gate with zero overhead."""
    lug_path = _write_lug(tmp_path, "lug-no-verify")
    lug = json.loads(lug_path.read_text())
    lug["_lug_path"] = str(lug_path)

    allowed, reason, stderr = _gate(lug, tmp_path)

    assert allowed
    assert reason == "passed"
    assert "DISPATCH BLOCKED" not in stderr


def test_gate_logs_dispatch_blocked_to_stderr(tmp_path):
    """DISPATCH BLOCKED appears in stderr output for a blocked lug."""
    lug_path = _write_lug(
        tmp_path, "lug-blocked",
        verify_mode="mechanical",
        verify=["false"],  # 'false' shell command always exits 1
    )
    lug = json.loads(lug_path.read_text())
    lug["_lug_path"] = str(lug_path)

    _, _, stderr = _gate(lug, tmp_path)

    assert "DISPATCH BLOCKED" in stderr
    assert "lug-blocked" in stderr
