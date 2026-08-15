#!/usr/bin/env python3
"""bench_snapshot.py — capture a BEFORE-state dogfood bench snapshot.

Part of the two-bench instrument required by Migration doctrine 5
(docs/wheelwright-v5-control-plane-directive.md, Part IV): "a phase certifies
only when both [benches] pass." A bench snapshot is the deterministic
before-state a later bench_assert.py run diffs against.

Captures three things about a spoke root:
  1. file_manifest  — sha256 of every in-scope file (path -> hash), so any
     content drift is visible even when a byte count would hide it.
  2. lug_counts     — per (type, status) counts under lugs/bytype/**, so
     "did the phase leave the backlog shape it claimed to" is checkable.
  3. oracle_results — circle_audit.py and dead_end_scan.py run --json against
     the same root (contract_validate.py is best-effort: it wants a
     registered wheel_id + AP history a fresh dogfood spoke won't have yet).

Scope resolution (fixed 2026-08-05 after a real defect: a fresh dogfood spoke
has no WAI-Harness/spoke/managed/ at all — managed/ arrives via distribution,
never via harness_init.py at birth — so the OLD fixed default silently
snapshotted 0 files and bench_assert then "round-tripped" 0 against 0,
reporting drift=False for a broken tool as readily as a working one).
resolve_default_scope() now checks what the root ACTUALLY contains:
  1. Prefer the narrow default (managed/ + spoke/local/lugs) when either
     exists — stable and fast on a canonical wheel like mywheel.
  2. Otherwise fall back to a full-root scan (still respecting the exclude
     list) so a managed/-less spoke — e.g. a just-recreated dogfood bench —
     still gets a real, non-empty capture of what it actually has.
An explicit --scope-dirs is never auto-widened: if you name dirs yourself and
they match nothing, that is a real error in your invocation, not something to
paper over.

capture() now HARD-FAILS (raises EmptyScopeError) if file_manifest comes back
empty. An oracle that can silently report "nothing changed" over "nothing
observed" is not an oracle — it is a Goodhart target. Zero drift may only be
reported over a non-empty capture.

Usage:
    bench_snapshot.py --root /path/to/spoke --out snapshot.json [--label greenfield]
    bench_snapshot.py --root /path/to/spoke --out snapshot.json --scope-dirs "WAI-Harness"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

DEFAULT_SCOPE_DIRS = [
    "WAI-Harness/spoke/managed",
    "WAI-Harness/spoke/local/lugs",
]

EXCLUDE_NAMES = {
    "__pycache__", ".DS_Store", "harness.db", "harness.db-wal",
    "harness.db-shm", "events-journal.jsonl", ".git",
    "node_modules", ".venv", ".worktrees",
}
EXCLUDE_SUFFIX = {".pyc", ".bak", ".tmp", ".log"}


class EmptyScopeError(RuntimeError):
    """Raised when a capture's file_manifest is empty. An oracle that cannot
    fail must refuse to report — this forces the caller to look at scope
    resolution rather than silently pass a 0-vs-0 comparison."""


def _has_any_file(d: Path) -> bool:
    return d.exists() and any(p.is_file() for p in d.rglob("*"))


def resolve_default_scope(root: Path) -> tuple[list[str], str]:
    """Pick scope dirs from what `root` actually contains, not a fixed list
    that may not apply to this spoke's current shape. A directory that
    EXISTS but holds zero files (e.g. a freshly-scaffolded, empty lugs/ tree)
    does not count as present — an empty-of-files scope is exactly the
    vacuous case this function exists to avoid."""
    existing = [sd for sd in DEFAULT_SCOPE_DIRS if _has_any_file(root / sd)]
    if existing:
        return existing, "default (managed/ + lugs/ — present and non-empty)"
    return ["."], ("auto-fallback: full-root scan — neither "
                    f"{' nor '.join(DEFAULT_SCOPE_DIRS)} has any files under {root}")


def _skip(p: Path) -> bool:
    return (p.name in EXCLUDE_NAMES or p.suffix in EXCLUDE_SUFFIX
            or any(part in EXCLUDE_NAMES for part in p.parts))


def file_manifest(root: Path, scope_dirs: list[str]) -> dict:
    manifest = {}
    for sd in scope_dirs:
        base = root / sd
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or _skip(p):
                continue
            rel = str(p.relative_to(root))
            h = hashlib.sha256()
            try:
                h.update(p.read_bytes())
            except OSError as e:
                manifest[rel] = f"UNREADABLE: {e}"
                continue
            manifest[rel] = h.hexdigest()
    return manifest


def lug_counts(root: Path) -> dict:
    counts = {}
    lugs_root = root / "WAI-Harness" / "spoke" / "local" / "lugs" / "bytype"
    if not lugs_root.exists():
        return counts
    for type_dir in sorted(p for p in lugs_root.iterdir() if p.is_dir()):
        for status_dir in sorted(p for p in type_dir.iterdir() if p.is_dir()):
            n = sum(1 for f in status_dir.glob("*.json"))
            if n:
                counts[f"{type_dir.name}/{status_dir.name}"] = n
    return counts


# Fix 2026-08-05 (2nd defect, sign flipped from the first): storing and
# wholesale-comparing the RAW oracle payload meant drift=True on every run,
# on every tree, forever — circle_audit's top-level `ts` and its nested
# `hub.budget_guard_detail.age_hours` are clock-derived and can never repeat.
# A gate that always fires is as useless as one that never does, and worse:
# it looks like it's working. Two layers fix this:
#
#   1. VOLATILE_ORACLE_KEYS — an explicit deny-list (not a heuristic) of key
#      names stripped recursively from any oracle payload before anything
#      else touches it. A reader can see exactly what's excluded and why.
#   2. ORACLE_MEANING — per-oracle extractors that pull out only what the
#      gate actually cares about (circle_audit: verdict + each circle's
#      verdict/breaks; dead_end_scan: clean + finding counts), applied AFTER
#      stripping. This is what gets stored and diffed — never the raw blob,
#      so a certification lug's bench_results stays small enough to read
#      instead of carrying a multi-kilobyte dump nobody opens.
VOLATILE_ORACLE_KEYS = {
    "ts", "timestamp", "generated_at", "captured_at", "checked_at",
    "last_evaluated", "observed_at", "age_hours", "age_h", "duration",
    "duration_s", "duration_ms", "elapsed", "elapsed_s", "run_id", "pid",
}


def _strip_volatile(obj):
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items()
                if k not in VOLATILE_ORACLE_KEYS}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


def _meaning_circle_audit(stripped: dict) -> dict:
    """The gate cares whether the overall verdict changed, or whether any
    circle's verdict or its `breaks` findings changed — not prose reshuffling
    or which order circles were emitted in (hence the id-sort)."""
    circles = sorted(
        ({"id": c.get("id"), "verdict": c.get("verdict"),
          "breaks": sorted(c.get("breaks") or [])}
         for c in (stripped.get("circles") or [])),
        key=lambda c: c["id"] or "")
    return {"verdict": stripped.get("verdict"), "circles": circles}


def _meaning_dead_end_scan(stripped: dict) -> dict:
    """The gate cares whether the tree is clean and how many findings of each
    kind exist — not the literal list of untracked filenames (which churns
    with unrelated concurrent work) or landing prose."""
    return {
        "clean": stripped.get("clean"),
        "counts": {
            "uncommitted": len(stripped.get("uncommitted") or []),
            "untracked_source": len(stripped.get("untracked_source") or []),
            "unpushed": stripped.get("unpushed"),
            "stashes": len(stripped.get("stashes") or []),
            "branches_ahead": len(stripped.get("branches_ahead") or []),
        },
    }


# Oracles without a curated extractor fall back to the stripped-of-volatility
# full payload — still safe (no clock fields survive _strip_volatile), just
# not curated down to a minimal meaning yet.
ORACLE_MEANING = {
    "circle_audit": _meaning_circle_audit,
    "dead_end_scan": _meaning_dead_end_scan,
}


def _run_oracle(cmd: list[str], cwd: Path, name: str) -> dict:
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True,
                               text=True, timeout=120)
        entry = {"returncode": proc.returncode}
        try:
            raw = json.loads(proc.stdout)
        except json.JSONDecodeError:
            entry["error"] = "non-JSON output"
            entry["stdout_tail"] = proc.stdout[-500:]
            entry["stderr_tail"] = proc.stderr[-500:]
            return entry
        stripped = _strip_volatile(raw)
        extractor = ORACLE_MEANING.get(name, lambda s: s)
        entry["meaning"] = extractor(stripped)
        return entry
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": str(e)}


def oracle_results(root: Path) -> dict:
    results = {}
    circle_audit = HERE / "circle_audit.py"
    dead_end_scan = HERE / "dead_end_scan.py"
    if circle_audit.exists():
        results["circle_audit"] = _run_oracle(
            [sys.executable, str(circle_audit), "--root", str(root), "--json", "--quiet"],
            root, "circle_audit")
    if dead_end_scan.exists():
        results["dead_end_scan"] = _run_oracle(
            [sys.executable, str(dead_end_scan), "--root", str(root), "--scope", "session", "--json"],
            root, "dead_end_scan")
    return results


def capture(root: Path, scope_dirs: list[str], label: str | None,
            with_oracles: bool = True, scope_note: str | None = None) -> dict:
    manifest = file_manifest(root, scope_dirs)
    if not manifest:
        raise EmptyScopeError(
            f"scope matched 0 files under root={root} scope_dirs={scope_dirs}. "
            "Refusing to report a capture over an empty set — that would make "
            "any later drift comparison vacuously pass. Check the scope_dirs "
            "actually exist under this root (a fresh spoke may have no "
            "managed/ until distribution runs — pass --scope-dirs explicitly, "
            "or rely on the auto-fallback full-root scan).")
    snap = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "label": label,
        "scope_dirs": scope_dirs,
        "scope_resolution": scope_note,
        "file_manifest": manifest,
        "lug_counts": lug_counts(root),
    }
    snap["file_count"] = len(snap["file_manifest"])
    if with_oracles:
        snap["oracle_results"] = oracle_results(root)
    return snap


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="spoke root to snapshot")
    ap.add_argument("--out", required=True, help="path to write the snapshot JSON")
    ap.add_argument("--label", default=None, help="e.g. greenfield / brownfield")
    ap.add_argument("--scope-dirs", default=None,
                    help="comma-separated root-relative dirs (default: managed/ + lugs/)")
    ap.add_argument("--no-oracles", action="store_true",
                    help="skip circle_audit/dead_end_scan (faster, structural-only)")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"ERROR: root does not exist: {root}", file=sys.stderr)
        return 2

    if args.scope_dirs:
        scope_dirs, scope_note = args.scope_dirs.split(","), "explicit --scope-dirs"
    else:
        scope_dirs, scope_note = resolve_default_scope(root)
        print(f"[bench_snapshot] scope: {scope_note} -> {scope_dirs}")

    try:
        snap = capture(root, scope_dirs, args.label, with_oracles=not args.no_oracles,
                       scope_note=scope_note)
    except EmptyScopeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snap, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[bench_snapshot] wrote {out_path} — {snap['file_count']} files, "
          f"{sum(snap['lug_counts'].values())} lugs counted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
