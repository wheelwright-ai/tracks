#!/usr/bin/env python3
"""sawyer.py -- the consideration advisor.

A sawyer judges raw timber before it becomes anything: what is usable, what is
punky, what needs seasoning. Sawyer does that for ideas, and then does the
thing that actually matters on this spoke: it comes back and checks whether
what was agreed ever LANDED, and whether it still works.

Context: the operator generates ideas far faster than they land (measured
12.79/day generated against 0.93/day landed). This spoke's documented failure
mode is built-but-never-wired -- work deployed, reported done, never actually
in service. Sawyer is the standing answer to "did the thing we agreed on
actually happen, and is it still happening."

Exactly five verbs. No daemon, no cron, no LLM calls. Sawyer orchestrates
records and runs shell checks; the model work happens outside it.

  intake   <file> [--title T]            split a prose file into ITEMS, dedup
                                         against every prior decision/tombstone
  brief    <id>                          emit a stage-1 EVIDENCE brief (factual
                                         on-disk questions only; UNKNOWN is a
                                         valid answer; judging is forbidden)
  decide   <id> --item N --verdict V     record a verdict; adopt/adapt REFUSE
           --why "..."                   without --landing-check (the forcing
           [--landing-check CMD]         function against built-but-never-wired)
           [--lug ID] [--revisit-after DATE]
  land     [--json]                      run every landing_check; classify
                                         LANDED / HOLDING / NOT_LANDED /
                                         REGRESSED; exit non-zero on REGRESSED
                                         or NOT_LANDED older than 14 days
  status   [--json]                      counts, oldest NOT_LANDED, seasonings due

Data (this spoke only, created on demand):
  WAI-Harness/spoke/local/advisors/sawyer/considerations/   one record per intake
  WAI-Harness/spoke/local/advisors/sawyer/decisions/        one record per verdict
  WAI-Harness/spoke/local/advisors/sawyer/tombstones/       rejected ideas

The REGRESSED vs NOT_LANDED split is the operator's explicit ask: "never got
built" and "was built and has rotted" need different responses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LAND_TIMEOUT_S = 120
NOT_LANDED_STALE_DAYS = 14

VERDICTS = ("adopt", "adapt", "reject", "season")


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    override = os.environ.get("SAWYER_REPO_ROOT")
    if override:
        return Path(override).resolve()
    # .../WAI-Harness/spoke/managed/tools/sawyer.py -> repo root is parents[4]
    return Path(__file__).resolve().parents[4]


def _data_root() -> Path:
    override = os.environ.get("SAWYER_DATA_DIR")
    if override:
        return Path(override).resolve()
    return (_repo_root() / "WAI-Harness" / "spoke" / "local"
            / "advisors" / "sawyer")


def _dirs(root: Path | None = None):
    root = root or _data_root()
    return {
        "considerations": root / "considerations",
        "decisions": root / "decisions",
        "tombstones": root / "tombstones",
    }


def _ensure_dirs():
    for d in _dirs().values():
        d.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# intake: splitting + fingerprints
# ---------------------------------------------------------------------------

# item-boundary markers: markdown headings, numbered items, bold leads
_BOUNDARY_RE = re.compile(r"^(#{1,3}\s|\d+\.\s|\*\*)")


def split_items(text: str) -> list[str]:
    """Split prose into items on headings / numbered items / bold leads.

    If nothing matches, the whole file is one item.
    """
    items: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if _BOUNDARY_RE.match(line) and current:
            items.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        items.append(current)
    chunks = ["\n".join(c).strip() for c in items]
    chunks = [c for c in chunks if c]
    if not chunks:
        return [text.strip()] if text.strip() else []
    return chunks


_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


def normalize_text(text: str) -> str:
    """Lowercase, whitespace-collapse, punctuation stripped."""
    t = text.lower()
    t = _PUNCT_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t).strip()
    return t


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def _item_title(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    first = re.sub(r"^#{1,3}\s+", "", first)
    first = re.sub(r"^\d+\.\s+", "", first)
    first = first.strip("*").strip()
    return first[:80] if first else "(untitled)"


def _load_all(d: Path) -> list[dict]:
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def _prior_verdicts() -> dict[str, dict]:
    """fingerprint -> prior decision/tombstone summary, for dedup."""
    priors: dict[str, dict] = {}
    for t in _load_all(_dirs()["tombstones"]):
        priors[t["fingerprint"]] = {
            "verdict": "reject",
            "reason": t.get("reason", ""),
            "date": t.get("rejected_at", ""),
        }
    for dec in _load_all(_dirs()["decisions"]):
        priors[dec["fingerprint"]] = {
            "verdict": dec.get("verdict", ""),
            "reason": dec.get("why", ""),
            "date": dec.get("decided_at", ""),
        }
    return priors


def _next_consideration_id() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"C-{today}-"
    existing = [c.get("id", "") for c in _load_all(_dirs()["considerations"])]
    n = 1
    for cid in existing:
        if cid.startswith(prefix):
            try:
                n = max(n, int(cid.rsplit("-", 1)[1]) + 1)
            except ValueError:
                continue
    return f"{prefix}{n:03d}"


# ---------------------------------------------------------------------------
# verbs
# ---------------------------------------------------------------------------

def cmd_intake(args) -> int:
    src = Path(args.file)
    if not src.exists():
        print(f"intake: file not found: {src}", file=sys.stderr)
        return 2
    _ensure_dirs()
    text = src.read_text()
    chunks = split_items(text)
    if not chunks:
        print("intake: file is empty", file=sys.stderr)
        return 2

    priors = _prior_verdicts()
    cid = _next_consideration_id()
    items = []
    n_dupes = 0
    for i, chunk in enumerate(chunks, 1):
        fp = fingerprint(chunk)
        prior = priors.get(fp)
        item = {
            "n": i,
            "id": f"{cid}#{i}",
            "title": _item_title(chunk),
            "text": chunk,
            "fingerprint": fp,
            "status": "already_decided" if prior else "pending",
            "prior": prior,
        }
        if prior:
            n_dupes += 1
        items.append(item)

    record = {
        "id": cid,
        "title": args.title or src.stem,
        "source_file": str(src),
        "created_at": _now_iso(),
        "items": items,
    }
    _atomic_write_json(_dirs()["considerations"] / f"{cid}.json", record)

    print(f"consideration: {cid}  ({len(items)} item(s), {n_dupes} already decided)")
    print(f"{'#':<4} {'status':<17} title")
    for it in items:
        print(f"{it['n']:<4} {it['status']:<17} {it['title']}")
    for it in items:
        if it["status"] == "already_decided":
            p = it["prior"]
            print(f"ALREADY DECIDED: {it['id']} -- prior verdict "
                  f"'{p['verdict']}' ({p['date']}): {p['reason']}")
    return 0


def cmd_brief(args) -> int:
    cons = _dirs()["considerations"] / f"{args.id}.json"
    if not cons.exists():
        print(f"brief: no consideration {args.id}", file=sys.stderr)
        return 2
    record = json.loads(cons.read_text())
    undecided = [it for it in record["items"] if it["status"] == "pending"]

    # data_root is <base>/advisors/sawyer; runtime is <base>/runtime
    out = _data_root().parent.parent / "runtime"
    out.mkdir(parents=True, exist_ok=True)
    brief_path = out / f"sawyer-brief-{args.id}.md"

    lines = [
        f"# Sawyer evidence brief -- {record['id']}: {record['title']}",
        "",
        "STAGE 1: EVIDENCE ONLY.",
        "",
        "- Do NOT judge the items. Do NOT recommend. Do NOT build anything.",
        "- Answer only factual, on-disk questions: does this exist here, where,",
        "  what would it touch, what breaks.",
        "- UNKNOWN is an acceptable answer. State it plainly; do not guess.",
        "",
        f"Source: {record['source_file']}  (intaken {record['created_at']})",
        "",
        f"## Undecided items ({len(undecided)})",
        "",
    ]
    for it in undecided:
        lines += [
            f"### {it['id']} -- {it['title']}",
            "",
            it["text"],
            "",
            "Questions (evidence only):",
            "1. Does something serving this already exist here? Where (file:line)?",
            "2. What files/surfaces would this touch if built?",
            "3. What breaks or goes stale if this lands? What breaks if it does not?",
            "",
        ]
    if not undecided:
        lines.append("(none -- every item was already decided)")
        lines.append("")
    brief_path.write_text("\n".join(lines))
    print(f"brief: {brief_path}")
    print(f"undecided items: {len(undecided)}")
    return 0


def _decision_path(cid: str, n: int) -> Path:
    return _dirs()["decisions"] / f"{cid}--item{n}.json"


def cmd_decide(args) -> int:
    cons = _dirs()["considerations"] / f"{args.id}.json"
    if not cons.exists():
        print(f"decide: no consideration {args.id}", file=sys.stderr)
        return 2
    record = json.loads(cons.read_text())
    item = next((it for it in record["items"] if it["n"] == args.item), None)
    if item is None:
        print(f"decide: no item {args.item} in {args.id}", file=sys.stderr)
        return 2

    if args.verdict in ("adopt", "adapt") and not args.landing_check:
        # THE FORCING FUNCTION. An agreed behaviour with no way to prove it
        # landed is how this spoke accumulated its built-but-never-wired debt.
        print(
            "decide: REFUSED -- verdict "
            f"'{args.verdict}' requires --landing-check \"<shell command>\".\n"
            "An agreed behaviour with no way to prove it landed is how this\n"
            "spoke accumulated its built-but-never-wired debt. Provide a\n"
            "command that exits 0 only when the behaviour is live.",
            file=sys.stderr,
        )
        return 2

    if args.verdict == "season" and not args.revisit_after:
        print("decide: REFUSED -- verdict 'season' requires "
              "--revisit-after <ISO date>", file=sys.stderr)
        return 2

    _ensure_dirs()
    now = _now_iso()
    dec = {
        "id": item["id"],
        "consideration": record["id"],
        "item": item["n"],
        "item_title": item["title"],
        "fingerprint": item["fingerprint"],
        "verdict": args.verdict,
        "why": args.why,
        "decided_at": now,
        "landing_check": args.landing_check,
        "lug": args.lug,
        "revisit_after": args.revisit_after,
        "landed_at": None,
        "landing_history": [],
    }
    _atomic_write_json(_decision_path(record["id"], item["n"]), dec)

    if args.verdict == "reject":
        tomb = {
            "fingerprint": item["fingerprint"],
            "reason": args.why,
            "rejected_at": now,
            "decision_id": item["id"],
            "item_title": item["title"],
        }
        _atomic_write_json(
            _dirs()["tombstones"] / f"{item['fingerprint'][:16]}.json", tomb)
        print(f"reject: tombstone written for {item['id']} "
              f"(future intakes of this idea return this verdict)")

    print(f"decide: {item['id']} -> {args.verdict}")
    return 0


def _classify(dec: dict, exit_code: int) -> str:
    previously_landed = dec.get("landed_at") is not None
    if exit_code == 0:
        return "HOLDING" if previously_landed else "LANDED"
    return "REGRESSED" if previously_landed else "NOT_LANDED"


def _days_old(iso_ts: str) -> float:
    try:
        then = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    return (datetime.now(timezone.utc) - then).total_seconds() / 86400.0


def _run_landing_checks(decisions: list[dict]) -> list[dict]:
    """Run every adopt/adapt landing_check. Returns per-decision run rows."""
    rows = []
    root = _repo_root()
    for dec in decisions:
        if dec.get("verdict") not in ("adopt", "adapt"):
            continue
        check = dec.get("landing_check")
        if not check:
            continue
        try:
            proc = subprocess.run(
                check, shell=True, cwd=str(root),
                capture_output=True, text=True, timeout=LAND_TIMEOUT_S,
            )
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code = 124
        cls = _classify(dec, code)
        ts = _now_iso()
        if cls == "LANDED":
            dec["landed_at"] = ts
        dec.setdefault("landing_history", []).append(
            {"ts": ts, "exit": code, "class": cls})
        _atomic_write_json(
            _decision_path(dec["consideration"], dec["item"]), dec)
        rows.append({"decision": dec, "exit": code, "class": cls})
    return rows


def cmd_land(args) -> int:
    _ensure_dirs()
    decisions = _load_all(_dirs()["decisions"])
    rows = _run_landing_checks(decisions)

    order = {"REGRESSED": 0, "NOT_LANDED": 1, "LANDED": 2, "HOLDING": 3}
    rows.sort(key=lambda r: (order.get(r["class"], 9), r["decision"]["id"]))

    if args.json:
        print(json.dumps([{
            "id": r["decision"]["id"],
            "class": r["class"],
            "exit": r["exit"],
            "landing_check": r["decision"].get("landing_check"),
            "decided_at": r["decision"].get("decided_at"),
            "landed_at": r["decision"].get("landed_at"),
        } for r in rows], indent=2))
    else:
        print(f"{'class':<12} {'exit':<5} {'id':<22} check")
        for r in rows:
            d = r["decision"]
            print(f"{r['class']:<12} {r['exit']:<5} {d['id']:<22} "
                  f"{d.get('landing_check', '')}")

    regressed = [r for r in rows if r["class"] == "REGRESSED"]
    stale_not_landed = [
        r for r in rows
        if r["class"] == "NOT_LANDED"
        and _days_old(r["decision"]["decided_at"]) > NOT_LANDED_STALE_DAYS
    ]
    if not args.json:
        print(f"\nREGRESSED: {len(regressed)}  "
              f"NOT_LANDED>14d: {len(stale_not_landed)}  "
              f"LANDED: {sum(1 for r in rows if r['class'] == 'LANDED')}  "
              f"HOLDING: {sum(1 for r in rows if r['class'] == 'HOLDING')}")
    if regressed or stale_not_landed:
        # A checker that cannot fail is not a checker.
        return 1
    return 0


def cmd_status(args) -> int:
    _ensure_dirs()
    decisions = _load_all(_dirs()["decisions"])
    considerations = _load_all(_dirs()["considerations"])

    by_verdict: dict[str, int] = {}
    for d in decisions:
        by_verdict[d["verdict"]] = by_verdict.get(d["verdict"], 0) + 1

    by_class: dict[str, int] = {}
    oldest_not_landed = None
    for d in decisions:
        last = (d.get("landing_history") or [None])[-1]
        if last:
            cls = last["class"]
            by_class[cls] = by_class.get(cls, 0) + 1
            if cls == "NOT_LANDED":
                if (oldest_not_landed is None
                        or d["decided_at"] < oldest_not_landed["decided_at"]):
                    oldest_not_landed = d
        elif d["verdict"] in ("adopt", "adapt"):
            by_class["NEVER_RUN"] = by_class.get("NEVER_RUN", 0) + 1
            if (oldest_not_landed is None
                    or d["decided_at"] < oldest_not_landed["decided_at"]):
                oldest_not_landed = d

    today = datetime.now(timezone.utc).date()
    season_due = [
        d for d in decisions
        if d.get("verdict") == "season" and d.get("revisit_after")
        and d["revisit_after"][:10] <= today.isoformat()
    ]

    summary = {
        "considerations": len(considerations),
        "decisions": len(decisions),
        "by_verdict": by_verdict,
        "by_landing_class": by_class,
        "oldest_not_landed": (
            {"id": oldest_not_landed["id"],
             "decided_at": oldest_not_landed["decided_at"],
             "title": oldest_not_landed["item_title"]}
            if oldest_not_landed else None),
        "seasoning_due": [
            {"id": d["id"], "revisit_after": d["revisit_after"],
             "title": d["item_title"]} for d in season_due],
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"considerations: {summary['considerations']}  "
              f"decisions: {summary['decisions']}")
        print("by verdict: " + (", ".join(
            f"{k}={v}" for k, v in sorted(by_verdict.items())) or "(none)"))
        print("by landing class: " + (", ".join(
            f"{k}={v}" for k, v in sorted(by_class.items())) or "(none)"))
        if oldest_not_landed:
            print(f"oldest NOT_LANDED: {oldest_not_landed['id']} "
                  f"({oldest_not_landed['decided_at']}) "
                  f"{oldest_not_landed['item_title']}")
        if season_due:
            print("seasoning due:")
            for d in season_due:
                print(f"  {d['id']} revisit {d['revisit_after']} -- {d['title']}")
    return 0


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        prog="sawyer",
        description="Sawyer -- the consideration advisor. Judges ideas, then "
                    "checks whether what was agreed ever landed.")
    sub = ap.add_subparsers(dest="verb", required=True)

    p = sub.add_parser("intake", help="split a prose file into items, dedup")
    p.add_argument("file")
    p.add_argument("--title", default=None)
    p.set_defaults(fn=cmd_intake)

    p = sub.add_parser("brief", help="emit a stage-1 EVIDENCE brief")
    p.add_argument("id")
    p.set_defaults(fn=cmd_brief)

    p = sub.add_parser("decide", help="record a verdict on one item")
    p.add_argument("id")
    p.add_argument("--item", type=int, required=True)
    p.add_argument("--verdict", choices=VERDICTS, required=True)
    p.add_argument("--why", required=True)
    p.add_argument("--landing-check", default=None,
                   help="shell command, exit 0 == the behaviour is live "
                        "(mandatory for adopt/adapt)")
    p.add_argument("--lug", default=None)
    p.add_argument("--revisit-after", default=None,
                   help="ISO date (mandatory for season)")
    p.set_defaults(fn=cmd_decide)

    p = sub.add_parser("land", help="run landing checks, classify, fail loudly")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_land)

    p = sub.add_parser("status", help="counts, oldest NOT_LANDED, seasonings due")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_status)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
