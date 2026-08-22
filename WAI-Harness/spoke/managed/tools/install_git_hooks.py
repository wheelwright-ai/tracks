#!/usr/bin/env python3
"""install_git_hooks.py — install the WAI pre-commit secret hook into a spoke (Fable MR-2).

The Fable review found ZERO pre-commit hooks across the fleet. This installer wires the
managed `.githooks/pre-commit` (secret scanner) into a spoke via `core.hooksPath`, which is
update-friendly (the hook stays a single tracked file, no per-spoke copy drifts) and safe
because the fleet has no pre-existing hooks to displace.

What it does (idempotent):
  1. seeds `<root>/.githooks/pre-commit` and `<root>/.gitleaks.toml` from the managed template
     if absent (so existing spokes can retrofit without a full template re-sync),
  2. makes the hook executable,
  3. sets `git config core.hooksPath .githooks` (warns first if custom hooks already exist).

Usage:
  python3 tools/install_git_hooks.py [--spoke-path .] [--force]
Exit: 0 installed / already-current | 1 error.
"""
from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

_MANAGED_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "spoke"


def _install_merge_policy(root: Path, report: dict) -> None:
    """Seed .gitattributes and register the `ours` driver it names.

    `.gitattributes` is distributed (tracked, travels with the template), but the driver
    it references is CLONE-LOCAL config — git will not run a merge driver it cannot
    resolve, and silently falls back to a normal conflict. Seeding one without the other
    is the failure mode this function exists to prevent, so both happen here or neither.
    """
    seeded = _seed(root / ".gitattributes", _MANAGED_TEMPLATE / ".gitattributes")
    report["actions"].append(f".gitattributes: {seeded}")

    # `true` is git's documented no-op driver: it leaves %A (our version) in place and
    # reports success. That is exactly "keep the merge target's copy".
    cur = _git(root, "config", "--get", "merge.ours.driver").stdout.strip()
    if cur:
        report["actions"].append(f"merge.ours.driver: already set ({cur})")
    else:
        r = _git(root, "config", "merge.ours.driver", "true")
        if r.returncode != 0:
            report["actions"].append(f"merge.ours.driver: FAILED ({r.stderr.strip()})")
        else:
            report["actions"].append("merge.ours.driver: registered")


def cur_is_githooks(root):
    """True when core.hooksPath resolves to a dir that actually HOLDS hooks.

    COUNT HOOKS, DO NOT TEST DIRECTORY EXISTENCE. Measured 2026-08-18: minder and
    nurturator both point core.hooksPath at an absolute path that EXISTS and is
    EMPTY. A detector that only asks "does the directory exist" reports both as
    healthy while neither has a gate.
    """
    cur = _git(root, "config", "--get", "core.hooksPath").stdout.strip()
    if not cur:
        return False
    # A RELATIVE hooksPath lives in the MAIN worktree, not the linked one. Caught
    # by this tool's own oracle 2026-08-18: from a worktree, `.githooks` resolved
    # to <worktree>/.githooks, which does not exist, so an ARMED repo reported
    # NOT armed -- the same resolve-against-the-wrong-root bug being fixed here,
    # one level up. The main tree is the parent of --git-common-dir.
    if os.path.isabs(cur):
        d = Path(cur)
    else:
        common = _git(root, "rev-parse", "--git-common-dir").stdout.strip()
        if common:
            cp = Path(common) if os.path.isabs(common) else (root / common)
            d = cp.parent / cur
        else:
            d = root / cur
    if not d.is_dir():
        return False
    return any(p.is_file() and not p.name.endswith(".sample") for p in d.glob("*"))


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def _repo_root(spoke_path: str) -> Path | None:
    r = _git(Path(spoke_path), "rev-parse", "--show-toplevel")
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def _seed(dst: Path, src: Path, executable: bool = False) -> str:
    if dst.exists():
        return "present"
    if not src.exists():
        return f"template-missing:{src}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if executable:
        dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return "seeded"


