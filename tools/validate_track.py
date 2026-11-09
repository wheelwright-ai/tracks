#!/usr/bin/env python3
"""Check a WAI Track (.jsonl) against spec/track-format.md.

Usage: python3 tools/validate_track.py [--check-name] FILE [FILE ...]
Exit 0 if every file is valid, 1 otherwise. Prints one line per problem,
each tagged with the spec rule it breaks, e.g. "[R12]". The rule IDs are
defined in the "Validation Rules" table of spec/track-format.md.
--check-name also enforces the file-naming rule (R01), which only applies to
exported Track files, not to samples or scratch files.
Standard library only.
"""
import json
import os
import re
import sys
from datetime import datetime

PHASES = {"orientation", "exploration", "planning", "execution",
          "review", "convergence", "crystallization"}
MODES = {"active-collection", "prep-and-request", "closing-request"}
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?Z$")
NAME = re.compile(r"^WAI_Track-\d{8}-\d{4}-[^-]+-.+\.jsonl$")
REQUIRED = {"turn": int, "ts": str, "phase": str, "focus": str,
            "action": str, "thinking": str}
STR_LISTS = ("activity", "decisions", "insights")
OBJ_LISTS = {"fossils": ("concept", "replaced_by", "reason"),
             "open": ("item", "status"),
             "files_in": ("name",), "files_out": ("name",)}
OPEN_STATUS = {"unknown", "deferred", "intentional", "blocked"}


def is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def sentences(text):
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def parse_ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def check_point(p, n, err):
    for k, t in REQUIRED.items():
        if k not in p:
            err(n, "R08", f"missing required field '{k}'")
        elif not isinstance(p[k], t) or isinstance(p[k], bool):
            err(n, "R08", f"'{k}' must be {t.__name__}")
    if isinstance(p.get("ts"), str) and not TS.match(p["ts"]):
        err(n, "R10", f"'ts' is not ISO-8601 UTC (ending Z): {p['ts']!r}")
    if isinstance(p.get("phase"), str) and p["phase"] not in PHASES:
        err(n, "R11", f"unknown phase {p['phase']!r}")
    if isinstance(p.get("thinking"), str):
        c = sentences(p["thinking"])
        if not 3 <= c <= 8:
            err(n, "R12", f"'thinking' has {c} sentences (must be 3-8)")
    for k in STR_LISTS:
        if k in p and not (isinstance(p[k], list) and all(isinstance(x, str) for x in p[k])):
            err(n, "R13", f"'{k}' must be an array of strings")
    if isinstance(p.get("activity"), list) and not p["activity"]:
        err(n, "R14", "'activity' is empty (use [\"conversational response only\"])")
    if "evolution" in p and not isinstance(p["evolution"], str):
        err(n, "R13", "'evolution' must be a string")
    for k, keys in OBJ_LISTS.items():
        if k not in p:
            continue
        if not isinstance(p[k], list):
            err(n, "R15", f"'{k}' must be an array of objects")
            continue
        for item in p[k]:
            if not isinstance(item, dict):
                err(n, "R15", f"'{k}' entries must be objects")
                continue
            for need in keys:
                if need not in item:
                    err(n, "R15", f"'{k}' entry missing '{need}'")
            if k == "open" and item.get("status") not in OPEN_STATUS:
                err(n, "R16", f"open status {item.get('status')!r} not in {sorted(OPEN_STATUS)}")
    if "context_health" in p:
        ch = p["context_health"]
        if not isinstance(ch, dict):
            err(n, "R17", "'context_health' must be an object")
        elif not is_num(ch.get("usage_estimate")) or not isinstance(ch.get("warning"), str):
            err(n, "R17", "'context_health' needs numeric 'usage_estimate' and string 'warning'")


