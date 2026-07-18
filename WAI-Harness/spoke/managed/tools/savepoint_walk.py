#!/usr/bin/env python3
"""savepoint_walk.py — walk the savepoint trail and re-check whether work still holds.

THE OPERATOR'S FRAMING (s138). Savepoint `work_done` records what a session set
out to do and what it actually finished. That is a path of progress, and Ozi
should be able to walk back over it later and ask, per entry: is this still doing
what was intended, does it need revision, or has it been replaced? His words:
"much easier than historian reviews."

He is right that it is easier, and the reason is the same one behind every other
instrument added this session — a historian review asks a model for an opinion,
while a walk re-runs a check the work already declared about itself. No model
judges anything here.

WHAT THE FIRST WALK REVEALED, AND WHY IT IS REPORTED LOUDLY. Across 263 savepoints
there are 330 work_done entries. Exactly 8 carry a `verification` string. But 100
are marked `verified: true`. So roughly ninety entries assert they were verified
while recording no way to check it — the self-graded pattern this session spent
its time dismantling, sitting in the middle of the record Ozi is meant to trust.

This tool therefore refuses to treat `verified: true` as evidence. A claim without
a re-runnable check is UNCHECKABLE, and the summary reports that count first. A
walk that returned mostly STILL-HOLDS by believing the record would be worse than
no walk at all, because it would launder assertion into confirmation.

VERDICTS, per work_done entry:
    still-holds   the entry's own verification was re-run and passed
    drifted       the verification was re-run and FAILED — needs revision/replacement
    unchecked     a verification exists but was not run (needs --run-commands)
    uncheckable   no verification recorded; nothing to re-run. NOT a pass.
    unknowable    a check exists but CANNOT be evaluated here — a sibling spoke's
                  commit, or a path in a directory that drains by design. Neither
                  a pass nor drift; saying "drifted" would be confidently wrong.

Usage:
    savepoint_walk.py walk [--run-commands] [--json] [--limit N]
    savepoint_walk.py coverage          # how much of the trail is checkable at all
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys

SAVEPOINT_GLOB = "WAI-Harness/spoke/local/initiatives/savepoints/**/*.json"

# A verification is re-runnable when we can turn it into a machine check without
# interpreting prose. Anything else is honestly reported as uncheckable rather
# than guessed at — a wrong STILL-HOLDS is worse than an admitted gap.
_PYTEST_RE = re.compile(r"(python3? -m pytest[^\n;|&]*)")
_CMD_RE = re.compile(r"^\s*`?(python3? [^\n`]+|pytest [^\n`]+)`?\s*$")
_PATH_RE = re.compile(r"((?:WAI-Harness|tools|tests)/[\w./-]+\.(?:py|sh|json|md))")
_SHA_RE = re.compile(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")


def _classify(verification):
    """Turn a verification string into (kind, payload) or (None, None).

    Deliberately conservative. Prose like "confirmed by reading the diff" is a
    human note, not an oracle, and pretending otherwise is how a checker becomes
    theatre.
    """
    if not verification or not verification.strip():
        return None, None
    v = verification.strip()
    m = _PYTEST_RE.search(v) or _CMD_RE.match(v)
    if m:
        return "command", m.group(1).strip()
    m = _PATH_RE.search(v)
    if m:
        return "path", m.group(1)
    # A commit sha is deterministically checkable via ancestry, and the validator
    # already accepts one as evidence. The two MUST agree on what counts —
    # savepoint_backfill.py promotes shas out of legacy prose, and if the walker
    # could not check them those promotions would be inert: a verification field
    # that implies checkability and delivers none.
    m = _SHA_RE.search(v)
    if m:
        return "sha", m.group(0)
    return None, None


def _run_command(cmd, root, timeout=120):
    try:
        p = subprocess.run(cmd, shell=True, cwd=root, capture_output=True,
                           text=True, timeout=timeout)
        return p.returncode == 0, (p.stdout or p.stderr)[-200:]
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except OSError as e:
        return False, str(e)[:200]


def _resolve_path(root, rel):
    """Find a recorded path, tolerating the root it was written relative to.

    Sessions recorded paths from wherever they were standing, so the same file
    appears as "tools/x.py" and "WAI-Harness/spoke/managed/tools/x.py". Treating
    those as different files manufactured drift for work that never moved.
    Falling back to a basename match is deliberately last and still exact on the
    filename — it recovers the prefix, it does not guess at identity.
    """
    cands = [rel,
             os.path.join("WAI-Harness/spoke/managed", rel),
             os.path.join("WAI-Harness/spoke/local", rel)]
    for c in cands:
        p = os.path.join(root, c)
        if os.path.exists(p):
            return c
    base = os.path.basename(rel)
    for stem in ("WAI-Harness/spoke/managed/tools", "WAI-Harness/spoke/managed/tests",
                 "WAI-Harness/spoke/managed/.claude/commands"):
        p = os.path.join(root, stem, base)
        if os.path.exists(p):
            return os.path.join(stem, base)
    return None


def _check_entry(entry, root, run_commands):
    """Re-check ONE work_done entry. Returns a verdict dict; never mutates input."""
    what = (entry.get("what") or "")[:100]
    kind, payload = _classify(entry.get("verification"))

    if kind is None:
        return {"verdict": "uncheckable", "what": what,
                "why": "no re-runnable verification recorded",
                # Surfaced so the gap between claim and evidence is visible.
                "claimed_verified": entry.get("verified") is True,
                "reconstructed": entry.get("reconstructed") is True}

    if kind == "path":
        # TRIAGED s138, two distinct false positives fixed here.
        #
        # 1. Paths were recorded relative to whichever root the session happened
        #    to be standing in. "tools/resident_prompt.md" reported DRIFTED while
        #    the file sat safely at managed/tools/resident_prompt.md. The work was
        #    never lost; only the prefix differed.
        # 2. A lug that has LEFT lugs/incoming/ is normal lifecycle, not loss. One
        #    entry reported drift for a notice that had been correctly delivered to
        #    a sibling spoke and processed there — exactly the system working.
        found = _resolve_path(root, payload)
        if found:
            return {"verdict": "still-holds", "what": what, "check": f"exists: {found}",
                    "why": None,
                    "claimed_verified": entry.get("verified") is True,
                    "reconstructed": entry.get("reconstructed") is True}
        if "/lugs/incoming/" in payload:
            return {"verdict": "unknowable", "what": what, "check": f"exists: {payload}",
                    "why": "path is in lugs/incoming/, which DRAINS by design — absence is "
                           "normal lifecycle (processed, or delivered onward), not drift",
                    "claimed_verified": entry.get("verified") is True,
                    "reconstructed": entry.get("reconstructed") is True}
        return {"verdict": "drifted", "what": what, "check": f"exists: {payload}",
                "why": f"path no longer exists anywhere under this spoke: {payload}",
                "claimed_verified": entry.get("verified") is True,
                "reconstructed": entry.get("reconstructed") is True}

    if kind == "sha":
        # TRIAGED s138: the first run reported 3 shas as DRIFTED that simply do
        # not exist in this repository — they came from sibling spokes, whose
        # commits were never going to be ancestors here. "Not an ancestor" and
        # "not in this repo" are completely different facts, and collapsing them
        # produced three confident, specific, wrong findings. That is how an
        # audit tool teaches its reader to ignore it.
        known, _ = _run_command(f"git cat-file -e {payload}", root, timeout=20)
        if not known:
            return {"verdict": "unknowable", "what": what,
                    "check": f"commit {payload}",
                    "why": f"commit {payload} does not exist in this repository — it is "
                           "almost certainly a sibling spoke's commit. Not checkable HERE, "
                           "and not evidence of drift.",
                    "claimed_verified": entry.get("verified") is True,
                    "reconstructed": entry.get("reconstructed") is True}
        # It IS our commit, so ancestry is the real question: a commit that was
        # reverted or rebased away is genuine drift.
        ok, _ = _run_command(f"git merge-base --is-ancestor {payload} HEAD", root, timeout=20)
        return {"verdict": "still-holds" if ok else "drifted", "what": what,
                "check": f"commit {payload} is an ancestor of HEAD",
                "why": None if ok else f"commit {payload} exists here but is not an ancestor "
                                       "of HEAD (reverted or rebased away)",
                "claimed_verified": entry.get("verified") is True,
                "reconstructed": entry.get("reconstructed") is True}

    if not run_commands:
        return {"verdict": "unchecked", "what": what, "check": payload,
                "why": "command verification not run (pass --run-commands)",
                "claimed_verified": entry.get("verified") is True,
                "reconstructed": entry.get("reconstructed") is True}

    ok, out = _run_command(payload, root)
    return {"verdict": "still-holds" if ok else "drifted", "what": what,
            "check": payload, "why": None if ok else f"command failed: {out}",
            "claimed_verified": entry.get("verified") is True,
            "reconstructed": entry.get("reconstructed") is True}


def load_trail(root):
    """Every savepoint, oldest first — the path of progress in order."""
    out = []
    for path in glob.glob(os.path.join(root, SAVEPOINT_GLOB), recursive=True):
        try:
            d = json.load(open(path))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(d, dict):
            continue
        out.append((d.get("created_at") or "", path, d))
    out.sort(key=lambda t: t[0])
    return out


def walk(root, run_commands=False, limit=None):
    """READ-ONLY. Re-check each entry's own declared verification."""
    results = []
    counts = {"still-holds": 0, "drifted": 0, "unchecked": 0, "uncheckable": 0,
              "unknowable": 0}
    claimed_but_uncheckable = 0

    trail = load_trail(root)
    if limit:
        trail = trail[-limit:]

    for created, path, sp in trail:
        entries = sp.get("work_done") or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            r = _check_entry(entry, root, run_commands)
            r["savepoint"] = sp.get("id") or os.path.basename(path)
            r["created_at"] = created
            counts[r["verdict"]] += 1
            if r["verdict"] == "uncheckable" and r["claimed_verified"]:
                claimed_but_uncheckable += 1
            results.append(r)

    total = sum(counts.values())
    checkable = counts["still-holds"] + counts["drifted"]
    return {
        "ok": True,
        "savepoints": len(trail),
        "entries": total,
        "counts": counts,
        # The number that matters: how much of the trail can be checked at all.
        "checkable_ratio": round(checkable / total, 4) if total else 0.0,
        # The number that matters MORE: claims of verification with no evidence.
        "claimed_verified_but_uncheckable": claimed_but_uncheckable,
        "results": results,
    }


