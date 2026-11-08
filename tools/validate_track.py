#!/usr/bin/env python3
"""Minimal Track file check: python3 tools/validate_track.py FILE.jsonl [...]

Every line must be a JSON object. A session_start line must come first. Turn
rows (an "event":"turn" row, or any row with a "turn" number) need an integer
turn, a ts, and turns must count up. Exit 0 if every file passes, 1 otherwise.
"""
import json
import sys


def check(path):
    errors, last_turn, first = [], 0, True
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError as exc:
                errors.append(f"line {n}: not JSON ({exc})")
                continue
            if not isinstance(row, dict):
                errors.append(f"line {n}: not a JSON object")
                continue
            if first and row.get("event") != "session_start":
                errors.append(f"line {n}: first line must be a session_start event")
            first = False
            if row.get("event") == "turn" or "turn" in row:
                t = row.get("turn")
                if not isinstance(t, int) or isinstance(t, bool):
                    errors.append(f"line {n}: turn must be an integer")
                elif t <= last_turn:
                    errors.append(f"line {n}: turn {t} does not follow turn {last_turn}")
                else:
                    last_turn = t
                if "ts" not in row:
                    errors.append(f"line {n}: turn row has no ts")
    if first:
        errors.append("file is empty")
    return errors


if __name__ == "__main__":
    bad = 0
    for p in sys.argv[1:]:
        errs = check(p)
        print(("FAIL " if errs else "ok   ") + p)
        for e in errs:
            print("  " + e)
        bad += bool(errs)
    sys.exit(1 if bad or len(sys.argv) < 2 else 0)
