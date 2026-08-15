#!/usr/bin/env python3
"""Resume-contract gate for savepoints (spec-savepoint-resume-contract-v1).

A savepoint is a RESUME CONTRACT, not a summary (P12 Resumable Completeness).
This is the deterministic, mechanical half of the gate (spec-ceremony-lean-v1:
mechanical work extracted to a script; the wai-savepoint skill is the thin
judgment wrapper that composes the fields and calls this before writing).

The contract test: a fresh no-context agent must resume and act, asking the user
nothing knowable at save time. This module asserts the STRUCTURAL preconditions
of that test:

  - first_actions non-empty (the resuming agent has an executable first step)
  - every deferred[].where_captured resolves to a real lug/file (nothing "lost")
  - every pending_handoffs[] carries how_to_verify AND fallback_if_not_done
  - every work_done[] item with verified=false has a matching honest_flag
    ("probably done" banned, P2/P12)
  - paper_trail.topics and paper_trail.decisions non-empty when the session
    touched any lugs (empty arrays no longer acceptable)

It does NOT enforce any length cap (the v3 60-char resume_note cap is removed).

CLI:
    python3 tools/validate_savepoint.py <savepoint.json> [--spoke-root DIR]
    exit 0 = contract satisfied; exit 1 = failures (printed, one per line).
"""
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wai_paths  # noqa: E402  harness-mode root resolver (single source of truth)


# ─── ONE re-runnable-evidence grammar ────────────────────────────────────────
# validate_savepoint decides whether re-runnable evidence EXISTS; savepoint_walk
# decides how to RE-RUN it. They must never disagree — a gate that accepts what the
# auditor rejects creates records that look valid and audit as empty. They HAVE
# disagreed before: savepoint_walk's own comment records 23 of 48 false "uncheckable"
# verdicts from a divergent copy of these patterns. So the grammar is defined once,
# here, and imported there. Never redefine it.
#
# The verb and root lists were Python-only, which made the rule backwards on any
# JS/TS spoke: `npx vitest run lib/x.test.ts` — a genuinely re-runnable command — was
# rejected as prose, pressuring authors to either downgrade honest verified=true
# claims or reword real evidence to satisfy a regex. Both degrade the trail the rule
# exists to protect. (Reported from pathfinder, bug-savepoint-ceremony-tooling-gaps-v1.)
#
# The plain POSIX checks were missing, and they are the ones authors reach for most:
# `test -f X`, `grep -q NEEDLE file`, `diff a b`. Measured on basher 2026-08-01, 20 of
# the trail's verification fields were exactly these. They did not fail outright — they
# fell through to the PATH pattern and were re-checked as "does this file exist", which
# is strictly weaker than the check the author wrote. `grep -q retired_threads x.py`
# became "x.py exists", so the entry stayed green after the symbol it was asserting had
# been deleted. A verification silently downgraded to a weaker one is a false pass, and
# a false pass in the trail is worse than a gap: the gap prompts a backfill.
RERUNNABLE_VERBS = (
    r"python3?|pytest|bash|sh|make|"
    r"npx|npm|pnpm|yarn|bun|node|deno|vitest|jest|"
    r"go|cargo|dotnet|mvn|gradle|"
    r"ruff|mypy|tsc|eslint|curl|git|"
    r"test|grep|diff|cmp|ls|jq|find|wc|stat|readlink|awk|sed"
)

# Source roots a re-runnable path may live under. Python-shaped repos keep evidence
# in tools/tests/scripts; JS/TS spokes keep it in app/lib/components/src.
SOURCE_ROOTS = (
    r"WAI-Harness|tools|tests|test|spec|scripts|"
    r"src|lib|app|apps|components|pages|api|packages|cmd|internal|bin"
)

PATH_PATTERN = r"(?:%s)/[\w./-]+\.\w+" % SOURCE_ROOTS
SHA_PATTERN = r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b"


