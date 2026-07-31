#!/usr/bin/env python3
"""recertification_sweep.py -- re-check what this wheel has already declared done.

W3 of epic-close-the-presumption-gap-v1.

W2 stops NEW false positives at the completion transition. It does nothing about
the backlog of them. 1399 lugs sit in completed/. Only 213 carry both verify steps
and file_targets, so 85% of everything this wheel has declared done cannot be
mechanically re-checked by anyone.

THREE BUCKETS, NEVER TWO:

  CERTIFIED   re-checked against its own verify[] and it holds.
  REFUTED     re-checked and it does not hold. Reopened with the evidence.
  UNCHECKABLE no verify steps, or none any certifier can decide. NOT certified,
              and never counted as such.

The third bucket is the whole point. Folding UNCHECKABLE into CERTIFIED would
produce a reassuring number and destroy the measurement -- and reporting those
1186 lugs as WRONG would be its own fabrication. "Nobody can tell" is the honest
finding, and it is what the operator is actually owed.

FALSE-REFUTED IS A REAL RISK AND IS TREATED AS ONE. An old lug's verify steps
describe the tree as it was. A file legitimately refactored away years later can
fail a check without the original work having been wrong. So:
  * --apply is OFF by default. The sweep reports before it touches anything.
  * A reopened lug keeps its completion history (`prior_completion`) rather than
    having it overwritten.
  * Every reopen carries the exact check that failed, so a human can overturn it.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import completion_certifier as cc  # noqa: E402

CERTIFIED = "certified"
REFUTED = "refuted"
UNCHECKABLE = "uncheckable"


def is_checkable(lug):
    """The lug's own definition: it carries verify steps AND file_targets.

    Both matter. verify[] without file_targets says what should be true but not
    where to look; file_targets without verify[] says where the work landed but
    not what would make it right."""
    verify = lug.get("verify") or lug.get("acceptance_criteria")
    return bool(verify) and bool(lug.get("file_targets"))


class Unreadable:
    """A file in completed/ that could not be parsed.

    It still occupies a slot in the corpus, so it must land in a bucket. The first
    version of this loop `continue`d past it, which dropped it from all three
    counts -- a file silently missing from a census about silent omissions. Caught
    by the independent certifier, not by me.
    """

    def __init__(self, error):
        self.error = error


def iter_completed(base):
    root = Path(base) / "lugs" / "bytype"
    if not root.is_dir():
        return
    for path in sorted(root.glob("*/completed/*.json")):
        try:
            yield path, json.loads(path.read_text())
        except (OSError, ValueError) as e:
            yield path, Unreadable(str(e))


def classify(lug, repo, base, use_agent=False):
    """Return (bucket, verdict). Never raises -- a crash is UNCHECKABLE, not a pass."""
    if isinstance(lug, Unreadable):
        return UNCHECKABLE, {"reason": "file is not valid JSON: %s" % lug.error[:60],
                             "disposition": "uncheckable"}
    if not is_checkable(lug):
        missing = []
        if not (lug.get("verify") or lug.get("acceptance_criteria")):
            missing.append("verify steps")
        if not lug.get("file_targets"):
            missing.append("file_targets")
        return UNCHECKABLE, {"reason": "no %s" % " and no ".join(missing),
                             "disposition": "uncheckable"}
    try:
        v = cc.certify(lug, repo, base, use_agent=use_agent)
    except Exception as e:  # noqa: BLE001
        return UNCHECKABLE, {"reason": "certifier error: %s" % e,
                             "disposition": "uncheckable"}
    if v["disposition"] == cc.APPROVED:
        return CERTIFIED, v
    if v["disposition"] == cc.HALTED:
        return REFUTED, v
    return UNCHECKABLE, v


def reopen(path, lug, verdict, now_iso):
    """Reopen a refuted lug WITHOUT destroying its completion history.

    The claim was made; erasing it would lose the evidence of how much of 'done'
    was real, which is the finding this sweep exists to produce."""
    lug["prior_completion"] = {
        "status": "completed",
        "completed_at": lug.get("completed_at"),
        "commit_sha": lug.get("commit_sha"),
        "refuted_at": now_iso,
    }
    lug["status"] = "open"
    lug["reopened_by"] = "recertification_sweep (W3, epic-close-the-presumption-gap-v1)"
    lug["reopened_reason"] = verdict.get("reason", "verify steps do not hold")
    lug["refutation_evidence"] = verdict.get("failed_checks", [])
    lug.pop("completed_at", None)
    lug.pop("commit_sha", None)
    dest = path.parent.parent / "open" / path.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(lug, indent=2) + "\n")
    path.unlink()
    return str(dest)


def sweep(base, repo, use_agent=False, apply=False, limit=None, jobs=1,
          progress=None):
    """Two phases, because they have wildly different costs.

    PHASE 1 is mechanical: fast, free, deterministic, and decides the lugs whose
    verify steps name a command, a path or a lug id.

    PHASE 2 is the agent pass, and only runs with use_agent. It escalates the
    lugs that are checkable-by-definition but whose verify steps are prose, to
    the read-only pattern-gate agent. Each one is a subprocess taking tens of
    seconds, so 209 of them serially is hours. They share no state and cannot
    write, so they run concurrently -- which is what the lug asked for.
    """
    now = datetime.now(timezone.utc).isoformat()
    report = {
        "measured_at": now, "base": str(base),
        "mode": "agent" if use_agent else "mechanical-only",
        "applied": bool(apply), "jobs": jobs,
        "totals": {"completed": 0, "checkable": 0,
                   CERTIFIED: 0, REFUTED: 0, UNCHECKABLE: 0},
        "refuted": [], "uncheckable_reasons": {}, "reopened": [],
        "agent_escalated": 0, "agent_decided": 0,
    }
    n = 0
    deferred = []  # (path, lug) checkable but not decided mechanically

    def record(path, lug, bucket, verdict):
        report["totals"][bucket] += 1
        if bucket == REFUTED:
            report["refuted"].append({
                "id": (lug.get("id") if isinstance(lug, dict) else None) or path.stem,
                "path": str(path), "reason": verdict.get("reason"),
                "basis": "agent" if verdict.get("_agent") else "mechanical",
                "failed": [c.get("observed") for c in verdict.get("failed_checks", [])]})
            if apply:
                report["reopened"].append(reopen(path, lug, verdict, now))
        elif bucket == UNCHECKABLE:
            r = verdict.get("reason", "unknown")[:80]
            report["uncheckable_reasons"][r] = report["uncheckable_reasons"].get(r, 0) + 1

    # ---- phase 1: mechanical
    for path, lug in iter_completed(base):
        report["totals"]["completed"] += 1
        if limit is not None and n >= limit:
            continue
        checkable = not isinstance(lug, Unreadable) and is_checkable(lug)
        if checkable:
            report["totals"]["checkable"] += 1
            n += 1
        bucket, verdict = classify(lug, repo, base, use_agent=False)
        if use_agent and checkable and bucket == UNCHECKABLE:
            deferred.append((path, lug))  # decided in phase 2, not counted yet
            continue
        record(path, lug, bucket, verdict)

    # ---- phase 2: agent escalation
    if deferred:
        report["agent_escalated"] = len(deferred)
        import concurrent.futures

        def judge(item):
            path, lug = item
            try:
                return path, lug, cc.certify(lug, repo, base, use_agent=True)
            except Exception as e:  # noqa: BLE001
                return path, lug, {"disposition": cc.ESCALATE,
                                   "reason": "certifier error: %s" % e,
                                   "failed_checks": [], "uncheckable": []}

        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
            for path, lug, v in ex.map(judge, deferred):
                done += 1
                if progress and done % 10 == 0:
                    progress("agent pass %d/%d" % (done, len(deferred)))
                v["_agent"] = True
                if v["disposition"] == cc.APPROVED:
                    bucket = CERTIFIED
                elif v["disposition"] == cc.HALTED:
                    bucket = REFUTED
                else:
                    bucket = UNCHECKABLE
                if bucket != UNCHECKABLE:
                    report["agent_decided"] += 1
                record(path, lug, bucket, v)

    decided = report["totals"][CERTIFIED] + report["totals"][REFUTED]
    report["refutation_rate"] = (
        round(report["totals"][REFUTED] / decided, 4) if decided else None)
    report["decided"] = decided
    report["undecidable_share"] = (
        round(report["totals"][UNCHECKABLE] / report["totals"]["completed"], 4)
        if report["totals"]["completed"] else None)
    return report


LEDGER = "reports/recertification-ledger.jsonl"


def record_ledger(report, base):
    """Append this run's numbers and compare to the previous run.

    THE REASON THIS EXISTS. A sweep run once produces a number, the number gets
    quoted in a report, and the corpus quietly goes on filling with uncheckable
    completions. That has already happened here at least once -- the operator's
    words: 'we've done this sweep before, so wonder how this will result in real
    change that sticks.' A one-shot measurement cannot stick. A RATCHET can:
    every run is recorded, and the run says out loud whether the share of work
    nobody can check went UP since last time.

    Returns the delta dict (None on the first ever run).
    """
    path = Path(base) / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    prev = None
    if path.exists():
        try:
            lines = [l for l in path.read_text().splitlines() if l.strip()]
            if lines:
                prev = json.loads(lines[-1])
        except (OSError, ValueError):
            prev = None
    entry = {
        "measured_at": report["measured_at"], "mode": report["mode"],
        "completed": report["totals"]["completed"],
        "certified": report["totals"][CERTIFIED],
        "refuted": report["totals"][REFUTED],
        "uncheckable": report["totals"][UNCHECKABLE],
        "undecidable_share": report["undecidable_share"],
    }
    delta = None
    if prev and prev.get("undecidable_share") is not None \
            and entry["undecidable_share"] is not None:
        moved = round(entry["undecidable_share"] - prev["undecidable_share"], 4)
        delta = {
            "since": prev["measured_at"],
            "undecidable_share_delta": moved,
            # RATCHET: the share of work nobody can check must not grow. It is the
            # one number that says whether the gates are actually holding.
            "ratchet": "HELD" if moved <= 0 else "BROKEN",
            "completed_delta": entry["completed"] - prev.get("completed", 0),
        }
        entry["delta"] = delta
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return delta


def render(r):
    t = r["totals"]
    lines = [
        "", "RECERTIFICATION SWEEP  (%s%s)" % (
            r["mode"], ", APPLIED" if r["applied"] else ", report only"),
        "  completed lugs examined : %d" % t["completed"],
        "  CERTIFIED               : %d" % t[CERTIFIED],
        "  REFUTED                 : %d" % t[REFUTED],
        "  UNCHECKABLE             : %d   (never counted as certified)" % t[UNCHECKABLE],
    ]
    if r["refutation_rate"] is not None:
        lines.append("  refutation rate         : %.1f%% of the %d that could be decided"
                     % (r["refutation_rate"] * 100, r["decided"]))
    else:
        lines.append("  refutation rate         : undefined -- nothing could be decided")
    if r["undecidable_share"] is not None:
        lines.append("  share nobody can check  : %.1f%%" % (r["undecidable_share"] * 100))
    if r["refuted"]:
        lines.append("  refuted:")
        for e in r["refuted"][:15]:
            lines.append("    - %s: %s" % (e["id"], (e["reason"] or "")[:80]))
        if len(r["refuted"]) > 15:
            lines.append("    ... %d more" % (len(r["refuted"]) - 15))
    d = r.get("ledger_delta")
    if d:
        arrow = "up" if d["undecidable_share_delta"] > 0 else "down/flat"
        lines.append("  RATCHET                 : %s — share nobody can check moved %+.1f%% "
                     "since %s (%s)" % (d["ratchet"], d["undecidable_share_delta"] * 100,
                                        d["since"][:16], arrow))
        lines.append("                            %+d completed lug(s) since then"
                     % d["completed_delta"])
    if r["uncheckable_reasons"]:
        lines.append("  why uncheckable:")
        for reason, count in sorted(r["uncheckable_reasons"].items(),
                                    key=lambda kv: -kv[1])[:6]:
            lines.append("    %5d  %s" % (count, reason))
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="WAI-Harness/spoke/local")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--agent", action="store_true",
                    help="escalate prose verify steps to pattern-gate (costs tokens)")
    ap.add_argument("--apply", action="store_true",
                    help="actually reopen REFUTED lugs; off by default")
    ap.add_argument("--jobs", type=int, default=8,
                    help="concurrent agent certifiers in phase 2 (read-only, no shared state)")
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after N checkable lugs (for a fast sample)")
    ap.add_argument("--out", default=None, help="write the full report JSON here")
    ap.add_argument("--no-ledger", action="store_true",
                    help="do not append this run to the ratchet ledger")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    r = sweep(a.base, a.repo, use_agent=a.agent, apply=a.apply, limit=a.limit,
              jobs=a.jobs, progress=lambda m: print(m, file=sys.stderr, flush=True))
    if not a.no_ledger:
        r["ledger_delta"] = record_ledger(r, a.base)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(r, indent=2))
    print(json.dumps(r, indent=2) if a.json else render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
