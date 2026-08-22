#!/usr/bin/env python3
"""verify_triage.py — every open lug ends with exactly one disposition.

WHY
---
Measured 2026-08-17 over WAI-Harness/spoke/local/lugs/bytype/*/open/*.json:
1,256 open lugs; 1,106 (88.1%) have no command-form `verify` step; 483 (38.5%)
have empty or missing file_targets. Ozi cannot mechanically confirm completion on
nine of ten lugs, so they are re-reviewed forever. Operator, 2026-08-17: "when we
have unverifiable lugs, they must be audited and processed. Either we can do
something with them or they need to be retired. But they can't just sit in a
unviable state. Sucking up resources on reviews."

THE CONTRACT — nothing may remain undisposed. Every open lug gets exactly one:

  OK        already has a runnable `cmd:` verify           -> untouched
  REPAIR    a falsifiable verify can be DERIVED            -> _triage.proposed_verify
  RETIRE    evidence it is dead                            -> _triage with reason
  ESCALATE  genuine judgment needed                        -> _triage.question (ONE question)

COST-CLASSED. No model call ever fires from inside this tool; Tier 3 is a human
(or Sawyer stage-1) question, not an LLM spend.

  Tier 1 (free) -> REPAIR. Derive ONLY when something falsifiable exists: a
  backticked or `cmd:`-prefixed command anywhere in acceptance_criteria/verify/
  execute prose, OR a test file that already exists and names one of the
  file_targets. A pure file-existence check (`test -f X`, `[ -f X ]`) is NEVER a
  derivable verify — it passes because a file exists and proves nothing about
  behaviour. That is exactly the Goodhart bait this work exists to remove.

  Tier 2 (free) -> RETIRE. Requires ALL THREE: every file_targets path absent
  from disk (and there is at least one target — zero targets is no evidence of
  anything), AND the lug is older than 90 days, AND it has no history/activity
  entries. AGE ALONE IS NEVER A RETIRE VERDICT — standing operator rule.

  Tier 3 -> ESCALATE. Everything else, including any lug this tool fails to
  classify. A lug this tool cannot classify is an ESCALATE, never a silent skip.

VERBS
-----
  scan [--limit N] [--json] [--root PATH]
      Classify, write `_triage` onto each lug (OK lugs are left untouched),
      print the tier split and counts. --limit is the canary control.
  apply --disposition REPAIR|RETIRE [--dry-run] [--commit] [--root PATH]
      Execute one disposition class. REPAIR installs the proposed verify into
      the lug's verify[] (as a `cmd:` entry) and marks _triage.applied.
      RETIRE moves the lug to bytype/<type>/retired/ with the reason recorded.
      --dry-run is the DEFAULT; mutation requires the explicit --commit flag.
      One disposition per invocation — never retire and repair in the same run.
  gate [--root PATH]
      Exit non-zero if any open lug has neither a runnable `cmd:` verify nor a
      live `_triage` disposition. A `_triage` older than 14 days is EXPIRED —
      it counts as undisposed again. That is the ratchet that stops the debt
      rebuilding: a fresh triage buys 14 days to act on it, then the gate asks
      again. (The grace-period reading is what oracle test 7 pins: no _triage
      at all fails; a fresh _triage passes.)

The verify-command grammar is NOT reimplemented here: `_extract_command` is
imported from wai_assurance (hub/local/scripts), the same source lug_gate and
the Gate-4 verifier use — one grammar, three moments (authoring, triage,
execution).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import os
import re
import shlex
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_WAI_ASSURANCE_PATH = os.path.join(
    _DEFAULT_ROOT, "WAI-Harness", "hub", "local", "scripts", "wai_assurance.py")

# ONE verify grammar, three moments — import, never reimplement.
#
# LOADED BY FILE PATH, not `sys.path.insert` + `import wai_assurance`. This tool's
# own directory (spoke/managed/tools/) ALSO carries a wai_assurance.py -- a real,
# independently-maintained 224-line file, not a duplicate. Under a plain script run
# this tool's dir is added to sys.path FIRST, so name-based import shadowed the
# hub's 468-line file with the wrong-but-same-named local one and worked by luck.
# Under pytest collection the search order differs and the shadow flipped the other
# way, breaking the import outright (ImportError: cannot import name
# '_extract_command'). Loading by explicit path removes the ambiguity in both cases.
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("_wai_assurance_hub", _WAI_ASSURANCE_PATH)
_wai_assurance_hub = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_wai_assurance_hub)
_extract_command = _wai_assurance_hub._extract_command

TOOL_VERSION = "1.1.0"
RETIRE_AGE_DAYS = 90
TRIAGE_GRACE_DAYS = 14

_BACKTICK_RE = re.compile(r"`([^`\n]+)`")

# A backticked span that _extract_command does not recognize is still a
# candidate command when the WHOLE span is command-shaped: its first token is a
# known shell head. This is the surface the Goodhart guard exists for — without
# it, `test -f X` is invisible to the grammar and the guard would guard nothing
# (proven by mutation: removing the guard left oracle 3 green until this
# fallback existed).
_COMMAND_HEADS = ("test", "[", "python3", "python", "pytest", "bash", "sh",
                  "node", "npm", "npx", "git", "diff", "grep", "make",
                  "cargo", "go")

# Directories searched for test files that already name a lug's file_targets.
_TEST_DIR_RELS = (
    os.path.join("WAI-Harness", "spoke", "managed", "tests"),
    os.path.join("WAI-Harness", "hub", "managed", "tests"),
)


# ---------------------------------------------------------------------------
# lug IO
# ---------------------------------------------------------------------------

def _open_lug_paths(root):
    pat = os.path.join(root, "WAI-Harness", "spoke", "local", "lugs",
                       "bytype", "*", "open", "*.json")
    return sorted(glob.glob(pat))


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path, lug):
    """2-space indent, insertion order, trailing newline — matches the existing
    tree's formatting so a _triage write is a minimal diff, not a reformat."""
    tmp = path + ".tmp-verify-triage"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lug, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def _as_str_list(v):
    """Legacy lugs carry prose fields as bare strings (lug_gate's
    field-shape-string-not-list error class — the content is real, the
    container is wrong). Treat a substantive string as one item; anything else
    as empty. Never raise on shape."""
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str)]
    if isinstance(v, str) and v.strip():
        return [v]
    return []


