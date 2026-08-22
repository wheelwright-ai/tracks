#!/usr/bin/env python3
"""What automation last did for this spoke, and when it runs next.

WHY
---
Operator, 2026-08-14: "this UI leads to too many low level asks whereas Ozi should
know to maximize time with the user over deferrable build activity ... share last
automation run on the spoke and next time it will run - this forecasts what should
happen next and when."

The launch menu already claimed "Autopilot (runs nightly -- no action needed)" over a
backlog count. That claim was never checked against anything. Two ways it was false
for basher on the day this was written, both silent:

  1. The crontab redirects to $HOME/.claude/logs/ozi-nightly/cron.log. The directory
     did not exist. A shell evaluates the redirect BEFORE exec, so the whole cron
     line failed and the nightly had never once run -- while the menu told the
     operator it was handled.
  2. The gate defers when a session was live in the last 45 minutes. This operator
     works late. A deferral is a legitimate outcome, but "deferred three runs in a
     row" and "ran and landed nine lugs" are not the same state, and the menu showed
     the same sentence for both.

So the rule here is: never assert that automation is handling something without
reading the ledger. ARMED/DEAD/STALE is derived from the machine, and every field can
come back unknown -- an honest blank beats a confident wrong forecast.

Emits shell-assignable KEY=VALUE lines (safe to `eval`), or --json.

  _APF_STATE        armed | dead | unscheduled | unknown
  _APF_STATE_WHY    one-line reason, '' when armed and healthy
  _APF_LAST_TS      ISO timestamp of the last recorded run, '' if never
  _APF_LAST_AGE     human age of that run ('3d ago'), '' if never
  _APF_LAST_OUTCOME landed | moved-zero | deferred | error | '' (never run)
  _APF_LAST_DETAIL  short reason/summary for the outcome
  _APF_NEXT_TS      ISO timestamp of the next scheduled run, '' if unscheduled
  _APF_NEXT_HUMAN   'tonight 02:00' / 'Mon 02:00', '' if unscheduled
  _APF_NEXT_IN      'in 1h 29m', '' if unscheduled
  _APF_SCHEDULE     the cron expression driving it, '' if none found
"""
import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

# The cron line that dispatches a spoke's nightly autopilot. Matched loosely: the
# operator's crontab has ~20 entries and this one is identified by the script name,
# not by position, so re-ordering the crontab cannot silently detach the forecast.
GATE_RE = re.compile(r"ozi_nightly_gate\.sh")


def crontab_lines():
    try:
        out = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        return out.stdout.splitlines() if out.returncode == 0 else []
    except Exception:
        return []


def parse_schedule(lines):
    """Return (cron_expr, command) for the nightly gate, or (None, None)."""
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#") or not GATE_RE.search(s):
            continue
        parts = s.split(None, 5)
        if len(parts) < 6:
            continue
        return " ".join(parts[:5]), parts[5]
    return None, None


def _field(spec, lo, hi):
    """Expand one cron field to the set of values it matches."""
    out = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, _, st = part.partition("/")
            step = int(st) if st.isdigit() else 1
        if part in ("*", ""):
            rng = range(lo, hi + 1)
        elif "-" in part:
            a, _, b = part.partition("-")
            rng = range(int(a), int(b) + 1)
        elif part.isdigit():
            rng = [int(part)]
        else:
            continue
        out.update(v for v in rng if (v - lo) % step == 0 or step == 1)
    return out


def next_fire(expr, now):
    """Next datetime matching a 5-field cron expression. None if unparseable.

    Minute-by-minute over a bounded window rather than a closed-form solver: the
    horizon that matters here is 'the next run', a week of minutes is ~10k
    iterations, and a wrong-but-fast forecast is worse than no forecast.
    """
    try:
        mins, hours, doms, months, dows = expr.split()
        M, H = _field(mins, 0, 59), _field(hours, 0, 23)
        DOM, MON = _field(doms, 1, 31), _field(months, 1, 12)
        DOW = {d % 7 for d in _field(dows, 0, 7)}
    except Exception:
        return None
    dom_restricted = doms.strip() != "*"
    dow_restricted = dows.strip() != "*"
    t = (now + dt.timedelta(minutes=1)).replace(second=0, microsecond=0)
    for _ in range(60 * 24 * 8):
        if t.minute in M and t.hour in H and t.month in MON:
            # cron's OR rule: with BOTH day fields restricted, either may match.
            d_ok = t.day in DOM
            w_ok = (t.weekday() + 1) % 7 in DOW
            if (d_ok and w_ok) if not (dom_restricted and dow_restricted) else (d_ok or w_ok):
                return t
        t += dt.timedelta(minutes=1)
    return None


