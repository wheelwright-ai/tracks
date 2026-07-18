#!/usr/bin/env python3
"""resident_digest.py — incremental synthesis of a spoke's track files into a resident digest.

The Resident is a spoke's continuity voice: it remembers what was discussed here and
carries it across sessions. Its memory is this digest — a log-structured rolling
synthesis, never a full re-read of the track corpus.

Cadence:
  bootstrap  — one-time full pass over every session track (run once per spoke)
  roll       — fold ONE session's track into the digest (run at savepoint/closeout)
  compact    — re-synthesize warm tier into cold summary (run every N sessions)

Design contract (see spec-resident-voice-v1):
  - Tiered: hot (current session) / warm (recent, full fidelity) / cold (compacted).
  - Incremental by default. `roll` reads only the named session, never the corpus.
  - Every entry carries provenance (session, turn) so a claim can be traced back.
  - Drops are LOGGED. A synthesis that silently discards is indistinguishable from
    one with nothing to say — the failure mode this whole design exists to avoid.

Usage:
  resident_digest.py bootstrap [--spoke-path P]
  resident_digest.py roll --session session-YYYYMMDD-HHMM [--spoke-path P]
  resident_digest.py compact [--keep-warm N] [--spoke-path P]
  resident_digest.py show [--tier hot|warm|cold|all]
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

DIGEST_VERSION = "1.0.0"
DEFAULT_KEEP_WARM = 10

# Track fields that carry durable, synthesizable signal. Everything else is
# per-turn mechanics (tokens, tool lists) that the Resident does not remember.
SIGNAL_FIELDS = ("decisions", "insights", "open")
CONTEXT_FIELDS = ("focus", "phase", "user_intent", "outcome")


def _now():
    return datetime.now(timezone.utc).isoformat()


def find_spoke_root(start=None):
    """Walk up from `start` until a dir containing WAI-Harness/spoke/local is found."""
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(cur, "WAI-Harness", "spoke", "local")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise SystemExit("resident_digest: no spoke root found (looked for WAI-Harness/spoke/local)")
        cur = parent


def paths(spoke_root):
    local = os.path.join(spoke_root, "WAI-Harness", "spoke", "local")
    return {
        "local": local,
        "sessions": os.path.join(local, "sessions"),
        "resident": os.path.join(local, "resident"),
        "digest": os.path.join(local, "resident", "digest.json"),
        "droplog": os.path.join(local, "resident", "drops.jsonl"),
    }


def load_digest(p):
    if os.path.exists(p["digest"]):
        with open(p["digest"]) as f:
            return json.load(f)
    return {
        "digest_version": DIGEST_VERSION,
        "spoke": os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(p["local"])))),
        "created_at": _now(),
        "updated_at": None,
        "sessions_folded": [],
        "hot": {},
        "warm": [],
        "cold": {"summary": [], "sessions_covered": 0},
        "open_threads": [],
        "stats": {"turns_read": 0, "entries_kept": 0, "entries_dropped": 0},
    }


def save_digest(p, digest):
    os.makedirs(p["resident"], exist_ok=True)
    digest["updated_at"] = _now()
    tmp = p["digest"] + ".tmp"
    with open(tmp, "w") as f:
        json.dump(digest, f, indent=2)
    os.replace(tmp, p["digest"])


def log_drops(p, session, drops):
    """Record what synthesis discarded and why. Never silent."""
    if not drops:
        return
    os.makedirs(p["resident"], exist_ok=True)
    with open(p["droplog"], "a") as f:
        for reason, count, sample in drops:
            f.write(json.dumps({
                "ts": _now(), "session": session, "reason": reason,
                "count": count, "sample": sample,
            }) + "\n")


def read_track(sessions_dir, session):
    """Read one session's track.jsonl. Returns (turns, malformed_count)."""
    path = os.path.join(sessions_dir, session, "track.jsonl")
    if not os.path.exists(path):
        return [], 0
    turns, malformed = [], 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                turns.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1
    return turns, malformed