# Shell builtins that legitimately head a verify command. `!` heads a negation
# pipeline, `test`/`[` probe state, `cd` is handled by the skip logic below.
_SHELL_BUILTIN_HEADS = frozenset({
    "cd", "pushd", "test", "[", "!", "echo", "true", "false", "set",
    "command", "exec", "eval",
})

_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _command_head(toks):
    """The token that actually executes. Skips leading VAR=value assignments and
    `cd <path> &&` / `cd <path>;` prefixes — a legitimate verify may begin with
    `cd <path> && ...` (operator note, 2026-08-17), so the head is what follows
    the last such prefix, not necessarily token zero."""
    i = 0
    while i < len(toks):
        t = toks[i]
        if _ENV_ASSIGN_RE.match(t):
            i += 1
            continue
        if t in ("cd", "pushd") and i + 2 < len(toks) and toks[i + 2] in ("&&", ";"):
            i += 3
            continue
        return t
    return None


def is_plausibly_runnable(cmd_tokens):
    """PROSE GUARD. True only when the extracted command's head token is
    something a shell could actually execute: a known command head, a shell
    builtin, a path-shaped token (./tool, /abs/x, tools/x.sh), or a binary
    resolvable on PATH. The shared grammar accepts everything after `cmd:`
    verbatim — which is what let prose like `cmd: with a fake lower VERSION,
    manifest_build exits nonzero...` classify OK. Measured 2026-08-17: 4 of the
    192 untouched OK lugs carried prose verifies through exactly that hole;
    prose is the unverifiable case this wave exists to remove, so it cannot be
    allowed to pass as runnable. A head nothing resolves is not a verify this
    spoke can run — ESCALATE is the honest verdict for it."""
    head = _command_head(cmd_tokens or [])
    if head is None:
        return False
    if head in _COMMAND_HEADS or head in _SHELL_BUILTIN_HEADS:
        return True
    if "/" in head:  # path-shaped: ./x, /abs/x, tools/x.sh
        return True
    return shutil.which(head) is not None


