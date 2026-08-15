#!/usr/bin/env python3
"""lug_provenance_gate.py — a source change must be traceable to a lug.

WHY
---
The PathGraph indexes LUGS, not commit messages and not chat. Work that ships
without a lug is work nobody can later verify was intended, reviewed, or done —
it exists only as a diff and a memory of the session that produced it.

MEASURED session 140: of 8 commits touching managed/tools, managed/tests or
.githooks that day, 5 carried NO lug reference. Four were the agent's own,
including the entire H2/H4 interface-contract seam — the most consequential work
of the session, shipped with no canonical record at all. The operator's correction
was exact: "otherwise we cant verify its being maintained in the future. I
shouldnt need to tell you that."

Resolving to remember is not a mitigation. This is the mitigation.

WHAT COUNTS
-----------
A commit touching guarded source must EITHER name a lug id in its message
(`<type>-<slug>-v1`) OR stage a lug whose own `file_targets` NAME the changed
file — or be an explicitly-marked exempt class.

Co-staging alone is not provenance, and this distinction is load-bearing. The
first version of this gate accepted "a lug file is staged somewhere in this
commit", and `git add -A` sweeps unrelated lug churn into nearly every commit
here — so it passed 0421b2cd3, the very commit whose missing record prompted it.
A gate that would have permitted the thing it was written for is theatre. The
lug must claim the file.

Exempt, deliberately and narrowly:
  - revert commits (provenance belongs to what is being reverted)
  - merge commits (the merged commits carry their own)
  - a commit that stages ONLY lug JSON (the record IS the change)
  - mechanical manifest recuts staging only MANIFEST.json

The gate names the missing reference and prints the two ways to satisfy it. It
never invents a lug: a lug written to satisfy a gate is the placeholder-lug
anti-pattern this repo already prohibits.

Usage:
  python3 lug_provenance_gate.py --staged [--repo-root PATH]   # pre-commit
  python3 lug_provenance_gate.py --rev-range origin/main..HEAD # audit a range
Exit:
  0 = every guarded commit/staging is traceable
  1 = at least one is not
"""
import argparse
import os
import re
import subprocess
import sys

# Source whose change must be explainable later. Deliberately NOT everything:
# runtime state, session tracks and lug files themselves churn constantly and
# gating them would train people to bypass, which is how the manifest gate came
# to be skipped 14 times in one session.
GUARDED = (
    "WAI-Harness/spoke/managed/tools/",
    "WAI-Harness/spoke/managed/tests/",
    "WAI-Harness/spoke/managed/shared/",
    "WAI-Harness/hub/managed/tools/",
    ".githooks/",
    ".claude/hooks/",
)

LUG_RE = re.compile(r"\b(?:impl|implementation|bug|change|task|spec|feature|epic|notice)-[a-z0-9][a-z0-9-]*-v\d+\b")
LUG_PATH_RE = re.compile(r"/lugs/(?:bytype|incoming|outgoing)/")


