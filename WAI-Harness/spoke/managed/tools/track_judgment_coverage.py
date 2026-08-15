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
    rich = floor = malformed = 0
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
        else:
            floor += 1
    return {"rich": rich, "floor": floor, "malformed": malformed,
            "turns": rich + floor,
            "pct": round(rich / (rich + floor) * 100) if (rich + floor) else None}


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
    mal = sum(s["malformed"] for s in sessions.values())
    thin = [k for k, s in sessions.items() if s["pct"] is not None and s["pct"] < 50]
    return {"sessions": len(sessions), "rich": rich, "floor": floor,
            "turns": rich + floor, "malformed": mal,
            "pct": round(rich / (rich + floor) * 100) if (rich + floor) else None,
            "sessions_below_50pct": sorted(thin)}


def render(sessions, summary, only_session=None):
    L = []
    if only_session:
        s = sessions.get(only_session)
        if not s:
            return f"TRACK JUDGMENT: no turns recorded for {only_session}"
        L.append(f"TRACK JUDGMENT — {only_session}")
        L.append(f"  {s['rich']} of {s['turns']} turns carry reasoning ({s['pct']}%)")
        if s["floor"]:
            L.append(f"  {s['floor']} turn(s) are FLOOR-only: facts kept, judgment lost "
                     f"(no thinking / decisions / insights / open)")
            L.append("  -> the per-turn track-buffer.json write was skipped on those turns")
        if s["malformed"]:
            L.append(f"  {s['malformed']} malformed line(s) — not JSON objects")
        return "\n".join(L)
    L.append(f"TRACK JUDGMENT — {summary['sessions']} session(s), {summary['turns']} turns")
    L.append(f"  {summary['rich']} carry reasoning ({summary['pct']}%), "
             f"{summary['floor']} are floor-only")
    if summary["sessions_below_50pct"]:
        n = len(summary["sessions_below_50pct"])
        L.append(f"  {n} session(s) below 50% — judgment is the exception there, not the rule")
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