def thread_id(text):
    """
    Stable identity for an open thread.

    Matching on raw text was the s138 failure: rewording a thread mid-session
    broke inheritance and every landing condition silently evaporated on the
    roll. This normalises (case, punctuation, whitespace) and hashes, so a
    thread keeps its identity — and its landing condition — through ordinary
    rephrasing. Not immune to a full rewrite; that is what an explicit `id` on
    the open entry is for.
    """
    norm = "".join(ch.lower() for ch in (text or "") if ch.isalnum() or ch.isspace())
    norm = " ".join(norm.split())[:120]
    return "th-" + hashlib.md5(norm.encode()).hexdigest()[:10]


def synthesize_session(session, turns):
    """Fold one session's turns into a single warm-tier entry.

    Deterministic extraction only — no model call. The Resident agent reasons OVER
    this digest; the digest itself must be reproducible and cheap.
    """
    entry = {
        "session": session,
        "turns": len(turns),
        "started": turns[0].get("ts") if turns else None,
        "ended": turns[-1].get("ts") if turns else None,
        "focus": None,
        "phases": [],
        "decisions": [],
        "insights": [],
        "open": [],
    }
    drops = []
    empty_turns = 0
    last_open_turn = None   # last turn that CARRIED `open`, empty list included

    for t in turns:
        if not any(t.get(k) for k in SIGNAL_FIELDS + CONTEXT_FIELDS):
            empty_turns += 1
            continue
        turn_no = t.get("turn")
        if t.get("focus"):
            entry["focus"] = t["focus"]  # last non-empty focus wins
        ph = t.get("phase")
        if ph and ph not in entry["phases"]:
            entry["phases"].append(ph)
        if "open" in t and isinstance(t.get("open"), (list, str)):
            last_open_turn = turn_no
        for field in SIGNAL_FIELDS:
            vals = t.get(field) or []
            if isinstance(vals, str):
                vals = [vals]
            for v in vals:
                # `open` entries may be a plain string OR an object carrying a
                # landing condition and a stable id:
                #   {"text": "...", "landing": {...}, "id": "thread-slug"}
                # Object form is what lets a thread be BORN checkable instead of
                # having conditions hand-attached to the digest afterwards
                # (s138: hand-attached conditions did not survive a same-session
                # roll because matching was on mutable text).
                if field == "open" and isinstance(v, dict):
                    row = {"turn": turn_no, "text": str(v.get("text", ""))}
                    if isinstance(v.get("landing"), dict):
                        row["landing"] = v["landing"]
                    if v.get("id"):
                        row["id"] = str(v["id"])
                    row.setdefault("id", thread_id(row["text"]))
                    entry[field].append(row)
                elif field == "open":
                    entry[field].append({"turn": turn_no, "text": str(v),
                                         "id": thread_id(str(v))})
                else:
                    entry[field].append({"turn": turn_no, "text": v})

    # `open` is overwritten each turn by design (it is a live list, not a log) —
    # keep only the final turn's view, but preserve provenance.
    #
    # The authoritative turn is the last one that CARRIED the `open` key at all,
    # not the last one that carried a NON-EMPTY list. That distinction is the
    # whole bug (s138, Fable): a final turn declaring `open: []` — the agent
    # saying "everything landed" — used to contribute nothing, so the previous
    # turn's list survived and the desk could never be cleared from inside a
    # session. Empty must mean cleared, here as well as in fold().
    if last_open_turn is not None:
        pruned = [o for o in entry["open"] if o["turn"] != last_open_turn]
        if pruned:
            drops.append(("open-superseded-by-later-turn", len(pruned), pruned[0]["text"][:120]))
        entry["open"] = [o for o in entry["open"] if o["turn"] == last_open_turn]

    if empty_turns:
        drops.append(("turn-carried-no-signal-fields", empty_turns, ""))

    return entry, drops


