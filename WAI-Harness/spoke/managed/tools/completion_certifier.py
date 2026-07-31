#!/usr/bin/env python3
"""completion_certifier.py -- no lug reaches completed/ on the word of the agent that built it.

W2 of epic-close-the-presumption-gap-v1.

THE FAILURE BEING REMOVED. Today a worker finishes, its subprocess exits 0, and
ozi_autopilot stamps `status: completed`. Exit-0 is the whole proof. Measured this
week on this wheel: one autopilot lug completed carrying `file_targets: []` -- its
work turned out to be real, but nothing on disk could have distinguished it from a
fabrication. The wheel's history also holds four lugs a verifier later refuted
while they sat marked complete.

THE RULE. Completion is a TWO-PARTY act:

  * the worker produces a CLAIM,
  * an isolated certifier rules on it against the lug's OWN verify[] and the tree,
  * only `approved` moves the lug to completed/; `halted` reopens it with the reason.

WHAT THE CERTIFIER IS NOT GIVEN. Never the worker's narrative. `build_request()`
strips every self-report field (summary, done_list, notes, implementation_notes,
acceptance_evidence, resolution, work_done, ...) before the request is rendered.
Reading the defendant's own testimony is precisely the failure being removed, and
it is a whitelist -- a new narrative field added to the lug schema later cannot
leak in by default.

TWO CERTIFICATION PATHS, IN THIS ORDER:

  1. MECHANICAL. A verify step that names a command, a path, or a lug id is
     checked deterministically. No model, no cost, no opinion.
  2. AGENT. Prose verify steps that no mechanical rule can decide are handed to
     the read-only `pattern-gate` agent, which has no Write/Edit tools and so
     cannot author the artifact it is judging.

A step that neither path can decide is UNCHECKABLE. UNCHECKABLE is counted
separately and NEVER folded into certified -- a gate that rounds "I could not
tell" up to "pass" is the thing we are replacing.

VERIFY_KINDS: WHICH STEPS ARE THIS GATE'S JOB.

Some verify steps are not addressed to a machine at all -- "the operator agrees
the wording reads well", "confirm on a real phone". A gate that reports those as
UNCHECKABLE is not being careful, it is answering a question nobody asked, and
it escalated the whole lug for it. Measured 2026-07-30: raising the executable
share of the backlog from 19% to 63% landed no work at all, because only 30 open
lugs had EVERY step runnable while 338 were mixed -- one prose note was enough to
sink a lug whose real checks all passed.

A lug may therefore carry `verify_kinds`, a list parallel to `verify` typing each
step "command" (this gate rules on it) or "manual" (a human does). When present:

  * only "command" steps are decided here;
  * "manual" steps are carried to the verdict as manual_steps_skipped and shown
    to the agent as context explicitly labelled as NOT its to judge;
  * all command steps passing with manual steps outstanding is AWAITING_HUMAN --
    a queue for the operator, which is a different statement from "could not
    decide" and must not be confused with a pass.

Three things this does NOT loosen, each pinned by a fixture:
  * a FAILING command step still HALTS;
  * a lug with NO command steps is still ESCALATE (uncheckable), because a gate
    with nothing to rule on has certified nothing;
  * a lug without verify_kinds behaves exactly as it did before.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

# Fields that carry the worker's own account of its work. The certifier must
# never see these. Whitelist-by-exclusion is deliberate: build_request() copies
# only known-safe keys, so a narrative field added to the schema next year is
# excluded by default rather than leaking until someone notices.
NARRATIVE_FIELDS = frozenset({
    "summary", "work_summary", "done_list", "notes", "implementation_notes",
    "acceptance_evidence", "resolution", "resolution_evidence", "work_done",
    "outcome", "completion_narrative", "test_evidence", "honest_flags",
    "certification", "thinking", "insights", "file_targets_note",
})

# The only fields the certifier is given.
REQUEST_FIELDS = ("id", "type", "title", "verify", "acceptance_criteria",
                  "file_targets", "epic", "wave")

APPROVED = "approved"
HALTED = "halted"
ESCALATE = "escalate"
# Every command step held, but the lug still carries steps only a human can close.
# Deliberately NOT escalate: escalate means "nobody could decide this", while this
# means "the machine decided its half and the remainder is yours". Collapsing the
# two is what made a mixed lug indistinguishable from an unverifiable one.
AWAITING_HUMAN = "awaiting_human"

# Values verify_kinds may carry. Anything else is treated as "command", the
# conservative reading: an unrecognised type stays this gate's problem rather
# than being quietly excused as human work nobody will ever check.
_KIND_MANUAL = "manual"
_KIND_COMMAND = "command"


def _run(cmd, cwd=None, timeout=120, shell=False, env=None):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, shell=shell, env=env)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # noqa: BLE001 -- a broken check must not crash a round
        return None, "", str(e)


# ---------------------------------------------------------------- file_targets

def backfill_file_targets(lug, repo, base_ref=None):
    """Empty file_targets defeats say-do: nothing can be re-checked later.

    bug-completed-lug-with-empty-file-targets-defeats-say-do-v1. Rather than
    trusting the worker to have listed what it touched, read it out of git --
    the diff is a record the worker did not write. Returns the list; does not
    mutate the lug.
    """
    existing = lug.get("file_targets") or []
    if existing:
        return list(existing)
    ref = base_ref or lug.get("dispatch_base_sha")
    if ref:
        rc, out, _ = _run(["git", "-C", str(repo), "diff", "--name-only", ref, "HEAD"])
    else:
        # No dispatch anchor recorded -- fall back to the last commit's diff.
        rc, out, _ = _run(["git", "-C", str(repo), "diff", "--name-only", "HEAD~1", "HEAD"])
    if rc != 0 or not out.strip():
        return []
    return [p for p in (line.strip() for line in out.splitlines()) if p]


# ---------------------------------------------------------------- isolation

def build_request(lug, repo, file_targets=None):
    """The certification payload. Carries the lug's OWN criteria and nothing else.

    Whitelist, never blacklist: only REQUEST_FIELDS are copied across."""
    req = {k: lug.get(k) for k in REQUEST_FIELDS if lug.get(k) is not None}
    if file_targets is not None:
        req["file_targets"] = list(file_targets)
    req["repo"] = str(repo)
    req["_isolation"] = ("the worker's own account of this work is deliberately "
                         "withheld; judge only the tree")
    return req


def leaks_narrative(request):
    """True if any narrative field survived into the request. Tests pin this."""
    return sorted(set(request) & NARRATIVE_FIELDS)


# ---------------------------------------------------------------- verify_kinds

def split_steps_by_kind(steps, kinds):
    """Split verify steps into (this gate's steps, the human's steps).

    Returns (command_steps, manual_steps, applied). `applied` is False whenever
    the typing cannot be trusted, and then every step comes back as a command
    step -- today's behaviour, unchanged.

    THE ALIGNMENT CHECK IS THE WHOLE SAFETY ARGUMENT. verify_kinds is positional:
    kinds[i] types steps[i]. If the two lists have drifted out of length -- a lug
    hand-edited to add a verify step without touching its kinds, which is the
    likely failure -- then every index past the edit is mistyped, and a
    mistyped-as-manual step is a real check silently excused from the gate. So a
    length mismatch does not "do its best"; it refuses the typing entirely and
    rules on everything. Wrongly certifying is the expensive error here; wrongly
    escalating merely costs a human a glance.
    """
    if not isinstance(kinds, list) or not kinds:
        return list(steps), [], False
    if len(kinds) != len(steps):
        return list(steps), [], False
    command, manual = [], []
    for step, kind in zip(steps, kinds):
        k = kind.strip().lower() if isinstance(kind, str) else ""
        (manual if k == _KIND_MANUAL else command).append(step)
    return command, manual, True


# ---------------------------------------------------------------- mechanical

# Command heads the mechanical checker is willing to execute. A whitelist, not a
# pattern: a verify step is text authored elsewhere, and running an arbitrary
# backticked string from it would make the certifier a code-execution surface.
# Anything outside this set falls through to UNCHECKABLE, which is honest --
# never to a pass.
_ALLOWED_CMD_HEADS = (
    "python3 ", "python ", "pytest ", "bash ", "sh ", "git ", "./",
    "test ", "[ ", "ls ", "grep ", "md5sum ", "sha1sum ", "diff ", "cmp ",
    "jq ", "node ", "wc ", "find ", "cat ",
)

_CMD_RE = re.compile(r"`([^`]+)`")

# Prose tells, MEASURED against the 382 real bare command-typed steps in this
# backlog on 2026-07-30 -- not invented. Each of these introduces a description
# of what a command should DO after naming it ("... -q -> 0 errors",
# "grep 'x' AGENTS.md returns no results"). Running the whole line then fails on
# the prose and refutes a lug whose work is genuinely done, which is the
# expensive error: a false ESCALATE costs a human a glance, a false HALTED
# reopens finished work and discredits the gate.
_PROSE_TELLS = (
    " returns ", " prints ", " passes", " green", " includes ", " shows ",
    " AND ", " across ", " with a ", " incl. ", " confirms ", "->", "(ran",
    " as expected", " was ", " only lines ", ": ", "=>", " exits ",
)

# Bare words that are legitimately part of a shell line rather than prose: the
# command vocabulary itself. Everything else alphabetic is a description.
_SHELL_WORDS = frozenset({
    "test", "grep", "ls", "cat", "git", "diff", "cmp", "wc", "find", "node",
    "jq", "bash", "sh", "pytest", "python", "python3", "md5sum", "sha1sum",
    "true", "false", "echo", "head", "tail", "sort", "uniq", "xargs", "env",
})

# The tree this wheel migrated away from. A command still reaching into it is
# describing where something USED to live -- the same "relocation is not absence"
# rule _check_path already applies to paths. Running it produces a failure about
# the migration, not about the work.
_RETIRED_TREE = "WAI-Spoke/"
# `git -C <dir>` is a template, not a command. Running it fails and refutes.
_PLACEHOLDER_RE = re.compile(r"<[^>]+>")


def bare_command_candidate(step):
    """A command-TYPED step whose author never wrote the backticks.

    Measured 2026-07-30: 382 of 402 command-typed verify steps in this backlog
    carry a real, runnable, whitelisted-head command written as bare text,
    because no convention ever required the delimiter. The certifier saw none of
    them, so 95% of the steps Tally certified as machine-checkable were invisible
    to the machine -- which is why raising the provable share from 19% to 63%
    landed almost nothing.

    Returns the command string to run, or None to leave the step undecided.

    ONLY REACHED FOR STEPS TYPED "command" BY verify_kinds. The typing is the
    author's own statement that this step is a machine's job, which is better
    evidence of intent than punctuation. Execution is still gated on the
    unchanged _ALLOWED_CMD_HEADS whitelist -- the security boundary is the
    whitelist and always was; backticks were only ever a delimiter.

    Conservative by construction: anything that smells of prose, carries a
    placeholder, or does not parse as a shell line stays undecided.
    """
    if not isinstance(step, str):
        return None
    s = step.strip()
    if not s or not s.startswith(_ALLOWED_CMD_HEADS):
        return None
    if s.endswith("."):          # a sentence, not a command line
        return None
    if _PLACEHOLDER_RE.search(s):  # `git -C <dir>` -- a template
        return None
    if any(tell in s for tell in _PROSE_TELLS):
        return None
    if _RETIRED_TREE in s:
        return None
    try:
        tokens = shlex.split(s)
    except ValueError:           # unbalanced quotes: not a shell line
        return None
    # THE STRUCTURAL GUARD, and the one that actually holds.
    #
    # A word list is only ever as good as the prose already seen. The first
    # measured pass let through "grep for truncation markers in rendered output:
    # ..." and "python3 ... exits 0 with verdict CLEAR on a clean tree ..."; the
    # second still let through "ls .../hooks/ lists POINTER.md only" and
    # "... --verify exits 0". Each would have run, failed on its own English, and
    # REFUTED a lug whose work was genuinely done.
    #
    # What separates a command from prose is shape, not vocabulary: a shell line
    # is heads, flags and paths, and every bare dictionary word in it belongs to
    # the command vocabulary itself. So ANY alphabetic token that is not shell
    # vocabulary is a description, and one is enough to abstain. Paths survive
    # (they carry / . or -), flags survive (they carry -), quoted arguments
    # survive (they carry spaces), and `test -e a && test -e b` survives because
    # "test" is shell vocabulary -- which matters, since chained existence checks
    # are the single largest honest category in this backlog.
    for t in tokens[1:]:
        if t.isalpha() and len(t) > 1 and t.lower() not in _SHELL_WORDS:
            return None
    return s
# `\b` does not match before `/` or `.`, so the first draft of this pattern silently
# chopped the head off every absolute or dot-prefixed path: `/home/mario/x.py` was
# read as `home/mario/x.py` and `.claude/commands/wai.md` as `claude/commands/wai.md`.
# Both then "did not exist", and the first real sweep produced ~10 false REFUTED
# verdicts against genuinely-completed lugs. Caught because --apply is off by default.
_PATH_RE = re.compile(
    r"(?<![\w/])((?:/|~/|\./)?[\w.@-]+(?:/[\w.@-]+)+\.(?:py|sh|md|json|jsonl|yaml|yml|txt))")
_LUG_RE = re.compile(r"\b((?:impl|bug|fix|spec|epic|task|change|notation|ask)-[a-z0-9-]+-v\d+)\b")


def _check_command(cmd, repo):
    rc, out, err = _run(cmd, cwd=str(repo), shell=True, timeout=180)
    if rc is None:
        return None, "could not run: %s" % err[:100]
    return rc == 0, "`%s` exited %s" % (cmd[:70], rc)


def _check_path(path, repo, declared_targets=None):
    """Existence of a path named in a verify step.

    DECISIVE ONLY FOR THE LUG'S OWN DECLARED OUTPUTS. A prose verify step may name
    any path in passing -- a tool it calls, a config it reads, a tree that has since
    been migrated away. Ruling a lug REFUTED because some incidentally-mentioned
    path moved is not a measurement, it is noise; the first real sweep produced
    exactly that against lugs whose verify steps referenced the retired WAI-Spoke
    tree. When the path is not one the lug claimed to produce, return undecided and
    let it count as UNCHECKABLE, which is the honest answer.
    """
    p = Path(path) if os.path.isabs(path) else Path(repo) / path
    if p.exists():
        return True, "%s exists" % path
    if declared_targets is not None:
        norm = {str(t).lstrip("./") for t in declared_targets}
        if str(path).lstrip("./") not in norm:
            return None, ("%s does not exist, but it is not one of this lug's "
                          "declared file_targets" % path)
    # RELOCATION IS NOT ABSENCE. This wheel migrated its whole tree from
    # WAI-Spoke/ to WAI-Harness/spoke/, so hundreds of lugs record file_targets
    # at paths that were correct when written. `tools/generate_wakeup_brief.py`
    # is "missing" and also very much present, one directory deeper. Refuting
    # completed work because the repo was later reorganised would be noise
    # wearing the costume of a measurement -- so a basename that still exists
    # somewhere in the tree is undecided, and a human is told where it went.
    name = Path(path).name
    if name:
        rc, out, _ = _run(["git", "-C", str(repo), "ls-files", "*/" + name, name])
        hits = [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []
        if hits:
            return None, ("%s is not at its recorded path, but %s exists at %s -- "
                          "looks like a relocation, not undone work"
                          % (path, name, hits[0]))
    return False, "%s does not exist" % path


def _check_lug(lug_id, repo, base):
    root = Path(base) / "lugs" / "bytype"
    if not root.is_dir():
        return None, "lugs/bytype not found"
    for p in root.rglob(lug_id + ".json"):
        return ("completed" in p.parts), "%s is in %s/" % (lug_id, p.parent.name)
    return False, "no lug file named %s.json" % lug_id


def mechanical_checks(verify_steps, repo, base, declared_targets=None,
                      typed_command=False):
    """Decide every verify step a deterministic rule can decide.

    Returns (results, undecided) where results is a list of
    {step, result: 1|0, observed} and undecided is the prose remainder.

    typed_command: these steps were typed "command" by the lug's own
    verify_kinds. Only then is a BARE (un-backticked) command line considered --
    see bare_command_candidate(). An untyped step is never executed bare,
    regardless of its text.
    """
    results, undecided = [], []
    for step in verify_steps or []:
        if not isinstance(step, str) or not step.strip():
            continue
        decided = None
        m = _CMD_RE.search(step)
        if m and m.group(1).startswith(_ALLOWED_CMD_HEADS):
            decided = _check_command(m.group(1), repo)
        elif typed_command:
            bare = bare_command_candidate(step)
            if bare:
                decided = _check_command(bare, repo)
        if decided is None:
            m = _LUG_RE.search(step)
            if m and ("completed" in step.lower() or "reaches" in step.lower()):
                decided = _check_lug(m.group(1), repo, base)
        if decided is None:
            m = _PATH_RE.search(step)
            if m and ("exist" in step.lower() or "present" in step.lower()
                      or "created" in step.lower()):
                decided = _check_path(m.group(1), repo, declared_targets)
        if decided is None or decided[0] is None:
            undecided.append(step)
            continue
        ok, observed = decided
        results.append({"step": step, "result": 1 if ok else 0, "observed": observed,
                        "basis": "mechanical"})
    return results, undecided


# ---------------------------------------------------------------- agent

def default_agent_runner(request, prose_steps, timeout=600):
    """Hand the undecidable steps to the read-only pattern-gate agent.

    pattern-gate has Read and Bash only -- by construction it cannot write the
    artifact it is certifying. Returns a list of result dicts, or None when no
    agent runtime is reachable (which is UNCHECKABLE, never a pass)."""
    prompt = (
        "Certify a completion claim. You are READ-ONLY and you did NOT do this work.\n"
        "You are deliberately NOT given the worker's account of what it did. Judge only\n"
        "what you can observe in the tree.\n\n"
        "LUG (its own declared criteria):\n"
        + json.dumps(request, indent=2)
        + "\n\nDecide EACH of these verify steps against the tree. THREE outcomes,\n"
          "and the third is not a failure state -- it is the honest answer when the\n"
          "evidence is not reachable from where you sit:\n\n"
          "  result 1     you can OBSERVE it holds\n"
          "  result 0     you can OBSERVE it does NOT hold\n"
          "  result null  you cannot tell -- the path is outside your reach, the\n"
          "               claim is about runtime behaviour you cannot execute, or the\n"
          "               evidence simply is not in this tree\n\n"
          "DO NOT return 0 for something you could not check. A lug marked complete\n"
          "will be REOPENED on a 0, so a 0 you are not sure of destroys real work's\n"
          "record. If your `observed` text would begin with words like 'cannot fully\n"
          "verify', 'cannot tell', 'unverifiable from here' or 'half holds', the\n"
          "correct result is null, not 0. Partial truth is null. Only a clean,\n"
          "observed failure is 0.\n\nSTEPS:\n"
        + "\n".join("- " + s for s in prose_steps)
        + "\n\nReturn ONLY a JSON object: "
          '{\"checks\": [{\"step\": \"...\", \"result\": 1, \"observed\": \"...\"}]}'
    )
    rc, out, err = _run(["claude", "-p", prompt, "--agents", "pattern-gate",
                         "--output-format", "json"], timeout=timeout,
                        # The spawned certifier session must never self-upgrade the
                        # spoke it is certifying: the SessionStart pull-on-spin-up
                        # overwrites WAI-Harness/spoke/managed/** from canon —
                        # a "read-only" certifier that mutates (reverts) the tree it
                        # certifies, then fails the lug for the fix it just deleted
                        # (change-autopilot-headless-dispatch-reverts-managed-edits-
                        # every-lug-v1, isolation proof reproduced 3x on basher).
                        env={**os.environ, "WAI_NO_HARNESS_PULL": "1", "WAI_AP_DISPATCH": "1"})
    if rc is None or rc != 0:
        return None
    try:
        payload = json.loads(out)
        text = payload.get("result", out) if isinstance(payload, dict) else out
        m = re.search(r"\{.*\"checks\".*\}", text, re.S)
        data = json.loads(m.group(0)) if m else json.loads(text)
        checks = data.get("checks") or []
    except Exception:  # noqa: BLE001
        return None
    for c in checks:
        c["basis"] = "agent"
    return checks


# ---------------------------------------------------------------- certify

def certify(lug, repo, base, agent_runner=default_agent_runner, use_agent=True,
            base_ref=None):
    """Rule on a completion claim. Returns a verdict dict.

    disposition:
      approved       -- every decidable verify step holds and none is undecidable
      halted         -- at least one step is observably false
      escalate       -- the lug declares no verify steps at all, declares no
                        step this gate owns, or steps remain UNCHECKABLE. None
                        is a pass: an unverifiable completion claim is exactly
                        the presumption this wave exists to remove.
      awaiting_human -- every command step holds, and the only thing left is
                        work typed as a human's. A queue, not a failure.
    """
    file_targets = backfill_file_targets(lug, repo, base_ref=base_ref)
    backfilled = bool(file_targets) and not (lug.get("file_targets") or [])

    steps = lug.get("verify") or lug.get("acceptance_criteria") or []
    if isinstance(steps, str):
        steps = [steps]

    # verify_kinds types the `verify` list specifically. When `verify` is absent
    # and we fell back to acceptance_criteria, the typing describes a different
    # list and positional alignment is meaningless -- so it does not apply.
    kinds = lug.get("verify_kinds") if lug.get("verify") else None
    steps, manual_steps, kinds_applied = split_steps_by_kind(steps, kinds)

    request = build_request(lug, repo, file_targets=file_targets)
    if manual_steps:
        # Context, never an instruction. The agent is told these exist so it can
        # read the lug coherently, and told in the same breath that ruling on
        # them is not its job -- otherwise it invents a verdict for them.
        request["_manual_steps_not_yours_to_judge"] = list(manual_steps)

    verdict = {
        "lug_id": lug.get("id"),
        "file_targets": file_targets,
        "file_targets_backfilled": backfilled,
        "certified_checks": [],
        "failed_checks": [],
        "uncheckable": [],
        # Always present, [] when nothing was skipped. A lug can never read as
        # certified while quietly carrying human work nobody was told about.
        "manual_steps_skipped": list(manual_steps),
        "verify_kinds_applied": kinds_applied,
        "narrative_withheld": True,
        "leaked_narrative_fields": leaks_narrative(request),
    }

    if not steps and not manual_steps:
        verdict["disposition"] = ESCALATE
        verdict["reason"] = ("the lug declares no verify steps, so no completion claim "
                             "about it can be certified by anyone")
        return verdict

    if not steps:
        # Every step is typed manual. The gate ran and ruled on nothing, which is
        # UNCHECKABLE by its plain meaning -- not AWAITING_HUMAN, because there is
        # no machine-side finding to hand over alongside the human's remainder.
        verdict["disposition"] = ESCALATE
        verdict["reason"] = ("all %d verify step(s) are typed manual, so this gate has "
                             "nothing to rule on -- UNCHECKABLE is not a pass"
                             % len(manual_steps))
        return verdict

    results, prose = mechanical_checks(steps, repo, base,
                                       declared_targets=file_targets,
                                       typed_command=kinds_applied)

    if prose and use_agent:
        agent_results = agent_runner(request, prose) if agent_runner else None
        if agent_results is None:
            verdict["uncheckable"] = list(prose)
        else:
            decided_texts = set()
            for c in agent_results:
                if not isinstance(c, dict):
                    continue
                r = c.get("result")
                if r not in (0, 1):
                    continue
                results.append({"step": c.get("step", ""), "result": r,
                                "observed": c.get("observed", ""), "basis": "agent"})
                decided_texts.add(c.get("step", ""))
            verdict["uncheckable"] = [s for s in prose if s not in decided_texts]
    elif prose:
        verdict["uncheckable"] = list(prose)

    verdict["certified_checks"] = [r for r in results if r["result"] == 1]
    verdict["failed_checks"] = [r for r in results if r["result"] == 0]

    if verdict["failed_checks"]:
        verdict["disposition"] = HALTED
        verdict["reason"] = "%d verify step(s) do not hold: %s" % (
            len(verdict["failed_checks"]),
            "; ".join(c["observed"] for c in verdict["failed_checks"][:3]))
    elif verdict["uncheckable"]:
        verdict["disposition"] = ESCALATE
        verdict["reason"] = ("%d verify step(s) could not be decided by any certifier "
                             "-- UNCHECKABLE is not a pass" % len(verdict["uncheckable"]))
    elif manual_steps:
        verdict["disposition"] = AWAITING_HUMAN
        verdict["reason"] = (
            "all %d command step(s) observed to hold; %d step(s) typed manual remain "
            "for a human" % (len(verdict["certified_checks"]), len(manual_steps)))
    else:
        verdict["disposition"] = APPROVED
        verdict["reason"] = "all %d verify step(s) observed to hold" % len(
            verdict["certified_checks"])
    return verdict


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("lug", help="path to the lug json")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base", default="WAI-Harness/spoke/local")
    ap.add_argument("--base-ref", default=None,
                    help="git ref the dispatch started from, for file_targets backfill")
    ap.add_argument("--no-agent", action="store_true",
                    help="mechanical checks only; prose steps become UNCHECKABLE")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-write", action="store_true",
                    help="compute the verdict without recording it on the lug")
    a = ap.parse_args(argv)

    lug = json.loads(Path(a.lug).read_text())
    v = certify(lug, a.repo, a.base, use_agent=not a.no_agent, base_ref=a.base_ref)

    # PERSIST the verdict onto the lug. This tool used to only PRINT it, while
    # exit_safety_check's uncertified-completions gate reads lug["certification"] --
    # so the command the gate told you to run could never satisfy the gate, and every
    # certified lug still counted as hand-closed. Recording it here closes that loop
    # and makes the certification durable evidence rather than terminal output that
    # dies with the session. --no-write keeps the old print-only behaviour for callers
    # that only want the verdict.
    if not a.no_write:
        try:
            lug["certification"] = v
            Path(a.lug).write_text(json.dumps(lug, indent=2) + "\n")
        except OSError as e:
            print("  (could not record certification on the lug: %s)" % e, file=sys.stderr)

    if a.json:
        print(json.dumps(v, indent=2))
    else:
        print("CERTIFICATION %s: %s" % (v["lug_id"], v["disposition"].upper()))
        print("  %s" % v["reason"])
        for c in v["certified_checks"]:
            print("  [ok]     %s" % c["observed"][:100])
        for c in v["failed_checks"]:
            print("  [FAIL]   %s" % c["observed"][:100])
        for s in v["uncheckable"]:
            print("  [UNCHK]  %s" % s[:100])
        for s in v.get("manual_steps_skipped") or []:
            print("  [HUMAN]  %s" % s[:100])
        if v["file_targets_backfilled"]:
            print("  file_targets backfilled from the diff: %d path(s)"
                  % len(v["file_targets"]))
    return {APPROVED: 0, HALTED: 10, ESCALATE: 20, AWAITING_HUMAN: 30}[v["disposition"]]


if __name__ == "__main__":
    sys.exit(main())
