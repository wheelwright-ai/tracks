#!/usr/bin/env python3
"""Fixtures for oracle_liveness.py -- the watcher of watchers.

The central property under test is the INVERSION: silence must outrank failure.
Several fixtures exist only to stop a future edit from quietly folding NEVER or
UNSCHEDULED into the healthy bucket, which is precisely how proofer stayed
invisible for its entire existence.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import oracle_liveness as ol


NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)


def _spoke(tmp_path, advisors):
    """advisors: {name: {"cadence": str|None, "ran_days_ago": int|None}}"""
    root = str(tmp_path)
    adir = os.path.join(root, "WAI-Harness", "spoke", "advisors")
    os.makedirs(adir, exist_ok=True)
    rows = []
    for name, spec in advisors.items():
        os.makedirs(os.path.join(adir, name), exist_ok=True)
        row = {"advisor_id": name}
        if spec.get("cadence"):
            row["run_cadence"] = spec["cadence"]
        ago = spec.get("ran_days_ago")
        if ago is not None:
            row["last_run_at"] = (NOW - timedelta(days=ago)).isoformat()
        rows.append(row)
    with open(os.path.join(adir, "schedule-index.json"), "w") as handle:
        json.dump({"advisors": rows}, handle)
    return root


def _state(root, name, grace=ol.DEFAULT_GRACE):
    report = ol.check(root, grace=grace, now=NOW)
    return {r["advisor"]: r for r in report["results"]}[name]["state"]


# --- the four states ------------------------------------------------------


def test_never_run_is_NEVER(tmp_path):
    root = _spoke(tmp_path, {"proofer": {"cadence": "daily", "ran_days_ago": None}})
    assert _state(root, "proofer") == ol.NEVER


def test_recent_run_is_LIVE(tmp_path):
    root = _spoke(tmp_path, {"ozi": {"cadence": "weekly", "ran_days_ago": 2}})
    assert _state(root, "ozi") == ol.LIVE


def test_slightly_overdue_is_LATE(tmp_path):
    root = _spoke(tmp_path, {"ozi": {"cadence": "weekly", "ran_days_ago": 9}})
    assert _state(root, "ozi") == ol.LATE


def test_long_overdue_is_SILENT(tmp_path):
    root = _spoke(tmp_path, {"ozi": {"cadence": "weekly", "ran_days_ago": 60}})
    assert _state(root, "ozi") == ol.SILENT


def test_grace_boundary_is_where_LATE_becomes_SILENT(tmp_path):
    inside = _spoke(tmp_path / "a", {"o": {"cadence": "weekly", "ran_days_ago": 20}})
    outside = _spoke(tmp_path / "b", {"o": {"cadence": "weekly", "ran_days_ago": 22}})
    assert _state(inside, "o") == ol.LATE
    assert _state(outside, "o") == ol.SILENT


# --- the inversion --------------------------------------------------------


def test_never_outranks_silent_which_outranks_late(tmp_path):
    root = _spoke(tmp_path, {
        "a_late": {"cadence": "weekly", "ran_days_ago": 9},
        "b_silent": {"cadence": "weekly", "ran_days_ago": 60},
        "c_never": {"cadence": "weekly", "ran_days_ago": None},
        "d_live": {"cadence": "weekly", "ran_days_ago": 1},
    })
    order = [r["advisor"] for r in ol.check(root, now=NOW)["results"]]
    assert order == ["c_never", "b_silent", "a_late", "d_live"]


def test_exit_2_is_reserved_for_the_silent_states(tmp_path):
    live = _spoke(tmp_path / "a", {"o": {"cadence": "weekly", "ran_days_ago": 1}})
    late = _spoke(tmp_path / "b", {"o": {"cadence": "weekly", "ran_days_ago": 9}})
    never = _spoke(tmp_path / "c", {"o": {"cadence": "weekly", "ran_days_ago": None}})
    silent = _spoke(tmp_path / "d", {"o": {"cadence": "weekly", "ran_days_ago": 60}})
    assert ol.exit_code(ol.check(live, now=NOW)) == 0
    assert ol.exit_code(ol.check(late, now=NOW)) == 1
    assert ol.exit_code(ol.check(never, now=NOW)) == 2
    assert ol.exit_code(ol.check(silent, now=NOW)) == 2


def test_worst_line_names_the_worst_never_an_average(tmp_path):
    root = _spoke(tmp_path, {
        "proofer": {"cadence": "daily", "ran_days_ago": None},
        **{f"ok{i}": {"cadence": "weekly", "ran_days_ago": 1} for i in range(9)},
    })
    line = ol.worst_line(ol.check(root, now=NOW))
    assert "proofer" in line
    assert "NEVER" in line
    assert "90%" not in line and "healthy" not in line.lower()


# --- no silent upgrades to healthy ----------------------------------------


def test_no_declared_cadence_is_UNSCHEDULED_not_LIVE(tmp_path):
    """Treating 'no cadence' as fine is exactly how proofer stayed invisible."""
    root = _spoke(tmp_path, {"x": {"cadence": None, "ran_days_ago": 400}})
    assert _state(root, "x") == ol.UNSCHEDULED


def test_unscheduled_is_not_counted_in_live(tmp_path):
    root = _spoke(tmp_path, {"x": {"cadence": None, "ran_days_ago": 400}})
    counts = ol.check(root, now=NOW)["counts"]
    assert counts[ol.LIVE] == 0
    assert counts[ol.UNSCHEDULED] == 1


def test_config_files_are_not_evidence_of_running(tmp_path):
    """contract.json proves someone configured the advisor, nothing more."""
    root = _spoke(tmp_path, {"x": {"cadence": "daily", "ran_days_ago": None}})
    with open(os.path.join(root, "WAI-Harness", "spoke", "advisors", "x",
                           "contract.json"), "w") as handle:
        handle.write('{"configured": true}\n')
    assert _state(root, "x") == ol.NEVER


def test_empty_output_file_is_not_evidence_of_running(tmp_path):
    root = _spoke(tmp_path, {"x": {"cadence": "daily", "ran_days_ago": None}})
    open(os.path.join(root, "WAI-Harness", "spoke", "advisors", "x",
                      "runs.jsonl"), "w").close()
    assert _state(root, "x") == ol.NEVER


def test_real_output_on_disk_counts_even_without_an_index_entry(tmp_path):
    root = _spoke(tmp_path, {"x": {"cadence": "daily", "ran_days_ago": None}})
    with open(os.path.join(root, "WAI-Harness", "spoke", "advisors", "x",
                           "runs.jsonl"), "w") as handle:
        handle.write('{"ran": true}\n')
    assert _state(root, "x") != ol.NEVER


def test_advisor_dir_absent_from_the_index_is_still_checked(tmp_path):
    """An advisor that exists on disk but not in the index must not vanish."""
    root = _spoke(tmp_path, {"known": {"cadence": "weekly", "ran_days_ago": 1}})
    os.makedirs(os.path.join(root, "WAI-Harness", "spoke", "advisors", "ghost"))
    names = [r["advisor"] for r in ol.check(root, now=NOW)["results"]]
    assert "ghost" in names


# --- cadence parsing ------------------------------------------------------


@pytest.mark.parametrize("cadence,days", [
    ("daily", 1), ("nightly", 1), ("weekly", 7), ("monthly", 30),
    ("biweekly", 14), ("quarterly", 90),
])
def test_named_cadences_parse(cadence, days):
    assert ol.cadence_days({"run_cadence": cadence}) == days


def test_numeric_cadence_parses():
    assert ol.cadence_days({"run_cadence": "every 5 days"}) == 5


def test_unknown_cadence_is_none_not_a_default(tmp_path):
    assert ol.cadence_days({"run_cadence": "when convenient"}) is None


# --- robustness -----------------------------------------------------------


def test_missing_schedule_index_does_not_crash(tmp_path):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "WAI-Harness", "spoke", "advisors"), exist_ok=True)
    assert ol.check(root, now=NOW)["total"] == 0


def test_corrupt_schedule_index_does_not_crash(tmp_path):
    root = _spoke(tmp_path, {"x": {"cadence": "daily", "ran_days_ago": 1}})
    with open(os.path.join(root, "WAI-Harness", "spoke", "advisors",
                           "schedule-index.json"), "w") as handle:
        handle.write("{broken")
    # The directory scan still finds the advisor; it just has no index row.
    assert "x" in [r["advisor"] for r in ol.check(root, now=NOW)["results"]]


def test_cli_json_in_both_positions(tmp_path, capsys):
    """--json before or after the verb must behave identically.

    A TIME BOMB lived here until 2026-08-08. The fixture dates last_run relative to the
    module's frozen NOW (2026-08-02), but `_main` reads the REAL clock, so the advisor drifted
    past its weekly cadence six days after that constant was written and the exit code flipped
    to 1. The test then failed for a reason that had nothing to do with what it was testing,
    and it blocked a push on unrelated work.

    The invariant this test actually owns is FLAG POSITION, so it asserts the two invocations
    AGREE rather than asserting a specific verdict. Whether the advisor is late is a different
    test's job, and that one injects `now` instead of reading the wall clock."""
    root = _spoke(tmp_path, {"o": {"cadence": "weekly", "ran_days_ago": 1}})
    after_rc = ol._main(["--root", root, "check", "--json"])
    after = json.loads(capsys.readouterr().out)
    before_rc = ol._main(["--root", root, "--json", "check"])
    before = json.loads(capsys.readouterr().out)
    assert after_rc == before_rc, "flag position changed the exit code"
    assert after["total"] == before["total"] == 1
    assert after["counts"] == before["counts"]


