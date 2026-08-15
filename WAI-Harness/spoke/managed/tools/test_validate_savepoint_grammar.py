#!/usr/bin/env python3
"""Locks extract_command's grammar: the `cmd:` label must not cost an author evidence.

WHY THIS FILE EXISTS. On 2026-08-14 a savepoint on ezorg-email-website failed the
resume contract three times while carrying correct, re-runnable checks. Every one was
written in the documented house style, `cmd: <command>`, and extract_command never
stripped that label -- so the whole-field path saw `cmd:` as its head token, declined,
and left only the bounded mid-string search, which fires only when a command happens to
end in a dotted filename. `grep -q x CLAUDE.md` slipped through; `curl ... https://...`,
`git show --stat <sha>`, `test ! -d <dir>` and `python3 -c "..."` did not.

The damage is to author behaviour, not to a number. Told they recorded no evidence, the
honest repairs available are to set verified=false or to downgrade to a weaker file
path -- so a gate built to demand commands was pushing authors away from them.

validate_savepoint and savepoint_walk share this ONE function by import. A divergent
second copy is what produced the 23/48 false "uncheckable" verdicts recorded in
savepoint_walk's own comments, so the guarantee under test is behavioural, not textual.

Run: python3 test_validate_savepoint_grammar.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_savepoint import extract_command  # noqa: E402

# (verification string, expect_command) -- True means "must yield a command".
CASES = [
    # The regression. Each of these was accepted bare and REJECTED with the prefix
    # the author was instructed to use. Measured, not hypothetical.
    ("cmd: test ! -d api/admin/impersonate", True),
    ("cmd: curl -s -o /dev/null https://ezorg.email/", True),
    ("cmd: git show --stat 5ec7fdc2", True),
    ('cmd: python3 -c "import sys; sys.exit(0)"', True),
    ("cmd: grep -q 'wai-exit sec 1c' CLAUDE.md", True),

    # The other accepted labels.
    ("command: node e2e/board-workspace/full-loop-ui.mjs", True),
    ("run: pytest -q tests/", True),
    ("shell: make check", True),
    ("verify: npx vitest run", True),
    ("CMD:   ls -la", True),          # case and padding are not meaningful

    # Bare commands must keep working -- the label is optional, never required.
    ("grep -q wai-exit CLAUDE.md", True),
    ("node e2e/board-workspace/full-loop-ui.mjs", True),

    # Piping and quoting must survive: the whole-field path is the one that keeps
    # them, and it is precisely the path the unstripped label was blocking.
    ("cmd: grep -l X logs/*.txt | wc -l", True),

    # Prose stays rejected. The label must not launder a sentence into a command.
    ("confirmed by reading the diff", False),
    ("cmd: ls some/dir/ is empty; 37 files now under completed/", False),
    ("cmd: the walker confirms the message survives compaction", False),
    ("run: this should be checked by hand", False),

    # A path is evidence, but it is not a COMMAND -- extract_command declines it and
    # _has_rerunnable_check accepts it separately. Guards against the fix widening.
    ("file: WAI-Harness/spoke/local/WAI-State.json", False),

    # Empty and junk.
    ("", False),
    ("   ", False),
    ("cmd:", False),

    # Only ONE label is stripped, and only at the head: a command whose own argument
    # mentions cmd: must reach the shell intact.
    ("cmd: grep -q 'cmd: run this' notes.md", True),
]


def main():
    failures = []
    for text, want_cmd in CASES:
        got = extract_command(text)
        ok = (got is not None) if want_cmd else (got is None)
        if not ok:
            failures.append((text, want_cmd, got))
        print("  %-5s %-46s <- %s" % ("PASS" if ok else "FAIL",
                                      str(got)[:44], text[:52]))

    # The label must not change WHAT runs, only whether it is found. Same command,
    # with and without the prefix, must extract identically.
    for bare in ("test ! -d api/admin/impersonate",
                 "curl -s -o /dev/null https://ezorg.email/",
                 "grep -l X logs/*.txt | wc -l"):
        a, b = extract_command(bare), extract_command("cmd: " + bare)
        if a != b:
            failures.append(("label changed the command: %r" % bare, a, b))
            print("  FAIL  label altered the command: %r vs %r" % (a, b))

    if failures:
        print("\n%d FAILED" % len(failures))
        for f in failures:
            print("   ", f)
        return 1
    print("\nALL %d PASS" % (len(CASES) + 3))
    return 0


def test_savepoint_grammar():
    """pytest entry point. Without this the file is named test_* but collects ZERO
    tests, so the suite reports green while never executing a single case here."""
    assert main() == 0


# ---------------------------------------------------------------------------
# WRITER-GATE tests, absorbed from the basher fork 2026-08-14.
#
# WHY THIS MERGE HAPPENED: basher's upgrade to harness 4.14.54 FAILED six times in
# three hours, each time refusing with "NET SYMBOL LOSS ... this pull would revert
# symbols" and naming these twelve tests. The guard was right. Canon carried a 25-case
# CASES table for extract_command and NOTHING for the writer gate; basher carried the
# writer-gate tests and none of the parsing table. Neither file was a superset, so
# distributing canon would have destroyed twelve real tests on the receiving spoke.
# Canon is now the UNION. Distribution can only be safe when the master is the richest
# copy -- otherwise every fan-out is a silent regression the guard has to catch.
#
# These use their own importlib loader (vs.*) rather than the module-level import
# above, kept verbatim from the fork so the absorbed tests are diff-checkable.
# ---------------------------------------------------------------------------
import importlib.util
import pathlib

_SPEC = importlib.util.spec_from_file_location(
    "validate_savepoint", pathlib.Path(__file__).with_name("validate_savepoint.py"))
vs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(vs)


def test_annotated_command_is_accepted_and_normalised():
    """The annotation is authorial habit, not a defect — accept it, strip it."""
    assert vs.extract_command("python3 -m pytest -q tools/test_x.py  (17 passed)") \
        == "python3 -m pytest -q tools/test_x.py"


def test_unparseable_prose_is_not_a_command():
    assert vs.extract_command(
        "git show-ref --verify --quiet refs/heads/x returns non-zero (branch gone), and more") is None


def test_pure_prose_is_not_a_command():
    assert vs.extract_command("confirmed by reading the diff") is None


def test_writer_gate_rejects_a_claim_backed_only_by_unparseable_prose():
    item = {"verified": True,
            "verification": "git show-ref --verify --quiet refs/heads/x returns non-zero (gone), and more"}
    assert not vs._has_rerunnable_check(item), \
        "an unparseable string was accepted as re-runnable evidence at write time"


def test_writer_gate_accepts_a_real_command():
    assert vs._has_rerunnable_check(
        {"verified": True, "verification": "python3 -m pytest -q tools/test_x.py"})


def test_writer_gate_still_accepts_a_path_and_a_sha():
    assert vs._has_rerunnable_check({"verified": True, "verification": "tools/thing.py"})
    assert vs._has_rerunnable_check({"verified": True, "evidence": "commit c0255607"})


def test_shell_parses_never_executes():
    """`bash -n` must not run the command — a side effect here would be catastrophic."""
    import tempfile, os
    d = tempfile.mkdtemp()
    target = os.path.join(d, "SHOULD_NOT_EXIST")
    vs.shell_parses(f"touch {target}")
    assert not os.path.exists(target), "shell_parses EXECUTED the command"


def test_python_one_liner_with_assert_is_a_command():
    """`assert` is a Python keyword, not prose. `python3 -c "...; assert ..."` is one
    of the most natural one-liner verifications an author can write, and an earlier
    version of _PROSE_MARKER_RE refused it — punishing exactly the right behaviour.
    Caught while composing this session's own savepoint."""
    cmd = 'python3 -c "import glob; assert len(glob.glob(\'a/*.json\')) >= 8"'
    assert vs.extract_command(cmd) == cmd, vs.extract_command(cmd)