def _git(repo_root, *args):
    try:
        return subprocess.run(["git", "-C", repo_root, *args],
                              capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def guarded_paths(paths):
    return [p for p in paths if any(p.startswith(g) for g in GUARDED)]


def _is_exempt(paths, message):
    """Narrow, explicit exemptions. Anything else must carry a reference."""
    if message.startswith("Revert ") or message.startswith("Merge "):
        return "revert/merge — provenance belongs to the underlying commits"
    non_lug = [p for p in paths if not LUG_PATH_RE.search(p)]
    if paths and not non_lug:
        return "stages only lug records — the record IS the change"
    if non_lug and all(os.path.basename(p) == "MANIFEST.json" for p in non_lug):
        return "mechanical manifest recut"
    return None


def _covered_by_staged_lugs(repo_root, guarded, staged_paths):
    """Which guarded paths a staged lug actually CLAIMS via its file_targets.

    Mere co-staging is NOT provenance. `git add -A` sweeps unrelated lug churn
    into almost every commit in this repo, so "a lug file is staged" would pass
    essentially everything — including 0421b2cd3, the very commit whose missing
    record prompted this gate. The link has to be the lug naming the file.
    """
    import json
    claimed = set()
    for p in staged_paths:
        if not LUG_PATH_RE.search(p) or not p.endswith(".json"):
            continue
        full = os.path.join(repo_root, p)
        try:
            with open(full) as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            continue
        targets = d.get("file_targets") or d.get("target_files") or []
        if isinstance(targets, str):
            targets = [targets]
        for t in targets:
            if isinstance(t, str):
                claimed.add(t.strip().lstrip("./"))
    return {g for g in guarded if g.lstrip("./") in claimed}


def check_staged(repo_root):
    paths = [p for p in _git(repo_root, "diff", "--cached", "--name-only",
                             "--diff-filter=ACMR").splitlines() if p.strip()]
    guarded = guarded_paths(paths)
    if not guarded:
        return []
    uncovered = sorted(set(guarded) - _covered_by_staged_lugs(repo_root, guarded, paths))
    if not uncovered:
        return []
    return [("<staged>", uncovered)]


def check_range(repo_root, rev_range):
    out = _git(repo_root, "log", "--format=%H", rev_range)
    failures = []
    for sha in [s for s in out.splitlines() if s.strip()]:
        paths = [p for p in _git(repo_root, "show", "--name-only", "--format=", sha)
                 .splitlines() if p.strip()]
        guarded = guarded_paths(paths)
        if not guarded:
            continue
        message = _git(repo_root, "show", "-s", "--format=%B", sha)
        if _is_exempt(paths, message.strip()):
            continue
        if LUG_RE.search(message):
            continue
        # Same rule as --staged: a co-committed lug counts only if it CLAIMS the
        # file. Co-presence is not provenance -- see _covered_by_staged_lugs.
        uncovered = sorted(set(guarded) - _covered_by_staged_lugs(repo_root, guarded, paths))
        if not uncovered:
            continue
        failures.append((sha[:9], uncovered))
    return failures


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--staged", action="store_true", help="check the staged set (pre-commit)")
    ap.add_argument("--rev-range", help="audit a commit range, e.g. origin/main..HEAD")
    args = ap.parse_args(argv)

    if not args.staged and not args.rev_range:
        ap.error("pass --staged or --rev-range")

    failures = (check_staged(args.repo_root) if args.staged
                else check_range(args.repo_root, args.rev_range))
    if not failures:
        return 0

    print(f"lug_provenance_gate: {len(failures)} change(s) to guarded source with no lug")
    for ref, paths in failures:
        print(f"  {ref}")
        for p in paths[:5]:
            print(f"      {p}")
        if len(paths) > 5:
            print(f"      ... and {len(paths) - 5} more")
    print()
    print("The PathGraph indexes lugs, not commit messages. Untraceable work cannot")
    print("be verified later as intended, reviewed, or done.")
    print()
    # The message escape is real but UNREACHABLE in --staged mode: pre-commit runs
    # before a commit object exists, so there is no message to read. The old hint
    # offered it anyway, and a session that took the advice hit the same refusal
    # twice with the lug id sitting in the message it had just written. Telling
    # someone to do something the tool cannot honour is worse than saying nothing.
    if any(ref == "<staged>" for ref, _ in failures):
        print("At COMMIT time there is only ONE fix — a lug is not enough; the lug")
        print("must CLAIM the file. Add each path above to that lug's file_targets:")
        print()
        print("  \"file_targets\": [ ..., \"<the path above>\" ]")
        print()
        print("(Naming a lug id in the commit message works on a RANGE check, not")
        print(" here: pre-commit runs before the message exists, so it cannot be read.)")
    else:
        print("Satisfy this by EITHER:")
        print("  1. staging a lug whose file_targets NAME the changed file, or")
        print("  2. naming an existing lug id in the commit message (e.g. impl-foo-v1)")
    print()
    print("Do NOT write a lug to satisfy this gate. A lug authored to clear a check")
    print("is the placeholder-lug anti-pattern; write the record you actually mean.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
