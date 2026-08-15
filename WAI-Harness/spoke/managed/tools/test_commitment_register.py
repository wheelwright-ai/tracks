#!/usr/bin/env python3
"""Fixtures for commitment_register.py.

The register exists because the operator said the work would be forgotten. So the
fixtures that matter most are the ones proving it CANNOT quietly report success:
an unknown landing kind must not land, a landed-but-unmeasured commitment must not
read as done, and work that comes undone must reappear as REGRESSED rather than
sitting on its old verdict.
"""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import commitment_register as cr
import trust_epoch as te


@pytest.fixture
def root(tmp_path):
    r = str(tmp_path)
    os.makedirs(os.path.join(r, "WAI-Harness", "spoke", "local"), exist_ok=True)
    return r


# --- landing evaluation ---------------------------------------------------


def test_file_exists_landing(root):
    cr.add(root, "c1", "make the file", {"kind": "file_exists", "path": "x.py"})
    assert cr.check(root)["rows"][0]["status"] == cr.OPEN
    open(os.path.join(root, "x.py"), "w").close()
    assert cr.check(root)["rows"][0]["status"] == cr.LANDED


def test_file_contains_landing(root):
    with open(os.path.join(root, "x.sh"), "w") as h:
        h.write("nothing here\n")
    cr.add(root, "c1", "add FOO", {"kind": "file_contains", "path": "x.sh", "needle": "FOO"})
    assert cr.check(root)["rows"][0]["status"] == cr.OPEN
    with open(os.path.join(root, "x.sh"), "w") as h:
        h.write("FOO=1\n")
    assert cr.check(root)["rows"][0]["status"] == cr.LANDED


def test_command_landing(root):
    cr.add(root, "c1", "make it exit 0", {"kind": "command", "cmd": "test -f ok.txt"})
    assert cr.check(root)["rows"][0]["status"] == cr.OPEN
    open(os.path.join(root, "ok.txt"), "w").close()
    assert cr.check(root)["rows"][0]["status"] == cr.LANDED


def test_lug_completed_landing(root):
    cr.add(root, "c1", "land the lug", {"kind": "lug_completed", "id": "impl-x-v1"})
    assert cr.check(root)["rows"][0]["status"] == cr.OPEN
    d = os.path.join(root, "WAI-Harness", "spoke", "local", "lugs", "bytype",
                     "impl", "completed")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "impl-x-v1.json"), "w") as h:
        json.dump({"id": "impl-x-v1"}, h)
    assert cr.check(root)["rows"][0]["status"] == cr.LANDED


def test_manual_landing_never_auto_lands(root):
    cr.add(root, "c1", "operator must decide",
           {"kind": "manual", "note": "needs a human ruling"})
    report = cr.check(root)
    assert report["rows"][0]["status"] == cr.OPEN
    assert report["manual_landings"] == 1


def test_unknown_landing_kind_does_not_land(root):
    """A typo must not mark work complete -- the cheapest way to fake the register."""
    cr.add(root, "c1", "typo'd kind", {"kind": "file_exsits", "path": "x.py"})
    row = cr.check(root)["rows"][0]
    assert row["status"] == cr.OPEN
    assert "unknown landing kind" in row["evidence"]


def test_malformed_landing_does_not_land(root):
    cr.add(root, "c1", "bad landing", "not-an-object")
    assert cr.check(root)["rows"][0]["status"] == cr.OPEN


# --- regression detection -------------------------------------------------


def test_work_that_comes_undone_reads_REGRESSED(root):
    path = os.path.join(root, "x.py")
    open(path, "w").close()
    cr.add(root, "c1", "keep the file", {"kind": "file_exists", "path": "x.py"})
    assert cr.check(root)["rows"][0]["status"] == cr.LANDED
    os.remove(path)
    report = cr.check(root)
    assert report["rows"][0]["status"] == cr.REGRESSED
    assert cr.exit_code(report) == 2


def test_regressed_then_repaired_returns_to_landed(root):
    path = os.path.join(root, "x.py")
    open(path, "w").close()
    cr.add(root, "c1", "keep the file", {"kind": "file_exists", "path": "x.py"})
    cr.check(root)
    os.remove(path)
    assert cr.check(root)["rows"][0]["status"] == cr.REGRESSED
    open(path, "w").close()
    assert cr.check(root)["rows"][0]["status"] == cr.LANDED


# --- impact, not just landing ---------------------------------------------


