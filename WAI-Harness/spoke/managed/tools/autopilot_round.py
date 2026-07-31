#!/usr/bin/env python3
"""Rounds — the unit of autonomous work you can review, trust, and undo.

A bare autopilot run is an open-ended thing that dispatches until its budget runs
out and tells you it completed N lugs. Nobody checks whether the work is right,
the blast radius is whatever it happened to touch, and a bad pass is discovered
afterwards by reading commits.

A ROUND fixes all three by being recorded as a unit:

    BASELINE   the sha before anything ran — the round's undo point
    MANIFEST   which lugs were in scope, decided and written down BEFORE dispatch
    CLAIMS     what the runner says it completed
    VERDICTS   what an INDEPENDENT verifier says about each claim
    IMPACT     exactly the commits and files this round produced
    VERDICT    CLEAN / GAPS / REFUTED, and whether it stopped early

WHY A SECOND AGENT. The say-do gate (autopilot_verify) proves work was RECORDED —
tracked, committed, referenced. It cannot tell you the work is CORRECT, because
the only evidence it has is the claim itself. So each completed lug is handed to a
fresh agent with the lug's own acceptance criteria and the actual diff, and asked
to REFUTE it. Defaulting to refuted-if-uncertain is deliberate: a verifier that
rubber-stamps is worse than none, because it converts an unchecked claim into a
checked-looking one.

The verifier never sees the executing agent's reasoning — only the criteria and
the diff. Self-assessment is exactly what is being replaced.

RUNAWAY CONTROL. Rounds are small and sequential by design. If a round comes back
REFUTED, the next one does not start; the impact group is bounded to one round's
worth of work, and `--undo` reverts precisely that.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import autopilot_verify
except Exception:  # pragma: no cover
    autopilot_verify = None

try:
    import token_attribution
except Exception:  # pragma: no cover
    token_attribution = None

# TIERS. The verifier must sit ABOVE the tier that produced the work it judges.
#
# A verifier on the implementer's own tier is not independent in the way that
# matters: it can reproduce the implementer's reasoning, so it is most likely to
# agree exactly where the implementer was most confidently wrong. The round
# already buys independence of CONTEXT (fresh agent, criteria and diff only, no
# access to the executing agent's reasoning); this buys independence of CAPACITY.
#
# Measured locally before this change: 6 of 7 chain claims survived refutation
# (86%) against 1 of 5 for unverified batch work (20%) — review compute is the
# only spend in this wheel with a measured return, and it was being bought at the
# cheapest tier available.
#
# The ordering is the invariant, not the specific names. TIER_ORDER is what the
# regression test checks; overriding either model by env is allowed, inverting
# the order is not.
TIER_ORDER = ["haiku", "sonnet", "opus"]

IMPLEMENTER_MODEL = os.environ.get("WAI_AP_IMPLEMENTER_MODEL", "sonnet")
VERIFIER_MODEL = os.environ.get("WAI_AP_VERIFIER_MODEL", "opus")
VERIFIER_TIMEOUT = 300


def tier_rank(model: str) -> int:
    """Position of a model in TIER_ORDER; -1 when unknown (custom/aliased ids)."""
    for i, name in enumerate(TIER_ORDER):
        if name in (model or "").lower():
            return i
    return -1


def _dispatch(model, prompt, pass_name, actor, timeout, root=".", lug_id=None,
              run_id=None, cwd=None):
    """One agent call, with its cost attributed to the pass that made it.

    Every model call a round makes goes through here, so the round cannot spend
    money it does not account for. The verifier tier lift is exactly the kind of
    decision this pays for: it deliberately buys a more expensive opinion, and
    the per-pass ledger is how the wheel finds out later whether that was right.

    Returns (returncode, text). Attribution failure never fails the call — a
    missing ledger line is a gap in measurement, not a reason to lose the work.
    """
    proc = subprocess.run(
        ["claude", "--print", "--output-format", "json", "--model", model,
         "--permission-mode", "bypassPermissions", "--no-session-persistence"],
        input=prompt, capture_output=True, text=True, timeout=timeout, cwd=cwd,
        # Headless child sessions must not self-upgrade the spoke mid-run: the
        # SessionStart pull-on-spin-up would overwrite spoke-local managed/ edits
        # (change-autopilot-headless-dispatch-reverts-managed-edits-every-lug-v1).
        env={**os.environ, "WAI_NO_HARNESS_PULL": "1"})
    raw = proc.stdout or ""
    text = raw
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict) and "result" in payload:
            text = payload.get("result") or ""
    except ValueError:
        pass  # older CLI, or plain text — the raw output is the answer
    if token_attribution is not None:
        try:
            token_attribution.attribute_from_proc(
                pass_name, actor, model, raw, lug_id=lug_id, run_id=run_id,
                root=root or cwd or ".")
        except Exception:
            pass
    return proc.returncode, text


def _now():
    return datetime.now(timezone.utc)


def _base(root):
    v4 = os.path.join(root, "WAI-Harness", "spoke", "local")
    return v4 if os.path.isdir(v4) else os.path.join(root, "WAI-Spoke")


def _rounds_dir(root):
    """Round records are EVIDENCE, not runtime churn — so they are tracked.

    They first lived under runtime/, which is gitignored, meaning the audit trail
    of what autonomous work was independently verified would not survive a clone
    or restore. That is the same failure this whole verification layer exists to
    prevent: quality evidence living somewhere temporary. A round record is how a
    future session knows whether the last unattended pass could be trusted.
    """
    return os.path.join(_base(root), "ap-rounds")


def _git(root, *args):
    try:
        return subprocess.run(["git", "-C", root, *args],
                              capture_output=True, text=True, timeout=120).stdout.strip()
    except Exception:
        return ""


def _find_lug(root, lug_id):
    import glob
    hits = glob.glob(os.path.join(_base(root), "lugs", "bytype", "*", "*", lug_id + ".json"))
    if not hits:
        return None
    try:
        with open(hits[0], "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _as_text(value, limit=1800):
    if isinstance(value, list):
        value = "\n".join(str(v) for v in value)
    return str(value or "")[:limit]


def verify_claim(root, lug_id, baseline_sha):
    """Hand one completed lug to a fresh agent and ask it to refute the claim.

    Returns {verdict, reasoning, ...}. UNVERIFIABLE is a real answer and must not
    be silently upgraded to CONFIRMED — a claim nobody could check is not a claim
    anybody should trust.
    """
    lug = _find_lug(root, lug_id)
    if not lug:
        return {"lug_id": lug_id, "verdict": "UNVERIFIABLE",
                "reasoning": "lug not found on disk"}

    diff = _git(root, "log", "-1", "-p", "--grep", lug_id, "--since", baseline_sha or "")
    if not diff:
        # Fall back to any commit naming it, regardless of round window.
        diff = _git(root, "log", "-1", "-p", "--grep", lug_id)
    if not diff:
        return {"lug_id": lug_id, "verdict": "REFUTED",
                "reasoning": "no commit references this lug, so nothing implements the claim"}

    prompt = f"""You are an ADVERSARIAL VERIFIER. Your job is to REFUTE a completion claim, not to confirm it.

