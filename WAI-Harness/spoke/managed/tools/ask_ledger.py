#!/usr/bin/env python3
"""ask_ledger.py -- every operator ask, enumerated, with its state and its evidence.

OPERATOR DIRECTIVE, 2026-08-22, verbatim:

    "Whenever I ask for something, I'd like you to enumerate the ask and store them in a
    way that assures it's been heard and whether or not it's been responded, reacted to.
    This will give us clear marching orders. And if we need adversarial check, do so. This
    is a excellent service that Ozzy can perform and tag to a session and an initiative."

WHY IT WAS ASKED FOR, measured in the session that produced it. Across roughly a dozen
turns the operator issued at least nine distinct asks. They were tracked in conversation
context and nowhere else, so:

  * a compaction or a crash would have erased the marching orders entirely;
  * two asks ("split the log, don't lose data", "deliver the right code then warm it")
    arrived while a long tool call was running and were answered several minutes late;
  * nothing anywhere could answer "which of his asks are still open?" without re-reading
    the whole transcript -- which is exactly the reconstruction cost his voice contract
    exists to eliminate.

THE STATES ARE DELIBERATELY NOT A PROGRESS BAR. "responded" and "landed" are different
claims and the gap between them is where this harness has historically lied to itself:

  heard        recorded verbatim. Costs nothing and is never skipped -- an ask that is
               only in context is an ask that a compaction can delete.
  responded    answered in words. NOT the same as done, and must never be reported as done.
  landed       done AND carrying evidence -- a commit sha, a measurement, a file path.
               `landed` without evidence is refused by validate(), because "I did it" is
               the claim this whole object model exists to stop taking on faith.
  refused      deliberately not done, with a stated reason. A legitimate terminal state.
  deferred     not now, with a named condition for resuming. Also terminal for this session.

ADVERSARIAL CHECK is per-ask and OFF by default, because marking everything for review
trains everyone to skip the review. It is for asks whose completion is a judgement call
rather than a fact -- where the author grading their own work is the failure mode.

CLI:
    ask_ledger.py add --session S --verbatim "..." [--item "..." ...] [--initiative I]
    ask_ledger.py state <ask_id> --state landed --evidence "commit abc123" [--item N]
    ask_ledger.py list [--session S] [--open-only]
    ask_ledger.py report [--session S]        # the marching-orders block
    ask_ledger.py validate                    # non-zero if any record is dishonest
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

STATES = ("heard", "responded", "landed", "refused", "deferred")
TERMINAL = ("landed", "refused", "deferred")
OPEN = ("heard", "responded")


def _store(base):
    p = Path(base) / "asks"
    p.mkdir(parents=True, exist_ok=True)
    return p / "asks.jsonl"


def _read(base):
    f = _store(base)
    out = []
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:  # noqa: BLE001 -- one bad line must not hide the rest
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _write_all(base, records):
    f = _store(base)
    tmp = f.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                   encoding="utf-8")
    os.replace(tmp, f)


def next_id(base, session):
    n = sum(1 for r in _read(base) if r.get("session") == session) + 1
    return f"ask-{session}-{n:03d}"


def add(base, session, verbatim, items, initiative="", ts="", adversarial=False):
    """Record an ask VERBATIM plus its enumeration.

    The verbatim text is kept because an enumeration is an interpretation, and the
    interpretation is the thing most likely to be wrong. Keeping only the parsed items
    would make a misreading unfalsifiable later.
    """
    rec = {
        "ask_id": next_id(base, session),
        "session": session,
        "initiative": initiative,
        "ts": ts,
        "verbatim": verbatim,
        "items": [{"n": i + 1, "text": t, "state": "heard",
                   "evidence": [], "note": ""} for i, t in enumerate(items or [verbatim])],
        "adversarial_check": bool(adversarial),
        "adversarial_result": None,
    }
    recs = _read(base)
    recs.append(rec)
    _write_all(base, recs)
    return rec


def set_state(base, ask_id, state, evidence="", item=None, note=""):
    if state not in STATES:
        raise SystemExit(f"unknown state {state!r}; valid: {', '.join(STATES)}")
    recs = _read(base)
    hit = False
    for r in recs:
        if r.get("ask_id") != ask_id:
            continue
        for it in r.get("items", []):
            if item is not None and it.get("n") != item:
                continue
            it["state"] = state
            if evidence:
                it.setdefault("evidence", []).append(evidence)
            if note:
                it["note"] = note
            hit = True
    if not hit:
        raise SystemExit(f"no such ask/item: {ask_id} item={item}")
    _write_all(base, recs)


def validate(base):
    """Refuse the two dishonest shapes. Exit non-zero on either.

    1. landed with NO evidence -- the say-do gap this harness keeps rediscovering.
    2. adversarial_check requested and never run, while items claim landed. A review
       that is asked for and skipped is worse than one never asked for: the record
       asserts scrutiny that did not happen.
    """
    problems = []
    for r in _read(base):
        for it in r.get("items", []):
            if it.get("state") == "landed" and not it.get("evidence"):
                problems.append(f"{r['ask_id']}#{it['n']}: landed with no evidence")
        if r.get("adversarial_check") and r.get("adversarial_result") is None:
            if any(it.get("state") == "landed" for it in r.get("items", [])):
                problems.append(
                    f"{r['ask_id']}: adversarial check requested, never run, items landed")
    return problems


def render(records, open_only=False):
    L = []
    tot = done = 0
    for r in records:
        items = r.get("items", [])
        shown = [i for i in items if not open_only or i.get("state") in OPEN]
        tot += len(items)
        done += sum(1 for i in items if i.get("state") in TERMINAL)
        if not shown:
            continue
        head = f"{r['ask_id']}"
        if r.get("initiative"):
            head += f"  [{r['initiative']}]"
        if r.get("adversarial_check"):
            head += "  [ADVERSARIAL]" + ("" if r.get("adversarial_result") else " NOT RUN")
        L.append(head)
        L.append(f'  "{" ".join(str(r.get("verbatim", "")).split())[:150]}"')
        for it in shown:
            ev = ("  <- " + "; ".join(it.get("evidence", [])[:2])) if it.get("evidence") else ""
            L.append(f"    {it['n']}. [{it['state'].upper():9}] {it['text'][:96]}{ev}")
    if not L:
        return "ASK LEDGER: nothing open"
    outstanding = tot - done
    L.insert(0, f"ASK LEDGER — {outstanding} of {tot} item(s) still open")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", default="WAI-Harness/spoke/local")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add"); a.add_argument("--session", required=True)
    a.add_argument("--verbatim", required=True); a.add_argument("--item", action="append")
    a.add_argument("--initiative", default=""); a.add_argument("--ts", default="")
    a.add_argument("--adversarial", action="store_true")

    s = sub.add_parser("state"); s.add_argument("ask_id")
    s.add_argument("--state", required=True); s.add_argument("--evidence", default="")
    s.add_argument("--item", type=int); s.add_argument("--note", default="")

    l = sub.add_parser("list"); l.add_argument("--session"); l.add_argument("--open-only", action="store_true")
    rp = sub.add_parser("report"); rp.add_argument("--session"); rp.add_argument("--json", action="store_true")
    # `report` takes --open-only too. It did not at first, and the first person to hit that
    # was its author one minute after shipping it: `report` is the marching-orders view, so
    # "just the open ones" is the commonest thing to want from it.
    rp.add_argument("--open-only", action="store_true")
    sub.add_parser("validate")

    args = ap.parse_args()
    if args.cmd == "add":
        r = add(args.base, args.session, args.verbatim, args.item, args.initiative,
                args.ts, args.adversarial)
        print(r["ask_id"])
    elif args.cmd == "state":
        set_state(args.base, args.ask_id, args.state, args.evidence, args.item, args.note)
        print("ok")
    elif args.cmd in ("list", "report"):
        recs = _read(args.base)
        if getattr(args, "session", None):
            recs = [r for r in recs if r.get("session") == args.session]
        if getattr(args, "json", False):
            print(json.dumps(recs, indent=2, ensure_ascii=False))
        else:
            print(render(recs, open_only=getattr(args, "open_only", False)))
    elif args.cmd == "validate":
        probs = validate(args.base)
        for p in probs:
            print(f"ASK LEDGER DISHONEST: {p}", file=sys.stderr)
        # Exit non-zero so a ceremony can gate on it. A ledger that lies is worse
        # than no ledger: it converts an unmet ask into a recorded success.
        return 1 if probs else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
