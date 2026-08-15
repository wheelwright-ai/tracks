#!/usr/bin/env python3
"""advisor_scheduler.py -- the thing that actually calls the recorder on a cadence.

W11 of the LOW TRUST tenet (spec-low-trust-tenet-v1), completing L2.

WHY THIS EXISTS AND WHY IT IS SEPARATE. oracle_liveness says who is overdue.
run_advisor executes one advisor and records that it ran. Neither of them ever
fires. Left there, the 3-to-5 improvement measured on 2026-08-02 decays back within
a week and the session that made it will read, correctly, as having achieved
nothing durable.

This is the same build-then-idle trap the tenet was written about, one level up: it
would have been a scheduler-shaped hole in a project about holes. The Deploy Warden
on this wheel is the standing example -- built, correct, and its cron entry never
installed.

WHAT `tick` WILL AND WILL NOT RUN. Cheap, deterministic, and conservative by
default, because an unattended job that can spend real money is a different kind of
object from one that cannot:

  * only advisors oracle_liveness reports as NEVER, SILENT or LATE;
  * only those whose contract declares `deterministic-tool-backed` -- agent-backed
    advisors cost tokens and are opt-in via --include-agent, never automatic;
  * capped by --max (default 3) and a whole-run --budget-seconds (default 600);
  * UNRUNNABLE and RETIRED are never attempted -- one cannot run, the other should
    not, and quietly retrying either every night is how a log becomes noise.

EVERY SKIP IS REPORTED. A scheduler that silently declines work looks identical to
one that had nothing to do, and the second reads as healthy. `tick` returns and
prints what it ran, what it skipped, and why, and the cron wrapper logs it.

CLI:
    advisor_scheduler.py --root DIR due [--json]
    advisor_scheduler.py --root DIR tick [--max N] [--budget-seconds N]
                                        [--include-agent] [--dry-run] [--json]

Exit codes: 0 nothing due or all ran clean, 1 something ran and failed,
2 something is due that this scheduler cannot run (needs a human).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import oracle_liveness as ol
import run_advisor as ra
import trust_epoch as te

DUE_STATES = (ol.NEVER, ol.SILENT, ol.LATE)
NEEDS_HUMAN_STATES = (ol.UNRUNNABLE,)
DEFAULT_MAX = 3
DEFAULT_BUDGET_SECONDS = 600
PER_RUN_TIMEOUT = 300


def _is_tool_backed(root, advisor_id):
    return "tool-backed" in str(
        ol.contract_row(root, advisor_id).get("kind", "")).lower()


def _is_funded(root, advisor_id):
    """Ozi's determination that this advisor is worth spending on.

    Read from the advisor's OWN contract, not the schedule index: the index is a
    cache written by whatever last ran, and a funding decision must come from the
    declaration. Same authority rule oracle_liveness.contract_row documents.
    """
    path = os.path.join(ol.advisors_dir(root), advisor_id, "contract.json")
    try:
        with open(path) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and data.get("fund") is True


def due(root, include_agent=False):
    """Who is due, who needs a human, and who was declined -- with reasons."""
    report = ol.check(root)
    runnable, needs_human, declined = [], [], []
    for row in report["results"]:
        advisor = row["advisor"]
        if row["state"] in NEEDS_HUMAN_STATES:
            needs_human.append({"advisor": advisor, "state": row["state"],
                                "reason": row["note"]})
            continue
        if row["state"] not in DUE_STATES:
            continue
        # ORDER MATTERS. Ask "is this mine to run?" BEFORE "can I run it?".
        # Reversed, every agent-dispatched advisor -- which legitimately carries no
        # command -- was reported as NEEDS HUMAN. The first live dry-run raised nine
        # of them, and nine false alarms beside one true one is how the true one
        # stops being read. Only a self-declared TOOL-BACKED advisor with nothing to
        # execute is a genuine call for a human.
        tool_backed = _is_tool_backed(root, advisor)
        # OPERATOR RULING (s140): "unattended jobs are allowed to spend tokens on
        # agent-backed advisors if Ozi determines they are something to prioritize."
        # `fund: true` IS that determination -- the flag ozi_autopilot and spoke_pulse
        # already read to decide what deserves resource. Honouring it here rather than
        # inventing a second signal keeps one answer to "is this worth paying for".
        # An UNFUNDED agent advisor is still declined: permission to spend is not the
        # same as a decision to spend, and collapsing the two turns a considered "yes,
        # when it matters" into a standing charge nobody revisits.
        funded = _is_funded(root, advisor)
        if not tool_backed and not include_agent and not funded:
            declined.append({"advisor": advisor, "state": row["state"],
                             "reason": "agent-backed and unfunded -- Ozi has not "
                                       "prioritised it; opt in with --include-agent"})
            continue
        command, source = ra.resolve_command(root, advisor)
        if command is None:
            bucket = needs_human if tool_backed else declined
            bucket.append({"advisor": advisor, "state": row["state"],
                           "reason": (f"declares itself tool-backed but {source}"
                                      if tool_backed else
                                      f"agent-dispatched, {source} -- not a cron job")})
            continue
        runnable.append({"advisor": advisor, "state": row["state"],
                         "command": command, "severity": ol.SEVERITY[row["state"]]})
    runnable.sort(key=lambda r: r["severity"])
    return {"checked_at": te._iso(te._now()), "runnable": runnable,
            "needs_human": needs_human, "declined": declined,
            "counts": report["counts"]}


def tick(root, max_runs=DEFAULT_MAX, budget_seconds=DEFAULT_BUDGET_SECONDS,
         include_agent=False, dry_run=False):
    plan = due(root, include_agent)
    started = time.monotonic()
    ran, skipped = [], []

    for item in plan["runnable"]:
        if len(ran) >= max_runs:
            skipped.append({**item, "why": f"--max {max_runs} reached"})
            continue
        remaining = budget_seconds - (time.monotonic() - started)
        if remaining <= 5:
            skipped.append({**item, "why": "budget exhausted"})
            continue
        if dry_run:
            skipped.append({**item, "why": "dry-run"})
            continue
        result = ra.run(root, item["advisor"],
                        timeout=int(min(PER_RUN_TIMEOUT, remaining)))
        ran.append({"advisor": item["advisor"], "state": result["state"],
                    "ok": result.get("ok"), "reason": result.get("reason")})

    return {
        "ticked_at": te._iso(te._now()),
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "ran": ran,
        "skipped": skipped,
        "needs_human": plan["needs_human"],
        "declined": plan["declined"],
        "dry_run": bool(dry_run),
    }


def render_due(plan):
    lines = [f"due now: {len(plan['runnable'])} runnable, "
             f"{len(plan['needs_human'])} need a human, "
             f"{len(plan['declined'])} declined"]
    for r in plan["runnable"]:
        lines.append(f"  [{r['state']:<7}] {r['advisor']}")
    for r in plan["needs_human"]:
        lines.append(f"  [HUMAN  ] {r['advisor']}: {r['reason']}")
    for r in plan["declined"]:
        lines.append(f"  [SKIP   ] {r['advisor']}: {r['reason']}")
    return "\n".join(lines)


def render_tick(result):
    lines = [f"tick {result['ticked_at']} ({result['elapsed_seconds']}s)"
             + ("  DRY-RUN" if result["dry_run"] else "")]
    for r in result["ran"]:
        lines.append(f"  [{r['state']:<11}] {r['advisor']}")
    for s in result["skipped"]:
        lines.append(f"  [skipped    ] {s['advisor']}: {s['why']}")
    for h in result["needs_human"]:
        lines.append(f"  [NEEDS HUMAN] {h['advisor']}: {h['reason']}")
    for d in result["declined"]:
        lines.append(f"  [declined   ] {d['advisor']}: {d['reason']}")
    if not any((result["ran"], result["skipped"], result["needs_human"],
                result["declined"])):
        lines.append("  nothing due")
    return "\n".join(lines)


def exit_code(result):
    if result.get("needs_human"):
        return 2
    if any(r.get("state") == "RAN_FAILED" for r in result.get("ran", [])):
        return 1
    if any(r.get("state") in ("UNRUNNABLE", "TIMEOUT")
           for r in result.get("ran", [])):
        return 2
    return 0


def _main(argv=None):
    top = argparse.ArgumentParser(add_help=False)
    top.add_argument("--root", default=".")
    top.add_argument("--json", action="store_true")
    top.add_argument("--include-agent", action="store_true")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--include-agent", action="store_true",
                        default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], parents=[top])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("due", parents=[common])
    p_tick = sub.add_parser("tick", parents=[common])
    p_tick.add_argument("--max", type=int, default=DEFAULT_MAX, dest="max_runs")
    p_tick.add_argument("--budget-seconds", type=int, default=DEFAULT_BUDGET_SECONDS)
    p_tick.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if args.cmd == "due":
        plan = due(args.root, args.include_agent)
        print(json.dumps(plan, indent=2) if args.json else render_due(plan))
        return 2 if plan["needs_human"] else (1 if plan["runnable"] else 0)

    result = tick(args.root, args.max_runs, args.budget_seconds,
                  args.include_agent, args.dry_run)
    print(json.dumps(result, indent=2) if args.json else render_tick(result))
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(_main())
