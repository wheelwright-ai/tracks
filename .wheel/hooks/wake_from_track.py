#!/usr/bin/env python3
"""SessionStart hook: a new session opens from the last session's Track.

Finds the newest WAI_Track-*.jsonl in .wheel/tracks (name order = time order), and prints its open items (from the
last point that lists any, since each point restates what is still unresolved) and every decision recorded, plus the
session_end summary when there is one. Output is the SessionStart additionalContext JSON. Silent when there is no
track. Never blocks a session start."""
import json, os, sys, glob

sys.dont_write_bytecode = True
MAX_DECISIONS = 10


def latest_track(root):
    files = sorted(glob.glob(os.path.join(root, ".wheel", "tracks", "WAI_Track-*.jsonl")))
    return files[-1] if files else None


def read_rows(path):
    rows = []
    for line in open(path):
        try:
            r = json.loads(line)
        except Exception:
            continue
        if isinstance(r, dict):
            rows.append(r)
    return rows


def digest(path):
    rows = read_rows(path)
    points = [r for r in rows if "turn" in r]
    end = next((r for r in reversed(rows) if r.get("event") == "session_end"), None)
    opens = []
    for p in reversed(points):
        if p.get("open"):
            opens = [o for o in p["open"] if isinstance(o, dict) and o.get("item")]
            break
    decisions = []
    for p in points:
        for d in p.get("decisions") or []:
            if isinstance(d, str) and d not in decisions:
                decisions.append(d)
    lines = ["Opening from the last session's track (%s, %d turns):" % (os.path.basename(path), len(points))]
    if end and end.get("summary"):
        lines.append("Summary: %s" % end["summary"])
    lines.append("Open items:" if opens else "Open items: none recorded.")
    for o in opens:
        lines.append("- %s [%s]" % (o["item"], o.get("status", "unknown")))
    lines.append("Decisions:" if decisions else "Decisions: none recorded.")
    for d in decisions[-MAX_DECISIONS:]:
        lines.append("- %s" % d)
    return "\n".join(lines)


def main():
    try:
        hook = json.load(sys.stdin)
    except Exception:
        hook = {}
    root = hook.get("cwd") or os.getcwd()
    path = latest_track(root)
    if not path:
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": digest(path)}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
