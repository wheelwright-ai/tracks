#!/usr/bin/env python3
"""tools/write_netnet.py — session net-net synopsis writer (impl-exitclarity-6).

At closeout, after the session track is finalized, writes ONE line to
sessions/netnet.jsonl: a short headline plus arcs of work. Every arc is
derived from mechanical inputs (track events + on-disk lug status) and every
arc's artifact_refs must resolve to a real lug/initiative/commit — a claim
with no resolving ref is dropped, never written (skeptic lens:
_improvement_lenses on the lug). Also renders the last-N headlines for the
wakeup "trajectory" read, and backfills recent sessions from their
track.jsonl files (marked backfilled:true).

Usage:
  write_netnet.py write --session-id S --track-path P [--headline TEXT] [--dry-run]
  write_netnet.py trajectory [-n 10]
  write_netnet.py backfill [-n 10]
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import wai_paths
except Exception:
    wai_paths = None

LUG_ID_RE = re.compile(r"\b(?:impl|fix|task|feature|notice|review|epic|spec|signal|initiative)-[a-z0-9][a-z0-9-]*-v\d+\b")
HEADLINE_MAX = 140


def _base(spoke_root="."):
    if wai_paths is not None:
        try:
            root, mode = wai_paths.resolve_wai_root(str(spoke_root))
            if root and mode != "none":
                return root
        except Exception:
            pass
    return os.path.join(str(spoke_root), "WAI-Harness", "spoke", "local")


def _load_jsonl(path):
    events = []
    if not os.path.exists(path):
        return events
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, list):
                events.extend(obj)
            else:
                events.append(obj)
    return events


def _open_text(entry):
    """An `open` entry is a bare string (legacy track) or {"text":..., "landing":...}."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("text", "")
    return str(entry)


def _lug_glob(base, lug_id):
    return glob.glob(os.path.join(base, "lugs", "bytype", "*", "*", f"{lug_id}.json"))


def lug_exists(base, lug_id):
    return bool(_lug_glob(base, lug_id))


def load_lug(base, lug_id):
    hits = _lug_glob(base, lug_id)
    if not hits:
        return None
    try:
        return json.load(open(hits[0]))
    except Exception:
        return None


def initiative_exists(base, initiative_id):
    return bool(glob.glob(os.path.join(base, "initiatives", "bytype", "initiative", "*", f"{initiative_id}.json")))


def commit_exists(repo_root, sha):
    try:
        r = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=repo_root,
                            capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def artifact_exists(base, repo_root, ref):
    """Used by consumers (e.g. wakeup trajectory) to spot-check a ref before trusting it."""
    if not ref or not isinstance(ref, str):
        return False
    if ref.startswith("initiative-"):
        return initiative_exists(base, ref)
    if lug_exists(base, ref):
        return True
    if re.fullmatch(r"[0-9a-f]{7,40}", ref):
        return commit_exists(repo_root, ref)
    return False


ARC_STATE_BY_STATUS = {
    "completed": "completed",
    "delivered": "completed",
    "in_progress": "advanced",
    "open": "opened",
    "draft": "opened",
}


def _arc_state(lug):
    status = lug.get("status") or lug.get("s") or "open"
    if status in ("completed", "delivered"):
        return "completed"
    if lug.get("needs_attention") or lug.get("triage_flag"):
        return "blocked"
    return ARC_STATE_BY_STATUS.get(status, "advanced")


def derive_arcs(base, repo_root, events):
    """Mechanical arc derivation: explicit lug-id events take priority over a
    regex sweep of free-text fields; every candidate is resolved against
    on-disk lug state. A candidate whose id does not resolve to a real lug or
    initiative is dropped (returned separately for transparency), never
    written as an arc — 'covered' must be PathGraph-checkable, not vibes.
    """
    explicit_status = {}
    mentioned = set()

    for ev in events:
        if not isinstance(ev, dict):
            continue
        lid = ev.get("lug_id")
        if lid:
            if ev.get("event") == "lug_status_change" and ev.get("to_status"):
                explicit_status[lid] = ev["to_status"]
            elif ev.get("turn_type") == "uat" and ev.get("acceptance") == "accepted":
                explicit_status.setdefault(lid, "completed")
            else:
                mentioned.add(lid)
        # Mechanical sweep over the WHOLE event (decisions/insights/action/outcome/
        # focus/open/files_touched/target_files/...) rather than a fixed field list —
        # lug ids show up in file paths (files_touched) as often as in prose.
        try:
            mentioned.update(LUG_ID_RE.findall(json.dumps(ev)))
        except Exception:
            pass

    arcs = []
    dropped = []
    for lid in sorted(set(explicit_status) | mentioned):
        if lid.startswith("initiative-"):
            if not initiative_exists(base, lid):
                dropped.append(lid)
                continue
            arcs.append({"topic": lid, "state": "advanced", "artifact_refs": [lid]})
            continue
        lug = load_lug(base, lid)
        if lug is None:
            dropped.append(lid)
            continue
        forced = explicit_status.get(lid)
        state = ARC_STATE_BY_STATUS.get(forced) if forced else None
        state = state or _arc_state(lug)
        arcs.append({"topic": lug.get("title", lid), "state": state, "artifact_refs": [lid]})

    return arcs, dropped


