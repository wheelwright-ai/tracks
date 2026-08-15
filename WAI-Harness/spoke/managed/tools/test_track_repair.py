#!/usr/bin/env python3
"""Fixtures for track_repair.py.

The repair is allowed to rejoin bytes that were always there. It is NOT allowed to
invent content, drop a line it could not parse, or reorder anything. Those three
prohibitions get the most fixtures, because a track repair tool that fabricates is
worse than the damage it fixes.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import track_repair as tr


def _pretty(obj):
    return json.dumps(obj, indent=2).splitlines()


def _turn(n, thinking=True):
    d = {"event": "turn", "turn": n, "user_msg": "x", "action": "y", "outcome": "z"}
    if thinking:
        d["thinking"] = "because x"
    return d


# --- the core repair ------------------------------------------------------


def test_pretty_printed_object_is_rejoined_to_one_line():
    lines = _pretty(_turn(1))
    assert len(lines) > 1
    out, stats = tr.analyse(lines)
    assert len(out) == 1
    assert stats["rejoined"] == 1
    assert json.loads(out[0]) == _turn(1)


def test_repair_preserves_every_field_exactly():
    original = _turn(7)
    original["nested"] = {"a": [1, 2, {"b": "c"}], "unicode": "em dash — here"}
    out, _ = tr.analyse(_pretty(original))
    assert json.loads(out[0]) == original, "repair mutated content"


def test_mixed_good_and_broken_lines(tmp_path):
    lines = [json.dumps(_turn(1))] + _pretty(_turn(2)) + [json.dumps(_turn(3))]
    out, stats = tr.analyse(lines)
    assert len(out) == 3
    assert stats["ok"] == 2 and stats["rejoined"] == 1
    assert [json.loads(l)["turn"] for l in out] == [1, 2, 3], "order changed"


def test_two_consecutive_pretty_blocks_both_rejoin():
    lines = _pretty(_turn(1)) + _pretty(_turn(2))
    out, stats = tr.analyse(lines)
    assert stats["rejoined"] == 2
    assert [json.loads(l)["turn"] for l in out] == [1, 2]


def test_already_clean_track_is_untouched():
    lines = [json.dumps(_turn(i)) for i in range(1, 5)]
    out, stats = tr.analyse(lines)
    assert out == lines
    assert stats["rejoined"] == 0


def test_repair_is_idempotent():
    once, _ = tr.analyse(_pretty(_turn(1)))
    twice, stats = tr.analyse(once)
    assert twice == once
    assert stats["rejoined"] == 0


# --- the three prohibitions -----------------------------------------------


def test_unrepairable_fragment_is_kept_not_dropped():
    """Never lose a line. A dropped line is silent data loss dressed as a fix."""
    lines = ["{ this is not json at all", json.dumps(_turn(2))]
    out, stats = tr.analyse(lines)
    assert stats["unrepairable"] == 1
    assert lines[0] in out, "an unparseable line was dropped"
    assert len(out) == 2


def test_bare_json_string_line_is_not_treated_as_a_turn():
    """mywheel's real damage included an array element that parses as a string."""
    lines = ['"Marked something as MEDIUM"', json.dumps(_turn(2))]
    out, stats = tr.analyse(lines)
    assert stats["unrepairable"] == 1
    assert stats["ok"] == 1


def test_repair_never_adds_a_thinking_field():
    """The judgment layer cannot be repaired -- only the agent ever held it."""
    floor = {"event": "turn", "turn": 1, "assistant_text": "x"}
    out, _ = tr.analyse(_pretty(floor))
    assert "thinking" not in json.loads(out[0])
    assert json.loads(out[0]) == floor


def test_repair_does_not_invent_turns():
    lines = _pretty(_turn(1))
    out, _ = tr.analyse(lines)
    assert len(out) == 1


# --- file-level behaviour -------------------------------------------------


def _write_track(tmp_path, lines, session="session-20260802-0000"):
    d = os.path.join(str(tmp_path), "WAI-Harness", "spoke", "local", "sessions", session)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "track.jsonl")
    with open(p, "w") as handle:
        handle.write("\n".join(lines) + "\n")
    return str(tmp_path), p


def test_dry_run_writes_nothing(tmp_path):
    root, path = _write_track(tmp_path, _pretty(_turn(1)))
    before = open(path).read()
    report = tr.scan(root, apply=False)
    assert report["rejoined"] == 1
    assert open(path).read() == before


def test_apply_writes_and_backs_up(tmp_path):
    root, path = _write_track(tmp_path, _pretty(_turn(1)))
    before = open(path).read()
    tr.scan(root, apply=True)
    assert len(open(path).read().strip().splitlines()) == 1
    assert open(path + ".bak").read() == before, "backup does not match the original"


def test_apply_makes_the_track_parseable_end_to_end(tmp_path):
    lines = [json.dumps(_turn(1))] + _pretty(_turn(2))
    root, path = _write_track(tmp_path, lines)
    tr.scan(root, apply=True)
    parsed = [json.loads(l) for l in open(path).read().splitlines() if l.strip()]
    assert [p["turn"] for p in parsed] == [1, 2]


def test_no_backup_written_when_nothing_changed(tmp_path):
    root, path = _write_track(tmp_path, [json.dumps(_turn(1))])
    tr.scan(root, apply=True)
    assert not os.path.exists(path + ".bak")


def test_blank_lines_are_dropped_not_counted_as_damage(tmp_path):
    out, stats = tr.analyse([json.dumps(_turn(1)), "", "  "])
    assert stats["blank"] == 2 and stats["unrepairable"] == 0
    assert len(out) == 1


# --- exit codes -----------------------------------------------------------


def test_exit_0_when_clean(tmp_path):
    root, _ = _write_track(tmp_path, [json.dumps(_turn(1))])
    assert tr._main(["--root", root, "scan"]) == 0


def test_exit_1_on_repairable_damage_not_yet_applied(tmp_path):
    root, _ = _write_track(tmp_path, _pretty(_turn(1)))
    assert tr._main(["--root", root, "scan"]) == 1


def test_exit_2_on_unrepairable_damage(tmp_path):
    root, _ = _write_track(tmp_path, ["{ not json"])
    assert tr._main(["--root", root, "scan"]) == 2
