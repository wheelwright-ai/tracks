#!/usr/bin/env python3
"""Check a WAI Track (.jsonl) against spec/track-format.md.

Usage: python3 tools/validate_track.py FILE [FILE ...]
Exit 0 if every file is valid, 1 otherwise. Prints one line per problem.
Standard library only.
"""
import json
import re
import sys

PHASES = {"orientation", "exploration", "planning", "execution",
          "review", "convergence", "crystallization"}
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})$")
REQUIRED = {"turn": int, "ts": str, "phase": str, "focus": str,
            "action": str, "thinking": str}
STR_LISTS = ("activity", "decisions", "insights")
OBJ_LISTS = {"fossils": ("concept", "replaced_by", "reason"),
             "open": ("item", "status"),
             "files_in": ("name",), "files_out": ("name",)}
OPEN_STATUS = {"unknown", "deferred", "intentional", "blocked"}


def check_point(p, n, err):
    for k, t in REQUIRED.items():
        if k not in p:
            err(n, f"missing required field '{k}'")
        elif not isinstance(p[k], t) or isinstance(p[k], bool):
            err(n, f"'{k}' must be {t.__name__}")
    if isinstance(p.get("ts"), str) and not TS.match(p["ts"]):
        err(n, f"'ts' is not ISO-8601: {p['ts']!r}")
    if isinstance(p.get("phase"), str) and p["phase"] not in PHASES:
        err(n, f"unknown phase {p['phase']!r}")
    for k in STR_LISTS:
        if k in p and not (isinstance(p[k], list) and all(isinstance(x, str) for x in p[k])):
            err(n, f"'{k}' must be an array of strings")
    for k, keys in OBJ_LISTS.items():
        if k not in p:
            continue
        if not isinstance(p[k], list):
            err(n, f"'{k}' must be an array of objects")
            continue
        for item in p[k]:
            if not isinstance(item, dict):
                err(n, f"'{k}' entries must be objects")
                continue
            for need in keys:
                if need not in item:
                    err(n, f"'{k}' entry missing '{need}'")
            if k == "open" and item.get("status") not in OPEN_STATUS | {None}:
                err(n, f"open status {item['status']!r} not in {sorted(OPEN_STATUS)}")
    if "evolution" in p and not isinstance(p["evolution"], str):
        err(n, "'evolution' must be a string")
    if "context_health" in p and not isinstance(p["context_health"], dict):
        err(n, "'context_health' must be an object")


def validate(path):
    problems = []

    def err(n, msg):
        problems.append(f"{path}:{n}: {msg}")

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
            err(i, f"not valid JSON ({e})")
            continue
        if not isinstance(d, dict):
            err(i, "line must be a JSON object")
            continue
        rows.append((i, d))
    if not rows:
        return problems or [f"{path}: empty file"]
    if rows[0][1].get("event") != "session_start":
        err(rows[0][0], "first line must be a session_start event")
    starts = [r for r in rows if r[1].get("event") == "session_start"]
    if len(starts) > 1:
        err(starts[1][0], "more than one session_start")
    for i, d in starts:
        for k in ("ts", "session_id", "provider", "model"):
            if not isinstance(d.get(k), str):
                err(i, f"session_start missing string '{k}'")
    ends = [r for r in rows if r[1].get("event") == "session_end"]
    if ends and rows[-1][1].get("event") != "session_end":
        err(ends[0][0], "session_end must be the last line")
    points = [(i, d) for i, d in rows if "event" not in d]
    for i, d in rows:
        if "event" in d and d["event"] not in ("session_start", "session_end"):
            err(i, f"unknown event {d['event']!r}")
    prev = 0
    for i, d in points:
        check_point(d, i, err)
        t = d.get("turn")
        if isinstance(t, int) and not isinstance(t, bool):
            if t != prev + 1:
                err(i, f"turn {t} does not follow turn {prev} (must be sequential)")
            prev = t
    for i, d in ends:
        if isinstance(d.get("total_turns"), int) and d["total_turns"] != len(points):
            err(i, f"total_turns={d['total_turns']} but file has {len(points)} points")
    return problems


def main(argv):
    if not argv:
        print(__doc__.strip())
        return 2
    bad = 0
    for path in argv:
        problems = validate(path)
        if problems:
            bad += 1
            print("\n".join(problems))
        else:
            print(f"OK  {path}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
