#!/usr/bin/env python3
"""managed_sentinel.py — who is dirtying master's managed/ tree, and freezing the fleet?

THE HOLE THIS FILLS (operator, 2026-07-22): "trace back or add logging to find what
is dirtying the managed/ folder." It dirtied THREE times in one day, each time
freezing fleet distribution — because master's self-verification reads the WORKING
tree, so any uncommitted edit under WAI-Harness/spoke/managed/ makes every spoke's
pull abort with "refusing to distribute a corrupt master."

ROOT CAUSE (established by evidence, not guess): mywheel-scoped lugs whose
`file_targets` point into managed/ get dispatched (by autopilot, or a concurrent
session working the mywheel backlog), the builder edits managed/, and the change
lands uncommitted or on a session lane rather than on main. The guard is correct;
the leak is unattributed managed edits.

This does two jobs:
  --check    is managed/ dirty RIGHT NOW? If so, attribute each dirty file to the
             in-progress/recently-completed lug that targets it, and to the git
             author of its last commit. Appends a record to the sentinel log so the
             dirtying is traceable after the fact. Exit 1 if dirty (so a caller —
             e.g. core_ap_run after a round — can log/halt), 0 if clean.
  --watch N  poll every N seconds; log every transition clean<->dirty.

It NEVER writes to managed/ or commits — it only observes and attributes. The
durable fix (verify the committed tree, or refuse agent dispatch at managed) is a
separate design call; this makes the problem visible until then.

Log: WAI-Harness/spoke/local/runtime/managed-sentinel.jsonl
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

MANAGED = "WAI-Harness/spoke/managed"
LOG_REL = "WAI-Harness/spoke/local/runtime/managed-sentinel.jsonl"


def _git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", str(root), *args],
                             capture_output=True, text=True, timeout=15)
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def dirty_managed_files(root: Path) -> list:
    raw = _git(root, "status", "--porcelain", "--", MANAGED)
    files = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        # porcelain: XY<space>path  (path may be "old -> new" for renames)
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path)
    return files


def _lug_for_file(root: Path, path: str) -> str | None:
    """Find an in_progress or recently-completed lug targeting this managed file."""
    want = path.replace(MANAGED + "/", "")
    for status in ("in_progress", "open", "completed"):
        for f in glob.iglob(str(root / "WAI-Harness/spoke/local/lugs/bytype" / "*" / status / "*.json")):
            try:
                d = json.loads(Path(f).read_text())
            except (OSError, ValueError):
                continue
            ft = d.get("file_targets") or d.get("target_files") or []
            for t in ft:
                t = str(t)
                if path in t or want in t or (t.endswith("/*.md") and want.startswith(t[:-5])):
                    return f"{d.get('id')} [{status}]"
    return None


def attribute(root: Path, files: list) -> list:
    rows = []
    for path in files:
        last = _git(root, "log", "-1", "--format=%h %an %ci", "--", path).strip()
        rows.append({
            "file": path,
            "last_commit": last or "(never committed — brand new)",
            "targeting_lug": _lug_for_file(root, path),
        })
    return rows


def check(root: Path, source: str = "manual") -> dict:
    files = dirty_managed_files(root)
    rec = {"clean": not files, "dirty_count": len(files), "source": source,
           "attributions": attribute(root, files) if files else []}
    if files:
        # Timestamp is added by the caller/log line via git, not Date.now (portable).
        log = root / LOG_REL
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            stamp = _git(root, "log", "-1", "--format=%cI").strip() or "unknown"
            with open(log, "a") as fh:
                fh.write(json.dumps({**rec, "head_commit_time": stamp}) + "\n")
        except OSError:
            pass
    return rec


def render(rec: dict) -> str:
    if rec["clean"]:
        return "managed/ CLEAN — fleet distribution not blocked by this repo."
    out = [f"managed/ DIRTY — {rec['dirty_count']} file(s) freeze fleet distribution:"]
    for a in rec["attributions"]:
        out.append(f"  {a['file']}")
        out.append(f"     last commit : {a['last_commit']}")
        out.append(f"     from lug    : {a['targeting_lug'] or '(no lug targets this — manual/tool edit)'}")
    out.append("  -> commit these to main (recut MANIFEST) or the next spoke pull aborts.")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--watch", type=int, metavar="SECS")
    ap.add_argument("--source", default="manual", help="tag the log record (e.g. 'core_ap_run:basher')")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    if args.watch:
        last = None
        try:
            while True:
                rec = check(root, args.source)
                if rec["clean"] != last:
                    print(render(rec), flush=True)
                    last = rec["clean"]
                time.sleep(args.watch)
        except KeyboardInterrupt:
            return 0

    rec = check(root, args.source)
    print(json.dumps(rec, indent=2) if args.json else render(rec))
    return 0 if rec["clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