def fold(digest, entry, p, malformed=0):
    if entry["session"] in digest["sessions_folded"]:
        # Re-fold if the session GREW since the last fold (mid-session roll followed
        # by more turns). Keying idempotency on session id alone left the digest
        # holding a stale open_threads list — defect caught live s138.
        prior = next((w for w in digest["warm"] if w["session"] == entry["session"]), None)
        if prior is None or entry["turns"] <= prior["turns"]:
            return digest, False
        digest["warm"] = [w for w in digest["warm"] if w["session"] != entry["session"]]
        digest["sessions_folded"].remove(entry["session"])
        digest["stats"]["turns_read"] -= prior["turns"]
        digest["stats"]["entries_kept"] -= sum(len(prior[f]) for f in SIGNAL_FIELDS)
        log_drops(p, entry["session"], [("refolded-session-grew",1,f"{prior['turns']}->{entry['turns']} turns")])
    if malformed:
        log_drops(p, entry["session"], [("malformed-jsonl-line", malformed, "")])
    digest["warm"].append(entry)
    digest["warm"].sort(key=lambda e: e["session"])
    digest["sessions_folded"].append(entry["session"])
    digest["sessions_folded"].sort()
    # LANDING CONTRACT (s138, caught by Fable review). This used to end in
    #   `... ] or digest["open_threads"]`
    # which meant an EMPTY final open list kept the PREVIOUS session's threads.
    # A cleared desk was indistinguishable from no data, so a thread could
    # never be closed by clearing it — the digest would keep instructing future
    # sessions to land work that had already landed.
    #
    # Empty now means CLEARED, which is the whole point: the closure vector's
    # thread list has to be able to reach zero or it is not a landing
    # instrument, it is an accumulator. The malformed-track case is handled
    # upstream (fold() refuses to overwrite from a track it could not read),
    # so reaching here with an empty list is a real signal, not a failure.
    # MERGE, never replace (s138, second Fable pass — this was REFUTED as a
    # full replacement). Two bugs lived in the old one-liner:
    #   1. it DROPPED any `landing` condition a thread carried, so the landing
    #      checker had nothing to check by the next roll; and
    #   2. it REPLACED the whole list with just this session's threads, so
    #      every still-open thread from every OTHER session was silently
    #      erased — worse than the sticky-threads bug it replaced, because
    #      that one at least kept work visible.
    #
    # Correct semantics: this session's fold is authoritative for ITS OWN
    # threads (so clearing them means cleared — the 4.9.2 fix survives), while
    # threads owned by other sessions persist untouched. `landing` is carried
    # forward by text identity so hand-authored conditions are not lost.
    _mine = entry["session"]
    # Key inheritance on the STABLE id (falling back to a freshly computed one
    # for legacy threads written before ids existed), never on mutable text.
    _prior_landing = {}
    for t in (digest.get("open_threads") or []):
        if isinstance(t, dict) and t.get("landing"):
            _prior_landing[t.get("id") or thread_id(t.get("text", ""))] = t["landing"]
    _others = [
        t for t in (digest.get("open_threads") or [])
        if isinstance(t, dict) and t.get("session") != _mine
    ]
    _new = []
    for o in entry["open"]:
        tid = o.get("id") or thread_id(o.get("text", ""))
        thread = {"session": _mine, "turn": o["turn"], "text": o["text"], "id": tid}
        # A landing condition supplied by the track wins; otherwise inherit the
        # condition previously carried by the SAME thread id.
        landing = o.get("landing") if isinstance(o, dict) else None
        landing = landing or _prior_landing.get(tid)
        if landing:
            thread["landing"] = landing
        _new.append(thread)
    digest["open_threads"] = _others + _new
    digest["stats"]["turns_read"] += entry["turns"]
    digest["stats"]["entries_kept"] += sum(len(entry[f]) for f in SIGNAL_FIELDS)
    return digest, True


def cmd_bootstrap(args, spoke_root, p):
    digest = load_digest(p)
    if not os.path.isdir(p["sessions"]):
        raise SystemExit(f"resident_digest: no sessions dir at {p['sessions']}")
    sessions = sorted(d for d in os.listdir(p["sessions"]) if d.startswith("session-"))
    folded = 0
    for s in sessions:
        turns, malformed = read_track(p["sessions"], s)
        if not turns:
            continue
        entry, drops = synthesize_session(s, turns)
        log_drops(p, s, drops)
        digest, did = fold(digest, entry, p, malformed)
        folded += int(did)
    save_digest(p, digest)
    print(f"bootstrap: {folded} session(s) folded, {digest['stats']['turns_read']} turns read")
    print(f"digest: {p['digest']}")
    return 0