def derive_headline(arcs):
    counts = {"completed": 0, "advanced": 0, "opened": 0, "blocked": 0}
    for a in arcs:
        counts[a["state"]] = counts.get(a["state"], 0) + 1
    parts = [f"{n} {label}" for label, n in counts.items() if n]
    headline = ("Session: " + ", ".join(parts)) if parts else "Session: no PathGraph-verifiable lug work"
    return headline[:HEADLINE_MAX]


def session_dates(events):
    stamps = sorted(ev.get("ts") for ev in events if isinstance(ev, dict) and ev.get("ts"))
    return {"start": stamps[0] if stamps else None, "end": stamps[-1] if stamps else None}


def operator_decisions(events):
    out = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        for d in ev.get("decisions") or []:
            if isinstance(d, str) and d not in out:
                out.append(d)
    return out


def operator_items_left(events):
    """Forward-looking: the LAST track point's `open` entries (threads still open at session end)."""
    for ev in reversed(events):
        if isinstance(ev, dict) and ev.get("open"):
            return [_open_text(e) for e in ev["open"]]
    return []


def next_pointer_from_state(base):
    try:
        state = json.load(open(os.path.join(base, "WAI-State.json")))
        return state.get("_session_state", {}).get("next_session_recommendation") or ""
    except Exception:
        return ""


def netnet_path(base):
    return os.path.join(base, "sessions", "netnet.jsonl")


def existing_session_ids(base):
    ids = set()
    for entry in _load_jsonl(netnet_path(base)):
        if isinstance(entry, dict) and entry.get("session_id"):
            ids.add(entry["session_id"])
    return ids


def build_line(session_id, base, repo_root, track_path, headline=None, backfilled=False):
    events = _load_jsonl(track_path)
    arcs, dropped = derive_arcs(base, repo_root, events)
    line = {
        "session_id": session_id,
        "dates": session_dates(events),
        "headline": (headline or derive_headline(arcs))[:HEADLINE_MAX],
        "arcs": arcs,
        "operator_decisions_made": operator_decisions(events),
        "operator_items_left": operator_items_left(events),
        "next_pointer": next_pointer_from_state(base),
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    if dropped:
        line["_dropped_refs"] = dropped  # transparency only — never counted as covered
    if backfilled:
        line["backfilled"] = True
    return line


def write_line(line, base):
    path = netnet_path(base)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(line) + "\n")
    return path


def cmd_write(args):
    base = args.base or _base(".")
    repo_root = args.repo or "."
    line = build_line(args.session_id, base, repo_root, args.track_path, headline=args.headline)
    if args.dry_run:
        print(json.dumps(line, indent=2))
        return
    path = write_line(line, base)
    print(json.dumps({"ok": True, "path": path, "arcs": len(line["arcs"]),
                       "dropped_refs": len(line.get("_dropped_refs", []))}))


def cmd_trajectory(args):
    base = args.base or _base(".")
    entries = _load_jsonl(netnet_path(base))
    last = entries[-args.n:]
    if not last:
        print("(no netnet history yet)")
        return
    for entry in last:
        tag = " [backfilled]" if entry.get("backfilled") else ""
        print(f"{entry.get('session_id', '?')}: {entry.get('headline', '')}{tag}")


def cmd_backfill(args):
    base = args.base or _base(".")
    repo_root = args.repo or "."
    have = existing_session_ids(base)
    dirs = sorted(
        (d for d in glob.glob(os.path.join(base, "sessions", "session-*")) if os.path.isdir(d)),
        key=os.path.getmtime, reverse=True,
    )
    written = 0
    for d in dirs:
        if written >= args.n:
            break
        session_id = os.path.basename(d)
        if session_id in have:
            continue
        track_path = os.path.join(d, "track.jsonl")
        if not os.path.exists(track_path):
            continue
        line = build_line(session_id, base, repo_root, track_path, backfilled=True)
        write_line(line, base)
        written += 1
    print(json.dumps({"ok": True, "backfilled": written}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base")
    ap.add_argument("--repo")
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write")
    w.add_argument("--session-id", required=True)
    w.add_argument("--track-path", required=True)
    w.add_argument("--headline")
    w.add_argument("--dry-run", action="store_true")
    w.set_defaults(func=cmd_write)

    t = sub.add_parser("trajectory")
    t.add_argument("-n", type=int, default=10)
    t.set_defaults(func=cmd_trajectory)

    b = sub.add_parser("backfill")
    b.add_argument("-n", type=int, default=10)
    b.set_defaults(func=cmd_backfill)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
