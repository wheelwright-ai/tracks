#!/usr/bin/env python3
"""harness_upgrade.py - the verify-apply-verify upgrade engine (v4 distribution).

The cutover gate: before WAI-Harness becomes the registered master, the path by
which a spoke (or the hub) PULLS the master's managed tree must be proven to work
and to be safe. This is that engine.

Model (matches the master layout):
  WAI-Harness/spoke/managed/   - manifest-controlled, MD5-verified, DISTRIBUTED.
                                 Overwritten on upgrade. Carries MANIFEST.json.
  WAI-Harness/spoke/local/     - per-spoke. NEVER touched by an upgrade.
  (hub/managed + hub/local mirror this for the hub.)

The engine only ever reads/writes under the target's `managed/` root. It cannot
touch `local/` by construction (it iterates the manifest's file list, all of which
are managed paths), so the per-spoke local guarantee holds mechanically.

Loop:
  1. verify-pre  -> home_map: per managed file, ADD / CHANGE / UNCHANGED vs master
                   (+ ORPHAN: a managed file in the target absent from the master).
                   --dry-run stops here: a full preview, zero writes.
  2. apply       -> copy each master managed file into the target managed root.
  3. verify-post -> recompute the target's md5s and assert they equal the master
                   MANIFEST. A mismatch is an upgrade FAILURE, not a silent pass.

Pure-ish core (filesystem only, no network): build_manifest, compute_home_map,
verify, apply, upgrade. CLI wraps with subcommands.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

MANIFEST_NAME = "MANIFEST.json"
DEFAULT_VERSION = "4.0.0-pre"

# build/runtime artifacts that are never source, never distributed, and whose
# bytes are non-deterministic (bytecode regenerates on import) — excluding them
# is what lets the master self-verify stably.
_EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git"}
_EXCLUDE_SUFFIXES = (".pyc", ".pyo")
_EXCLUDE_NAMES = {".DS_Store"}


def _excluded(rel):
    parts = rel.split("/")
    if any(p in _EXCLUDE_DIRS for p in parts):
        return True
    if rel.endswith(_EXCLUDE_SUFFIXES):
        return True
    return parts[-1] in _EXCLUDE_NAMES


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_files(root):
    """All files under root, as posix relpaths (excludes the manifest itself)."""
    root = Path(root)
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != MANIFEST_NAME:
            rel = p.relative_to(root).as_posix()
            if not _excluded(rel):
                yield rel


def build_manifest(managed_root, version=DEFAULT_VERSION, is_master=True,
                   default_owner="framework", generated_at="1970-01-01T00:00:00Z"):
    """Compute a MANIFEST for a managed root. Preserves owner/version from a prior
    MANIFEST.json where present; new files get default_owner + version. generated_at
    is injected (no wall-clock) so the manifest is reproducible/testable."""
    managed_root = Path(managed_root)
    prior = {}
    mpath = managed_root / MANIFEST_NAME
    if mpath.exists():
        try:
            prior = json.loads(mpath.read_text()).get("files", {})
        except (OSError, json.JSONDecodeError):
            prior = {}
    files = {}
    for rel in _iter_files(managed_root):
        p = managed_root / rel
        files[rel] = {
            "version": prior.get(rel, {}).get("version", version),
            "md5": _md5(p),
            "owner": prior.get(rel, {}).get("owner", default_owner),
        }
    return {"harness_version": version, "is_master": is_master,
            "generated_at": generated_at, "files": files}


def load_manifest(managed_root):
    return json.loads((Path(managed_root) / MANIFEST_NAME).read_text())


def compute_home_map(master_managed, target_managed):
    """Diff the master MANIFEST against the target's current managed files.
    Returns {add, change, unchanged, orphan} lists of relpaths. No writes."""
    master_files = load_manifest(master_managed)["files"]
    target_root = Path(target_managed)
    add, change, unchanged = [], [], []
    for rel, meta in master_files.items():
        tp = target_root / rel
        if not tp.exists():
            add.append(rel)
        elif _md5(tp) != meta["md5"]:
            change.append(rel)
        else:
            unchanged.append(rel)
    # orphans: managed files present in the target but not in the master manifest
    present = set(_iter_files(target_managed)) if target_root.exists() else set()
    orphan = sorted(present - set(master_files))
    return {"add": sorted(add), "change": sorted(change),
            "unchanged": sorted(unchanged), "orphan": orphan}


def verify(managed_root, manifest):
    """Recompute md5s under managed_root and compare to manifest. Returns
    {ok, mismatches:[{file,expected,actual}], missing:[file]}."""
    root = Path(managed_root)
    mismatches, missing = [], []
    for rel, meta in manifest["files"].items():
        p = root / rel
        if not p.exists():
            missing.append(rel)
            continue
        actual = _md5(p)
        if actual != meta["md5"]:
            mismatches.append({"file": rel, "expected": meta["md5"], "actual": actual})
    return {"ok": not mismatches and not missing, "mismatches": mismatches, "missing": missing}


def apply(master_managed, target_managed, manifest):
    """Copy every managed file from master into the target managed root. Only writes
    under target_managed; never touches a sibling local/ tree. Returns the count."""
    master_root, target_root = Path(master_managed), Path(target_managed)
    written = 0
    for rel in manifest["files"]:
        src, dst = master_root / rel, target_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        written += 1
    # carry the manifest itself so the target records what it now holds
    shutil.copy2(master_root / MANIFEST_NAME, target_root / MANIFEST_NAME)
    return written


def upgrade(master_managed, target_managed, dry_run=False):
    """The full verify-apply-verify loop. Returns a structured report.

    Safety: the master must self-verify (every file's md5 matches its own MANIFEST)
    BEFORE anything is applied — a corrupt/half-cut master is never distributed.
    This is the floor that makes a real cutover safe to automate.
    """
    manifest = load_manifest(master_managed)
    home_map = compute_home_map(master_managed, target_managed)
    report = {"dry_run": dry_run, "home_map": home_map,
              "changes_pending": len(home_map["add"]) + len(home_map["change"])}

    # verify-master gate (skipped on dry-run since dry-run writes nothing anyway,
    # but still reported so a preview surfaces a bad master)
    master_check = verify(master_managed, manifest)
    report["verify_master"] = master_check
    if not master_check["ok"]:
        report["applied"] = 0
        report["verify_post"] = None
        report["ok"] = False
        report["aborted"] = "master failed self-verification — refusing to distribute a corrupt master"
        return report

    if dry_run:
        report["applied"] = 0
        report["verify_post"] = None
        report["ok"] = True   # a preview always "succeeds"; it asserts nothing applied
        return report
    report["applied"] = apply(master_managed, target_managed, manifest)
    report["verify_post"] = verify(target_managed, manifest)
    report["ok"] = report["verify_post"]["ok"]
    return report


def install(master_root, spoke_root, include_hub=False):
    """NON-DESTRUCTIVE v4 install: drop a `WAI-Harness/` folder into an existing
    spoke, beside its v3 `WAI-Spoke/`. Both then coexist; which runs depends on
    which hub folder you invoke. Nothing outside `<spoke>/WAI-Harness/` is written.

    - fresh (no WAI-Harness yet): copy the master spoke tree (managed + the empty
      local skeleton) into <spoke>/WAI-Harness/spoke; optionally the master hub tree.
    - re-install (WAI-Harness exists): run the verify-apply-verify upgrade on its
      managed tree (local untouched).

    Returns a report incl. the pre-existing top-level entries observed before and
    after, so the caller can assert non-destruction.
    """
    master_root, spoke_root = Path(master_root), Path(spoke_root)
    harness = spoke_root / "WAI-Harness"
    pre_existing = sorted(p.name for p in spoke_root.iterdir()) if spoke_root.exists() else []

    report = {"spoke_root": str(spoke_root), "fresh": not harness.exists(),
              "pre_existing": pre_existing}

    if not harness.exists():
        # fresh install: copy master spoke (and optionally hub) wholesale, minus
        # build artifacts (bytecode etc.) so the install matches the manifest exactly
        _ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".DS_Store")
        shutil.copytree(master_root / "spoke", harness / "spoke", ignore=_ignore)
        if include_hub and (master_root / "hub").exists():
            shutil.copytree(master_root / "hub", harness / "hub", ignore=_ignore)
        # ship the always-clean .gitignore so the installed spoke's local/ churn
        # can never dirty the tracked tree (the invariant)
        gi = master_root / ".gitignore"
        if gi.exists():
            shutil.copy2(gi, harness / ".gitignore")
        report["installed"] = "fresh"
        report["gitignore_shipped"] = (harness / ".gitignore").exists()
    else:
        # re-install = upgrade the managed tree in place
        up = upgrade(master_root / "spoke" / "managed", harness / "spoke" / "managed")
        report["installed"] = "upgrade"
        report["upgrade"] = up

    # verify the installed managed tree against the master manifest
    report["verify"] = verify(harness / "spoke" / "managed",
                              load_manifest(master_root / "spoke" / "managed"))
    if include_hub and (harness / "hub" / "managed").exists():
        report["verify_hub"] = verify(harness / "hub" / "managed",
                                      load_manifest(master_root / "hub" / "managed"))

    report["post_existing"] = sorted(p.name for p in spoke_root.iterdir())
    # non-destruction: every pre-existing top-level entry still present, WAI-Harness added
    report["non_destructive"] = (set(pre_existing) <= set(report["post_existing"])
                                 and "WAI-Harness" in report["post_existing"])
    report["ok"] = report["verify"]["ok"] and report["non_destructive"]
    return report


# --- CLI --------------------------------------------------------------------

def _resolve_managed(root, side):
    """root may be a WAI-Harness root, a spoke/hub root, or a managed dir itself."""
    p = Path(root)
    if (p / MANIFEST_NAME).exists():
        return p
    for cand in (p / side / "managed", p / "managed"):
        if cand.exists():
            return cand
    return p / side / "managed"


def main(argv):
    ap = argparse.ArgumentParser(description="verify-apply-verify harness upgrade engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("manifest", help="(re)generate a MANIFEST.json for a managed root")
    g.add_argument("--managed", required=True)
    g.add_argument("--version", default=DEFAULT_VERSION)
    g.add_argument("--generated-at", default="1970-01-01T00:00:00Z")
    g.add_argument("--owner", default="framework")
    g.add_argument("--write", action="store_true")

    for name in ("home-map", "upgrade"):
        s = sub.add_parser(name, help=f"{name} master -> target")
        s.add_argument("--master", required=True)
        s.add_argument("--target", required=True)
        s.add_argument("--side", default="spoke", choices=["spoke", "hub"])
        if name == "upgrade":
            s.add_argument("--dry-run", action="store_true")

    v = sub.add_parser("verify", help="verify a managed root against its MANIFEST")
    v.add_argument("--managed", required=True)
    v.add_argument("--side", default="spoke", choices=["spoke", "hub"])

    i = sub.add_parser("install", help="non-destructively add WAI-Harness/ to a spoke")
    i.add_argument("--master", required=True, help="WAI-Harness master root")
    i.add_argument("--spoke", required=True, help="target spoke root (WAI-Harness/ is added here)")
    i.add_argument("--with-hub", action="store_true", help="also install the hub tree")

    args = ap.parse_args(argv)

    if args.cmd == "install":
        rep = install(args.master, args.spoke, include_hub=args.with_hub)
        print(json.dumps(rep, indent=2))
        return 0 if rep["ok"] else 1

    if args.cmd == "manifest":
        m = build_manifest(args.managed, version=args.version,
                           default_owner=args.owner, generated_at=args.generated_at)
        if args.write:
            (Path(args.managed) / MANIFEST_NAME).write_text(json.dumps(m, indent=2) + "\n")
            print(f"wrote {Path(args.managed) / MANIFEST_NAME} ({len(m['files'])} files)")
        else:
            print(json.dumps(m, indent=2))
        return 0

    if args.cmd == "home-map":
        master = _resolve_managed(args.master, args.side)
        target = _resolve_managed(args.target, args.side)
        hm = compute_home_map(master, target)
        print(json.dumps(hm, indent=2))
        return 0

    if args.cmd == "upgrade":
        master = _resolve_managed(args.master, args.side)
        target = _resolve_managed(args.target, args.side)
        rep = upgrade(master, target, dry_run=args.dry_run)
        print(json.dumps(rep, indent=2))
        return 0 if rep["ok"] else 1

    if args.cmd == "verify":
        managed = _resolve_managed(args.managed, args.side)
        r = verify(managed, load_manifest(managed))
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1

    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
