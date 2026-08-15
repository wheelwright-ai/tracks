#!/usr/bin/env python3
"""Fixtures for floor_gate.py -- the binding half of the LOW TRUST tenet.

Two properties matter more than the rest and each has several fixtures:
  1. an unestablished floor actually BLOCKS build work (or the tenet is decorative);
  2. it never blocks the work that would establish the floor (or the gate gets
     deleted the first night it bricks a spoke).
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import floor_gate as fg
import trust_epoch as te
import warmup as wu


def _spoke(tmp_path, *, floor=None):
    """floor: None = never warmed, 'established', 'incomplete', 'stale'."""
    root = str(tmp_path)
    base = os.path.join(root, "WAI-Harness", "spoke", "local")
    os.makedirs(base, exist_ok=True)
    with open(os.path.join(base, "WAI-State.json"), "w") as handle:
        json.dump({"wheel": {"name": "s", "goal": "g" * 40, "version": "1.0.0"}}, handle)
    tdir = os.path.join(root, "WAI-Harness", "spoke", "managed", "tools")
    os.makedirs(tdir, exist_ok=True)
    with open(os.path.join(tdir, "test_fixture.py"), "w") as handle:
        handle.write("def test_ok():\n    assert True\n")
    adv = os.path.join(root, "WAI-Harness", "spoke", "advisors", "ozi")
    os.makedirs(adv, exist_ok=True)
    with open(os.path.join(adv, "runs.jsonl"), "w") as handle:
        handle.write('{"ran": true}\n')
    # TIER 0: a spoke with no track can never reach ESTABLISHED, admissions or not.
    # Dated TODAY: the track probe grades the POST-EPOCH window, so a hardcoded
    # date silently ages out of the graded set and the fixture starts testing the
    # epoch instead of the gate.
    _today = datetime.now(timezone.utc).strftime("%Y%m%d")
    sdir = os.path.join(base, "sessions", f"session-{_today}-0000")
    os.makedirs(sdir, exist_ok=True)
    with open(os.path.join(sdir, "track.jsonl"), "w") as handle:
        for t in range(10):
            handle.write(json.dumps({
                "event": "turn", "turn": t + 1, "user_msg": "x", "user_intent": "x",
                "action": "x", "outcome": "x", "thinking": "because x",
                "focus": "x", "phase": "build"}) + "\n")

    if floor is None:
        return root
    te.stamp(root)
    if floor == "incomplete":
        wu.run(root, apply=True, run_tests=False)
        return root
    wu.run(root, apply=True, run_tests=False, admitted=["tests", "history", "advisors"])
    if floor == "stale":
        path = wu.floor_path(root)
        record = json.load(open(path))
        record["expires_at"] = te._iso(te._now() - timedelta(days=1))
        with open(path, "w") as handle:
            json.dump(record, handle)
    return root


def _lug(lug_id, ltype, title="a thing", tags=None):
    return {"id": lug_id, "type": ltype, "title": title, "tags": tags or []}


# --- work classification --------------------------------------------------


@pytest.mark.parametrize("ltype", ["impl", "feature", "epic"])
def test_capability_types_are_build(ltype):
    assert fg.classify_work(_lug("x-v1", ltype, "add a widget")) == fg.BUILD


@pytest.mark.parametrize("ltype", ["fix", "bug", "test", "chore", "audit"])
def test_repair_types_are_floor_work(ltype):
    assert fg.classify_work(_lug("x-v1", ltype)) == fg.FLOOR_WORK


@pytest.mark.parametrize("ltype", ["notation", "signal", "report", "task"])
def test_other_types_are_neutral(ltype):
    assert fg.classify_work(_lug("x-v1", ltype)) == fg.NEUTRAL


@pytest.mark.parametrize("marker", ["trust", "warmup", "floor", "certification",
                                    "assurance", "oracle", "hygiene"])
def test_floor_markers_beat_the_build_type(marker):
    """An impl lug about the gate itself is floor work, or the spoke deadlocks."""
    lug = _lug(f"impl-{marker}-thing-v1", "impl", f"build the {marker} layer")
    assert fg.classify_work(lug) == fg.FLOOR_WORK


def test_floor_marker_in_tags_also_counts():
    lug = _lug("impl-widget-v1", "impl", "add a widget", tags=["trust-floor"])
    assert fg.classify_work(lug) == fg.FLOOR_WORK


# --- the gate actually blocks ---------------------------------------------

def test_build_is_blocked_when_floor_never_established(tmp_path):
    root = _spoke(tmp_path, floor=None)
    ruling = fg.check(root, _lug("impl-widget-v1", "impl"))
    assert ruling["disposition"] == fg.BLOCKED
    assert ruling["floor_verdict"] == wu.UNKNOWN


def test_build_is_blocked_when_floor_incomplete(tmp_path):
    root = _spoke(tmp_path, floor="incomplete")
    ruling = fg.check(root, _lug("impl-widget-v1", "impl"))
    assert ruling["disposition"] == fg.BLOCKED
    assert ruling["floor_verdict"] == wu.INCOMPLETE


def test_build_is_blocked_when_floor_went_stale(tmp_path):
    """The regression that matters: a floor established once, trusted forever."""
    root = _spoke(tmp_path, floor="stale")
    ruling = fg.check(root, _lug("impl-widget-v1", "impl"))
    assert ruling["disposition"] == fg.BLOCKED


def test_build_is_allowed_on_an_established_floor(tmp_path):
    root = _spoke(tmp_path, floor="established")
    ruling = fg.check(root, _lug("impl-widget-v1", "impl"))
    assert ruling["disposition"] == fg.ALLOWED


def test_blocked_ruling_names_a_remedy(tmp_path):
    root = _spoke(tmp_path, floor="incomplete")
    ruling = fg.check(root, _lug("impl-widget-v1", "impl"))
    assert ruling.get("remedy"), "a block with no way out is a brick"


# --- the gate never blocks the path out -----------------------------------


@pytest.mark.parametrize("floor", [None, "incomplete", "stale"])
@pytest.mark.parametrize("lug", [
    _lug("fix-thing-v1", "fix"),
    _lug("impl-warmup-ceremony-v1", "impl", "build the warmup ceremony"),
    _lug("impl-trust-epoch-v1", "impl", "stamp the trust epoch"),
    _lug("notation-x-v1", "notation"),
])
def test_floor_work_is_never_blocked(tmp_path, floor, lug):
    root = _spoke(tmp_path, floor=floor)
    assert fg.check(root, lug)["disposition"] == fg.ALLOWED


# --- override -------------------------------------------------------------


def test_override_requires_a_reason(tmp_path):
    root = _spoke(tmp_path, floor=None)
    with pytest.raises(ValueError):
        fg.override(root, "impl-widget-v1", "")


def test_override_unblocks_only_the_named_lug(tmp_path):
    root = _spoke(tmp_path, floor=None)
    fg.override(root, "impl-widget-v1", "shipping under a deadline, floor next session")
    assert fg.check(root, _lug("impl-widget-v1", "impl"))["disposition"] == fg.ALLOWED
    assert fg.check(root, _lug("impl-other-v1", "impl"))["disposition"] == fg.BLOCKED


def test_override_is_recorded_with_reason_and_floor_state(tmp_path):
    root = _spoke(tmp_path, floor=None)
    fg.override(root, "impl-widget-v1", "deadline")
    rows = fg.read_ledger(root)
    assert len(rows) == 1
    assert rows[0]["reason"] == "deadline"
    assert rows[0]["floor_verdict_at_override"] == wu.UNKNOWN
    assert rows[0]["at"]


def test_overrides_accumulate_and_are_countable(tmp_path):
    root = _spoke(tmp_path, floor=None)
    for i in range(3):
        fg.override(root, f"impl-{i}-v1", "reason")
    assert fg.check_all(root)["override_count"] == 3


# --- check-all and exit codes ---------------------------------------------


def test_check_all_counts_blocked_build_work(tmp_path):
    root = _spoke(tmp_path, floor=None)
    d = os.path.join(root, "WAI-Harness", "spoke", "local", "lugs", "bytype", "impl", "open")
    os.makedirs(d, exist_ok=True)
    for i in range(3):
        with open(os.path.join(d, f"impl-w{i}-v1.json"), "w") as handle:
            json.dump(_lug(f"impl-w{i}-v1", "impl"), handle)
    fdir = os.path.join(root, "WAI-Harness", "spoke", "local", "lugs", "bytype", "fix", "open")
    os.makedirs(fdir, exist_ok=True)
    with open(os.path.join(fdir, "fix-a-v1.json"), "w") as handle:
        json.dump(_lug("fix-a-v1", "fix"), handle)

    out = fg.check_all(root)
    assert out["total"] == 4
    assert out["blocked"] == 3
    assert out["allowed"] == 1
    assert out["by_class"][fg.BUILD] == 3


def test_exit_2_distinguishes_unknown_floor_from_a_plain_block(tmp_path):
    root = _spoke(tmp_path, floor=None)
    path = os.path.join(root, "lug.json")
    with open(path, "w") as handle:
        json.dump(_lug("impl-widget-v1", "impl"), handle)
    assert fg._main(["--root", root, "check", path]) == 2

    root2 = _spoke(tmp_path / "b", floor="incomplete")
    path2 = os.path.join(root2, "lug.json")
    with open(path2, "w") as handle:
        json.dump(_lug("impl-widget-v1", "impl"), handle)
    assert fg._main(["--root", root2, "check", path2]) == 1


def test_exit_0_when_allowed(tmp_path):
    root = _spoke(tmp_path, floor="established")
    path = os.path.join(root, "lug.json")
    with open(path, "w") as handle:
        json.dump(_lug("impl-widget-v1", "impl"), handle)
    assert fg._main(["--root", root, "check", path]) == 0


def test_malformed_lug_files_are_skipped_not_fatal(tmp_path):
    root = _spoke(tmp_path, floor=None)
    d = os.path.join(root, "WAI-Harness", "spoke", "local", "lugs", "bytype", "impl", "open")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "broken.json"), "w") as handle:
        handle.write("{nope")
    assert fg.check_all(root)["total"] == 0


# --- CLI argument order ---------------------------------------------------


def test_json_flag_accepted_after_the_subcommand(tmp_path, capsys):
    root = _spoke(tmp_path, floor=None)
    assert fg._main(["--root", root, "check-all", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["floor_verdict"] == wu.UNKNOWN


def test_root_is_not_redefaulted_by_the_subparser(tmp_path, capsys):
    root = _spoke(tmp_path, floor="established")
    assert fg._main(["--root", root, "check-all", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["cleared_to_build"] is True