def human_delta(delta):
    secs = int(delta.total_seconds())
    if secs < 0:
        secs = -secs
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def human_when(when, now):
    if when.date() == now.date():
        return f"today {when:%H:%M}"
    if when.date() == (now + dt.timedelta(days=1)).date():
        # 'tonight' only when it is still the small hours and the run is before dawn.
        return f"tonight {when:%H:%M}" if now.hour < 6 or when.hour < 6 else f"tomorrow {when:%H:%M}"
    return f"{when:%a} {when:%H:%M}"


def missing_logdir(command):
    """The directory a cron line redirects into, when it does not exist.

    THE DEAD-ON-ARRIVAL CHECK, and the reason this tool exists at all. A shell opens
    a redirect target BEFORE exec'ing the command, so `>> some/dir/x.log` with no
    `some/dir` fails the whole cron line -- the job never starts, cron mails an error
    nobody reads, and every surface that says "runs nightly" keeps saying it. That is
    precisely how basher's Ozi nightly had never once run. The gate script's own
    `mkdir -p "$LOGDIR"` cannot help: it is inside the process that never launches.

    Returns the missing directory, or '' when the line is fine. A path containing a
    command substitution ($(date …)) in its DIRECTORY part is not checkable, so it is
    reported as fine rather than guessed at -- a false "dead" would be worse than the
    silence being fixed here.
    """
    m = re.search(r">>?\s*(\S+)", command or "")
    if not m:
        return ""
    target = os.path.expandvars(os.path.expanduser(m.group(1)))
    parent = os.path.dirname(target)
    if not parent or "$(" in parent or not parent.startswith("/"):
        return ""
    return "" if os.path.isdir(parent) else parent


def read_ledger(path):
    """Last row of the nightly-gate ledger, or None."""
    try:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    except Exception:
        return None
    return rows[-1] if rows else None


def resolve_ledger(hub_root, explicit):
    if explicit:
        return Path(explicit)
    if hub_root:
        return Path(hub_root) / "ap-runs" / "nightly-gate-ledger.jsonl"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub-root", default="", help="…/WAI-Harness/hub/local")
    ap.add_argument("--ledger", default="", help="explicit ledger path (overrides --hub-root)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    now = dt.datetime.now()
    out = {k: "" for k in (
        "_APF_STATE", "_APF_STATE_WHY", "_APF_LAST_TS", "_APF_LAST_AGE",
        "_APF_LAST_OUTCOME", "_APF_LAST_DETAIL", "_APF_NEXT_TS",
        "_APF_NEXT_HUMAN", "_APF_NEXT_IN", "_APF_SCHEDULE")}
    out["_APF_STATE"] = "unknown"

    expr, command = parse_schedule(crontab_lines())
    if not expr:
        out["_APF_STATE"] = "unscheduled"
        out["_APF_STATE_WHY"] = "no ozi_nightly_gate.sh entry in crontab"
    else:
        out["_APF_SCHEDULE"] = expr
        nxt = next_fire(expr, now)
        if nxt:
            out["_APF_NEXT_TS"] = nxt.isoformat(timespec="minutes")
            out["_APF_NEXT_HUMAN"] = human_when(nxt, now)
            out["_APF_NEXT_IN"] = "in " + human_delta(nxt - now)
        out["_APF_STATE"] = "armed"

        missing = missing_logdir(command)
        if missing:
            out["_APF_STATE"] = "dead"
            out["_APF_STATE_WHY"] = f"cron log dir missing ({missing}) — the redirect fails before the job runs"

    row = read_ledger(resolve_ledger(args.hub_root, args.ledger))
    if row:
        ts = str(row.get("ts", ""))
        out["_APF_LAST_TS"] = ts
        out["_APF_LAST_OUTCOME"] = str(row.get("outcome", "")) or "unknown"
        out["_APF_LAST_DETAIL"] = str(row.get("reason", "") or row.get("summary", ""))[:80]
        try:
            when = dt.datetime.fromisoformat(ts)
            if when.tzinfo:
                when = when.astimezone().replace(tzinfo=None)
            out["_APF_LAST_AGE"] = human_delta(now - when) + " ago"
        except Exception:
            pass
    elif out["_APF_STATE"] == "armed":
        out["_APF_STATE_WHY"] = "scheduled but no run recorded yet"

    if args.json:
        print(json.dumps(out, indent=2))
    else:
        for k, v in out.items():
            print(f"{k}={shlex.quote(v)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