# ─── A COMMAND MUST BE A COMMAND ─────────────────────────────────────────────
# Measured on basher 2026-08-01, walking the full trail (120 savepoints, 299
# entries): 19 of 43 "drifted" verdicts were not drift at all. They were
# verification fields holding a real command with prose or a result annotation
# glued on, which no shell can parse:
#
#     python3 -m pytest -q .../test_harness_telemetry.py  (17 passed)
#     git show-ref --verify --quiet refs/heads/X returns non-zero (branch gone), …
#
# Both halves of the contract failed on these. The WRITER gate (_has_rerunnable_check)
# only asked "does a re-runnable VERB appear somewhere in the blob?", so the
# annotated string sailed through at save time. The WALKER then extracted the whole
# field, ran it, watched the shell reject the `(`, and reported the WORK as drifted —
# accusing landed, working code of having regressed.
#
# That is the failure the trail exists to prevent, committed by the trail itself. A
# check that cannot run is not evidence, and reporting it as drift is worse than
# reporting nothing: "uncheckable" tells the truth and prompts a backfill, while a
# false "drifted" sends someone to re-do finished work.
#
# So the grammar gains a third stage after find-and-truncate: PARSE IT. `bash -n`
# reads a command and reports syntax without executing it — an exact, zero-side-effect
# oracle for "is this a command or is it prose?". Anything that fails to parse is
# uncheckable by definition, and is now rejected at WRITE time rather than
# misreported at walk time.
#
# ONE grammar, two tools: savepoint_walk imports extract_command from here. Never
# reimplement it there — a divergent second copy is what produced the 23/48 false
# "uncheckable" verdicts recorded in that module's own comments.
_TRAILING_PARENS_RE = re.compile(r"\s+\([^()]*\)\s*$")
_RESULT_ARROW_RE = re.compile(r"\s+(?:=>|->)\s.*$", re.S)


def strip_result_annotation(cmd):
    """Drop a trailing '(17 passed)' / '=> 5' note authors append to a command.

    Deliberately only strips at the END and only a balanced, operator-free paren
    group, so a real shell construct — `(cd x && make)`, `foo $(bar)` — is never
    truncated into something that means something different when run.
    """
    prev = None
    while prev != cmd:
        prev = cmd
        cmd = _RESULT_ARROW_RE.sub("", cmd).rstrip()
        cmd = _TRAILING_PARENS_RE.sub("", cmd).rstrip()
    return cmd