def test_landing_without_a_measured_effect_is_not_done(root):
    """The half that makes this evolve rather than merely complete."""
    with open(os.path.join(root, "count.sh"), "w") as h:
        h.write("echo 7\n")
    cr.add(root, "c1", "improve the number", {"kind": "file_exists", "path": "x.py"},
           measure="sh count.sh")
    open(os.path.join(root, "x.py"), "w").close()
    report = cr.check(root)
    assert report["rows"][0]["status"] == cr.LANDED_UNMEASURED
    assert cr.exit_code(report) == 1, "landed-unmeasured read as finished"


def test_measuring_moves_it_to_landed_and_records_the_delta(root):
    with open(os.path.join(root, "count.sh"), "w") as h:
        h.write("echo 7\n")
    cr.add(root, "c1", "improve", {"kind": "file_exists", "path": "x.py"},
           measure="sh count.sh")
    open(os.path.join(root, "x.py"), "w").close()
    with open(os.path.join(root, "count.sh"), "w") as h:
        h.write("echo 3\n")
    out = cr.measure(root, "c1")
    assert out["baseline"] == 7.0 and out["effect"] == 3.0 and out["delta"] == -4.0
    assert cr.check(root)["rows"][0]["status"] == cr.LANDED


def test_baseline_is_sampled_at_registration_not_later(root):
    with open(os.path.join(root, "count.sh"), "w") as h:
        h.write("echo 42\n")
    out = cr.add(root, "c1", "x", {"kind": "manual", "note": "n"}, measure="sh count.sh")
    assert out["baseline"] == 42.0


def test_non_numeric_measure_is_unmeasured_not_an_improvement(root):
    with open(os.path.join(root, "prose.sh"), "w") as h:
        h.write("echo all good\n")
    cr.add(root, "c1", "x", {"kind": "file_exists", "path": "x.py"}, measure="sh prose.sh")
    open(os.path.join(root, "x.py"), "w").close()
    out = cr.measure(root, "c1")
    assert out["effect"] is None
    assert cr.check(root)["rows"][0]["status"] == cr.LANDED_UNMEASURED


def test_no_measure_declared_lands_cleanly(root):
    cr.add(root, "c1", "x", {"kind": "file_exists", "path": "x.py"})
    open(os.path.join(root, "x.py"), "w").close()
    assert cr.check(root)["rows"][0]["status"] == cr.LANDED


# --- visibility -----------------------------------------------------------


def test_oldest_open_is_named_not_just_counted(root):
    cr.add(root, "old-one", "the forgotten thing", {"kind": "manual", "note": "n"})
    cr.add(root, "new-one", "recent", {"kind": "manual", "note": "n"})
    data = cr.read(root)
    data["commitments"][0]["opened_at"] = "2026-01-01T00:00:00+00:00"
    cr.write(root, data)
    report = cr.check(root)
    assert report["oldest_open"]["id"] == "old-one"
    assert "old-one" in cr.line(report)


def test_regressed_dominates_the_wakeup_line(root):
    open(os.path.join(root, "x.py"), "w").close()
    cr.add(root, "c1", "keep", {"kind": "file_exists", "path": "x.py"})
    cr.add(root, "c2", "other", {"kind": "manual", "note": "n"})
    cr.check(root)
    os.remove(os.path.join(root, "x.py"))
    assert "REGRESSED" in cr.line(cr.check(root))


def test_register_says_when_it_has_become_a_backlog(root):
    for i in range(cr.CROWDING_LIMIT + 1):
        cr.add(root, f"c{i}", "x", {"kind": "manual", "note": "n"})
    report = cr.check(root)
    assert report["crowded"] is True
    assert "backlog" in cr.render(report)


def test_manual_only_landings_are_flagged_as_depending_on_memory(root):
    cr.add(root, "c1", "x", {"kind": "manual", "note": "human ruling"})
    assert "depend on someone remembering" in cr.render(cr.check(root))


def test_empty_register_is_explicit(root):
    assert cr.line(cr.check(root)) == "Commitments: none registered"
    assert cr.exit_code(cr.check(root)) == 0


# --- integrity ------------------------------------------------------------


def test_duplicate_id_is_refused(root):
    cr.add(root, "c1", "x", {"kind": "manual", "note": "n"})
    assert cr.add(root, "c1", "y", {"kind": "manual", "note": "n"})["added"] is False
    assert len(cr.read(root)["commitments"]) == 1


def test_corrupt_register_does_not_crash(root):
    path = cr.register_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as h:
        h.write("{broken")
    assert cr.check(root)["total"] == 0


def test_cli_json_in_both_positions(root, capsys):
    cr.add(root, "c1", "x", {"kind": "manual", "note": "n"})
    assert cr._main(["--root", root, "check", "--json"]) == 1
    after = json.loads(capsys.readouterr().out)
    assert cr._main(["--root", root, "--json", "check"]) == 1
    before = json.loads(capsys.readouterr().out)
    assert after["total"] == before["total"] == 1
