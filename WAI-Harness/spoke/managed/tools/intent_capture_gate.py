#!/usr/bin/env python3
"""Incorporation Gate: nothing discussed leaves a session as prose.

Reads the session track (Layer-1 turn entries: decisions[], open[], insights)
and reconciles every captured intent against artifacts that exist on disk
(lugs / initiatives / plans / memory-noted wont-dos created or touched during
the session window). Output = the reconciliation list the closeout ceremony
MUST drain: each MISSING intent becomes a lug (full or seed) or an explicit
wont-do entry before the exit verdict may render SAFE.

The matcher is deliberately mechanical and recall-biased: it surfaces
candidates for the closing agent/human to confirm; it never silently decides
an intent was captured. False-positive MISSING is cheap (one glance);
false-negative (silent loss) is the failure class this tool exists to kill.

spec: spec-incorporation-gate-v1
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

STOPWORDS = {
    "the", "a", "an", "to", "of", "for", "and", "or", "in", "on", "with",
    "via", "per", "as", "is", "are", "be", "this", "that", "it", "its",
    "we", "our", "my", "not", "no", "never", "now", "then", "at", "by",
    "from", "into", "over", "under", "vs", "will", "must", "should",
}


def _tokens(text):
    words = re.findall(r"[a-z0-9][a-z0-9_-]{2,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def _intent_text(item):
    """The intent sentence from a track entry, whatever schema wrote it.

    Track schema v2.0.2 made `open` entries OBJECTS carrying a machine-checkable
    landing condition: {"text": ..., "landing": {...}}. `decisions` stayed strings.
    The original loader accepted `str` only, so from the day the landing contract
    shipped this gate silently dropped every `open` entry it was built to police.
    Measured on session-20260728-1855 before the fix: 18 intents on disk, 7 read,
    11 dropped, verdict PASS. A gate whose whole purpose is killing silent loss
    must not be the thing losing them.

    Returns (text, landing) with landing None when the entry carries none.
    """
    if isinstance(item, str):
        return item.strip(), None
    if isinstance(item, dict):
        text = item.get("text") or item.get("intent") or item.get("what") or ""
        if isinstance(text, str):
            landing = item.get("landing")
            return text.strip(), landing if isinstance(landing, dict) else None
    return "", None


def load_track_intents(track_path):
    """Every decisions[] and open[] intent from every turn, deduped, with turn refs.

    Accepts both shapes: bare strings (decisions, legacy open) and landing-contract
    objects (open, v2.0.2+). An entry whose text cannot be recovered is COUNTED as
    unparsed rather than dropped -- silence is the failure class here."""
    intents = {}
    unparsed = 0
    with open(track_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            turn = row.get("turn", "?")
            for field in ("decisions", "open"):
                for item in row.get(field) or []:
                    text, landing = _intent_text(item)
                    if not text or len(text) < 12:
                        if item:
                            unparsed += 1
                        continue
                    entry = intents.setdefault(
                        text, {"field": field, "turns": [], "landing": None})
                    entry["turns"].append(turn)
                    if landing and not entry["landing"]:
                        entry["landing"] = landing
    return intents, unparsed


def load_artifacts(base, since_iso):
    """Artifact corpus: lug/initiative/plan files modified since the session start."""
    since = datetime.fromisoformat(since_iso).timestamp() if since_iso else 0
    corpus = []
    roots = [
        os.path.join(base, "lugs", "bytype"),
        os.path.join(base, "initiatives"),
        os.path.join(base, "plans"),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                if not name.endswith((".json", ".md")):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    if os.path.getmtime(path) < since:
                        continue
                    with open(path, encoding="utf-8") as fh:
                        text = fh.read()
                except OSError:
                    continue
                corpus.append({
                    "path": os.path.relpath(path, base),
                    "tokens": _tokens(name + " " + text[:4000]),
                })
    return corpus


def resolve_landing(landing, base):
    """Deterministic capture check for a landing condition. No lexical guessing.

    An `open` entry under the landing contract already names the artifact that
    proves it. Where it does, believe the artifact and not a token-overlap score:
    a lug id either exists on disk or it does not.

    Returns (state, evidence) where state is:
      'captured'   -- the named artifact exists (the ask IS tracked)
      'missing'    -- the landing names an artifact that does not exist
      None         -- not resolvable here; fall back to the lexical matcher
    """
    if not landing:
        return None, None
    kind = landing.get("kind")
    if kind == "lug_completed":
        lug_id = landing.get("id")
        if not lug_id:
            return None, None
        root = os.path.join(base, "lugs")
        if not os.path.isdir(root):
            return None, None
        for dirpath, _dirs, files in os.walk(root):
            if lug_id + ".json" in files:
                return "captured", os.path.relpath(os.path.join(dirpath, lug_id + ".json"), base)
        return "missing", "no lug file named %s.json anywhere under lugs/" % lug_id
    if kind == "file_exists":
        path = landing.get("path")
        if not path:
            return None, None
        if os.path.exists(path) or os.path.exists(os.path.join(base, path)):
            return "captured", path
        return "missing", "landing names %s, which does not exist" % path
    # command / commit / file_contains / manual are runtime conditions, not
    # capture evidence -- an ask can be legitimately tracked and still unlanded.
    return None, None


def reconcile(intents, corpus, threshold=0.35, base="."):
    report = {"captured": [], "missing": []}
    for text, meta in intents.items():
        itoks = _tokens(text)
        if not itoks:
            continue
        landing = meta.get("landing")
        state, evidence = resolve_landing(landing, base)
        entry = {
            "intent": text[:200],
            "field": meta["field"],
            "turns": meta["turns"][:6],
            "landing_kind": (landing or {}).get("kind"),
        }
        if state is not None:
            # Deterministic: the landing named an artifact. Believe it.
            entry["best_match"] = evidence if state == "captured" else None
            entry["score"] = 1.0 if state == "captured" else 0.0
            entry["basis"] = "landing"
            if state == "missing":
                entry["reason"] = evidence
            report["captured" if state == "captured" else "missing"].append(entry)
            continue
        best, best_score = None, 0.0
        for art in corpus:
            overlap = len(itoks & art["tokens"]) / max(len(itoks), 1)
            if overlap > best_score:
                best, best_score = art["path"], overlap
        entry["best_match"] = best
        entry["score"] = round(best_score, 2)
        entry["basis"] = "lexical"
        (report["captured"] if best_score >= threshold else report["missing"]).append(entry)
    report["missing"].sort(key=lambda e: e["score"])
    return report


def emit_seed_lugs(missing, base, session_id=None, now_iso=None):
    """Turn each MISSING intent into a seed lug carrying the ask VERBATIM.

    VERBATIM IS THE WHOLE POINT. A summarised ask is a second artifact that
    drifts from what was actually said, and the drift is invisible -- by the time
    anyone reads the lug, the sentence it came from is buried in a track file.
    `verbatim` holds the recorded sentence untouched; `title` is a truncation of
    it, never a rewording.

    A seed lug is a sanctioned tier, not a placeholder: it carries full PEV plus
    the provenance needed to resume. Deterministic id (hash of the intent text)
    so re-running the gate re-finds the same lug instead of minting duplicates.

    Returns (created, existing) as lists of lug ids.
    """
    now = now_iso or datetime.now(timezone.utc).isoformat()
    out_dir = os.path.join(base, "lugs", "bytype", "task", "open")
    os.makedirs(out_dir, exist_ok=True)
    lug_root = os.path.join(base, "lugs")
    created, existing = [], []
    for entry in missing:
        text = entry.get("intent", "").strip()
        if not text:
            continue
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
        lug_id = "ask-%s-v1" % digest
        # Idempotent across status dirs: if it already exists anywhere, leave it.
        found = False
        for dirpath, _dirs, files in os.walk(lug_root):
            if lug_id + ".json" in files:
                found = True
                break
        if found:
            existing.append(lug_id)
            continue
        title = text if len(text) <= 100 else text[:97].rstrip() + "..."
        lug = {
            "id": lug_id,
            "type": "task",
            "status": "open",
            "va": "grind",
            "routed_to": "LOCAL",
            "tier": "seed",
            "title": title,
            "verbatim": text,
            "perceive": (
                "Recorded in session %s (turn(s) %s) as a %s entry and reconciled "
                "against artifacts on disk by intent_capture_gate.py: no lug, "
                "initiative or plan carries it. The ask exists only as prose.\n\n"
                "VERBATIM AS RECORDED:\n%s" % (
                    session_id or "unknown", entry.get("turns"),
                    entry.get("field", "?"), text)),
            "execute": (
                "Scope this ask into real work, or close it as an explicit wont-do "
                "with a reason. Do not delete it silently -- that is the failure "
                "class the gate exists to prevent."),
            "verify": [
                "the ask is either implemented and certified, or closed with a "
                "recorded wont-do reason",
                "intent_capture_gate.py no longer reports this intent as MISSING",
            ],
            "file_targets": [],
            "created_at": now,
            "created_by": "intent_capture_gate.emit_seed_lugs",
            "source_session": session_id,
            "source_field": entry.get("field"),
            "source_turns": entry.get("turns"),
            "epic": "epic-close-the-presumption-gap-v1",
        }
        with open(os.path.join(out_dir, lug_id + ".json"), "w", encoding="utf-8") as fh:
            json.dump(lug, fh, indent=2)
        created.append(lug_id)
    return created, existing


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--track", required=True, help="session track.jsonl")
    ap.add_argument("--base", default="WAI-Harness/spoke/local", help="spoke data base")
    ap.add_argument("--since", default=None, help="session start ISO ts (default: track first entry date)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.35)
    ap.add_argument("--emit-lugs", action="store_true",
                    help="write a seed lug per MISSING intent, carrying the ask verbatim")
    ap.add_argument("--session-id", default=None,
                    help="provenance stamped onto emitted lugs")
    args = ap.parse_args(argv)

    since = args.since
    if since is None:
        with open(args.track, encoding="utf-8") as fh:
            for line in fh:
                try:
                    since = json.loads(line).get("ts")
                    break
                except (json.JSONDecodeError, AttributeError):
                    continue
    if since is None:
        since = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")
    # date-floor so artifacts from the whole session day count
    since = since[:10] + "T00:00:00+00:00"

    intents, unparsed = load_track_intents(args.track)
    corpus = load_artifacts(args.base, since)
    report = reconcile(intents, corpus, args.threshold, base=args.base)
    by_landing = sum(1 for e in report["captured"] + report["missing"]
                     if e.get("basis") == "landing")
    report["summary"] = {
        "intents": len(intents),
        "artifacts_in_window": len(corpus),
        "captured": len(report["captured"]),
        "missing": len(report["missing"]),
        "resolved_by_landing": by_landing,
        "unparsed_entries": unparsed,
        "gate": "PASS" if not report["missing"] else "DRAIN REQUIRED: every missing intent becomes a lug or a wont-do before exit",
    }
    if args.emit_lugs and report["missing"]:
        created, existing = emit_seed_lugs(
            report["missing"], args.base, session_id=args.session_id)
        report["emitted"] = {"created": created, "already_present": existing}
        report["summary"]["lugs_created"] = len(created)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        s = report["summary"]
        print(f"INCORPORATION GATE: {s['intents']} intents | {s['captured']} captured | {s['missing']} MISSING")
        print(f"  ({by_landing} resolved deterministically by landing condition, "
              f"{len(intents) - by_landing} by lexical match)")
        if unparsed:
            print(f"  WARNING: {unparsed} track entr(ies) carried no recoverable intent text")
        for e in report["missing"]:
            why = e.get("reason") or f"best {e['score']}"
            print(f"  MISSING (t{e['turns']}, {why}): {e['intent'][:120]}")
        if "emitted" in report:
            em = report["emitted"]
            print(f"  EMITTED: {len(em['created'])} seed lug(s) created"
                  f"{', ' + str(len(em['already_present'])) + ' already present' if em['already_present'] else ''}")
            for lug_id in em["created"]:
                print(f"    + {lug_id}")
        print(f"  -> {s['gate']}")
    return 0 if not report["missing"] else 10


if __name__ == "__main__":
    sys.exit(main())
