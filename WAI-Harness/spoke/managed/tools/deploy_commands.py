#!/usr/bin/env python3
"""deploy_commands.py — sync the canonical ceremony/command set to the spoke's
ACTIVE slash-command dir.

The operator's slash commands resolve from <spoke_root>/.claude/commands/. The
CANONICAL source is <spoke_root>/WAI-Harness/spoke/managed/.claude/commands/
(MANIFEST-verified, distributed via harness_upgrade pull). Nothing kept the two in
sync, so the active commands drifted to stale copies (P0 of
initiative-optimize-ceremonies-v1: the operator ran a Jun-5 wai-closeout stub /
a v3 wai-savepoint while the canonical was far ahead).

This tool COPIES every managed command into the active dir (overwriting stale),
PRESERVES active-only local commands (not present in managed), and PRUNES retired
commands (named in RETIRED). Idempotent. Run on pull-on-spin-up + at activate so
the active set can never lag the canonical.

CLI:
    python3 deploy_commands.py --root DIR [--dry-run] [--json]
Exit: 0 ok | 2 error.
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import sys
from pathlib import Path

MANAGED_REL = "WAI-Harness/spoke/managed/.claude/commands"
ACTIVE_REL = ".claude/commands"
# The THIRD command tree. Deployed by nothing, but test_command_template_parity
# asserts against it, so a retirement that skips it leaves an orphan template and
# a permanently red suite (s138: wai-closeout-feedback-v2-slim.md sat here for
# days after both other trees had dropped it, and the failing gate surfaced only
# as an opaque Stop-hook error).
TEMPLATES_REL = "WAI-Harness/spoke/managed/templates/commands"

# Commands retired from the canonical set — remove from the active dir if present.
RETIRED = (
    "wai-closeout-feedback-v2.md",
    "wai-closeout-feedback-v2-slim.md",
)


def _sources(managed_dir: Path):
    return sorted(p for p in managed_dir.glob("*.md") if p.is_file())


def deploy(spoke_root: str, dry_run: bool = True) -> dict:
    root = Path(spoke_root).resolve()
    managed = root / MANAGED_REL
    active = root / ACTIVE_REL
    templates = root / TEMPLATES_REL
    if not managed.is_dir():
        return {"ok": False, "error": f"managed commands dir not found: {managed}"}
    active.mkdir(parents=True, exist_ok=True)

    copied, current, pruned = [], [], []
    managed_names = set()
    for src in _sources(managed):
        managed_names.add(src.name)
        dst = active / src.name
        if dst.exists() and filecmp.cmp(src, dst, shallow=False):
            current.append(src.name)
            continue
        copied.append(src.name)
        if not dry_run:
            shutil.copy2(src, dst)

    # RETIRED files are removed from BOTH trees, and from managed FIRST.
    #
    # THE BUG THIS FIXES (s138, caught rehearsing basher's upgrade). A retired
    # command that still exists in a spoke's MANAGED tree was deployed by the loop
    # above and deleted by this one in the same run — net zero, reported as
    # "2 synced, 2 pruned". An upgrade that changed nothing announced success.
    # Distribution copies files IN but never removes files that should be GONE, so
    # the contradiction persisted on every spoke that had ever received them.
    #
    # Removing from managed too is what makes an upgrade actually DROP deprecated
    # elements rather than carry them forever. It is also safe: managed is
    # regenerated from the master cut, so a wrong removal is one distribution away
    # from being undone.
    for name in RETIRED:
        removed = False
        for tree in (managed, active, templates):
            dst = tree / name
            if dst.exists():
                removed = True
                if not dry_run:
                    dst.unlink()
        # Report the bare NAME once, not once per tree: both directories are
        # called "commands", so a tree-qualified label was both ambiguous and a
        # silent break of this function's existing contract (caught by
        # test_ceremony_deploy_and_drift).
        if removed:
            pruned.append(name)
    # MIRROR live -> templates. RULING (operator delegated, 2026-07-30).
    #
    # templates/commands is deployed by nothing, but test_command_template_parity
    # asserts against it in BOTH directions, so it fails whenever anyone adds or
    # retires a command. Twice in one session: a retired template stranded there,
    # and then three live commands had no template — both fixed by hand, and Ozi
    # tripped the same drift again within the hour by editing three ceremonies.
    #
    # Retire-the-tree was the other option and is what hooks did. Commands differ:
    # the template tree is a documentation surface people read, and the parity test
    # is the only thing that has ever caught ceremony drift. So KEEP it and make it
    # derived rather than hand-maintained — a generated copy cannot drift, and both
    # directions of the parity test become structurally unfailable.
    mirrored = []
    if templates.is_dir():
        for src in _sources(managed):
            if src.name in RETIRED:
                continue
            dst = templates / src.name
            if not dst.exists() or dst.read_bytes() != src.read_bytes():
                mirrored.append(src.name)
                if not dry_run:
                    shutil.copy2(src, dst)
        # A template with no live counterpart is unreachable: prune it.
        live_names = {p.name for p in _sources(managed)}
        for tpl in sorted(templates.glob("*.md")):
            if tpl.name not in live_names and tpl.name not in RETIRED:
                mirrored.append(f"{tpl.name} (removed: no live command)")
                if not dry_run:
                    tpl.unlink()

    # A file cannot be both synced and pruned in one run.
    copied = [c for c in copied if c not in RETIRED]

    # active-only local commands (preserved, never touched)
    active_only = sorted(
        p.name for p in active.glob("*.md")
        if p.name not in managed_names and p.name not in RETIRED
    )
    return {
        "ok": True, "dry_run": dry_run,
        "managed_dir": str(managed), "active_dir": str(active),
        "copied": copied, "already_current": current, "pruned": pruned,
        "mirrored_to_templates": mirrored,
        "preserved_local": active_only,
        "summary": f"{len(copied)} synced, {len(current)} current, "
                   f"{len(pruned)} pruned, {len(mirrored)} mirrored, {len(active_only)} local preserved",
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deploy canonical commands to the active .claude/commands dir.")
    ap.add_argument("--root", default=".", help="spoke root")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rep = deploy(args.root, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        if not rep.get("ok"):
            print(f"deploy_commands: ERROR — {rep.get('error')}", file=sys.stderr)
            return 2
        tag = "[dry-run] would sync" if args.dry_run else "synced"
        print(f"deploy_commands: {tag} — {rep['summary']}")
        for n in rep["copied"]:
            print(f"  ~ {n}")
        for n in rep["pruned"]:
            print(f"  - {n} (retired)")
    return 0 if rep.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
