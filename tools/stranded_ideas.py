#!/usr/bin/env python3
"""List ideas left open at the end of old Tracks, as backlog candidates.

Usage: python3 -B tools/stranded_ideas.py FILE [FILE ...]
Read-only: opens each Track for reading and prints to stdout; writes nothing.
An idea is "stranded" when it is in the `open` list of the LAST point that
has one (the thread was still open when the track stopped being updated) and
its status is not `intentional` (intentional items are planned, not lost).
Output, one per line: FILE:LINE  [status]  item   (LINE = that point's line).
Exit 0 always, unless a file cannot be read (exit 2). Standard library only.
"""
import json
import sys

sys.dont_write_bytecode = True


def stranded(path):
    last = None  # (line_no, open_list)
    with open(path, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                pt = json.loads(raw)
            except ValueError:
                continue
            if isinstance(pt, dict) and isinstance(pt.get("open"), list):
                last = (n, pt["open"])
    if not last:
        return []
    n, items = last
    return [(n, o.get("status", "unknown"), o.get("item", ""))
            for o in items if isinstance(o, dict)
            and o.get("status") != "intentional" and o.get("item")]


def main(argv):
    if not argv:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    total = 0
    for path in argv:
        try:
            rows = stranded(path)
        except OSError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        for n, status, item in rows:
            print(f"{path}:{n}  [{status}]  {item}")
        total += len(rows)
    print(f"{total} stranded idea(s) in {len(argv)} track(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
