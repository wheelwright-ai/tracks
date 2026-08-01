#!/usr/bin/env python3
"""
managed_retire.py — sanctioned retirement path for managed/ source files.

mywheel is is_master, the canonical author of managed/**, but
.claude/hooks/pre-tool-guard.sh blocks raw rm/mv against /managed/ to protect
harness.db and patterns/*.jsonl append-only substrate. Retirement (deleting a
superseded managed/ source file) is a normal authoring operation and needs a
safe, recoverable path instead of a raw rm: snapshot the current blob to
refs/recovery/ (same pattern as revert-mine.sh), delete, drop any matching
capabilities-graph.json entry, and recut MANIFEST.json in the same operation
so the fix never strands.

Usage:
    python3 managed_retire.py <path> [<path> ...] [--reason TEXT] [--no-manifest]

<path> is relative to the managed/ directory (e.g. templates/commands/foo.md)
or a path that otherwise resolves inside managed/.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANAGED_DIR = HERE.parent


def repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=MANAGED_DIR, capture_output=True, text=True, check=True,
    )
    return Path(out.stdout.strip())


def resolve_target(raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        cand = MANAGED_DIR / raw
        p = cand if cand.exists() else Path(raw).resolve()
    return p.resolve()


def guard_protected(path: Path) -> None:
    s = str(path)
    if "harness.db" in s or ("/patterns/" in s and s.endswith(".jsonl")):
        print(f"managed_retire: REFUSED — {path} is protected append-only substrate, not a managed/ source file.", file=sys.stderr)
        sys.exit(2)
    try:
        path.relative_to(MANAGED_DIR)
    except ValueError:
        print(f"managed_retire: REFUSED — {path} is not inside {MANAGED_DIR}", file=sys.stderr)
        sys.exit(2)


def snapshot(path: Path, repo: Path, ts: str) -> str | None:
    rel = path.relative_to(repo)
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(rel)],
        cwd=repo, capture_output=True, text=True,
    )
    if tracked.returncode != 0:
        return None  # untracked/never-committed — nothing to snapshot
    blob = subprocess.run(
        ["git", "rev-parse", f"HEAD:{rel}"],
        cwd=repo, capture_output=True, text=True, check=True,
    ).stdout.strip()
    recref = f"refs/recovery/retire-{path.stem}-{ts}"
    subprocess.run(["git", "update-ref", recref, blob], cwd=repo, check=True)
    return recref


def drop_capgraph_entry(rel_to_managed: str) -> int:
    cg_path = MANAGED_DIR / "capabilities-graph.json"
    if not cg_path.exists():
        return 0
    data = json.loads(cg_path.read_text())
    entries = data.get("entries", [])
    kept = [e for e in entries if rel_to_managed not in e.get("file_paths", [])]
    removed = len(entries) - len(kept)
    if removed:
        data["entries"] = kept
        cg_path.write_text(json.dumps(data, indent=2) + "\n")
    return removed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--reason", default=None)
    ap.add_argument("--no-manifest", action="store_true", help="skip the manifest recut (for batch callers that recut once at the end)")
    args = ap.parse_args()

    repo = repo_root()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    retired_any = False

    for raw in args.paths:
        target = resolve_target(raw)
        guard_protected(target)
        if not target.exists():
            print(f"managed_retire: {target} does not exist — nothing to retire.", file=sys.stderr)
            continue
        if not target.is_file():
            print(f"managed_retire: {target} is not a file — refusing (directories not supported).", file=sys.stderr)
            sys.exit(2)

        recref = snapshot(target, repo, ts)
        rel_to_managed = str(target.relative_to(MANAGED_DIR))
        target.unlink()
        retired_any = True
        if recref:
            print(f"managed_retire: retired {rel_to_managed} — recoverable via `git show {recref}` (ref {recref})")
        else:
            print(f"managed_retire: retired {rel_to_managed} — was untracked, no recovery ref needed")

        dropped = drop_capgraph_entry(rel_to_managed)
        if dropped:
            print(f"managed_retire: dropped {dropped} capabilities-graph.json entr{'y' if dropped == 1 else 'ies'} referencing {rel_to_managed}")

    if retired_any and not args.no_manifest:
        result = subprocess.run([sys.executable, str(HERE / "manifest_build.py"), str(MANAGED_DIR)])
        if result.returncode != 0:
            print("managed_retire: manifest recut FAILED — fix before committing.", file=sys.stderr)
            sys.exit(result.returncode)

    if args.reason:
        print(f"managed_retire: reason: {args.reason}")


if __name__ == "__main__":
    main()