An autonomous agent reported that it COMPLETED this lug. You did not see its reasoning
and must not assume competence. Judge ONLY the lug's stated criteria against the actual diff.

LUG: {lug_id}
TITLE: {_as_text(lug.get('title'), 200)}

WHAT IT SAID IT WOULD VERIFY:
{_as_text(lug.get('verify'))}

ACCEPTANCE CRITERIA:
{_as_text(lug.get('acceptance_criteria'))}

DECLARED TARGET FILES:
{_as_text(lug.get('target_files') or lug.get('file_targets'), 600)}

THE ACTUAL COMMIT AND DIFF:
{diff[:12000]}

Answer with a single JSON object and nothing else:
{{"verdict": "CONFIRMED" | "REFUTED" | "UNVERIFIABLE",
  "reasoning": "<two sentences max, concrete, citing the diff>",
  "criteria_met": <true|false>,
  "touched_declared_targets": <true|false>,
  "fault_domain": "implementation" | "criteria" | "process",
  "fix_hint": "<one sentence: the smallest change that would make this pass>"}}

fault_domain tells the remediator WHERE to aim, so pick it carefully:
- "implementation" — the work is wrong, incomplete, or was never done. The lug is
  fine; the agent did not deliver it.
- "criteria"       — the lug's own verify/acceptance are too vague, unmeasurable,
  or contradict its targets. No implementation could satisfy them as written.
- "process"        — the harness or dispatch is at fault: no diff available, work
  landed outside the declared targets because the targets were wrong, tooling
  failed. The agent could not have succeeded.

