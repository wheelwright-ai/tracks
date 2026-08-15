#!/usr/bin/env python3
"""Fixtures for advisor_scheduler.py -- the thing that fires the recorder.

An unattended job that can spend real money is a different kind of object from one
that cannot, so the fixtures here are weighted toward what it REFUSES: agent-backed
advisors by default, anything unrunnable, anything past the cap or the budget. And
every refusal must be reported, because a scheduler that silently declines work is
indistinguishable from one with nothing to do -- and the second reads as healthy.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import advisor_scheduler as sch
import oracle_liveness as ol
import run_advisor as ra


def _spoke(tmp_path):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "WAI-Harness", "spoke", "advisors"), exist_ok=True)
    return root


def _advisor(root, name, *, cadence="daily", ran_days_ago=None, kind=None,
             tool="t.py", make_tool=True, status=None, exit_code=0):
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", name)
    os.makedirs(d, exist_ok=True)
    contract = {}
    if kind:
        contract["kind"] = kind
    if status:
        contract["status"] = status
    if contract:
        with open(os.path.join(d, "contract.json"), "w") as h:
            json.dump(contract, h)
    if make_tool and tool:
        with open(os.path.join(root, tool), "w") as h:
            h.write(f"import sys\nprint('ran')\nsys.exit({exit_code})\n")
    # keep scan_state saying never-run unless told otherwise
    with open(os.path.join(d, "scan_state.json"), "w") as h:
        json.dump({"advisor_id": name, "last_run_at": None, "stats": {"runs": 0}}, h)

    idx_path = os.path.join(root, "WAI-Harness", "spoke", "advisors",
                            "schedule-index.json")
    idx = {"advisors": []}
    if os.path.exists(idx_path):
        idx = json.load(open(idx_path))
    row = {"advisor_id": name}
    if cadence:
        row["run_cadence"] = cadence
    if tool:
        row["tool"] = tool
    idx["advisors"].append(row)
    with open(idx_path, "w") as h:
        json.dump(idx, h)
    return root


def _runs(root, name):
    p = os.path.join(root, "WAI-Harness", "spoke", "advisors", name, "runs.jsonl")
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


# --- what is due ----------------------------------------------------------


def test_never_run_tool_backed_advisor_is_runnable(tmp_path):
    root = _advisor(_spoke(tmp_path), "a", kind="deterministic-tool-backed")
    plan = sch.due(root)
    assert [r["advisor"] for r in plan["runnable"]] == ["a"]


def test_agent_backed_advisor_is_declined_by_default(tmp_path):
    """Agent-backed advisors cost tokens; an unattended job must not spend by default."""
    root = _advisor(_spoke(tmp_path), "a", kind="advisor")
    plan = sch.due(root)
    assert plan["runnable"] == []
    assert plan["declined"][0]["advisor"] == "a"
    assert "opt in" in plan["declined"][0]["reason"]


def test_include_agent_widens_the_net(tmp_path):
    root = _advisor(_spoke(tmp_path), "a", kind="advisor")
    plan = sch.due(root, include_agent=True)
    assert [r["advisor"] for r in plan["runnable"]] == ["a"]


def test_advisor_with_no_command_needs_a_human(tmp_path):
    root = _advisor(_spoke(tmp_path), "a", kind="deterministic-tool-backed",
                    tool=None)
    plan = sch.due(root)
    assert plan["runnable"] == []
    assert plan["needs_human"][0]["advisor"] == "a"


def test_retired_advisor_is_never_due(tmp_path):
    root = _advisor(_spoke(tmp_path), "a", kind="deterministic-tool-backed",
                    status="superseded")
    plan = sch.due(root)
    assert plan["runnable"] == [] and plan["needs_human"] == []


def test_live_advisor_is_not_due(tmp_path):
    root = _spoke(tmp_path)
    _advisor(root, "a", kind="deterministic-tool-backed", cadence="weekly")
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", "a")
    with open(os.path.join(d, "runs.jsonl"), "w") as h:
        h.write('{"ran": true}\n')
    with open(os.path.join(d, "scan_state.json"), "w") as h:
        json.dump({"stats": {"runs": 1}, "last_run_at": ra.te._iso(ra.te._now())}, h)
    assert sch.due(root)["runnable"] == []


def test_worst_state_is_offered_first(tmp_path):
    root = _spoke(tmp_path)
    _advisor(root, "z_never", kind="deterministic-tool-backed", cadence="daily")
    _advisor(root, "a_late", kind="deterministic-tool-backed", cadence="weekly",
             tool="t2.py")
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", "a_late")
    with open(os.path.join(d, "runs.jsonl"), "w") as h:
        h.write('{"ran": true}\n')
    with open(os.path.join(d, "scan_state.json"), "w") as h:
        json.dump({"stats": {"runs": 1},
                   "last_run_at": "2026-07-20T00:00:00+00:00"}, h)
    order = [r["advisor"] for r in sch.due(root)["runnable"]]
    assert order[0] == "z_never"


# --- tick: caps and budgets -----------------------------------------------


def test_tick_runs_a_due_advisor_and_records_it(tmp_path):
    root = _advisor(_spoke(tmp_path), "a", kind="deterministic-tool-backed")
    result = sch.tick(root)
    assert [r["advisor"] for r in result["ran"]] == ["a"]
    assert len(_runs(root, "a")) == 1


def test_max_cap_is_honoured_and_the_rest_reported(tmp_path):
    root = _spoke(tmp_path)
    for i in range(4):
        _advisor(root, f"a{i}", kind="deterministic-tool-backed", tool=f"t{i}.py")
    result = sch.tick(root, max_runs=2)
    assert len(result["ran"]) == 2
    assert len(result["skipped"]) == 2
    assert all("max" in s["why"] for s in result["skipped"])


def test_budget_exhaustion_is_reported_not_silent(tmp_path):
    root = _spoke(tmp_path)
    for i in range(3):
        _advisor(root, f"a{i}", kind="deterministic-tool-backed", tool=f"t{i}.py")
    result = sch.tick(root, budget_seconds=0)
    assert result["ran"] == []
    assert len(result["skipped"]) == 3
    assert all("budget" in s["why"] for s in result["skipped"])


def test_dry_run_records_nothing(tmp_path):
    root = _advisor(_spoke(tmp_path), "a", kind="deterministic-tool-backed")
    result = sch.tick(root, dry_run=True)
    assert result["ran"] == []
    assert _runs(root, "a") == []
    assert result["skipped"][0]["why"] == "dry-run"


def test_nothing_due_is_an_explicit_statement(tmp_path):
    root = _spoke(tmp_path)
    result = sch.tick(root)
    assert result["ran"] == [] and result["skipped"] == []
    assert "nothing due" in sch.render_tick(result)


# --- every refusal is visible ---------------------------------------------


def test_declined_advisors_appear_in_the_tick_output(tmp_path):
    """A scheduler that silently declines looks like one with nothing to do."""
    root = _advisor(_spoke(tmp_path), "a", kind="advisor")
    result = sch.tick(root)
    assert result["declined"][0]["advisor"] == "a"
    assert "declined" in sch.render_tick(result)


def test_needs_human_appears_in_the_tick_output(tmp_path):
    root = _advisor(_spoke(tmp_path), "a", kind="deterministic-tool-backed",
                    tool=None)
    result = sch.tick(root)
    assert result["needs_human"][0]["advisor"] == "a"
    assert "NEEDS HUMAN" in sch.render_tick(result)


# --- exit codes -----------------------------------------------------------


def test_exit_0_when_nothing_due(tmp_path):
    assert sch._main(["--root", _spoke(tmp_path), "tick"]) == 0


def test_exit_1_when_a_run_fails(tmp_path):
    root = _advisor(_spoke(tmp_path), "a", kind="deterministic-tool-backed",
                    exit_code=3)
    assert sch._main(["--root", root, "tick"]) == 1


def test_exit_2_when_something_needs_a_human(tmp_path):
    root = _advisor(_spoke(tmp_path), "a", kind="deterministic-tool-backed",
                    tool=None)
    assert sch._main(["--root", root, "tick"]) == 2


def test_a_failing_run_still_clears_NEVER(tmp_path):
    """The inversion holds through the scheduler too: red beats silent."""
    root = _advisor(_spoke(tmp_path), "a", kind="deterministic-tool-backed",
                    exit_code=1)
    sch.tick(root)
    state = {r["advisor"]: r for r in ol.check(root)["results"]}["a"]["state"]
    assert state == ol.LIVE


# --- ordering: "is it mine to run?" before "can I run it?" ----------------


def test_agent_advisor_with_no_command_is_declined_not_escalated(tmp_path):
    """The first live dry-run raised nine of these as NEEDS HUMAN. Nine false
    alarms beside one true one is how the true one stops being read."""
    root = _advisor(_spoke(tmp_path), "a", kind="advisor", tool=None)
    plan = sch.due(root)
    assert plan["needs_human"] == []
    assert plan["declined"][0]["advisor"] == "a"


def test_tool_backed_with_no_command_is_still_escalated(tmp_path):
    root = _advisor(_spoke(tmp_path), "a", kind="deterministic-tool-backed", tool=None)
    plan = sch.due(root)
    assert plan["needs_human"][0]["advisor"] == "a"
    assert plan["declined"] == []


def test_include_agent_does_not_turn_missing_commands_into_human_work(tmp_path):
    root = _advisor(_spoke(tmp_path), "a", kind="advisor", tool=None)
    plan = sch.due(root, include_agent=True)
    assert plan["needs_human"] == []
    assert plan["declined"][0]["advisor"] == "a"
    assert "not a cron job" in plan["declined"][0]["reason"]


def test_one_true_alarm_is_not_buried(tmp_path):
    root = _spoke(tmp_path)
    for i in range(5):
        _advisor(root, f"agent{i}", kind="advisor", tool=None)
    _advisor(root, "real", kind="deterministic-tool-backed", tool=None)
    plan = sch.due(root)
    assert [h["advisor"] for h in plan["needs_human"]] == ["real"]