def cmd_roll(args, spoke_root, p):
    digest = load_digest(p)
    turns, malformed = read_track(p["sessions"], args.session)
    if not turns:
        print(f"roll: no track for {args.session} — nothing to fold")
        return 0
    entry, drops = synthesize_session(args.session, turns)
    log_drops(p, args.session, drops)
    digest, did = fold(digest, entry, p, malformed)
    if not did:
        print(f"roll: {args.session} already folded — no-op")
        return 0
    save_digest(p, digest)
    print(f"roll: folded {args.session} ({entry['turns']} turns, "
          f"{len(entry['decisions'])} decisions, {len(entry['open'])} open)")
    return 0


def cmd_compact(args, spoke_root, p):
    """Fold the oldest warm entries into the cold tier, keeping the newest N warm."""
    digest = load_digest(p)
    keep = args.keep_warm
    if len(digest["warm"]) <= keep:
        print(f"compact: {len(digest['warm'])} warm entries <= keep-warm {keep} — no-op")
        return 0
    to_cold = digest["warm"][:-keep]
    digest["warm"] = digest["warm"][-keep:]
    for entry in to_cold:
        digest["cold"]["summary"].append({
            "session": entry["session"],
            "focus": entry["focus"],
            "decisions": [d["text"] for d in entry["decisions"]],
            "turns": entry["turns"],
        })
        digest["cold"]["sessions_covered"] += 1
    log_drops(p, "compact", [(
        "warm-detail-compacted-to-cold", len(to_cold),
        f"{to_cold[0]['session']}..{to_cold[-1]['session']}")])
    save_digest(p, digest)
    print(f"compact: {len(to_cold)} session(s) warm -> cold; {len(digest['warm'])} kept warm")
    return 0


def cmd_show(args, spoke_root, p):
    digest = load_digest(p)
    if not digest.get("updated_at"):
        print("resident: no digest yet — run `resident_digest.py bootstrap`")
        return 1
    tier = args.tier
    print(f"RESIDENT DIGEST v{digest['digest_version']} — updated {digest['updated_at']}")
    print(f"  sessions folded: {len(digest['sessions_folded'])} | "
          f"turns read: {digest['stats']['turns_read']} | "
          f"warm: {len(digest['warm'])} | cold: {digest['cold']['sessions_covered']}")
    if digest["open_threads"]:
        print(f"\nOPEN THREADS ({len(digest['open_threads'])}):")
        for o in digest["open_threads"]:
            print(f"  - [{o['session']} t{o['turn']}] {o['text']}")
    if tier in ("warm", "all"):
        print(f"\nWARM ({len(digest['warm'])} sessions):")
        for e in digest["warm"][-5:]:
            print(f"  {e['session']}  focus={e['focus']}  "
                  f"{len(e['decisions'])} decisions, {len(e['insights'])} insights")
    if tier in ("cold", "all") and digest["cold"]["summary"]:
        print(f"\nCOLD ({digest['cold']['sessions_covered']} sessions compacted)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spoke-path", help="spoke root (auto-detected if omitted)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("bootstrap", help="one-time full pass over every session track")

    r = sub.add_parser("roll", help="fold ONE session into the digest (savepoint/closeout)")
    r.add_argument("--session", required=True, help="session-YYYYMMDD-HHMM")

    c = sub.add_parser("compact", help="fold oldest warm entries into cold tier")
    c.add_argument("--keep-warm", type=int, default=DEFAULT_KEEP_WARM)

    s = sub.add_parser("show", help="print the digest")
    s.add_argument("--tier", choices=["hot", "warm", "cold", "all"], default="all")

    args = ap.parse_args(argv)
    spoke_root = args.spoke_path or find_spoke_root()
    p = paths(spoke_root)

    return {
        "bootstrap": cmd_bootstrap,
        "roll": cmd_roll,
        "compact": cmd_compact,
        "show": cmd_show,
    }[args.cmd](args, spoke_root, p)


if __name__ == "__main__":
    sys.exit(main())
