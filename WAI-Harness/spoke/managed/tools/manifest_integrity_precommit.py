#!/usr/bin/env python3
"""manifest_integrity_precommit.py — block a commit that drifts a managed/ MANIFEST.

A managed file (spoke/managed or hub/managed) edited and committed WITHOUT a
MANIFEST recut leaves the recorded md5 stale: the master fails self-verification,
distribution ABORTS ("corrupt master"), and every spoke silently keeps running
stale managed code while reporting version_current:true. This stranded the AP
phase-3 non-dict guard fleet-wide for 3 days (s136, see wai_hygiene.py's
manifest_integrity_heal, which HEALS this before push but doesn't stop the
commit itself). This is the commit-time half: if staged changes touch a managed
root and that root's own MANIFEST doesn't self-verify against the now-staged
content, block — don't let a drifted commit land at all.

impl-manifest-integrity-precommit-gate-v1.

Usage:
  python3 tools/manifest_integrity_precommit.py [--repo-root PATH]
Exit codes:
  0 = no managed/ files staged, or all touched managed roots self-verify
  1 = a touched managed root fails self-verify (staged content vs its MANIFEST)
"""
import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manifest_build

MANAGED_ROOTS = ("WAI-Harness/spoke/managed", "WAI-Harness/hub/managed")


def _staged_paths(repo_root):
    try:
        out = subprocess.run(
            ["git", "-C", repo_root, "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [p for p in out.splitlines() if p.strip()]


def touched_managed_roots(repo_root):
    """Which of MANAGED_ROOTS have a staged change under them (excluding MANIFEST.json
    itself — recutting the manifest is the fix, not itself a drift signal)."""
    staged = _staged_paths(repo_root)
    touched = []
    for root in MANAGED_ROOTS:
        prefix = root + "/"
        for p in staged:
            if p.startswith(prefix) and p != f"{root}/MANIFEST.json":
                touched.append(root)
                break
    return touched


def check(repo_root="."):
    """Return list of (managed_root, verify_report) for roots that fail self-verify."""
    failures = []
    for root in touched_managed_roots(repo_root):
        mroot = os.path.join(repo_root, root)
        manifest_path = os.path.join(mroot, "MANIFEST.json")
        if not os.path.isfile(manifest_path):
            continue  # nothing to verify against — not this gate's concern
        report = manifest_build.verify(mroot, manifest_path)
        if not report.get("ok", True):
            failures.append((root, report))
    return failures


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args(argv)

    failures = check(args.repo_root)
    if not failures:
        return 0

    print(f"manifest_integrity_precommit: {len(failures)} managed root(s) drifted")
    for root, report in failures:
        print(f"  FAIL: {root} — {len(report.get('mismatches', []))} mismatch, "
              f"{len(report.get('missing', []))} missing, {len(report.get('new', []))} new")
    print("Recut before committing: "
          "python3 WAI-Harness/spoke/managed/tools/manifest_build.py <managed_dir> "
          "--manifest-path <managed_dir>/MANIFEST.json --harness-version <ver>")
    return 1


if __name__ == "__main__":
    sys.exit(main())
