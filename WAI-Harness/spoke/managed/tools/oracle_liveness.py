#!/usr/bin/env python3
"""oracle_liveness.py -- who watches the watchers, and says so out loud.

W5 of the LOW TRUST tenet (spec-low-trust-tenet-v1), mechanism M5.

THE FAILURE BEING REMOVED, in one measurement. On 2026-08-02 this wheel held five
assurance tools, an epic marked COMPLETE that had built them, and an advisor named
`proofer` whose entire job was to run the assurance oracle. proofer had never run.
Not late -- never, not once, and no instrument anywhere said so. The whole
anti-hallucination apparatus was resting on the assumption that things which were
supposed to run were running, which is the single largest act of trust on the wheel.

THE INVERSION THIS FILE ENCODES. A red result is GOOD NEWS: it means the oracle
ran, reached a verdict, and told you. Silence is the dangerous state, and it is the
state every dashboard renders as fine. So:

    an oracle that has stopped reporting pages LOUDER than one reporting failure.

FOUR STATES, and the ranking is deliberate -- worst first, because that is the order
a reader needs them in, and because the two worst states are the two that look like
nothing at all:

    NEVER   registered, never produced a single output. Its findings are UNKNOWN and
            have always been UNKNOWN. This is not a new oracle being patient; it is
            an oracle that has never once done its job. Highest severity.
    SILENT  ran before, then stopped -- overdue by more than GRACE x its cadence.
            Something broke and nobody was told. Second highest.
    LATE    overdue, but inside the grace window. Ordinary slippage.
    LIVE    reported within its cadence.

WHY `NEVER` OUTRANKS `SILENT`. A silent oracle has at least demonstrated it can run;
its history is real and its last verdict meant something. A never-run oracle has
produced exactly zero evidence in its entire existence, and every green the wheel has
shown next to its name has been decoration. UNKNOWN is not GREEN, and the longest
UNKNOWN is the worst one.

CADENCE IS READ, NOT GUESSED. An advisor with no declared cadence cannot be judged
late, so it is reported as UNSCHEDULED rather than folded into LIVE. A tool that
quietly treats "no cadence" as "fine" would have called proofer healthy.

CLI:
    oracle_liveness.py --root DIR check [--json] [--grace N]
    oracle_liveness.py --root DIR worst [--json]     one line for a brief/banner

Exit codes: 0 all LIVE, 1 LATE present, 2 NEVER or SILENT present.
Exit-2 is the loud one, and it is reserved for the two silent states rather than for
failing checks -- which is the whole inversion, expressed where callers can see it.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import trust_epoch as te


NEVER = "NEVER"
SILENT = "SILENT"
LATE = "LATE"
LIVE = "LIVE"
UNSCHEDULED = "UNSCHEDULED"
EVENT_DRIVEN = "EVENT_DRIVEN"
UNRUNNABLE = "UNRUNNABLE"
RETIRED = "RETIRED"

# Worst first. Callers sort on this and the brief reads the head of the list.
# EVENT_DRIVEN sits beside UNSCHEDULED rather than beside LIVE: it is an honest
# "a clock cannot judge this", not a pass. See _CADENCE_IS_EVENT below.
SEVERITY = {UNRUNNABLE: 0, NEVER: 1, SILENT: 2, LATE: 3, UNSCHEDULED: 4,
            EVENT_DRIVEN: 5, LIVE: 6, RETIRED: 7}

CADENCE_DAYS = {
    "continuous": 1, "hourly": 1, "daily": 1, "nightly": 1,
    "every-2-days": 2, "twice-weekly": 4, "weekly": 7,
    "biweekly": 14, "fortnightly": 14, "monthly": 30, "quarterly": 90,
}

DEFAULT_GRACE = 3.0  # multiples of the cadence before LATE becomes SILENT


def _now():
    return datetime.now(timezone.utc)


def advisors_dir(root):
    return os.path.join(root, "WAI-Harness", "spoke", "advisors")


def schedule_index(root):
    path = os.path.join(advisors_dir(root), "schedule-index.json")
    try:
        with open(path) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    # BOTH SHAPES ARE REAL ON DISK. The schedulers write this file as a BARE LIST of
    # advisor rows; only the dict form {"advisors": [...]} was accepted here, so a
    # list-shaped index silently resolved to {} and EVERY reader saw an empty bench:
    # no cadence, no last_run_at, no declared tool. MEASURED 2026-08-06 (basher s123)
    # — the index held 3 advisors and run_advisor still reported historian as
    # "no dispatch_command, command, or tool declared" with the tool sitting in the
    # row it never read. Returning {} for a file that parsed fine is the silent
    # failure this module exists to prevent.
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get("advisors")
    else:
        rows = None
    out = {}
    for row in rows or []:
        if isinstance(row, dict) and row.get("advisor_id"):
            out[row["advisor_id"]] = row
    return out


# A cadence that names a TRIGGER rather than an interval. Judging these by a clock
# is simply wrong -- an on-event advisor is late only if its event fired and it did
# not run, which is a different check nobody has built yet. Calling them LIVE would
# be the silent upgrade this file exists to prevent, so they get their own class and
# the missing check is named in the note rather than papered over.
_CADENCE_IS_EVENT = ("on-event", "on_event", "on-demand", "on_demand", "closeout",
                     "session-start", "session_start", "per ap round", "per-ap-round",
                     "push", "pre_distribution", "pre-distribution")


def cadence_days(row):
    """Declared cadence in days; None when undeclared; 0 when event-driven."""
    raw = (row.get("run_cadence") or row.get("cadence") or "").strip().lower()
    if not raw:
        return None
    if any(tok in raw for tok in _CADENCE_IS_EVENT):
        return 0
    if raw in CADENCE_DAYS:
        return CADENCE_DAYS[raw]
    for name, days in CADENCE_DAYS.items():
        if name in raw:
            return days
    digits = "".join(c for c in raw if c.isdigit())
    return int(digits) if digits else None


def contract_row(root, advisor_id):
    """The advisor's own contract. AUTHORITATIVE over schedule-index.json.

    The index is a cache written by whatever last ran; the contract is the
    declaration. Measured 2026-08-02: 16 of 34 advisors read UNSCHEDULED from the
    index while their contracts plainly declared a cadence. Reporting a spoke as
    having no cadence when the cadence is written down two directories away is the
    instrument being wrong about the thing it exists to measure.
    """
    path = os.path.join(advisors_dir(root), advisor_id, "contract.json")
    try:
        with open(path) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    row = {"_status": data.get("status"), "_superseded_by": data.get("superseded_by")}
    run_block = data.get("run")
    if isinstance(run_block, dict) and run_block.get("tool"):
        row["tool"] = run_block["tool"]
    for key in ("run_cadence", "cadence"):
        if data.get(key):
            row["run_cadence"] = data[key]
            break
    if not row.get("run_cadence"):
        sched = data.get("schedule")
        if isinstance(sched, dict) and sched.get("cadence"):
            row["run_cadence"] = sched["cadence"]
    if data.get("kind"):
        row["kind"] = data["kind"]
    return row


# Files that describe an advisor rather than record it running. An mtime on any of
# these proves someone edited a config, never that the advisor executed.
_NON_EVIDENCE = {"contract.json", "readme.md", "mission.md", "config.json",
                 "scan_state.json", "state.json", "manifest.json"}

_STATE_FILES = ("scan_state.json", "state.json")


def explicit_never(directory):
    """An advisor's own state file declaring it has never run. AUTHORITATIVE.

    Caught 2026-08-02 on the first live run: `proofer` reported SILENT (35d) when
    its scan_state.json plainly said runs: 0 and last_run_at: null -- it had never
    run in its life. The mtime of that very state file was what made it look like
    it once had. An mtime is an INFERENCE about running; `runs: 0` is a STATEMENT
    about running, and when the two disagree the statement wins.

    The general rule, and the reason this function exists rather than a wider
    exclusion list: when two sources of evidence disagree about how healthy
    something is, take the less trusting one. Every silent upgrade in this
    codebase's history has come from doing the opposite.
    """
    for name in _STATE_FILES:
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        runs = (data.get("stats") or {}).get("runs") if isinstance(
            data.get("stats"), dict) else None
        if runs == 0 and not data.get("last_run_at"):
            return True
    return False


def _newest_output(directory):
    """Most recent mtime among this advisor's non-empty output files, or None.

    Evidence of RUNNING, not of being configured: contract.json and the like are
    excluded, because a config file proves someone set the advisor up and proves
    nothing whatever about it ever having executed.
    """
    newest = None
    for path in glob.glob(os.path.join(directory, "**", "*"), recursive=True):
        if not os.path.isfile(path):
            continue
        if os.path.basename(path).lower() in _NON_EVIDENCE:
            continue
        try:
            if os.path.getsize(path) == 0:
                continue
            mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    return newest


def last_run(root, advisor_id, row):
    """Latest of the declared last_run_at and any real output on disk.

    Both are consulted because each lies in a different direction: the index goes
    stale when a run does not update it, and file mtimes move for reasons that are
    not runs. Taking the later of the two is the generous reading -- and being
    generous here is safe, because the finding we care about is the advisor that
    has NEITHER.
    """
    directory = os.path.join(advisors_dir(root), advisor_id)
    if explicit_never(directory):
        return None
    declared = te._parse_ts(row.get("last_run_at") or row.get("last_run"))
    observed = _newest_output(directory)
    if declared and observed:
        return max(declared, observed)
    return declared or observed


_PY_PATH = re.compile(r"([\w./-]+\.py)")


def broken_command(root, row):
    """A registered command pointing at a file that does not exist.

    Found 2026-08-02: historian_archaeology had never run because its
    dispatch_command named `tools/historian_archaeology.py`, a v3 path, while the
    file lives under WAI-Harness/spoke/managed/tools/. It was registered, scheduled,
    monthly, and structurally incapable of executing -- and every instrument
    reported it as merely overdue.

    This outranks NEVER. A never-run oracle might run tomorrow; this one cannot run
    at all, and the distinction is the difference between waiting and being wrong.
    """
    for key in ("dispatch_command", "command", "tool"):
        value = row.get(key)
        if not isinstance(value, str):
            continue
        for candidate in _PY_PATH.findall(value):
            if not os.path.exists(os.path.join(root, candidate)):
                return f"{key} names {candidate}, which does not exist"
    return None


def classify(root, advisor_id, row, grace=DEFAULT_GRACE, now=None):
    now = now or _now()
    contract = contract_row(root, advisor_id)

    # A RETIRED advisor is not an alarm. qa_assurance was superseded on 2026-06-29
    # and was still being counted as NEVER five weeks later -- a permanent false
    # positive, and false positives are how a reader learns to discount the real
    # ones. Excluded from every count rather than merely sorted last.
    if str(contract.get("_status", "")).lower() in ("superseded", "retired", "archived"):
        return {
            "advisor": advisor_id, "state": RETIRED, "cadence_days": None,
            "last_run": None, "overdue_days": None,
            "note": f"retired ({contract.get('_status')})"
                    + (f", superseded by {contract['_superseded_by']}"
                       if contract.get("_superseded_by") else "")
                    + " -- excluded from the counts, not an alarm",
        }

    # An advisor that DECLARES ITSELF tool-backed and names no tool cannot run --
    # the UNRUNNABLE condition reached from the other direction: not a broken path,
    # no path at all. Narrowed to `deterministic-tool-backed` on purpose: most
    # advisors are agent-dispatched and legitimately carry no command, and an
    # earlier draft of this rule flagged all of them, which would have been a
    # 30-advisor false alarm shipped in the name of rigour.
    _tool_backed = "tool-backed" in str(contract.get("kind", "")).lower()
    if _tool_backed and not any(row.get(k) or contract.get(k)
                                for k in ("dispatch_command", "command", "tool")):
        return {
            "advisor": advisor_id, "state": UNRUNNABLE, "cadence_days": None,
            "last_run": None, "overdue_days": None,
            "note": "declares itself deterministic-tool-backed but names no tool -- "
                    "there is nothing to run; it is not late, it is undefined",
        }

    broken = broken_command(root, row) or broken_command(root, contract)
    if broken:
        return {
            "advisor": advisor_id, "state": UNRUNNABLE, "cadence_days": None,
            "last_run": None, "overdue_days": None,
            "note": f"cannot execute -- {broken}; it is not late, it is impossible",
        }
    ran = last_run(root, advisor_id, row) or last_run(root, advisor_id, contract)
    days = cadence_days(row)
    if days is None:
        # Index says nothing -- ask the advisor's own contract before concluding
        # it is unscheduled.
        days = cadence_days(contract)

    if ran is None:
        return {
            "advisor": advisor_id, "state": NEVER, "cadence_days": days,
            "last_run": None, "overdue_days": None,
            "note": "registered and has never produced output -- its findings have "
                    "always been UNKNOWN, and UNKNOWN is not green",
        }

    age = (now - ran).total_seconds() / 86400.0
    if days == 0:
        return {
            "advisor": advisor_id, "state": EVENT_DRIVEN, "cadence_days": 0,
            "last_run": te._iso(ran), "overdue_days": None,
            "note": f"event-driven -- last output {age:.0f}d ago. A clock cannot "
                    "judge this; it is late only if its trigger fired and it did "
                    "not run, and no check for that exists yet",
        }
    if days is None:
        return {
            "advisor": advisor_id, "state": UNSCHEDULED, "cadence_days": None,
            "last_run": te._iso(ran), "overdue_days": None,
            "note": f"no declared cadence -- last output {age:.0f}d ago, cannot be "
                    "judged late, and is deliberately not counted as healthy",
        }

    overdue = age - days
    if overdue <= 0:
        state, note = LIVE, f"reported {age:.0f}d ago, inside its {days}d cadence"
    elif age <= days * grace:
        state, note = LATE, f"overdue {overdue:.0f}d on a {days}d cadence"
    else:
        state, note = SILENT, (f"stopped reporting -- last output {age:.0f}d ago on a "
                               f"{days}d cadence; something broke and nobody was told")
    return {
        "advisor": advisor_id, "state": state, "cadence_days": days,
        "last_run": te._iso(ran), "overdue_days": round(overdue, 1),
        "note": note,
    }


def check(root, grace=DEFAULT_GRACE, now=None):
    index = schedule_index(root)
    directory = advisors_dir(root)
    seen = set(index)
    if os.path.isdir(directory):
        for entry in os.listdir(directory):
            if os.path.isdir(os.path.join(directory, entry)):
                seen.add(entry)

    results = [classify(root, a, index.get(a, {}), grace, now) for a in sorted(seen)]
    results.sort(key=lambda r: (SEVERITY[r["state"]], r["advisor"]))
    counts = {s: sum(1 for r in results if r["state"] == s)
              for s in (UNRUNNABLE, NEVER, SILENT, LATE, UNSCHEDULED,
                        EVENT_DRIVEN, LIVE, RETIRED)}
    return {
        "checked_at": te._iso(now or _now()),
        "total": len(results),
        "active_total": len(results) - counts[RETIRED],
        "counts": counts,
        "silent_total": counts[NEVER] + counts[SILENT] + counts[UNRUNNABLE],
        "results": results,
    }


def worst_line(report):
    """One line for a wakeup banner. Names the worst state, never an average."""
    c = report["counts"]
    if c[UNRUNNABLE]:
        head = report["results"][0]
        return (f"Oracles: ⚠ {c[UNRUNNABLE]} UNRUNNABLE (worst: {head['advisor']}) "
                "-- registered and scheduled, with nothing it can actually execute")
    if c[NEVER] or c[SILENT]:
        head = report["results"][0]
        return (f"Oracles: {c[NEVER]} NEVER ran, {c[SILENT]} went SILENT "
                f"(worst: {head['advisor']}) -- silence outranks a red result")
    if c[LATE]:
        return f"Oracles: {c[LATE]} LATE, {c[LIVE]} live"
    if c[UNSCHEDULED]:
        return f"Oracles: {c[LIVE]} live, {c[UNSCHEDULED]} unscheduled (not counted healthy)"
    if c[EVENT_DRIVEN]:
        return (f"Oracles: {c[LIVE]} live on a clock, {c[EVENT_DRIVEN]} event-driven "
                "(no trigger-fired check exists yet)")
    return f"Oracles: all {c[LIVE]} live"


def exit_code(report):
    if report["silent_total"]:
        return 2
    return 1 if report["counts"][LATE] else 0


def render(report):
    lines = [worst_line(report), ""]
    for r in report["results"]:
        if r["state"] == LIVE:
            continue
        lines.append(f"  [{r['state']:<11}] {r['advisor']:<28} {r['note']}")
    live = report["counts"][LIVE]
    if live:
        lines.append(f"  ({live} live, not listed)")
    return "\n".join(lines)


def _main(argv=None):
    top = argparse.ArgumentParser(add_help=False)
    top.add_argument("--root", default=".")
    top.add_argument("--json", action="store_true")
    top.add_argument("--grace", type=float, default=DEFAULT_GRACE)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--grace", type=float, default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], parents=[top])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", parents=[common])
    sub.add_parser("worst", parents=[common])
    args = parser.parse_args(argv)

    report = check(args.root, args.grace)
    if args.cmd == "worst":
        print(json.dumps({"line": worst_line(report),
                          "counts": report["counts"]}, indent=2)
              if args.json else worst_line(report))
        return exit_code(report)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report))
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(_main())
