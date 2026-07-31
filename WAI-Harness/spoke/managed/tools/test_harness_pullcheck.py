"""Test-at-birth for harness_pullcheck.py - the spoke-side wakeup pull-check
(impl-dist-spoke-pullcheck-v1).

Proves the three acceptance criteria against a fully-injected master+spoke fixture
(hub-registry.json, groups.json, harness-availability.json store):
  - a spoke behind its group's AVAILABLE version self-pulls and MANIFEST verifies
  - a spoke already at AVAILABLE -> no-op (no file rewrite)
  - a cut master has moved past AVAILABLE (uncertified) is never pulled, even
    though the spoke is behind master's raw HEAD
  - no group / no AVAILABLE data resolvable -> falls back to today's ungated pull
    (no regression while availability data is still being populated fleet-wide)
  - a spoke already AHEAD of AVAILABLE is left alone (never a downgrade pull)
"""
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_upgrade as hu  # noqa: E402
import harness_pullcheck as hpc  # noqa: E402

REAL_AVAILABILITY = (Path(__file__).resolve().parents[3] / "hub" / "local" / "tools"
                      / "harness_availability.py")

# This module injects the REAL hub-side availability resolver into its fixture, so it
# can only run where a hub tree exists — the master. It ships to every spoke (it lives
# in managed/tools/, which IS distributed, unlike managed/tests/), and on a spoke the
# copy blew up with FileNotFoundError. That failure was not a spoke defect: it made
# harness_validate's selftest check FAIL on every spoke, which turned every upgrade
# report fleet-wide into a permanent PARTIAL and cost the validation signal its meaning.
# Skip honestly where the source cannot exist rather than fail — the same stance
# check_selftest already takes for a missing pytest ("cannot run, so not claiming pass").
pytestmark = pytest.mark.skipif(
    not REAL_AVAILABILITY.exists(),
    reason=("hub-only source absent (WAI-Harness/hub/local/tools/harness_availability.py) — "
            "this suite injects the real hub resolver, so it runs on the master only"))


def _write(p, text):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _make_master_managed(managed_root, files, version="1.0.0"):
    for rel, txt in files.items():
        _write(Path(managed_root) / rel, txt)
    m = hu.build_manifest(managed_root, version=version, generated_at="2026-01-01T00:00:00Z")
    (Path(managed_root) / hu.MANIFEST_NAME).write_text(json.dumps(m, indent=2) + "\n")


def _make_fixture(tmp_path, master_files, master_version, spoke_id="s1", group_members=("s1",),
                  available_version=None, spoke_version="0.0.0", spoke_files=None):
    """A master WAI-Harness dir (spoke/managed + hub/local/{hub-registry,registry/groups,
    registry/harness-availability,tools/harness_availability.py}) and a spoke repo root
    wired to resolve to `spoke_id` in that registry."""
    master_root = tmp_path / "master" / "WAI-Harness"
    _make_master_managed(master_root / "spoke" / "managed", master_files, version=master_version)

    spoke_root = tmp_path / spoke_id
    _write(spoke_root / "WAI-Harness" / "VERSION", spoke_version + "\n")
    for rel, txt in (spoke_files or {}).items():
        _write(spoke_root / "WAI-Harness" / "spoke" / "managed" / rel, txt)

    registry = {"wheels": [{"wheel_id": spoke_id, "path": str(spoke_root)}]}
    _write(master_root / "hub" / "local" / "hub-registry.json", json.dumps(registry))

    groups = {"groups": [{"group_id": "g1",
                          "members": [{"wheel_id": w} for w in group_members]}]}
    _write(master_root / "hub" / "local" / "registry" / "groups.json", json.dumps(groups))

    if available_version is not None:
        store = {"g1": {"available_version": available_version, "receipt_sha": "deadbeef",
                        "marked_at": "2026-01-01T00:00:00+00:00"}}
        _write(master_root / "hub" / "local" / "registry" / "harness-availability.json",
              json.dumps(store))

    dst = master_root / "hub" / "local" / "tools" / "harness_availability.py"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REAL_AVAILABILITY, dst)

    return master_root, spoke_root


