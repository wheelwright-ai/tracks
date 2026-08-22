#!/usr/bin/env python3
"""observation_freshness.py -- is this observation about the run you think it is?

MEASURED 2026-08-18, three times in ONE session, by the same agent, in the same shape:

  1. A push reported as landed. `PUSH_EXIT=0` was a trailing `tail`'s exit code, not git's;
     the pre-push gate had blocked it.
  2. A push reported as landed a second time, off a monitor event that described the
     PREVIOUS push.
  3. A cadence run reported as "the fix did not work". The log line read was from the run
     BEFORE the fix was written -- no new run had happened at all, and the conclusion was
     the opposite of the truth.

Each time the remedy written down was "check the exit code" or "check the timestamp", and
each time a later moment of momentum skipped it. A rule that competes with attention loses
to attention. The same lesson is recorded one directory over in install.py:57, where a
stated rule to bump a constant went unfollowed twice and was caught instead by a checker
that compares CONTENT.

So this is the mechanical form: an observation is only evidence if it is NEWER than the
event it is supposed to describe. Ask, do not remember.

    freshness.py after --file <log> --since <iso> [--pattern RE]
        exit 0  the newest matching line is at or after --since  (fresh: report it)
        exit 1  the newest matching line PREDATES --since        (stale: do NOT report it)
        exit 2  no matching line at all                          (absent: do NOT report it)

STALE AND ABSENT ARE DISTINCT EXIT CODES on purpose. "The run has not happened yet" and
"the run happened and said nothing" call for opposite responses, and collapsing them is
how a not-yet-started cadence got reported as a failed one.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone

FRESH, STALE, ABSENT = 0, 1, 2

# Timestamps as they actually appear in these logs: ISO with or without a UTC offset.
_TS = re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)")


def parse_time(text):
    """First ISO timestamp in `text`, as an aware datetime, or None.

    A naive stamp is assumed LOCAL, not UTC. Assuming UTC would silently shift every
    local-clock log by the offset -- and cron writes local time, which is exactly the
    surface this exists to read.
    """
    m = _TS.search(text or "")
    if not m:
        return None
    raw = m.group(1).replace(" ", "T")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt.astimezone() if dt.tzinfo is None else dt


def newest(path, pattern=""):
    """The newest timestamped line matching `pattern`, as (datetime, line)."""
    rx = re.compile(pattern) if pattern else None
    best = None
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if rx and not rx.search(line):
                    continue
                ts = parse_time(line)
                if ts is None:
                    continue
                if best is None or ts > best[0]:
                    best = (ts, line.rstrip())
    except OSError:
        return None
    return best


def verdict(path, since, pattern=""):
    hit = newest(path, pattern)
    if hit is None:
        return ABSENT, None, "no timestamped line matches; the run may not have started"
    ts, line = hit
    if ts >= since:
        return FRESH, line, f"newest matching line is {ts.isoformat()} (at or after --since)"
    return STALE, line, (f"newest matching line is {ts.isoformat()}, which PREDATES "
                         f"{since.isoformat()} -- this describes an EARLIER run")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("after")
    p.add_argument("--file", required=True)
    p.add_argument("--since", required=True, help="ISO timestamp the observation must beat")
    p.add_argument("--pattern", default="", help="only consider lines matching this regex")
    args = ap.parse_args(argv)

    since = parse_time(args.since)
    if since is None:
        print(f"--since {args.since!r} is not an ISO timestamp", file=sys.stderr)
        return ABSENT
    code, line, why = verdict(args.file, since, args.pattern)
    label = {FRESH: "FRESH", STALE: "STALE", ABSENT: "ABSENT"}[code]
    print(f"{label}: {why}")
    if line:
        print(f"  {line[:160]}")
    return code


if __name__ == "__main__":
    sys.exit(main())
