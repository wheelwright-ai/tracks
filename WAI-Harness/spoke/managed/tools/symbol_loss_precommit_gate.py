#!/usr/bin/env python3
"""symbol_loss_precommit_gate.py — refuse a commit that reverts a managed/ file.

Second line of defense for impl-detect-harness-pull-reverts-before-they-commit-v1.
harness_upgrade.py's NET SYMBOL LOSS gate catches a revert at pull time; this
catches the same class of loss at COMMIT time, so a reverted managed/ tree
cannot land even if the pull guard was bypassed (WAI_ALLOW_SYMBOL_LOSS=1,
BASHER_SKIP_GATE, a hand-applied patch, a bad merge/cherry-pick, …).

Scope, deliberately narrow: only staged, MODIFIED files under
WAI-Harness/spoke/managed/ (new files can't lose symbols they never had;
deleted files are the retire path, a different concern entirely). For each
such .py/.sh/.bash file, diffs HEAD's committed blob (before) against the
staged index blob (after) with the shared symbol_loss module — the exact same
detector harness_upgrade.py uses, so "halted at pull" and "halted at commit"
never disagree about what counts as a loss.

A halt is appended to harness-ahead.json (via harness_upgrade's existing
_record_symbol_loss_halt — one mechanism, not a parallel one), not only
printed, so a headless/CI commit attempt still leaves durable evidence.

Escape hatch, same name/shape as harness_upgrade's pull-time override:
  WAI_ALLOW_SYMBOL_LOSS=1  — deliberate removal, let the commit proceed.

Usage:
  python3 tools/symbol_loss_precommit_gate.py [--root PATH] [--quiet]
Exit codes:
  0 = no net symbol loss in staged managed/ changes (or override set)
  1 = at least one staged file shows net symbol loss (listed on stdout)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import symbol_loss
import harness_upgrade as hu

MANAGED_REL = os.path.join("WAI-Harness", "spoke", "managed")


def _git(root, *args):
    """Run a read-only git command rooted at `root`. Returns stdout (str), or
    None on any failure (never raises — a git hiccup must not be mistaken for
    a symbol-loss finding)."""
    try:
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    return r.stdout if r.returncode == 0 else None


def staged_managed_files(root):
    """Staged, MODIFIED (not added/deleted) paths under WAI-Harness/spoke/managed/,
    relative to `root`. Empty list on any git failure (fail-open on discovery —
    the halt itself only fires on a PROVEN loss, never on 'could not check')."""
    out = _git(root, "diff", "--cached", "--name-only", "--diff-filter=M",
              "--", MANAGED_REL)
    if out is None:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _blob(root, ref, relpath):
    """Read `relpath` at `ref` (a commit-ish, or ':' for the index) via git
    show. Returns text, or None if unreadable (binary, missing, git error)."""
    spec = f"{ref}:{relpath}" if ref != ":" else f":{relpath}"
    try:
        r = subprocess.run(["git", "-C", str(root), "show", spec],
                           capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    return r.stdout if r.returncode == 0 else None


def check(root="."):
    """Returns {relpath: [lost symbol names]} for staged managed/ files that
    would revert a symbol. Empty dict = clean."""
    root = Path(root)
    losses = {}
    for rel in staged_managed_files(root):
        if not rel.endswith((".py", ".sh", ".bash")):
            continue
        before_text = _blob(root, "HEAD", rel)
        after_text = _blob(root, ":", rel)
        if before_text is None or after_text is None:
            continue
        lost = symbol_loss.net_symbol_loss(before_text, after_text, rel)
        if lost:
            losses[rel] = lost
    return losses


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="repo root")
    ap.add_argument("--quiet", action="store_true", help="suppress per-file output, exit code only")
    args = ap.parse_args(argv)

    root = Path(args.root)
    losses = check(root)
    if not losses:
        if not args.quiet:
            print("symbol_loss_precommit_gate: clean")
        return 0

    overridden = os.environ.get(hu.SYMBOL_LOSS_OVERRIDE_ENV) == "1"
    target_managed = root / MANAGED_REL
    if target_managed.is_dir():
        hu._record_symbol_loss_halt(target_managed, losses, overridden=overridden)

    if not args.quiet:
        verb = "OVERRIDDEN" if overridden else "FAIL"
        print(f"symbol_loss_precommit_gate: {len(losses)} file(s) with net symbol loss ({verb})")
        for rel, syms in losses.items():
            print(f"  {rel}: lost {', '.join(syms)}")
        if not overridden:
            print(f"  If this removal is deliberate, set {hu.SYMBOL_LOSS_OVERRIDE_ENV}=1 and retry.")
    return 0 if overridden else 1


if __name__ == "__main__":
    sys.exit(main())
