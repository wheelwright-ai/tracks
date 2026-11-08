#!/usr/bin/env python3
"""Validate a WAI Track .jsonl file against spec/track-format.md.

Every rule has an ID (the RULES dict). Errors are printed as "<RULE-ID>: msg".
Usage: validate_track.py [--check-name] FILE...   (exit 1 on any violation)
"""
import json, os, re, sys
from datetime import datetime

RULES = {
    "NAME-1": "File name is WAI_Track-YYYYMMDD-HHMM-Provider-Model.jsonl (opt-in: --check-name)",
    "STRUCT-1": "Every line is a JSON object",
    "STRUCT-2": "First line is a session_start event",
    "STRUCT-3": "session_end, if present, is the last line and only once",
    "START-1": "session_start has ts, session_id, provider, model, mode, continues",
    "START-2": "session_start mode is active-collection, prep-and-request or closing-request",
    "START-3": "A continuation (continues set) carries continuation_gap_hours over 24",
    "END-1": "session_end has ts, total_turns, summary, unresolved_count",
    "END-2": "session_end total_turns equals the number of points",
    "POINT-1": "Point has turn, ts, phase, focus, action, thinking, with the right types",
    "POINT-2": "turn numbers are sequential from 1",
    "POINT-3": "phase is in the phase vocabulary",
    "POINT-4": "thinking is 3-8 sentences",
    "POINT-5": "ts is ISO-8601 UTC",
    "COND-1": "Conditional fields, when present, have their specified types",
    "COND-2": "context_health usage_estimate is a number and the field only appears above 0.70",
}
PHASES = {"orientation", "exploration", "planning", "execution", "review", "convergence", "crystallization"}
MODES = {"active-collection", "prep-and-request", "closing-request"}
NAME_RE = re.compile(r"^WAI_Track-\d{8}-\d{4}-[A-Za-z0-9]+-[A-Za-z0-9._-]+\.jsonl$")
TS_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z$")

def ts_ok(v):
    if not (isinstance(v, str) and TS_RE.match(v)):
        return False
    try:
        datetime.strptime(v[:19], "%Y-%m-%dT%H:%M:%S")
        return True
    except ValueError:
        return False

def sentences(text):
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()])

def is_list_of(v, keys=None):
    if not isinstance(v, list):
        return False
    if keys is None:
        return all(isinstance(x, str) for x in v)
    return all(isinstance(x, dict) and all(k in x for k in keys) for x in v)

COND = {
    "evolution": lambda v: isinstance(v, str),
    "activity": lambda v: is_list_of(v),
    "decisions": lambda v: is_list_of(v),
    "insights": lambda v: is_list_of(v),
    "fossils": lambda v: is_list_of(v, ["concept", "replaced_by", "reason"]),
    "open": lambda v: is_list_of(v, ["item", "status"]) and all(
        x["status"] in {"unknown", "deferred", "intentional", "blocked"} for x in v),
    "files_in": lambda v: is_list_of(v, ["name", "type", "purpose"]),
    "files_out": lambda v: is_list_of(v, ["name", "type", "summary"]),
    "context_health": lambda v: isinstance(v, dict),
}

def validate(path, check_name=False):
    errs = []
    def e(rule, msg):
        errs.append((rule, msg))
    if check_name and not NAME_RE.match(os.path.basename(path)):
        e("NAME-1", "bad file name %s" % os.path.basename(path))
    events, points = [], []
    with open(path, encoding="utf-8") as f:
        lines = [l for l in f.read().split("\n") if l.strip()]
    objs = []
    for i, l in enumerate(lines, 1):
        try:
            o = json.loads(l)
            if not isinstance(o, dict):
                raise ValueError
            objs.append((i, o))
        except ValueError:
            e("STRUCT-1", "line %d is not a JSON object" % i)
    if not objs or objs[0][1].get("event") != "session_start":
        e("STRUCT-2", "first line is not a session_start event")
    ends = [(i, o) for i, o in objs if o.get("event") == "session_end"]
    if len(ends) > 1 or (ends and ends[0][0] != objs[-1][0]):
        e("STRUCT-3", "session_end must appear once, as the last line")
    for i, o in objs:
        ev = o.get("event")
        if ev == "session_start":
            miss = [k for k in ("ts", "session_id", "provider", "model", "mode", "continues") if k not in o]
            if miss:
                e("START-1", "line %d missing %s" % (i, ", ".join(miss)))
            if "ts" in o and not ts_ok(o["ts"]):
                e("POINT-5", "line %d bad ts" % i)
            if "mode" in o and o["mode"] not in MODES:
                e("START-2", "line %d mode %r" % (i, o["mode"]))
            if o.get("continues"):
                g = o.get("continuation_gap_hours")
                if not isinstance(g, (int, float)) or isinstance(g, bool) or g <= 24:
                    e("START-3", "line %d continuation needs continuation_gap_hours > 24" % i)
        elif ev == "session_end":
            miss = [k for k in ("ts", "total_turns", "summary", "unresolved_count") if k not in o]
            if miss:
                e("END-1", "line %d missing %s" % (i, ", ".join(miss)))
            if "ts" in o and not ts_ok(o["ts"]):
                e("POINT-5", "line %d bad ts" % i)
        elif ev is None:
            points.append((i, o))
    types = {"turn": int, "ts": str, "phase": str, "focus": str, "action": str, "thinking": str}
    for n, (i, o) in enumerate(points, 1):
        for k, t in types.items():
            if k not in o or not isinstance(o[k], t) or isinstance(o[k], bool):
                e("POINT-1", "line %d field %s missing or not %s" % (i, k, t.__name__))
        if o.get("turn") != n:
            e("POINT-2", "line %d turn is %r, expected %d" % (i, o.get("turn"), n))
        if isinstance(o.get("phase"), str) and o["phase"] not in PHASES:
            e("POINT-3", "line %d phase %r" % (i, o["phase"]))
        if isinstance(o.get("thinking"), str) and not 3 <= sentences(o["thinking"]) <= 8:
            e("POINT-4", "line %d thinking has %d sentences" % (i, sentences(o["thinking"])))
        if "ts" in o and not ts_ok(o["ts"]):
            e("POINT-5", "line %d bad ts" % i)
        for k, ok in COND.items():
            if k in o and not ok(o[k]):
                e("COND-1", "line %d field %s malformed" % (i, k))
        ch = o.get("context_health")
        if isinstance(ch, dict):
            u = ch.get("usage_estimate")
            if not isinstance(u, (int, float)) or isinstance(u, bool) or u <= 0.70:
                e("COND-2", "line %d context_health needs usage_estimate > 0.70" % i)
    if ends and ends[0][1].get("total_turns") != len(points):
        e("END-2", "total_turns %r but %d points" % (ends[0][1].get("total_turns"), len(points)))
    return errs

def main(argv):
    check_name = "--check-name" in argv
    files = [a for a in argv if not a.startswith("--")]
    bad = 0
    for p in files:
        errs = validate(p, check_name)
        for r, m in errs:
            print("%s: %s: %s" % (p, r, m))
        bad += bool(errs)
        if not errs:
            print("%s: ok" % p)
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