def install(spoke_path: str = ".", force: bool = False) -> dict:
    root = _repo_root(spoke_path)
    if root is None:
        return {"ok": False, "error": f"{spoke_path} is not inside a git repo"}

    report = {"ok": True, "root": str(root), "actions": []}

    hook = root / ".githooks" / "pre-commit"
    report["actions"].append(
        f"hook: {_seed(hook, _MANAGED_TEMPLATE / '.githooks' / 'pre-commit', executable=True)}")
    if hook.exists():  # ensure executable even if it was already present
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    report["actions"].append(
        f"gitleaks-config: {_seed(root / '.gitleaks.toml', _MANAGED_TEMPLATE / '.gitleaks.toml')}")

    if not hook.exists():
        return {"ok": False, "error": "no pre-commit hook to install (template missing)", **report}

    # Warn (don't clobber) if the spoke already has custom hooks under the default path.
    #
    # ASK GIT FOR THE HOOKS DIR. NEVER BUILD root/".git"/"hooks" BY HAND.
    # In a LINKED WORKTREE `root/.git` is a FILE, not a directory, so the old
    # `(root / ".git" / "hooks")` glob found nothing, `existing` came back empty,
    # this guard passed, and the installer set core.hooksPath -- which is
    # REPO-LEVEL config shared by every worktree. The spoke's real gate was
    # disabled everywhere, with no warning and a printed success line.
    #
    # Reported by basher and reproduced here 2026-08-18: in this repo the main
    # tree's .git is_dir() is True and .worktrees/<id>/.git is_dir() is False.
    # A fleet sweep the same day found THREE active spokes (minder, nurturator,
    # ezorg-email-website) running with zero hooks in their effective dir.
    #
    # --git-common-dir is correct in a worktree, a submodule and a plain clone
    # alike; every hand-built .git path is a guess that works in the common case
    # and fails in exactly the case that costs you the gate.
    _common = _git(root, "rev-parse", "--git-common-dir").stdout.strip()
    if _common:
        default_hooks = Path(_common) if os.path.isabs(_common) else (root / _common)
        default_hooks = default_hooks / "hooks"
    else:
        default_hooks = root / ".git" / "hooks"      # non-git dir; caller handles
    existing = [p.name for p in default_hooks.glob("*")
                if p.is_file() and not p.name.endswith(".sample")] if default_hooks.is_dir() else []
    report["effective_hooks_dir"] = str(default_hooks)
    # STATE THE VERDICT, do not leave it inferred. basher 2026-08-18: "an explicit
    # ARMED / NOT ARMED line so the state is stated rather than inferred."
    report["gate_armed_before"] = bool(existing) or cur_is_githooks(root)
    cur = _git(root, "config", "--get", "core.hooksPath").stdout.strip()
    if existing and cur != ".githooks" and not force:
        report["ok"] = False
        report["error"] = (f"existing custom hooks in .git/hooks ({existing}) — re-run with --force "
                           f"to switch core.hooksPath to .githooks (those hooks would be bypassed)")
        return report

    if cur == ".githooks":
        report["actions"].append("core.hooksPath: already .githooks")
    else:
        r = _git(root, "config", "core.hooksPath", ".githooks")
        if r.returncode != 0:
            return {"ok": False, "error": f"git config failed: {r.stderr.strip()}", **report}
        report["actions"].append("core.hooksPath: set to .githooks")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Install the WAI pre-commit secret hook (Fable MR-2).")
    ap.add_argument("--spoke-path", default=".")
    ap.add_argument("--force", action="store_true",
                    help="switch core.hooksPath even if custom .git/hooks exist")
    args = ap.parse_args(argv)

    rep = install(args.spoke_path, args.force)
    for a in rep.get("actions", []):
        print(f"  {a}")
    if rep["ok"]:
        print(f"✓ WAI pre-commit hook active in {rep['root']} (bypass a commit with --no-verify)")
        return 0
    print(f"✖ {rep.get('error')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
