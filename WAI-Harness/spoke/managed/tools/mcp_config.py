#!/usr/bin/env python3
"""mcp_config.py -- a distributed MCP baseline that cannot clobber a spoke's own servers.

OPERATOR CORRECTION, 2026-08-19: "Basher should manage that global file but locally in the
spoke they may have customizations."

The naive design -- distribute .mcp.json wholesale -- would have DELETED ezorg's supabase
server, the only genuinely customized spoke in the estate. That server answers an
initialize handshake today; a fan-out would have removed it and no harness surface would
have reported the loss.

So the shape mirrors settings.json / settings.local.json, which this estate already uses
for exactly this problem:

    .mcp.json          BASELINE   Basher owns it, distributed, manifest-tracked
    .mcp.local.json    LOCAL      the spoke owns it, never distributed
    effective          MERGE      local wins per server NAME, otherwise union

WHY PER-NAME AND NOT PER-FILE: a spoke that adds one server must still receive baseline
updates to the others. Whole-file precedence would freeze a spoke's entire MCP surface the
moment it customised any part of it -- which is the quiet way a fleet stops receiving
fixes.

AN EMPTY BASELINE NEVER ERASES A POPULATED LOCAL FILE. Measured 2026-08-19: basher, minder
and framework each carry an EMPTY .mcp.json. If empty meant "delete everything", the first
distribution would wipe any spoke that looked like those three.

USAGE
  mcp_config.py effective --root <spoke>  [--json]   what this spoke actually gets
  mcp_config.py check     --root <spoke>             would a distribution lose anything?
"""
from __future__ import annotations

import argparse
import json
import os
import sys

TOOL_VERSION = "1.0.0"

BASELINE = ".mcp.json"
LOCAL = ".mcp.local.json"


def _servers(path):
    """(servers, file_present). Absent and empty are DIFFERENT and both are reported."""
    try:
        with open(path, encoding="utf-8") as fh:
            return dict((json.load(fh) or {}).get("mcpServers") or {}), True
    except FileNotFoundError:
        return {}, False
    except (OSError, ValueError):
        # Unreadable is not empty. Returning {} silently would let a corrupt local file
        # look like a spoke that customised nothing, and the merge would then "win"
        # against a file it could not read.
        return {}, True


def merge(baseline: dict, local: dict) -> dict:
    """Union by name; local wins a conflict. Never subtractive."""
    out = dict(baseline)
    out.update(local)
    return out


def effective(root=".") -> dict:
    b, b_present = _servers(os.path.join(root, BASELINE))
    l, l_present = _servers(os.path.join(root, LOCAL))
    merged = merge(b, l)
    overridden = sorted(set(b) & set(l))
    return {
        "root": root,
        "baseline": sorted(b), "baseline_file_present": b_present,
        "local": sorted(l), "local_file_present": l_present,
        "effective": sorted(merged),
        "overridden_by_local": overridden,
        "local_only": sorted(set(l) - set(b)),
        "baseline_only": sorted(set(b) - set(l)),
        "declares_nothing": b_present and not b and not l,
    }


def check(root=".", incoming_baseline=None) -> dict:
    """Would distributing INCOMING_BASELINE lose anything this spoke has today?

    THE FIRST CUT OF THIS FUNCTION COULD NEVER SAY NO. It merged the spoke's CURRENT
    baseline with its local file and compared that to itself, so `lost` was always empty
    and every spoke reported safe -- including ezorg, whose supabase server sits in
    .mcp.json, the exact file a distribution REPLACES.

    A check that cannot fail is not a check. Distribution overwrites the baseline, so the
    incoming content is an INPUT: without it this function is asking whether a file equals
    itself.

    incoming_baseline=None means "nothing is being distributed", which is honest for a
    read-only inspection and reports safe because nothing would change.
    """
    e = effective(root)
    current, _ = _servers(os.path.join(root, BASELINE))
    live_local, _ = _servers(os.path.join(root, LOCAL))
    has_now = set(current) | set(live_local)

    if incoming_baseline is None:
        e["would_lose"] = []
        e["safe"] = True
        e["checked_against"] = "nothing incoming -- inspection only"
        return e

    after = set(merge(dict(incoming_baseline), live_local))
    lost = sorted(has_now - after)
    # WHAT THE SPOKE WILL HAVE, as distinct from what it has. `effective` answers the
    # present tense; a fan-out decision needs the future one, and leaving that implicit is
    # how a reader checks the wrong number.
    e["effective_after"] = sorted(after)
    e["would_gain"] = sorted(after - has_now)
    e["would_lose"] = lost
    e["safe"] = not lost
    e["checked_against"] = sorted(incoming_baseline)
    # THE MIGRATION THIS EXPOSES: a server the spoke wants but the baseline does not carry
    # must live in .mcp.local.json, or every distribution deletes it again.
    e["must_move_to_local"] = sorted(set(current) - set(incoming_baseline))
    return e


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("effective", "check"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
        p.add_argument("--json", action="store_true")
        if name == "check":
            p.add_argument("--against", default="",
                           help="path to the baseline that WOULD be distributed")
    args = ap.parse_args(argv)

    incoming = None
    if args.cmd == "check" and args.against:
        incoming, _ = _servers(args.against)
    res = check(args.root, incoming) if args.cmd == "check" else effective(args.root)
    if args.json:
        print(json.dumps(res, indent=2))
        return 0 if res.get("safe", True) else 1

    print(f"\n{res['root']}")
    print(f"  baseline ({BASELINE}):  {res['baseline'] or '(none)'}"
          + ("" if res["baseline_file_present"] else "   [file absent]"))
    print(f"  local ({LOCAL}):  {res['local'] or '(none)'}"
          + ("" if res["local_file_present"] else "   [file absent]"))
    print(f"  EFFECTIVE:  {res['effective'] or '(none)'}")
    if res["overridden_by_local"]:
        print(f"  local overrides: {res['overridden_by_local']}")
    if res["local_only"]:
        print(f"  local-only (a distribution must NOT remove these): {res['local_only']}")
    if res["declares_nothing"]:
        print("  DECLARES NOTHING -- a file that reads as configured and lists no servers")
    if "would_lose" in res:
        print(f"  distribution safe: {res['safe']}"
              + (f"  WOULD LOSE {res['would_lose']}" if res["would_lose"] else ""))
        if res.get("effective_after") is not None:
            print(f"  EFFECTIVE AFTER: {res['effective_after'] or '(none)'}"
                  + (f"  gains {res['would_gain']}" if res.get("would_gain") else ""))
        if res.get("must_move_to_local"):
            print(f"  MUST MOVE to {LOCAL} first: {res['must_move_to_local']}")
    return 0 if res.get("safe", True) else 1


if __name__ == "__main__":
    sys.exit(main())
