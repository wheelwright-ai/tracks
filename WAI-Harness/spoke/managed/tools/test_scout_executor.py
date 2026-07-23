"""Test-at-birth for scout_executor.py --promote (draft -> ready promotion).

Proves the gap from impl-scout-draft-to-ready-promoter-v1: a valid draft is
validated then moved to ready/, an invalid draft is left in draft/ with a
clear error, and directory mode sweeps spoke_local/draft/ in one call.
"""
import json
from pathlib import Path

import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scout_executor as se


VALID_SCOUT = {
    "id": "scout-test-promote-v1",
    "name": "Test Promote Scout",
    "description": "A minimal valid scout job for --promote tests.",
    "owner": "test-owner",
    "scope": "spoke_local",
    "status": "draft",
    "prompt_template": "Say PASS. {input}",
    "model_class": "small",
}


def _wire_dirs(tmp_path, monkeypatch):
    draft = tmp_path / "draft"
    ready = tmp_path / "ready"
    draft.mkdir()
    monkeypatch.setattr(se, "SCOUTS_SPOKE_DRAFT", draft)
    monkeypatch.setattr(se, "SCOUTS_SPOKE_READY", ready)
    return draft, ready


def test_promote_valid_draft_moves_to_ready(tmp_path, monkeypatch):
    draft, ready = _wire_dirs(tmp_path, monkeypatch)
    draft_file = draft / "scout-test-promote-v1.json"
    draft_file.write_text(json.dumps(VALID_SCOUT))

    status, msg = se.promote_one(draft_file)

    assert status == "PROMOTED"
    assert not draft_file.exists()
    assert (ready / "scout-test-promote-v1.json").exists()


def test_promote_invalid_draft_stays_in_draft(tmp_path, monkeypatch):
    draft, ready = _wire_dirs(tmp_path, monkeypatch)
    bad = dict(VALID_SCOUT)
    del bad["prompt_template"]  # required field missing -> fails schema
    draft_file = draft / "scout-bad-v1.json"
    draft_file.write_text(json.dumps(bad))

    status, msg = se.promote_one(draft_file)

    assert status == "ERROR"
    assert "prompt_template" in msg
    assert draft_file.exists()
    assert not (ready / "scout-bad-v1.json").exists()


def test_promote_directory_mode_sweeps_all_drafts(tmp_path, monkeypatch):
    draft, ready = _wire_dirs(tmp_path, monkeypatch)
    good = dict(VALID_SCOUT)
    (draft / "scout-good-v1.json").write_text(json.dumps(good))

    bad = dict(VALID_SCOUT, id="scout-bad-v1")
    del bad["owner"]
    bad_file = draft / "scout-bad-v1.json"
    bad_file.write_text(json.dumps(bad))

    counts = se.promote(None)  # no arg -> defaults to SCOUTS_SPOKE_DRAFT

    assert counts == {"promoted": 1, "skipped": 0, "errors": 1}
    assert (ready / "scout-good-v1.json").exists()
    assert bad_file.exists()  # invalid draft left in place


def test_promote_creates_ready_dir_if_absent(tmp_path, monkeypatch):
    draft, ready = _wire_dirs(tmp_path, monkeypatch)
    assert not ready.exists()
    draft_file = draft / "scout-test-promote-v1.json"
    draft_file.write_text(json.dumps(VALID_SCOUT))

    se.promote_one(draft_file)

    assert ready.is_dir()
