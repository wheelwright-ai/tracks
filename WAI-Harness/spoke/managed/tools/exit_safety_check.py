#!/usr/bin/env python3
"""exit_safety_check.py -- ONE deterministic SAFE-TO-EXIT verdict.

impl-exitclarity-1-exit-safety-verdict-tool-v1 (initiative-exit-clarity-v1).

The question this answers is the one the operator actually has at close: am I safe
to walk away, and if not, exactly what do I run first? Today that answer is spread
across CSRP exit codes, converge candidates, git state and savepoint validity, and
the operator is left inferring it. This aggregates them into one verdict plus a
rendered block a ceremony prints as its FINAL output.

Three verdicts:
  SAFE_TO_EXIT -- nothing blocking, nothing to remediate.
  SAFE_AFTER   -- ordered remediations remain; each carries the exact command.
  NOT_SAFE     -- something blocking; work would be lost or stranded.

DESIGN RULES (from the lug's adversarial critique -- do not regress these):
  * READ-ONLY. This tool never mutates state. Running it twice is identical and
    leaves `git status --porcelain` unchanged. A checker with side effects at exit
    is worse than no checker.
  * DEGRADE LOUDLY, NEVER SILENTLY PASS. A check that cannot run reports
    check_unavailable and is RENDERED. It never crashes the ceremony (always
    exit 0 with a block) and never counts as a pass. "A checker that itself
    silently fails is worse than none."
  * REUSE, DON'T REIMPLEMENT. CSRP and converge logic already exist and drift;
    this INVOKES them and maps their exit codes rather than copying their rules.
  * NEVER SYNTHESIZE A SESSION ID. Two id formats exist in the wild
    ('mario-2026-04-14-164612' and 'session-20260626-1205'). --session-id wins,
    else session-guard.json's session_id VERBATIM, else check_unavailable.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent

# severities
BLOCKING = "blocking"      # -> NOT_SAFE
REMEDIABLE = "remediable"  # -> SAFE_AFTER
INFO = "info"              # never affects the verdict
UNAVAILABLE = "unavailable"  # rendered loudly; never a pass, never blocking


def _run(cmd, cwd=None, timeout=60):
    """Run a command, returning (rc, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # noqa: BLE001 — a broken subsystem must not crash the ceremony
        return None, "", str(e)


def _git(args, repo):
    return _run(["git", "-C", str(repo)] + args)


def _finding(check, severity, reason, exact_command=None):
    return {"check": check, "severity": severity, "reason": reason,
            "exact_command": exact_command or ""}


def _rel(p, repo):
    """Path relative to the repo root when it is inside it, else absolute.

    Commands are meant to be PASTED by a tired operator, so they read
    `cd <repo> && python3 WAI-Harness/...` rather than carrying a 90-char
    absolute path per argument."""
    try:
        return str(Path(p).resolve().relative_to(Path(repo).resolve()))
    except (ValueError, OSError):
        return str(p)


# ---------------------------------------------------------------- checks

def check_git(repo):
    """Dirty tree, unpushed commits, missing upstream, session branch not merged.

    'Commits stranded on session branches' is a known recurring failure, so an
    unmerged session branch is called out explicitly rather than left implicit."""
    out = []
    rc, _, _ = _git(["rev-parse", "--is-inside-work-tree"], repo)
    if rc != 0:
        out.append(_finding("git", UNAVAILABLE, "not a git repository: %s" % repo))
        return out

    rc, dirty, _ = _git(["status", "--porcelain"], repo)
    if rc == 0 and dirty.strip():
        n = len([x for x in dirty.splitlines() if x.strip()])
        out.append(_finding(
            "git.dirty", BLOCKING, "%d uncommitted file(s) — work would be left behind" % n,
            "cd %s && git status --porcelain   # scope your adds, then commit" % repo))

    rc, branch, _ = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo)
    branch = branch.strip() if rc == 0 else ""

    rc_up, upstream, _ = _git(["rev-parse", "--abbrev-ref", "@{u}"], repo)
    if rc_up != 0:
        # No upstream does NOT mean unpushed. A session may fast-forward its branch
        # straight onto origin/main (branch:main) — the CSRP-safe way to land work when
        # the main checkout is dirty and shared by other live sessions, since it touches
        # no working tree. That leaves HEAD fully pushed with no tracking ref. Ask the
        # question that actually matters — "is HEAD reachable from a remote?" — instead
        # of inferring it from tracking config.
        rc_c, remotes, _ = _git(["branch", "-r", "--contains", "HEAD"], repo)
        containing = [r.strip() for r in remotes.splitlines() if r.strip()] if rc_c == 0 else []
        if containing:
            out.append(_finding(
                "git.pushed_without_upstream", INFO,
                "branch '%s' has no upstream, but HEAD is contained in %s — work IS pushed"
                % (branch, ", ".join(containing[:3]))))
        else:
            out.append(_finding(
                "git.no_upstream", REMEDIABLE,
                "branch '%s' has no upstream and HEAD is on no remote — nothing is pushed anywhere"
                % branch,
                "cd %s && git push -u origin %s" % (repo, branch or "HEAD")))
    else:
        rc, counts, _ = _git(["rev-list", "--left-right", "--count", "@{u}...HEAD"], repo)
        if rc == 0 and counts.strip():
            parts = counts.split()
            ahead = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            if ahead:
                out.append(_finding(
                    "git.unpushed", BLOCKING,
                    "%d commit(s) not pushed to %s" % (ahead, upstream.strip()),
                    "cd %s && git push" % repo))

    # LANDING, against the one shared definition (landing.LANDED_DEFINITION).
    #
    # This used to ask only "is HEAD unmerged into main?" and print
    # `git merge --ff-only` for every answer -- a command that fails precisely
    # when the branch has diverged, which is when the operator needs it. It also
    # collapsed ahead and behind into one finding, hiding the half that actually
    # ships: harness_upgrade distributes this working tree, so BEHIND is what the
    # fleet receives.
    #
    # SEVERITY IS DELIBERATELY SPLIT. Being ahead is a landing DEBT -- legitimately
    # owed while concurrent CSRP lanes are live, so it is REMEDIABLE, tracked and
    # retried rather than blocking. A gate that blocked every concurrent session
    # would be routed around within a week. Being behind is BLOCKING: it is never
    # a normal state to exit in, and it is what gets distributed.
    try:
        if str(TOOLS) not in sys.path:
            sys.path.insert(0, str(TOOLS))
        import landing
        st = landing.landing_status(repo)
        if st["state"] == landing.UNKNOWN:
            out.append(_finding(
                "git.landing_unknown", REMEDIABLE,
                "landing could not be confirmed — %s" % st["severity_note"]))
        elif st["state"] in (landing.BEHIND, landing.DIVERGED):
            out.append(_finding(
                "git.behind_canon", BLOCKING,
                "%s — %s" % (landing.describe(st), st["severity_note"]),
                st["remediation"]))
        elif st["state"] == landing.AHEAD:
            out.append(_finding(
                "git.unlanded", REMEDIABLE,
                "%s — %s" % (landing.describe(st), st["severity_note"]),
                st["remediation"]))
    except Exception as _lexc:  # noqa: BLE001
        out.append(_finding(
            "git.landing_unavailable", UNAVAILABLE,
            "landing check failed to run (%s) — landing is unconfirmed, "
            "which is not landed" % _lexc))
    return out