def test_prose_using_the_word_asserts_is_still_rejected():
    """Guard the removal: the prose case `assert` was meant to catch is already
    rejected by the head-token check, because its first word is not a command."""
    assert vs.extract_command(
        "test_turn_counter_and_emit asserts the message survives a dead stderr") is None


def test_a_valid_command_is_not_rejected_by_its_prose_evidence():
    """A BUG I SHIPPED WITH THE PARSE RULE ITSELF. _has_rerunnable_check joined
    verification + evidence and asked whether THAT parsed as shell. Evidence is prose
    by design, so the join can essentially never parse — a perfectly good command was
    rejected whenever its evidence contained no repo-rooted path to satisfy the
    fallback. It rejected two entries of the very savepoint that shipped the rule.
    The command question belongs to `verification` alone."""
    item = {"verified": True,
            "verification": 'test 0 -eq "$(grep -c foo /abs/path/outside/repo.sh)"',
            "evidence": "verified mywheel and pathfinder hooks contain 0 occurrences"}
    assert vs._has_rerunnable_check(item), \
        "prose evidence must not invalidate a command that parses on its own"


def test_a_sha_in_evidence_alone_still_counts():
    """The blob is still right for path/sha: a commit cited in evidence IS checkable."""
    assert vs._has_rerunnable_check(
        {"verified": True, "verification": "confirmed by reading it",
         "evidence": "commit c0255607"})


def test_prose_in_both_fields_is_still_rejected():
    assert not vs._has_rerunnable_check(
        {"verified": True, "verification": "looked at it", "evidence": "seemed fine"})


if __name__ == "__main__":
    sys.exit(main())
