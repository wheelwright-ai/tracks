"""A spoke holding an ahead-pin must still be able to certify itself.

THE DEADLOCK. harness_upgrade has two halves that must agree about what a pinned file
is supposed to look like:

  * compute_home_map()/apply() are direction-aware. A file named in the spoke's
    harness-ahead.json is a deliberate local fix with a change-lug in flight to canon,
    so apply() reports it and does NOT overwrite it. That is the entire point of the
    ledger — without it every pull reverts the spoke's own fixes.

  * verify() recomputed md5 against the manifest and knew nothing about the ledger.
    Every pin apply() correctly refused to clobber therefore came back a MISMATCH, and
    verify_post_ok went false BECAUSE the upgrade had done the right thing.

Unwinnable, not flaky: a spoke with any pin could never self-certify. MEASURED on
basher, the distributor spoke, 2026-08-05 — 5 upgrade-reports for 4.14.46 across two
days, every one "981 file(s) applied; bytes MISMATCHED", with 3 of the 5 named
mismatches being declared pins carrying change-lugs already sent to canon. And since
registry_version_stamp's evidence gate requires verify_post_ok, basher could not prove
its own version either, so the fleet's registry column stayed fiction.

These tests fix the CONTRACT, not the incident: verify() must classify a pinned
difference as `ahead`, must not let it poison `ok`, must still catch an unpinned one,
and must stay strict when no ledger is passed.
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_upgrade as hu  # noqa: E402


def _md5(p):
    return hashlib.md5(Path(p).read_bytes()).hexdigest()


@pytest.fixture
def tree(tmp_path):
    """A managed root with two files and a manifest that matches, then both edited."""
    managed = tmp_path / "managed"
    managed.mkdir()
    pinned = managed / "tools" / "pinned.py"
    plain = managed / "tools" / "plain.py"
    pinned.parent.mkdir(parents=True)
    pinned.write_text("canon version\n")
    plain.write_text("canon version\n")
    manifest = {"files": {
        "tools/pinned.py": {"md5": _md5(pinned)},
        "tools/plain.py": {"md5": _md5(plain)},
    }}
    return {"managed": managed, "manifest": manifest, "pinned": pinned, "plain": plain}


def test_a_pinned_difference_is_ahead_not_a_mismatch(tree):
    tree["pinned"].write_text("spoke fixed this ahead of canon\n")
    pins = {"tools/pinned.py": {"change_lug": "change-canon-something-v1",
                                "reason": "fix in flight"}}
    r = hu.verify(str(tree["managed"]), tree["manifest"], pins=pins)

    assert r["ok"] is True, "a declared ahead-pin must not fail the verdict"
    assert [a["file"] for a in r["ahead"]] == ["tools/pinned.py"]
    assert r["mismatches"] == []
    # The lug travels with the finding — a bare 'ahead' with no upstream reference is
    # indistinguishable from a fork, which is what the ledger exists to prevent.
    assert r["ahead"][0]["change_lug"] == "change-canon-something-v1"


def test_an_unpinned_difference_is_still_a_mismatch(tree):
    """The exemption must be narrow. Undeclared drift is exactly what verify is for."""
    tree["plain"].write_text("someone edited this without declaring it\n")
    pins = {"tools/pinned.py": {"change_lug": "change-canon-something-v1"}}
    r = hu.verify(str(tree["managed"]), tree["manifest"], pins=pins)

    assert r["ok"] is False
    assert [m["file"] for m in r["mismatches"]] == ["tools/plain.py"]
    assert r["ahead"] == []


def test_no_ledger_means_strict_byte_check(tree):
    """Callers that want a raw comparison (the certifier's extract check) keep it."""
    tree["pinned"].write_text("spoke fixed this ahead of canon\n")
    r = hu.verify(str(tree["managed"]), tree["manifest"])

    assert r["ok"] is False
    assert [m["file"] for m in r["mismatches"]] == ["tools/pinned.py"]
    assert r["ahead"] == []


def test_a_missing_file_still_fails_even_if_pinned(tree):
    """A pin says 'this file differs deliberately', never 'this file may be absent'."""
    tree["pinned"].unlink()
    pins = {"tools/pinned.py": {"change_lug": "change-canon-something-v1"}}
    r = hu.verify(str(tree["managed"]), tree["manifest"], pins=pins)

    assert r["ok"] is False
    assert r["missing"] == ["tools/pinned.py"]


def test_pin_auto_retires_when_canon_catches_up(tree):
    """A pin cannot become a permanent exemption.

    load_ahead_ledger drops a pin once master's bytes match the spoke's. Here the file
    matches the manifest, so it is not a difference at all and must appear in neither
    bucket — the exemption evaporates on its own rather than needing a cleanup pass.
    """
    pins = {"tools/pinned.py": {"change_lug": "change-canon-something-v1"}}
    r = hu.verify(str(tree["managed"]), tree["manifest"], pins=pins)

    assert r["ok"] is True
    assert r["ahead"] == []
    assert r["mismatches"] == []


def test_basher_own_tree_certifies(tmp_path):
    """The live regression, against basher's real tree and real ledger.

    This is the assertion the 5 failed upgrade-reports would have caught. It reads the
    repo read-only.
    """
    repo = Path(__file__).resolve().parents[4]
    managed = repo / "WAI-Harness" / "spoke" / "managed"
    manifest_path = managed / "MANIFEST.json"
    ledger = managed / "harness-ahead.json"
    if not manifest_path.exists() or not ledger.exists():
        pytest.skip("not a spoke tree with a manifest and an ahead ledger")

    manifest = json.loads(manifest_path.read_text())
    pins, err = hu.load_ahead_ledger(str(managed))
    assert err is None, f"ahead ledger unreadable: {err}"

    r = hu.verify(str(managed), manifest, pins=pins)
    assert r["ok"] is True, (
        "basher cannot self-certify. Undeclared mismatches: "
        + ", ".join(m["file"] for m in r["mismatches"])
        + ". Either the change is wanted (declare it in harness-ahead.json with the "
          "change-lug sent to canon) or it is drift (revert it)."
    )