def check_csrp(repo, base):
    """Invoke csrp_notice_check.sh and map its exit code.

    It has NO JSON mode: it prints human lines and communicates via exit 0/10 only.
    So parse notice ids by regex over its '[CSRP] {id}' stdout; if parsing fails,
    degrade to an exit-code-only finding rather than guessing."""
    tool = TOOLS / "csrp_notice_check.sh"
    if not tool.exists():
        return [_finding("csrp", UNAVAILABLE, "csrp_notice_check.sh not found at %s" % tool)]
    rc, so, se = _run(["bash", str(tool)], cwd=str(repo))
    if rc is None:
        return [_finding("csrp", UNAVAILABLE, "csrp_notice_check.sh failed to run: %s" % se[:120])]
    if rc == 0:
        return []
    if rc != 10:
        return [_finding("csrp", UNAVAILABLE,
                         "csrp_notice_check.sh exited %s (expected 0 or 10)" % rc)]
    ids = [m for m in re.findall(r"\[CSRP\]\s+(\S+)", so or "")
           if m.lower() not in ("no",)]
    # Does any notice flag THIS lane's work unmerged/unpushed? That is blocking.
    blob = (so or "").lower()
    blocking = any(k in blob for k in ("unmerged", "unpushed", "reconcile up", "diverge"))
    if ids:
        reason = "%d CSRP notice(s) unacknowledged: %s" % (len(ids), ", ".join(ids[:3]))
    else:
        reason = ("CSRP notices pending, run the ceremony 0.4 step for detail "
                  "(could not parse notice ids from output)")
    return [_finding("csrp", BLOCKING if blocking else REMEDIABLE, reason,
                     "cd %s && bash %s" % (repo, _rel(tool, repo)))]