# Command heads that change state or report without judging. None of them can
# serve as a verify: a mutating command is not a check, and a reporting command
# exits 0 whether or not the behaviour it prints is correct.
_NON_ASSERTING_HEADS = frozenset({"git", "echo", "printf", "cat", "ls", "head",
                                  "tail", "cp", "mv", "rm", "mkdir", "touch",
                                  "chmod", "sed", "tee"})


def asserts_something(cmd_tokens):
    """ASSERTION GUARD. False when the command cannot FAIL on a wrong answer.

    Added 2026-08-18 after an adversarial review refuted 25 of 25 sampled
    REPAIR proposals. Five died precisely here: the proposal printed a value
    and exited 0 regardless, two MUTATED the tree, and one executed the very
    bug its lug reported. A command that always exits 0 is not a verify; it is
    a green light wired to nothing.

    A `python3 -c` one-liner counts only if it actually asserts -- printing a
    list proves the list can be printed, not that it contains the right thing.
    """
    if not cmd_tokens:
        return False
    head = _command_head(cmd_tokens) or ""
    if head in _NON_ASSERTING_HEADS:
        return False
    blob = " ".join(cmd_tokens)
    # A <placeholder> is a template, not a command. It cannot run unattended,
    # so it cannot be a verify -- `--spoke-path <spoke>` reached the proposal
    # set on 2026-08-18 and would have failed on every unattended run.
    if re.search(r"<[a-zA-Z][\w -]*>", blob):
        return False
    # `... | wc -l` and friends report a count and exit 0 whatever it is.
    if re.search(r"\|\s*(wc|head|tail|cat)\b", blob):
        return False
    if head in ("python3", "python") and " -c" in " " + blob:
        return "assert" in blob            # print-only one-liners do not count
    return True


def _is_decision_record(lug):
    """True for lug kinds whose content is a HUMAN DECISION, not code behaviour.

    No test can prove a ruling was made or a spec was agreed, so these are
    ESCALATE by construction rather than candidates for a derived verify.
    Four of the 25 refuted proposals were exactly this: a test pinned adjacent
    mechanics and could not speak to the decision the lug recorded.
    """
    t = str(lug.get("type") or "").strip().lower()
    if t in ("ack", "spec", "decision", "notice", "report", "signal"):
        return True
    title = str(lug.get("title") or "").lower()
    return "operator ruling" in title or t == "task" and "ruling" in title


def has_runnable_verify(lug):
    """True when any verify[] entry carries a mechanically-runnable command,
    per the canonical grammar AND the prose guard — a command the grammar
    extracts but no shell could execute does not count."""
    for v in _as_str_list(lug.get("verify")):
        toks = _extract_command(v)
        if toks is not None and is_plausibly_runnable(toks):
            return True
    return False


def is_existence_check(cmd_tokens):
    """GOODHART GUARD. True only for a command that is ENTIRELY a file/dir
    existence probe: `test -f X`, `test -e X`, `test -d X`, `[ -f X ]`, etc.
    A compound command that merely STARTS with one is not flagged here — and a
    pure existence probe is never a verify, because it passes when the file
    exists and proves nothing about behaviour."""
    if not cmd_tokens:
        return False
    t = cmd_tokens
    if t[0] == "test" and len(t) == 3 and t[1] in ("-f", "-e", "-d"):
        return True
    if t[0] == "[" and len(t) == 4 and t[1] in ("-f", "-e", "-d") and t[3] == "]":
        return True
    return False


def _commands_in_prose(lug):
    """Candidate commands from backticked spans and cmd:-prefixed text anywhere
    in acceptance_criteria / verify / execute. Returns shell strings in order
    found, existence checks excluded."""
    out = []
    fields = _as_str_list(lug.get("acceptance_criteria")) + \
             _as_str_list(lug.get("verify")) + \
             _as_str_list(lug.get("execute"))
    for item in fields:
        if not isinstance(item, str):
            continue
        spans = _BACKTICK_RE.findall(item)
        # A cmd:-prefixed entry is explicit even without backticks.
        if "cmd:" in item and item not in spans:
            spans.append(item)
        for span in spans:
            toks = _extract_command(span)
            if toks is None:
                try:
                    whole = shlex.split(span)
                except ValueError:
                    whole = []
                if whole and (whole[0] in _COMMAND_HEADS or
                              whole[0].startswith(("./", "/"))):
                    toks = whole
            if toks and not is_existence_check(toks) and is_plausibly_runnable(toks):
                out.append(" ".join(toks))
    return out


