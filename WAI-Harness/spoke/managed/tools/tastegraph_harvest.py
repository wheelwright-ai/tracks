#!/usr/bin/env python3
"""tastegraph_harvest.py — the PRODUCER half of the spoke TasteGraph loop.

Everything downstream of `taste.spoke.yaml` has been built and working for
months, and has never once received input:

    taste.spoke.yaml -> compile_tastegraph.py -> tastegraph.json -> vector -> session

`compile_tastegraph.py` reads a spoke slot, maps `accepted` to verified and
`proposed` to inferred, and the wakeup ceremony already surfaces proposed entries
for ratification. But NOTHING writes the file. Measured 2026-07-27 on the master:
`source_files.spoke: null`, `spoke_entries: 0`. Every preference in force came
from the user level. A spoke could not learn anything about itself.

This mines the one corpus that records the operator correcting this spoke: the
session tracks. 391 usable messages on the master, ~23% carrying an explicit
preference marker.

THREE COMMITMENTS, because a bad harvester is worse than none:

  VERBATIM, NOT PARAPHRASED. A proposal's statement is the operator's own
  sentence. A model-written summary of what he meant is a second artifact that
  can drift from the first, and the drift is invisible precisely because the
  summary reads better than the quote.

  PROPOSED IS NEVER BINDING. Harvested entries land as `status: proposed`, which
  compile_tastegraph maps to `inferred`, which the Cardinal rule filters OUT of
  injection. Nothing this tool writes can change behaviour until a human accepts
  it. That is what makes an imperfect miner safe to run.

  SURFACE THE OVERLAP, DO NOT FAKE ADJUDICATING IT. Sole-source spoke preferences
  measured near-zero compliance in s138, so restating org canon as a "new" spoke
  preference would spend the operator's attention to make adherence worse. But
  lexical similarity turned out unable to separate the two on this corpus: a
  candidate scored 0.25 against its own twin while unrelated pairs sat at 0.20.
  So only a near-verbatim restatement (>= DROP_CEILING) is dropped unseen; every
  other candidate carries the NEAREST existing preference and its similarity, and
  the ratifier judges. A threshold tuned into that measured band would have been
  a number that looks like a decision and is actually a coin toss.

Ranked and capped per run, because 90 candidates dumped at once is not a review
queue, it is a wall the operator will (correctly) ignore.

Commands:
    scan      show ranked candidates, write nothing
    propose   append the top N to taste.spoke.yaml as status: proposed
    ratify    accept / reject a proposed entry by id
    status    loop health: proposed / accepted / rejected, and spoke_entries
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - yaml ships with the harness
    yaml = None

DEFAULT_CAP = 5
MIN_SCORE = 3
MIN_LEN, MAX_LEN = 25, 600

# Marker weights. Deliberately conservative: a marker earns its weight only when
# it is an INSTRUCTION about future behaviour, not merely an opinion about the
# task at hand. "always" scores; "this is good" does not, and should not.
MARKERS = [
    (3, "standing", r"\bfrom now on\b|\bgoing forward\b|\bin (?:the )?future\b|\bevery time\b|\beach time\b|\bevery session\b"),
    (3, "prohibition", r"\bnever\b|\bdo not\b|\bdon'?t\b(?!\s+(?:know|think|see|mind))|\bstop\b"),
    (3, "obligation", r"\balways\b|\bmust\b|\bmandatory\b|\bnon-?waivable\b"),
    (2, "expectation", r"\bi (?:want|expect|need|prefer)\b|\bi'?d like\b|\bplease (?:always|never|stop|keep)\b"),
    (2, "substitution", r"\binstead of\b|\brather than\b|\bnot\b[^.]{0,30}\bbut\b"),
    (2, "correction", r"\byou (?:lost|forgot|missed|keep|kept|failed)\b|\bagain\b|\bstill (?:not|no|hasn'?t|didn'?t)\b"),
    (2, "autonomy", r"\b(?:don'?t|do not|no need to|stop) ask(?:ing)?\b|\bwithout asking\b|\bjust do\b|\bproceed\b"),
]

# Messages that are not the operator speaking about behaviour.
SKIP = re.compile(r"^\s*(/|\[background notification|\[system|\[mid-turn)", re.I)


def _now():
    return datetime.now(timezone.utc).isoformat()


def find_repo_root(start=None):
    cur = Path(start or Path(__file__).resolve()).resolve()
    for cand in [cur] + list(cur.parents):
        if (cand / "WAI-Harness").is_dir():
            return cand
    return Path.cwd()


def default_base(root):
    return Path(root) / "WAI-Harness" / "spoke" / "local"


def _load_yaml(p):
    if not p or not Path(p).exists() or yaml is None:
        return {}
    try:
        return yaml.safe_load(Path(p).read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def candidate_id(text):
    """Stable id from the normalised message, so a re-scan never re-proposes it."""
    norm = re.sub(r"\s+", " ", text.strip().lower())
    return "harvest-" + hashlib.sha1(norm.encode("utf-8")).hexdigest()[:12]


def score(text):
    """(total, [marker names]) — how strongly does this read as a standing instruction?"""
    low = text.lower()
    total, names = 0, []
    for weight, name, pat in MARKERS:
        if re.search(pat, low):
            total += weight
            names.append(name)
    return total, names


def read_tracks(base):
    """Yield (session_id, turn, user_msg) for every usable operator message."""
    out = []
    for f in sorted(glob.glob(str(Path(base) / "sessions" / "*" / "track.jsonl"))):
        sid = Path(f).parent.name
        try:
            fh = open(f, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(d, dict):
                    continue
                msg = d.get("user_msg")
                if not isinstance(msg, str):
                    continue
                msg = msg.strip()
                if not (MIN_LEN <= len(msg) <= MAX_LEN) or SKIP.match(msg):
                    continue
                out.append((sid, d.get("turn"), msg))
    return out


def _flatten_text(v):
    """All text inside a preference value. Org `value` is often a nested dict
    (condition / framing_rule / anti_patterns), and str()-ing it would fold JSON
    punctuation and key names into the token set, inflating overlap."""
    if isinstance(v, dict):
        return " ".join(_flatten_text(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return " ".join(_flatten_text(x) for x in v)
    return str(v or "")


def _canon_tokens(text):
    return set(re.findall(r"[a-z]{4,}", _flatten_text(text).lower()))


def user_canon_ids(root, base):
    """(id, token_set) for every preference already in force above the spoke."""
    out = []
    sources = [
        Path(base) / "tastegraph.json",
        Path(root) / "WAI-Harness" / "hub" / "local" / "tastegraph-org.json",
    ]
    for tg in sources:
        try:
            data = json.loads(Path(tg).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        prefs = data.get("preferences")
        if isinstance(prefs, dict):
            prefs = [p for group in prefs.values() if isinstance(group, list) for p in group]
        for p in prefs or []:
            if isinstance(p, dict):
                text = p.get("value") or p.get("statement") or p.get("preference")
                pid = p.get("id") or p.get("key") or "?"
            else:
                text, pid = p, "?"
            toks = _canon_tokens(text)
            if toks:
                out.append((str(pid), toks))
    return out


def user_canon(root, base):
    """Token sets of every preference already in force above the spoke.

    Reads BOTH graphs deliberately. The compiled spoke graph carries ~13 user
    entries; the ORG graph carries the ~123 the session actually receives. A
    first cut checked only the small one and would have proposed a restatement of
    an org preference as if it were new -- exactly the noise that made sole-source
    spoke preferences worthless in s138.
    """
    sets = []
    sources = [
        Path(base) / "tastegraph.json",
        Path(root) / "WAI-Harness" / "hub" / "local" / "tastegraph-org.json",
    ]
    for tg in sources:
        try:
            data = json.loads(Path(tg).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        prefs = data.get("preferences")
        if isinstance(prefs, dict):          # org graph nests by category
            prefs = [p for group in prefs.values() if isinstance(group, list) for p in group]
        for p in prefs or []:
            if isinstance(p, dict):
                text = p.get("value") or p.get("statement") or p.get("preference")
            else:
                text = p
            sets.append(_canon_tokens(str(text)))
    return [s for s in sets if s]


def _overlap(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(min(len(a), len(b)))


def _stopwords(canon, frac=0.12):
    """Tokens too common across the canon to distinguish anything.

    Raw token overlap does not work on this corpus and shipping it would have
    been a silent no-op: measured on the master, a candidate that genuinely
    restates an existing preference (CSRP / worktrees) scored 0.27 against its
    own twin while unrelated pairs sat at 0.20. The signal was inside the noise
    band because the shared words were `operator`, `session`, `harness`, `must` --
    the house vocabulary, present in nearly every preference. Dropping those
    leaves the terms that actually name a subject.
    """
    if not canon:
        return set()
    df = {}
    for s in canon:
        for t in s:
            df[t] = df.get(t, 0) + 1
    ceiling = max(2, int(len(canon) * frac))
    return {t for t, n in df.items() if n > ceiling}


def _rare_overlap(a, b, stop):
    """Overlap measured only on distinguishing tokens."""
    a2, b2 = a - stop, b - stop
    return _overlap(a2, b2)


def existing_entries(base):
    doc = _load_yaml(Path(base) / "taste.spoke.yaml")
    return {str(e.get("id")): e for e in (doc.get("entries") or []) if e.get("id")}


# A restatement this close is near-verbatim and safe to drop unseen. It is set
# ABOVE the measured discrimination band on purpose: lexical similarity could not
# reliably separate a true duplicate (0.25 against its own twin) from an unrelated
# pair (0.18) on this corpus, so the tool does NOT pretend to adjudicate. Below
# the ceiling it ANNOTATES the nearest existing preference and lets the ratifier
# judge. A threshold tuned to fire inside that band would have been a number that
# looks like a decision and is actually a coin toss.
DROP_CEILING = 0.60


def scan(root=None, base=None, cap=DEFAULT_CAP, dup_threshold=DROP_CEILING):
    root = Path(root or find_repo_root())
    base = Path(base or default_base(root))

    seen = existing_entries(base)
    canon = user_canon_ids(root, base)
    stop = _stopwords([t for _, t in canon])
    msgs = read_tracks(base)

    best = {}
    dropped_dupe = 0
    for sid, turn, msg in msgs:
        s, names = score(msg)
        if s < MIN_SCORE:
            continue
        cid = candidate_id(msg)
        if cid in seen:
            continue
        toks = _canon_tokens(msg)

        near_id, near_score = None, 0.0
        for pid, ctoks in canon:
            ov = _rare_overlap(toks, ctoks, stop)
            if ov > near_score:
                near_id, near_score = pid, ov
        if near_score >= dup_threshold:
            dropped_dupe += 1
            continue

        cand = {"id": cid, "score": s, "markers": names, "statement": msg,
                "session_source": sid, "turn": turn,
                "nearest_existing": near_id,
                "nearest_similarity": round(near_score, 3)}
        prev = best.get(cid)
        if prev is None or (s, sid) > (prev["score"], prev["session_source"]):
            best[cid] = cand

    ranked = sorted(best.values(),
                    key=lambda c: (-c["score"], c["session_source"], str(c["turn"])))
    return {"messages_read": len(msgs), "candidates": ranked[:cap],
            "candidates_total": len(ranked), "already_known": len(seen),
            "dropped_as_org_canon": dropped_dupe, "base": str(base)}


def _write_yaml(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True,
                                  default_flow_style=False), encoding="utf-8")
    tmp.replace(path)


def propose(root=None, base=None, cap=DEFAULT_CAP):
    """Append top candidates to taste.spoke.yaml as status: proposed."""
    root = Path(root or find_repo_root())
    base = Path(base or default_base(root))
    res = scan(root=root, base=base, cap=cap)

    path = Path(base) / "taste.spoke.yaml"
    doc = _load_yaml(path)
    if not isinstance(doc, dict):
        doc = {}
    doc.setdefault("entries", [])

    added = []
    for c in res["candidates"]:
        doc["entries"].append({
            "id": c["id"],
            "category": "other",
            # proposed -> inferred -> filtered out of injection. Non-binding by
            # construction; only `ratify --accept` can make it act on anything.
            "status": "proposed",
            "statement": c["statement"],
            "session_source": c["session_source"],
            "proposed_by": "tastegraph_harvest",
            "proposed_at": _now(),
            "evidence": {"markers": c["markers"], "score": c["score"],
                         "turn": c["turn"],
                         "nearest_existing": c.get("nearest_existing"),
                         "nearest_similarity": c.get("nearest_similarity")},
        })
        added.append(c["id"])

    if added:
        _write_yaml(path, doc)
    res["proposed"] = added
    res["path"] = str(path)
    return res


def ratify(entry_id, accept, root=None, base=None, category=None):
    root = Path(root or find_repo_root())
    base = Path(base or default_base(root))
    path = Path(base) / "taste.spoke.yaml"
    doc = _load_yaml(path)
    entries = doc.get("entries") or []
    for e in entries:
        if str(e.get("id")) == entry_id:
            e["status"] = "accepted" if accept else "rejected"
            e["accepted_at" if accept else "rejected_at"] = _now()
            if category:
                e["category"] = category
            _write_yaml(path, doc)
            return {"ok": True, "id": entry_id, "status": e["status"]}
    return {"ok": False, "error": f"no entry {entry_id} in {path}"}


def status(root=None, base=None):
    root = Path(root or find_repo_root())
    base = Path(base or default_base(root))
    entries = list(existing_entries(base).values())
    counts = {}
    for e in entries:
        s = str(e.get("status") or "unknown")
        counts[s] = counts.get(s, 0) + 1
    spoke_entries = None
    try:
        tg = json.loads((Path(base) / "tastegraph.json").read_text(encoding="utf-8"))
        spoke_entries = (tg.get("counts") or {}).get("spoke_entries")
    except (OSError, ValueError):
        pass

    # `compiled_spoke_entries` counts everything SOURCED from the spoke, proposals
    # included -- so it moves the moment this tool writes anything, which makes it
    # useless as a measure of whether the loop closed. `in_force` is the honest
    # number: entries the operator actually accepted, which are the only ones that
    # reach a session. Report both, and never let the first stand in for the second.
    return {"entries": len(entries), "by_status": counts,
            "in_force": counts.get("accepted", 0),
            "compiled_spoke_entries": spoke_entries,
            "path": str(Path(base) / "taste.spoke.yaml")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root")
    ap.add_argument("--base")
    # --json is accepted BEFORE or AFTER the subcommand. Argparse puts parent flags
    # before the subcommand only, which reads as broken to anyone who types the
    # obvious `status --json` -- caught in this tool's own first verification pass.
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _sub(name, **kw):
        s = sub.add_parser(name, **kw)
        s.add_argument("--json", action="store_true", dest="json_sub")
        return s

    p_scan = _sub("scan", help="rank candidates, write nothing")
    p_scan.add_argument("--cap", type=int, default=DEFAULT_CAP)

    p_prop = _sub("propose", help="write top candidates as status: proposed")
    p_prop.add_argument("--cap", type=int, default=DEFAULT_CAP)

    p_rat = _sub("ratify", help="accept or reject a proposed entry")
    p_rat.add_argument("id")
    g = p_rat.add_mutually_exclusive_group(required=True)
    g.add_argument("--accept", action="store_true")
    g.add_argument("--reject", action="store_true")
    p_rat.add_argument("--category")

    _sub("status", help="loop health")

    a = ap.parse_args(argv)
    want_json = a.json or getattr(a, 'json_sub', False)

    if a.cmd == "scan":
        out = scan(root=a.root, base=a.base, cap=a.cap)
    elif a.cmd == "propose":
        out = propose(root=a.root, base=a.base, cap=a.cap)
    elif a.cmd == "ratify":
        out = ratify(a.id, a.accept, root=a.root, base=a.base, category=a.category)
    else:
        out = status(root=a.root, base=a.base)

    if want_json:
        print(json.dumps(out, indent=2))
    elif a.cmd in ("scan", "propose"):
        print(f"tastegraph_harvest {a.cmd}: {out['messages_read']} message(s) read, "
              f"{out['candidates_total']} candidate(s), showing {len(out['candidates'])} "
              f"(known {out['already_known']}, dropped as org canon "
              f"{out['dropped_as_org_canon']})")
        for c in out["candidates"]:
            print(f"  [{c['score']}] {c['id']}  {','.join(c['markers'])}")
            print(f"      {c['statement'][:150]}")
            if c.get("nearest_existing"):
                print(f"      nearest existing: {c['nearest_existing']} "
                      f"(similarity {c['nearest_similarity']} — judge, do not assume)")
        if a.cmd == "propose":
            print(f"  -> {len(out['proposed'])} written as status: proposed (NOT injected "
                  f"until ratified) in {out['path']}")
    else:
        print(json.dumps(out, indent=2))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