def _resolve_session_id(base, arg_session_id):
    """--session-id wins; else session-guard.json's session_id VERBATIM; else None.

    Never normalize or synthesize: two id formats are live in the wild and a
    synthesized id would silently query the wrong lane."""
    if arg_session_id:
        return arg_session_id, "arg"
    guard = Path(base) / "runtime" / "session-guard.json"
    try:
        sid = json.loads(guard.read_text()).get("session_id")
        if sid:
            return sid, "session-guard.json"
    except Exception:  # noqa: BLE001 — absent/malformed guard is an expected state
        pass
    return None, None


def check_lanes(base, session_id, repo):
    """Peer lanes absorbable into this one, via converge_closeout.py candidates.

    Contract: --base/--session-id; exit 10 with {absorption_candidates,count} JSON
    on stdout when candidates exist, 0 when none."""
    tool = TOOLS / "converge_closeout.py"
    if not tool.exists():
        return [_finding("lanes", UNAVAILABLE, "converge_closeout.py not found")]
    sid, src = _resolve_session_id(base, session_id)
    if not sid:
        return [_finding(
            "lanes", UNAVAILABLE,
            "no session id: --session-id not given and %s/runtime/session-guard.json "
            "has none (runtime/ is gitignored, so worktrees often lack it)" % base,
            "cd %s && python3 %s candidates --base %s --session-id <your-session-id>"
            % (repo, _rel(tool, repo), _rel(base, repo)))]
    rc, so, se = _run([sys.executable, str(tool), "candidates", "--base", str(base),
                       "--session-id", sid], cwd=str(repo))
    if rc is None:
        return [_finding("lanes", UNAVAILABLE, "converge_closeout.py failed: %s" % se[:120])]
    if rc == 0:
        return []
    if rc != 10:
        return [_finding("lanes", UNAVAILABLE,
                         "converge_closeout.py candidates exited %s (expected 0 or 10)" % rc)]
    try:
        data = json.loads(so)
        count = data.get("count", len(data.get("absorption_candidates", [])))
    except Exception:  # noqa: BLE001
        return [_finding("lanes", UNAVAILABLE,
                         "converge candidates exited 10 but its JSON did not parse",
                         "cd %s && python3 %s candidates --base %s --session-id %s"
                         % (repo, _rel(tool, repo), _rel(base, repo), sid))]
    if not count:
        return []
    return [_finding(
        "lanes.absorbable", REMEDIABLE,
        "%d peer lane(s) absorbable into this session (id via %s)" % (count, src),
        "cd %s && python3 %s converge --base %s --session-id %s --repo ."
        % (repo, _rel(tool, repo), _rel(base, repo), sid))]


