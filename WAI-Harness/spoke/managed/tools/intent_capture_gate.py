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


def load_track_intents(track_path):
    """Every decisions[] and open[] string from every turn, deduped, with turn refs."""
    intents = {}
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
                    if not isinstance(item, str) or len(item) < 12:
                        continue
                    key = item.strip()
                    intents.setdefault(key, {"field": field, "turns": []})
                    intents[key]["turns"].append(turn)
    return intents


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


def reconcile(intents, corpus, threshold=0.35):
    report = {"captured": [], "missing": []}
    for text, meta in intents.items():
        itoks = _tokens(text)
        if not itoks:
            continue
        best, best_score = None, 0.0
        for art in corpus:
            overlap = len(itoks & art["tokens"]) / max(len(itoks), 1)
            if overlap > best_score:
                best, best_score = art["path"], overlap
        entry = {
            "intent": text[:200],
            "field": meta["field"],
            "turns": meta["turns"][:6],
            "best_match": best,
            "score": round(best_score, 2),
        }
        (report["captured"] if best_score >= threshold else report["missing"]).append(entry)
    report["missing"].sort(key=lambda e: e["score"])
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--track", required=True, help="session track.jsonl")
    ap.add_argument("--base", default="WAI-Harness/spoke/local", help="spoke data base")
    ap.add_argument("--since", default=None, help="session start ISO ts (default: track first entry date)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.35)
    args = ap.parse_args()

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

    intents = load_track_intents(args.track)
    corpus = load_artifacts(args.base, since)
    report = reconcile(intents, corpus, args.threshold)
    report["summary"] = {
        "intents": len(intents),
        "artifacts_in_window": len(corpus),
        "captured": len(report["captured"]),
        "missing": len(report["missing"]),
        "gate": "PASS" if not report["missing"] else "DRAIN REQUIRED: every missing intent becomes a lug or a wont-do before exit",
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        s = report["summary"]
        print(f"INCORPORATION GATE: {s['intents']} intents | {s['captured']} captured | {s['missing']} MISSING")
        for e in report["missing"]:
            print(f"  MISSING (t{e['turns']}, best {e['score']}): {e['intent'][:120]}")
        print(f"  -> {s['gate']}")
    return 0 if not report["missing"] else 10


if __name__ == "__main__":
    sys.exit(main())
