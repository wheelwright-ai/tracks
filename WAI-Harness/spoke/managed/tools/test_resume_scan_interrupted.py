#!/usr/bin/env python3
"""test_resume_scan_interrupted.py — the interrupted list must mean something.

THE BUG (measured on basher 2026-08-01): wai-enter listed 11 INTERRUPTED sessions.
Ten of them had been durably closed by a savepoint, and four of those were
zero-turn launcher shells spawned inside a 12-minute window on 2026-07-29 that had
never done anything at all. Exactly one was real.

Root cause: nothing wrote a terminal record to the track at exit. /wai-closeout
did; wai-exit did not. And `_is_closed` accepted only `closeout` or
`completed=true` — so a session closed by SAVEPOINT stayed interrupted forever,
even though canon (taste work-style-savepoint-must-stand-alone) says: "The operator
OFTEN leaves a session having done only a savepoint and no closeout. A savepoint
must therefore leave the wheel fully durable on its own."

The list was not detecting interruption. It was detecting that the operator does
not run /wai-closeout, which canon says he never has to.

The danger in fixing it is over-correcting into silence, so these tests pin BOTH
directions: the false positives go away AND a genuinely interrupted session still
surfaces. A quiet list that hides real interruption is worse than the noisy one.
"""
import importlib.util
import json
import pathlib

_SPEC = importlib.util.spec_from_file_location(
    "wai_enter_resume_scan", pathlib.Path(__file__).with_name("wai_enter_resume_scan.py"))
rs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rs)


def _mk(base, sid, records, savepoint=None):
    d = base / "sessions" / sid
    d.mkdir(parents=True, exist_ok=True)
    (d / "track.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    if savepoint is not None:
        sp = base / "initiatives" / "savepoints" / "initiative-x"
        sp.mkdir(parents=True, exist_ok=True)
        name = savepoint.get("id", "sp-" + sid)
        (sp / f"{name}.json").write_text(json.dumps({**savepoint, "session_id": sid}))
    return d


def _ids(base):
    return {r["id"] for r in rs.scan_interrupted(str(base))}


TURN = {"event": "turn", "turn": 1}


def test_zero_turn_launcher_shell_is_not_interrupted(tmp_path):
    """The four 2026-07-29 shells: one session_start line, nothing else, no context."""
    _mk(tmp_path, "session-empty", [{"event": "session_start"}])
    assert "session-empty" not in _ids(tmp_path)


def test_session_closed_by_savepoint_is_not_interrupted(tmp_path):
    """Ten of the eleven. Canon: a savepoint leaves the wheel fully durable."""
    _mk(tmp_path, "session-sp", [{"event": "session_start"}, TURN],
        savepoint={"id": "sp-real", "status": "pending", "slug": "did-work"})
    assert "session-sp" not in _ids(tmp_path)


def test_autoeject_savepoint_does_NOT_count_as_a_close(tmp_path):
    """An auto-eject is the harness catching a session that ran out of room — a
    crash cushion, not a deliberate close. That session IS interrupted."""
    _mk(tmp_path, "session-ae", [{"event": "session_start"}, TURN],
        savepoint={"id": "sp-session-ae-autoeject", "status": "auto-eject"})
    assert "session-ae" in _ids(tmp_path), \
        "an auto-eject was accepted as a deliberate close — real interruption hidden"


def test_real_interruption_still_surfaces(tmp_path):
    """Turns done, no savepoint, no closeout — the one true positive of the eleven."""
    _mk(tmp_path, "session-real", [{"event": "session_start"}, TURN, TURN])
    assert "session-real" in _ids(tmp_path)


def test_exit_record_closes_only_when_durable(tmp_path):
    """wai-exit stamps every exit. Accepting all of them would trade a noisy list
    for a lying one, so durable=false must keep surfacing."""
    _mk(tmp_path, "session-exit-ok", [TURN, {"event": "exit", "durable": True}])
    _mk(tmp_path, "session-exit-bad", [TURN, {"event": "exit", "durable": False}])
    ids = _ids(tmp_path)
    assert "session-exit-ok" not in ids, "a durable exit was still listed"
    assert "session-exit-bad" in ids, \
        "a non-durable exit was treated as a clean close — the list now lies"


def test_closeout_still_closes(tmp_path):
    _mk(tmp_path, "session-co", [TURN, {"event": "closeout", "summary": "done"}])
    assert "session-co" not in _ids(tmp_path)


def test_completed_flag_still_closes(tmp_path):
    _mk(tmp_path, "session-cf", [{"event": "turn", "turn": 7, "completed": True}])
    assert "session-cf" not in _ids(tmp_path)
