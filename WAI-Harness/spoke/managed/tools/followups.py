#!/usr/bin/env python3
"""followups.py -- work that books its own review, and comes back to say whether it worked.

OPERATOR 2026-08-20: "each lug initiative can have a schedule of next touches either when a
milestone (10 sessions elapse since creation) happens or on a timed schedule (eg. in 30
days) with the followup actions (eg. review data to determine if the hypothesis goal was
met, if not tweak and iterate)."

THE GAP THIS CLOSES. Every lug in this estate records what was DONE. None records what was
EXPECTED, so nothing can ever ask whether it happened. A completed lug is a claim about the
past; a followup is a claim about the future that the future gets to judge.

Measured across s141: 20+ changes landed, each with an oracle proving it WORKS. Not one
carried a way to ask whether it HELPED. Those are different questions -- the Stop-hook
scoping is green in every test and the honest verdict on whether it improved a session is
still unwritten, because nothing was scheduled to look.

TWO CLOCKS, because the operator named two and they measure different things:

    sessions_elapsed   effort. 10 sessions is "we have worked a while since then",
                       which is the right clock for "has this had a fair trial".
    days               calendar. 30 days is "the world has moved", the right clock
                       for adoption, drift, and anything waiting on other people.

A HYPOTHESIS IS REQUIRED, NOT OPTIONAL. `schedule` REFUSES a followup that does not say
what it expects, because "review this later" is a reminder and reminders get dismissed. The
whole value is that a future session can compare a written expectation against a measured
outcome and reach a verdict the author cannot pre-empt.

NOTHING IS AUTO-CLOSED. Due followups are SURFACED; a human or a session decides. A tool
that silently marked its own hypotheses met would be the most expensive false green here.

USAGE
  followups.py schedule --lug <path> --in-days 30 --hypothesis "..." --expect "..." --action "..."
  followups.py schedule --lug <path> --in-sessions 10 --hypothesis "..." --expect "..." --action "..."
  followups.py due [--root .] [--now ISO] [--session-count N] [--json]
  followups.py settle --lug <path> --verdict met|unmet|inconclusive --saw "..."
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone

TOOL_VERSION = "1.0.0"

FIELD = "_followup"
PENDING, SETTLED = "pending", "settled"
MET, UNMET, INCONCLUSIVE = "met", "unmet", "inconclusive"


class FollowupRefused(ValueError):
    """A followup that cannot be judged later is a reminder, not a followup."""


def _now(iso=""):
    if iso:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def build(hypothesis: str, expect: str, action: str, in_days=None, in_sessions=None,
          session_count=0, now_iso="") -> dict:
    """One followup. REFUSES anything a later session could not judge."""
    if not (hypothesis or "").strip():
        raise FollowupRefused(
            "a followup with no hypothesis cannot be judged later -- it is a reminder, and "
            "reminders get dismissed. Say what you expect to be true.")
    if not (expect or "").strip():
        raise FollowupRefused(
            "a followup with no expected OUTCOME cannot be compared to anything. 'review "
            "this' is not an expectation.")
    if not (action or "").strip():
        raise FollowupRefused(
            "a followup with no action leaves the next session to invent one, which is how "
            "a due item becomes a shrug")
    if in_days is None and in_sessions is None:
        raise FollowupRefused(
            "a followup needs a clock: --in-days (calendar) or --in-sessions (effort)")

    now = _now(now_iso)
    out = {
        "status": PENDING,
        "hypothesis": hypothesis.strip(),
        "expect": expect.strip(),
        "action": action.strip(),
        "created_at": now.isoformat(),
        "created_at_session_count": int(session_count or 0),
        "tool_version": TOOL_VERSION,
    }
    if in_days is not None:
        out["due_at"] = (now + timedelta(days=int(in_days))).isoformat()
        out["clock"] = "days"
    if in_sessions is not None:
        out["due_after_sessions"] = int(session_count or 0) + int(in_sessions)
        out["clock"] = "sessions" if "clock" not in out else "both"
    return out


def is_due(fu: dict, now_iso="", session_count=0) -> bool:
    """EITHER clock firing makes it due.

    Either, not both: a followup scheduled for 30 days OR 10 sessions is asking to be looked
    at when the first of those arrives. Requiring both would let a quiet month hold back a
    review that ten sessions of work had already earned.
    """
    if not fu or fu.get("status") != PENDING:
        return False
    if fu.get("due_at"):
        try:
            if _now(now_iso) >= _now(fu["due_at"]):
                return True
        except ValueError:
            pass
    if fu.get("due_after_sessions") is not None:
        if int(session_count or 0) >= int(fu["due_after_sessions"]):
            return True
    return False


def _lug_paths(root):
    pats = [os.path.join(root, "WAI-Harness/spoke/local/lugs/bytype/*/*/*.json"),
            os.path.join(root, "WAI-Harness/spoke/local/initiatives/*.json")]
    out = []
    for p in pats:
        out.extend(glob.glob(p))
    return sorted(out)


def due(root=".", now_iso="", session_count=0) -> dict:
    """Every followup whose clock has fired, with what it expected."""
    items, scheduled = [], 0
    for path in _lug_paths(root):
        try:
            with open(path, encoding="utf-8") as fh:
                obj = json.load(fh)
        except (OSError, ValueError):
            continue
        fu = obj.get(FIELD)
        if not isinstance(fu, dict):
            continue
        scheduled += 1
        if is_due(fu, now_iso, session_count):
            items.append({"lug": obj.get("id") or os.path.basename(path)[:-5],
                          "path": path, "hypothesis": fu["hypothesis"],
                          "expect": fu["expect"], "action": fu["action"],
                          "clock": fu.get("clock"), "created_at": fu.get("created_at")})
    return {"due": items, "scheduled_total": scheduled,
            "verdict": (f"{len(items)} followup(s) due of {scheduled} scheduled"
                        if scheduled else "no followups scheduled anywhere")}


def settle(path, verdict_value, saw) -> dict:
    """Record what actually happened. Never automatic."""
    if verdict_value not in (MET, UNMET, INCONCLUSIVE):
        raise FollowupRefused(f"{verdict_value!r} is not one of {MET}/{UNMET}/{INCONCLUSIVE}")
    if not (saw or "").strip():
        raise FollowupRefused(
            "settling a followup requires saying what was SEEN. A verdict without evidence "
            "is the claim this whole object exists to make checkable.")
    with open(path, encoding="utf-8") as fh:
        obj = json.load(fh)
    fu = obj.get(FIELD)
    if not isinstance(fu, dict):
        raise FollowupRefused(f"{path} carries no {FIELD}")
    fu["status"] = SETTLED
    fu["verdict"] = verdict_value
    fu["saw"] = saw.strip()
    fu["settled_at"] = _now().isoformat()
    obj[FIELD] = fu
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    return fu


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("schedule")
    s.add_argument("--lug", required=True)
    s.add_argument("--in-days", type=int)
    s.add_argument("--in-sessions", type=int)
    s.add_argument("--hypothesis", default="")
    s.add_argument("--expect", default="")
    s.add_argument("--action", default="")
    s.add_argument("--session-count", type=int, default=0)

    d = sub.add_parser("due")
    d.add_argument("--root", default=".")
    d.add_argument("--now", default="")
    d.add_argument("--session-count", type=int, default=0)
    d.add_argument("--json", action="store_true")

    t = sub.add_parser("settle")
    t.add_argument("--lug", required=True)
    t.add_argument("--verdict", required=True)
    t.add_argument("--saw", default="")

    args = ap.parse_args(argv)
    try:
        if args.cmd == "schedule":
            with open(args.lug, encoding="utf-8") as fh:
                obj = json.load(fh)
            obj[FIELD] = build(args.hypothesis, args.expect, args.action,
                               args.in_days, args.in_sessions, args.session_count)
            with open(args.lug, "w", encoding="utf-8") as fh:
                json.dump(obj, fh, indent=2)
            print(f"scheduled: {obj[FIELD]['clock']} clock on {obj.get('id')}")
            return 0
        if args.cmd == "settle":
            fu = settle(args.lug, args.verdict, args.saw)
            print(f"settled {fu['verdict']}: {fu['saw'][:90]}")
            return 0
    except FollowupRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    res = due(args.root, args.now, args.session_count)
    if args.json:
        print(json.dumps(res, indent=2))
        return 0
    print(f"\n{res['verdict']}\n")
    for i in res["due"]:
        print(f"  {i['lug']}")
        print(f"    expected: {i['expect'][:96]}")
        print(f"    do:       {i['action'][:96]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
