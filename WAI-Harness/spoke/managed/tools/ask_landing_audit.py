#!/usr/bin/env python3
"""ask_landing_audit.py -- did the thing he asked for actually land?

W4 of epic-close-the-presumption-gap-v1, and the last piece of the operator's
original sentence: asks should be "reviewed by historian checks to see if it
truely landed".

W1 makes an ask traceable (nothing leaves a session as prose). W2 makes a
completion trustworthy (no worker certifies itself). W3 re-checks the backlog.
None of them answer the question he actually asks months later: I asked for X,
is it live?

THREE STATES, and the third is the one that matters:

  LANDED    the ask's own landing condition is observably true, with evidence.
  OPEN      the condition is checkable and is not true yet.
  STALLED   OPEN, and nothing has moved on it for STALL_DAYS. This is the only
            state that interrupts him at wakeup -- a report he has to go looking
            for is a report he will not read.

  UNCHECKABLE is reported as its own state and NEVER counted as LANDED. An ask
  with no checkable condition is the presumption gap in miniature: it will
  otherwise sit forever looking fine.

The audit is READ-ONLY. It never closes an ask, because "the condition holds"
and "the operator agrees it is done" are different claims and only he makes the
second one.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
import completion_certifier as cc  # noqa: E402

LANDED = "LANDED"
OPEN = "OPEN"
STALLED = "STALLED"
UNCHECKABLE = "UNCHECKABLE"

STALL_DAYS = 14


def _parse_ts(value):
    if not value or not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def iter_asks(base):
    """Every ask-* lug, in any status directory."""
    root = Path(base) / "lugs" / "bytype"
    if not root.is_dir():
        return
    for path in sorted(root.glob("*/*/ask-*.json")):
        try:
            yield path, json.loads(path.read_text())
        except (OSError, ValueError):
            continue


def audit_one(path, lug, repo, base, now=None, stall_days=STALL_DAYS):
    now = now or datetime.now(timezone.utc)
    status_dir = path.parent.name
    steps = lug.get("verify") or lug.get("acceptance_criteria") or []
    if isinstance(steps, str):
        steps = [steps]

    entry = {
        "id": lug.get("id") or path.stem,
        "asked_at": lug.get("created_at"),
        "verbatim": (lug.get("verbatim") or lug.get("verbatim_ask")
                     or lug.get("title") or "")[:400],
        "status_dir": status_dir,
        "evidence": [],
    }

    if not steps:
        entry["state"] = UNCHECKABLE
        entry["why"] = ("the ask carries no landing condition, so nothing can ever "
                        "prove it landed")
        return entry

    results, prose = cc.mechanical_checks(steps, repo, base,
                                          declared_targets=lug.get("file_targets"))
    entry["evidence"] = [{"step": r["step"][:120], "result": r["result"],
                          "observed": (r.get("observed") or "")[:200]} for r in results]

    if not results:
        entry["state"] = UNCHECKABLE
        entry["why"] = ("%d landing condition(s), none of them decidable by any "
                        "mechanical check" % len(prose))
        return entry

    if all(r["result"] == 1 for r in results) and not prose:
        entry["state"] = LANDED
        entry["why"] = "all %d landing condition(s) observed to hold" % len(results)
        return entry

    unmet = [r for r in results if r["result"] == 0]
    entry["why"] = "%d of %d condition(s) not yet true%s" % (
        len(unmet), len(results),
        "; %d more undecidable" % len(prose) if prose else "")

    # STALLED is OPEN plus time. Age from the most recent sign of life.
    touched = (_parse_ts(lug.get("updated_at")) or _parse_ts(lug.get("created_at")))
    entry["state"] = OPEN
    if touched:
        age = (now - touched).days
        entry["age_days"] = age
        if age >= stall_days:
            entry["state"] = STALLED
            entry["why"] += " — and nothing has moved for %d days" % age
    return entry


def audit(base, repo, stall_days=STALL_DAYS, now=None):
    entries = [audit_one(p, l, repo, base, now=now, stall_days=stall_days)
               for p, l in iter_asks(base)]
    counts = {s: 0 for s in (LANDED, OPEN, STALLED, UNCHECKABLE)}
    for e in entries:
        counts[e["state"]] += 1
    return {
        "measured_at": (now or datetime.now(timezone.utc)).isoformat(),
        "stall_days": stall_days,
        "counts": counts,
        "total": len(entries),
        "asks": entries,
        # The ONLY thing that earns an interruption at wakeup.
        "surface_at_wakeup": [e for e in entries if e["state"] == STALLED],
    }


def wakeup_line(report):
    """One line for the wakeup brief. Empty ONLY when nothing is outstanding.

    An ask he made that has not landed is surfaced -- OPEN as well as STALLED.

    The first version gated this on STALLED alone and argued that a line
    appearing every session stops being read. An independent certifier halted
    the wave over it: the acceptance criterion says an ask whose condition does
    not hold is "surfaced at wakeup", and quietly redefining "surfaced" to mean
    "present in the JSON payload" is a worker reinterpreting its own bar. The
    noise argument was real but it was mine to raise BEFORE agreeing the
    criterion, not to satisfy by narrowing it afterwards.

    Noise is handled by WEIGHT, not by silence: STALLED asks are named because
    they are the ones rotting, OPEN asks are counted because he still wants to
    know they exist. Silence means everything he asked for has landed.
    """
    stalled = report.get("surface_at_wakeup") or []
    counts = report.get("counts") or {}
    open_n = counts.get(OPEN, 0)
    if not stalled and not open_n:
        return ""
    parts = []
    if stalled:
        first = stalled[0]
        parts.append("%d STALLED — oldest \"%s\" (%s days)"
                     % (len(stalled), (first.get("verbatim") or first["id"])[:60],
                        first.get("age_days", "?")))
    if open_n:
        parts.append("%d open" % open_n)
    return "Asks not yet landed: " + " | ".join(parts)


def render(report):
    c = report["counts"]
    lines = ["", "ASK LANDING AUDIT  (%d ask(s))" % report["total"],
             "  LANDED      : %d" % c[LANDED],
             "  OPEN        : %d" % c[OPEN],
             "  STALLED     : %d   (>= %d days, surfaced at wakeup)"
             % (c[STALLED], report["stall_days"]),
             "  UNCHECKABLE : %d   (never counted as landed)" % c[UNCHECKABLE]]
    for e in report["asks"]:
        lines.append("  [%s] %s" % (e["state"][:5].ljust(5), e["id"]))
        if e.get("verbatim"):
            lines.append("        \"%s\"" % e["verbatim"][:100])
        lines.append("        %s" % e.get("why", ""))
        for ev in e.get("evidence", [])[:3]:
            mark = "ok  " if ev["result"] == 1 else "FAIL"
            lines.append("        [%s] %s" % (mark, ev["observed"][:90]))
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="WAI-Harness/spoke/local")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--stall-days", type=int, default=STALL_DAYS)
    ap.add_argument("--wakeup-line", action="store_true",
                    help="print only the wakeup line (empty when nothing stalled)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    r = audit(a.base, a.repo, stall_days=a.stall_days)
    if a.wakeup_line:
        line = wakeup_line(r)
        if line:
            print(line)
    elif a.json:
        print(json.dumps(r, indent=2))
    else:
        print(render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
