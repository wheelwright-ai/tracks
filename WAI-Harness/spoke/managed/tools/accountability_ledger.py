#!/usr/bin/env python3
"""accountability_ledger.py — every aspect of the spoke is accountable to itself.

Maps each in-scope file (an "aspect") to a HANDLER:
  owner            — who/what is responsible (person, agent, spoke, advisor)
  virtuous_circle  — the maintenance loop that keeps it healthy (advisor / initiative / lug / monitor id)
  goal_impact      — 0-10 perceived impact on the spoke's goal (how much energy it deserves)
  monitor          — the proof-of-presence check that this aspect stays correct
  documented_in    — where its contract/spec lives (until intentionally removed)
  last_verified    — when the handler last confirmed it

An in-scope file with NO handler (missing, or empty owner AND empty virtuous_circle) is
OPEN — unowned work the wheel can pick up, prioritized by perceived goal_impact. A handled
file whose last_verified is stale needs re-verification. Aspects in the deprecation record
are intentionally removed and excluded from "open" (a single record of deprecation, local
or global, so a removed anti-pattern is never re-surfaced as work).

This is how the harness becomes self-documenting and self-identifying of work: it knows what
matters and what is unowned, so it can spend energy where the spoke's goal needs it.

  scan(root, scope_globs) -> classification {handled, open, stale, deprecated}
  metrics(...)            -> {open_count, handled_count, stale_count, coverage_pct}

CLI:
  accountability_ledger.py [--root R] [--json] [--open] [--stale]
Exit 0 always; --json emits the machine-readable classification for a monitor/oracle.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

# Resolve spoke paths off this file (managed/tools -> spoke root is 3 up from managed).
_TOOLS = os.path.dirname(os.path.abspath(__file__))
_SPOKE_MANAGED = os.path.dirname(_TOOLS)                       # spoke/managed
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_SPOKE_MANAGED)))  # repo root
LEDGER = os.path.join(_REPO, "WAI-Harness", "spoke", "local", "accountability-ledger.json")
DEPRECATIONS = os.path.join(_REPO, "WAI-Harness", "spoke", "local", "deprecations.jsonl")
HUB_DEPRECATIONS = os.path.join(_REPO, "WAI-Harness", "hub", "local", "deprecations.jsonl")

DEFAULT_SCOPE = [
    "WAI-Harness/spoke/managed/tools/*.py",
    "WAI-Harness/spoke/managed/schemas/*.json",
]
STALE_DAYS = 90


def load_ledger(path=LEDGER) -> dict:
    if not os.path.isfile(path):
        return {"aspects": {}}
    try:
        return json.load(open(path))
    except (json.JSONDecodeError, OSError):
        return {"aspects": {}}


def load_deprecations(paths=(DEPRECATIONS, HUB_DEPRECATIONS)) -> dict:
    """Return {aspect_path_or_id: record}. Reads local + hub (global) records; a single
    combined view so a deprecation recorded anywhere is honored."""
    out = {}
    for p in paths:
        if not os.path.isfile(p):
            continue
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = rec.get("aspect") or rec.get("id")
            if key:
                out[key] = rec
    return out


def in_scope(root: str, scope_globs) -> set:
    found = set()
    for g in scope_globs:
        for p in glob.glob(os.path.join(root, g)):
            if os.path.isfile(p):
                found.add(os.path.relpath(p, root))
    return found


def _is_handled(entry: dict) -> bool:
    return bool(entry) and bool(entry.get("owner") or entry.get("virtuous_circle"))


def _is_stale(entry: dict, now: datetime) -> bool:
    lv = entry.get("last_verified")
    if not lv:
        return True
    try:
        dt = datetime.fromisoformat(lv.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (now - dt).days > STALE_DAYS


def scan(root: str, scope_globs=DEFAULT_SCOPE, ledger=None, deprecations=None, now=None) -> dict:
    ledger = ledger if ledger is not None else load_ledger()
    deprecations = deprecations if deprecations is not None else load_deprecations()
    now = now or datetime.now(timezone.utc)
    aspects = ledger.get("aspects", {})
    scoped = in_scope(root, scope_globs)

    handled, open_, stale, deprecated = [], [], [], []
    for rel in sorted(scoped):
        if rel in deprecations:
            deprecated.append(rel)
            continue
        entry = aspects.get(rel)
        if _is_handled(entry):
            handled.append(rel)
            if _is_stale(entry, now):
                stale.append(rel)
        else:
            open_.append({"aspect": rel, "goal_impact": (entry or {}).get("goal_impact", None)})
    # open sorted by goal_impact desc (unknown last) so energy goes to what matters
    open_.sort(key=lambda o: (-(o["goal_impact"] if isinstance(o["goal_impact"], (int, float)) else -1)))
    return {"handled": handled, "open": open_, "stale": stale, "deprecated": deprecated,
            "scoped_total": len(scoped)}


def metrics(cls: dict) -> dict:
    total = cls["scoped_total"] or 1
    handled = len(cls["handled"])
    return {
        "open_count": len(cls["open"]),
        "handled_count": handled,
        "stale_count": len(cls["stale"]),
        "deprecated_count": len(cls["deprecated"]),
        "coverage_pct": round(100.0 * handled / total, 1),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Accountability ledger — self-identifying unowned work")
    ap.add_argument("--root", default=_REPO)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--open", action="store_true", help="list OPEN (unhandled) aspects")
    ap.add_argument("--stale", action="store_true", help="list stale handled aspects")
    a = ap.parse_args(argv)

    cls = scan(a.root)
    m = metrics(cls)
    if a.json:
        print(json.dumps({"metrics": m, **cls}, indent=2))
        return 0
    print(f"Accountability: {m['handled_count']}/{cls['scoped_total']} handled "
          f"({m['coverage_pct']}%) | OPEN={m['open_count']} | stale={m['stale_count']} | deprecated={m['deprecated_count']}")
    if a.open or (not a.stale):
        print("\nOPEN (unowned -> available work, highest goal_impact first):")
        for o in cls["open"][:50]:
            gi = o["goal_impact"]
            print(f"  [{'?' if gi is None else gi}] {o['aspect']}")
    if a.stale:
        print("\nSTALE (handled but past re-verify TTL):")
        for s in cls["stale"]:
            print(f"  {s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