def check_track(base, repo):
    """An unflushed turn buffer means this turn's record would be lost.

    The buffer is TRANSIENT: the flush hook unlink()s it after flushing, so ABSENT
    is a PASS (already flushed), not a missing-file error. Two paths are live
    (lane dir first, then runtime) -- check both, mirroring stop-track-flush.sh."""
    runtime = Path(base) / "runtime"
    candidates = [runtime / "track-buffer.json"]
    lanes = runtime / "lanes"
    if lanes.is_dir():
        try:
            candidates += [d / "track-buffer.json" for d in lanes.iterdir() if d.is_dir()]
        except OSError:
            pass
    present = [p for p in candidates if p.exists()]
    if not present:
        return []  # absent == already flushed == pass
    return [_finding(
        "track.buffer", BLOCKING,
        "unflushed turn buffer at %s — this turn's record would be lost" % _rel(present[0], repo),
        "complete the turn (the Stop hook flushes it), or run "
        "python3 .claude/hooks/flush_buffer.py")]


def check_savepoint(base, repo):
    """If a savepoint exists, it must validate. No savepoint is not a failure."""
    tool = TOOLS / "validate_savepoint.py"
    # Savepoints live under initiatives/savepoints/{initiative_id}/ — wai-savepoint.md
    # explicitly RETIRES the loose {BASE}/savepoints/ home. This check read the retired
    # path, found nothing, and reported "nothing to validate", which reads as a pass.
    # Measured in mywheel at the time of the fix: the loose home held 0 savepoints while
    # 320 lived in the initiative-scoped tree — so the exit gate was inert on every spoke
    # that had migrated, which is all of them. A gate that cannot find its subject must
    # never be indistinguishable from a gate that passed.
    sp_roots = [Path(base) / "initiatives" / "savepoints", Path(base) / "savepoints"]
    sps = []
    for root in sp_roots:
        if not root.is_dir():
            continue
        try:
            sps.extend(root.rglob("*.json"))
        except OSError as e:
            return [_finding("savepoint", UNAVAILABLE, "cannot list savepoints: %s" % e)]
    if not any(r.is_dir() for r in sp_roots):
        return [_finding("savepoint", INFO, "no savepoints directory — nothing to validate")]
    try:
        sps = sorted(sps, key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError as e:
        return [_finding("savepoint", UNAVAILABLE, "cannot stat savepoints: %s" % e)]
    if not sps:
        return [_finding("savepoint", INFO, "no savepoint recorded — nothing to validate")]
    if not tool.exists():
        return [_finding("savepoint", UNAVAILABLE, "validate_savepoint.py not found")]
    latest = sps[0]
    rc, so, se = _run([sys.executable, str(tool), str(latest), "--spoke-root", str(repo)])
    if rc is None:
        return [_finding("savepoint", UNAVAILABLE, "validate_savepoint.py failed: %s" % se[:120])]
    if rc != 0:
        return [_finding(
            "savepoint.invalid", BLOCKING,
            "latest savepoint %s failed validation" % latest.name,
            "cd %s && python3 %s %s --spoke-root ." % (repo, _rel(tool, repo), _rel(latest, repo)))]
    return []


def check_unstamped_completions(base):
    """RULE 2 (spec-lug-lifecycle-ownership-v1, atomic completion): completing
    an impl lug MEANS stamping status:completed + completed_at + commit_sha
    AND moving it to completed/, never deferred to closeout. A lug that
    carries a commit_sha/completed_at but is not physically in completed/ is
    the canonical basher incident (work committed, artifact left claiming
    status:open) -- flag it, never silently tolerate it."""
    lugs = Path(base) / "lugs" / "bytype"
    if not lugs.is_dir():
        return []
    offenders = []
    try:
        for status_dir in ("open", "in_progress", "needs_attention"):
            for p in lugs.glob("*/%s/*.json" % status_dir):
                try:
                    data = json.loads(p.read_text())
                except (OSError, ValueError):
                    continue
                if isinstance(data, dict) and (data.get("commit_sha") or data.get("completed_at")):
                    offenders.append(data.get("id") or p.stem)
    except OSError as e:
        return [_finding("lug_completion", UNAVAILABLE, "could not scan lugs/bytype/: %s" % e)]
    if not offenders:
        return []
    names = ", ".join(offenders[:3])
    return [_finding(
        "lug_completion.unstamped", REMEDIABLE,
        "%d lug(s) carry a commit_sha/completed_at but are not in completed/ — "
        "atomic-completion violation (RULE 2, spec-lug-lifecycle-ownership-v1): %s"
        % (len(offenders), names),
        "python3 WAI-Harness/spoke/managed/tools/ozi_autopilot.py --dry-run  "
        "# the next real (non-dry-run) groom pass auto-reconciles these to completed/; "
        "or move + stamp them by hand now")]


def check_intent_capture(base, session_id, repo):
    """W1, epic-close-the-presumption-gap-v1: no ask leaves a session as prose.

    intent_capture_gate.py reconciles every intent recorded in this session's
    track against artifacts on disk. It shipped complete and tested and was
    invoked by ZERO ceremonies -- the instruction to drain its MISSING list
    existed in the closeout doc while nothing ever produced one.

    Wired HERE rather than inline in wai-savepoint.md / wai-closeout.md on
    purpose. Both ceremonies already call this tool as their final step, so one
    check covers both; and the ceremony line budget is exhausted (savepoint
    470/470 headroom 0, closeout 1369/1370 headroom 1), so an inline call
    would have had to evict another step to fit.

    BLOCKING: an ask the operator made that no artifact carries is exactly the
    thing that must not survive an exit verdict. Contract: exit 0 = clean,
    10 = MISSING, anything else = the gate itself is broken (never a pass)."""
    tool = TOOLS / "intent_capture_gate.py"
    if not tool.exists():
        return [_finding("intent_capture", UNAVAILABLE, "intent_capture_gate.py not found")]
    sid, src = _resolve_session_id(base, session_id)
    if not sid:
        return [_finding(
            "intent_capture", UNAVAILABLE,
            "no session id: cannot locate this session's track to reconcile asks against",
            "cd %s && python3 %s --track %s/sessions/<session-id>/track.jsonl --base %s"
            % (repo, _rel(tool, repo), _rel(base, repo), _rel(base, repo)))]
    track = Path(base) / "sessions" / sid / "track.jsonl"
    if not track.exists():
        return [_finding(
            "intent_capture", UNAVAILABLE,
            "session track not found at %s (id via %s)" % (_rel(track, repo), src))]
    rc, so, se = _run([sys.executable, str(tool), "--track", str(track),
                       "--base", str(base), "--json"], cwd=str(repo), timeout=120)
    if rc is None:
        return [_finding("intent_capture", UNAVAILABLE,
                         "intent_capture_gate.py failed: %s" % se[:120])]
    if rc not in (0, 10):
        return [_finding("intent_capture", UNAVAILABLE,
                         "intent_capture_gate.py exited %s (expected 0 or 10)" % rc)]
    try:
        rep = json.loads(so)
        missing = rep.get("missing", [])
        summary = rep.get("summary", {})
    except Exception:  # noqa: BLE001
        return [_finding("intent_capture", UNAVAILABLE,
                         "intent_capture_gate.py exited %s but its JSON did not parse" % rc)]
    out = []
    # netnet line (impl-exitclarity-3): the intents/captured/missing accounting is
    # always rendered, not just on failure, so the operator sees the drain ratio
    # every exit -- s138 proved 45/41/4 live; a silent pass hides that reconciliation
    # happened at all.
    out.append(_finding(
        "intent_capture.summary", INFO,
        "%d intent(s) | %d captured | %d missing" % (
            summary.get("intents", 0), summary.get("captured", 0),
            summary.get("missing", len(missing)))))
    unparsed = summary.get("unparsed_entries") or 0
    if unparsed:
        out.append(_finding(
            "intent_capture.unparsed", UNAVAILABLE,
            "%d track entr(ies) carried no recoverable intent text — the gate could "
            "not police them" % unparsed))
    if not missing:
        return out
    first = missing[0].get("intent", "")[:90]
    out.append(_finding(
        "intent_capture.missing", BLOCKING,
        "%d of %d recorded ask(s) have no artifact on disk — e.g. \"%s\"" % (
            len(missing), summary.get("intents", len(missing)), first),
        "cd %s && python3 %s --track %s --base %s   # then lug each MISSING, or record an explicit wont-do"
        % (repo, _rel(tool, repo), _rel(track, repo), _rel(base, repo))))
    return out


def check_uncertified_completions(base, session_id, repo):
    """A lug completed BY HAND this session, carrying no certification.

    The choke-point gate in wai_ozi_dispatch covers every programmatic caller.
    It does not cover a human or an interactive agent writing the JSON directly
    -- which is exactly what happened while W1 and W2 were being built: two lugs
    were marked completed by a script, and no gate saw either of them. A gate
    with a hand-shaped hole in it is the presumption gap wearing a badge.

    REMEDIABLE, not blocking: certifying by hand at exit is cheap and the
    operator may have a reason, but it must never be silent."""
    lugs = Path(base) / "lugs" / "bytype"
    if not lugs.is_dir():
        return []
    sid, _src = _resolve_session_id(base, session_id)
    offenders = []
    try:
        for p in lugs.glob("*/completed/*.json"):
            try:
                d = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
            if not isinstance(d, dict) or d.get("certification"):
                continue
            # attribute to THIS session only -- someone else's legacy lug is the
            # recertification sweep's problem, not this exit's.
            stamped = str(d.get("completed_by") or d.get("session_id")
                          or d.get("commit_session") or "")
            if sid and sid in stamped:
                offenders.append(d.get("id") or p.stem)
    except OSError as e:
        return [_finding("completion_certification", UNAVAILABLE,
                         "could not scan completed lugs: %s" % e)]
    if not offenders:
        return []
    return [_finding(
        "completion_certification.uncertified", REMEDIABLE,
        "%d lug(s) completed this session carry no certification — they were "
        "marked done by hand, bypassing the choke-point gate: %s"
        % (len(offenders), ", ".join(offenders[:3])),
        "cd %s && python3 %s <lug-path> --repo . --base %s   # certify, or record why not"
        % (repo, _rel(TOOLS / "completion_certifier.py", repo), _rel(base, repo)))]


def check_lugs(base):
    """INFORMATIONAL ONLY -- never affects the verdict.

    Per-session claim attribution is not implementable today: most live
    in_progress lugs carry no session-claim field (see impl-lug-session-claim-field-v1),
    so this cannot know which are THIS session's. Reporting a count as a footnote is
    honest; blocking exit on someone else's lug would not be."""
    lugs = Path(base) / "lugs" / "bytype"
    if not lugs.is_dir():
        return []
    try:
        n = len(list(lugs.glob("*/in_progress/*.json")))
    except OSError:
        return []
    if not n:
        return []
    return [_finding("lugs.in_progress", INFO,
                     "%d lug(s) in_progress fleet-wide (not attributable to this session)" % n)]


# ---------------------------------------------------------------- aggregate

def aggregate(findings):
    if any(f["severity"] == BLOCKING for f in findings):
        return "NOT_SAFE"
    if any(f["severity"] in (REMEDIABLE, UNAVAILABLE) for f in findings):
        return "SAFE_AFTER"
    return "SAFE_TO_EXIT"


def converge_line(findings):
    """The mandatory CONVERGE line -- present in EVERY verdict, yes or no."""
    for f in findings:
        if f["check"] == "lanes.absorbable":
            return "CONVERGE RECOMMENDED: yes (%s)" % f["reason"], f["exact_command"]
    for f in findings:
        if f["check"] == "lanes" and f["severity"] == UNAVAILABLE:
            return "CONVERGE RECOMMENDED: unknown (%s)" % f["reason"], f["exact_command"]
    return "CONVERGE RECOMMENDED: no (no absorbable peer lanes)", ""


def run_checks(repo, base, session_id):
    findings = []
    findings += check_git(repo)
    findings += check_csrp(repo, base)
    findings += check_lanes(base, session_id, repo)
    findings += check_track(base, repo)
    findings += check_savepoint(base, repo)
    findings += check_intent_capture(base, session_id, repo)
    findings += check_uncertified_completions(base, session_id, repo)
    findings += check_lugs(base)
    findings += check_unstamped_completions(base)
    return findings


def render(result):
    """Fixed-format block, ~12 lines, printed as a ceremony's FINAL output."""
    findings = result["findings"]
    lines = ["", "EXIT SAFETY"]
    order = {BLOCKING: 0, REMEDIABLE: 1, UNAVAILABLE: 2, INFO: 3}
    actionable = [f for f in findings if f["severity"] != INFO]
    actionable.sort(key=lambda f: order.get(f["severity"], 9))
    if not actionable:
        lines.append("  all checks pass")
    for f in actionable:
        tag = {BLOCKING: "BLOCK", REMEDIABLE: "TODO ", UNAVAILABLE: "UNAVL"}.get(
            f["severity"], "     ")
        lines.append("  [%s] %s: %s" % (tag, f["check"], f["reason"]))
        if f["exact_command"]:
            lines.append("          $ %s" % f["exact_command"])
    for f in findings:
        if f["severity"] == INFO:
            lines.append("  (note) %s" % f["reason"])
    cline, ccmd = converge_line(findings)
    lines.append("  " + cline)
    # Only repeat the command if it was not already rendered above as a finding —
    # the block is read by a tired operator; a duplicated 140-char command is noise.
    already = any(f["exact_command"] == ccmd for f in actionable)
    if ccmd and not already and cline.startswith("CONVERGE RECOMMENDED: yes"):
        lines.append("          $ %s" % ccmd)
    # CAPTURED (impl-exitclarity-3): only rendered when the ceremony passed
    # --captured -- a caller that never adopted the capture-then-exit contract
    # (e.g. wai-savepoint.md, which backs every first_action with a lug already)
    # gets no line rather than a misleading "CAPTURED: none".
    captured = result.get("captured_ids")
    if captured is not None:
        if captured:
            lines.append("  CAPTURED: %d lug(s): %s" % (len(captured), ", ".join(captured)))
        else:
            lines.append("  CAPTURED: none")
    verdict = result["verdict"]
    if verdict == "SAFE_TO_EXIT":
        lines.append("  VERDICT: SAFE TO EXIT")
    elif verdict == "SAFE_AFTER":
        lines.append("  VERDICT: SAFE AFTER - run the commands above, then re-run")
    else:
        lines.append("  VERDICT: NOT SAFE - run the commands above, then re-run")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="one deterministic SAFE-TO-EXIT verdict")
    ap.add_argument("--base", default=None,
                    help="spoke local base; default resolves via wai_paths")
    ap.add_argument("--session-id", default=None,
                    help="wins over session-guard.json; never synthesized")
    ap.add_argument("--repo", default=None, help="git repo root; default cwd's toplevel")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--render", action="store_true", help="terminal verdict block (default)")
    ap.add_argument("--captured", default=None,
                    help="comma-separated lug ids captured this session's recommendations "
                         "(wai-closeout.md Step 3 capture-then-exit contract); omit if the "
                         "calling ceremony has no capture step")
    a = ap.parse_args(argv)

    repo = a.repo
    if not repo:
        rc, out, _ = _run(["git", "rev-parse", "--show-toplevel"])
        repo = out.strip() if rc == 0 and out.strip() else os.getcwd()

    base = a.base
    if not base:
        try:
            sys.path.insert(0, str(TOOLS))
            import wai_paths  # noqa: PLC0415 — optional dep; fall back if absent
            base = str(Path(wai_paths.category(repo, "runtime")).parent)
        except Exception:  # noqa: BLE001
            base = str(Path(repo) / "WAI-Harness" / "spoke" / "local")

    findings = run_checks(repo, base, a.session_id)
    result = {"verdict": aggregate(findings), "findings": findings,
              "repo": str(repo), "base": str(base)}
    result["converge_recommended"] = converge_line(findings)[0].split(": ", 1)[1]
    if a.captured is not None:
        result["captured_ids"] = [c.strip() for c in a.captured.split(",") if c.strip()]

    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print(render(result))
    # Always exit 0: this REPORTS, it does not gate. A checker that kills the
    # ceremony on a finding would make ceremonies avoid calling it.
    return 0


if __name__ == "__main__":
    sys.exit(main())
