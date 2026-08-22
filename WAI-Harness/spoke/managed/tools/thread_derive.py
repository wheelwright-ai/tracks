#!/usr/bin/env python3
"""Derive the live threads of work from artifacts the agent already had to produce.

OPERATOR: "Every save is insurance and awareness for next session's agent to
comprehend. Ozi should automate the documentation of the various threads we are
developing at any particular time ensuring our insurance is real and not pretty
words."

THE MEASUREMENT THIS IS BUILT ON. Across 1,850 tracked turns on this spoke:

    user_intent   85%   written by a hook
    thinking      47%   asked of the agent
    action/focus/phase  47%

Zero turns where the agent supplied judgment and the mechanism had not already fired.
Meanwhile, of 56 commits in one session, 44 carried a reasoned body -- 711 lines of
explanation -- because a commit message is an artifact the work REQUIRES, not a
side-trip after it.

    Guidance and record must ride an artifact the agent already produces.
    Everything that asked for a separate artifact ran at 47%.
    Everything carried by the main output ran near 100%.

So this does not ask anyone to write threads. It reads what is already there:
commit bodies for the WHY, open lugs for the WHAT, and their intersection for what is
actually in flight right now.

WHAT A THREAD IS. Not a task and not a lug. A thread is a line of reasoning that is
still open -- something a returning agent would otherwise have to reconstruct from the
transcript. A lug says "do X". A thread says "we are mid-argument about X, here is
where it got to, here is what would settle it."

HONESTY RULES, because insurance that overstates itself is worse than none:
  * A thread with no evidence is not emitted. No inference from titles alone.
  * `confidence` is stated per thread and derives from how many independent sources
    agree, never from how plausible the summary reads.
  * A commit body is quoted, never paraphrased into something more confident than it
    was.

USAGE
  thread_derive.py                    # human-readable
  thread_derive.py --json             # for Ozi / the savepoint
  thread_derive.py --write            # persist to local/runtime/threads.json
  thread_derive.py --since <ref>      # default: last 120 commits (recency, not push state)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SPOKE_ROOT = TOOLS.parents[3]

DEFAULT_COMMITS = 120   # deep enough to span several sessions of reasoning

LUG_RE = re.compile(r"\b((?:impl|fix|bug|task|change|spec|seed|notice|ack|retire)-[a-z0-9-]+-v\d+)\b")
OPEN_STATES = {"open", "ready", "draft", "in_progress", "ready_for_recheck",
               "needs_attention", "blocked"}


def _git(root, *args):
    try:
        p = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                           text=True, timeout=120)
        return p.stdout if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _commits(root, since):
    """[(sha, subject, body)] newest first."""
    # RECENCY, NOT PUSH STATE. The first cut defaulted to origin/main..HEAD, which
    # meant every live thread vanished the instant the work was pushed -- measured on
    # this spoke: 1 thread found where there were seven open. Insurance that
    # disappears when you save is not insurance.
    #
    # A thread is live because its reasoning is recent and its lug is open, and
    # neither of those has anything to do with whether a remote has seen the commit.
    args = ["log", "--format=%H%x1f%s%x1f%b%x1e"]
    args += [since] if since else [f"-{DEFAULT_COMMITS}"]
    raw = _git(root, *args)
    out = []
    for rec in raw.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        parts = rec.split("\x1f")
        if len(parts) >= 3:
            out.append((parts[0], parts[1], parts[2]))
    return out



def _reasoning(body: str) -> str:
    """The first line that actually explains something.

    Taking line 0 verbatim produced `why: impl-portable-track-capture-v1` -- a bare
    lug id restated as an explanation. A returning agent reading that learns nothing,
    and worse, learns nothing while being shown a field labelled "why".
    """
    skip = ("Co-Authored-By", "Refs ", "Signed-off-by")
    for line in body.splitlines():
        t = line.strip()
        if not t or t.startswith(skip):
            continue
        if LUG_RE.fullmatch(t):          # a bare lug id is a label, not a reason
            continue
        if len(t) < 25:                  # headers, bullets, fragments
            continue
        return t
    return ""


def _lugs(root):
    out = {}
    for base in ("WAI-Harness/spoke/local/lugs/bytype", "WAI-Spoke/work"):
        p = Path(root) / base
        if not p.is_dir():
            continue
        for f in p.rglob("*.json"):
            if ".worktrees" in str(f):
                continue
            try:
                d = json.load(open(f, encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if isinstance(d, dict) and d.get("id"):
                out[d["id"]] = d
    return out


def derive(root: Path, since=None):
    commits = _commits(root, since)
    lugs = _lugs(root)

    # A thread is anchored on a lug that is STILL OPEN and has commit evidence, or on
    # a commit body that names an open question with no lug behind it yet. Anything
    # else is history, not a thread -- and history belongs in the changelog.
    by_lug = {}
    orphan_reasoning = []

    for sha, subj, body in commits:
        ids = set(LUG_RE.findall(subj + "\n" + body))
        touched_open = [i for i in ids if lugs.get(i, {}).get("status") in OPEN_STATES]
        if touched_open:
            for i in touched_open:
                by_lug.setdefault(i, []).append((sha[:9], subj, body))
        elif not ids and body.strip():
            # Reasoning with no lug attached. This is the shape of a decision made in
            # conversation and never recorded -- the thing the operator called
            # "conversations dying on the vine".
            orphan_reasoning.append((sha[:9], subj, body))

    threads = []
    for lug_id, evidence in by_lug.items():
        lug = lugs[lug_id]
        # The most recent body that actually discusses this lug, quoted not summarised.
        newest = evidence[0]
        quote = _reasoning(newest[2]) or "\n".join(
            l for l in newest[2].splitlines()
            if l.strip() and not l.startswith("Co-Authored-By"))[:300]
        threads.append({
            "thread": lug_id,
            "state": lug.get("status"),
            "what": lug.get("title") or lug.get("one_liner") or "",
            "open_question": lug.get("one_liner") or "",
            "blocked_by": lug.get("blocked_by") or [],
            "evidence_commits": [e[0] for e in evidence],
            "latest_reasoning": quote,
            "confidence": "high" if len(evidence) > 1 else "medium",
            "source": "open lug with commit evidence",
        })

    for sha, subj, body in orphan_reasoning[:8]:
        quote = "\n".join(l for l in body.splitlines()
                          if l.strip() and not l.startswith("Co-Authored-By"))[:700]
        threads.append({
            "thread": f"unlugged:{sha}",
            "state": "unrecorded",
            "what": subj,
            "open_question": "This reasoning has no lug behind it. If it still matters, "
                             "it needs one; if it does not, it is finished history.",
            "blocked_by": [],
            "evidence_commits": [sha],
            "latest_reasoning": quote,
            "confidence": "low",
            "source": "commit body with no lug reference",
        })

    threads.sort(key=lambda t: (t["state"] == "unrecorded", -len(t["evidence_commits"])))
    return threads


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(SPOKE_ROOT))
    ap.add_argument("--since")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write", action="store_true",
                    help="persist to spoke/local/runtime/threads.json")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    threads = derive(root, args.since)

    if args.write:
        dest = root / "WAI-Harness/spoke/local/runtime/threads.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(
            {"threads": threads, "count": len(threads),
             "_note": ("DERIVED, not authored. Built from commit bodies and open lugs "
                       "because those are artifacts the work already required. Nothing "
                       "here was asked of an agent as a separate step -- that channel "
                       "measured 47%.")},
            indent=1) + "\n", encoding="utf-8")
        print(f"thread_derive: {len(threads)} thread(s) -> {dest}", file=sys.stderr)

    if args.json:
        print(json.dumps({"threads": threads, "count": len(threads)}, indent=1))
        return 0

    if not threads:
        print("thread_derive: no live threads found. Either the work is closed out, or "
              "the commits carry no reasoning to derive from — check which before "
              "reading this as done.")
        return 0

    print(f"\nLIVE THREADS — {len(threads)}\n")
    for t in threads:
        print(f"[{t['state']}] {t['thread']}   ({t['confidence']} confidence)")
        if t["what"]:
            print(f"    {t['what']}")
        if t["blocked_by"]:
            print(f"    blocked by: {', '.join(t['blocked_by'])}")
        first = (t["latest_reasoning"].splitlines() or [""])[0]
        if first:
            print(f"    why: {first[:150]}")
        print(f"    commits: {', '.join(t['evidence_commits'][:5])}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
