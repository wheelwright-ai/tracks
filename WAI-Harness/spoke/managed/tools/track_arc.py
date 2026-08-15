#!/usr/bin/env python3
"""track_arc.py -- render a past session's ARC so the next one resumes a thought, not a state.

WHY THIS EXISTS. Wakeup already answers "where are things": the savepoint says what to do
next, the resident digest carries open threads, netnet gives one line per session. None of
them answer "how did the thinking GET here" -- the order in which a problem was understood,
what was tried, what that ruled out. Operator, 2026-08-07: "the agent doing a read of the
track file would be a big assistance to the progression of a thought/action."

WHAT MEASUREMENT CHANGED ABOUT THE DESIGN. Sampling 142 real turn rows across 10 sessions:

    16%  model-authored, carries WHY (thinking / decisions / outcome)
    66%  synthesized from the transcript by the Layer-2 net -- carries WHAT
         (assistant_text, tools_used, files_touched) and CANNOT carry why,
         because the deriver never knew it
    16%  empty, hook seed only

So an arc that renders only model-authored rows would be blank for most sessions, and one
that treats synthesized rows as equivalent would present WHAT as if it were reasoning. This
renders both and LABELS which it had. A session that recorded no reasoning must look
different from one that did, or the next agent trusts an arc that is really a file listing.

WHY NOT JUST READ track.jsonl. Measured: 24-95KB per session, 66% of it transcript echo. The
arc is the 5% that carries the thread. Handing a fresh agent 95KB of JSONL is not a rewarm.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Order matters: the first field present wins as the turn's headline. focus is the
# model's own one-line summary of the turn, so it beats a derived one every time.
_HEADLINE = ("focus", "user_intent", "action")
_MAX_LINE = 100          # accessibility: the operator reads these; no wall of prose
_DEFAULT_TURNS = 12


def _clip(text, width=_MAX_LINE):
    s = " ".join(str(text or "").split())
    return s if len(s) <= width else s[: width - 1].rstrip() + "…"


def read_track(path):
    """Every parseable row. A torn line is skipped, never fatal -- a crashed session is
    exactly when the arc matters most."""
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return rows


def classify(row):
    """'why' | 'what' | 'empty' -- the three shapes measured in the real corpus."""
    if str(row.get("thinking", "")).strip():
        return "why"
    if any(str(row.get(k, "")).strip() for k in ("action", "focus", "outcome")):
        return "why"
    if str(row.get("assistant_text", "")).strip() or row.get("tools_used"):
        return "what"
    return "empty"


def _what_line(row):
    """Derive a headline for a synthesized row from what it DOES carry."""
    files = row.get("files_touched") or []
    tools = row.get("tools_used") or []
    if files:
        names = [os.path.basename(str(f)) for f in files[:3]]
        more = f" +{len(files) - 3}" if len(files) > 3 else ""
        return "touched " + ", ".join(names) + more
    if tools:
        # tools_used is a list of {"name": ..., "count": ...} in the synthesized rows, and
        # a list of bare strings in older ones. Rendering str(dict) leaked
        # "ran {'name': 'Bash', 'count': 8}" into the operator's read on the first run.
        seen = []
        for t in tools:
            name = t.get("name") if isinstance(t, dict) else str(t)
            count = t.get("count") if isinstance(t, dict) else None
            if not name:
                continue
            label = f"{name}x{count}" if count and count > 1 else str(name)
            if label not in seen:
                seen.append(label)
        if seen:
            return "ran " + ", ".join(seen[:4])
    return _clip(row.get("assistant_text", ""), 80)


def build_arc(rows, limit=_DEFAULT_TURNS):
    """Return (lines, stats, carry). Newest LAST, so the arc reads forwards like a story.

    ORDERED BY TIMESTAMP, NOT BY `turn`. Measured on the first real run: a single session
    emitted turn numbers 19, 2, 3, 57, 6, 10, 11 in file order, because the counter is
    derived per-invocation and resets across compaction and lane switches. Trusting it would
    print the story out of sequence while claiming to be an arc. `ts` is hook-owned and
    stamped from the system clock, so it is the one field that cannot be reordered.
    """
    turns = [r for r in rows if r.get("event") == "turn"]
    turns.sort(key=lambda r: str(r.get("ts") or ""))
    stats = {"turns": len(turns), "why": 0, "what": 0, "empty": 0}
    for r in turns:
        stats[classify(r)] += 1

    lines, carry = [], []
    window = turns[-limit:]
    first = len(turns) - len(window)
    for offset, row in enumerate(window, start=first + 1):
        kind = classify(row)
        if kind == "empty":
            continue
        # CHRONOLOGICAL POSITION, NOT THE `turn` FIELD. The same run that exposed the
        # ordering bug also proved the numbers themselves are unusable as labels: 19, 2, 3,
        # 57, 6, 10, 11 within one session. A label the operator cannot point at is worse
        # than no label, so this counts the rows and shows the clock instead.
        n = offset
        clock = str(row.get("ts") or "")[11:16]
        n = f"{n}." + (f" {clock}" if clock else "")
        if kind == "why":
            head = ""
            for key in _HEADLINE:
                if str(row.get(key, "")).strip():
                    head = str(row[key])
                    break
            phase = str(row.get("phase", "")).strip()
            tag = f"[{phase}] " if phase else ""
            lines.append(f"  {n} {tag}{_clip(head)}")
            out = str(row.get("outcome", "")).strip()
            if out:
                lines.append(f"       -> {_clip(out, _MAX_LINE - 10)}")
            for d in (row.get("decisions") or [])[:2]:
                if isinstance(d, dict) and d.get("decision"):
                    why = d.get("why", "")
                    lines.append(f"       ! {_clip(d['decision'], 70)}"
                                 + (f"  ({_clip(why, 60)})" if why else ""))
            # Only the LAST rich row's open items are carried: earlier ones were either
            # closed later in the session or restated. Accumulating them all reproduces
            # the stale-thread pile the digest already has.
            if row.get("open"):
                carry = row["open"]
        else:
            lines.append(f"  {n} (no reasoning recorded) {_clip(_what_line(row), 70)}")
    return lines, stats, carry


def render(session_dir, limit=_DEFAULT_TURNS):
    session_dir = Path(session_dir)
    rows = read_track(session_dir / "track.jsonl")
    if not rows:
        return f"ARC {session_dir.name}: no track rows -- nothing to resume from."

    lines, stats, carry = build_arc(rows, limit)
    pct = (100 * stats["why"] // stats["turns"]) if stats["turns"] else 0
    out = [f"ARC {session_dir.name} -- {stats['turns']} turn(s), "
           f"{stats['why']} with reasoning ({pct}%)"]
    # An honest header beats a full-looking arc. A reader who knows only 1 turn in 10
    # recorded WHY reads the rest as a file listing, which is what it is.
    if stats["turns"] and pct < 50:
        out.append(f"  (thin: {stats['what']} turn(s) are transcript-derived WHAT only, "
                   f"{stats['empty']} empty -- treat gaps as unrecorded, not as idle)")
    out.extend(lines or ["  (no turn carried renderable content)"])
    if carry:
        out.append("  OPEN at close:")
        for item in carry[:5]:
            if isinstance(item, dict):
                landing = item.get("landing", "")
                out.append(f"    - {_clip(item.get('item', ''), 78)}")
                if landing:
                    out.append(f"        lands when: {_clip(landing, 70)}")
            else:
                out.append(f"    - {_clip(item, 78)}")
    return "\n".join(out)


def latest_session(base):
    """Most recent session dir that actually HAS a track, not merely the newest name.

    A bare directory sorts first and would silently render an empty arc -- the same
    exists-therefore-fine mistake that once made the flush hook lose a day of turns.
    """
    sessions = Path(base) / "sessions"
    if not sessions.is_dir():
        return None
    cands = [d for d in sessions.glob("session-*") if (d / "track.jsonl").is_file()]
    if not cands:
        return None
    return max(cands, key=lambda d: (d / "track.jsonl").stat().st_mtime)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="WAI-Harness/spoke/local")
    ap.add_argument("--session", default="", help="session id; default = latest with a track")
    ap.add_argument("-n", "--turns", type=int, default=_DEFAULT_TURNS)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.session:
        sd = Path(a.base) / "sessions" / a.session
    else:
        sd = latest_session(a.base)
    if sd is None or not sd.is_dir():
        # Silence, not an error: a spoke with no sessions yet is normal, and a wakeup
        # must never fail because there is no history to show.
        return 0

    if a.json:
        rows = read_track(sd / "track.jsonl")
        lines, stats, carry = build_arc(rows, a.turns)
        print(json.dumps({"session": sd.name, "stats": stats,
                          "lines": lines, "open": carry}, indent=2))
    else:
        print(render(sd, a.turns))
    return 0


if __name__ == "__main__":
    sys.exit(main())
