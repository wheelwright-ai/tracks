"""Test-at-birth for symbol_loss.py (impl-detect-harness-pull-reverts-before-they-commit-v1).

Covers: real loss detected, no false positive on pure addition, the documented
rename decision, and the WAI_ALLOW_SYMBOL_LOSS override path through
harness_upgrade.upgrade()'s NET SYMBOL LOSS gate.
"""
import json
import os
import pathlib
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import symbol_loss
import harness_upgrade as hu


# ---------------------------------------------------------------------------
# Python symbol extraction / diffing
# ---------------------------------------------------------------------------

def test_python_symbols_top_level_only():
    text = (
        "def alpha():\n"
        "    def nested():\n"
        "        pass\n"
        "    return nested\n"
        "\n"
        "class Beta:\n"
        "    def method(self):\n"
        "        pass\n"
    )
    syms = symbol_loss.python_symbols(text)
    # top-level only: nested() and Beta.method are NOT top-level names.
    assert syms == {"alpha", "Beta"}


def test_loss_detected():
    before = "def screen_command(cmd):\n    pass\n\ndef other():\n    pass\n"
    after = "def other():\n    pass\n"
    result = symbol_loss.diff_symbols(before, after, "thread_landing.py")
    assert result["lost"] == ["screen_command"]
    assert result["gained"] == []


def test_no_false_positive_on_pure_addition():
    """Adding a NEW function/class must never register as a loss."""
    before = "def existing():\n    pass\n"
    after = "def existing():\n    pass\n\ndef brand_new():\n    pass\n"
    result = symbol_loss.diff_symbols(before, after, "some_tool.py")
    assert result["lost"] == []
    assert result["gained"] == ["brand_new"]


def test_rename_reports_as_loss_by_design():
    """DECISION (documented, not a bug): a rename genuinely removes the old name
    and adds a new one. This module has no notion of "this def became that def"
    -- it only knows names that existed and now don't -- so a rename shows up as
    ONE lost symbol and ONE gained symbol, exactly like a real deletion-plus-
    unrelated-addition would.

    This is deliberately the SAFE default for a revert-detection guard: at pull
    time the caller cannot tell "an intentional rename shipped upstream" from
    "the old name was reverted away and a coincidentally-named new function
    landed" without semantic/history information this module does not have.
    Flagging a rename as a loss means an operator momentarily has to confirm a
    rename via WAI_ALLOW_SYMBOL_LOSS=1 (or the pre-commit override) -- a small
    known cost -- rather than the guard silently waving through a real revert
    that happens to also add an unrelated symbol. False positive here is far
    cheaper than the false negative it would otherwise risk.
    """
    before = "def old_name(x):\n    return x\n"
    after = "def new_name(x):\n    return x\n"
    result = symbol_loss.diff_symbols(before, after, "renamed.py")
    assert result["lost"] == ["old_name"]
    assert result["gained"] == ["new_name"]


def test_shell_symbols_detected():
    before = "screen_command() {\n  echo hi\n}\n\nfunction other {\n  :\n}\n"
    after = "function other {\n  :\n}\n"
    result = symbol_loss.diff_symbols(before, after, "wakeup-canonical.sh")
    assert result["lost"] == ["screen_command"]


def test_unparseable_python_never_raises():
    # after-text is broken python -> ast.parse raises inside symbols_for(),
    # yielding an empty symbol set for that side rather than propagating the
    # SyntaxError. Since an empty after-side can't be proven to still contain
    # any before-side name, this is conservatively (and correctly) reported as
    # loss of everything before — a corrupted/unparseable after-text is exactly
    # the kind of thing a revert-detection guard should be loud about, not the
    # kind of case it should silently pass. The contract under test is "does
    # not crash", not "reports nothing".
    before = "def a():\n    pass\n"
    after = "def a(:\n    this is not python\n"
    result = symbol_loss.diff_symbols(before, after, "broken.py")
    assert result["lost"] == ["a"]


def test_non_code_file_yields_no_symbols():
    result = symbol_loss.diff_symbols("old text\n", "new text\n", "notes.md")
    assert result == {"lost": [], "gained": []}


def test_scan_for_loss_only_returns_files_with_loss():
    pairs = [
        ("clean.py", "def a():\n    pass\n", "def a():\n    pass\n"),
        ("bad.py", "def a():\n    pass\n\ndef b():\n    pass\n", "def a():\n    pass\n"),
    ]
    out = symbol_loss.scan_for_loss(pairs)
    assert out == {"bad.py": ["b"]}


# ---------------------------------------------------------------------------
# The real incident: thread_landing.py's screen_command loss (session-120)
# ---------------------------------------------------------------------------

GOOD_SHA = "2669698e"   # commit holding the good (pre-revert) thread_landing.py
BAD_SHA = "e76f27f5"    # commit that committed the revert
INCIDENT_PATH = "WAI-Harness/spoke/managed/tools/thread_landing.py"


