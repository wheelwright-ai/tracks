#!/usr/bin/env python3
"""Fixtures for trust_epoch.py -- the LOW TRUST W1 gate.

Each test pins one property the tenet depends on. The ones that matter most are the
NEGATIVE fixtures: an unmeasured floor must never render as a number, and an
unfalsifiable lug must never be counted as trusted by any path.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import trust_epoch as te


EPOCH = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)


def _write_lug(root, ltype, lug):
    d = os.path.join(root, "WAI-Harness", "spoke", "local", "lugs", "bytype", ltype, "completed")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{lug['id']}.json")
    with open(path, "w") as handle:
        json.dump(lug, handle, indent=2)
    return path


def _lug(lug_id, *, verify=True, targets=True, when=None, certified=False):
    lug = {"id": lug_id, "type": "impl", "status": "completed"}
    if verify:
        lug["verify"] = ["pytest -q tests/x.py"]
    if targets:
        lug["file_targets"] = ["tools/x.py"]
    if when is not None:
        lug["completed_at"] = when.isoformat()
    if certified:
        lug["certification"] = {"verdict": "approved", "by": "pattern-gate"}
    return lug


@pytest.fixture
def spoke(tmp_path):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "WAI-Harness", "spoke", "local"), exist_ok=True)
    return root


# --- epoch stamping -------------------------------------------------------


def test_stamp_creates_epoch(spoke):
    out = te.stamp(spoke, when=EPOCH)
    assert out["changed"] is True
    assert te.epoch_of(spoke) == EPOCH


def test_stamp_is_idempotent_without_force(spoke):
    te.stamp(spoke, when=EPOCH)
    out = te.stamp(spoke, when=EPOCH + timedelta(days=5))
    assert out["changed"] is False
    assert te.epoch_of(spoke) == EPOCH, "epoch moved without --force"


def test_restamp_requires_force_and_is_recorded(spoke):
    te.stamp(spoke, when=EPOCH)
    later = EPOCH + timedelta(days=5)
    out = te.stamp(spoke, when=later, force=True)
    assert out["changed"] is True
    assert te.epoch_of(spoke) == later
    history = te.read_state(spoke)["epoch_history"]
    assert len(history) == 1 and history[0]["was"] == te._iso(EPOCH)


# --- classification -------------------------------------------------------


def test_pre_epoch_checkable_lug_is_quarantined(spoke):
    te.stamp(spoke, when=EPOCH)
    _write_lug(spoke, "impl", _lug("old-v1", when=EPOCH - timedelta(days=1)))
    result = te.scan(spoke)
    assert result["counts"][te.CLASS_QUARANTINED] == 1
    assert result["counts"][te.CLASS_PROVEN] == 0


def test_post_epoch_certified_lug_is_proven(spoke):
    te.stamp(spoke, when=EPOCH)
    _write_lug(spoke, "impl", _lug("new-v1", when=EPOCH + timedelta(hours=1), certified=True))
    result = te.scan(spoke)
    assert result["counts"][te.CLASS_PROVEN] == 1


def test_post_epoch_uncertified_lug_is_provisional_not_proven(spoke):
    te.stamp(spoke, when=EPOCH)
    _write_lug(spoke, "impl", _lug("new-v2", when=EPOCH + timedelta(hours=1)))
    result = te.scan(spoke)
    assert result["counts"][te.CLASS_PROVISIONAL] == 1
    assert result["counts"][te.CLASS_PROVEN] == 0, "self-completion counted as proven"


@pytest.mark.parametrize("targets", [True, False])
def test_missing_verify_is_unfalsifiable_regardless_of_targets(spoke, targets):
    """No verify statement means nothing says what would prove the lug. file_targets
    alone say what was touched, which is not the same as what correct looks like."""
    te.stamp(spoke, when=EPOCH)
    _write_lug(spoke, "impl", _lug(
        f"u-{int(targets)}", verify=False, targets=targets,
        when=EPOCH + timedelta(hours=1), certified=True))
    result = te.scan(spoke)
    assert result["counts"][te.CLASS_UNFALSIFIABLE] == 1
    assert result["counts"][te.CLASS_PROVEN] == 0, "a certified stamp laundered an uncheckable lug"


def test_verify_without_targets_is_checkable_but_flagged_unlocatable(spoke):
    """The correction of 2026-08-02: a re-runnable verify step IS a check. Missing
    file_targets is a locatability cost, reported separately, never a disqualifier."""
    te.stamp(spoke, when=EPOCH)
    _write_lug(spoke, "impl", _lug("v-only", verify=True, targets=False,
                                   when=EPOCH + timedelta(hours=1), certified=True))
    result = te.scan(spoke)
    assert result["counts"][te.CLASS_PROVEN] == 1
    assert result["counts"][te.CLASS_UNFALSIFIABLE] == 0
    assert result["unlocatable"] == 1


def test_unfalsifiable_outranks_quarantine(spoke):
    """A pre-epoch uncheckable lug reports unfalsifiable -- quarantine implies a way out."""
    te.stamp(spoke, when=EPOCH)
    _write_lug(spoke, "impl", _lug("old-u", verify=False, targets=False,
                                   when=EPOCH - timedelta(days=30)))
    result = te.scan(spoke)
    assert result["counts"][te.CLASS_UNFALSIFIABLE] == 1
    assert result["counts"][te.CLASS_QUARANTINED] == 0


def test_missing_timestamp_is_quarantined_not_trusted(spoke):
    te.stamp(spoke, when=EPOCH)
    _write_lug(spoke, "impl", _lug("no-ts", when=None, certified=True))
    result = te.scan(spoke)
    assert result["counts"][te.CLASS_QUARANTINED] == 1


def test_unparseable_timestamp_is_quarantined(spoke):
    te.stamp(spoke, when=EPOCH)
    lug = _lug("bad-ts", when=None, certified=True)
    lug["completed_at"] = "sometime last tuesday"
    _write_lug(spoke, "impl", lug)
    assert te.scan(spoke)["counts"][te.CLASS_QUARANTINED] == 1


# --- the UNKNOWN contract -------------------------------------------------


def test_no_epoch_means_everything_quarantined_and_ratio_unknown(spoke):
    _write_lug(spoke, "impl", _lug("x-v1", when=EPOCH, certified=True))
    result = te.scan(spoke)
    assert result["epoch_stamped"] is False
    assert result["trust_ratio"] is None
    assert result["trust_ratio_display"] == "UNKNOWN"
    assert result["counts"][te.CLASS_QUARANTINED] == 1


def test_empty_post_epoch_population_is_unknown_not_zero(spoke):
    te.stamp(spoke, when=EPOCH)
    _write_lug(spoke, "impl", _lug("old-v1", when=EPOCH - timedelta(days=1)))
    result = te.scan(spoke)
    assert result["post_epoch_population"] == 0
    assert result["trust_ratio"] is None, "no post-epoch work rendered as a numeric score"
    assert result["trust_ratio_display"] == "UNKNOWN"


def test_empty_post_epoch_population_is_unknown_not_perfect(spoke):
    """The mirror failure: an empty denominator must not read as 100% either."""
    te.stamp(spoke, when=EPOCH)
    result = te.scan(spoke)
    assert result["trust_ratio_display"] == "UNKNOWN"
    assert "100" not in result["trust_ratio_display"]


def test_quarantined_work_never_enters_the_ratio(spoke):
    te.stamp(spoke, when=EPOCH)
    for i in range(9):
        _write_lug(spoke, "impl", _lug(f"old-{i}", when=EPOCH - timedelta(days=1), certified=True))
    _write_lug(spoke, "impl", _lug("new-1", when=EPOCH + timedelta(hours=1), certified=True))
    result = te.scan(spoke)
    assert result["post_epoch_population"] == 1
    assert result["trust_ratio"] == 1.0, "pre-epoch certifications leaked into the ratio"


# --- exit codes -----------------------------------------------------------


def test_exit_2_when_no_epoch_stamped(spoke):
    assert te._main(["--root", spoke, "status"]) == 2, "unstamped spoke exited 0 (reads as green)"


def test_exit_1_when_findings_present(spoke):
    te.stamp(spoke, when=EPOCH)
    _write_lug(spoke, "impl", _lug("old-v1", when=EPOCH - timedelta(days=1)))
    assert te._main(["--root", spoke, "status"]) == 1


def test_exit_0_only_when_clean(spoke):
    te.stamp(spoke, when=EPOCH)
    _write_lug(spoke, "impl", _lug("new-v1", when=EPOCH + timedelta(hours=1), certified=True))
    assert te._main(["--root", spoke, "status"]) == 0


# --- classify writeback ---------------------------------------------------


def test_classify_dry_run_writes_nothing(spoke):
    te.stamp(spoke, when=EPOCH)
    path = _write_lug(spoke, "impl", _lug("dry-v1", when=EPOCH - timedelta(days=1)))
    before = open(path).read()
    te.classify(spoke, apply=False)
    assert open(path).read() == before


def test_classify_apply_stamps_the_trust_block(spoke):
    te.stamp(spoke, when=EPOCH)
    path = _write_lug(spoke, "impl", _lug("wet-v1", when=EPOCH - timedelta(days=1)))
    result = te.classify(spoke, apply=True)
    assert result["written"] == 1
    lug = json.load(open(path))
    assert lug["trust"]["class"] == te.CLASS_QUARANTINED
    assert lug["trust"]["epoch"] == te._iso(EPOCH)


def test_classify_apply_is_idempotent(spoke):
    te.stamp(spoke, when=EPOCH)
    _write_lug(spoke, "impl", _lug("idem-v1", when=EPOCH - timedelta(days=1)))
    te.classify(spoke, apply=True)
    assert te.classify(spoke, apply=True)["written"] == 0


# --- robustness -----------------------------------------------------------


def test_unreadable_lug_is_reported_not_silently_dropped(spoke):
    te.stamp(spoke, when=EPOCH)
    d = os.path.join(spoke, "WAI-Harness", "spoke", "local", "lugs", "bytype", "impl", "completed")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "broken.json"), "w") as handle:
        handle.write("{not json")
    result = te.scan(spoke)
    assert len(result["unreadable"]) == 1
    assert result["total_completed"] == 0


# --- CLI argument order ---------------------------------------------------


def test_json_flag_accepted_in_both_positions(spoke, capsys):
    te.stamp(spoke, when=EPOCH)
    assert te._main(["--root", spoke, "status", "--json"]) == 0
    after = json.loads(capsys.readouterr().out)
    assert te._main(["--root", spoke, "--json", "status"]) == 0
    before = json.loads(capsys.readouterr().out)
    assert after["trust_epoch"] == before["trust_epoch"] == te._iso(EPOCH)


def test_root_is_not_redefaulted_by_the_subparser(spoke, capsys):
    te.stamp(spoke, when=EPOCH)
    _write_lug(spoke, "impl", _lug("old-v1", when=EPOCH - timedelta(days=1)))
    assert te._main(["--root", spoke, "status", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_completed"] == 1, "read the CWD instead of --root"