# --- explicit self-report beats mtime inference ---------------------------


def test_state_file_saying_runs_zero_forces_NEVER(tmp_path):
    """The live regression of 2026-08-02: proofer read SILENT (35d) because the
    mtime of the very state file declaring runs: 0 looked like activity."""
    root = _spoke(tmp_path, {"proofer": {"cadence": "daily", "ran_days_ago": None}})
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", "proofer")
    with open(os.path.join(d, "scan_state.json"), "w") as handle:
        json.dump({"advisor_id": "proofer", "last_run_at": None,
                   "stats": {"runs": 0}}, handle)
    with open(os.path.join(d, "contract.json"), "w") as handle:
        handle.write('{"configured": true}\n')
    assert _state(root, "proofer") == ol.NEVER


def test_explicit_never_overrides_a_declared_last_run_at(tmp_path):
    """Two sources disagreeing about health: take the less trusting one."""
    root = _spoke(tmp_path, {"p": {"cadence": "daily", "ran_days_ago": 1}})
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", "p")
    with open(os.path.join(d, "scan_state.json"), "w") as handle:
        json.dump({"last_run_at": None, "stats": {"runs": 0}}, handle)
    assert _state(root, "p") == ol.NEVER


def test_state_file_with_real_runs_does_not_force_NEVER(tmp_path):
    root = _spoke(tmp_path, {"p": {"cadence": "weekly", "ran_days_ago": 1}})
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", "p")
    with open(os.path.join(d, "scan_state.json"), "w") as handle:
        json.dump({"last_run_at": "2026-08-01T00:00:00Z", "stats": {"runs": 4}}, handle)
    assert _state(root, "p") == ol.LIVE