def _git_show(sha, path):
    import subprocess
    repo_root = Path(__file__).resolve().parents[4]  # tools/ -> managed -> spoke -> WAI-Harness -> repo root
    r = subprocess.run(["git", "-C", str(repo_root), "show", f"{sha}:{path}"],
                       capture_output=True, text=True, timeout=10)
    return r.stdout if r.returncode == 0 else None


def test_real_incident_reverted_thread_landing_loses_screen_command():
    """Reproduces the ACTUAL session-120 incident from git history: GOOD_SHA
    holds the good (pre-revert) thread_landing.py, BAD_SHA is the commit that
    silently reverted it. Proves the detector names screen_command as lost —
    the exact case this guard exists for. Skips (never fails the suite) if
    this checkout lacks those commits (e.g. a shallow clone)."""
    before = _git_show(GOOD_SHA, INCIDENT_PATH)
    after = _git_show(BAD_SHA, INCIDENT_PATH)
    if before is None or after is None:
        import pytest
        pytest.skip(f"commits {GOOD_SHA}/{BAD_SHA} not available in this checkout")
    result = symbol_loss.diff_symbols(before, after, "thread_landing.py")
    assert "screen_command" in result["lost"]


# ---------------------------------------------------------------------------
# harness_upgrade.py wiring: halt + override, end to end
# ---------------------------------------------------------------------------

def _make_master(root, files):
    managed = Path(root) / "managed"
    for rel, txt in files.items():
        p = managed / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt)
    m = hu.build_manifest(managed, generated_at="2026-01-01T00:00:00Z")
    (managed / hu.MANIFEST_NAME).write_text(json.dumps(m, indent=2) + "\n")
    return managed


def test_upgrade_halts_on_symbol_loss_and_writes_no_bytes(tmp_path, monkeypatch):
    monkeypatch.delenv("WAI_ALLOW_SYMBOL_LOSS", raising=False)
    good = "def screen_command(cmd):\n    pass\n\ndef other():\n    pass\n"
    bad = "def other():\n    pass\n"
    master = _make_master(tmp_path / "master", {"tools/thread_landing.py": bad})
    target = tmp_path / "target" / "managed"
    (target / "tools").mkdir(parents=True, exist_ok=True)
    (target / "tools" / "thread_landing.py").write_text(good)
    # target's prior manifest = the master's manifest, so home_map sees this as
    # a genuine CHANGE (not an untracked add).
    (target / hu.MANIFEST_NAME).write_text((master / hu.MANIFEST_NAME).read_text())

    rep = hu.upgrade(master, target, dry_run=False, validate=False)

    assert rep["ok"] is False
    assert "screen_command" in rep["symbol_loss"]["tools/thread_landing.py"]
    assert "NET SYMBOL LOSS" in rep["aborted"]
    assert (target / "tools" / "thread_landing.py").read_text() == good  # untouched

    ledger = json.loads((target / hu.AHEAD_LEDGER).read_text())
    assert len(ledger["halts"]) == 1
    assert ledger["halts"][0]["overridden"] is False
    assert "screen_command" in ledger["halts"][0]["losses"]["tools/thread_landing.py"]


def test_upgrade_override_env_lets_deliberate_removal_through(tmp_path, monkeypatch):
    monkeypatch.setenv("WAI_ALLOW_SYMBOL_LOSS", "1")
    good = "def screen_command(cmd):\n    pass\n\ndef other():\n    pass\n"
    bad = "def other():\n    pass\n"
    master = _make_master(tmp_path / "master", {"tools/thread_landing.py": bad})
    target = tmp_path / "target" / "managed"
    (target / "tools").mkdir(parents=True, exist_ok=True)
    (target / "tools" / "thread_landing.py").write_text(good)
    (target / hu.MANIFEST_NAME).write_text((master / hu.MANIFEST_NAME).read_text())

    rep = hu.upgrade(master, target, dry_run=False, validate=False)

    assert rep["ok"] is True
    assert rep["symbol_loss_overridden"] is True
    assert (target / "tools" / "thread_landing.py").read_text() == bad  # applied

    ledger = json.loads((target / hu.AHEAD_LEDGER).read_text())
    assert len(ledger["halts"]) == 1
    assert ledger["halts"][0]["overridden"] is True


def test_upgrade_clean_when_no_loss(tmp_path, monkeypatch):
    monkeypatch.delenv("WAI_ALLOW_SYMBOL_LOSS", raising=False)
    master = _make_master(tmp_path / "master",
                          {"tools/a.py": "def a():\n    pass\n\ndef b():\n    pass\n"})
    target = tmp_path / "target" / "managed"
    (target / "tools").mkdir(parents=True, exist_ok=True)
    (target / "tools" / "a.py").write_text("def a():\n    pass\n")  # pure addition upstream
    (target / hu.MANIFEST_NAME).write_text((master / hu.MANIFEST_NAME).read_text())

    rep = hu.upgrade(master, target, dry_run=False, validate=False)

    assert rep["ok"] is True
    assert rep["symbol_loss"] == {}
    assert not (target / hu.AHEAD_LEDGER).exists()


