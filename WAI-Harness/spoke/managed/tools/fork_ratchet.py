#!/usr/bin/env python3
"""Fail when a NEW divergent duplicate appears. A ratchet, not an alarm.

WHY A RATCHET. The s141 sweep found 58 basename groups whose copies have drifted.
A check that simply fails on divergence would fail on the first run, every run, and
be muted inside a day -- turning on a smoke alarm in a building already full of
smoke. So this records a baseline of the known 58 and fails only when the set GROWS
or an unknown group appears. The existing debt stays visible in the count without
drowning the signal that someone just forked something new.

WHAT IT IS FOR. Measured in one evening:
  * ./autopilot was a 404-line fork of the 442-line managed tool, and BOTH fixes
    made that day landed only in managed -- never reaching the file a human types.
  * WAI-Spoke/kernel is a runnable vendored copy of WAI-Harness/kernel; the two
    disagreed by 60 files and reported different backlog counts for the same repo.
  * hub/local (what cron invokes) and hub/managed (what MANIFEST distributes) drift
    in BOTH directions, meaning no reconciliation step exists at all.
None of it was detected by anything. Each was found by hand, twice by accident.

EXIT CODES
  0  no new divergence (existing baseline entries are reported, not failed)
  1  a new divergent group appeared, or a known one gained a copy
  2  usage / unreadable baseline -- never confused with a clean run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

# Copies that are SUPPOSED to exist and are not forks. Each exclusion is a claim, so
# each carries its reason -- an unexplained exclusion is how a real fork hides.
EXCLUDE_PARTS = (
    ".git",                      # not source
    ".worktrees",                # per-session checkouts of this same tree
    ".claude/worktrees",
    ".certify-9f08-extract",     # a frozen certification snapshot, deliberately stale
    "teachings_repo",            # payload copies distributed to spokes by design
    "_archive",
    ".subsumed-graveyard",
    "processed",
    "node_modules",
    "__pycache__",
    "site-packages",
)
SUFFIXES = (".py", ".sh")

DEFAULT_BASELINE = ("WAI-Harness/spoke/local/maintenance/fork-ratchet-baseline.json")


def _skip(path: str) -> bool:
    return any(f"/{part}/" in f"/{path}/" for part in EXCLUDE_PARTS)


def divergent_groups(root: str = ".") -> dict:
    """basename -> sorted list of md5s, for every basename with 2+ DIFFERING copies."""
    by_name: dict[str, dict[str, str]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in
                       (".git", "__pycache__", "node_modules", ".worktrees")]
        for fn in filenames:
            if not fn.endswith(SUFFIXES):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            if _skip(rel):
                continue
            try:
                digest = hashlib.md5(open(full, "rb").read()).hexdigest()
            except OSError:
                continue
            by_name.setdefault(fn, {})[rel] = digest
    out = {}
    for name, copies in by_name.items():
        if len(copies) > 1 and len(set(copies.values())) > 1:
            out[name] = sorted(copies)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--update-baseline", action="store_true",
                    help="re-record the current set as accepted. A deliberate act: "
                         "it forgives every fork present right now.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    root = args.root
    baseline_path = Path(args.baseline or os.path.join(root, DEFAULT_BASELINE))
    current = divergent_groups(root)

    if args.update_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(
            {"_why": "Known divergent duplicates. The ratchet fails only on ADDITIONS. "
                     "Shrink this list; never grow it without saying why.",
             "groups": {k: len(v) for k, v in sorted(current.items())}},
            indent=1) + "\n", encoding="utf-8")
        print(f"fork-ratchet: baseline recorded — {len(current)} divergent group(s)")
        return 0

    try:
        known = (json.loads(baseline_path.read_text(encoding="utf-8"))
                 .get("groups") or {}) if baseline_path.exists() else {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"fork-ratchet: baseline unreadable ({exc}) -- refusing to guess", file=sys.stderr)
        return 2

    new = sorted(k for k in current if k not in known)
    grown = sorted(k for k in current if k in known and len(current[k]) > known[k])

    if args.json:
        print(json.dumps({"divergent": len(current), "baseline": len(known),
                          "new": new, "grown": grown}, indent=1))
    else:
        print(f"fork-ratchet: {len(current)} divergent group(s), baseline {len(known)}")
        for n in new:
            print(f"  NEW FORK    {n}: {', '.join(current[n])}", file=sys.stderr)
        for n in grown:
            print(f"  GREW        {n}: now {len(current[n])} copies "
                  f"(was {known[n]})", file=sys.stderr)
        if not new and not grown:
            print("  no new divergence")

    return 1 if (new or grown) else 0


if __name__ == "__main__":
    sys.exit(main())