def test_state_file_mtime_alone_is_not_evidence_of_running(tmp_path):
    root = _spoke(tmp_path, {"p": {"cadence": "daily", "ran_days_ago": None}})
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", "p")
    with open(os.path.join(d, "scan_state.json"), "w") as handle:
        json.dump({"advisor_id": "p"}, handle)   # no runs key at all
    assert _state(root, "p") == ol.NEVER


# --- contract is authoritative over the index -----------------------------


def _contract(root, name, **fields):
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "contract.json"), "w") as handle:
        json.dump(fields, handle)


def test_contract_cadence_is_used_when_the_index_has_none(tmp_path):
    """16 of 34 advisors read UNSCHEDULED while their contracts declared a cadence."""
    root = _spoke(tmp_path, {"a": {"cadence": None, "ran_days_ago": 2}})
    _contract(root, "a", run_cadence="weekly")
    assert _state(root, "a") == ol.LIVE


def test_contract_cadence_can_make_an_advisor_late(tmp_path):
    root = _spoke(tmp_path, {"a": {"cadence": None, "ran_days_ago": 9}})
    _contract(root, "a", run_cadence="weekly")
    assert _state(root, "a") == ol.LATE


def test_index_cadence_wins_when_present(tmp_path):
    root = _spoke(tmp_path, {"a": {"cadence": "monthly", "ran_days_ago": 9}})
    _contract(root, "a", run_cadence="weekly")
    assert _state(root, "a") == ol.LIVE


def test_no_cadence_anywhere_is_still_unscheduled(tmp_path):
    root = _spoke(tmp_path, {"a": {"cadence": None, "ran_days_ago": 2}})
    _contract(root, "a", kind="advisor")
    assert _state(root, "a") == ol.UNSCHEDULED


def test_unreadable_contract_does_not_crash(tmp_path):
    root = _spoke(tmp_path, {"a": {"cadence": None, "ran_days_ago": 2}})
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", "a")
    with open(os.path.join(d, "contract.json"), "w") as handle:
        handle.write("{broken")
    assert _state(root, "a") == ol.UNSCHEDULED


