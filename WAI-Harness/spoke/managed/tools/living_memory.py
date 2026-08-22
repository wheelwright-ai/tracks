#!/usr/bin/env python3
"""Short-term memory that survives a compaction, and a cold start that recalls.

OPERATOR ARCHITECTURE 2026-08-17:

    "I'd want to see data proving that Ozi learns and doesnt forget relevant short
     term memory each turn which survives a compaction or clear. On new context it
     just refreshes its memory based on its living memory. On new session startup
     with that initial short term memory it reviews its extended memory in track
     files to see if there were relevant/similar memories it should append and
     leverage."

TWO TIERS, AND THE DISTINCTION IS THE DESIGN:

    LIVING (short-term)   this session's working set -- the goal it is serving, the
                          directives that arrived mid-session, the threads in flight.
                          Refreshed EVERY turn. Survives compaction because it is a
                          file, not context.

    EXTENDED (long-term)  492 session tracks on this spoke. Queried at cold start
                          against the living set, so a fresh agent inherits not just
                          where it is but what was learned somewhere else that bears
                          on it.

WHY THIS EXISTS, measured rather than assumed. compact-resume.json -- the payload a
post-compaction agent actually reads -- was inspected on 2026-08-17 and carried:
  * 7 of 10 "in progress" lugs that were not in progress
  * a previous session's active_initiative_id
  * savepoint_status "pending" two minutes after a save
  * a focus_lock naming an agenda from a different session
  * no threads at all, while 38 accurate ones sat in threads.json

The compaction survival mechanism was already wired. It was wired to the wrong
artifacts, which is the same failure shape as everything else audited that night.

WHAT A DIRECTIVE IS, and why it is not guessed. A directive is a decision the agent
RECORDED in the track, paired with the user message that prompted it. Both fields
already exist on 56 of this session's 68 turns. Inferring intent from raw user text
with keyword heuristics would manufacture directives that were never given, and a
memory that invents its own instructions is worse than one that forgets.

THE PROOF OBLIGATION. `retention` measures what fraction of turn N's directives are
still correctly held at turn N+k. That number is the claim; everything else here is
plumbing. A memory system that cannot show its own retention is asking to be trusted.

USAGE
  living_memory.py refresh            # rebuild the living set (Stop hook, every turn)
  living_memory.py show               # what is currently held
  living_memory.py recall             # query extended memory against the living set
  living_memory.py retention          # THE ORACLE: does it forget?
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SPOKE_ROOT = TOOLS.parents[3]

LIVING = "WAI-Harness/spoke/local/runtime/living-memory.json"
THREADS = "WAI-Harness/spoke/local/runtime/threads.json"
SESSIONS = "WAI-Harness/spoke/local/sessions"

# Directives decay, but slowly and never to nothing. An operator ruling from turn 3
# still binds at turn 68 unless it was superseded -- that is what makes it a ruling
# rather than a passing remark. Recency orders them; it does not delete them.
MAX_DIRECTIVES = 24
MAX_THREADS = 10
RECENT_TURNS = 6

_WORD = re.compile(r"[a-z][a-z0-9_-]{3,}")
_STOP = {"that", "this", "with", "from", "have", "will", "should", "would", "there",
         "their", "which", "about", "because", "these", "those", "your", "into",
         "than", "then", "when", "what", "were", "been", "they", "them", "here"}


def _terms(text: str):
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP}


def _track_rows(path):
    out = []
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict) and "turn" in d:
                out.append(d)
    except OSError:
        pass
    return out


def _current_session_track(root: Path):
    """The LIVE lane's track, not merely the most recently written file.

    MEASURED, and it was about to erase this file. "Newest by mtime" looked obviously
    right and is wrong: spawned subprocesses -- autopilot children, hook helpers --
    create their own session directories and touch a 1-turn track. Minutes after the
    living set was built from a 70-turn session, session-20260817-0759 appeared with
    ONE turn and became the newest. The next refresh would have rebuilt the memory
    from it and dropped 22 directives to zero, silently, with the file still looking
    well-formed.

    sessions-live.json names the lane that is actually running and the wai_session it
    belongs to. That is the authority. mtime is a guess that happens to be right until
    something else writes.

    Falls back to the richest recent track rather than the newest, because a fallback
    that can select an empty file reintroduces the same bug one layer down.
    """
    paths = glob.glob(str(root / SESSIONS / "*" / "track.jsonl"))
    if not paths:
        return None, []

    try:
        live = json.load(open(root / "WAI-Harness/spoke/local/runtime/sessions-live.json",
                              encoding="utf-8"))
        named = {rec.get("wai_session") for rec in (live.get("lanes") or {}).values()
                 if rec.get("wai_session")}
        for p in paths:
            if Path(p).parent.name in named:
                return p, _track_rows(p)
    except (OSError, ValueError):
        pass

    # No live lane on record. Prefer substance over recency.
    scored = [(len(_track_rows(p)), os.path.getmtime(p), p) for p in paths]
    scored = [s for s in scored if s[0] > 0]
    if not scored:
        return None, []
    scored.sort(key=lambda s: (-s[0], -s[1]))
    best = scored[0][2]
    return best, _track_rows(best)


def build(root: Path):
    """The living set. Assembled from what the turn already recorded, never asked for."""
    track_path, rows = _current_session_track(root)

    directives = []
    for r in rows:
        decs = r.get("decisions")
        if not decs:
            continue
        items = decs if isinstance(decs, list) else [decs]
        for d in items:
            text = d if isinstance(d, str) else json.dumps(d)
            if len(text.strip()) < 20:
                continue
            directives.append({"turn": r.get("turn"), "decision": text[:400],
                               "prompted_by": (r.get("user_msg") or "")[:200]})
    # Newest first, de-duplicated on the decision text -- a ruling restated across
    # turns is one directive, not five.
    seen, uniq = set(), []
    for d in reversed(directives):
        k = d["decision"][:120]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(d)
    directives = uniq[:MAX_DIRECTIVES]

    threads = []
    try:
        td = json.load(open(root / THREADS, encoding="utf-8"))
        threads = [t for t in (td.get("threads") or [])
                   if t.get("state") != "unrecorded"][:MAX_THREADS]
        threads_stale = bool(td.get("_stale"))
    except (OSError, ValueError):
        threads_stale = False

    recent = [{"turn": r.get("turn"), "intent": (r.get("user_intent") or "")[:220]}
              for r in rows[-RECENT_TURNS:]]

    initiative = None
    for cand in ("WAI-Harness/spoke/local/initiatives/current.json",):
        try:
            initiative = (json.load(open(root / cand, encoding="utf-8")) or {}).get("id")
        except (OSError, ValueError):
            pass

    return {
        "schema": 1,
        "track": track_path,
        "turns_seen": len(rows),
        "initiative": initiative,
        "directives": directives,
        "threads": threads,
        "threads_stale": threads_stale,
        "recent_turns": recent,
        "_note": ("LIVING memory: this session's working set, rebuilt every turn from "
                  "what the turn already recorded. Nothing here was asked of an agent "
                  "as a separate step -- that channel measures 47% on this spoke."),
    }


def refresh(root: Path):
    mem = build(root)
    dest = root / LIVING
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(mem, indent=1) + "\n", encoding="utf-8")
    return mem


def load(root: Path):
    try:
        return json.load(open(root / LIVING, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def recall(root: Path, limit=8):
    """Extended memory: prior sessions that bear on what is live right now.

    Scored on term overlap between the living set and each session's recorded
    intents. Crude on purpose -- an embedding index would be better and is not
    something to fake with a keyword match dressed up as semantics. The score is
    reported so a reader can discount it.
    """
    mem = load(root) or build(root)
    focus = set()
    for d in mem.get("directives", [])[:10]:
        focus |= _terms(d.get("decision", ""))
    for t in mem.get("threads", [])[:10]:
        focus |= _terms(t.get("what", ""))
    if not focus:
        return {"matches": [], "focus_terms": 0,
                "note": "no living focus to match against — nothing recalled"}

    cur = mem.get("track")
    paths = [p for p in glob.glob(str(root / SESSIONS / "*" / "track.jsonl")) if p != cur]

    # DISCOUNT WHAT EVERY SESSION SAYS. The first cut scored raw term overlap and
    # returned matches of 73 on words like "active", "agent", "already", "become",
    # "better" -- common English, present in every track, ranking sessions by how much
    # they were written in the same language rather than about the same thing.
    #
    # A term appearing in most sessions carries no signal about THIS one. Anything
    # above the document-frequency ceiling is dropped before scoring. Crude IDF, and
    # named as crude: a real embedding index would be better, and a keyword match
    # dressed up as semantics would be worse than admitting the limit.
    per_session_terms = {}
    df = collections.Counter()
    for p in paths:
        rows = _track_rows(p)
        if not rows:
            continue
        t = _terms(" ".join((r.get("user_intent") or "") for r in rows))
        per_session_terms[p] = (t, len(rows))
        df.update(t)

    n_docs = max(len(per_session_terms), 1)
    ceiling = 0.20 * n_docs
    distinctive = {t for t in focus if df.get(t, 0) <= ceiling}
    if not distinctive:
        return {"matches": [], "focus_terms": len(focus), "distinctive_terms": 0,
                "sessions_scanned": n_docs,
                "note": ("every term in the live focus is common across sessions -- "
                         "nothing distinctive to match on, so nothing is recalled "
                         "rather than returning noise")}

    scored = []
    for p, (terms, nrows) in per_session_terms.items():
        overlap = distinctive & terms
        if len(overlap) < 3:
            continue
        scored.append({"session": Path(p).parent.name, "turns": nrows,
                       "overlap": len(overlap),
                       "shared_terms": sorted(overlap, key=lambda t: df[t])[:12]})
    scored.sort(key=lambda s: -s["overlap"])
    return {"matches": scored[:limit], "focus_terms": len(focus),
            "distinctive_terms": len(distinctive), "df_ceiling": round(ceiling),
            "sessions_scanned": n_docs}


def retention(root: Path):
    """THE ORACLE. Does the living set hold what earlier turns established?

    Rebuilds the living set as it would have been at an earlier turn, then checks how
    much of it survives into the present one. A memory that cannot show this number is
    asking to be trusted rather than demonstrating anything.
    """
    track_path, rows = _current_session_track(root)
    if len(rows) < 10:
        return {"verdict": "UNKNOWN", "reason": f"only {len(rows)} turns — too few"}

    def directives_upto(n):
        out = set()
        for r in rows:
            if (r.get("turn") or 0) > n:
                continue
            decs = r.get("decisions") or []
            for d in (decs if isinstance(decs, list) else [decs]):
                text = d if isinstance(d, str) else json.dumps(d)
                if len(text.strip()) >= 20:
                    out.add(text[:120])
        return out

    turns = [r.get("turn") or 0 for r in rows]
    mid = sorted(turns)[len(turns) // 2]
    early = directives_upto(mid)
    now = load(root) or build(root)
    held = {d["decision"][:120] for d in now.get("directives", [])}

    if not early:
        return {"verdict": "UNKNOWN", "reason": "no directives recorded before the midpoint"}

    survived = early & held
    pct = 100 * len(survived) / len(early)
    # A cap is not amnesia, but it must be visible: MAX_DIRECTIVES bounds the set, so
    # a long session legitimately drops the oldest. Report it rather than scoring it
    # as forgetting.
    capped = len(early) > MAX_DIRECTIVES
    return {
        "verdict": "OK" if pct >= 60 or capped else "FORGETTING",
        "midpoint_turn": mid,
        "directives_by_midpoint": len(early),
        "still_held_now": len(survived),
        "retention_pct": round(pct),
        "capped_by_max_directives": capped,
        "cap": MAX_DIRECTIVES,
        "note": ("A cap is a deliberate bound, not forgetting -- but if this reads "
                 "capped=true often, MAX_DIRECTIVES is too low for how this operator "
                 "works."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(SPOKE_ROOT))
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("refresh", "show", "recall", "retention"):
        sp = sub.add_parser(name)
        # --json on BOTH parent and subparser. argparse binds a parent-level flag only
        # BEFORE the subcommand, so `living_memory.py retention --json` -- the order
        # every reader will type -- errored out.
        sp.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    if args.cmd == "refresh":
        m = refresh(root)
        out = {"turns_seen": m["turns_seen"], "directives": len(m["directives"]),
               "threads": len(m["threads"])}
        print(json.dumps(out) if args.json else
              f"living memory: {out['directives']} directive(s), {out['threads']} thread(s), "
              f"{out['turns_seen']} turn(s) seen")
        return 0

    if args.cmd == "show":
        m = load(root)
        if not m:
            print("living memory: none yet — run refresh")
            return 1
        if args.json:
            print(json.dumps(m, indent=1))
            return 0
        print(f"\nLIVING MEMORY — {m['turns_seen']} turns, "
              f"{len(m['directives'])} directive(s), {len(m['threads'])} thread(s)\n")
        for d in m["directives"][:8]:
            print(f"  [t{d['turn']}] {d['decision'][:130]}")
        return 0

    if args.cmd == "recall":
        r = recall(root)
        if args.json:
            print(json.dumps(r, indent=1))
            return 0
        print(f"\nEXTENDED RECALL — {len(r.get('matches', []))} of "
              f"{r.get('sessions_scanned', 0)} prior sessions bear on the live focus\n")
        for m in r.get("matches", []):
            print(f"  {m['session']}  overlap={m['overlap']}  turns={m['turns']}")
            print(f"      {', '.join(m['shared_terms'][:8])}")
        return 0

    r = retention(root)
    print(json.dumps(r, indent=1) if args.json else
          f"retention: {r['verdict']} — {r.get('retention_pct', '?')}% of directives "
          f"from turn {r.get('midpoint_turn','?')} still held "
          f"({r.get('still_held_now','?')}/{r.get('directives_by_midpoint','?')})")
    return 0 if r["verdict"] in ("OK", "UNKNOWN") else 1


if __name__ == "__main__":
    sys.exit(main())