def shell_parses(cmd):
    """True when bash can PARSE cmd. Never executes it (`bash -n` is read-only)."""
    if not cmd or not cmd.strip():
        return False
    try:
        return subprocess.run(
            ["bash", "-n", "-c", cmd], capture_output=True, timeout=10
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        # No bash, or the probe itself failed: do not manufacture a verdict from a
        # broken probe. Fall back to accepting — the walker will find out for real.
        return True


# Words that mean a human is describing a result rather than issuing a command.
# Needed because some prose HAPPENS to be valid shell: `ls some/dir/ is empty; 37
# files now under completed/` parses fine (two `;`-separated commands) and would run
# `37` — exit 127 — reporting the work as drifted. Parseability alone is necessary,
# not sufficient.
# NOTE: `assert` is deliberately NOT a marker. It is a Python keyword, and
# `python3 -c "...; assert ..."` is one of the most natural one-liner verifications
# an author can write — rejecting it as prose punishes exactly the right behaviour.
# Caught while composing this session's own savepoint, whose completed-savepoint
# count check was refused by this guard. Verified the word is not load-bearing: the
# prose case it was meant to catch ("test_turn_counter_and_emit asserts the message
# survives...") is already rejected by _HEAD_VERB_RE, since its head token is not a
# command. A guard that only fires where another guard already fired is not adding
# safety, it is adding false negatives.
_PROSE_MARKER_RE = re.compile(
    r"\b(is empty|returns? non-zero|returns? zero|now under|should be|"
    r"expected to|verified by|confirms?|no longer|still resolves)\b|,\s+and\s", re.I)

_HEAD_VERB_RE = re.compile(r"^\s*`?!?\s*\(?\s*(?:%s)\b" % RERUNNABLE_VERBS)

# `cmd: ` is the HOUSE STYLE for a verification, not decoration. Every lug in the
# fleet writes its verify steps as `cmd: <command>`, and the savepoint schema invites
# the same. This module never stripped that label, so the whole-field path — the good
# path, the one that keeps pipes and quoting intact — could not match: its first token
# was `cmd:`, not a verb. What survived was the bounded mid-string search, which only
# fires when the command happens to end in a dotted filename.
#
# Measured on ezorg-email-website 2026-08-14, five real verifications, each accepted
# bare and REJECTED with the prefix the author was told to use:
#   test ! -d api/admin/impersonate            bare ok / cmd: rejected
#   curl -s -o /dev/null https://ezorg.email/  bare ok / cmd: rejected
#   git show --stat 5ec7fdc2                   bare ok / cmd: rejected
#   python3 -c "import sys; sys.exit(0)"       bare ok / cmd: rejected
#   grep -q 'wai-exit sec 1c' CLAUDE.md        bare ok / cmd: rejected
#
# The cost is not cosmetic. A savepoint author who writes a correct, re-runnable check
# in the documented form is told they recorded no evidence, and the honest repairs are
# to downgrade verified to false or to swap in a weaker file path. A gate that pushes
# authors AWAY from commands is inverted: it degrades the very trail it exists to keep.
# Stripping the label is the whole fix. Deliberately anchored and single-shot, so a
# command whose own argument contains `cmd:` is untouched.
_COMMAND_LABEL_RE = re.compile(r"^\s*(?:cmd|command|run|shell|verify)\s*:\s*", re.I)


def _strip_command_label(v):
    """Drop one leading `cmd:`/`command:`/`run:`/`shell:`/`verify:` label."""
    return _COMMAND_LABEL_RE.sub("", v, count=1).strip()


def extract_command(verification, _patterns=None):
    """The one place a verification string becomes a runnable command, or nothing.

    Returns the command, or None when the field is prose / unparseable. Callers:
    savepoint_walk._classify (to RE-RUN it) and _has_rerunnable_check (to decide
    whether it counts as evidence at write time). They must never disagree.

    WHOLE FIELD FIRST, then the bounded patterns. Order matters and it is the
    opposite of what it used to be. The bounded patterns stop at the first token
    that does not look like part of a command, which is right for
    `pytest x.py  (17 passed)` but WRONG for `grep -l X logs/*.txt | wc -l`, where
    it truncates to `grep -l X dotfiles/.config` — a different command that means
    something else. Trying the whole field first is only safe because it must now
    survive both guards below; the old code used the whole field with NO parse check
    at all, which is what made it dangerous.
    """
    if not verification or not verification.strip():
        return None
    v = _strip_command_label(verification.strip())

    whole = strip_result_annotation(v)
    if (whole and not _PROSE_MARKER_RE.search(whole)
            and _HEAD_VERB_RE.match(whole) and shell_parses(whole)):
        return whole

    pats = _patterns if _patterns is not None else _command_patterns()
    for pat, anchored in pats:
        m = pat.match(v) if anchored else pat.search(v)
        if not m:
            continue
        cmd = strip_result_annotation(m.group(1).strip())
        if cmd and not _PROSE_MARKER_RE.search(cmd) and shell_parses(cmd):
            return cmd
    return None


def _command_patterns():
    """(regex, anchored) in priority order. Bounded patterns FIRST: they stop at
    the first sign of trailing prose, while the anchored whole-field pattern is
    greedy to end-of-string and is only safe once the others have declined."""
    global _CMD_PATTERNS
    if _CMD_PATTERNS is None:
        _CMD_PATTERNS = [
            # pytest, bounded: the charset now excludes '(' as well as ; | &. It did
            # not, so `pytest -q x.py  (17 passed)` was captured WHOLE — this greedy
            # pattern ran before the bounded one that would have handled it correctly,
            # defeating the module's own anti-prose design.
            (re.compile(r"(python3? -m pytest[^\n;|&()]*)"), False),
            (re.compile(r"((?:%s)(?:\s+[\w.@/-]+){0,4}\s+[\w./-]+\.\w+)" % RERUNNABLE_VERBS), False),
            (re.compile(r"^\s*`?((?:%s)\b[^\n`]+)`?\s*$" % RERUNNABLE_VERBS), True),
        ]
    return _CMD_PATTERNS


_CMD_PATTERNS = None


def _has_rerunnable_check(item):
    """Does this work_done entry record something a machine can re-run LATER?

    Intentionally the SAME conservative test savepoint_walk.py applies when it
    walks the trail, so the validator and the walker cannot disagree about what
    counts as evidence — a gate that accepts what the auditor rejects is worse
    than no gate, because it creates records that look valid and audit as empty.

    Accepts a shell/pytest command or a repo path. Rejects prose. `evidence` is
    checked too: a commit sha there is re-checkable even when `verification`
    reads as a human note.
    """
    verification = str(item.get("verification") or "")
    blob = " ".join(str(item.get(k) or "") for k in ("verification", "evidence"))
    if not blob.strip():
        return False
    # A COMMAND must actually parse as one. The old test was "does a re-runnable
    # verb appear anywhere in the blob", which accepted `pytest … (17 passed)` —
    # a string the walker then ran, failed, and reported as DRIFTED work.
    #
    # ASK THE COMMAND QUESTION OF `verification` ALONE. Asking it of the JOINED blob
    # was a bug I introduced with the parse requirement itself: evidence is prose by
    # design, so verification+evidence concatenated can essentially never parse as
    # shell, and a perfectly good command was rejected whenever its evidence happened
    # to contain no repo-rooted path to satisfy the fallback. It rejected two entries
    # of the very savepoint that shipped the rule. The blob is still right for the
    # path/sha fallbacks — a sha cited in evidence IS re-checkable.
    if extract_command(verification):
        return True
    return bool(
        re.search(PATH_PATTERN, blob)
        or re.search(SHA_PATTERN, blob)  # commit sha — ancestry is checkable
    )


def _is_nonempty_list(v):
    return isinstance(v, list) and len(v) > 0


def _lug_dirs(spoke_root):
    """The lug tree(s) to search for a captured lug, harness-mode-aware.
    The active harness's lugs dir is authoritative; in v3/coexist the legacy
    WAI-Spoke/lugs is included as a read-only fallback during the overlap window.
    In v4-only ($WAI_HARNESS_MODE=v4-only) only the v4 tree is consulted — zero
    WAI-Spoke access (spec-savepoint-resume-contract-v1 + V4-COMPLETE Phase B)."""
    dirs = []
    active = wai_paths.category(spoke_root, "lugs")
    if active:
        dirs.append(active)
    # overlap-window fallback: legacy v3 lugs, only when not forced v4-only
    if (os.environ.get("WAI_HARNESS_MODE", "").lower() not in ("v4", "v4-only", "v4only")):
        legacy = os.path.join(spoke_root, "WAI-Spoke", "lugs")
        if legacy not in dirs and os.path.isdir(legacy):
            dirs.append(legacy)
    return dirs


def resolve_capture(where_captured, spoke_root="."):
    """A deferred item is 'not lost' only if where_captured points to something
    that actually exists: an existing file path (relative to spoke_root or
    absolute), or a lug id discoverable under the active harness's lug tree."""
    if not where_captured or not isinstance(where_captured, str):
        return False
    wc = where_captured.strip()
    # 1. direct path (relative-from-root or absolute)
    if os.path.exists(wc) or os.path.exists(os.path.join(spoke_root, wc)):
        return True
    # 2. lug id: search the resolved lug tree(s) for {id}.json
    lug_id = wc[:-5] if wc.endswith(".json") else wc
    for d in _lug_dirs(spoke_root):
        if glob.glob(os.path.join(d, "**", lug_id + ".json"), recursive=True):
            return True
    return False


_DECISION_WORDS = (" pick ", " choose ", " decide ", " which ", " or ", "?")


def validate_resume_contract(sp, spoke_root="."):
    """Validate a savepoint dict against the resume contract.

    Returns {"ok": bool, "failures": [str,...], "warnings": [str,...]}. ok is True
    only when failures is empty (warnings never block). Pure (no writes) so the skill
    can call it before deciding to write.

    Hardened S45 after a resume session hit avoidable friction: a savepoint must say
    WHERE to work (workspace), its first action must be DECIDED (not a fork the resumer
    must stop and ask about), and it should snapshot the inbox + flag auth-gated steps.
    """
    failures = []
    warnings = []

    # --- first_actions: the resuming agent must have an executable first step ---
    fa = sp.get("first_actions")
    if not _is_nonempty_list(fa):
        failures.append(
            "first_actions empty — a resuming agent has no executable first step "
            "(thin savepoint rejected)"
        )
    else:
        for i, a in enumerate(fa):
            if not isinstance(a, dict) or not a.get("action"):
                failures.append(f"first_actions[{i}] missing 'action'")

    # --- work_done: itemized with evidence; unverified items need an honest_flag ---
    wd = sp.get("work_done")
    honest_flags = sp.get("honest_flags") or []
    if not _is_nonempty_list(wd):
        failures.append("work_done empty or not an itemized list (one-line summary banned)")
    else:
        has_unverified = False
        for i, item in enumerate(wd):
            if not isinstance(item, dict):
                failures.append(
                    f"work_done[{i}] is not an object {{what, evidence, verified}} "
                    "(thin string summary banned)"
                )
                continue
            if "verified" not in item:
                failures.append(f"work_done[{i}] missing 'verified' boolean")
            elif item.get("verified") is False:
                has_unverified = True
            elif item.get("verified") is True and not _has_rerunnable_check(item):
                # THE CLAIM-IS-NOT-EVIDENCE RULE (s138). Measured across the real
                # trail: 330 work entries, 8 with a re-runnable check, 100 marked
                # verified=true. ~98 entries asserted verification and recorded no
                # way to confirm it. That is the self-graded pattern the compliance
                # oracle exists to kill, sitting inside the record Ozi is meant to
                # walk back over and trust.
                #
                # A savepoint is the durable record. If "verified" can mean "I say
                # so", the trail is decoration. So verified=true must carry
                # something a machine can re-run later: a command, or a path.
                failures.append(
                    f"work_done[{i}] claims verified=true but records no RE-RUNNABLE check. "
                    "Put a command or a file path in 'verification' (prose like 'confirmed by "
                    "reading the diff' is a note, not evidence). If it genuinely cannot be "
                    "re-checked, set verified=false and add an honest_flag."
                )
        if has_unverified and not _is_nonempty_list(honest_flags):
            failures.append(
                "work_done has unverified item(s) (verified=false) but honest_flags "
                "is empty — 'probably done' is banned (P2/P12)"
            )

    # --- pending_handoffs: each must carry how_to_verify AND fallback ---
    for i, h in enumerate(sp.get("pending_handoffs") or []):
        if not isinstance(h, dict):
            failures.append(f"pending_handoffs[{i}] is not an object")
            continue
        if not h.get("how_to_verify"):
            failures.append(f"pending_handoffs[{i}] missing how_to_verify")
        if not h.get("fallback_if_not_done"):
            failures.append(
                f"pending_handoffs[{i}] missing fallback_if_not_done — "
                "re-creates the hand-feeding tax on the next session"
            )

    # --- deferred: every item must be captured somewhere that exists ---
    for i, d in enumerate(sp.get("deferred") or []):
        if not isinstance(d, dict):
            failures.append(f"deferred[{i}] is not an object")
            continue
        wc = d.get("where_captured")
        if not wc:
            failures.append(
                f"deferred[{i}] ('{d.get('item','?')}') missing where_captured — "
                "a deferred item with no capture is a LOST item"
            )
        elif not resolve_capture(wc, spoke_root):
            failures.append(
                f"deferred[{i}] where_captured '{wc}' does not resolve to an "
                "existing lug/file — lost item"
            )

    # --- paper_trail.topics/decisions: non-empty when the session touched lugs ---
    # HALT AND NAME THE SHAPE, never crash. paper_trail is an object; a savepoint that
    # writes it as a list used to take this function out with an unhandled
    # AttributeError ('list' object has no attribute 'get') instead of reporting a
    # schema violation. Measured 2026-08-14 while dogfooding this validator on a
    # hand-written savepoint. A validator that tracebacks tells the author nothing about
    # what it wanted, which is the same failure as demoting an unrecognised shape into a
    # queue nobody reads.
    pt = sp.get("paper_trail") or {}
    if not isinstance(pt, dict):
        failures.append(
            f"paper_trail must be an object, got {type(pt).__name__} — expected keys: "
            "lugs_completed, lugs_opened, lugs_in_flight, topics, decisions"
        )
        pt = {}
    touched = bool((pt.get("lugs_completed") or []) or (pt.get("lugs_opened") or [])
                   or (pt.get("lugs_in_flight") or []))
    if touched:
        if not _is_nonempty_list(pt.get("topics")):
            failures.append(
                "paper_trail.topics empty for a session that touched lugs "
                "(empty arrays no longer acceptable)"
            )
        if not _is_nonempty_list(pt.get("decisions")):
            failures.append(
                "paper_trail.decisions empty for a session that touched lugs "
                "(empty arrays no longer acceptable)"
            )

    # --- workspace: WHERE to work must be stated (removes framework-vs-mywheel ambiguity) ---
    ws = sp.get("workspace")
    if not (isinstance(ws, dict) and ws.get("path")) and not (isinstance(ws, str) and ws.strip()):
        failures.append(
            "workspace missing — the savepoint must state which tree to work in (e.g. "
            "{path, why}); a resumer should never have to ask 'framework or mywheel?'"
        )

    # --- first_actions[0] must be DECIDED, not a fork the resumer stops on (warning) ---
    if _is_nonempty_list(fa) and isinstance(fa[0], dict):
        a0 = (fa[0].get("action") or "").lower()
        if any(w in f" {a0} " for w in _DECISION_WORDS):
            warnings.append(
                "first_actions[0] reads like a decision/fork (pick/choose/which/or/?). The "
                "resumer must be able to EXECUTE it with no decision — make the call here, "
                "list the alternative as a fallback, not a question."
            )

    # --- inbox snapshot: so the resumer isn't surprised by inbox-first work (warning) ---
    if "inbox_snapshot" not in sp:
        warnings.append(
            "no inbox_snapshot — record what is in lugs/incoming/ at save time so the resumer's "
            "inbox-first pass surfaces nothing unexpected."
        )

    return {"ok": not failures, "failures": failures, "warnings": warnings}


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    spoke_root = "."
    for a in argv:
        if a.startswith("--spoke-root="):
            spoke_root = a.split("=", 1)[1]
    if "--spoke-root" in argv:
        i = argv.index("--spoke-root")
        if i + 1 < len(argv):
            spoke_root = argv[i + 1]
            args = [a for a in args if a != spoke_root]
    if not args:
        print("usage: validate_savepoint.py <savepoint.json> [--spoke-root DIR]", file=sys.stderr)
        return 2
    sp = json.load(open(args[0]))
    result = validate_resume_contract(sp, spoke_root)
    for w in result.get("warnings", []):
        print(f"  ⚠ {w}")
    if result["ok"]:
        print(f"OK — resume contract satisfied: {args[0]}"
              + (f" ({len(result['warnings'])} warning(s))" if result.get("warnings") else ""))
        return 0
    print(f"FAIL — resume contract NOT satisfied ({len(result['failures'])} issue(s)):")
    for f in result["failures"]:
        print(f"  - {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