class _TestCorpus:
    """Lazily-loaded test-file corpus for the test-names-target derivation.
    Loaded once per scan; substring-checked per candidate lug."""

    def __init__(self, root):
        self.root = root
        self._files = None

    def _load(self):
        self._files = []
        for rel in _TEST_DIR_RELS:
            d = os.path.join(self.root, rel)
            if not os.path.isdir(d):
                continue
            for path in sorted(glob.glob(os.path.join(d, "**", "*.py"), recursive=True)):
                try:
                    with open(path, encoding="utf-8") as f:
                        text = f.read()
                except (OSError, UnicodeDecodeError):
                    continue
                self._files.append((os.path.relpath(path, self.root), text))

    def find_test_naming(self, target):
        """The test that CONVENTIONALLY covers `target`, or None.

        NAME PAIRING ONLY: tools/foo.py -> tests/test_foo.py. A test whose
        FILENAME derives from the target's module name is a real, checkable
        association. Anything looser is not evidence.

        THIS USED TO SUBSTRING-MATCH THE TEST BODY -- `if target in text` --
        returning the first test file that merely MENTIONED the path anywhere,
        in sorted order. Measured 2026-08-18 across the full tree: 264 REPAIR
        lugs collapsed onto just 63 distinct commands, and ONE file,
        test_archeologist.py, became the proposed proof-of-done for 59
        completely unrelated lugs (22% of all REPAIRs). Those tests pass, so
        applying that would have marked 264 lugs mechanically verified while
        proving nothing about any of them.

        That is precisely the Goodhart failure this whole tool exists to
        remove, arriving through the tool itself. A lug with no conventional
        test is an ESCALATE -- an honest "someone must judge this" -- not a
        cheap green tick.
        """
        if self._files is None:
            self._load()
        stem = os.path.splitext(os.path.basename(target.strip()))[0]
        if not stem or len(stem) < 4:
            return None          # too short to pair on without collisions
        wanted = "test_{}.py".format(stem)
        for rel, _text in self._files:
            if os.path.basename(rel) == wanted:
                return rel
        return None


def derive_verify(lug, corpus):
    """Tier 1. Return a proposed verify shell string, or None when nothing
    falsifiable exists. Never returns an existence check.

    ONLY a command the lug ITSELF states is accepted. Nothing is inferred from
    the shape of the tree.

    TEST NAME-PAIRING WAS REMOVED 2026-08-18, after an adversarial review
    refuted 25 of 25 sampled proposals -- ZERO confirmed. Pairing `tools/foo.py`
    with `tests/test_foo.py` proves the test imports the target and nothing
    more: in 13 of 25 the test exercised a different concern than the lug
    claimed, in 4 the lug was a decision record no test can speak to, and
    several tests skip their whole module when the target file is absent, so
    REVERTING the lug's work still produced a green.

    It also did active harm: 17 of 107 REPAIR lugs already carried a correct,
    stronger verify of their own, and the derivation OVERWROTE it with a weaker
    name-paired pytest run.

    A derivation with a zero percent confirm rate is not a derivation. A lug
    with no stated command is an honest ESCALATE -- someone must judge it --
    which is a true answer rather than a cheap green tick.

    `corpus` is retained in the signature for callers and tests; it is no longer
    consulted here.
    """
    if _is_decision_record(lug):
        return None                       # a ruling is not testable
    for cmd in _commands_in_prose(lug):
        if asserts_something(cmd.split()):
            return cmd                    # first command that can actually FAIL
    return None


def _parse_created(lug):
    raw = lug.get("created_at")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_dt.timezone.utc)
    return dt


def retire_evidence(lug, root, now):
    """Tier 2. Return a reason string when ALL THREE conditions hold, else None.
    Age alone is never a verdict — the missing targets and dead history are
    what carry it."""
    targets = [t.strip() for t in _as_str_list(lug.get("file_targets")) if t.strip()]
    if not targets:
        return None  # zero targets is no evidence of anything
    if any(os.path.exists(os.path.join(root, t)) for t in targets):
        return None
    created = _parse_created(lug)
    if created is None:
        return None
    age_days = (now - created).days
    if age_days <= RETIRE_AGE_DAYS:
        return None
    if lug.get("history") or lug.get("activity"):
        return None
    return ("all {} file_targets absent from disk; created {} days ago; "
            "no history/activity entries".format(len(targets), age_days))


