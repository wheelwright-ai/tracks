#!/usr/bin/env python3
"""harness_converge.py — P7 master-side cross-spoke convergence (CSRP).

Master (mywheel) is the canonical convergence lead. Spokes accumulate managed/
edits as LOCAL proposals. This tool reconciles those proposals into the master
managed tree, re-cuts the MANIFEST, and bumps the version — giving spokes a
clean path back via harness_upgrade pull.

Symmetry with P6: P6 converges lanes within a spoke; P7 converges spokes back
into the master. Same guarantee: no effort lost, conflicts return as notice lugs
(never silent overwrite), master tree is never corrupted.

Path conventions (consistent with harness_upgrade.py):
  master_harness = WAI-Harness dir of the master (e.g. /mywheel/WAI-Harness)
  spoke_root     = repo root of a contributing spoke (e.g. /basher)
  master_managed = master_harness / spoke / managed
  spoke_managed  = spoke_root / WAI-Harness / spoke / managed

Commands:
  list-contributions  [--spoke-roots R ...] [--master M]
      Diff each spoke's managed/ vs master. Reports: additions, conflicts, same.

  reconcile  --spoke-root R [--master M] [--dry-run] [--base-sha SHA]
      Adopt additions, 3-way merge conflicts, emit notice lug on unresolvable
      conflict, re-cut MANIFEST, bump minor version.

  contribute  --master M [--spoke-root R] [--base-sha SHA]
      Spoke-side: record base sha + deliver contribution lug to master incoming.

  absorb-contributions  [--master M]
      Master reads all pending harness-contribution lugs from its incoming/,
      reconciles each, marks lugs processed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import harness_upgrade as hu  # noqa: E402 — resolves after sys.path insert

CONTRIBUTION_LUG_PREFIX = "harness-contribution-"
BASE_SHA_FILE = "spoke/local/runtime/harness-base.json"


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _iter_managed_files(root):
    root = Path(root)
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != hu.MANIFEST_NAME:
            rel = p.relative_to(root).as_posix()
            if not hu._excluded(rel):
                yield rel


def _md5file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _diff_trees(master_managed, spoke_managed):
    """Compare two managed/ trees. Returns:
      same      — identical content in both
      additions — only in spoke (spoke contributes to master)
      conflicts — in both but different content
      orphans   — only in master (spoke will receive on pull; not actionable here)
    """
    mw = {r: _md5file(Path(master_managed) / r) for r in _iter_managed_files(master_managed)}
    sp = {r: _md5file(Path(spoke_managed) / r) for r in _iter_managed_files(spoke_managed)}

    same, additions, conflicts, orphans = [], [], [], []
    for r, h in sp.items():
        if r not in mw:
            additions.append(r)
        elif mw[r] == h:
            same.append(r)
        else:
            conflicts.append(r)
    for r in mw:
        if r not in sp:
            orphans.append(r)
    return {
        "same": sorted(same),
        "additions": sorted(additions),
        "conflicts": sorted(conflicts),
        "orphans": sorted(orphans),
    }


def _resolve_master_harness(master=None):
    """Resolve to the WAI-Harness dir of the master (matches harness_upgrade DEFAULT_MASTER)."""
    if master:
        return str(Path(master).resolve())
    env = os.environ.get("WAI_HARNESS_MASTER")
    if env:
        return env
    return hu.DEFAULT_MASTER


def _master_managed(master_harness):
    return str(Path(master_harness) / "spoke" / "managed")


def _master_local(master_harness):
    return str(Path(master_harness) / "spoke" / "local")


def _spoke_managed(spoke_root):
    return str(Path(spoke_root) / "WAI-Harness" / "spoke" / "managed")


def _bump_minor(version):
    """Bump minor, reset patch: 4.3.4 → 4.4.0."""
    parts = str(version).split(".")
    if len(parts) >= 3:
        try:
            return f"{parts[0]}.{int(parts[1])+1}.0"
        except ValueError:
            pass
    return version


def _read_harness_base(spoke_root):
    """Read the recorded base SHA from a spoke's local runtime (written by harness_upgrade pull)."""
    p = Path(spoke_root) / "WAI-Harness" / BASE_SHA_FILE
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return None