def check_start(i, d, err):
    for k in ("ts", "session_id", "provider", "model"):
        if not isinstance(d.get(k), str):
            err(i, "R05", f"session_start missing string '{k}'")
    if isinstance(d.get("ts"), str) and not TS.match(d["ts"]):
        err(i, "R10", f"'ts' is not ISO-8601 UTC (ending Z): {d['ts']!r}")
    if "mode" in d and d["mode"] not in MODES:
        err(i, "R06", f"mode {d['mode']!r} not in {sorted(MODES)}")
    cont = d.get("continues")
    if "continues" in d and cont is not None and not isinstance(cont, str):
        err(i, "R07", "'continues' must be a filename string or null")
    if isinstance(cont, str):
        gap = d.get("continuation_gap_hours")
        if not is_num(gap):
            err(i, "R07", "'continues' requires numeric 'continuation_gap_hours'")
        elif gap <= 24:
            err(i, "R18", f"continuation_gap_hours={gap} but a linked continuation needs a gap over 24")
    elif "continuation_gap_hours" in d:
        err(i, "R07", "'continuation_gap_hours' without 'continues'")


def validate(path, check_name=False):
    problems = []

    def err(n, rule, msg):
        problems.append(f"{path}:{n}: [{rule}] {msg}")

    if check_name and not NAME.match(os.path.basename(path)):
        err(0, "R01", "file name must be WAI_Track-{YYYYMMDD}-{HHMM}-{Provider}-{Model}.jsonl")
    try:
        with open(path, encoding="utf-8") as f:
            lines = [(i, l) for i, l in enumerate(f, 1) if l.strip()]
    except OSError as e:
        return [f"{path}: cannot read ({e})"]
    rows = []
    for i, l in lines:
        try:
            d = json.loads(l)
        except ValueError as e:
            err(i, "R02", f"not valid JSON ({e})")
            continue
        if not isinstance(d, dict):
            err(i, "R02", "line must be a JSON object")
            continue
        rows.append((i, d))
    if not rows:
        return problems or [f"{path}: [R02] empty file"]
    if rows[0][1].get("event") != "session_start":
        err(rows[0][0], "R03", "first line must be a session_start event")
    starts = [r for r in rows if r[1].get("event") == "session_start"]
    if len(starts) > 1:
        err(starts[1][0], "R03", "more than one session_start")
    for i, d in starts:
        check_start(i, d, err)
    ends = [r for r in rows if r[1].get("event") == "session_end"]
    if ends and rows[-1][1].get("event") != "session_end":
        err(ends[0][0], "R04", "session_end must be the last line")
    if len(ends) > 1:
        err(ends[1][0], "R04", "more than one session_end")
    points = [(i, d) for i, d in rows if "event" not in d]
    for i, d in rows:
        if "event" in d and d["event"] not in ("session_start", "session_end"):
            err(i, "R03", f"unknown event {d['event']!r}")
    prev = 0
    last_ts = None
    for i, d in points:
        check_point(d, i, err)
        t = d.get("turn")
        if is_int(t):
            if t != prev + 1:
                err(i, "R09", f"turn {t} does not follow turn {prev} (must be sequential, one point per turn)")
            prev = t
        cur = parse_ts(d.get("ts")) if isinstance(d.get("ts"), str) else None
        if cur and last_ts and cur.tzinfo and last_ts.tzinfo and cur < last_ts:
            err(i, "R10", "'ts' goes backwards")
        last_ts = cur or last_ts
    for i, d in ends:
        if not isinstance(d.get("ts"), str) or not TS.match(d["ts"]):
            err(i, "R10", f"session_end 'ts' is not ISO-8601 UTC (ending Z): {d.get('ts')!r}")
        if not is_int(d.get("total_turns")):
            err(i, "R19", "session_end needs integer 'total_turns'")
        elif d["total_turns"] != len(points):
            err(i, "R19", f"total_turns={d['total_turns']} but file has {len(points)} points")
        if not isinstance(d.get("summary"), str):
            err(i, "R19", "session_end needs string 'summary'")
        if not is_int(d.get("unresolved_count")):
            err(i, "R19", "session_end needs integer 'unresolved_count'")
        else:
            unresolved = sum(len(p["open"]) for _, p in points if isinstance(p.get("open"), list))
            # open items may be resolved later, so this is an upper bound only
            if d["unresolved_count"] > unresolved:
                err(i, "R19", f"unresolved_count={d['unresolved_count']} exceeds {unresolved} open items recorded")
    return problems


def main(argv):
    check_name = "--check-name" in argv
    argv = [a for a in argv if a != "--check-name"]
    if not argv:
        print(__doc__.strip())
        return 2
    bad = 0
    for path in argv:
        problems = validate(path, check_name)
        if problems:
            bad += 1
            print("\n".join(problems))
        else:
            print(f"OK  {path}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
