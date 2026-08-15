#!/usr/bin/env python3
"""test_track_judgment_coverage.py — the measurement must not be silent or brittle.

This instrument exists because a fleet-wide decay ran for months with no error, no
warning, and no brief line: roughly two thirds of every spoke's turns carry facts but
no reasoning. It was found only because an operator noticed a missing statusline.

So the tests weigh two things. It must COUNT correctly (a wrong number is worse than
none — it would launder the decay as healthy). And it must never die on bad input: a
reader that crashes on one malformed line reports nothing about the other thousand,
which is how a measurement becomes another silence.
"""
import importlib.util
import json
import pathlib

_SPEC = importlib.util.spec_from_file_location(
    "tjc", pathlib.Path(__file__).with_name("track_judgment_coverage.py"))
tjc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(tjc)


def _track(tmp_path, sid, lines):
    d = tmp_path / "sessions" / sid
    d.mkdir(parents=True, exist_ok=True)
    (d / "track.jsonl").write_text("".join(lines))
    return str(d / "track.jsonl")


RICH = json.dumps({"event": "turn", "turn": 1, "thinking": "why I did it"}) + "\n"
FLOOR = json.dumps({"event": "turn", "turn": 2, "synthesized": True,
                    "user_intent": "do a thing", "assistant_text": "did it"}) + "\n"
NOTATURN = json.dumps({"event": "savepoint_created"}) + "\n"


def test_counts_rich_versus_floor(tmp_path):
    p = _track(tmp_path, "session-a", [RICH, FLOOR, FLOOR, NOTATURN])
    s = tjc.scan_session(p)
    assert (s["rich"], s["floor"], s["turns"], s["pct"]) == (1, 2, 3, 33)


def test_non_turn_events_are_not_counted(tmp_path):
    p = _track(tmp_path, "session-b", [NOTATURN, NOTATURN])
    assert tjc.scan_session(p)["turns"] == 0


def test_a_bare_string_line_is_counted_not_fatal(tmp_path):
    """REAL SHAPE: mywheel session-20260722-0824 has a track line that is a bare JSON
    string, not an object. An earlier ad-hoc scan died on it with AttributeError and
    reported nothing for that whole spoke."""
    p = _track(tmp_path, "session-c", [RICH, json.dumps("i am a string") + "\n", FLOOR])
    s = tjc.scan_session(p)
    assert s["malformed"] == 1
    assert s["turns"] == 2, "one bad line must not hide the good ones"


def test_unparseable_line_is_counted_not_fatal(tmp_path):
    p = _track(tmp_path, "session-d", [RICH, "{not json\n", FLOOR])
    s = tjc.scan_session(p)
    assert s["malformed"] == 1 and s["turns"] == 2


def test_missing_track_returns_empty_rather_than_raising(tmp_path):
    s = tjc.scan_session(str(tmp_path / "nope" / "track.jsonl"))
    assert s["turns"] == 0 and s["malformed"] == 0


def test_empty_thinking_string_counts_as_floor(tmp_path):
    """An entry that HAS the key but left it blank explains nothing — it is floor.
    Presence-of-key would have inflated the number and hidden the decay."""
    blank = json.dumps({"event": "turn", "turn": 3, "thinking": ""}) + "\n"
    assert tjc.scan_session(_track(tmp_path, "session-e", [blank]))["rich"] == 0


def test_spoke_summary_flags_sessions_below_half(tmp_path):
    _track(tmp_path, "session-good", [RICH, RICH, FLOOR])
    _track(tmp_path, "session-bad", [RICH, FLOOR, FLOOR, FLOOR])
    sess = tjc.scan_spoke(str(tmp_path))
    summ = tjc.summarise(sess)
    assert summ["sessions"] == 2 and summ["turns"] == 7 and summ["rich"] == 3
    assert summ["sessions_below_50pct"] == ["session-bad"]


def test_render_names_the_consequence_not_just_a_number(tmp_path):
    _track(tmp_path, "session-f", [RICH, FLOOR, FLOOR])
    sess = tjc.scan_spoke(str(tmp_path))
    out = tjc.render(sess, tjc.summarise(sess))
    assert "floor-only" in out
    assert "lens" in out and "resident" in out, \
        "a bare percentage does not tell the reader what was lost"
