#!/usr/bin/env python3
"""dead_end_scan.py — the no-loose-ends gate (initiative-no-dead-ends-v1 +
initiative-optimize-ceremonies-v1 P3).

A "dead-end" is work with no durable home and no tracked disposition. This scans a
repo for the classes that bit us in practice and reports them so a ceremony can
BLOCK (savepoint/closeout) or SURFACE (wakeup) rather than let work silently strand.

Classes detected (per repo / worktree):
  - uncommitted        tracked files modified/deleted but not committed
  - untracked_source   untracked, non-gitignored SOURCE files (*.py/.sh/.md/.js/.ts/
                       .json/.yaml/.sql/...) that exist in no ref — the orphan-source
                       dead-end (lives only in a working tree / stash)
  - unpushed           commits on the current branch ahead of its upstream (or, if no
                       upstream, ahead of origin/main) — reunified-but-unpublished
  - stashes            git stashes (off-history; a stash without a tracking lug is a
                       dead-end by definition)
  - branches_ahead     local session/* branches with commits not in main (stranded
                       branch work — the reunification class; informational at session
                       scope, actionable at fleet scope)

`clean` is True when the SESSION-scope classes (uncommitted, untracked_source,
unpushed, stashes) are all empty. branches_ahead is reported but does not by itself
fail the session gate (it is a fleet/reunification concern).

CLI:
  python3 dead_end_scan.py [--root .] [--json] [--scope session|fleet]
Exit: 0 clean | 1 dead-ends found | 2 error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

SOURCE_EXT = (
    ".py", ".sh", ".bash", ".js", ".ts", ".jsx", ".tsx", ".md", ".json", ".jsonl",
    ".yaml", ".yml", ".sql", ".toml", ".rb", ".go", ".rs", ".css", ".html",
)


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def _is_repo(root):
    return _git(root, "rev-parse", "--is-inside-work-tree").returncode == 0


def scan(root=".", scope="session") -> dict:
    if not _is_repo(root):
        return {"ok": False, "error": f"not a git repo: {root}"}

    uncommitted, untracked_source = [], []
    st = _git(root, "status", "--porcelain").stdout.splitlines()
    for line in st:
        if not line.strip():
            continue
        code, path = line[:2], line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[-1].strip()
        if code == "??":
            if any(path.endswith(e) for e in SOURCE_EXT):
                untracked_source.append(path)
        else:
            uncommitted.append(path)

    # unpushed: ahead of upstream, else ahead of origin/main
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    upstream = _git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip()
    ref = upstream if upstream and "fatal" not in upstream else "origin/main"
    cnt = _git(root, "rev-list", "--count", f"{ref}..HEAD").stdout.strip()
    unpushed = int(cnt) if cnt.isdigit() else 0

    stashes = [s for s in _git(root, "stash", "list").stdout.splitlines() if s.strip()]

    branches_ahead = []
    if scope == "fleet" or True:  # cheap; always compute (session scope just won't gate on it)
        # CANON IS origin/main, NOT the local ref. A session that lands work with
        # `git push HEAD:main` (the CSRP-safe way — it touches no other lane's
        # working tree) never moves the LOCAL main pointer, so local main drifts
        # behind and every `main..branch` count is measured against a stale ref.
        # Observed 2026-07-30: local main sat 13 commits behind origin/main and the
        # scan reported two branches "ahead" that were both fully merged. Fall back
        # to local main only when there is no remote to compare against.
        canon = "origin/main"
        if _git(root, "rev-parse", "--verify", canon).returncode != 0:
            canon = "main"
        for b in _git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads/").stdout.splitlines():
            b = b.strip()
            if not b or b == "main":
                continue
            ahead = _git(root, "rev-list", "--count", f"{canon}..{b}").stdout.strip()
            if ahead.isdigit() and int(ahead) > 0:
                branches_ahead.append({"branch": b, "ahead": int(ahead)})

    session_dead_ends = bool(uncommitted or untracked_source or unpushed or stashes)
    clean = not session_dead_ends

    # LANDING, from the one shared definition (landing.LANDED_DEFINITION).
    # This tool reported clean:true on 2026-07-30 for a session with 17 pushed
    # commits, none of which were on main -- "clean" answered a narrower question
    # than the reader assumed. `clean` deliberately still means "no stranded
    # session work", because a CSRP lane is legitimately ahead of canon mid-flight
    # and gating on that would fail every concurrent session. What changes is that
    # the report now SAYS where the work stands, so clean can never be silently
    # read as landed.
    landing_report = None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import landing as _landing
        landing_report = _landing.landing_status(root)
        landing_report["describe"] = _landing.describe(landing_report)
    except Exception as e:  # noqa: BLE001 -- never crash the scan over this
        landing_report = {"state": "unknown", "landed": False,
                          "describe": "landing UNKNOWN — probe failed: %s" % e}

    return {
        "ok": True, "clean": clean, "scope": scope, "branch": branch,
        "uncommitted": uncommitted,
        "untracked_source": untracked_source,
        "unpushed": unpushed,
        "stashes": stashes,
        "branches_ahead": branches_ahead,
        "landing": landing_report,
        "summary": (f"{len(uncommitted)} uncommitted, {len(untracked_source)} untracked-source, "
                    f"{unpushed} unpushed, {len(stashes)} stash(es), "
                    f"{len(branches_ahead)} branch(es) ahead of main"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Scan for dead-end work (no-loose-ends gate).")
    ap.add_argument("--root", default=".")
    ap.add_argument("--scope", choices=["session", "fleet"], default="session")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rep = scan(args.root, scope=args.scope)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0 if rep.get("clean") else (2 if "error" in rep else 1)
    if "error" in rep:
        print(f"dead_end_scan: ERROR — {rep['error']}", file=sys.stderr)
        return 2
    _land = rep.get("landing") or {}
    if rep["clean"]:
        # CLEAN is about stranded session work only. Saying so alongside the
        # landing state stops a reader taking one for the other, which is the
        # exact misreading that let 17 pushed-but-unlanded commits pass.
        print(f"no dead-ends: CLEAN — {rep['summary']}")
        print(f"  landing: {_land.get('describe', 'unknown')}")
        if not _land.get("landed"):
            print("  (CLEAN means no stranded session work — it does NOT mean landed on canon)")
        if rep["branches_ahead"]:
            print(f"  (note: {len(rep['branches_ahead'])} branch(es) ahead of main — fleet reunification, not a session blocker)")
        return 0
    print(f"DEAD-ENDS FOUND — {rep['summary']}")
    print(f"  landing: {_land.get('describe', 'unknown')}")
    for p in rep["uncommitted"]:
        print(f"  [uncommitted]      {p}")
    for p in rep["untracked_source"]:
        print(f"  [untracked-source] {p}  (orphan — commit, lug, or discard-with-reason)")
    if rep["unpushed"]:
        print(f"  [unpushed]         {rep['unpushed']} commit(s) ahead of {rep['branch']} upstream")
    for s in rep["stashes"]:
        print(f"  [stash]            {s}  (pair with a tracking lug or drop)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