Rules:
- REFUTED if the diff does not actually satisfy the stated criteria.
- REFUTED if it edited unrelated files instead of the declared targets.
- REFUTED if it only edited docs/comments while the criteria demanded behaviour.
- UNVERIFIABLE if the criteria are too vague to check against a diff.
- DEFAULT TO REFUTED WHEN UNCERTAIN. A rubber stamp is worse than no check."""

    try:
        _rc, out = _dispatch(VERIFIER_MODEL, prompt, "verify", "verifier",
                             VERIFIER_TIMEOUT, root=root, lug_id=lug_id)
        out = (out or "").strip()
        start, end = out.find("{"), out.rfind("}")
        if start >= 0 and end > start:
            parsed = json.loads(out[start:end + 1])
            parsed["lug_id"] = lug_id
            parsed.setdefault("verdict", "UNVERIFIABLE")
            return parsed
        return {"lug_id": lug_id, "verdict": "UNVERIFIABLE",
                "reasoning": "verifier returned no parseable verdict"}
    except subprocess.TimeoutExpired:
        return {"lug_id": lug_id, "verdict": "UNVERIFIABLE",
                "reasoning": f"verifier timed out after {VERIFIER_TIMEOUT}s"}
    except Exception as exc:
        return {"lug_id": lug_id, "verdict": "UNVERIFIABLE",
                "reasoning": f"verifier failed: {exc}"}


def completions_since(root, since_iso):
    path = os.path.join(root, "WAI-Harness", "spoke", "advisors",
                        "autopilot", "activity-log.jsonl")
    if not os.path.isfile(path):
        path = os.path.join(root, "WAI-Spoke", "advisors", "autopilot", "activity-log.jsonl")
    out = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("outcome") == "completed" and rec.get("lug_id") \
                        and str(rec.get("ts", "")) >= since_iso:
                    out.append(rec)
    except OSError:
        pass
    return out


def close_round(root, round_rec, verify=True):
    """Verify every claim, compute the impact group, and write the verdict."""
    started = round_rec["started_at"]
    baseline = round_rec["baseline_sha"]

    claims = completions_since(root, started)
    round_rec["claims"] = [{"lug_id": c["lug_id"], "tokens": c.get("tokens_used")}
                           for c in claims]

    # Impact group: exactly what this round produced, so review and undo are both
    # bounded to it rather than to "whatever the tree looks like now".
    commits = [l for l in _git(root, "log", "--oneline",
                               f"{baseline}..HEAD").splitlines() if l.strip()]
    files = [f for f in _git(root, "diff", "--name-only",
                             f"{baseline}..HEAD").splitlines() if f.strip()]
    round_rec["impact"] = {"commits": commits, "files": files,
                           "commit_count": len(commits), "file_count": len(files)}

    if verify and claims:
        round_rec["verdicts"] = [verify_claim(root, c["lug_id"], baseline) for c in claims]
    else:
        round_rec["verdicts"] = []

    # Recording check runs alongside correctness: a claim can be committed and
    # wrong, or right and uncommitted. Both are failures, of different kinds.
    if autopilot_verify is not None:
        say_do = autopilot_verify.check(root, started)
        round_rec["say_do"] = {"ok": say_do["ok"], "gaps": say_do["gaps"]}
    else:
        round_rec["say_do"] = {"ok": None, "gaps": [], "note": "autopilot_verify unavailable"}

    # A CHAIN records its outcomes in steps[], not verdicts[] — it verifies as it
    # goes rather than in a batch at the end. Reading only verdicts[] made a chain
    # that HALTED on a refutation report CLEAN in its own summary line, directly
    # contradicting the step detail printed above it. A top-line verdict that
    # disagrees with its own evidence is the precise failure this tool exists to
    # catch, so it must not be possible here of all places.
    step_verdicts = [{"lug_id": st.get("lug_id"), "verdict": st.get("verdict"),
                      "reasoning": st.get("reasoning")}
                     for st in round_rec.get("steps", [])
                     if st.get("verdict") not in (None, "NO-WORK")]
    all_verdicts = list(round_rec["verdicts"]) + step_verdicts


    round_rec["verdict"] = decide_round_verdict(round_rec)

    round_rec["refuted_count"] = len(
        [v for v in all_verdicts if v.get("verdict") == "REFUTED"])
    round_rec["ended_at"] = _now().isoformat()

    os.makedirs(_rounds_dir(root), exist_ok=True)
    path = os.path.join(_rounds_dir(root), round_rec["round_id"] + ".json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(round_rec, fh, indent=2)
        fh.write("\n")
    round_rec["_path"] = path
    return round_rec




MAX_SETTLE_ATTEMPTS = 3


def settle_step(root, lug_id, step_baseline, on_refute="remediate",
                max_attempts=MAX_SETTLE_ATTEMPTS, verbose=True):
    """Validate, remediate, re-validate — until it passes or the attempts run out.

    A single verify-then-halt turns every imperfect result into a full stop for the
    operator. Looping instead means the chain only advances on a CONFIRMED verdict,
    and each failure is spent improving something rather than merely reporting it.
    Movement becomes tied to quality: nothing proceeds until it earns the pass.

    Remediation is AIMED by the verifier's fault_domain, because the three failures
    need opposite responses:

      implementation  the agent did not deliver — fix the work, re-verify
      criteria        no implementation could satisfy the lug as written — the lug
                      is the defect, so sharpen it rather than hammer the code
      process         the harness or dispatch made success impossible — the fault
                      is OURS, and hammering the work would never fix it

    PROCESS FAULTS ARE NOT AUTO-PATCHED. Live-editing the harness underneath a
    running pass is how a bad diagnosis becomes a broken runner mid-flight. They
    raise a lug and halt, which is the honest boundary: the wheel improves from the
    signal, deliberately, on the next pass.
    """
    attempts = []
    for attempt in range(1, max_attempts + 1):
        verdict = verify_claim(root, lug_id, step_baseline)
        attempts.append({"attempt": attempt, "verdict": verdict.get("verdict"),
                         "fault_domain": verdict.get("fault_domain"),
                         "reasoning": verdict.get("reasoning"),
                         "fix_hint": verdict.get("fix_hint")})
        if verbose:
            print(f"    attempt {attempt}: {verdict.get('verdict')}"
                  + (f" ({verdict.get('fault_domain')})" if verdict.get("fault_domain") else ""),
                  flush=True)

        if verdict.get("verdict") == "CONFIRMED":
            return {"verdict": "CONFIRMED", "attempts": attempts, "settled_on": attempt}

        if verdict.get("verdict") == "UNVERIFIABLE" or on_refute != "remediate":
            return {"verdict": verdict.get("verdict"), "attempts": attempts,
                    "settled_on": None}

        if attempt == max_attempts:
            break

        domain = (verdict.get("fault_domain") or "implementation").lower()

        if domain == "process":
            lug = _raise_process_lug(root, lug_id, verdict)
            return {"verdict": "PROCESS-FAULT", "attempts": attempts,
                    "process_lug": lug, "settled_on": None}

        if verbose:
            print(f"    remediating ({domain})...", flush=True)
        if domain == "criteria":
            attempts[-1]["remediation"] = _sharpen_criteria(root, lug_id, verdict)
        else:
            attempts[-1]["remediation"] = _remediate(root, lug_id, verdict)

    return {"verdict": "REFUTED", "attempts": attempts, "settled_on": None,
            "exhausted": True}


def _sharpen_criteria(root, lug_id, verdict):
    """The lug is the defect: make its criteria checkable without changing intent.

    Strictly bounded. An agent allowed to rewrite acceptance criteria freely will
    weaken them until the existing work passes, which produces a confirmed verdict
    over unchanged code — worse than the original refusal because it looks settled.
    """
    prompt = f"""A verifier could not check lug {lug_id} because its OWN criteria are the problem.