def _git_head(repo_root):
    """Return HEAD SHA for a git repo, or None."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _git_file_at_sha(repo_root, sha, relpath):
    """Return file bytes at a specific commit, or None if absent."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{sha}:{relpath}"],
            capture_output=True, timeout=30,
        )
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def _three_way_merge(base_content, ours_content, theirs_content):
    """3-way merge using git merge-file in a temp dir.
    Returns (merged_content, had_conflict)."""
    with tempfile.TemporaryDirectory() as tmp:
        base_f = Path(tmp) / "base"
        ours_f = Path(tmp) / "ours"
        theirs_f = Path(tmp) / "theirs"
        base_f.write_bytes(base_content)
        ours_f.write_bytes(ours_content)
        theirs_f.write_bytes(theirs_content)
        r = subprocess.run(
            ["git", "merge-file", "-q", "--stdout",
             str(ours_f), str(base_f), str(theirs_f)],
            capture_output=True, timeout=30,
        )
        merged = r.stdout
        had_conflict = r.returncode != 0
        return merged, had_conflict


def _emit_conflict_lug(master_harness, spoke_name, conflicted_files):
    """Write a notice lug to the spoke's incoming/ (delivered back to that spoke)
    and to master's own local/ as a record."""
    # Try to find the spoke's incoming/ via hub registry
    spoke_incoming = None
    try:
        repo_root = Path(master_harness).parent
        hub_registry = repo_root / "WAI-Harness" / "hub" / "local" / "hub-registry.json"
        reg = json.loads(hub_registry.read_text())
        spoke_entry = next(
            (w for w in reg.get("wheels", [])
             if w.get("name") == spoke_name or w.get("wheel_id") == spoke_name),
            None,
        )
        if spoke_entry:
            sp_path = spoke_entry.get("path", "")
            if sp_path:
                spoke_incoming = Path(sp_path) / "WAI-Harness" / "spoke" / "local" / "lugs" / "incoming"
    except Exception:
        pass

    slug = f"notice-harness-converge-conflict-{spoke_name}-v1"
    lug = {
        "id": slug,
        "type": "notice",
        "status": "open",
        "from_spoke": "mywheel",
        "to_spoke": spoke_name,
        "title": (f"harness-converge: {len(conflicted_files)} managed/ file(s) conflict "
                  f"with master — review needed"),
        "body": (
            "The master ran harness_converge reconcile and found files that diverged in BOTH "
            "the master and your spoke since the last sync. These were NOT auto-merged "
            "to avoid silent data loss. Master version kept. Review the diff and re-contribute "
            "if your version should win."
        ),
        "conflicted_files": conflicted_files,
        "resolution": "review each file; confirm master version is correct or re-contribute via harness_converge contribute",
        "created_at": _utcnow(),
    }

    master_local_incoming = Path(master_harness) / "spoke" / "local" / "lugs" / "incoming"
    for dest in [p for p in [spoke_incoming, master_local_incoming] if p]:
        try:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"{slug}.json").write_text(json.dumps(lug, indent=2) + "\n")
        except Exception:
            pass
    return lug


def _recut_manifest(master_harness, new_version):
    """Re-cut the master MANIFEST with a bumped version. Returns the new manifest."""
    managed = Path(master_harness) / "spoke" / "managed"
    m = hu.build_manifest(str(managed), version=new_version, generated_at=_utcnow())
    mpath = managed / hu.MANIFEST_NAME
    mpath.write_text(json.dumps(m, indent=2) + "\n")
    return m


# ── list-contributions ────────────────────────────────────────────────────────

def list_contributions(spoke_roots, master=None):
    """Diff each spoke's managed/ vs master. Pure read — no writes."""
    master_harness = _resolve_master_harness(master)
    mm = _master_managed(master_harness)
    results = []
    for sr in spoke_roots:
        sr = str(Path(sr).resolve())
        sm = _spoke_managed(sr)
        if not Path(sm).is_dir():
            results.append({"spoke": sr, "error": "no WAI-Harness/spoke/managed/ found"})
            continue
        diff = _diff_trees(mm, sm)
        base_info = _read_harness_base(sr)
        results.append({
            "spoke": sr,
            "base": base_info,
            "additions": len(diff["additions"]),
            "conflicts": len(diff["conflicts"]),
            "same": len(diff["same"]),
            "orphans": len(diff["orphans"]),
            "detail": diff,
        })
    return results


# ── reconcile ─────────────────────────────────────────────────────────────────

