#!/usr/bin/env python3
"""advisor_agent_dispatch.py -- run one AGENT-backed advisor headlessly.

The other half of W10. run_advisor.py could execute any advisor that named a
deterministic tool; every agent-backed advisor named nothing, so the nightly
scheduler declined all of them and two (luci, unknown) sat SILENT for 59 days
with no path back. Measured 2026-08-03: of 34 advisors, ZERO agent-backed ones
carried a dispatch command, so authorising spend alone would have changed
nothing -- there was no thing to spend it on.

OPERATOR RULING (2026-08-03, s140), which this file exists to implement:

    "unattended jobs are allowed to spend tokens on agent-backed advisors
     if Ozi determines they are something to prioritize"

The ruling has two halves and BOTH are gates here. Permission to spend is not
the same as a decision to spend, and collapsing them would turn a considered
"yes, when it matters" into a standing charge against the operator's budget.

  1. FUNDED -- the contract must carry `fund: true`. That flag is Ozi's existing
     determination, already consumed by ozi_autopilot.py and spoke_pulse.py to
     decide what deserves resource. It is not a new mechanism invented to satisfy
     this ruling; it is the one already in use, now honoured on the unattended
     path too. 6 of 34 advisors carry it today.
  2. DUE -- the scheduler only reaches this tool for an advisor its cadence says
     is actually due. A funded advisor that is current costs nothing.

WHAT IT REFUSES, and why each refusal is exit 2 rather than a quiet skip:

  * fund is not true          -> unfunded work must never spend money by accident
  * no context_prompt.md      -> nothing to ask; an advisor with no prompt is
                                 undefined, not idle (luci has no contract at all)
  * `claude` not on PATH      -> a missing binary is UNRUNNABLE. Never record a
                                 run that did not happen; that is the exact
                                 fabricated-evidence failure the tenet removes.

MODEL. Defaults to haiku: these prompts ask for a ~300-word advisory brief, and
the cheapest model that can do the job is the correct one for an unattended job
billed to someone who is asleep. A contract may raise it with `agent_model`,
which is a deliberate per-advisor decision rather than a global default nobody
revisits.

OUTPUT. The brief is written to <advisor>/last-brief.md and the run is recorded
by run_advisor.record_run through the normal path, so an agent advisor becomes
LIVE by the same evidence rule as a tool-backed one: it produced output.

CLI:
    advisor_agent_dispatch.py --advisor ID [--root DIR] [--model M] [--dry-run]

Exit codes: 0 ran and produced a brief, 1 ran and the model returned nothing
usable, 2 refused to run (unfunded, undefined, or no binary).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import oracle_liveness as ol

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_TIMEOUT = 600
REFUSED = 2


def advisor_dir(root, advisor_id):
    return os.path.join(ol.advisors_dir(root), advisor_id)


def _input_fingerprint(root, advisor_id):
    """A cheap deterministic hash of EVERYTHING the dispatched run reads: the
    prompt, the contract, and the context snapshots. Content-based, so an
    untouched tree fingerprints identically every time. This is the skip
    precondition: re-asking the same question of the same inputs is a pure
    cost — measured 2026-08-17, eligibility() checked config and never data,
    so a funded advisor re-ran on unchanged inputs forever."""
    import hashlib
    h = hashlib.sha1()
    adir = advisor_dir(root, advisor_id)
    for rel in ("context_prompt.md", "contract.json"):
        path = os.path.join(adir, rel)
        try:
            with open(path, "rb") as handle:
                h.update(handle.read())
        except OSError:
            h.update(b"<absent:" + rel.encode() + b">")
    context_dir = os.path.join(adir, "context")
    if os.path.isdir(context_dir):
        for name in sorted(os.listdir(context_dir)):
            if not (name.startswith("snapshot-") and name.endswith(".md")):
                continue
            try:
                with open(os.path.join(context_dir, name), "rb") as handle:
                    h.update(name.encode())
                    h.update(handle.read())
            except OSError:
                continue
    return h.hexdigest()


def _dispatch_state_path(root, advisor_id):
    return os.path.join(root, "WAI-Harness", "spoke", "local", "runtime",
                        "advisor-dispatch", advisor_id + ".json")


def _last_dispatch(root, advisor_id):
    try:
        with open(_dispatch_state_path(root, advisor_id)) as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _save_dispatch(root, advisor_id, fingerprint, state):
    path = _dispatch_state_path(root, advisor_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            json.dump({"fingerprint": fingerprint, "state": state,
                       "at": datetime.now(timezone.utc).isoformat()}, handle, indent=2)
            handle.write("\n")
    except OSError:
        pass  # a state-write failure must never fake a dispatch failure


def load_contract(root, advisor_id):
    path = os.path.join(advisor_dir(root, advisor_id), "contract.json")
    try:
        with open(path) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def eligibility(root, advisor_id):
    """(ok, reason). The two halves of the operator's ruling, checked here as
    well as in the scheduler -- defence in depth, because this tool can also be
    invoked directly and must not become a way around the funding gate."""
    contract = load_contract(root, advisor_id)
    if not contract:
        return False, ("no contract.json -- this advisor is undefined, not idle; "
                       "define it before funding a run")
    if contract.get("fund") is not True:
        return False, ("not funded (contract.fund is not true) -- Ozi has not "
                       "determined this is worth spending on")
    prompt = os.path.join(advisor_dir(root, advisor_id), "context_prompt.md")
    if not os.path.exists(prompt):
        return False, "no context_prompt.md -- there is nothing to ask"
    return True, "funded and defined"


def build_prompt(root, advisor_id):
    """The advisor's own prompt, with {FEEDS_CONTEXT} filled from what is on disk.

    Left as the literal placeholder when no feed exists, rather than silently
    dropped: a brief written against no context should say so, so the reader can
    discount it. A quiet substitution would make a context-free run look identical
    to a well-fed one."""
    adir = advisor_dir(root, advisor_id)
    path = os.path.join(adir, "context_prompt.md")
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()

    # Feeds are PER-ADVISOR snapshots written by advisor_context_refresh.py into
    # <advisor>/context/snapshot-*.md -- not a global context-feeds directory. The
    # first draft of this function guessed a global path that has never existed, so
    # every dispatch would have run context-free while reporting nothing amiss.
    context_dir = os.path.join(adir, "context")
    chunks = []
    if os.path.isdir(context_dir):
        snaps = sorted(n for n in os.listdir(context_dir)
                       if n.startswith("snapshot-") and n.endswith(".md"))
        for name in snaps[-3:]:                      # newest few only
            try:
                with open(os.path.join(context_dir, name), encoding="utf-8",
                          errors="replace") as handle:
                    chunks.append(f"### {name}\n{handle.read()[:6000]}")
            except OSError:
                continue
    context = "\n\n".join(chunks) if chunks else (
        "(no context snapshots on disk for this advisor -- write the brief from what "
        "you can read in the repository, and SAY in the brief that it was produced "
        "without refreshed feeds so the reader can weigh it accordingly)")
    text = text.replace("{FEEDS_CONTEXT}", context)

    # UNATTENDED-RUN CONTRACT. The advisor prompts are written as briefings for an
    # interactive agent, so dispatched cold the model asks a clarifying question and
    # produces nothing -- observed live on the second dispatch of `unknown`, which
    # came back asking which of three things it should do. Nobody is there to answer.
    # An advisor that returns a question has not run; stating the terms up front is
    # the difference between an oracle and an expensive no-op.
    return text + (
        "\n\n---\n\n"
        "## Execution Terms (unattended run)\n\n"
        "This is an AUTOMATED run. No human is reading this and no one can answer a "
        "question. Do not ask what is wanted, do not offer options, and do not "
        "describe what you would do.\n\n"
        "Produce the advisory brief itself, now, as your entire reply, in the format "
        "the section above specifies. Where evidence is missing, say so inside the "
        "brief and continue -- an honest brief that names its own gaps is the "
        "deliverable; a request for clarification is a failed run."
    )


def dispatch(root, advisor_id, model=None, timeout=DEFAULT_TIMEOUT, dry_run=False,
             force=False):
    ok, reason = eligibility(root, advisor_id)
    if not ok:
        return {"advisor": advisor_id, "state": "REFUSED", "ran": False, "reason": reason}

    # DATA PRECONDITION, not config: skip when nothing the run reads has changed
    # since the last SUCCESSFUL run. eligibility() checks the funding decision;
    # this checks whether there is anything new to say. Only a RAN_OK anchors a
    # skip — a failed or empty run leaves the question genuinely unanswered.
    fingerprint = _input_fingerprint(root, advisor_id)
    if not force:
        last = _last_dispatch(root, advisor_id)
        if last and last.get("fingerprint") == fingerprint \
                and last.get("state") == "RAN_OK":
            return {"advisor": advisor_id, "state": "SKIPPED_UNCHANGED", "ran": False,
                    "reason": ("inputs unchanged since the last successful run at "
                               "{} -- not spending to re-ask the same question "
                               "(pass force to override)").format(last.get("at"))}

    contract = load_contract(root, advisor_id)
    model = model or contract.get("agent_model") or DEFAULT_MODEL

    binary = shutil.which("claude")
    if not binary:
        return {"advisor": advisor_id, "state": "UNRUNNABLE", "ran": False,
                "reason": "`claude` is not on PATH -- nothing ran, nothing recorded"}

    prompt = build_prompt(root, advisor_id)
    abs_root = os.path.abspath(root)

    # RUN FROM OUTSIDE THE PROJECT, then grant it back with --add-dir.
    #
    # The first live dispatch (unknown, 2026-08-03) ran with cwd=root and came back
    # with a WAI WAKEUP BANNER instead of an advisory brief: at cwd=root the project's
    # CLAUDE.md, skills and SessionStart hooks all load, and the wakeup machinery
    # simply outweighed the advisor's own prompt. It cost real tokens to produce an
    # artifact that was not the advisor's work at all -- and, worse, it would have
    # flipped the advisor from SILENT to LIVE on evidence it never produced, which is
    # precisely the manufactured-green this tenet exists to remove.
    #
    # A neutral cwd carries no CLAUDE.md and fires no project hooks; --add-dir hands
    # back read access to the repo the advisor actually needs. Preferred over --bare,
    # which also disables CLAUDE.md discovery but forces auth to ANTHROPIC_API_KEY
    # only -- an unattended job must not break the moment the operator is on OAuth.
    neutral_cwd = os.path.join(abs_root, "WAI-Harness", "spoke", "local", "runtime",
                               "agent-dispatch-cwd")
    try:
        os.makedirs(neutral_cwd, exist_ok=True)
    except OSError:
        neutral_cwd = None

    argv = [binary, "--print", "--model", model,
            "--add-dir", abs_root, "--no-session-persistence", prompt]

    if dry_run:
        return {"advisor": advisor_id, "state": "RESOLVED", "ran": False,
                "model": model, "prompt_chars": len(prompt), "cwd": neutral_cwd,
                "reason": "dry-run -- nothing dispatched and nothing recorded"}

    try:
        proc = subprocess.run(argv, cwd=neutral_cwd or abs_root, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"advisor": advisor_id, "state": "TIMEOUT", "ran": False,
                "reason": f"exceeded {timeout}s -- no verdict reached, nothing recorded"}
    except OSError as exc:
        return {"advisor": advisor_id, "state": "UNRUNNABLE", "ran": False,
                "reason": str(exc)}

    brief = (proc.stdout or "").strip()
    if not brief:
        # It ran and cost money, so it IS a run and is recorded as one -- but the
        # result is empty and must not read as a healthy brief.
        _record(root, advisor_id, argv, proc.returncode or 1, "(empty output)")
        return {"advisor": advisor_id, "state": "RAN_EMPTY", "ran": True, "ok": False,
                "model": model, "reason": "model returned no usable brief"}

    out_path = os.path.join(advisor_dir(root, advisor_id), "last-brief.md")
    stamp = datetime.now(timezone.utc).isoformat()
    try:
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write(f"<!-- {advisor_id} | {model} | {stamp} -->\n\n{brief}\n")
    except OSError:
        pass

    _record(root, advisor_id, argv, proc.returncode, brief.splitlines()[-6:])
    state = "RAN_OK" if proc.returncode == 0 else "RAN_FAILED"
    _save_dispatch(root, advisor_id, fingerprint, state)
    return {"advisor": advisor_id, "state": state,
            "ran": True, "ok": proc.returncode == 0,
            "model": model, "brief_path": out_path, "brief_chars": len(brief)}


def _record(root, advisor_id, argv, returncode, tail):
    """Record through run_advisor so an agent run is evidence by the same rule a
    tool run is -- one recorder, so the two cannot drift apart."""
    import run_advisor as ra
    shown = " ".join(argv[:4]) + " <prompt>"
    if isinstance(tail, list):
        tail = "\n".join(tail)
    try:
        ra.record_run(root, advisor_id, shown, returncode, tail or "")
    except Exception:  # noqa: BLE001 -- a recording failure must not fake a refusal
        pass


def _main(argv=None):
    ap = argparse.ArgumentParser(description="run one agent-backed advisor headlessly")
    ap.add_argument("--root", default=".")
    ap.add_argument("--advisor", required=True)
    ap.add_argument("--model", default=None)
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="dispatch even when inputs are unchanged since the last run")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    result = dispatch(args.root, args.advisor, args.model, args.timeout, args.dry_run,
                      force=args.force)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"[{result['state']}] {result['advisor']}"
              + (f": {result['reason']}" if result.get("reason") else "")
              + (f" -> {result['brief_path']}" if result.get("brief_path") else ""))
    if result["state"] in ("REFUSED", "UNRUNNABLE", "TIMEOUT"):
        return REFUSED
    # A dry-run that resolved cleanly is a SUCCESS, not a failure. Returning 1 here
    # made `--dry-run` indistinguishable from a real run that produced nothing,
    # which is precisely the confusion an unattended caller cannot recover from.
    if result["state"] == "RESOLVED":
        return 0
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(_main())
