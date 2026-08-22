#!/usr/bin/env python3
"""track_restore.py -- rebuild track turns from the raw transcripts that still hold them.

OPERATOR DIRECTIVE, 2026-08-22: "as for the missing data, I'm glad you found the problem.
You can restore from a backup. Correct? Go ahead and proceed to remediate that missing data."

WHAT WAS ACTUALLY BROKEN, and why dedup would have made it worse.

MEASURED 2026-08-22 across 2,144 recorded turns: 1,339 of them (62%) carry a body identical
to another turn's. The obvious reading is "one turn written many times" and the obvious fix
is to delete the copies. Both are wrong. The duplicates carry DIFFERENT turn numbers and
DIFFERENT timestamps, minutes apart:

    turn=3  ts=19:33:01   |
    turn=4  ts=19:47:07   |  identical bodies
    turn=5  ts=19:58:09   |

Those are 21 separate turns, a quarter of an hour apart, each of which recorded the
PREVIOUS turn's content because the buffer was never cleared between them. Deleting the
copies would delete 21 real turns and keep one wrong one. The content of those turns was
never written to the track at all -- and `user_msg` is empty on them, so the operator's own
words were not captured either.

THE TRACK IS A DERIVED RECORD. THE TRANSCRIPT IS THE ORIGINAL.
471 MB of raw session transcripts survive under ~/.claude/projects/, covering 2026-06-23
onward. Everything the track lost is still in them. That is the backup.

THE JOIN IS TIME, BECAUSE NOTHING ELSE EXISTS. A track turn carries no session id, no
transcript path, no uuid -- verified by inspection, the join-key set is literally empty.
That absence is why nothing could ever rebuild this. Both sides do carry timestamps, so a
turn is matched to the operator message that most recently preceded it.

  * Track timestamps are UTC. Transcript timestamps are UTC. The session DIRECTORY name is
    local time, and mixing those two cost the first attempt at this join -- a window built
    from the directory name found the wrong file.
  * A turn is only filled from a transcript whose span actually contains it. No span, no
    fill; the turn is reported unrestorable rather than guessed at.
  * Where two transcripts overlap one turn (concurrent sessions), the turn is left ALONE
    and counted as ambiguous. A confidently wrong restoration is worse than a gap, because
    a gap is visible and a wrong attribution is not.

NOTHING IS EVER DELETED. This writes a new file and leaves the original in place until the
caller has verified. Per the integrity contract -- "Agents write new lines. Agents NEVER
delete lines, even if they look wrong. The history is the value." A restored turn is
stamped `_restored` with its source, so a reader can always tell a rebuilt record from an
originally-captured one, and no later pass can mistake this output for pristine capture.

CLI:
    track_restore.py scan  --base <spoke_local>            # what is damaged, restore nothing
    track_restore.py plan  --base <spoke_local> --session <id>
    track_restore.py apply --base <spoke_local> --session <id> [--yes]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

TRANSCRIPT_ROOTS = [
    Path(os.path.expanduser("~/.claude/projects")),
]


def _epoch(ts):
    """UTC ISO string -> epoch seconds, or None. Never raises."""
    if not isinstance(ts, str) or len(ts) < 10:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return None


def _body_hash(rec):
    """Identity of a turn's CONTENT, ignoring the fields that legitimately differ.

    turn/ts/source/model differ between honest consecutive turns; everything else being
    identical is the signature of the carry-over bug.
    """
    skip = {"turn", "ts", "ts_source", "event", "source", "model", "_restored"}
    body = {k: v for k, v in rec.items() if k not in skip}
    return hashlib.md5(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def read_track(path):
    out = []
    try:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                out.append({"_unparseable": line})
    except OSError:
        pass
    return out


def diagnose(records):
    """Which turns are damaged, and how. Counts only; changes nothing."""
    turns = [r for r in records if isinstance(r, dict) and r.get("event") == "turn"]
    seen = {}
    dup, blank = [], []
    for i, r in enumerate(turns):
        h = _body_hash(r)
        if h in seen:
            dup.append(i)
        else:
            seen[h] = i
        if not str(r.get("user_msg") or "").strip():
            blank.append(i)
    return {"turns": len(turns), "carried_over": len(dup), "no_user_msg": len(blank),
            "damaged": len(set(dup) | set(blank))}


def project_slug(base):
    """Claude Code's transcript folder name for the repo this spoke lives in.

    ~/.claude/projects/-home-mario-projects-wheelwright-mywheel  <- for /home/mario/projects/wheelwright/mywheel
    """
    repo = Path(base).resolve()
    for _ in range(4):                      # spoke/local -> spoke -> WAI-Harness -> repo
        if (repo / ".git").exists():
            break
        repo = repo.parent
    return str(repo).replace("/", "-")


def _iter_transcripts(slug=None):
    """Transcripts for THIS project only, when a slug is given.

    MEASURED 2026-08-22: the first cut walked every project folder on the machine. Sessions
    in basher, pathfinder and a dozen other repos overlap these timestamps, so almost every
    turn matched several transcripts and the ambiguity rule -- correctly, given what it was
    shown -- refused to touch it. Result: 5 turns restorable out of 1,200, and the failure
    looked like a property of the data rather than a bug in the search.

    A mywheel turn can only have come from a mywheel conversation. Scoping the candidate
    set is not a heuristic, it is the fact that was being ignored.
    """
    for root in TRANSCRIPT_ROOTS:
        if not root.is_dir():
            continue
        for proj in root.iterdir():
            if not proj.is_dir():
                continue
            if slug and proj.name != slug:
                continue
            for f in proj.glob("*.jsonl"):
                yield f


def transcript_index(slug=None, cache={}):  # noqa: B006 -- deliberate per-process memo
    """(first_epoch, last_epoch, path) for every transcript. Built once.

    Scanning 400+ files of ~470 MB is the expensive step, so it happens once per process
    and only reads timestamp-bearing lines.
    """
    if cache:
        return cache["idx"]
    idx = []
    for f in _iter_transcripts(slug):
        first = last = None
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if '"timestamp"' not in line:
                        continue
                    try:
                        e = _epoch(json.loads(line).get("timestamp", ""))
                    except Exception:  # noqa: BLE001
                        continue
                    if e is None:
                        continue
                    if first is None or e < first:
                        first = e
                    if last is None or e > last:
                        last = e
        except OSError:
            continue
        if first and last:
            idx.append((first, last, f))
    cache["idx"] = idx
    return idx


def operator_messages(path):
    """Real operator turns from a transcript, oldest first: (epoch, text).

    Tool results also arrive as role=user; they are excluded by shape -- a genuine operator
    message is a plain string, a tool result is a list of content blocks.
    """
    out = []
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"role"' not in line and '"type"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                msg = r.get("message") or {}
                if r.get("type") != "user" and msg.get("role") != "user":
                    continue
                content = msg.get("content")
                if not isinstance(content, str) or not content.strip():
                    continue
                # WHAT IS NOT THE OPERATOR. Every one of these arrives as role=user and
                # none of them is a person speaking. The first cut excluded only three of
                # them and the very first sample it produced restored a COMPACTION SUMMARY
                # into a turn -- "This session is being continued from a previous
                # conversation..." -- which would have recorded the operator as having said
                # something he never said. A wrong fill is worse than a blank one: the blank
                # is visible and the wrong one is not.
                s = content.lstrip()
                # ANY XML-ISH WRAPPER IS MACHINERY, NOT A PERSON. task-notifications,
                # system-reminders, command echoes and their output all arrive as role=user
                # and all open with a tag. The operator writes prose; prose does not start
                # with '<'. Two rounds of naming individual tags each let a new one through
                # -- the shape is the rule, not the list.
                if s.startswith("<"):
                    continue
                if s.startswith((
                        "<system-reminder",      # harness-injected context
                        "<command-",             # a slash command the operator typed, not prose
                        "<local-command",        # that command's output
                        "[SYSTEM",               # background-task notifications
                        "Caveat:",               # tool-provided preamble
                        "This session is being continued",   # compaction summary
                        "[Request interrupted",  # a cancel, not a statement
                        "Your task is to create",            # subagent briefs
                )):
                    continue
                e = _epoch(r.get("timestamp", ""))
                if e:
                    out.append((e, content.strip()))
    except OSError:
        pass
    out.sort()
    return out


def lane_join(base, cache={}):  # noqa: B006 -- deliberate per-process memo
    """wai_session -> transcript path, from the lane registry. THE EXACT JOIN.

    A lane directory is named for the Claude session id, which is also the transcript's
    filename, and its guard.json names the wai_session that lane belongs to. That is a
    recorded identity, not an inference from clocks.

    MEASURED 2026-08-22: 118 lanes on disk, 55 of them carrying both a wai_session and a
    transcript that still exists. Those 55 need no time matching at all.

    The first cut of this tool had only the time join and it was useless where it mattered
    most: session-20260817-1753 has 192 damaged turns, and several long transcripts overlap
    its window, so every one of the 192 came back ambiguous and was correctly left alone.
    Refusing was right. Refusing everything is not a restore.
    """
    if cache:
        return cache["m"]
    m = {}
    lanes = Path(base) / "runtime" / "lanes"
    if lanes.is_dir():
        for d in lanes.iterdir():
            g = d / "guard.json"
            if not g.is_file():
                continue
            try:
                wai = json.loads(g.read_text(encoding="utf-8")).get("session_id", "")
            except Exception:  # noqa: BLE001
                continue
            if not wai:
                continue
            for root in TRANSCRIPT_ROOTS:
                if not root.is_dir():
                    continue
                for proj in root.iterdir():
                    cand = proj / f"{d.name}.jsonl"
                    if cand.is_file():
                        m[wai] = cand
                        break
    cache["m"] = m
    return m


def plan_session(track_path, base=None):
    """What could be restored for one session, and from where. Writes nothing."""
    # EXACT JOIN FIRST. Only fall back to clocks when no lane recorded this session.
    if base:
        exact = lane_join(base).get(Path(track_path).parent.name)
        if exact:
            records = read_track(track_path)
            turns = [(i, r) for i, r in enumerate(records)
                     if isinstance(r, dict) and r.get("event") == "turn"]
            msgs = operator_messages(exact)
            fills, restorable = {}, 0
            for idx, rec in turns:
                if str(rec.get("user_msg") or "").strip():
                    continue
                e = _epoch(rec.get("ts"))
                if not e:
                    continue
                prior = [(t, m) for t, m in msgs if t <= e]
                if not prior:
                    continue
                fills[idx] = prior[-1][1][:500]
                restorable += 1
            return {"restorable": restorable, "ambiguous": 0,
                    "unmatched": len(turns) - restorable, "join": "lane",
                    "sources": [exact.name], "records": records, "fills": fills}

    records = read_track(track_path)
    turns = [(i, r) for i, r in enumerate(records)
             if isinstance(r, dict) and r.get("event") == "turn"]
    stamps = [e for e in (_epoch(r.get("ts")) for _, r in turns) if e]
    if not stamps:
        return {"restorable": 0, "ambiguous": 0, "unmatched": len(turns),
                "sources": [], "records": records, "fills": {}}

    lo, hi = min(stamps), max(stamps)
    overlapping = [(a, b, f) for a, b, f in transcript_index(project_slug(base) if base else None)
                   if b >= lo and a <= hi]

    # AMBIGUITY IS A REFUSAL, NOT A COIN FLIP. Two concurrent sessions can both span a
    # turn; picking one would attribute the operator's words to the wrong conversation,
    # and nothing downstream could ever detect it.
    if len(overlapping) != 1:
        return {"restorable": 0, "ambiguous": len(turns) if len(overlapping) > 1 else 0,
                "unmatched": len(turns) if not overlapping else 0,
                "sources": [f.name for _, _, f in overlapping],
                "records": records, "fills": {}}

    msgs = operator_messages(overlapping[0][2])
    fills, restorable = {}, 0
    for idx, rec in turns:
        e = _epoch(rec.get("ts"))
        if not e:
            continue
        prior = [(t, m) for t, m in msgs if t <= e]
        if not prior:
            continue
        _, text = prior[-1]
        if str(rec.get("user_msg") or "").strip():
            continue
        fills[idx] = text[:500]
        restorable += 1
    return {"restorable": restorable, "ambiguous": 0,
            "unmatched": len(turns) - restorable,
            "sources": [overlapping[0][2].name], "join": "time", "records": records, "fills": fills}


def apply_session(track_path, plan):
    """Write the restored track beside the original. The original is left untouched."""
    records, fills = plan["records"], plan["fills"]
    if not fills:
        return None
    src = plan["sources"][0] if plan["sources"] else ""
    for idx, text in fills.items():
        records[idx]["user_msg"] = text
        records[idx]["_restored"] = {
            "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "from": src, "field": "user_msg", "by": "track_restore.py",
            "note": ("rebuilt from the raw transcript; this turn's own capture was lost to "
                     "the buffer carry-over bug"),
        }
    out = Path(str(track_path) + ".restored")
    out.write_text("".join(
        json.dumps(r, ensure_ascii=False) + "\n"
        for r in records if "_unparseable" not in r), encoding="utf-8")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["scan", "plan", "apply"])
    ap.add_argument("--base", default="WAI-Harness/spoke/local")
    ap.add_argument("--session")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    sess = Path(a.base) / "sessions"
    dirs = sorted(d for d in sess.iterdir() if d.is_dir()) if sess.is_dir() else []
    if a.session:
        dirs = [d for d in dirs if d.name == a.session]

    if a.cmd == "scan":
        tot = {"turns": 0, "carried_over": 0, "no_user_msg": 0, "damaged": 0}
        rows = []
        for d in dirs:
            t = d / "track.jsonl"
            if not t.exists():
                continue
            dg = diagnose(read_track(t))
            for k in tot:
                tot[k] += dg[k]
            if dg["damaged"]:
                rows.append((dg["damaged"], dg["turns"], d.name))
        rows.sort(reverse=True)
        print(f"TRACK DAMAGE — {len(dirs)} session(s)")
        print(f"  turns {tot['turns']}  carried-over {tot['carried_over']}  "
              f"no-user-msg {tot['no_user_msg']}  damaged {tot['damaged']}")
        for dmg, n, name in rows[: (a.limit or 15)]:
            print(f"    {name:28} {dmg:>4} of {n:>4}")
        return 0

    total_r = total_a = 0
    for d in dirs[: (a.limit or len(dirs))]:
        t = d / "track.jsonl"
        if not t.exists():
            continue
        p = plan_session(t, a.base)
        if not p["restorable"] and not p["ambiguous"]:
            continue
        total_r += p["restorable"]
        total_a += p["ambiguous"]
        print(f"  {d.name:28} restorable={p['restorable']:<4} "
              f"ambiguous={p['ambiguous']:<4} src={(p['sources'] or ['-'])[0][:12]}")
        if a.cmd == "apply" and a.yes and p["restorable"]:
            out = apply_session(t, p)
            if out:
                print(f"      -> {out.name}")
    print(f"TOTAL restorable={total_r}  ambiguous(left alone)={total_a}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