def reconcile(spoke_root, master=None, dry_run=False, base_sha=None):
    """Apply a spoke's managed/ contributions onto master.

    1. Copy additions (spoke-only files) to master — always clean.
    2. For conflicts (same file, different content):
       - With base_sha: 3-way merge. Clean → apply. Conflict → notice lug, keep master.
       - Without base_sha: keep master, emit notice lug.
    3. Re-cut MANIFEST, bump minor version (only when changes were adopted).
    """
    master_harness = Path(_resolve_master_harness(master)).resolve()
    spoke_root = Path(spoke_root).resolve()
    spoke_name = spoke_root.name

    mm = master_harness / "spoke" / "managed"
    sm = spoke_root / "WAI-Harness" / "spoke" / "managed"

    if not sm.is_dir():
        return {"ok": False, "error": f"no managed/ at {sm}"}

    diff = _diff_trees(str(mm), str(sm))

    # Resolve base SHA
    if not base_sha:
        base_info = _read_harness_base(str(spoke_root))
        if base_info:
            base_sha = base_info.get("master_sha")

    try:
        current_manifest = hu.load_manifest(str(mm))
        current_version = current_manifest.get("harness_version", "4.0.0")
    except Exception:
        current_version = "4.0.0"
    new_version = _bump_minor(current_version)

    report = {
        "ok": False,
        "dry_run": dry_run,
        "spoke": str(spoke_root),
        "master": str(master_harness),
        "base_sha": base_sha,
        "version_before": current_version,
        "version_after": None,
        "adopted": [],
        "merged": [],
        "kept_master": [],
        "conflicts_emitted": [],
    }

    # Step 1: adopt additions (spoke-only files)
    for rel in diff["additions"]:
        src = sm / rel
        dst = mm / rel
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        report["adopted"].append(rel)

    # Step 2: resolve conflicts
    conflicted_files = []
    for rel in diff["conflicts"]:
        master_bytes = (mm / rel).read_bytes()
        spoke_bytes = (sm / rel).read_bytes()
        resolved = False

        if base_sha:
            git_rel = f"WAI-Harness/spoke/managed/{rel}"
            base_bytes = _git_file_at_sha(str(spoke_root), base_sha, git_rel)
            if base_bytes is None:
                base_bytes = _git_file_at_sha(str(master_harness.parent), base_sha, f"WAI-Harness/spoke/managed/{rel}")

            if base_bytes is not None:
                if spoke_bytes == base_bytes:
                    # Spoke unchanged from base → master is newer → keep master
                    report["kept_master"].append(rel)
                    resolved = True
                elif master_bytes == base_bytes:
                    # Master unchanged from base → spoke has clean contribution → adopt
                    if not dry_run:
                        shutil.copy2(sm / rel, mm / rel)
                    report["merged"].append(rel)
                    resolved = True
                else:
                    # Both changed since base → attempt 3-way merge
                    merged_content, had_conflict = _three_way_merge(base_bytes, master_bytes, spoke_bytes)
                    if not had_conflict:
                        if not dry_run:
                            (mm / rel).write_bytes(merged_content)
                        report["merged"].append(rel)
                        resolved = True

        if not resolved:
            report["conflicts_emitted"].append(rel)
            conflicted_files.append(rel)

    if conflicted_files and not dry_run:
        _emit_conflict_lug(str(master_harness), spoke_name, conflicted_files)

    # Step 3: re-cut MANIFEST and bump version when anything changed
    changes_made = len(report["adopted"]) + len(report["merged"])
    if not dry_run and changes_made > 0:
        new_manifest = _recut_manifest(str(master_harness), new_version)
        verify_result = hu.verify(str(mm), new_manifest)
        report["verify_post"] = verify_result
        report["ok"] = verify_result["ok"]
        report["version_after"] = new_version
    else:
        report["ok"] = True
        report["version_after"] = new_version if dry_run else current_version
        if not dry_run:
            report["note"] = "no changes made; MANIFEST version unchanged"

    return report


# ── contribute ────────────────────────────────────────────────────────────────

def contribute(master, spoke_root=None, base_sha=None):
    """Spoke-side: deliver a contribution lug to master's incoming/.

    Lists files this spoke would contribute and records the base SHA so the
    master's reconcile can compute the correct 3-way diff.
    """
    master_harness = Path(_resolve_master_harness(master)).resolve()
    if spoke_root is None:
        spoke_root = Path(".").resolve()
    else:
        spoke_root = Path(spoke_root).resolve()

    spoke_name = spoke_root.name
    mm = master_harness / "spoke" / "managed"
    sm = spoke_root / "WAI-Harness" / "spoke" / "managed"

    if not sm.is_dir():
        return {"ok": False, "error": f"no managed/ at {sm}"}

    if not base_sha:
        base_info = _read_harness_base(str(spoke_root))
        if base_info:
            base_sha = base_info.get("master_sha")
    if not base_sha:
        base_sha = _git_head(str(master_harness.parent))

    diff = _diff_trees(str(mm), str(sm))
    spoke_head = _git_head(str(spoke_root))

    lug_id = f"{CONTRIBUTION_LUG_PREFIX}{spoke_name}-v1"
    lug = {
        "id": lug_id,
        "type": "harness-contribution",
        "status": "open",
        "from_spoke": spoke_name,
        "to_spoke": "mywheel",
        "title": (f"Managed tree contribution from {spoke_name}: "
                  f"{len(diff['additions'])} additions, {len(diff['conflicts'])} conflicts"),
        "spoke_root": str(spoke_root),
        "spoke_head": spoke_head,
        "base_sha": base_sha,
        "files_to_adopt": diff["additions"],
        "files_conflicting": diff["conflicts"],
        "created_at": _utcnow(),
    }

    dest = master_harness / "spoke" / "local" / "lugs" / "incoming"
    dest.mkdir(parents=True, exist_ok=True)
    lug_path = dest / f"{lug_id}.json"
    lug_path.write_text(json.dumps(lug, indent=2) + "\n")

    # Record base sha on spoke for future reference
    base_rec_path = spoke_root / "WAI-Harness" / BASE_SHA_FILE
    base_rec_path.parent.mkdir(parents=True, exist_ok=True)
    base_rec_path.write_text(json.dumps({
        "master_sha": base_sha,
        "master_root": str(master_harness),
        "recorded_at": _utcnow(),
    }, indent=2) + "\n")

    return {
        "ok": True,
        "lug": str(lug_path),
        "additions": len(diff["additions"]),
        "conflicts": len(diff["conflicts"]),
    }