def _escalate_question(lug, root):
    targets = [t.strip() for t in _as_str_list(lug.get("file_targets")) if t.strip()]
    title = lug.get("title") or lug.get("id") or "this lug"
    if not targets:
        return ("Which files does \"{}\" change? Name them in file_targets so a "
                "verify can be derived.".format(title[:80]))
    missing = [t for t in targets if not os.path.exists(os.path.join(root, t))]
    if missing:
        return ("Targets {} are absent but the lug is not old enough to retire "
                "— is the work already done, renamed, or abandoned?".format(
                    ", ".join(missing[:3])))
    return ("What single shell command would prove \"{}\" is done?".format(title[:80]))


def classify_lug(lug, root, corpus, now):
    """Return (disposition, record-fields dict). Never raises on shape — a lug
    this tool cannot classify is an ESCALATE, never a silent skip."""
    try:
        if has_runnable_verify(lug):
            return "OK", {"reason": "already has a runnable cmd: verify"}
        proposed = derive_verify(lug, corpus)
        if proposed:
            return "REPAIR", {"proposed_verify": proposed,
                              "reason": "falsifiable verify derived deterministically"}
        reason = retire_evidence(lug, root, now)
        if reason:
            return "RETIRE", {"reason": reason}
        return "ESCALATE", {"question": _escalate_question(lug, root),
                            "reason": "no falsifiable verify derivable; not provably dead"}
    except Exception as e:  # a lug we cannot classify is an ESCALATE
        return "ESCALATE", {"question": "verify_triage failed to classify this lug: {}".format(e),
                            "reason": "classifier error: {}".format(e)}


def _triage_record(lug, root, corpus, now):
    disp, fields = classify_lug(lug, root, corpus, now)
    rec = {"tool": "verify_triage", "tool_version": TOOL_VERSION,
           "triaged_at": now.isoformat(), "disposition": disp}
    rec.update(fields)
    return rec


# ---------------------------------------------------------------------------
# verbs
# ---------------------------------------------------------------------------

def cmd_scan(root, limit, as_json):
    paths = _open_lug_paths(root)
    if limit is not None:
        paths = paths[:limit]
    now = _dt.datetime.now(_dt.timezone.utc)
    corpus = _TestCorpus(root)
    counts = {"OK": 0, "REPAIR": 0, "RETIRE": 0, "ESCALATE": 0}
    rows = []
    for path in paths:
        try:
            lug = _load(path)
        except Exception as e:
            counts["ESCALATE"] += 1
            rows.append({"path": os.path.relpath(path, root), "disposition": "ESCALATE",
                         "reason": "unparseable lug: {}".format(e)})
            continue
        rec = _triage_record(lug, root, corpus, now)
        disp = rec["disposition"]
        counts[disp] += 1
        if disp != "OK":  # OK lugs are untouched
            lug["_triage"] = rec
            _write(path, lug)
        row = {"path": os.path.relpath(path, root), "disposition": disp}
        for k in ("proposed_verify", "question", "reason"):
            if k in rec:
                row[k] = rec[k]
        rows.append(row)
    total = len(paths)
    split = {k: {"n": n, "pct": round(100.0 * n / total, 1) if total else 0.0}
             for k, n in counts.items()}
    if as_json:
        print(json.dumps({"root": root, "scanned": total, "split": split,
                          "lugs": rows}, indent=2))
    else:
        print("verify_triage scan — {} lug(s)".format(total))
        for k in ("OK", "REPAIR", "RETIRE", "ESCALATE"):
            print("  {:9s} {:4d}  ({}%)".format(k, counts[k], split[k]["pct"]))
    return 0


