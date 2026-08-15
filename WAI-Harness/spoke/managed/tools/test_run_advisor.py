#!/usr/bin/env python3
"""Fixtures for run_advisor.py -- executing an advisor AND recording that it ran.

The prohibition under test above all others: it must never record a run it did not
perform. A liveness record is evidence, and evidence written without doing the work
is the precise failure the LOW TRUST tenet exists to remove. Dry-run, unresolvable
commands and timeouts all have fixtures asserting that nothing was written.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import oracle_liveness as ol
import run_advisor as ra


def _spoke(tmp_path, advisor="a", **entry):
    root = str(tmp_path)
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", advisor)
    os.makedirs(d, exist_ok=True)
    row = {"advisor_id": advisor}
    row.update(entry)
    with open(os.path.join(root, "WAI-Harness", "spoke", "advisors",
                           "schedule-index.json"), "w") as handle:
        json.dump({"advisors": [row]}, handle)
    return root


def _tool(root, name="t.py", exit_code=0, out="did the thing"):
    path = os.path.join(root, name)
    with open(path, "w") as handle:
        handle.write(f"import sys\nprint({out!r})\nsys.exit({exit_code})\n")
    return name


def _runs(root, advisor="a"):
    p = os.path.join(root, "WAI-Harness", "spoke", "advisors", advisor, "runs.jsonl")
    if not os.path.exists(p):
        return []
    return [json.loads(l) for l in open(p) if l.strip()]


def _state_file(root, advisor="a"):
    p = os.path.join(root, "WAI-Harness", "spoke", "advisors", advisor,
                     "scan_state.json")
    return json.load(open(p)) if os.path.exists(p) else None


# --- resolution -----------------------------------------------------------


def test_tool_field_becomes_a_python_command(tmp_path):
    root = _spoke(tmp_path, tool="t.py")
    _tool(root)
    cmd, src = ra.resolve_command(root, "a")
    assert cmd == "python3 t.py" and src == "schedule-index.tool"


def test_dispatch_command_is_taken_as_written(tmp_path):
    root = _spoke(tmp_path, dispatch_command="python3 t.py --flag")
    cmd, _ = ra.resolve_command(root, "a")
    assert cmd == "python3 t.py --flag"


def test_contract_is_the_fallback_when_the_index_is_silent(tmp_path):
    root = _spoke(tmp_path)
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", "a")
    with open(os.path.join(d, "contract.json"), "w") as handle:
        json.dump({"command": "python3 t.py"}, handle)
    cmd, src = ra.resolve_command(root, "a")
    assert cmd == "python3 t.py" and src == "contract.command"


def test_nothing_declared_is_unresolvable(tmp_path):
    root = _spoke(tmp_path)
    cmd, reason = ra.resolve_command(root, "a")
    assert cmd is None and "no dispatch_command" in reason


# --- it must not record a run it did not perform --------------------------


def test_dry_run_executes_nothing_and_records_nothing(tmp_path):
    root = _spoke(tmp_path, tool="t.py")
    _tool(root)
    out = ra.run(root, "a", dry_run=True)
    assert out["ran"] is False and out["state"] == "RESOLVED"
    assert _runs(root) == []
    assert _state_file(root) is None


def test_unresolvable_command_records_nothing(tmp_path):
    root = _spoke(tmp_path)
    out = ra.run(root, "a")
    assert out["state"] == "UNRUNNABLE" and out["ran"] is False
    assert _runs(root) == []


def test_missing_tool_path_records_nothing(tmp_path):
    root = _spoke(tmp_path, tool="gone.py")
    out = ra.run(root, "a")
    assert out["state"] == "UNRUNNABLE"
    assert "missing path" in out["reason"]
    assert _runs(root) == []


def test_timeout_records_nothing(tmp_path):
    """No verdict was reached, so recording one would be inventing evidence."""
    root = _spoke(tmp_path, tool="slow.py")
    with open(os.path.join(root, "slow.py"), "w") as handle:
        handle.write("import time\ntime.sleep(30)\n")
    out = ra.run(root, "a", timeout=1)
    assert out["state"] == "TIMEOUT" and out["ran"] is False
    assert _runs(root) == []


def test_there_is_no_force_flag(tmp_path):
    """A way to stamp a run without running is the one thing this must not have.

    Checks the declared CLI surface, not the prose -- the module docstring says the
    word "--force" precisely to explain its absence."""
    import inspect
    src = inspect.getsource(ra)
    body = src.split('"""', 2)[-1]           # drop the module docstring
    assert 'add_argument("--force"' not in body
    assert "assume_ok" not in body and 'add_argument("--assume-ok"' not in body
    assert "def record_run" in body and "subprocess.run" in body


# --- a failed run is still a run ------------------------------------------


def test_successful_run_is_recorded(tmp_path):
    root = _spoke(tmp_path, tool="t.py")
    _tool(root, exit_code=0)
    out = ra.run(root, "a")
    assert out["state"] == "RAN_OK" and out["ok"] is True
    rows = _runs(root)
    assert len(rows) == 1 and rows[0]["exit_code"] == 0 and rows[0]["ok"] is True