def test_behind_available_self_pulls_and_verifies(tmp_path):
    master_root, spoke_root = _make_fixture(
        tmp_path, {"tools/a.py": "v2\n"}, master_version="2.0.0",
        available_version="2.0.0", spoke_version="1.0.0",
        spoke_files={"tools/a.py": "v1\n"})

    rep = hpc.check(str(spoke_root), str(master_root), validate=False)

    assert rep["gate"]["decision"] == "gated"
    assert rep["gate"]["available_version"] == "2.0.0"
    assert rep["pull"]["status"] == "upgraded"
    assert rep["pull"]["ok"] is True
    target = spoke_root / "WAI-Harness" / "spoke" / "managed" / "tools" / "a.py"
    assert target.read_text() == "v2\n"
    # MANIFEST verify ran and passed
    assert rep["pull"]["verify_post"]["ok"] is True


def test_current_spoke_is_a_noop(tmp_path):
    master_root, spoke_root = _make_fixture(
        tmp_path, {"tools/a.py": "v2\n"}, master_version="2.0.0",
        available_version="2.0.0", spoke_version="2.0.0",
        spoke_files={"tools/a.py": "v2\n"})

    rep = hpc.check(str(spoke_root), str(master_root), validate=False)

    assert rep["gate"]["decision"] == "gated"
    assert rep["pull"]["status"] == "current"
    assert rep["pull"]["pulled"] == 0


def test_uncertified_cut_beyond_available_is_never_pulled(tmp_path):
    # master has moved on to 3.0.0 but only 2.0.0 was ever marked AVAILABLE for g1.
    master_root, spoke_root = _make_fixture(
        tmp_path, {"tools/a.py": "v3-uncertified\n"}, master_version="3.0.0",
        available_version="2.0.0", spoke_version="1.0.0",
        spoke_files={"tools/a.py": "v1\n"})

    rep = hpc.check(str(spoke_root), str(master_root), validate=False)

    assert rep["gate"]["decision"] == "gated"
    assert rep["pull"]["status"] == "version-desync"
    assert rep["pull"]["pulled"] == 0
    target = spoke_root / "WAI-Harness" / "spoke" / "managed" / "tools" / "a.py"
    assert target.read_text() == "v1\n"   # untouched -- the uncertified cut never landed


def test_no_available_data_falls_back_to_ungated_pull(tmp_path):
    # group resolves but no version has ever been marked AVAILABLE for it: today's
    # unconditioned pull-on-spin-up behavior, unchanged.
    master_root, spoke_root = _make_fixture(
        tmp_path, {"tools/a.py": "v2\n"}, master_version="2.0.0",
        available_version=None, spoke_version="1.0.0",
        spoke_files={"tools/a.py": "v1\n"})

    rep = hpc.check(str(spoke_root), str(master_root), validate=False)

    assert rep["gate"]["decision"] == "ungated"
    assert rep["gate"]["available_version"] is None
    assert rep["pull"]["status"] == "upgraded"
    target = spoke_root / "WAI-Harness" / "spoke" / "managed" / "tools" / "a.py"
    assert target.read_text() == "v2\n"


def test_ungrouped_spoke_falls_back_to_ungated_pull(tmp_path):
    # spoke not a member of any group at all
    master_root, spoke_root = _make_fixture(
        tmp_path, {"tools/a.py": "v2\n"}, master_version="2.0.0",
        group_members=("someone-else",), available_version="2.0.0",
        spoke_version="1.0.0", spoke_files={"tools/a.py": "v1\n"})

    rep = hpc.check(str(spoke_root), str(master_root), validate=False)

    assert rep["gate"]["group"] is None
    assert rep["gate"]["decision"] == "ungated"
    assert rep["pull"]["status"] == "upgraded"


def test_ahead_of_available_is_never_downgraded(tmp_path):
    master_root, spoke_root = _make_fixture(
        tmp_path, {"tools/a.py": "v2\n"}, master_version="2.0.0",
        available_version="2.0.0", spoke_version="5.0.0",
        spoke_files={"tools/a.py": "custom-ahead\n"})

    rep = hpc.check(str(spoke_root), str(master_root), validate=False)

    assert rep["gate"]["decision"] == "ahead-of-available"
    assert rep["pull"] is None
    target = spoke_root / "WAI-Harness" / "spoke" / "managed" / "tools" / "a.py"
    assert target.read_text() == "custom-ahead\n"
