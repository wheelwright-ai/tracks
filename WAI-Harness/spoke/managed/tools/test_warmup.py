#!/usr/bin/env python3
"""Fixtures for warmup.py -- the FLOOR ceremony.

The load-bearing tests here are the ones that try to CHEAT the floor: declare
nothing, let a floor expire and keep claiming it, launder an unproven probe into
a pass. Each of those is a fixture, because each is how this becomes theatre.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import trust_epoch as te
import warmup as wu


NOW = datetime.now(timezone.utc)


def _mkspoke(tmp_path, *, name="testspoke", goal=None, tests=0, advisors=(),
             advisor_output=True, track=(10, 0), epoch=True):
    """track: (rich, floor) turns for one session, or None for a spoke with none.
    Defaults to a healthy track because TIER 0 gates every other verdict -- a
    fixture that forgets it is testing the track probe, not the one it named."""
    root = str(tmp_path)
    base = os.path.join(root, "WAI-Harness", "spoke", "local")
    os.makedirs(base, exist_ok=True)
    wheel = {"name": name}
    if goal:
        wheel["goal"] = goal
    wheel["version"] = "1.0.0"
    with open(os.path.join(base, "WAI-State.json"), "w") as handle:
        json.dump({"wheel": wheel}, handle)

    tdir = os.path.join(root, "WAI-Harness", "spoke", "managed", "tools")
    os.makedirs(tdir, exist_ok=True)
    for i in range(tests):
        with open(os.path.join(tdir, f"test_fixture_{i}.py"), "w") as handle:
            handle.write("def test_ok():\n    assert True\n")

    for adv in advisors:
        d = os.path.join(root, "WAI-Harness", "spoke", "advisors", adv)
        os.makedirs(d, exist_ok=True)
        if advisor_output:
            with open(os.path.join(d, "runs.jsonl"), "w") as handle:
                handle.write('{"ran": true}\n')
    if track is not None:
        _mktrack(root, [track])
    if epoch:
        # A spoke operating under this regime has an epoch; the track probe grades
        # the post-epoch window, so a fixture without one is testing the epoch.
        te.stamp(root)
    return root


# --- declare --------------------------------------------------------------


def test_declare_reads_the_spokes_own_testimony(tmp_path):
    root = _mkspoke(tmp_path, name="alpha", goal="x" * 40, tests=1, advisors=["ozi"])
    d = wu.declare(root)
    assert wu._decl_value(d, "identity") == "alpha"
    assert wu._decl_value(d, "tests") == 1
    assert wu._decl_value(d, "advisors") == ["ozi"]
    assert d["meaningful"] is True


def test_declaration_with_no_name_is_not_meaningful(tmp_path):
    root = _mkspoke(tmp_path, name=None, tests=1)
    assert wu.declare(root)["meaningful"] is False


# --- the silence cheat ----------------------------------------------------


def test_empty_declaration_is_EMPTY_not_ESTABLISHED(tmp_path):
    """Declaring nothing must not buy a clean floor."""
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "WAI-Harness", "spoke", "local"), exist_ok=True)
    record = wu.run(root, run_tests=False)
    assert record["verdict"] == wu.EMPTY
    assert record["verdict"] != wu.ESTABLISHED


def test_empty_floor_is_not_cleared_to_build(tmp_path):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "WAI-Harness", "spoke", "local"), exist_ok=True)
    wu.run(root, apply=True, run_tests=False)
    assert wu.status(root)["cleared_to_build"] is False


# --- probes ---------------------------------------------------------------


def test_missing_goal_fails_its_probe(tmp_path):
    root = _mkspoke(tmp_path, goal=None, tests=1, advisors=["ozi"])
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["goal"]["verdict"] == wu.FAILED


def test_terse_goal_is_unproven_not_proven(tmp_path):
    root = _mkspoke(tmp_path, goal="be good", tests=1, advisors=["ozi"])
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["goal"]["verdict"] == wu.UNPROVEN


def test_advisor_that_never_produced_output_fails(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1,
                    advisors=["ozi"], advisor_output=False)
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["advisors"]["verdict"] == wu.FAILED
    assert "never ran" in results["advisors"]["evidence"]


def test_partial_advisor_coverage_is_not_proven(tmp_path):
    """One advisor that has never run drags the whole probe off PROVEN."""
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    d = os.path.join(root, "WAI-Harness", "spoke", "advisors", "silent")
    os.makedirs(d, exist_ok=True)
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["advisors"]["verdict"] != wu.PROVEN


def test_no_trust_epoch_fails_the_history_probe(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"], epoch=False)
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["history"]["verdict"] == wu.FAILED


def test_stamped_epoch_with_no_post_epoch_work_is_unproven_not_proven(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    te.stamp(root)
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["history"]["verdict"] == wu.UNPROVEN


def test_skipping_the_suite_is_unproven_never_proven(tmp_path):
    """--no-tests must not silently upgrade to a pass."""
    root = _mkspoke(tmp_path, goal="x" * 40, tests=2, advisors=["ozi"])
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["tests"]["verdict"] == wu.UNPROVEN


def test_a_real_passing_suite_proves_the_tests_probe(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    results = {r["id"]: r for r in wu.probe(root, run_tests=True)["results"]}
    assert results["tests"]["verdict"] == wu.PROVEN, results["tests"]["evidence"]


def test_a_failing_suite_fails_the_tests_probe(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    tdir = os.path.join(root, "WAI-Harness", "spoke", "managed", "tools")
    with open(os.path.join(tdir, "test_broken.py"), "w") as handle:
        handle.write("def test_bad():\n    assert False\n")
    results = {r["id"]: r for r in wu.probe(root, run_tests=True)["results"]}
    assert results["tests"]["verdict"] == wu.FAILED


# --- verdict folding ------------------------------------------------------


def test_any_open_gap_blocks_ESTABLISHED(tmp_path):
    root = _mkspoke(tmp_path, goal=None, tests=1, advisors=["ozi"])
    te.stamp(root)
    record = wu.run(root, run_tests=False)
    assert record["verdict"] == wu.INCOMPLETE
    assert any(g["id"] == "goal" for g in record["delta"])


def test_explicit_admission_clears_a_gap(tmp_path):
    """An admitted gap is a recorded decision -- it unblocks, and it stays visible."""
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    te.stamp(root)
    blocked = wu.run(root, run_tests=False)
    assert blocked["verdict"] == wu.INCOMPLETE
    cleared = wu.run(root, run_tests=False, admitted=["tests", "history", "advisors"])
    assert cleared["verdict"] == wu.ESTABLISHED
    assert cleared["admitted_unproven"] == ["advisors", "history", "tests"]
    assert cleared["delta"], "an admitted gap disappeared from the record"


def test_admitting_everything_still_needs_one_real_proof(tmp_path):
    """You cannot admit your way to a floor with zero proven items."""
    root = str(tmp_path)
    base = os.path.join(root, "WAI-Harness", "spoke", "local")
    os.makedirs(base, exist_ok=True)
    with open(os.path.join(base, "WAI-State.json"), "w") as handle:
        json.dump({"wheel": {}}, handle)
    record = wu.run(root, run_tests=False,
                    admitted=list(wu.PROBES.keys()))
    assert record["verdict"] != wu.ESTABLISHED


# --- staleness ------------------------------------------------------------


def test_fresh_established_floor_clears_the_build(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    te.stamp(root)
    wu.run(root, apply=True, run_tests=False, admitted=["tests", "history", "advisors"])
    st = wu.status(root)
    assert st["verdict"] == wu.ESTABLISHED
    assert st["cleared_to_build"] is True


def test_expired_floor_reads_UNKNOWN_not_ESTABLISHED(tmp_path):
    """A proof from six weeks ago is a historical fact, not a current one."""
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    te.stamp(root)
    wu.run(root, apply=True, run_tests=False, admitted=["tests", "history", "advisors"])
    path = wu.floor_path(root)
    record = json.load(open(path))
    record["expires_at"] = te._iso(NOW - timedelta(days=3))
    with open(path, "w") as handle:
        json.dump(record, handle)
    st = wu.status(root)
    assert st["verdict"] == wu.UNKNOWN
    assert st["stored_verdict"] == wu.ESTABLISHED
    assert st["cleared_to_build"] is False
    assert "STALE" in st["reason"]


def test_missing_floor_is_UNKNOWN(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    st = wu.status(root)
    assert st["verdict"] == wu.UNKNOWN
    assert st["cleared_to_build"] is False


def test_floor_without_expiry_is_UNKNOWN(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    path = wu.floor_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        json.dump({"verdict": wu.ESTABLISHED}, handle)
    assert wu.status(root)["verdict"] == wu.UNKNOWN


def test_unsigned_floor_records_that_it_is_unsigned(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    te.stamp(root)
    record = wu.run(root, run_tests=False)
    assert record["certified_by"] is None


# --- exit codes -----------------------------------------------------------


def test_exit_codes_reserve_zero_for_established(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    te.stamp(root)
    assert wu._main(["--root", root, "run", "--no-tests"]) == 1
    assert wu._main(["--root", root, "run", "--no-tests",
                     "--admit", "tests", "--admit", "history", "--admit", "advisors", "--apply"]) == 0
    assert wu._main(["--root", root, "status"]) == 0


def test_status_exit_2_when_never_run(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    assert wu._main(["--root", root, "status"]) == 2


# --- CLI argument order ---------------------------------------------------


def test_json_flag_accepted_after_the_subcommand(tmp_path, capsys):
    """The wakeup hook calls `status --json`. The first version exited 2 on that
    and the hook rendered a blank line -- a silent miss, not a visible error."""
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    assert wu._main(["--root", root, "status", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == wu.UNKNOWN


def test_json_flag_accepted_before_the_subcommand(tmp_path, capsys):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    assert wu._main(["--root", root, "--json", "status"]) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == wu.UNKNOWN


def test_root_survives_the_subparser(tmp_path, capsys):
    """The SUPPRESS guard: --root before the subcommand must not be re-defaulted
    to '.' by the subparser, which would silently read the wrong directory."""
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    te.stamp(root)
    wu.run(root, apply=True, run_tests=False, admitted=["tests", "history", "advisors"])
    assert wu._main(["--root", root, "status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == wu.ESTABLISHED


# --- criticality tiers ----------------------------------------------------


def _mktrack(root, sessions):
    """sessions: list of (n_rich, n_floor). Dated TODAY so they fall inside the
    post-epoch window the track probe grades (the all-time figure is a scar that
    no fixture and no spoke can move)."""
    base = os.path.join(root, "WAI-Harness", "spoke", "local", "sessions")
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    for i, (rich, floor) in enumerate(sessions):
        d = os.path.join(base, f"session-{today}-{i:02d}00")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "track.jsonl"), "w") as handle:
            for t in range(rich):
                handle.write(json.dumps({
                    "event": "turn", "turn": t + 1, "user_msg": "x",
                    "user_intent": "x", "action": "x", "outcome": "x",
                    "thinking": "because x", "focus": "x", "phase": "build"}) + "\n")
            for t in range(floor):
                handle.write(json.dumps({
                    "event": "turn", "turn": rich + t + 1,
                    "assistant_text": "x", "tools": []}) + "\n")


def test_track_is_tier_zero_and_ranks_above_everything(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"], track=(9, 1))
    results = wu.probe(root, run_tests=False)["results"]
    assert results[0]["id"] == "track", "track did not sort first"
    assert results[0]["tier"] == 0
    assert results[0]["tier_name"] == "CONSTITUTIONAL"


def test_no_track_at_all_fails_tier_zero(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"], track=None)
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["track"]["verdict"] == wu.FAILED


def test_track_below_half_reasoning_fails(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"], track=(2, 8))
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["track"]["verdict"] == wu.FAILED


def test_track_decaying_is_unproven_not_proven(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"], track=(6, 4))
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["track"]["verdict"] == wu.UNPROVEN


def test_healthy_track_is_proven(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["track"]["verdict"] == wu.PROVEN, results["track"]["evidence"]


def test_tier_zero_gap_cannot_be_admitted_away(tmp_path):
    """The whole point of the tier: admitting the track is not on offer, because
    the reasoning lost while it is unproven is never recoverable later."""
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    te.stamp(root)
    _mktrack(root, [(1, 9)])          # track FAILED (overwrites the healthy default)
    record = wu.run(root, run_tests=False,
                    admitted=["track", "tests", "history", "advisors"])
    assert record["verdict"] == wu.INCOMPLETE
    assert record["blocking_tier0"] == ["track"]


def test_admitting_everything_else_works_once_the_track_is_healthy(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    te.stamp(root)
    record = wu.run(root, run_tests=False,
                    admitted=["tests", "history", "advisors"])
    assert record["verdict"] == wu.ESTABLISHED
    assert record["blocking_tier0"] == []


def test_tier_zero_is_marked_not_admittable_in_the_record(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"])
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["track"]["admittable"] is False
    assert results["advisors"]["admittable"] is True


def test_unknown_probe_defaults_to_structural_not_operational(tmp_path):
    """Defaulting an unclassified check downward is how new checks go optional."""
    assert wu.tier_of("a-brand-new-probe") == 1
    assert wu.is_admittable("a-brand-new-probe") is True


def test_delta_carries_tier_so_a_reader_can_rank_the_gaps(tmp_path):
    root = _mkspoke(tmp_path, goal=None, tests=1, advisors=["ozi"], track=(1, 9))
    te.stamp(root)
    record = wu.run(root, run_tests=False)
    tiers = {g["id"]: g["tier"] for g in record["delta"]}
    assert tiers["track"] == 0
    assert tiers["goal"] == 2
    assert record["delta"][0]["tier"] == 0, "delta not ordered worst-tier-first"


# --- the post-epoch window, and its Goodhart guards -----------------------


def _dated_track(root, session_date, rich, floor):
    d = os.path.join(root, "WAI-Harness", "spoke", "local", "sessions",
                     f"session-{session_date}-1200")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "track.jsonl"), "w") as handle:
        for t in range(rich):
            handle.write(json.dumps({
                "event": "turn", "turn": t + 1, "user_msg": "x", "user_intent": "x",
                "action": "x", "outcome": "x", "thinking": "because x",
                "focus": "x", "phase": "build"}) + "\n")
        for t in range(floor):
            handle.write(json.dumps({
                "event": "turn", "turn": rich + t + 1,
                "assistant_text": "x", "tools": []}) + "\n")


def test_pre_epoch_sessions_do_not_drag_the_grade(tmp_path):
    """The scar is real and unrecoverable; it must not make the gate unreachable."""
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"], track=None)
    _dated_track(root, "20260101", 0, 200)       # ancient, all floor-only
    _dated_track(root, datetime.now(timezone.utc).strftime("%Y%m%d"), 20, 0)
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["track"]["verdict"] == wu.PROVEN, results["track"]["evidence"]


def test_the_legacy_scar_is_always_reported_even_when_proven(tmp_path):
    """Narrowing the window is only honest if the thing excluded stays visible."""
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"], track=None)
    _dated_track(root, "20260101", 0, 200)
    _dated_track(root, datetime.now(timezone.utc).strftime("%Y%m%d"), 20, 0)
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert "legacy scar" in results["track"]["evidence"]
    assert "200" in results["track"]["evidence"] or "220" in results["track"]["evidence"]


def test_too_few_post_epoch_turns_is_unproven_not_proven(tmp_path):
    """You cannot reach the floor by writing nothing since the epoch."""
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"], track=None)
    _dated_track(root, "20260101", 400, 0)      # a glorious past
    _dated_track(root, datetime.now(timezone.utc).strftime("%Y%m%d"), 2, 0)
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["track"]["verdict"] == wu.UNPROVEN
    assert "too few to grade" in results["track"]["evidence"]


def test_pre_epoch_excellence_cannot_carry_a_bad_post_epoch_window(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"], track=None)
    _dated_track(root, "20260101", 500, 0)
    _dated_track(root, datetime.now(timezone.utc).strftime("%Y%m%d"), 2, 18)
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["track"]["verdict"] == wu.FAILED


def test_undatable_session_counts_as_legacy_not_as_graded(tmp_path):
    """Defaulting an odd name into the graded window is the direction that flatters."""
    assert wu._session_started_after("weird-name", datetime.now(timezone.utc)) is False
    assert wu._session_started_after("", datetime.now(timezone.utc)) is False


def test_malformed_lines_fail_outright_regardless_of_window(tmp_path):
    root = _mkspoke(tmp_path, goal="x" * 40, tests=1, advisors=["ozi"], track=None)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    _dated_track(root, today, 20, 0)
    d = os.path.join(root, "WAI-Harness", "spoke", "local", "sessions",
                     f"session-{today}-1200")
    with open(os.path.join(d, "track.jsonl"), "a") as handle:
        handle.write("{ broken fragment\n")
    results = {r["id"]: r for r in wu.probe(root, run_tests=False)["results"]}
    assert results["track"]["verdict"] == wu.FAILED
    assert "track_repair" in results["track"]["evidence"]
