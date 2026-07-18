#!/usr/bin/env python3
"""lug_json_parse_gate.py — fail fast on unparseable or conflict-marked lug JSON.

Sweeps <root>/lugs/bytype/**/*.json (resolved via wai_paths, v3/v4-aware) for
JSONDecodeError or leftover git merge conflict markers. A bad hand-merge can bake
conflict markers into a committed lug file, making it invisible to every scanner
that reads JSON (dispatch, groom, expediter, etc.) while still sitting in the tree
as dead weight. Doctrine: re-cut/drop conflicted lugs at merge time, never
hand-splice — this gate exists so a violation is caught before it lands on main
again (impl-lug-json-parse-gate-v1, WAI-Harness/hub/local/reviews/mywheel/phase3-synthesis.md).

Usage:
  python3 tools/lug_json_parse_gate.py [--root PATH] [--quiet]
Exit codes:
  0 = all lugs parse clean, no conflict markers
  1 = at least one lug is unparseable or conflict-marked (listed on stdout)
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wai_paths

CONFLICT_RE = re.compile(r"^(<{7,8}|={7,8}$|>{7,8})", re.MULTILINE)


def sweep(root="."):
    """Return list of (path, reason) for unparseable/conflict-marked lug JSONs."""
    bad = []
    lugs_base = wai_paths.category(root, "lugs")
    if not lugs_base or not os.path.isdir(lugs_base):
        return bad
    for path in sorted(glob.glob(os.path.join(lugs_base, "bytype", "**", "*.json"), recursive=True)):
        try:
            text = open(path, encoding="utf-8").read()
        except Exception as e:
            bad.append((path, f"read-error: {e}"))
            continue
        if CONFLICT_RE.search(text):
            bad.append((path, "unresolved git conflict markers"))
            continue
        try:
            json.loads(text)
        except json.JSONDecodeError as e:
            bad.append((path, f"JSONDecodeError: {e}"))
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="spoke root (contains WAI-Spoke and/or WAI-Harness)")
    ap.add_argument("--quiet", action="store_true", help="suppress per-file output, exit code only")
    args = ap.parse_args(argv)

    bad = sweep(args.root)
    if bad:
        if not args.quiet:
            print(f"lug_json_parse_gate: {len(bad)} unparseable/conflicted lug(s)")
            for p, reason in bad:
                print(f"  FAIL: {p} — {reason}")
        return 1
    if not args.quiet:
        print("lug_json_parse_gate: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
