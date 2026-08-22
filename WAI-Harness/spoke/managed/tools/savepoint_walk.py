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
    savepoint_walk.py close [--dry-run] # complete pending savepoints that still hold

A savepoint had no TERMINAL state in practice until `close` existed. Measured on
basher 2026-08-01: 120 savepoints on disk, 0 ever claimed, 22 pending named ones
going back to 2026-07-02. Nothing wrote claimed_at or completed_at, so the trail
only ever grew and the operator paid attention rent on it at every wakeup. `close`
completes a pending savepoint only when its own declared checks re-run and hold,
and refuses to close one that has no runnable check at all — closing on an absence
of evidence is the self-graded pattern this whole tool exists to kill.
"""

import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

SAVEPOINT_GLOB = "WAI-Harness/spoke/local/initiatives/savepoints/**/*.json"

# A verification is re-runnable when we can turn it into a machine check without
# interpreting prose. Anything else is honestly reported as uncheckable rather
# than guessed at — a wrong STILL-HOLDS is worse than an admitted gap.
#
# TRIAGED (assurance-trail-unevidenced-2f9c4dd6-v1): this classifier disagreed
# with validate_savepoint.py's _has_rerunnable_check on what counts — the
# validator already accepts bash/sh commands, any tests/tools/scripts/WAI-Harness
# path extension, but this walker only recognized python/pytest and a 4-extension
# allowlist with no "scripts/" prefix. That gap silently reported real, already
# write-time-validated evidence as UNCHECKABLE. The two MUST agree (same argument
# the sha comment below already makes) — 23 of 48 false "uncheckable" verdicts
# were entries like "bash tests/test_x.bash  (T39/T40; 40/40 pass)" that the
# validator had already accepted and this walker alone refused to re-run.
# ONE grammar, two tools — imported from validate_savepoint, never redefined here.
# That divergence is exactly what produced the 23/48 false "uncheckable" verdicts
# described above; keeping a second copy in this file would guarantee it recurs.
try:
    from validate_savepoint import (RERUNNABLE_VERBS, SOURCE_ROOTS, SHA_PATTERN,
                                    extract_command)
    from thread_landing import screen_command
except ImportError:  # pragma: no cover — same-dir import, as lug_gate does with wai_assurance
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from validate_savepoint import (RERUNNABLE_VERBS, SOURCE_ROOTS, SHA_PATTERN,
                                    extract_command)
    from thread_landing import screen_command

# The find-truncate-PARSE grammar now lives in validate_savepoint.extract_command,
# imported above. It used to be three regexes here, and two of them leaked prose into
# the string this module runs: _PYTEST_RE's charset excluded ; | & but not '(', so
# `pytest -q x.py  (17 passed)` was captured WHOLE — and it ran BEFORE the bounded
# pattern that would have handled it correctly. The anchored whole-field pattern had
# the same flaw by design ("only safe when the ENTIRE field is nothing but the
# command") with nothing checking that precondition. Result: 19 of this spoke's 43
# drifted verdicts were unparseable strings reported as regressed work.
_PATH_RE = re.compile(r"((?:%s)/[\w./-]+\.\w+)" % SOURCE_ROOTS)
_SHA_RE = re.compile(SHA_PATTERN)


def _classify(verification):
    """Turn a verification string into (kind, payload) or (None, None).

    Deliberately conservative. Prose like "confirmed by reading the diff" is a
    human note, not an oracle, and pretending otherwise is how a checker becomes
    theatre.
    """
    if not verification or not verification.strip():
        return None, None
    v = verification.strip()
    # ONE grammar, two tools — find, strip the trailing result annotation, and
    # require that bash can PARSE what is left. A string that is not a command is
    # prose: it must fall through to "uncheckable" (honest, prompts a backfill),
    # never be run and reported as "drifted" (which sends someone to re-do
    # finished work).
    cmd = extract_command(v)
    if cmd:
        return "command", cmd
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
        # BASH, not the platform /bin/sh. shell=True defaults to /bin/sh, which is
        # dash on Debian/Ubuntu — so a recorded verification using bash syntax
        # (process substitution, `[[ ]]`, arrays, `(( ))`) dies with a parse error
        # and the walk reports the WORK as DRIFTED.
        #
        # HONEST SCOPE (corrected after measuring, 2026-08-01): this reclaimed zero
        # entries on basher. The 8 verdicts first blamed on the dash dialect were
        # really malformed verification strings — `pytest -q x.py  (17 passed)` —
        # whose trailing '(' is a syntax error under BOTH shells; dash's wording
        # merely disguised it. That is fixed in extract_command, not here. This stays
        # because it is independently correct and keeps a bash verification recorded
        # tomorrow from being scored as drift.
        p = subprocess.run(cmd, shell=True, executable="/bin/bash", cwd=root,
                           capture_output=True, text=True, timeout=timeout)
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


DRAIN_REASON = ("references lugs/incoming/, which DRAINS by design — absence is normal "
                "lifecycle (the lug was processed, or delivered onward), not drift. "
                "Assert on the DESTINATION the lug reaches, not on the mailbox it "
                "passes through.")


def _drains_by_design(text):
    """Does this check assert the presence of something in a directory that empties?

    A lug that has LEFT lugs/incoming/ is the system working. Asserting it is still
    there turns a peer spoke doing its job into a drift report against you.
    """
    return "/lugs/incoming/" in (text or "")


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
        if _drains_by_design(payload):
            return {"verdict": "unknowable", "what": what, "check": f"exists: {payload}",
                    "why": DRAIN_REASON,
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
        ok, _ = _run_command(f"git merge-base --is-ancestor {payload} HEAD", root, timeout=20)
        if ok:
            return {"verdict": "still-holds", "what": what,
                    "check": f"commit {payload} is an ancestor of HEAD", "why": None,
                    "claimed_verified": entry.get("verified") is True,
                    "reconstructed": entry.get("reconstructed") is True}
        # NOT AN ANCESTOR IS NOT DRIFT. This used to say "drifted (reverted or
        # rebased away)" — the same over-confidence the sibling-spoke case two
        # comments up was fixed for, made one step further along.
        #
        # A rebase, squash or cherry-pick relands the WORK under a NEW sha, leaving
        # the original commit in the repo and unreachable. Ancestry cannot tell those
        # apart from a revert. Proven on basher 2026-08-01: the trail reported
        # 9e36da62 (hub-currency) as drifted, and scripts/hub-currency.sh plus
        # tests/test_hub_currency.bash are both present in HEAD — salvaged by
        # e875d0ab. Re-doing that work on the trail's say-so would have duplicated it.
        #
        # So: unknowable, with the one cheap fact that helps a human decide — whether
        # the files the commit touched are still on disk. Recording a sha as evidence
        # is inherently fragile under history rewriting; a path or command check
        # survives it, and that is what a backfill should reach for.
        _, files = _run_command(
            f"git show --name-only --format= {payload}", root, timeout=20)
        names = [f for f in (files or "").split("\n") if f.strip()]
        present = [f for f in names if os.path.exists(os.path.join(root, f))]
        hint = (f"{len(present)}/{len(names)} of its files still exist" if names
                else "could not list its files")
        return {"verdict": "unknowable", "what": what,
                "check": f"commit {payload} is an ancestor of HEAD",
                "why": f"commit {payload} exists here but is not an ancestor of HEAD. That "
                       "is a rebase/squash/cherry-pick OR a revert — ancestry cannot tell "
                       f"them apart, so this is not evidence of drift ({hint}). Re-record "
                       "this entry with a path or command check, which survives history "
                       "rewriting.",
                "claimed_verified": entry.get("verified") is True,
                "reconstructed": entry.get("reconstructed") is True}

    # SAME DENY-LIST AS thread_landing, imported not copied — this module executes
    # recorded strings with shell=True in the REPO ROOT, and one of the verifications
    # actually on this trail is `tests/run.sh`, which thread_landing already refuses
    # because the full suite has a known fixture escape into the shared .git. An
    # auditor that corrupts the repo it is auditing is not an auditor. Reported, never
    # silently skipped, and never as "drifted" — nothing was checked, so the honest
    # verdict is unknowable.
    denied, reason = screen_command(payload)
    if denied:
        return {"verdict": "unknowable", "what": what, "check": payload,
                "why": f"{reason} — re-record this entry with a narrower check",
                "claimed_verified": entry.get("verified") is True,
                "reconstructed": entry.get("reconstructed") is True}

    if not run_commands:
        return {"verdict": "unchecked", "what": what, "check": payload,
                "why": "command verification not run (pass --run-commands)",
                "claimed_verified": entry.get("verified") is True,
                "reconstructed": entry.get("reconstructed") is True}

    ok, out = _run_command(payload, root)
    # The DRAIN-BY-DESIGN rule applies to commands too, not just bare paths. It lived
    # only in the path branch, and widening RERUNNABLE_VERBS to include `test`/`ls`
    # promoted `test -f .../lugs/incoming/X.json` from a path check into a command —
    # which silently walked it straight past the exemption. Caught by re-walking the
    # real trail after that change: several entries flipped to "drifted" purely
    # because the sibling spoke had PROCESSED the lug they asserted was delivered,
    # i.e. because the system worked. Same rule, one predicate, both branches.
    if not ok and _drains_by_design(payload):
        return {"verdict": "unknowable", "what": what, "check": payload,
                "why": DRAIN_REASON,
                "claimed_verified": entry.get("verified") is True,
                "reconstructed": entry.get("reconstructed") is True}
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


# ── Read-only walk cache ─────────────────────────────────────────────────────
# MEASURED 2026-08-21 (basher s126): the READ-ONLY walk is 2.29s of the 4.29s
# generate_wakeup_brief.py spends, and 2.09s of THAT is 295 subprocess forks —
# 223 of them `bash -n -c` inside validate_savepoint.shell_parses, deciding
# whether a recorded verification string is parseable. That answer is a pure
# function of the savepoint files, and those files do not change between two
# launches a minute apart. Every `wcl` paid the whole fork storm again.
#
# So the read-only report is memoised against a fingerprint of its own inputs:
# every savepoint's (relpath, mtime_ns, size), plus HEAD — because the path and
# sha branches of _check_entry read the TREE, not just the trail — plus the
# arguments and a schema tag, so a change to the checking logic invalidates
# every cache in the fleet by bumping one integer.
#
# THREE THINGS THIS DELIBERATELY DOES NOT DO.
# 1. It never caches run_commands=True. That path EXECUTES recorded commands;
#    a cached pass would be a claim of verification nobody re-ran, which is the
#    exact self-grading this module exists to refuse.
# 2. It fails OPEN in both directions: an unreadable, corrupt, or stale entry
#    walks for real, and an unwritable runtime dir just skips the write. A
#    broken cache costs latency, never a wrong verdict.
# 3. It carries a wall-clock TTL as well as the fingerprint, because an
#    UNCOMMITTED edit to the tree moves neither the savepoint mtimes nor HEAD.
#    The fingerprint catches every change to the trail; the TTL bounds how long
#    a working-tree change can hide behind an unchanged trail.
_CACHE_SCHEMA = 1
_CACHE_TTL_SEC = 1800
_CACHE_REL = "WAI-Harness/spoke/local/runtime/savepoint-walk-cache.json"


def _cache_path(root):
    return os.path.join(root, _CACHE_REL)


def _trail_fingerprint(root, limit):
    """Identity of everything the read-only walk reads. Cheap: stat, no parse."""
    parts = []
    for path in sorted(glob.glob(os.path.join(root, SAVEPOINT_GLOB), recursive=True)):
        try:
            st = os.stat(path)
        except OSError:
            continue
        parts.append("%s:%d:%d" % (os.path.relpath(path, root), st.st_mtime_ns, st.st_size))
    head = ""
    try:
        head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    key = "\n".join(parts) + "||" + head + "||" + repr((limit, _CACHE_SCHEMA))
    return hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()


def _cache_read(root, fp):
    try:
        with open(_cache_path(root), encoding="utf-8") as fh:
            blob = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(blob, dict) or blob.get("fingerprint") != fp:
        return None
    try:
        age = datetime.datetime.now().timestamp() - float(blob.get("written_at") or 0)
    except (TypeError, ValueError):
        return None
    if age < 0 or age > _CACHE_TTL_SEC:
        return None
    rep = blob.get("report")
    return rep if isinstance(rep, dict) and rep.get("ok") else None


def _cache_write(root, fp, report):
    path = _cache_path(root)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"fingerprint": fp,
                       "written_at": datetime.datetime.now().timestamp(),
                       "schema": _CACHE_SCHEMA,
                       "report": report}, fh)
        os.replace(tmp, path)
    except OSError:
        pass


def walk(root, run_commands=False, limit=None):
    """READ-ONLY. Re-check each entry's own declared verification."""
    # Only the non-executing walk is cacheable — see the note above _CACHE_SCHEMA.
    fp = None
    if not run_commands:
        fp = _trail_fingerprint(root, limit)
        hit = _cache_read(root, fp)
        if hit is not None:
            return hit
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
    report = {
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
    if fp is not None:
        _cache_write(root, fp, report)
    return report


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


def close_eligible(root, run_commands=True):
    """Which pending savepoints have EARNED completion, and why.

    A savepoint had no terminal state in practice. Measured on basher 2026-08-01:
    120 savepoints on disk, 0 ever claimed, 22 pending named ones going back to
    2026-07-02 — because nothing ever wrote claimed_at or completed_at. The trail
    only ever grew. The walk could already tell you a savepoint's work still holds;
    there was no way to act on that, so the list stayed a monotonically growing pile
    and the operator paid attention rent on it every wakeup.

    THE BAR, and why it is set here:
      - zero drifted entries          — an unresolved regression is not "done"
      - at least one CHECKABLE entry  — closing on an absence of evidence is the
                                        self-graded pattern the trail exists to kill
                                        ("claim is not evidence", validate_savepoint)
      - status is pending             — auto-ejects are pruned, not completed
    A savepoint that is all-prose therefore does NOT close. It needs a backfilled
    verification first, which is the honest outcome: the fix is to record a check,
    never to relax what counts as one.
    """
    rep = walk(root, run_commands=run_commands)
    by_sp = {}
    for r in rep["results"]:
        by_sp.setdefault(r["savepoint"], []).append(r)

    out = []
    for created, path, sp in load_trail(root):
        if sp.get("status") != "pending":
            continue
        sid = sp.get("id") or os.path.basename(path)
        rows = by_sp.get(sid, [])
        holds = sum(1 for r in rows if r["verdict"] == "still-holds")
        drifted = sum(1 for r in rows if r["verdict"] == "drifted")
        uncheckable = sum(1 for r in rows if r["verdict"] == "uncheckable")
        if drifted == 0 and holds > 0:
            reason = f"{holds} check(s) re-ran and still hold; 0 drifted"
            eligible = True
        elif drifted:
            reason = f"{drifted} check(s) DRIFTED — resolve or retire first"
            eligible = False
        else:
            reason = (f"no re-runnable check ({uncheckable} uncheckable) — "
                      "backfill a verification; do not close on prose")
            eligible = False
        out.append({"id": sid, "path": path, "eligible": eligible, "reason": reason,
                    "holds": holds, "drifted": drifted, "uncheckable": uncheckable})
    return out


def cmd_close(args, root):
    rows = close_eligible(root, run_commands=not args.no_run_commands)
    closed = 0
    for r in rows:
        mark = "CLOSE " if r["eligible"] else "keep  "
        print(f"  {mark} {r['id'][:62]:63} {r['reason']}")
        if not r["eligible"] or args.dry_run:
            continue
        try:
            with open(r["path"], encoding="utf-8") as fh:
                d = json.load(fh)
            d["status"] = "completed"
            d["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            # Record WHY it closed, so a later reader can audit the decision without
            # re-running the trail — and so "completed" never means "someone said so".
            d["completion_evidence"] = {
                "closed_by": "savepoint_walk close",
                "checks_rerun": r["holds"],
                "drifted": r["drifted"],
                "uncheckable": r["uncheckable"],
            }
            with open(r["path"], "w", encoding="utf-8") as fh:
                json.dump(d, fh, indent=1, ensure_ascii=False)
            closed += 1
        except (OSError, json.JSONDecodeError) as e:
            print(f"         ! could not write {r['path']}: {e}")
    verb = "would close" if args.dry_run else "closed"
    print(f"\n{verb} {closed if not args.dry_run else sum(1 for r in rows if r['eligible'])}"
          f" of {len(rows)} pending savepoint(s)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Walk the savepoint trail")
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("walk")
    w.add_argument("--run-commands", action="store_true",
                   help="actually execute command verifications (slower, real)")
    w.add_argument("--json", action="store_true")
    w.add_argument("--limit", type=int, default=None, help="most recent N savepoints")
    sub.add_parser("coverage")
    c = sub.add_parser("close", help="complete pending savepoints whose checks all still hold")
    c.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    c.add_argument("--no-run-commands", action="store_true",
                   help="skip executing command checks (path/sha checks only)")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    return {"walk": cmd_walk, "coverage": cmd_coverage, "close": cmd_close}[args.cmd](args, root)


if __name__ == "__main__":
    sys.exit(main())