def cmd_walk(args, root):
    rep = walk(root, run_commands=args.run_commands, limit=args.limit)
    if args.json:
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return 0

    c = rep["counts"]
    print(f"SAVEPOINT TRAIL — {rep['savepoints']} savepoint(s), {rep['entries']} work entries")
    print(f"  still-holds {c['still-holds']}   drifted {c['drifted']}   "
          f"unchecked {c['unchecked']}   uncheckable {c['uncheckable']}   "
          f"unknowable {c['unknowable']}")
    print(f"  checkable: {rep['checkable_ratio']:.0%} of the trail")
    if rep["claimed_verified_but_uncheckable"]:
        print(f"\n  ** {rep['claimed_verified_but_uncheckable']} entries claim verified=true "
              f"with NO re-runnable check recorded.")
        print("     A claim is not evidence. These are counted as UNCHECKABLE, never as passes.")

    drifted = [r for r in rep["results"] if r["verdict"] == "drifted"]
    if drifted:
        print(f"\nDRIFTED ({len(drifted)}) — intended work that no longer verifies:")
        for r in drifted[:15]:
            print(f"  [{r['savepoint']}] {r['what']}")
            print(f"      {r['why']}")
    return 1 if drifted else 0


def cmd_coverage(args, root):
    rep = walk(root, run_commands=False)
    c = rep["counts"]
    checkable = c["still-holds"] + c["drifted"] + c["unchecked"]
    print(f"Trail coverage: {checkable}/{rep['entries']} entries carry a re-runnable check "
          f"({checkable / rep['entries']:.0%})" if rep["entries"] else "empty trail")
    print(f"Claims of verified=true with no check: {rep['claimed_verified_but_uncheckable']}")
    print("\nCoverage is a floor to raise by RECORDING verifications as work is done —")
    print("never by relaxing what counts as one. Backfill adds checks, not claims.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Walk the savepoint trail (read-only)")
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("walk")
    w.add_argument("--run-commands", action="store_true",
                   help="actually execute command verifications (slower, real)")
    w.add_argument("--json", action="store_true")
    w.add_argument("--limit", type=int, default=None, help="most recent N savepoints")
    sub.add_parser("coverage")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    return {"walk": cmd_walk, "coverage": cmd_coverage}[args.cmd](args, root)


if __name__ == "__main__":
    sys.exit(main())
