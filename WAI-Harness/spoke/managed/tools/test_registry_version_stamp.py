"""Test-at-birth for registry_version_stamp.py — the consumer half of the version circle.

The defect this tool exists to kill: hub-registry.json's `harness_version` column
had no writer on the distribution path, so it drifted into confident fiction
(registry 4.14.10 vs byte-verified 4.14.18 on the same day, same spokes).

These prove the properties that make the stamp trustworthy rather than merely
present. Each one corresponds to a way the naive version of this tool would lie:

  - a passing, byte-verified report stamps, with provenance attached
  - a FAILED report never stamps (it proves nothing about that spoke's disk)
  - a report with verify_post_ok false never stamps (bytes were never confirmed)
  - newest report wins, including when it is a DOWNGRADE (rollbacks are real)
  - an older report re-read from completed/ cannot overwrite newer evidence
  - dry-run does not touch the file; --apply does
  - applying twice is a no-op (idempotent)
  - a report from a spoke absent from the registry is surfaced, never silently dropped
  - a wheel matches by realpath even when the registry path is spelled differently
  - coverage() separates proven from unproven, so an unowned value cannot pose as known
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry_version_stamp as rvs  # noqa: E402


def _reg(tmp_path, wheels):
    p = tmp_path / "hub-registry.json"
    p.write_text(json.dumps({"wheels": wheels}, indent=2))
    return p


def _report(d, spoke_id, path, version, created_at, *, outcome="pass", verify=True, rid=None):
    d.mkdir(parents=True, exist_ok=True)
    rid = rid or f"upgrade-report-{spoke_id}-{created_at.replace(':', '').replace('-', '')}-v1"
    (d / f"{rid}.json").write_text(json.dumps({
        "id": rid,
        "type": "upgrade-report",
        "spoke_id": spoke_id,
        "spoke_path": str(path),
        "harness_version": version,
        "outcome": outcome,
        "verify_post_ok": verify,
        "created_at": created_at,
    }, indent=2))
    return rid


@pytest.fixture
def env(tmp_path):
    spoke = tmp_path / "spokes" / "pathfinder"
    spoke.mkdir(parents=True)
    reg = _reg(tmp_path, [
        {"wheel_id": "pathfinder", "path": str(spoke), "status": "active",
         "harness_version": "4.14.10"},
        {"wheel_id": "orphan", "path": str(tmp_path / "spokes" / "orphan"),
         "status": "active", "harness_version": None},
    ])
    reports = tmp_path / "reports" / "open"
    return {"tmp": tmp_path, "spoke": spoke, "registry": reg, "reports": reports}


def _run(env, apply=False, dirs=None):
    return rvs.run(registry_path=env["registry"],
                   report_dirs=dirs or [env["reports"]], apply=apply)


def _wheel(env, wid="pathfinder"):
    reg = json.loads(Path(env["registry"]).read_text())
    return next(w for w in reg["wheels"] if w["wheel_id"] == wid)


def test_passing_verified_report_stamps_with_provenance(env):
    rid = _report(env["reports"], "pathfinder", env["spoke"], "4.14.18", "2026-07-27T23:27:00+00:00")
    out = _run(env, apply=True)
    assert out["applied"] == 1
    w = _wheel(env)
    assert w["harness_version"] == "4.14.18"
    assert w["harness_version_source"] == "upgrade-report"
    assert w["harness_version_evidence"] == rid
    assert w["harness_version_at"] == "2026-07-27T23:27:00+00:00"


def test_failed_report_never_stamps(env):
    _report(env["reports"], "pathfinder", env["spoke"], "4.14.18",
            "2026-07-27T23:27:00+00:00", outcome="fail")
    out = _run(env, apply=True)
    assert out["applied"] == 0
    assert _wheel(env)["harness_version"] == "4.14.10"
    assert any(r["reason"] == "outcome=fail" for r in out["rejected"])


def test_unverified_bytes_never_stamp(env):
    _report(env["reports"], "pathfinder", env["spoke"], "4.14.18",
            "2026-07-27T23:27:00+00:00", verify=False)
    out = _run(env, apply=True)
    assert out["applied"] == 0
    assert _wheel(env)["harness_version"] == "4.14.10"
    assert any("verify_post_ok" in r["reason"] for r in out["rejected"])


def test_newest_wins_even_when_it_is_a_downgrade(env):
    _report(env["reports"], "pathfinder", env["spoke"], "4.14.18", "2026-07-27T23:00:00+00:00")
    _report(env["reports"], "pathfinder", env["spoke"], "4.14.13", "2026-07-27T23:40:00+00:00")
    _run(env, apply=True)
    # A rollback is exactly when a wrong registry costs the most.
    assert _wheel(env)["harness_version"] == "4.14.13"


def test_older_evidence_cannot_overwrite_newer(env):
    _report(env["reports"], "pathfinder", env["spoke"], "4.14.18", "2026-07-27T23:27:00+00:00")
    _run(env, apply=True)

    archive = env["tmp"] / "reports" / "completed"
    _report(archive, "pathfinder", env["spoke"], "4.13.0", "2026-07-01T00:00:00+00:00")
    out = rvs.run(registry_path=env["registry"], report_dirs=[archive], apply=True)

    assert out["applied"] == 0
    assert _wheel(env)["harness_version"] == "4.14.18"
    assert any(s["reason"] == "registry has newer evidence" for s in out["skipped"])


def test_dry_run_does_not_write(env):
    _report(env["reports"], "pathfinder", env["spoke"], "4.14.18", "2026-07-27T23:27:00+00:00")
    before = Path(env["registry"]).read_text()
    out = _run(env, apply=False)
    assert out["applied"] == 0
    assert [s for s in out["stamps"] if s["changed"]]
    assert Path(env["registry"]).read_text() == before


def test_apply_is_idempotent(env):
    _report(env["reports"], "pathfinder", env["spoke"], "4.14.18", "2026-07-27T23:27:00+00:00")
    assert _run(env, apply=True)["applied"] == 1
    after_first = Path(env["registry"]).read_text()
    assert _run(env, apply=True)["applied"] == 0
    assert Path(env["registry"]).read_text() == after_first


def test_unregistered_spoke_is_surfaced_not_dropped(env):
    _report(env["reports"], "ghost", env["tmp"] / "spokes" / "ghost", "4.14.18",
            "2026-07-27T23:27:00+00:00")
    out = _run(env, apply=True)
    assert [u for u in out["unmatched"] if u["spoke"] == "ghost"]
    # Silence here would mean a spoke taking cuts that the registry does not know exists.


def test_matches_by_realpath_not_string(env, tmp_path):
    # Registry spells the path with a redundant segment; realpath must still match.
    reg = json.loads(Path(env["registry"]).read_text())
    reg["wheels"][0]["path"] = str(env["spoke"]) + "/./"
    Path(env["registry"]).write_text(json.dumps(reg, indent=2))
    _report(env["reports"], "pathfinder", env["spoke"], "4.14.18", "2026-07-27T23:27:00+00:00")
    assert _run(env, apply=True)["applied"] == 1


def test_coverage_separates_proven_from_unproven(env):
    out = _run(env, apply=False)
    before = out["coverage_before"]["active"]
    # pathfinder has a version with no provenance -> unproven, NOT known.
    assert before["proven"] == 0
    assert before["unproven"] == 1
    assert before["unknown"] == 1

    _report(env["reports"], "pathfinder", env["spoke"], "4.14.18", "2026-07-27T23:27:00+00:00")
    out = _run(env, apply=True)
    after = out["coverage_after"]["active"]
    assert after["proven"] == 1
    assert after["unproven"] == 0
    assert after["unknown"] == 1


def test_malformed_report_does_not_block_the_readable_ones(env):
    env["reports"].mkdir(parents=True, exist_ok=True)
    (env["reports"] / "broken.json").write_text("{not json")
    _report(env["reports"], "pathfinder", env["spoke"], "4.14.18", "2026-07-27T23:27:00+00:00")
    out = _run(env, apply=True)
    assert out["applied"] == 1
    assert out["unreadable_reports"]


def _manifest(root, version, is_master=True):
    d = Path(root) / "WAI-Harness" / "spoke" / "managed"
    d.mkdir(parents=True, exist_ok=True)
    (d / "MANIFEST.json").write_text(json.dumps(
        {"harness_version": version, "is_master": is_master}))


def test_master_stamps_its_own_row_from_its_manifest(tmp_path):
    master = tmp_path / "mywheel"
    _manifest(master, "4.14.18", is_master=True)
    reg = _reg(tmp_path, [{"wheel_id": "mywheel", "path": str(master),
                           "status": "active", "harness_version": "4.6.4"}])
    out = rvs.run(root=master, registry_path=reg, report_dirs=[], apply=True)

    assert out["self_stamped"] is True
    w = json.loads(reg.read_text())["wheels"][0]
    assert w["harness_version"] == "4.14.18"
    assert w["harness_version_source"] == "master-manifest"
    # A master-manifest stamp counts as PROVEN: it is the declaration, not a report about one.
    assert out["coverage_after"]["active"]["proven"] == 1


def test_non_master_never_self_stamps(tmp_path):
    spoke = tmp_path / "somespoke"
    _manifest(spoke, "9.9.9", is_master=False)
    reg = _reg(tmp_path, [{"wheel_id": "somespoke", "path": str(spoke),
                           "status": "active", "harness_version": "4.6.4"}])
    out = rvs.run(root=spoke, registry_path=reg, report_dirs=[], apply=True)

    assert out["self_stamped"] is False
    assert out["applied"] == 0
    # A spoke's manifest carries no byte-verify; only its upgrade report may speak for it.
    assert json.loads(reg.read_text())["wheels"][0]["harness_version"] == "4.6.4"