# --- event-driven is its own answer, not a pass ---------------------------


@pytest.mark.parametrize("cad", ["on-event", "on-demand", "closeout",
                                 "session-start", "per AP round", "on_event"])
def test_trigger_cadences_are_event_driven(tmp_path, cad):
    root = _spoke(tmp_path / cad.replace(" ", "_"),
                  {"a": {"cadence": None, "ran_days_ago": 400}})
    _contract(root, "a", run_cadence=cad)
    assert _state(root, "a") == ol.EVENT_DRIVEN


def test_event_driven_is_not_counted_as_live(tmp_path):
    root = _spoke(tmp_path, {"a": {"cadence": None, "ran_days_ago": 400}})
    _contract(root, "a", run_cadence="on-event")
    counts = ol.check(root, now=NOW)["counts"]
    assert counts[ol.LIVE] == 0
    assert counts[ol.EVENT_DRIVEN] == 1


def test_event_driven_names_the_missing_check(tmp_path):
    """An honest gap must say what would close it, not just decline to judge."""
    root = _spoke(tmp_path, {"a": {"cadence": None, "ran_days_ago": 400}})
    _contract(root, "a", run_cadence="on-event")
    note = {r["advisor"]: r for r in ol.check(root, now=NOW)["results"]}["a"]["note"]
    assert "trigger fired" in note and "no check for that exists" in note


def test_event_driven_never_run_is_still_NEVER(tmp_path):
    """Event-driven excuses the clock, never the total absence of output."""
    root = _spoke(tmp_path, {"a": {"cadence": None, "ran_days_ago": None}})
    _contract(root, "a", run_cadence="on-event")
    assert _state(root, "a") == ol.NEVER


def test_compound_cadence_picks_the_interval(tmp_path):
    """proofer declares 'daily + on-close'. The interval half must still bind."""
    root = _spoke(tmp_path, {"a": {"cadence": None, "ran_days_ago": 30}})
    _contract(root, "a", run_cadence="daily")
    assert _state(root, "a") == ol.SILENT


# --- UNRUNNABLE: registered, scheduled, and impossible ---------------------


def test_command_pointing_at_a_missing_file_is_UNRUNNABLE(tmp_path):
    """historian_archaeology, 2026-08-02: monthly, registered, and its
    dispatch_command named a v3 path that did not exist. Every instrument called
    it merely overdue for as long as it had existed."""
    root = _spoke(tmp_path, {"a": {"cadence": "monthly", "ran_days_ago": 2}})
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors")
    idx = json.load(open(os.path.join(d, "schedule-index.json")))
    idx["advisors"][0]["dispatch_command"] = "python3 tools/gone.py --submit"
    json.dump(idx, open(os.path.join(d, "schedule-index.json"), "w"))
    assert _state(root, "a") == ol.UNRUNNABLE


def test_unrunnable_outranks_never(tmp_path):
    """A never-run oracle might run tomorrow; this one cannot run at all."""
    root = _spoke(tmp_path, {
        "a_never": {"cadence": "daily", "ran_days_ago": None},
        "b_broken": {"cadence": "daily", "ran_days_ago": 1},
    })
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors")
    idx = json.load(open(os.path.join(d, "schedule-index.json")))
    for r in idx["advisors"]:
        if r["advisor_id"] == "b_broken":
            r["tool"] = "tools/does_not_exist.py"
    json.dump(idx, open(os.path.join(d, "schedule-index.json"), "w"))
    order = [r["advisor"] for r in ol.check(root, now=NOW)["results"]]
    assert order[0] == "b_broken"


def test_unrunnable_counts_toward_the_loud_exit_code(tmp_path):
    root = _spoke(tmp_path, {"a": {"cadence": "daily", "ran_days_ago": 1}})
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors")
    idx = json.load(open(os.path.join(d, "schedule-index.json")))
    idx["advisors"][0]["tool"] = "tools/missing.py"
    json.dump(idx, open(os.path.join(d, "schedule-index.json"), "w"))
    report = ol.check(root, now=NOW)
    assert ol.exit_code(report) == 2
    assert "UNRUNNABLE" in ol.worst_line(report)


def test_a_resolvable_command_is_not_unrunnable(tmp_path):
    root = _spoke(tmp_path, {"a": {"cadence": "weekly", "ran_days_ago": 1}})
    real = os.path.join(root, "real_tool.py")
    open(real, "w").close()
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors")
    idx = json.load(open(os.path.join(d, "schedule-index.json")))
    idx["advisors"][0]["tool"] = "real_tool.py"
    json.dump(idx, open(os.path.join(d, "schedule-index.json"), "w"))
    assert _state(root, "a") == ol.LIVE