VERIFIER'S FINDING:
{verdict.get('reasoning', '')}

SUGGESTED FIX:
{verdict.get('fix_hint', '')}

Rewrite ONLY the lug's `verify` and `acceptance_criteria` so they are concrete and
machine-checkable — a command that exits 0, a file that must contain something, a
measurable number.

HARD CONSTRAINT: do not weaken the bar and do not change what the lug is asking
for. If the existing work would still fail the sharpened criteria, that is the
correct outcome — leave it failing. Changing the target so the arrow lands is the
one thing you must not do.

Do not touch the implementation. Work in {root}, commit referencing {lug_id}."""
    try:
        rc, out = _dispatch(IMPLEMENTER_MODEL, prompt, "remediate", "remediate:criteria",
                            900, root=root, lug_id=lug_id, cwd=root)
        return {"kind": "criteria", "rc": rc, "output": (out or "")[-500:]}
    except Exception as exc:
        return {"kind": "criteria", "error": str(exc)}


def _raise_process_lug(root, lug_id, verdict):
    """Record an AP-process defect as work, rather than patching it mid-run.

    This is how the wheel improves from its own failures: a process fault becomes a
    lug with the verifier's evidence attached, reviewable before anything changes.
    """
    slug = f"fix-ap-process-{lug_id[:36]}-v1"
    lug = {
        "id": slug,
        "type": "fix",
        "title": f"AP process fault surfaced while verifying {lug_id}"[:118],
        "status": "open",
        "initiative": "harness-v4-self-certifying",
        "created_at": _now().isoformat(),
        "created_by": "autopilot_round.settle",
        "model_fit": "sonnet",
        "model_fit_reason": "Harness/tooling fix with a concrete verifier finding to work from.",
        "perceive": [
            f"An independent verifier refuted the completion of {lug_id} and attributed "
            f"the fault to the AP PROCESS rather than to the work or the lug — meaning "
            f"the dispatched agent could not have succeeded no matter what it did.\n\n"
            f"VERIFIER FINDING: {verdict.get('reasoning', '')}\n"
            f"SUGGESTED FIX: {verdict.get('fix_hint', '')}\n\n"
            f"Raised rather than auto-patched: live-editing the harness underneath a "
            f"running pass is how a bad diagnosis becomes a broken runner mid-flight."
        ],
        "execute": [
            "1. Reproduce the fault the verifier describes.\n"
            "2. Fix the harness/dispatch path, not the lug that exposed it.\n"
            f"3. Re-run verification for {lug_id} and confirm it can now be judged."
        ],
        "verify": [f"Verifying {lug_id} returns CONFIRMED or a fault_domain other than 'process'."],
        "acceptance_criteria": [
            "The process fault is reproduced before it is fixed",
            f"{lug_id} can be verified without the same process failure",
        ],
        "target_files": ["WAI-Harness/spoke/managed/tools/ozi_autopilot.py",
                         "WAI-Harness/spoke/managed/tools/autopilot_round.py"],
        "file_targets": ["WAI-Harness/spoke/managed/tools/ozi_autopilot.py",
                         "WAI-Harness/spoke/managed/tools/autopilot_round.py"],
        "_improvement_lenses": {
            "skeptic": "Is this really a process fault, or an implementation failure the verifier misattributed? Reproduce before changing the harness.",
            "architect": "A process fault that recurs across lugs is a design gap, not a bug — check whether other refutations share this fault_domain.",
            "naive_reader": "State plainly what the harness did that made success impossible.",
        },
        "tags": ["ap-process", "verifier-surfaced", "self-improvement"],
        "disposition": "needs_you",
        "disposition_reason": "Harness-level change surfaced mid-run; needs review before the runner is altered.",
    }
    try:
        d = os.path.join(_base(root), "lugs", "bytype", "fix", "open")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, slug + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(lug, fh, indent=2)
            fh.write("\n")
        return {"created": True, "lug_id": slug, "path": path}
    except OSError as exc:
        return {"created": False, "error": str(exc)}


def run_chain(root, steps, scope_flag, runner, on_refute="remediate", verbose=True):
    """Execute lugs ONE AT A TIME, verifying each before the next begins.

    The batch alternative — dispatch ten, verify at the end — was measured
    refuting 4 of 5 claims, which means nine further lugs would have run on top
    of a broken first one before anybody knew. Chaining trades throughput for the
    thing actually in short supply right now: confidence that a completion means
    what it says.

    Each step is: execute one lug -> hand it to a FRESH verifier -> only proceed
    on approval. The verifier sees the lug's criteria and the diff, never the
    executing agent's reasoning.

    on_refute:
      stop       halt the chain, leave everything for review (default — the
                 conservative choice while confidence is being established)
      remediate  dispatch a follow-up agent to fix what the verifier refuted,
                 then re-verify once; halt if it still fails
      continue   record and carry on (only sensible once trust is high)
    """
    round_rec = open_round(root, steps, scope_flag)
    round_rec["mode"] = "chain"
    round_rec["on_refute"] = on_refute
    round_rec["steps"] = []

    for index in range(1, steps + 1):
        step_baseline = _git(root, "rev-parse", "HEAD")
        step_started = _now().isoformat()

        if verbose:
            print(f"\n─── step {index}/{steps} ─── dispatching", flush=True)

        cmd = [sys.executable, runner, "--spoke-path", root, "--budget", "1",
               "--trigger-source", "manual"]
        if scope_flag and scope_flag != "all-work":
            cmd.append("--not-blocking-me")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

        claims = completions_since(root, step_started)
        if not claims:
            # DID THE RUNNER FINISH, OR DID IT FALL OVER?
            #
            # "no completions" has two causes that look identical from here and
            # mean opposite things: the backlog is genuinely empty, or a phase
            # threw and nothing was ever dispatched. Reporting both as "queue
            # exhausted" told the operator the work was done while 277
            # dispatchable lugs sat waiting behind an AttributeError in
            # phase_3 (a lug whose execute_when was a string, not an object).
            #
            # The runner reports its own phase errors in its JSON, so ask it
            # rather than inferring from the silence.
            phase_errors = []
            try:
                blob = json.loads((proc.stdout or "").strip()[
                    (proc.stdout or "").find("{"):(proc.stdout or "").rfind("}") + 1])
                phase_errors = blob.get("errors") or []
            except Exception:
                pass

            if phase_errors:
                if verbose:
                    print("    RUNNER FAILED — this is not an empty queue:", flush=True)
                    for err in phase_errors[:5]:
                        print(f"      {err}", flush=True)
                    print("    ending chain; fix the runner before trusting a NO-WORK result.",
                          flush=True)
                round_rec["steps"].append({"step": index, "lug_id": None,
                                           "verdict": "RUNNER-ERROR",
                                           "errors": phase_errors,
                                           "baseline": step_baseline})
                round_rec["stopped_early"] = "runner error: " + "; ".join(phase_errors[:3])
                break

            if verbose:
                print(f"    no lug completed — queue exhausted, ending chain", flush=True)
            round_rec["steps"].append({"step": index, "lug_id": None,
                                       "verdict": "NO-WORK", "baseline": step_baseline})
            break

        lug_id = claims[-1]["lug_id"]
        if verbose:
            print(f"    completed: {lug_id}", flush=True)
            print(f"    verifying (independent agent, asked to refute)...", flush=True)

        # Settle the step: validate, remediate by fault domain, re-validate — the
        # chain advances only on CONFIRMED, so movement is tied to quality rather
        # than to the runner having merely finished.
        settled = settle_step(root, lug_id, step_baseline, on_refute=on_refute,
                              verbose=verbose)
        last = settled["attempts"][-1] if settled["attempts"] else {}
        step = {"step": index, "lug_id": lug_id, "baseline": step_baseline,
                "verdict": settled["verdict"],
                "reasoning": last.get("reasoning"),
                "fault_domain": last.get("fault_domain"),
                "attempts": settled["attempts"],
                "settled_on_attempt": settled.get("settled_on"),
                "process_lug": settled.get("process_lug"),
                "tokens": claims[-1].get("tokens_used"),
                "commits": [c for c in _git(root, "log", "--oneline",
                                            f"{step_baseline}..HEAD").splitlines() if c.strip()]}

        if verbose:
            mark = {"CONFIRMED": "APPROVED", "REFUTED": "REFUTED",
                    "PROCESS-FAULT": "PROCESS FAULT",
                    "UNVERIFIABLE": "UNVERIFIABLE"}.get(step["verdict"], "?")
            print(f"    => {mark}"
                  + (f" (settled on attempt {settled['settled_on']})"
                     if settled.get("settled_on") else ""), flush=True)

        round_rec["steps"].append(step)

        # UNVERIFIABLE BELONGS HERE, and its absence was a silent free pass.
        #
        # This module's own contract (see verify_step's docstring) says UNVERIFIABLE
        # "must not be silently upgraded to CONFIRMED — a claim nobody could check
        # is not a claim anybody should trust", and the comment above this loop says
        # the chain "advances only on CONFIRMED". The tuple said otherwise: it named
        # REFUTED and PROCESS-FAULT, so an UNVERIFIABLE step fell through, the chain
        # advanced, and the lug KEPT the completed stamp its verifier had just
        # declined to confirm.
        #
        # Observed live 2026-07-31, step 1 of an 8-step chain:
        # bug-managed-test-suite-deletes-tracked-lug-index-files-v1 verified
        # REFUTED, remediated, came back UNVERIFIABLE — and landed in completed/
        # with no certification recorded at all. Left running, the chain would have
        # built seven more steps on top of it. This is the measured "1 in 5 true
        # completion rate" made mechanical: not agents doing bad work, one missing
        # tuple member turning "nobody could check this" into "done".
        #
        # A lug whose completion nobody could confirm is demoted to needs_attention
        # rather than left wearing a stamp it did not earn.
        # THE VERDICT MUST REACH THE LUG. It used to live only in the round record
        # and the console, so the backlog — which is what the operator and the next
        # session actually read — carried no trace of whether anything had been
        # verified at all.
        #
        # Observed live 2026-07-31 immediately after the UNVERIFIABLE fix below:
        # impl-exitclarity-6-session-netnet-v1 settled APPROVED on attempt 2, its
        # artifact (write_netnet.py + the closeout wiring) genuinely on disk — and
        # the lug sat in needs_attention with NO reason recorded: no escalation
        # reason, no verdict, no timestamp. Something in the refute-then-remediate
        # path had moved it and the APPROVED settle never moved it back, so real,
        # independently-confirmed work read as unfinished. That is the same
        # verdict/lug-state divergence as the UNVERIFIABLE bug, pointing the other
        # way: a false negative rather than a false pass. Less dangerous, equally
        # corrosive — a backlog that lies in either direction stops being read.
        _record_verdict(root, lug_id, step["verdict"], step.get("reasoning"))
        if step["verdict"] == "UNVERIFIABLE":
            _demote_unverified(root, lug_id, step.get("reasoning"))
        if (step["verdict"] in ("REFUTED", "PROCESS-FAULT", "UNVERIFIABLE")
                and on_refute in ("stop", "remediate")):
            round_rec["stopped_early"] = (
                f"step {index} {step['verdict'].lower()}: "
                f"{str(step.get('reasoning'))[:200]}")
            if verbose:
                print(f"\n    CHAIN HALTED at step {index} — not proceeding on top of "
                      f"unverified work", flush=True)
            break

    return close_round(root, round_rec, verify=False)


def _record_verdict(root, lug_id, verdict, reasoning=None):
    """Write the chain's verdict onto the lug, and let CONFIRMED restore `completed`.

    Two jobs, both about the backlog telling the truth:

    1. RECORD. Without this the verdict exists only in the round record and the
       console, so a lug carries no durable evidence that anyone checked it. The
       next session reads the backlog, not the log.
    2. PROMOTE ON CONFIRMED. The refute-then-remediate path can leave the lug
       parked in needs_attention; an APPROVED settle that does not move it back
       leaves genuinely verified work reading as unfinished. The chain's verdict is
       the authority here, so it is asserted rather than assumed.

    CONFIRMED is the ONLY verdict that promotes. Everything else records and leaves
    placement alone — UNVERIFIABLE is handled by _demote_unverified, and a REFUTED
    lug has no business being moved to completed by a bookkeeping helper.
    """
    from pathlib import Path
    import datetime
    try:
        path = None
        for p in Path(root).joinpath(
                "WAI-Harness/spoke/local/lugs/bytype").rglob(lug_id + ".json"):
            path = p
            break
        if path is None:
            return False
        lug = json.loads(Path(path).read_text())
        lug["chain_verdict"] = {
            "verdict": verdict,
            "reasoning": str(reasoning)[:500] if reasoning else None,
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "by": "autopilot_round chain verifier (independent, asked to refute)",
        }
        dest = path
        if verdict == "CONFIRMED" and "completed" not in Path(path).parts:
            lug["status"] = "completed"
            lug.setdefault("completed_at",
                           datetime.datetime.now(datetime.timezone.utc).isoformat())
            for state in ("needs_attention", "in_progress", "open"):
                if f"/{state}/" in str(path):
                    dest = Path(str(path).replace(f"/{state}/", "/completed/"))
                    break
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(lug, indent=2) + "\n")
        if dest != path:
            path.unlink()
            print(f"    promoted {lug_id}: -> completed (CONFIRMED)", flush=True)
        return True
    except Exception as e:  # noqa: BLE001 -- bookkeeping must never fail a round
        print(f"    WARNING: could not record verdict for {lug_id}: {e}", flush=True)
        return False


def _demote_unverified(root, lug_id, reasoning=None):
    """Strip the completed stamp from a lug nobody could verify.

    Halting the chain is not enough on its own: the lug has ALREADY been moved to
    completed/ by the time the verifier rules, so a chain that merely stopped would
    still leave the unverified claim sitting in the done pile, indistinguishable
    from work that earned it. needs_attention is the same destination the completion
    certifier uses for ESCALATE, and for the same reason — an unverifiable
    completion is a question for a human, not a result.

    Best-effort by design: a failure to demote must not crash the round, but it is
    reported, because silently failing to un-stamp would rebuild the exact hole
    this closes.
    """
    from pathlib import Path  # module-local: this file otherwise works in os.path
    try:
        path = None
        for p in Path(root).joinpath(
                "WAI-Harness/spoke/local/lugs/bytype").rglob(lug_id + ".json"):
            path = p
            break
        if path is None or "completed" not in Path(path).parts:
            return False
        lug = json.loads(Path(path).read_text())
        lug["status"] = "needs_attention"
        lug["escalation_reason"] = (
            "chain verifier returned UNVERIFIABLE — the completion claim could not "
            "be checked by anyone, so it does not keep the completed stamp"
            + (": %s" % str(reasoning)[:200] if reasoning else ""))
        lug["unverified_completion"] = True
        dest = Path(str(path).replace("/completed/", "/needs_attention/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(lug, indent=2) + "\n")
        Path(path).unlink()
        print(f"    demoted {lug_id}: completed -> needs_attention (UNVERIFIABLE)",
              flush=True)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"    WARNING: could not demote unverified {lug_id}: {e}",
              flush=True)
        return False


def _remediate(root, lug_id, verdict):
    """Dispatch a follow-up agent to fix exactly what the verifier refuted.

    Narrow on purpose: it is told the refutation and asked to address THAT, not to
    reinterpret the lug. A remediator free to redefine the work would simply move
    the goalposts until the claim passed.
    """
    prompt = f"""A completion claim for lug {lug_id} was REFUTED by an independent verifier.

