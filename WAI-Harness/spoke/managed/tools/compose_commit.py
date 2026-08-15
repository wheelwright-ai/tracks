#!/usr/bin/env python3
"""Compose a commit from git objects, without touching any working tree.

WHY THIS EXISTS
---------------
On 2026-08-01 this repo lost canon: the pre-push test suite, running with git's
exported GIT_DIR inherited, renamed a fixture branch onto main. The recovery then
hit the mirror-image problem — every obvious repair (`git checkout <sha> -- paths`,
`git read-tree -u --reset`, `git reset`) mutates a working tree, and other live
sessions were sharing that tree. Repairing one thing risked breaking another.

The way out was to stop needing a working tree at all. A commit is a tree, a set
of parents and a message; all three can be built from objects through a TEMPORARY
index. Nothing is checked out, nothing is overwritten, and concurrent worktrees
become irrelevant rather than dangerous.

That is the durable lesson: in a repo with concurrent sessions, routine commit
composition should never contend for a checkout. Use this instead of reaching for
checkout/reset in a tree you do not exclusively own.

WHAT IT DOES NOT DO
-------------------
It does not run tools that need files on disk (a MANIFEST recut, a formatter, a
test run). Those still need a working tree — but make it a FRESH one of your own
(`git worktree add`), which is additive and safe, rather than mutating a shared one.

USAGE
-----
    # start from a base tree, graft files from other commits, commit onto parents
    python3 compose_commit.py \
        --base 0c45a9aaf \
        --graft 4a57c9223:README.md \
        --graft 31a4f1b09:.githooks/pre-push \
        --parent 0c45a9aaf --parent 31a4f1b09 \
        --message "restore: reunite the real tip and the fix" \
        --ref refs/heads/session/my-restore

    # dry run: print the resulting tree sha and file count, write nothing
    python3 compose_commit.py --base X --graft Y:path --dry-run

Exit codes: 0 composed (or dry-run ok), 2 bad input, 3 git failure.
"""

import argparse
import os
import subprocess
import sys
import tempfile


def git(args, index=None, capture=True, check=True):
    env = dict(os.environ)
    if index:
        env["GIT_INDEX_FILE"] = index
    # Never let an inherited GIT_DIR decide which repo we operate on: that is the
    # exact failure this tool was written in response to.
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_QUARANTINE_PATH"):
        env.pop(var, None)
    r = subprocess.run(["git"] + args, env=env, check=False,
                       capture_output=capture, text=True)
    if check and r.returncode != 0:
        sys.stderr.write(f"git {' '.join(args)} failed: {r.stderr.strip()}\n")
        sys.exit(3)
    return r.stdout.strip() if capture else ""


def parse_graft(spec):
    if ":" not in spec:
        sys.stderr.write(f"--graft expects <commit>:<path>, got: {spec}\n")
        sys.exit(2)
    commit, path = spec.split(":", 1)
    return commit, path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True,
                    help="commit or tree whose tree is the starting point")
    ap.add_argument("--graft", action="append", default=[], metavar="COMMIT:PATH",
                    help="take PATH's blob from COMMIT and place it at PATH (repeatable)")
    ap.add_argument("--remove", action="append", default=[], metavar="PATH",
                    help="remove PATH from the composed tree (repeatable)")
    ap.add_argument("--parent", action="append", default=[], metavar="COMMIT",
                    help="parent of the new commit (repeatable; order is preserved)")
    ap.add_argument("--message", help="commit message (required unless --dry-run)")
    ap.add_argument("--ref", help="ref to point at the new commit, e.g. refs/heads/x")
    ap.add_argument("--dry-run", action="store_true",
                    help="compose the tree, report it, write no commit and move no ref")
    a = ap.parse_args()

    if not a.dry_run and not a.message:
        sys.stderr.write("--message is required unless --dry-run\n")
        sys.exit(2)

    fd, index = tempfile.mkstemp(prefix="compose-", suffix=".idx")
    os.close(fd)
    os.unlink(index)  # git wants to create it itself
    try:
        git(["read-tree", a.base], index=index)
        base_count = len(git(["ls-files"], index=index).splitlines())

        for spec in a.graft:
            commit, path = parse_graft(spec)
            blob = git(["rev-parse", f"{commit}:{path}"], index=index)
            listing = git(["ls-tree", commit, path], index=index)
            mode = listing.split()[0] if listing else "100644"
            git(["update-index", "--add", "--cacheinfo", f"{mode},{blob},{path}"],
                index=index)

        for path in a.remove:
            git(["update-index", "--force-remove", path], index=index)

        tree = git(["write-tree"], index=index)
        final_count = len(git(["ls-files"], index=index).splitlines())

        print(f"base:    {a.base}  ({base_count} files)")
        print(f"grafted: {len(a.graft)}   removed: {len(a.remove)}")
        print(f"tree:    {tree}  ({final_count} files)")

        if a.dry_run:
            print("dry-run: no commit written, no ref moved")
            return 0

        args = ["commit-tree", tree]
        for p in a.parent:
            args += ["-p", p]
        args += ["-m", a.message]
        commit = git(args, index=index)
        print(f"commit:  {commit}")

        if a.ref:
            git(["update-ref", a.ref, commit], index=index)
            print(f"ref:     {a.ref} -> {commit}")
        else:
            print("no --ref given; the commit is unreferenced until you point a ref at it")
        return 0
    finally:
        if os.path.exists(index):
            os.unlink(index)


if __name__ == "__main__":
    sys.exit(main())
