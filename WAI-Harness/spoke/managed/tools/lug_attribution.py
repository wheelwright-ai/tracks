#!/usr/bin/env python3
"""lug_attribution.py -- who owned a lug, and did its completion ever reach canon.

THE CONTINUITY PROBLEM THIS EXISTS TO SOLVE (operator, 2026-08-08): "the continuity of work
should be a consideration so you can adapt when needed and avoid injecting isolated or
outdated code."

The v6 kernel now stamps session, model and commit on every unit of work it creates. That is
correct and it is ISOLATED: the kernel's work objects live in `.wai/`, while the estate this
project actually runs on is 2,739 lugs under `WAI-Harness/spoke/local/lugs/`. A brand-new
attribution system that only describes work created after today answers nothing about the
work already done -- which is precisely where "what was that agent trying to do" gets asked.

So this tool applies the kernel's two questions to the LIVE corpus:

    coverage   how much of the real corpus can be attributed at all
    backfill   derive attribution for the rest, from git, without inventing any
    landing    which COMPLETED lugs never reached canon

MEASURED BASELINE, 2026-08-08: 2,739 lugs, 1,778 (64.9%) carry any session tag. Of 1,402
completed lugs only 817 (58.3%) do. 585 completed lugs are unattributable.

INFERRED IS NEVER WRITTEN AS STATED. A derived owner goes to `origin_session_inferred`,
never to `origin_session`, and carries the method and the commit sha that produced it. The
whole failure this corpus demonstrates is confident values nobody can re-derive; a backfill
that laundered guesses into the stated field would add 585 more of them.

UNDERIVABLE IS COUNTED, NOT HIDDEN. A lug whose origin git cannot establish is left exactly
as it was and reported as a number. An honest unknown beats a fabricated owner.

WHY ONE GIT CALL AND NOT 2,739. `git log --follow` per file is minutes of work and the
reason this was never done. A single `git log --name-only` pass over the lug tree yields the
introducing commit for every path at once.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

# BOTH PATHS, ALWAYS. A v4-only spoke has no WAI-Spoke/ and a v3 spoke has no
# spoke/local/ -- naming one silently no-ops on half the fleet.
BASES = ("WAI-Harness/spoke/local", "WAI-Spoke")

STATED_FIELDS = ("origin_session", "created_by", "authored_by")
DONE_STATUSES = ("completed", "complete", "done")


def resolve_base(root: str) -> str:
    for candidate in BASES:
        if os.path.isdir(os.path.join(root, candidate, "lugs")):
            return candidate
    return BASES[0]


def git(root: str, *args, timeout: int = 180):
    try:
        result = subprocess.run(("git",) + args, cwd=root, capture_output=True,
                                text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    return result.returncode == 0, result.stdout


def lug_paths(root: str, base: str) -> list:
    """Every lug record, repo-relative. bytype/ only -- incoming/ is a queue, not the corpus."""
    top = os.path.join(root, base, "lugs", "bytype")
    out = []
    for dirpath, _dirs, files in os.walk(top):
        for name in files:
            if name.endswith(".json"):
                out.append(os.path.relpath(os.path.join(dirpath, name), root))
    return sorted(out)


def stated_owner(lug: dict) -> str:
    for field in STATED_FIELDS:
        value = lug.get(field)
        if value:
            return str(value)
    return ""


def read_lug(root: str, rel: str):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def introducing_commits(root: str, base: str) -> dict:
    """path -> (sha, unix_time) for the commit that ADDED each lug file.

    One pass, oldest-first, first writer wins. `--diff-filter=A` restricts the name list to
    additions so a later edit does not overwrite the origin -- the question is who created
    this, not who touched it last.
    """
    ok, out = git(root, "log", "--reverse", "--diff-filter=A", "--name-only",
                  "--format=@%H %ct", "--", os.path.join(base, "lugs"))
    if not ok:
        return {}
    found, sha, when = {}, "", 0
    for line in out.splitlines():
        if line.startswith("@"):
            parts = line[1:].split()
            sha, when = parts[0], int(parts[1]) if len(parts) > 1 else 0
        elif line.strip() and line not in found:
            found.setdefault(line.strip(), (sha, when))
    return found


def session_index(root: str, base: str) -> list:
    """(start_unix, session_id), oldest first, from the session directory names.

    The names are the only durable record of when a session existed; a track file's mtime
    moves when anything appends to it, which would attribute a lug to whichever session
    happened to be written most recently.
    """
    sessions_dir = os.path.join(root, base, "sessions")
    index = []
    if not os.path.isdir(sessions_dir):
        return index
    for name in os.listdir(sessions_dir):
        if not name.startswith("session-"):
            continue
        try:
            stamp = datetime.strptime(name[len("session-"):][:13], "%Y%m%d-%H%M")
        except ValueError:
            continue
        index.append((stamp.replace(tzinfo=timezone.utc).timestamp(), name))
    return sorted(index)


def session_at(index: list, when: int) -> str:
    """The session that was open at `when`: the newest one that had already started."""
    chosen = ""
    for start, name in index:
        if start <= when:
            chosen = name
        else:
            break
    return chosen


def _gap_hours(sessions: list, session: str, when: int):
    """Hours between the matched session opening and the commit that added the lug."""
    for start, name in sessions:
        if name == session:
            return round((when - start) / 3600.0, 1)
    return None


def _confidence(gap):
    """How far the inference reached, in words, so a reader need not do the arithmetic.

    The thresholds are declared rather than tuned: within a working day the matched session
    is almost certainly the one that wrote the lug; beyond three days the gap is wide enough
    that an unrecorded session could have existed, and the value is a lead to check.
    """
    if gap is None:
        return "unknown"
    if gap <= 12:
        return "strong"
    if gap <= 72:
        return "plausible"
    return "weak -- treat as a lead, not a fact"


def coverage(root: str) -> dict:
    base = resolve_base(root)
    paths = lug_paths(root, base)
    total = stated = done = done_stated = done_any = inferred = unreadable = 0
    for rel in paths:
        lug = read_lug(root, rel)
        if lug is None:
            unreadable += 1
            continue
        total += 1
        has_stated = bool(stated_owner(lug))
        has_inferred = bool(lug.get("origin_session_inferred"))
        stated += 1 if has_stated else 0
        inferred += 1 if has_inferred else 0
        if lug.get("status") in DONE_STATUSES:
            done += 1
            done_stated += 1 if has_stated else 0
            done_any += 1 if (has_stated or has_inferred) else 0
    return {
        "base": base, "lugs": total, "unreadable": unreadable,
        "stated": stated, "inferred": inferred,
        "attributed": stated + inferred,
        "coverage": round((stated + inferred) / total, 4) if total else None,
        "completed": done,
        # STATED AND ATTRIBUTABLE ARE REPORTED APART, and this is not pedantry: a backfill
        # moves the second and must never appear to move the first. Collapsing them would
        # let a run of inference look like a run of recovered fact.
        "completed_stated": done_stated,
        "completed_attributed": done_any,
        "completed_coverage": round(done_stated / done, 4) if done else None,
        "completed_attributed_coverage": round(done_any / done, 4) if done else None,
        "verdict": (f"{total} lugs, {stated + inferred} attributable "
                    f"({(stated + inferred) / total:.1%}); of {done} completed, "
                    f"{done_stated} stated ({done_stated / done:.1%}) and "
                    f"{done_any} attributable ({done_any / done:.1%})"
                    if total and done else "no lugs found"),
    }


def backfill(root: str, apply: bool = False) -> dict:
    """Derive attribution from git for lugs that carry none. Dry-run unless --apply."""
    base = resolve_base(root)
    commits = introducing_commits(root, base)
    sessions = session_index(root, base)
    if not commits:
        return {"error": "git produced no history for the lug tree; nothing can be derived",
                "derived": 0, "underivable": 0, "applied": False}

    derived, underivable, already, changes = 0, 0, 0, []
    for rel in lug_paths(root, base):
        lug = read_lug(root, rel)
        if lug is None:
            continue
        if stated_owner(lug) or lug.get("origin_session_inferred"):
            already += 1
            continue
        entry = commits.get(rel)
        session = session_at(sessions, entry[1]) if entry else ""
        if not session:
            # No introducing commit, or no session was open then. Left untouched on
            # purpose: an honest unknown beats a fabricated owner.
            underivable += 1
            continue
        derived += 1
        changes.append((rel, session, entry[0]))
        if apply:
            lug["origin_session_inferred"] = session
            lug["origin_inferred_by"] = {
                "method": ("the commit that ADDED this lug file, mapped to the most "
                           "recently opened session directory at that commit time"),
                "commit": entry[0],
                "commit_time": datetime.fromtimestamp(entry[1], timezone.utc).isoformat(),
                # HOW FAR THE INFERENCE REACHED. Spot-checked 2026-08-08: one lug's
                # introducing commit sat 1.7 days after its matched session opened. That
                # is still the best available answer -- no other session had started --
                # but a reader has to be able to see the reach rather than trust a bare
                # id. A small gap is near-certain; a large one is a lead, not a fact.
                "session_started_hours_before": _gap_hours(sessions, session, entry[1]),
                "confidence": _confidence(_gap_hours(sessions, session, entry[1])),
                "recheck": f"git log --diff-filter=A --format=%H -- {rel}",
                "at": datetime.now(timezone.utc).isoformat(),
            }
            with open(os.path.join(root, rel), "w", encoding="utf-8") as handle:
                json.dump(lug, handle, indent=2)

    return {
        "base": base, "applied": apply, "derived": derived,
        "underivable": underivable, "already_attributed": already,
        "sample": [{"lug": c[0], "session": c[1], "commit": c[2]} for c in changes[:5]],
        "verdict": (f"{derived} derivable, {underivable} underivable (left untouched), "
                    f"{already} already attributed"
                    + ("" if apply else " -- DRY RUN, nothing written")),
    }


def landing(root: str, canon: str = "origin/main") -> dict:
    """Completed lugs whose own record never reached canon.

    THE OPERATOR'S QUESTION over the real corpus: find done items that were never merged.
    The oracle is the lug record itself -- if the file marking work complete is not in
    canon's tree, then by this project's own definition of landed, the completion has not
    landed, whatever the status field says.

    This is a floor, not a ceiling: a lug present on canon may still describe code that is
    not. It is chosen because it is CHECKABLE with one git call, and a checkable floor beats
    an unfalsifiable estimate.
    """
    base = resolve_base(root)
    ok, out = git(root, "ls-tree", "-r", "--name-only", canon, "--",
                  os.path.join(base, "lugs"))
    if not ok:
        return {"error": f"canon ref {canon!r} does not resolve here", "state": "UNKNOWN"}
    on_canon = set(out.split("\n"))

    stranded = []
    checked = 0
    for rel in lug_paths(root, base):
        lug = read_lug(root, rel)
        if lug is None or lug.get("status") not in DONE_STATUSES:
            continue
        checked += 1
        if rel not in on_canon:
            stranded.append({
                "lug": lug.get("id", os.path.basename(rel)[:-5]),
                "path": rel,
                "title": lug.get("title", ""),
                "session": (stated_owner(lug) or lug.get("origin_session_inferred")
                            or "unresolved"),
            })
    return {
        "base": base, "canon": canon, "completed_checked": checked,
        "not_landed": stranded, "count": len(stranded),
        "ok": not stranded,
        "verdict": (f"{checked - len(stranded)}/{checked} completed lugs are on {canon}"
                    + (f"; {len(stranded)} DONE BUT NOT ON CANON" if stranded else "")),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=("coverage", "backfill", "landing"))
    parser.add_argument("--root", default=".")
    parser.add_argument("--apply", action="store_true", help="backfill: write the changes")
    parser.add_argument("--canon", default="origin/main")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)
    if args.command == "coverage":
        report = coverage(root)
    elif args.command == "backfill":
        report = backfill(root, args.apply)
    else:
        report = landing(root, args.canon)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(report.get("verdict") or report.get("error", ""))
        for row in report.get("not_landed", [])[:20]:
            print(f"  NOT ON CANON  {row['lug']:<52} {row['session']}")
        for row in report.get("sample", []):
            print(f"  {row['lug']}  ->  {row['session']}  ({row['commit'][:12]})")
    return 0 if report.get("ok", True) and "error" not in report else 1


if __name__ == "__main__":
    sys.exit(main())