def test_failed_run_is_still_recorded_as_having_run(tmp_path):
    """Downgrading a failing oracle back to NEVER would hide a working one."""
    root = _spoke(tmp_path, tool="t.py")
    _tool(root, exit_code=3)
    out = ra.run(root, "a")
    assert out["state"] == "RAN_FAILED" and out["ok"] is False
    rows = _runs(root)
    assert len(rows) == 1 and rows[0]["ok"] is False and rows[0]["exit_code"] == 3


def test_ok_is_recorded_separately_from_the_fact_of_running(tmp_path):
    root = _spoke(tmp_path, tool="t.py")
    _tool(root, exit_code=1)
    ra.run(root, "a")
    row = _runs(root)[0]
    assert set(["ran_at", "ok", "exit_code"]).issubset(row)


# --- the record reaches every reader --------------------------------------


def test_scan_state_runs_counter_increments(tmp_path):
    root = _spoke(tmp_path, tool="t.py")
    _tool(root)
    ra.run(root, "a")
    ra.run(root, "a")
    assert _state_file(root)["stats"]["runs"] == 2


def test_scan_state_last_run_at_is_stamped(tmp_path):
    root = _spoke(tmp_path, tool="t.py")
    _tool(root)
    ra.run(root, "a")
    assert _state_file(root)["last_run_at"]


def test_schedule_index_last_run_at_is_stamped(tmp_path):
    root = _spoke(tmp_path, tool="t.py")
    _tool(root)
    ra.run(root, "a")
    idx = json.load(open(os.path.join(root, "WAI-Harness", "spoke", "advisors",
                                      "schedule-index.json")))
    assert idx["advisors"][0]["last_run_at"]


def test_runs_jsonl_is_append_only(tmp_path):
    root = _spoke(tmp_path, tool="t.py")
    _tool(root)
    for _ in range(3):
        ra.run(root, "a")
    assert len(_runs(root)) == 3


# --- the whole point: liveness changes afterwards -------------------------


def test_a_never_run_advisor_stops_reading_NEVER_after_a_real_run(tmp_path):
    """The defect this file exists for: proofer ran, produced findings, and still
    reported NEVER because nothing wrote the run down."""
    root = _spoke(tmp_path, tool="t.py", run_cadence="daily")
    _tool(root)
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", "a")
    with open(os.path.join(d, "scan_state.json"), "w") as handle:
        json.dump({"advisor_id": "a", "last_run_at": None, "stats": {"runs": 0}}, handle)
    before = {r["advisor"]: r for r in ol.check(root)["results"]}["a"]["state"]
    assert before == ol.NEVER

    ra.run(root, "a")
    after = {r["advisor"]: r for r in ol.check(root)["results"]}["a"]["state"]
    assert after == ol.LIVE, "running an advisor still did not move its liveness"


def test_a_failing_run_also_clears_NEVER(tmp_path):
    root = _spoke(tmp_path, tool="t.py", run_cadence="daily")
    _tool(root, exit_code=2)
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", "a")
    with open(os.path.join(d, "scan_state.json"), "w") as handle:
        json.dump({"advisor_id": "a", "last_run_at": None, "stats": {"runs": 0}}, handle)
    ra.run(root, "a")
    after = {r["advisor"]: r for r in ol.check(root)["results"]}["a"]["state"]
    assert after == ol.LIVE, "a red oracle was still counted as silent"


# --- run-all --------------------------------------------------------------


def test_run_all_targets_only_the_named_states(tmp_path):
    root = _spoke(tmp_path, "never_one", tool="t.py", run_cadence="daily")
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors")
    os.makedirs(os.path.join(d, "live_one"), exist_ok=True)
    with open(os.path.join(d, "live_one", "runs.jsonl"), "w") as handle:
        handle.write('{"ran": true}\n')
    idx = json.load(open(os.path.join(d, "schedule-index.json")))
    idx["advisors"].append({"advisor_id": "live_one", "run_cadence": "weekly",
                            "last_run_at": ra.te._iso(ra.te._now())})
    json.dump(idx, open(os.path.join(d, "schedule-index.json"), "w"))
    _tool(root)

    out = ra.run_all(root, states=("NEVER",), dry_run=True)
    assert out["targets"] == ["never_one"]


def test_run_all_dry_run_records_nothing(tmp_path):
    root = _spoke(tmp_path, tool="t.py", run_cadence="daily")
    _tool(root)
    ra.run_all(root, states=("NEVER",), dry_run=True)
    assert _runs(root) == []


# --- exit codes -----------------------------------------------------------


def test_exit_codes(tmp_path):
    root = _spoke(tmp_path, tool="t.py")
    _tool(root, exit_code=0)
    assert ra._main(["--root", root, "run", "a"]) == 0
    _tool(root, exit_code=1)
    assert ra._main(["--root", root, "run", "a"]) == 1
    root2 = _spoke(tmp_path / "b")
    assert ra._main(["--root", root2, "run", "a"]) == 2
