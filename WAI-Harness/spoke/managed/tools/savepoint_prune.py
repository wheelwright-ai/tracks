#!/usr/bin/env python3
"""savepoint_prune.py — archive disposable savepoints into a per-initiative _archive/.

Arm of the hygiene advisor (impl-hygiene-advisor-and-arms-v1). Savepoints are
grouped per-initiative under `initiatives/savepoints/<initiative_id>/`. Within each
initiative directory:
  - top-level `*.json` files are the CURRENT savepoints for that initiative,
  - a `superseded/` subdir (an existing, pre-hygiene convention) already holds
    savepoints that were manually demoted — this tool treats those as disposable
    too (they were already judged not-current by whoever put them there),
  - a `completed/` subdir holds terminal savepoints — NEVER touched by this tool.

ELIGIBLE for archival = top-level files with status == "auto-eject", PLUS every
file already sitting in `superseded/`. Everything else — status "closeout",
"active", "pending" (regardless of first_actions — the broader "protect
pending+active+unknown" floor supersedes the narrower original
pending-with-first_actions wording per the Fable Agent-B round-fix on the parent
lug), or any unrecognized/missing status — is PROTECTED and is never a candidate,
independent of --keep.

Among the eligible set (per initiative), the newest --keep (default 5, by
timestamp parsed from the filename/session_id — never mtime) are left in place;
the rest are archived into `<initiative_dir>/_archive/...` (mirroring the source's
subdir so a superseded/ file and a top-level file can never collide on name).

FLOORS (hard, non-bypassable):
  - never touch status in {closeout, active, pending, unknown} (see above),
  - never touch anything already in `completed/`,
  - never prune an initiative's on-disk savepoint count to zero: if archiving the
    full overflow would leave NOTHING behind anywhere in the initiative dir
    (top-level + superseded/ + completed/, post-move), the newest eligible file
    is kept back regardless of --keep.

Dry-run is the DEFAULT. This tool never calls git itself except via --apply
--exec-git (git mv, same belt-and-suspenders double-flag as session_reaper.py).
A JSON receipt is written to hub/local/maintenance/receipts/ and mirrored to
hub/local/maintenance/savepoint-prune-latest.json.

CLI:
    python3 savepoint_prune.py --spoke-root DIR [--keep 5] [--apply --exec-git] [--quiet]
Exit: 0 on a clean run; 2 on an internal error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import wai_paths  # noqa: E402

_TS_RE = re.compile(r"(\d{8})-(\d{4})")
DEFAULT_KEEP = 5
PROTECTED_STATUSES = {"closeout", "active", "pending"}
ELIGIBLE_TOP_LEVEL_STATUS = "auto-eject"
KNOWN_SUBDIRS = {"superseded", "completed", "_archive"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(text: str):
    m = _TS_RE.search(text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _load_status(path: Path):
    try:
        d = json.loads(path.read_text())
        return d.get("status")
    except (json.JSONDecodeError, OSError):
        return None


def _initiative_files(init_dir: Path):
    """Return (top_level_json, superseded_json, completed_json) as lists of Path,
    plus the total count already under _archive/ (informational only)."""
    top = sorted(p for p in init_dir.glob("*.json") if p.is_file())
    superseded = sorted((init_dir / "superseded").glob("*.json")) if (init_dir / "superseded").is_dir() else []
    completed = sorted((init_dir / "completed").glob("*.json")) if (init_dir / "completed").is_dir() else []
    return top, superseded, completed


def _classify(init_dir: Path):
    top, superseded, completed = _initiative_files(init_dir)
    protected, eligible = [], []
    for p in top:
        status = _load_status(p)
        if status == ELIGIBLE_TOP_LEVEL_STATUS:
            eligible.append(p)
        else:
            # closeout / active / pending / unknown / missing -> protected
            protected.append(p)
    eligible.extend(superseded)  # already-demoted files are always eligible
    return protected, eligible, completed


def scan(spoke_root: str, keep: int = DEFAULT_KEEP) -> dict:
    base, mode = wai_paths.resolve_wai_root(spoke_root)
    if base is None:
        return {"ok": False, "error": f"no WAI working base found under {spoke_root}"}
    sp_root = Path(base) / "initiatives" / "savepoints"
    if not sp_root.is_dir():
        return {"ok": False, "error": f"no initiatives/savepoints dir at {sp_root}"}

    now = _now()
    per_initiative = {}
    planned_moves = []
    total_eligible = total_kept = total_archived = 0

    for init_dir in sorted(p for p in sp_root.iterdir() if p.is_dir()):
        init_id = init_dir.name
        protected, eligible, completed = _classify(init_dir)

        def sort_key(p: Path):
            ts = _parse_ts(p.stem)
            return ts or datetime.min.replace(tzinfo=timezone.utc)

        eligible_sorted = sorted(eligible, key=sort_key, reverse=True)  # newest first
        keep_n = keep
        to_archive = eligible_sorted[keep_n:]
        kept = eligible_sorted[:keep_n]

        # Floor: never leave the initiative with literally nothing on disk.
        floor_triggered = False
        remaining_after = len(protected) + len(completed) + len(kept)
        if remaining_after == 0 and to_archive:
            # pull the single newest archive-candidate back into "kept"
            kept.append(to_archive.pop(0))
            floor_triggered = True

        moves = []
        for p in to_archive:
            try:
                rel_parent = p.parent.relative_to(init_dir)
            except ValueError:
                rel_parent = Path(".")
            dst = init_dir / "_archive" / rel_parent / p.name
            src_rel = str(p.relative_to(spoke_root)) if _is_relative(p, spoke_root) else str(p)
            dst_rel = str(dst.relative_to(spoke_root)) if _is_relative(dst, spoke_root) else str(dst)
            moves.append({"src": src_rel, "dst": dst_rel})

        per_initiative[init_id] = {
            "protected_count": len(protected),
            "completed_count": len(completed),
            "eligible_count": len(eligible),
            "kept_count": len(kept),
            "archived_planned_count": len(to_archive),
            "floor_triggered": floor_triggered,
            "moves": moves,
        }
        planned_moves.extend(moves)
        total_eligible += len(eligible)
        total_kept += len(kept)
        total_archived += len(to_archive)

    return {
        "ok": True,
        "spoke_root": os.path.abspath(spoke_root),
        "base": base,
        "harness_mode": mode,
        "keep": keep,
        "ts": now.isoformat(),
        "total_initiatives_scanned": len(per_initiative),
        "total_eligible": total_eligible,
        "total_kept": total_kept,
        "total_archived_planned": total_archived,
        "per_initiative": per_initiative,
        "planned_moves": planned_moves,
    }


def _is_relative(p: Path, root) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


def apply_prune(spoke_root: str, manifest: dict, exec_git: bool = False) -> dict:
    moves = list(manifest["planned_moves"])
    if exec_git:
        for m in moves:
            dst_abs = Path(spoke_root) / m["dst"]
            dst_abs.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "mv", m["src"], m["dst"]], cwd=spoke_root, check=True)
    return {"executed": bool(exec_git), "moves": moves, "count": len(moves)}


def _write_receipt(spoke_root: str, manifest: dict, apply_result: dict | None) -> list:
    receipt = {
        "receipt_id": f"savepoint-prune-{manifest['ts'].replace(':', '')}",
        "tool": "savepoint_prune.py",
        "ts": manifest["ts"],
        "spoke_root": manifest["spoke_root"],
        "keep": manifest["keep"],
        "total_initiatives_scanned": manifest["total_initiatives_scanned"],
        "total_eligible": manifest["total_eligible"],
        "total_kept": manifest["total_kept"],
        "total_archived_planned": manifest["total_archived_planned"],
        "per_initiative_summary": {
            k: {kk: v[kk] for kk in ("eligible_count", "kept_count", "archived_planned_count", "floor_triggered")}
            for k, v in manifest["per_initiative"].items()
        },
        "applied": bool(apply_result and apply_result.get("executed")),
    }
    hub_maint = Path(spoke_root) / "WAI-Harness" / "hub" / "local" / "maintenance"
    written = []
    try:
        receipts_dir = hub_maint / "receipts"
        receipts_dir.mkdir(parents=True, exist_ok=True)
        p = receipts_dir / f"{receipt['receipt_id']}.json"
        p.write_text(json.dumps(receipt, indent=2))
        written.append(str(p))
        latest = hub_maint / "savepoint-prune-latest.json"
        latest.write_text(json.dumps(receipt, indent=2))
        written.append(str(latest))
    except OSError as e:
        receipt["_receipt_write_error"] = str(e)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Archive disposable savepoints, keeping newest --keep per initiative.")
    ap.add_argument("--spoke-root", default=".", help="spoke root (contains WAI-Harness/)")
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    ap.add_argument("--apply", action="store_true", help="write the receipt as an apply run (still requires --exec-git to actually move anything)")
    ap.add_argument("--exec-git", action="store_true", help="actually run `git mv` for each planned move (requires --apply)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    manifest = scan(args.spoke_root, args.keep)
    if not manifest.get("ok"):
        print(json.dumps(manifest, indent=2))
        return 2

    if not args.quiet:
        print(f"savepoint_prune: {manifest['total_initiatives_scanned']} initiatives, "
              f"{manifest['total_eligible']} eligible, {manifest['total_kept']} kept, "
              f"{manifest['total_archived_planned']} planned to archive (keep={manifest['keep']}).")
        for init_id, info in manifest["per_initiative"].items():
            if info["archived_planned_count"]:
                print(f"  {init_id}: eligible={info['eligible_count']} kept={info['kept_count']} "
                      f"archive={info['archived_planned_count']} floor_triggered={info['floor_triggered']}")

    apply_result = None
    if args.apply:
        apply_result = apply_prune(args.spoke_root, manifest, exec_git=args.exec_git)
        if not args.quiet:
            print(json.dumps({"apply": apply_result}, indent=2))

    written = _write_receipt(args.spoke_root, manifest, apply_result)
    manifest["_receipt_written"] = written

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