# ---------------------------------------------------------------------------
# DECLARED SUPERSESSIONS
#
# The test above records the safe default and its known cost: "an operator
# momentarily has to confirm a rename via WAI_ALLOW_SYMBOL_LOSS=1". Measured
# 2026-08-11, that cost was not momentary. hub could not upgrade at all, and
# every spoke on an older cut would have refused for the same two names
# forever, because the rename shipped in canon and the alarm never expires.
#
# The default stays exactly as it was. What is added is a way for the AUTHOR to
# state, in canon, next to the code, that a specific name became a specific
# other name. Not detection -- a declaration. Body-similarity matching was the
# alternative and it is a guess, and this module exists because guessing about
# regressions is how the regressions got through.
# ---------------------------------------------------------------------------

def test_a_declared_rename_is_forgiven():
    before = "def old_name(x):\n    return x\n"
    after = "def new_name(x):\n    return x\n"
    lost = symbol_loss.net_symbol_loss(before, after, "t.py",
                                       supersessions={"old_name": "new_name"})
    assert lost == []


def test_a_declaration_whose_successor_never_ARRIVED_does_not_forgive():
    """THE LOAD-BEARING HALF. Without it a stale line in the declaration file
    would mask a genuine deletion forever, and the escape hatch would quietly
    become a permanent hole in the guard. The successor must actually be in the
    new text before the old name is forgiven."""
    before = "def old_name(x):\n    return x\n"
    after = "def something_else(x):\n    return x\n"
    lost = symbol_loss.net_symbol_loss(before, after, "t.py",
                                       supersessions={"old_name": "new_name"})
    assert lost == ["old_name"]


def test_an_undeclared_rename_still_reports_as_loss():
    """The default must not move. Only what is declared is forgiven."""
    before = "def old_name(x):\n    return x\n"
    after = "def new_name(x):\n    return x\n"
    assert symbol_loss.net_symbol_loss(before, after, "t.py",
                                       supersessions={"unrelated": "other"}) == ["old_name"]


def test_a_real_deletion_beside_a_declared_rename_still_halts():
    """A declaration forgives ONE name. It must not become a per-file amnesty."""
    before = ("def old_name(x):\n    return x\n\n\n"
              "def genuinely_deleted(y):\n    return y\n")
    after = "def new_name(x):\n    return x\n"
    lost = symbol_loss.net_symbol_loss(before, after, "t.py",
                                       supersessions={"old_name": "new_name"})
    assert lost == ["genuinely_deleted"]


def test_no_declarations_behaves_exactly_as_before(tmp_path):
    before = "def old_name(x):\n    return x\n"
    after = "def new_name(x):\n    return x\n"
    assert symbol_loss.net_symbol_loss(before, after, "t.py") == ["old_name"]
    assert symbol_loss.net_symbol_loss(before, after, "t.py", supersessions=None) == ["old_name"]
    assert symbol_loss.load_supersessions(tmp_path) == {}


def test_the_declaration_file_is_read_per_file(tmp_path):
    (tmp_path / symbol_loss.SUPERSESSION_FILE).write_text(json.dumps({
        "supersessions": [
            {"file": "tools/a.py", "was": "gone", "now": "arrived", "why": "renamed"},
        ]}))
    declared = symbol_loss.load_supersessions(tmp_path)
    assert declared == {"tools/a.py": {"gone": "arrived"}}
    before, after = "def gone():\n    pass\n", "def arrived():\n    pass\n"
    assert symbol_loss.net_symbol_loss(before, after, "tools/a.py",
                                       supersessions=declared.get("tools/a.py")) == []
    # A different file with the same symbol names is NOT covered by that entry.
    assert symbol_loss.net_symbol_loss(before, after, "tools/b.py",
                                       supersessions=declared.get("tools/b.py")) == ["gone"]


def test_an_unreadable_declaration_file_is_empty_not_fatal(tmp_path):
    (tmp_path / symbol_loss.SUPERSESSION_FILE).write_text("{not json")
    assert symbol_loss.load_supersessions(tmp_path) == {}


def test_the_shipped_declarations_name_symbols_that_actually_exist():
    """Guards the canon file itself. A declaration pointing at a successor nobody
    wrote forgives nothing and silently rots -- so assert the successors are real."""
    here = pathlib.Path(__file__).resolve().parent
    declared = symbol_loss.load_supersessions(here.parent)
    assert declared, "the master ships no supersession declarations"
    for rel, mapping in declared.items():
        target = here.parent / rel
        assert target.is_file(), f"{rel} is declared but does not exist"
        present = symbol_loss.symbols_for(target.read_text(encoding="utf-8"), rel)
        for was, now in mapping.items():
            assert now in present, f"{rel}: declared successor {now!r} is not in the file"
            assert was not in present, f"{rel}: {was!r} still exists, so it was not superseded"