def cmd_apply(root, disposition, commit):
    paths = _open_lug_paths(root)
    acted, skipped = [], []
    for path in paths:
        try:
            lug = _load(path)
        except Exception:
            continue
        triage = lug.get("_triage")
        if not isinstance(triage, dict) or triage.get("disposition") != disposition:
            continue
        rel = os.path.relpath(path, root)
        if disposition == "REPAIR":
            proposed = triage.get("proposed_verify")
            if not proposed:
                skipped.append((rel, "REPAIR without proposed_verify"))
                continue
            if commit:
                entry = "cmd: {}  (derived by verify_triage)".format(proposed)
                verify = lug.setdefault("verify", [])
                if entry not in verify:
                    verify.append(entry)
                kinds = lug.setdefault("verify_kinds", [])
                if "command" not in kinds:
                    kinds.append("command")
                if not lug.get("verify_mode"):
                    lug["verify_mode"] = "executable"
                triage["applied"] = True
                triage["applied_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
                _write(path, lug)
            acted.append((rel, "install verify: {}".format(proposed)))
        elif disposition == "RETIRE":
            reason = triage.get("reason", "no reason recorded")
            if commit:
                lug["retired"] = {"reason": reason, "by": "verify_triage apply",
                                  "at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
                lug["status"] = "retired"
                dest_dir = os.path.join(os.path.dirname(os.path.dirname(path)), "retired")
                os.makedirs(dest_dir, exist_ok=True)
                dest = os.path.join(dest_dir, os.path.basename(path))
                _write(path, lug)
                os.replace(path, dest)
            acted.append((rel, "retire: {}".format(reason)))
    mode = "COMMIT" if commit else "DRY-RUN (pass --commit to mutate)"
    print("verify_triage apply --disposition {} — {}".format(disposition, mode))
    for rel, what in acted:
        print("  {}".format(rel))
        print("    {}".format(what))
    for rel, why in skipped:
        print("  SKIPPED {} ({})".format(rel, why))
    print("  {} lug(s) {}, {} skipped".format(
        len(acted), "mutated" if commit else "would be mutated", len(skipped)))
    return 0


def cmd_gate(root):
    """Exit 1 when any open lug is undisposed: no runnable cmd: verify AND
    (no _triage OR _triage older than TRIAGE_GRACE_DAYS)."""
    now = _dt.datetime.now(_dt.timezone.utc)
    undisposed = []
    for path in _open_lug_paths(root):
        try:
            lug = _load(path)
        except Exception:
            undisposed.append((os.path.relpath(path, root), "unparseable"))
            continue
        if has_runnable_verify(lug):
            continue
        triage = lug.get("_triage")
        live = False
        if isinstance(triage, dict):
            try:
                age = now - _dt.datetime.fromisoformat(
                    str(triage.get("triaged_at", "")).replace("Z", "+00:00"))
                live = age.days <= TRIAGE_GRACE_DAYS
            except ValueError:
                live = False
        if not live:
            why = "no _triage" if not isinstance(triage, dict) else "_triage expired (>{}d)".format(TRIAGE_GRACE_DAYS)
            undisposed.append((os.path.relpath(path, root), why))
    if undisposed:
        print("verify_triage gate: FAIL — {} open lug(s) undisposed:".format(len(undisposed)))
        for rel, why in undisposed[:20]:
            print("  {} ({})".format(rel, why))
        if len(undisposed) > 20:
            print("  ... and {} more".format(len(undisposed) - 20))
        return 1
    print("verify_triage gate: PASS — every open lug has a runnable verify or a live _triage")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="verify_triage — no open lug remains undisposed")
    sub = ap.add_subparsers(dest="verb", required=True)
    for name in ("scan", "gate"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=_DEFAULT_ROOT)
        if name == "scan":
            p.add_argument("--limit", type=int, default=None)
            p.add_argument("--json", action="store_true")
    p = sub.add_parser("apply")
    p.add_argument("--root", default=_DEFAULT_ROOT)
    p.add_argument("--disposition", choices=["REPAIR", "RETIRE"], required=True)
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="default; mutation requires --commit")
    p.add_argument("--commit", action="store_true",
                   help="actually mutate (default is dry-run)")
    args = ap.parse_args(argv)
    if args.verb == "scan":
        return cmd_scan(args.root, args.limit, args.json)
    if args.verb == "gate":
        return cmd_gate(args.root)
    return cmd_apply(args.root, args.disposition, args.commit)


if __name__ == "__main__":
    sys.exit(main())
