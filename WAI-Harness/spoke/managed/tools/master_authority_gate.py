#!/usr/bin/env python3
"""Refuse a local edit to distributed source on a spoke that does not author it.

OPERATOR DIRECTIVE 2026-08-17:

    "we are having competing spokes this is the only spoke that manages what the
     harness does and is distributed the other spokes should know to phone home
     and direct changes through mywheel"

WHY A GATE AND NOT A PARAGRAPH. The rule already existed -- CLAUDE.md's "Tool
Ownership (author vs distribute)" says a non-master spoke proposes changes by lug
and never edits the distributed source locally. Nothing enforced it. Every spoke
carries `is_master: false` in its MANIFEST, correctly stamped at distribution
time, and on 2026-08-17 a grep showed no hook, tool or test anywhere that reads
that field to refuse anything.

So the only thing standing between a spoke and a divergent private fork of the
harness was an agent remembering a paragraph. That is the mechanism this whole
codebase keeps learning is not a mechanism: the same night this was written, the
completion gate was found approving 23% of lugs without checking them, and the
test suite was found latching a live STOP on production. A rule nobody can
violate is worth more than a rule everybody agrees with.

WHAT DIVERGENCE ACTUALLY COSTS. A local edit to managed/** does not stay local.
The next `harness_upgrade` overwrites it from the master cut, so the spoke either
silently loses the fix or the operator hand-reconciles two histories. Meanwhile
the fix never reaches the other spokes that need it. Both outcomes are worse than
being told "no" at commit time.

THE ASYMMETRY THIS ENCODES, and it is the important part:

  - Editing a sibling's source        -> NEVER allowed. Refused here.
  - Delivering a lug to a sibling     -> ALWAYS allowed, never gated, never asked
                                         about. It is the sanctioned channel and
                                         the mechanism sovereignty REQUIRES.

They are opposites, not degrees. This gate blocks the first and points at the
second; it must never be extended to gate lug delivery.

USAGE
  master_authority_gate.py                 # gate the staged changeset (pre-commit)
  master_authority_gate.py --paths a b c   # gate an explicit list
  master_authority_gate.py --explain       # print this spoke's authority, exit 0
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Distributed source. An edit here is an edit to what every other spoke will run.
GUARDED_PREFIXES = (
    "WAI-Harness/spoke/managed/",
    "WAI-Harness/hub/managed/",
)

# Carve-outs inside managed/. These are per-spoke state that legitimately differs
# and is expected to move locally; gating them would block ordinary work and train
# people to reach for the override, which is how a gate dies.
ALLOWED_SUFFIXES = (
    ".gitkeep",
)
ALLOWED_SUBPATHS = (
    "/local/",          # anything explicitly namespaced local
)

OVERRIDE_ENV = "WAI_ALLOW_MANAGED_EDIT"


def repo_root(start: str = ".") -> Path:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=start,
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return Path(start).resolve()


def authority(root: Path):
    """(is_master, source) for this spoke.

    UNKNOWN IS NOT PERMISSION, but it is not refusal either. A missing or
    unreadable MANIFEST means we cannot tell whether this spoke authors the
    harness -- and a gate that blocks every commit on a repo it does not
    understand gets disabled within the hour. Report it and allow; the manifest
    integrity gate already covers a malformed cut.
    """
    mf = root / "WAI-Harness" / "spoke" / "managed" / "MANIFEST.json"
    if not mf.is_file():
        return None, f"no MANIFEST at {mf.relative_to(root) if mf.is_relative_to(root) else mf}"
    try:
        data = json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"MANIFEST unreadable ({exc})"
    if "is_master" not in data:
        return None, "MANIFEST carries no is_master field"
    return bool(data["is_master"]), "MANIFEST.is_master"


def staged_paths(root: Path):
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRD"],
            cwd=str(root), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"master-authority: cannot read the index ({exc})", file=sys.stderr)
        return []
    return [l.strip() for l in out.stdout.splitlines() if l.strip()]


def guarded(paths):
    hits = []
    for p in paths:
        norm = p.replace("\\", "/")
        if not norm.startswith(GUARDED_PREFIXES):
            continue
        if norm.endswith(ALLOWED_SUFFIXES):
            continue
        if any(sub in norm for sub in ALLOWED_SUBPATHS):
            continue
        hits.append(norm)
    return hits


def phone_home(root: Path) -> str:
    """Where the author lives.

    MANIFEST FIRST. The hub registry lives only on mywheel, so every spoke that
    needs this answer is the one place that cannot look it up -- measured, this
    printed a literal "<mywheel>" on minder. The cut now stamps `author` at build
    time and distribution preserves it, so the address travels with the payload.
    The registry stays as a fallback for cuts made before the stamp existed.
    """
    mf = root / "WAI-Harness" / "spoke" / "managed" / "MANIFEST.json"
    if mf.is_file():
        try:
            author = (json.loads(mf.read_text(encoding="utf-8")) or {}).get("author")
            if isinstance(author, dict) and author.get("inbox"):
                return str(author["inbox"]) + "/"
        except (OSError, json.JSONDecodeError):
            pass
    for reg in (root / "WAI-Harness" / "hub" / "local" / "hub-registry.json",
                root / "WAI-Harness" / "hub" / "hub-registry.json"):
        if not reg.is_file():
            continue
        try:
            data = json.loads(reg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for w in (data.get("wheels") or []):
            if str(w.get("wheel_id", "")).lower() in ("mywheel", "wai-mywheel"):
                p = w.get("path")
                if p:
                    return f"{p}/WAI-Harness/spoke/local/lugs/incoming/"
    return "<mywheel>/WAI-Harness/spoke/local/lugs/incoming/"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--paths", nargs="*", default=None,
                    help="explicit paths instead of the staged changeset")
    ap.add_argument("--root", default=".")
    ap.add_argument("--explain", action="store_true",
                    help="report this spoke's authority and exit 0")
    args = ap.parse_args(argv)

    root = repo_root(args.root)
    is_master, source = authority(root)

    if args.explain:
        label = {True: "MASTER — authors the harness",
                 False: "DISTRIBUTED — routes changes to the author",
                 None: "UNKNOWN"}[is_master]
        print(f"spoke   : {root}")
        print(f"authority: {label}  ({source})")
        print(f"author  : {phone_home(root)}")
        return 0

    if is_master is None:
        print(f"master-authority: cannot determine authority ({source}) — allowing",
              file=sys.stderr)
        return 0
    if is_master:
        return 0

    paths = args.paths if args.paths is not None else staged_paths(root)
    hits = guarded(paths)
    if not hits:
        return 0

    if os.environ.get(OVERRIDE_ENV):
        # Loud, never silent. An override that leaves no trace is indistinguishable
        # from no gate at all the next time someone audits why a spoke diverged.
        print(f"master-authority: OVERRIDDEN via {OVERRIDE_ENV} — "
              f"{len(hits)} distributed file(s) edited on a non-master spoke. "
              "This WILL be overwritten by the next harness upgrade.", file=sys.stderr)
        for h in hits[:10]:
            print(f"    {h}", file=sys.stderr)
        return 0

    print("", file=sys.stderr)
    print("master-authority: REFUSED — this spoke does not author the harness.",
          file=sys.stderr)
    print("", file=sys.stderr)
    print(f"  {len(hits)} distributed file(s) staged:", file=sys.stderr)
    for h in hits[:12]:
        print(f"    {h}", file=sys.stderr)
    if len(hits) > 12:
        print(f"    … and {len(hits) - 12} more", file=sys.stderr)
    print("", file=sys.stderr)
    print("  These files are distributed FROM the master. Editing them here means", file=sys.stderr)
    print("  the next harness upgrade silently overwrites your work, and no other", file=sys.stderr)
    print("  spoke ever receives it.", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Phone home instead — write a change-lug into:", file=sys.stderr)
    print(f"    {phone_home(root)}", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Delivering a lug to another spoke is ALWAYS allowed and never gated.", file=sys.stderr)
    print("  It is editing their source directly that is refused.", file=sys.stderr)
    print("", file=sys.stderr)
    print(f"  Genuinely need the local edit? {OVERRIDE_ENV}=1 git commit …", file=sys.stderr)
    print("", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
