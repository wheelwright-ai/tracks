#!/usr/bin/env python3
"""tastegraph_harvest_check.py — no corpus retires unharvested.

THE CLASS THIS KILLS (s138, proven twice in one session): the good copy strands
on a dead path while the system silently reads the poor one. It happened to the
launcher (1790-line canon stranded vs 660-line fork live) and to the TasteGraph
itself (42 rich preferences dead-pathed vs 11 live). The knowledge-level variant
is a DEPRECATED REPO: its session tracks hold operator-voice history that nothing
will ever read again — unless it is harvested before the lights go out.

CONTRACT
  A *harvest receipt* records that a corpus's session tracks were mined for
  operator preferences: when, how many files, what came of it. Receipts live in
  the hub registry file (hub/local/tastegraph-harvests.json) — central, never in
  the harvested repo (a deprecated repo is never written to).

  check mode (default):
    HARD  every corpus flagged deprecated MUST hold a receipt        -> else RED
    HARD  a receipt goes STALE if the corpus grew new track files
          after the harvest (mtime of newest track > harvested_at)   -> else RED
    SOFT  active spokes without a receipt are listed as advisory.

  Exit 0 = all hard checks green. Exit 2 = a deprecated corpus is unharvested
  or stale — i.e. operator knowledge is about to strand. Loud, listed, lugable.

  record mode: append/update a receipt after a mining pass.

Wheelwright shape: receipts are data, the gate is mechanical, failure names the
work (harvest X), and the fix is a mining pass — never a bypass.
"""
import argparse, json, os, sys, datetime

DEFAULT_DEPRECATED = [
    # Known-retired repos superseded by mywheel (reference-deprecated-framework-hub-repos).
    "/home/mario/projects/wheelwright/framework",
    "/home/mario/projects/wheelwright/hub",
]
TRACK_GLOBS = ("WAI-Spoke/sessions", "WAI-Spoke/lanes", "WAI-Harness/spoke/local/sessions")


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def newest_track(repo: str):
    """(count, newest_mtime_iso|None) over every track.jsonl in the repo's session trees."""
    newest, count = 0.0, 0
    for sub in TRACK_GLOBS:
        base = os.path.join(repo, sub)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            if "/.worktrees/" in root:
                continue
            for f in files:
                if f == "track.jsonl":
                    p = os.path.join(root, f)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    if st.st_size > 0:
                        count += 1
                        newest = max(newest, st.st_mtime)
    return count, (_iso(newest) if count else None)


def load_registry(path: str) -> dict:
    if os.path.isfile(path):
        with open(path) as f:
            return json.load(f)
    return {"harvests": {}}


def cmd_record(args) -> int:
    reg = load_registry(args.registry)
    count, newest = newest_track(args.repo)
    reg["harvests"][args.repo] = {
        "repo": args.repo,
        "harvested_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "corpus_files": count,
        "corpus_newest_track": newest,
        "by": args.by,
        "candidates": args.candidates,
        "incorporated": args.incorporated,
        "note": args.note or "",
    }
    os.makedirs(os.path.dirname(args.registry), exist_ok=True)
    tmp = args.registry + ".tmp"
    with open(tmp, "w") as f:
        json.dump(reg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, args.registry)
    print(f"receipt recorded: {args.repo} ({count} files, {args.incorporated} incorporated)")
    return 0


def cmd_check(args) -> int:
    reg = load_registry(args.registry)
    harvests = reg.get("harvests", {})
    deprecated = list(args.deprecated or DEFAULT_DEPRECATED)
    red, advisories = [], []

    for repo in deprecated:
        if not os.path.isdir(repo):
            continue  # gone entirely — nothing left to strand
        count, newest = newest_track(repo)
        r = harvests.get(repo)
        if count == 0:
            continue
        if r is None:
            red.append(f"UNHARVESTED deprecated corpus: {repo} ({count} track files) — mine it, then `record` a receipt")
        elif newest and r.get("harvested_at", "") < newest:
            red.append(f"STALE receipt: {repo} grew tracks after harvest ({r.get('harvested_at')} < {newest}) — re-mine")

    # Advisory: registered active wheels without receipts (knowledge accrues unharvested).
    hub_reg = args.hub_registry
    if hub_reg and os.path.isfile(hub_reg):
        try:
            wheels = json.load(open(hub_reg)).get("wheels", [])
        except Exception:
            wheels = []
        for w in wheels:
            p = w.get("path")
            if p and os.path.isdir(p) and p not in harvests and p not in deprecated:
                c, _ = newest_track(p)
                if c:
                    advisories.append(f"advisory: active spoke never harvested: {p} ({c} track files)")

    for line in red:
        print(f"  RED  {line}")
    for line in advisories[: args.advisory_cap]:
        print(f"  ...  {line}")
    if len(advisories) > args.advisory_cap:
        print(f"  ...  (+{len(advisories) - args.advisory_cap} more advisory — cap announced, not silent)")
    if red:
        print(f"harvest_check: RED — {len(red)} deprecated corpus(es) with strandable operator knowledge")
        return 2
    print(f"harvest_check: GREEN — deprecated corpora harvested ({len(advisories)} advisory)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--registry", default="WAI-Harness/hub/local/tastegraph-harvests.json")
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check")
    c.add_argument("--deprecated", nargs="*", default=None)
    c.add_argument("--hub-registry", default="WAI-Harness/hub/local/hub-registry.json")
    c.add_argument("--advisory-cap", type=int, default=8)
    r = sub.add_parser("record")
    r.add_argument("--repo", required=True)
    r.add_argument("--by", required=True, help="session/agent that performed the mining")
    r.add_argument("--candidates", type=int, required=True)
    r.add_argument("--incorporated", type=int, required=True)
    r.add_argument("--note", default="")
    a = ap.parse_args(argv)
    if a.cmd == "record":
        return cmd_record(a)
    a.deprecated = getattr(a, "deprecated", None)
    a.hub_registry = getattr(a, "hub_registry", "WAI-Harness/hub/local/hub-registry.json")
    a.advisory_cap = getattr(a, "advisory_cap", 8)
    return cmd_check(a)


if __name__ == "__main__":
    sys.exit(main())
