#!/usr/bin/env python3
"""track_judgment_coverage.py — how much of the track carries REASONING, not just facts.

THE SILENCE THIS BREAKS. The WAI track has two layers. The model writes a RICH entry
per turn (thinking, decisions, insights, open threads, focus, phase); when it does not,
synthesize_turn.py reconstructs a FLOOR entry from the transcript so no turn is lost.
The floor is genuinely good — assistant_text, user_intent, files_touched, tools_used,
tokens, uuids. What it cannot reconstruct is judgment: WHY a choice was made, what was
rejected, what is still open.

Measured across the fleet on 2026-08-02, and nobody knew:

    mywheel   1014 turns   50% rich
    basher     511 turns   37% rich      36 of 65 sessions below 50%
    pathfinder 325 turns   31% rich
    ezorg      272 turns   23% rich
    why-go-bye  80 turns   18% rich

So roughly two thirds of the fleet's recorded history has facts and no reasoning. This
never errored, never warned, and never appeared in any brief. It was found only because
an operator noticed a missing statusline.

That matters because the judgment layer is not decoration — it is the input to lens's
[s] insights page, the resident continuity digest, and Ozi's attention routing. Those
have been running on a third of their intended signal.

WHY A MEASUREMENT AND NOT A BLOCK. The per-turn write is an instruction to a model, and
instructions get skipped under load — that is what happened here, on nine turns of one
long session, by an agent that had spent the whole session fixing exactly this class of
defect elsewhere. Blocking a turn on it would be worse than the disease. Making the loss
VISIBLE per session converts a silent decay into something a ceremony can report and an
operator can see, which is the smallest change that actually alters behaviour.

CLI:
    track_judgment_coverage.py --base <spoke_local>                  # this spoke
    track_judgment_coverage.py --base <spoke_local> --session <id>   # one session
    track_judgment_coverage.py --base <spoke_local> --json
Exit: 0 always (a measurement never blocks a ceremony).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

# The fields that make an entry RICH. thinking is the load-bearing one — an entry with
# thinking but nothing else still explains itself; one with everything but thinking does
# not. Kept as a set so a schema change is a one-line edit here, not a hunt.
JUDGMENT_FIELDS = ("thinking", "decisions", "insights", "open")
FLOOR_MARKER = "synthesized"


def scan_session(track_path):
    """Three buckets, not two — because two fused two DIFFERENT failures into one number.

    FLOOR_MARKER was declared at the top of this file and never read by anything. The
    original scan bucketed purely on `thinking`, so a layer-2 backfill — which CANNOT
    carry judgment by construction, because synthesize_turn.py reconstructs it from a
    transcript after the fact — was counted as the model having skipped its write.

    MEASURED 2026-08-22, mywheel, last 15 sessions with turns:
        source=model            61 turns, 61 carry thinking
        source=transcript-synth 154 turns, 0 carry thinking   <- zero exceptions
    Two long sessions (145 and 79 turns) held 224 of 279 turns. In session-20260820-1815
    turns 0-8 are source=model and all nine are rich; from turn 9 on it is backfill and
    coverage is 0/136. That is not a model that stopped reasoning. That is a capture path
    that died at turn 9 while the safety net kept producing rows that look like turns.

    Confirmed on an independent tree the same day (basher, last 18 sessions):
        fused number this tool used to report .......... 47%
        judgment over MODEL-AUTHORED turns ............. 78%
        turns that never reached layer 1 ............... 40%
    So the fleet table in the docstring above measures the wrong thing, and the lug's
    premise ("byte-identical hooks, therefore behavioural") inverts once the two are split.

    rich   = the model wrote judgment.                      (the good case)
    floor  = the model authored the turn and left it blank. (a real discipline miss)
    synth  = layer 1 never ran; layer 2 backfilled.         (a DEAD CAPTURE PATH)

    `pct` is now judgment over AUTHORED turns only. Counting synth in the denominator
    punishes a model for turns it was never asked to write.
    (bug-track-judgment-layer-unenforced-fleet-wide-v1)
    """
    rich = floor = synth = malformed = 0
    for line in _lines(track_path):
        try:
            rec = json.loads(line)
        except Exception:
            malformed += 1
            continue
        if not isinstance(rec, dict):
            # A bare string on a track line. Real: mywheel session-20260722-0824 has one.
            # Counted, never crashed on — a reader that dies on one bad line reports
            # nothing about the other thousand.
            malformed += 1
            continue
        if rec.get("event") != "turn":
            continue
        if rec.get("thinking"):
            rich += 1
        elif rec.get(FLOOR_MARKER):
            # The constant finally does something. A synthesized turn is not a missed
            # write — it is evidence the write was never solicited.
            synth += 1
        else:
            floor += 1
    authored = rich + floor
    turns = authored + synth
    return {"rich": rich, "floor": floor, "synth": synth, "malformed": malformed,
            "authored": authored, "turns": turns,
            "pct": round(rich / authored * 100) if authored else None,
            "synth_pct": round(synth / turns * 100) if turns else None}


def _lines(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield line
    except OSError:
        return


def scan_spoke(base, only_session=None):
    out = {}
    pattern = os.path.join(base, "sessions", only_session or "session-*", "track.jsonl")
    for f in sorted(glob.glob(pattern)):
        sid = os.path.basename(os.path.dirname(f))
        s = scan_session(f)
        if s["turns"] or s["malformed"]:
            out[sid] = s
    return out


def summarise(sessions):
    rich = sum(s["rich"] for s in sessions.values())
    floor = sum(s["floor"] for s in sessions.values())
    synth = sum(s.get("synth", 0) for s in sessions.values())
    mal = sum(s["malformed"] for s in sessions.values())
    thin = [k for k, s in sessions.items() if s["pct"] is not None and s["pct"] < 50]
    # A session where the capture path died is a SEPARATE alarm from a thin one, and the
    # more urgent of the two: a thin session lost judgment on some turns, a dark session
    # was never asked for judgment at all and nothing said so.
    dark = [k for k, s in sessions.items()
            if s.get("synth_pct") is not None and s["synth_pct"] >= 50]
    authored = rich + floor
    turns = authored + synth
    return {"sessions": len(sessions), "rich": rich, "floor": floor, "synth": synth,
            "authored": authored, "turns": turns, "malformed": mal,
            "pct": round(rich / authored * 100) if authored else None,
            "synth_pct": round(synth / turns * 100) if turns else None,
            "sessions_below_50pct": sorted(thin),
            "sessions_capture_dark": sorted(dark)}


def render(sessions, summary, only_session=None):
    L = []
    if only_session:
        s = sessions.get(only_session)
        if not s:
            return f"TRACK JUDGMENT: no turns recorded for {only_session}"
        L.append(f"TRACK JUDGMENT — {only_session}")
        if s["authored"]:
            L.append(f"  {s['rich']} of {s['authored']} AUTHORED turns carry reasoning "
                     f"({s['pct']}%)")
        else:
            # NO AUTHORED TURNS MEANS THE COVERAGE IS UNMEASURABLE, NOT ZERO AND NOT None%.
            # session-20260820-1730 renders here: 71 turns, every one a backfill. A
            # percentage printed over an empty denominator invites exactly the wrong
            # conclusion — that the model wrote nothing — when the truth is it was never
            # asked. Say the instrument cannot measure this rather than emit a number.
            L.append("  coverage UNMEASURABLE — 0 turns were authored by the model; "
                     "every turn in this session is a backfill")
        if s["floor"]:
            L.append(f"  {s['floor']} turn(s) are FLOOR-only: facts kept, judgment lost "
                     f"(no thinking / decisions / insights / open)")
            L.append("  -> the model authored these and skipped the track-buffer.json write")
        if s.get("synth"):
            # NEVER say "the write was skipped" about a synthesized turn. It was not
            # skipped; layer 1 never ran and layer 2 backfilled from the transcript.
            # Reporting the wrong cause is what sent this investigation at the model's
            # discipline for weeks instead of at the capture path.
            L.append(f"  {s['synth']} turn(s) are BACKFILL (synthesize_turn.py): layer 1 "
                     f"never ran, so no judgment was ever solicited")
            L.append(f"  -> capture-path liveness, not model discipline: {s['synth_pct']}% "
                     f"of {s['turns']} total turns reached only layer 2")
        if s["malformed"]:
            L.append(f"  {s['malformed']} malformed line(s) — not JSON objects")
        return "\n".join(L)
    L.append(f"TRACK JUDGMENT — {summary['sessions']} session(s), {summary['turns']} turns")
    L.append(f"  {summary['rich']} of {summary['authored']} authored turns carry reasoning "
             f"({summary['pct']}%), {summary['floor']} are floor-only")
    if summary.get("synth"):
        L.append(f"  {summary['synth']} turn(s) ({summary['synth_pct']}%) are backfill — "
                 f"layer 1 did not run and nothing reported it")
    if summary["sessions_below_50pct"]:
        n = len(summary["sessions_below_50pct"])
        L.append(f"  {n} session(s) below 50% — judgment is the exception there, not the rule")
    if summary.get("sessions_capture_dark"):
        n = len(summary["sessions_capture_dark"])
        L.append(f"  {n} session(s) CAPTURE-DARK (>=50% backfill) — the turn writer was "
                 f"not running; fix that before reading anything into their coverage")
    if summary["malformed"]:
        L.append(f"  {summary['malformed']} malformed track line(s)")
    L.append("  The floor keeps assistant_text, user_intent, files_touched, tools, tokens.")
    L.append("  It cannot reconstruct WHY — which is what lens [s], the resident digest,")
    L.append("  and Ozi's attention routing consume.")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Measure judgment coverage of the WAI track")
    ap.add_argument("--base", default="WAI-Harness/spoke/local")
    ap.add_argument("--session", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    sessions = scan_spoke(a.base, a.session)
    summary = summarise(sessions)
    if a.json:
        print(json.dumps({"summary": summary, "sessions": sessions}, indent=1))
    else:
        print(render(sessions, summary, a.session))
    return 0


if __name__ == "__main__":
    sys.exit(main())