# ── absorb-contributions ──────────────────────────────────────────────────────

def absorb_contributions(master=None):
    """Master-side: process all pending harness-contribution lugs from incoming/.

    Runs reconcile for each spoke, marks lugs processed.
    """
    master_harness = Path(_resolve_master_harness(master)).resolve()
    incoming = master_harness / "spoke" / "local" / "lugs" / "incoming"
    processed_dir = incoming / "processed"

    if not incoming.is_dir():
        return {"ok": True, "contributions": [], "note": "no incoming/ dir"}

    contribution_lugs = sorted(incoming.glob(f"{CONTRIBUTION_LUG_PREFIX}*.json"))
    if not contribution_lugs:
        return {"ok": True, "contributions": [], "note": "no pending contributions"}

    results = []
    all_ok = True
    for lug_path in contribution_lugs:
        try:
            lug = json.loads(lug_path.read_text())
        except Exception as e:
            results.append({"lug": lug_path.name, "ok": False, "error": str(e)})
            all_ok = False
            continue

        spoke_root_str = lug.get("spoke_root")
        base_sha = lug.get("base_sha")

        if not spoke_root_str or not Path(spoke_root_str).is_dir():
            results.append({
                "lug": lug_path.name, "ok": False,
                "error": f"spoke_root {spoke_root_str!r} not accessible",
            })
            all_ok = False
            continue

        rep = reconcile(spoke_root_str, str(master_harness), dry_run=False, base_sha=base_sha)
        rep["lug"] = lug_path.name
        results.append(rep)
        if not rep.get("ok"):
            all_ok = False

        # Move lug to processed/
        processed_dir.mkdir(parents=True, exist_ok=True)
        lug["status"] = "processed"
        lug["processed_at"] = _utcnow()
        lug["reconcile_summary"] = {
            "ok": rep.get("ok"),
            "adopted": len(rep.get("adopted", [])),
            "merged": len(rep.get("merged", [])),
            "conflicts_emitted": len(rep.get("conflicts_emitted", [])),
        }
        (processed_dir / lug_path.name).write_text(json.dumps(lug, indent=2) + "\n")
        lug_path.unlink()

    return {"ok": all_ok, "contributions": results}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd")

    lc = sub.add_parser("list-contributions", help="diff spoke managed/ trees vs master")
    lc.add_argument("--spoke-roots", nargs="+", default=[], metavar="R")
    lc.add_argument("--master", default=None, help="master WAI-Harness path (default from env/config)")

    rec = sub.add_parser("reconcile", help="apply a spoke's contributions onto master")
    rec.add_argument("--spoke-root", required=True)
    rec.add_argument("--master", default=None)
    rec.add_argument("--dry-run", action="store_true")
    rec.add_argument("--base-sha", default=None, help="last sync SHA (spoke or master git)")

    con = sub.add_parser("contribute", help="(spoke-side) deliver contribution lug to master")
    con.add_argument("--master", required=True, help="master WAI-Harness path")
    con.add_argument("--spoke-root", default=None)
    con.add_argument("--base-sha", default=None)

    ab = sub.add_parser("absorb-contributions", help="(master-side) process all pending contribution lugs")
    ab.add_argument("--master", default=None)

    args = ap.parse_args(argv)

    if args.cmd == "list-contributions":
        result = list_contributions(args.spoke_roots or [], args.master)
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "reconcile":
        result = reconcile(args.spoke_root, args.master, dry_run=args.dry_run, base_sha=args.base_sha)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "contribute":
        result = contribute(args.master, args.spoke_root, args.base_sha)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "absorb-contributions":
        result = absorb_contributions(args.master)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