THE REFUTATION:
{verdict.get('reasoning', 'no reasoning recorded')}

Fix exactly what the refutation identifies. Do not reinterpret the lug's scope or
weaken its acceptance criteria to make the claim pass — if the criteria genuinely
cannot be met, say so and change nothing.

Work in {root}. Commit your fix referencing {lug_id}."""
    try:
        rc, out = _dispatch(IMPLEMENTER_MODEL, prompt, "remediate", "remediate:implementation",
                            1200, root=root, lug_id=lug_id, cwd=root)
        return {"ran": True, "rc": rc, "output": (out or "")[-600:]}
    except Exception as exc:
        return {"ran": False, "error": str(exc)}


def open_round(root, budget, scope):
    stamp = _now().strftime("%Y%m%dT%H%M%S")
    rec = {
        "round_id": f"round-{stamp}",
        "started_at": _now().isoformat(),
        "budget": budget,
        "scope": scope,
        # The undo point. Captured BEFORE dispatch so the round is revertable even
        # if everything after this goes wrong.
        "baseline_sha": _git(root, "rev-parse", "HEAD"),
        "baseline_branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
    }
    os.makedirs(_rounds_dir(root), exist_ok=True)
    return rec


def render(rec):
    v = rec.get("verdict", "?")
    icon = {"CLEAN": "OK", "GAPS": "!!", "REFUTED": "XX", "UNVERIFIED": "??"}.get(v, "??")
    lines = [
        f"ROUND {rec['round_id']} — {icon} {v}",
        f"  budget {rec.get('budget')} | scope {rec.get('scope')} | baseline {str(rec.get('baseline_sha'))[:8]}",
        f"  claims {len(rec.get('claims', []))} | commits {rec['impact']['commit_count']} | files {rec['impact']['file_count']}",
    ]
    if rec.get("verdicts"):
        lines.append("")
        lines.append("  INDEPENDENT VERIFICATION (adversarial — asked to refute):")
        for verdict in rec["verdicts"]:
            mark = {"CONFIRMED": "+", "REFUTED": "X", "UNVERIFIABLE": "?"}.get(
                verdict.get("verdict"), "?")
            lines.append(f"    {mark} {verdict.get('verdict','?'):12s} {verdict.get('lug_id','?')[:46]}")
            if verdict.get("verdict") != "CONFIRMED":
                lines.append(f"        {str(verdict.get('reasoning',''))[:110]}")
    gaps = rec.get("say_do", {}).get("gaps") or []
    if gaps:
        lines.append("")
        lines.append(f"  SAY-DO GAPS: {len(gaps)} (work claimed but not recorded)")
        for gap in gaps:
            lines.append(f"    [{gap['severity']}] {gap['lug_id'][:52]}")
    if v == "REFUTED":
        lines.append("")
        lines.append("  NEXT ROUND BLOCKED — a claim was refuted. Review, then either fix")
        lines.append(f"  the lug or undo this round: autopilot_round.py --undo {rec['round_id']}")
    return "\n".join(lines)


def decide_round_verdict(rec):
    """The round's top-line verdict. Extracted so the rule is testable at all.

    THE RULE IS "ANYTHING THAT IS NOT A PASS", not a list of known-bad verdicts.
    Enumerating the bad ones is what kept letting this back in: the module comment
    above records the CLEAN-over-a-halt bug being fixed for REFUTED, it recurred
    for UNVERIFIABLE, and it recurred again for PROCESS-FAULT — observed live
    2026-07-31, when round-20260731T084737 HALTED at step 2 ("the commit touches
    none of the five declared target files") and its own header still read CLEAN.
    Written this way, a verdict kind added next year is NOT-CLEAN by default
    rather than silently qualifying as green.

    A top-line verdict that disagrees with the evidence printed beneath it is the
    precise failure this tool exists to catch, so it must not be possible here.
    """
    steps = rec.get("steps", []) or []
    step_verdicts = [{"lug_id": st.get("lug_id"), "verdict": st.get("verdict")}
                     for st in steps if st.get("verdict") not in (None, "NO-WORK")]
    all_verdicts = list(rec.get("verdicts") or []) + step_verdicts

    def _of(kind):
        return [v for v in all_verdicts if v.get("verdict") == kind]

    # A runner that threw produced no claims to judge, so every check below would
    # find nothing wrong and hand back CLEAN — a green verdict on a round that
    # never ran. Measured: round-20260722T025333 reported CLEAN over a phase_3
    # AttributeError with 277 dispatchable lugs untouched.
    if _of("RUNNER-ERROR"):
        return "RUNNER-ERROR"
    if _of("REFUTED"):
        return "REFUTED"
    if not (rec.get("say_do") or {}).get("ok", True):
        return "GAPS"
    if _of("UNVERIFIABLE"):
        return "UNVERIFIED"
    passing = {"CONFIRMED", "NO-WORK", None}
    other = [v for v in all_verdicts if v.get("verdict") not in passing]
    if other:
        # Named by its own verdict rather than flattened, so the header says the
        # same thing as the step detail beneath it.
        return str(other[0].get("verdict") or "NOT-CLEAN")
    return "CLEAN"


def render_chain(rec):
    steps = rec.get("steps", [])
    confirmed = sum(1 for s in steps if s.get("verdict") == "CONFIRMED")
    # EVERY verdict is counted, not just the two that were thought of first.
    # "2 step(s): 1 approved, 0 refuted" was printed for a round HALTED by a
    # PROCESS-FAULT — true on its own terms and false as a summary, because the
    # halting verdict appeared in neither number. A tally that silently omits the
    # outcome that stopped the run is how a reader concludes nothing went wrong.
    other = {}
    for s in steps:
        v = s.get("verdict")
        if v and v != "CONFIRMED":
            other[v] = other.get(v, 0) + 1
    tally = ", ".join([f"{confirmed} approved"]
                      + [f"{n} {v.lower()}" for v, n in sorted(other.items())])
    lines = [
        f"CHAIN {rec['round_id']} — {rec.get('verdict','?')}",
        f"  {len(steps)} step(s): {tally}"
        f"  | on-refute={rec.get('on_refute')}",
        f"  baseline {str(rec.get('baseline_sha'))[:8]} | "
        f"{rec['impact']['commit_count']} commit(s), {rec['impact']['file_count']} file(s)",
        "",
    ]
    for step in steps:
        mark = {"CONFIRMED": "+", "REFUTED": "X", "UNVERIFIABLE": "?",
                "NO-WORK": "-"}.get(step.get("verdict"), "?")
        lines.append(f"  {mark} step {step['step']}: {str(step.get('lug_id'))[:48]}"
                     f"  [{step.get('verdict')}]")
        if step.get("verdict") != "CONFIRMED" and step.get("reasoning"):
            lines.append(f"      {str(step['reasoning'])[:120]}")
        if step.get("remediation"):
            lines.append(f"      remediation ran -> {step.get('verdict_after_remediation')}")
    if rec.get("stopped_early"):
        lines.append("")
        lines.append(f"  HALTED: {rec['stopped_early'][:160]}")
        lines.append("  Nothing ran on top of unverified work. Review, fix the lug, or")
        lines.append(f"  undo: autopilot_round.py --undo {rec['round_id']}")
    return "\n".join(lines)


def undo(root, round_id):
    """Revert exactly this round's commits — the bounded blast radius paying off."""
    path = os.path.join(_rounds_dir(root), round_id + ".json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return {"ok": False, "error": f"no round record {round_id}"}

    baseline = rec.get("baseline_sha")
    if not baseline:
        return {"ok": False, "error": "round has no baseline sha"}

    dirty = _git(root, "status", "--porcelain")
    if dirty:
        return {"ok": False,
                "error": "working tree is dirty — commit or stash first; refusing to "
                         "revert over uncommitted work"}

    # revert --no-commit over the range, so the undo is itself a reviewable commit
    # rather than a history rewrite that would strand anyone who already pulled.
    proc = subprocess.run(
        ["git", "-C", root, "revert", "--no-edit", "--no-commit", f"{baseline}..HEAD"],
        capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        subprocess.run(["git", "-C", root, "revert", "--abort"], capture_output=True)
        return {"ok": False, "error": f"revert failed: {proc.stderr[:300]}"}

    subprocess.run(["git", "-C", root, "commit", "--no-verify", "-m",
                    f"revert({round_id}): undo round — verifier refuted its claims\n\n"
                    f"Reverts {rec['impact']['commit_count']} commit(s) back to "
                    f"{baseline[:8]}. The round record is kept at\n"
                    f"runtime/ap-rounds/{round_id}.json so the refutation and its "
                    f"reasoning survive the undo.\n"],
                   capture_output=True, text=True, timeout=120)
    return {"ok": True, "reverted_to": baseline,
            "commits": rec["impact"]["commit_count"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--open", action="store_true", help="open a round (prints the record)")
    parser.add_argument("--close", metavar="ROUND_JSON", help="close+verify a round from its opened record")
    parser.add_argument("--undo", metavar="ROUND_ID", help="revert exactly one round")
    parser.add_argument("--list", action="store_true", help="list recorded rounds")
    parser.add_argument("--budget", type=int, default=3)
    parser.add_argument("--scope", default="not-blocking-me")
    parser.add_argument("--no-verify", action="store_true", help="skip the independent verifier")
    parser.add_argument("--chain", type=int, metavar="N",
                        help="execute N lugs ONE AT A TIME, verifying each before the next")
    parser.add_argument("--runner", default=None, help="path to ozi_autopilot.py")
    parser.add_argument("--on-refute", choices=("stop", "remediate", "continue"),
                        default="remediate",
                        help="on refusal: remediate (default — validate/fix/re-validate "
                             "until it passes), stop (halt immediately), continue")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.undo:
        result = undo(args.root, args.undo)
        print(json.dumps(result, indent=2) if args.json else
              (f"round {args.undo} reverted ({result['commits']} commit(s))" if result["ok"]
               else f"undo FAILED: {result['error']}"))
        return 0 if result["ok"] else 1

    if args.list:
        d = _rounds_dir(args.root)
        rows = []
        for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, name), "r", encoding="utf-8") as fh:
                    r = json.load(fh)
                rows.append((r.get("round_id"), r.get("verdict", "?"),
                             r.get("impact", {}).get("commit_count", 0),
                             len(r.get("claims", []))))
            except Exception:
                continue
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            print(f"{'round':26s} {'verdict':11s} {'commits':>7s} {'claims':>7s}")
            for rid, verdict, commits, claims in rows:
                print(f"{rid:26s} {verdict:11s} {commits:7d} {claims:7d}")
        return 0

    if args.chain:
        runner = args.runner or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "ozi_autopilot.py")
        rec = run_chain(args.root, args.chain, args.scope, runner,
                        on_refute=args.on_refute)
        print()
        print(json.dumps(rec, indent=2) if args.json else render_chain(rec))
        return 0 if rec["verdict"] in ("CLEAN", "UNVERIFIED") else 1

    if args.open:
        rec = open_round(args.root, args.budget, args.scope)
        print(json.dumps(rec, indent=2))
        return 0

    if args.close:
        with open(args.close, "r", encoding="utf-8") as fh:
            rec = json.load(fh)
        rec = close_round(args.root, rec, verify=not args.no_verify)
        print(json.dumps(rec, indent=2) if args.json else render(rec))
        return 0 if rec["verdict"] in ("CLEAN", "UNVERIFIED") else 1

    parser.error("one of --open / --close / --undo / --list is required")


if __name__ == "__main__":
    sys.exit(main())
