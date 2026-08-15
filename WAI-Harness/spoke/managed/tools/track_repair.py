#!/usr/bin/env python3
"""track_repair.py -- rejoin pretty-printed JSON objects in a JSONL track.

W9 of the LOW TRUST tenet (spec-low-trust-tenet-v1), closing part of mywheel's
TIER 0 track gap.

THE DAMAGE. A track is JSONL: one object per line. A writer that used indent=2
instead of a compact dump turns one turn into forty-six lines, every one of which
is unparseable on its own. Measured on mywheel 2026-08-02: session-20260722-0824
holds 86 lines, 45 of them fragments of a single object, plus one array element
that happens to parse as a bare JSON string. Every reader of that session -- the
lens, the resident digest, the judgment-coverage oracle -- saw garbage and reported
nothing for the whole session.

WHAT THIS DOES AND DOES NOT DO. It rejoins contiguous fragment runs that parse as
one object when concatenated. That is a lossless, mechanical repair: the bytes were
always there, the newlines were the defect.

It does NOT invent content. A turn that was written floor-only stays floor-only.
The judgment layer cannot be repaired by any tool, because the reasoning was never
written down -- and a repair tool that filled that in would be fabricating a record
of thinking that never happened, which is the single worst thing anything in this
codebase could do. If a fragment run does not parse when rejoined, it is left
exactly as found and reported as unrepairable.

SAFETY. Dry-run by default. Writes a .bak beside the file before touching it. Never
reorders, never drops a line it could not parse, and is idempotent -- a repaired
track passes through unchanged.

CLI:
    track_repair.py --root DIR scan [--json]          what is broken, no writes
    track_repair.py --root DIR repair [--apply]       rejoin; dry-run without --apply

Exit codes: 0 nothing broken, 1 repairable damage found, 2 unrepairable damage.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import trust_epoch as te

MAX_RUN = 400  # a single turn object longer than this is not a pretty-print artefact


def track_paths(root, mode=None):
    return sorted(glob.glob(os.path.join(
        te.base_dir(root, mode), "sessions", "*", "track.jsonl")))


def _is_object_line(line):
    try:
        return isinstance(json.loads(line), dict)
    except ValueError:
        return False


def analyse(lines):
    """Return (repaired_lines, stats). Pure -- no I/O, so it is trivially testable."""
    out, i = [], 0
    stats = {"total": len(lines), "ok": 0, "rejoined": 0, "consumed": 0,
             "unrepairable": 0, "blank": 0}

    while i < len(lines):
        raw = lines[i]
        if not raw.strip():
            stats["blank"] += 1
            i += 1
            continue
        if _is_object_line(raw):
            out.append(raw)
            stats["ok"] += 1
            i += 1
            continue

        # A fragment. Greedily extend until the concatenation parses as an object.
        joined, end = None, None
        for j in range(i + 1, min(i + MAX_RUN, len(lines)) + 1):
            candidate = "".join(part.strip() for part in lines[i:j])
            try:
                parsed = json.loads(candidate)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                joined, end = json.dumps(parsed), j
                break

        if joined is None:
            out.append(raw)          # never dropped; reported instead
            stats["unrepairable"] += 1
            i += 1
            continue

        out.append(joined)
        stats["rejoined"] += 1
        stats["consumed"] += (end - i)
        i = end

    return out, stats


def repair_file(path, apply=False):
    with open(path) as handle:
        lines = handle.read().splitlines()
    repaired, stats = analyse(lines)
    stats["path"] = path
    stats["changed"] = stats["rejoined"] > 0
    if apply and stats["changed"]:
        shutil.copy2(path, path + ".bak")
        with open(path, "w") as handle:
            handle.write("\n".join(repaired) + ("\n" if repaired else ""))
        stats["backup"] = path + ".bak"
    return stats


def scan(root, mode=None, apply=False):
    results = [repair_file(p, apply=apply) for p in track_paths(root, mode)]
    damaged = [r for r in results if r["rejoined"] or r["unrepairable"]]
    return {
        "files": len(results),
        "damaged_files": len(damaged),
        "rejoined": sum(r["rejoined"] for r in results),
        "lines_consumed": sum(r["consumed"] for r in results),
        "unrepairable": sum(r["unrepairable"] for r in results),
        "applied": bool(apply),
        "details": damaged,
    }


def render(report):
    lines = [f"tracks: {report['files']} file(s), {report['damaged_files']} damaged"]
    for d in report["details"]:
        session = os.path.basename(os.path.dirname(d["path"]))
        lines.append(f"  {session}: {d['rejoined']} object(s) rejoined from "
                     f"{d['consumed']} line(s)"
                     + (f", {d['unrepairable']} UNREPAIRABLE" if d["unrepairable"] else ""))
    verb = "repaired" if report["applied"] else "would repair (dry-run; pass --apply)"
    lines.append(f"{verb}: {report['rejoined']} object(s)")
    if report["unrepairable"]:
        lines.append(f"! {report['unrepairable']} line(s) cannot be rejoined -- left as found")
    return "\n".join(lines)


def _main(argv=None):
    top = argparse.ArgumentParser(add_help=False)
    top.add_argument("--root", default=".")
    top.add_argument("--mode", default=None)
    top.add_argument("--json", action="store_true")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS)
    common.add_argument("--mode", default=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], parents=[top])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan", parents=[common])
    p_rep = sub.add_parser("repair", parents=[common])
    p_rep.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    report = scan(args.root, args.mode, apply=(args.cmd == "repair" and args.apply))
    print(json.dumps(report, indent=2) if args.json else render(report))
    if report["unrepairable"]:
        return 2
    return 1 if report["rejoined"] and not report["applied"] else 0


if __name__ == "__main__":
    raise SystemExit(_main())