def test_non_python_commands_are_not_judged_unrunnable(tmp_path):
    """The check only rules on .py paths it can resolve; it does not guess at shell."""
    root = _spoke(tmp_path, {"a": {"cadence": "weekly", "ran_days_ago": 1}})
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors")
    idx = json.load(open(os.path.join(d, "schedule-index.json")))
    idx["advisors"][0]["command"] = "make audit && echo done"
    json.dump(idx, open(os.path.join(d, "schedule-index.json"), "w"))
    assert _state(root, "a") == ol.LIVE


# --- retired advisors are not alarms --------------------------------------


def test_superseded_advisor_is_RETIRED_not_NEVER(tmp_path):
    """qa_assurance was superseded 2026-06-29 and still counted as NEVER five weeks
    later -- a permanent false positive, and false positives teach a reader to
    discount the real ones."""
    root = _spoke(tmp_path, {"a": {"cadence": "daily", "ran_days_ago": None}})
    _contract(root, "a", status="superseded", superseded_by="release_engineer")
    assert _state(root, "a") == ol.RETIRED


@pytest.mark.parametrize("status", ["superseded", "retired", "archived", "SUPERSEDED"])
def test_all_retirement_words_are_honoured(tmp_path, status):
    root = _spoke(tmp_path / status, {"a": {"cadence": "daily", "ran_days_ago": None}})
    _contract(root, "a", status=status)
    assert _state(root, "a") == ol.RETIRED


def test_retired_is_excluded_from_the_active_total(tmp_path):
    root = _spoke(tmp_path, {
        "live": {"cadence": "weekly", "ran_days_ago": 1},
        "dead": {"cadence": "daily", "ran_days_ago": None},
    })
    _contract(root, "dead", status="superseded")
    report = ol.check(root, now=NOW)
    assert report["total"] == 2
    assert report["active_total"] == 1
    assert report["counts"][ol.RETIRED] == 1
    assert report["silent_total"] == 0, "a retired advisor raised a silence alarm"


def test_retired_does_not_affect_the_exit_code(tmp_path):
    root = _spoke(tmp_path, {"a": {"cadence": "daily", "ran_days_ago": None}})
    _contract(root, "a", status="superseded")
    assert ol.exit_code(ol.check(root, now=NOW)) == 0


def test_active_status_is_judged_normally(tmp_path):
    root = _spoke(tmp_path, {"a": {"cadence": "daily", "ran_days_ago": None}})
    _contract(root, "a", status="active")
    assert _state(root, "a") == ol.NEVER


# --- tool-backed with no tool ---------------------------------------------


def test_tool_backed_advisor_naming_no_tool_is_UNRUNNABLE(tmp_path):
    root = _spoke(tmp_path, {"a": {"cadence": "daily", "ran_days_ago": None}})
    _contract(root, "a", kind="deterministic-tool-backed")
    assert _state(root, "a") == ol.UNRUNNABLE


def test_agent_advisor_with_no_tool_is_not_unrunnable(tmp_path):
    """Most advisors are agent-dispatched; flagging them all would be a false alarm
    shipped in the name of rigour."""
    root = _spoke(tmp_path, {"a": {"cadence": "daily", "ran_days_ago": 1}})
    _contract(root, "a", kind="advisor")
    assert _state(root, "a") == ol.LIVE


def test_nested_run_block_tool_is_resolved(tmp_path):
    """qa_assurance declares its tool under `run`, not at the top level."""
    root = _spoke(tmp_path, {"a": {"cadence": "daily", "ran_days_ago": 1}})
    real = os.path.join(root, "real.py")
    open(real, "w").close()
    _contract(root, "a", kind="deterministic-tool-backed",
              run={"tool": "real.py", "interpreter": "python3"})
    assert _state(root, "a") == ol.LIVE


def test_unrunnable_headline_does_not_overclaim_the_cause(tmp_path):
    """Two different faults reach UNRUNNABLE -- a broken path and no path at all.
    The headline must not assert the first when it was the second."""
    root = _spoke(tmp_path, {"a": {"cadence": "daily", "ran_days_ago": None}})
    _contract(root, "a", kind="deterministic-tool-backed")
    line = ol.worst_line(ol.check(root, now=NOW))
    assert "UNRUNNABLE" in line
    assert "does not exist" not in line
