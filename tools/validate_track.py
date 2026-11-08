#!/usr/bin/env python3
"""Check a Track file (.jsonl) against spec/track-format.md.

Usage: python3 tools/validate_track.py FILE [FILE ...]
Exit 0 if every file is valid, 1 otherwise. Standard library only.
"""
import json
import re
import sys

PHASES = {"orientation", "exploration", "planning", "execution",
          "review", "convergence", "crystallization"}
REQUIRED = {"turn": int, "ts": str, "phase": str, "focus": str,
            "action": str, "thinking": str}
LISTS = ("activity", "decisions", "insights", "fossils", "open",
         "files_in", "files_out")
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})$")


def check(path):
    errs = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = [(i, l) for i, l in enumerate(f, 1) if l.strip()]
    except OSError as e:
        return [f"cannot read: {e}"]
    rows = []
    for n, line in lines:
        try:
            obj = json.loads(line)
        except ValueError as e:
            errs.append(f"line {n}: not valid JSON ({e})")
            continue
        if not isinstance(obj, dict):
            errs.append(f"line {n}: not a JSON object")
            continue
        rows.append((n, obj))
    if not rows:
        return errs + ["file has no records"]
    if rows[0][1].get("event") != "session_start":
        errs.append(f"line {rows[0][0]}: first record must be a session_start event")
    expected = 1
    for n, o in rows:
        ev = o.get("event")
        if ev == "session_start":
            if n != rows[0][0]:
                errs.append(f"line {n}: session_start must be the first record only")
            for k in ("ts", "session_id"):
                if not isinstance(o.get(k), str) or not o.get(k):
                    errs.append(f"line {n}: session_start needs string '{k}'")
            continue
        if ev == "session_end":
            if n != rows[-1][0]:
                errs.append(f"line {n}: session_end must be the last record")
            continue
        if ev is not None:
            errs.append(f"line {n}: unknown event '{ev}'")
            continue
        for k, t in REQUIRED.items():
            v = o.get(k)
            if not isinstance(v, t) or isinstance(v, bool) or (t is str and not v.strip()):
                errs.append(f"line {n}: point needs {t.__name__} '{k}'")
        if o.get("turn") != expected:
            errs.append(f"line {n}: turn is {o.get('turn')!r}, expected {expected}")
        expected += 1
        if isinstance(o.get("ts"), str) and not ISO.match(o["ts"]):
            errs.append(f"line {n}: ts is not ISO-8601")
        if isinstance(o.get("phase"), str) and o["phase"] not in PHASES:
            errs.append(f"line {n}: phase '{o['phase']}' not in the phase vocabulary")
        for k in LISTS:
            if k in o and not isinstance(o[k], list):
                errs.append(f"line {n}: '{k}' must be a list")
    return errs


def main(argv):
    if not argv:
        print(__doc__.strip())
        return 2
    bad = 0
    for p in argv:
        errs = check(p)
        if errs:
            bad += 1
            print(f"FAIL {p}")
            for e in errs:
                print(f"  {e}")
        else:
            print(f"OK   {p}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
