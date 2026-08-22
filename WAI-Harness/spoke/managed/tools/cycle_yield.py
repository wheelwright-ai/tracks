#!/usr/bin/env python3
"""cycle_yield.py -- did the round pay for itself? The learn half of iterate/review/learn.

OPERATOR 2026-08-20: "orchestrate the iteration/review/learn cycle without me being in the
loop ... our dogfooding tool to see if the expected results come from the work invested ...
the conductor's hands to initiate work on a cycle to maximize the use of the limits we have
on MEANINGFUL WORK NOT BUSY NOISE."

WHAT ALREADY EXISTED, and why this is not another chainer:

    ITERATE   core_ap_run.sh work-steals rounds across the core group
    REVIEW    wave records say what each spoke returned; the phase-3 tally says
              where every eligible lug went
    LEARN     nothing. No round was ever compared to the one before it.

Without the third, a campaign cannot tell a productive round from an expensive one. It runs
to its round goal either way -- which is precisely how 8 waves spent 0 tokens against a
400,000 ceiling and nobody noticed until a human read a log.

THE MEASURE IS LANDED, NOT DISPATCHED. This is the whole point and it is not a detail:

    dispatched   a model was asked. Costs tokens. Proves nothing.
    completed    the lug says done. Cheap to claim.
    LANDED       the work is on canon and its verify RAN.

Counting dispatches would make a round that fires 40 lugs and lands none look like the best
round of the campaign. Yield is landed-per-100k-tokens, and a round that lands nothing has a
yield of zero however busy it was.

SCOUT WORK IS NOT PRODUCT. Completions whose ids start with scout-/advisor-scout-/
crew-recommend-/coverage-eval are the autopilot talking to itself. Conductor already
excludes them from ROLLING for the same reason -- an engine that scouts on every empty round
would otherwise report itself productive forever.

THE STOP RULE, and it is the operator's ask stated mechanically: after
UNPRODUCTIVE_STREAK_LIMIT consecutive rounds that land nothing, the campaign STOPS and says
so. Limits are for meaningful work; a loop that cannot stop cannot prefer it.

NAMED cycle_yield, NOT ap_cycle. The first cut of this file CLOBBERED an existing
ap_cycle.py -- the git-transaction tool that gives each AP cycle a branch and a merge gate.
Different subject, same obvious name, and `cat >` does not warn. Its own test suite caught
it within a minute, which is the only reason this note is a footnote rather than an
incident. Check before you name.

USAGE
  cycle_yield.py record --spoke X --tokens N --completed a,b --landed-before N --landed-after N
  cycle_yield.py verdict [--spoke X] [--json]      is the campaign paying for itself
  cycle_yield.py should-continue [--json]          the conductor's hands: exit 0 run, 1 stop
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

TOOL_VERSION = "1.0.0"

LEDGER = "WAI-Harness/hub/local/ap-runs/cycle-ledger.jsonl"

# Ids the autopilot mints for itself. Same rule conductor uses to keep scout churn out of
# ROLLING -- an engine that scouts every empty round would report itself productive forever.
SELF_TALK = ("scout-", "advisor-scout-", "crew-recommend-", "coverage-eval")

# Consecutive landless rounds before a campaign stops. Two, not one: a single barren round
# is ordinary (a spoke can legitimately have nothing ready), two in a row is a pattern.
UNPRODUCTIVE_STREAK_LIMIT = 2

IMPROVING, FLAT, DEGRADING, BARREN, UNKNOWN = (
    "improving", "flat", "degrading", "barren", "unknown")


def _now():
    return datetime.now(timezone.utc).isoformat()


def real_completions(completed) -> list:
    """Completions that are not the autopilot talking to itself."""
    return [c for c in (completed or []) if not str(c).startswith(SELF_TALK)]


def yield_per_100k(landed: int, tokens: int):
    """Landed work per 100k tokens, or None when nothing was spent.

    None, never zero: a round that spent nothing has no yield to report, and returning 0.0
    would rank it as the worst round rather than as an unmeasured one. That distinction is
    the same one `unknown is not green` protects everywhere else here.
    """
    if not tokens or tokens <= 0:
        return None
    return round(landed * 100000.0 / tokens, 2)


def record(place_root, spoke, tokens, completed, landed_before, landed_after,
           dispatched=0, note="") -> dict:
    """Append one round to the ledger. Returns the row."""
    real = real_completions(completed)
    landed = max(0, int(landed_after) - int(landed_before))
    row = {
        "at": _now(), "spoke": spoke, "tokens": int(tokens or 0),
        "dispatched": int(dispatched or 0),
        "completed": len(completed or []), "real_completions": len(real),
        "self_talk": len(completed or []) - len(real),
        "landed": landed,
        "yield_per_100k": yield_per_100k(landed, int(tokens or 0)),
        "productive": landed > 0,
        "note": note, "tool_version": TOOL_VERSION,
    }
    path = os.path.join(place_root, LEDGER)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def rows(place_root, spoke="") -> list:
    path = os.path.join(place_root, LEDGER)
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not spoke or r.get("spoke") == spoke:
                    out.append(r)
    except OSError:
        return []
    return out


def unproductive_streak(history) -> int:
    """How many rounds in a row have landed nothing, counting back from the end."""
    streak = 0
    for r in reversed(history):
        if r.get("productive"):
            break
        streak += 1
    return streak


def verdict(place_root, spoke="") -> dict:
    """Is the invested work returning the expected result?"""
    history = rows(place_root, spoke)
    if not history:
        return {"verdict": UNKNOWN, "rounds": 0,
                "why": "no rounds recorded -- nothing to compare"}

    streak = unproductive_streak(history)
    landed_total = sum(r.get("landed", 0) for r in history)
    tokens_total = sum(r.get("tokens", 0) for r in history)

    if streak >= UNPRODUCTIVE_STREAK_LIMIT:
        return {"verdict": BARREN, "rounds": len(history),
                "unproductive_streak": streak, "landed_total": landed_total,
                "tokens_total": tokens_total,
                "why": (f"{streak} consecutive round(s) landed nothing. Limits are for "
                        "meaningful work; this is busy noise and the campaign should stop.")}

    measured = [r["yield_per_100k"] for r in history if r.get("yield_per_100k") is not None]
    if len(measured) < 2:
        return {"verdict": UNKNOWN, "rounds": len(history),
                "unproductive_streak": streak, "landed_total": landed_total,
                "tokens_total": tokens_total,
                "why": ("fewer than two rounds spent anything measurable -- a trend needs "
                        "two points, and guessing one is how a campaign talks itself into "
                        "continuing")}

    half = max(1, len(measured) // 2)
    earlier = sum(measured[:half]) / half
    later = sum(measured[half:]) / max(1, len(measured) - half)
    if later > earlier * 1.15:
        v, why = IMPROVING, f"yield rose {earlier:.1f} -> {later:.1f} per 100k tokens"
    elif later < earlier * 0.85:
        v, why = DEGRADING, (f"yield fell {earlier:.1f} -> {later:.1f} per 100k tokens -- "
                             "the same spend is returning less")
    else:
        v, why = FLAT, f"yield steady around {later:.1f} per 100k tokens"
    return {"verdict": v, "rounds": len(history), "unproductive_streak": streak,
            "landed_total": landed_total, "tokens_total": tokens_total,
            "yield_earlier": round(earlier, 2), "yield_later": round(later, 2), "why": why}


def should_continue(place_root, spoke="") -> dict:
    """The conductor's hands. True keeps the campaign running.

    Continues on UNKNOWN deliberately: a campaign with no history yet has to be allowed to
    create some. The stop is for MEASURED unproductiveness, not for the absence of a
    measurement -- the opposite of the capacity gate, where an unreadable budget must stop
    the run because spending is the risk there and here it is the only way to learn.
    """
    v = verdict(place_root, spoke)
    stop = v["verdict"] in (BARREN, DEGRADING)
    return {"continue": not stop, "verdict": v["verdict"], "why": v["why"],
            "rounds": v.get("rounds", 0)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("record")
    p.add_argument("--root", default=".")
    p.add_argument("--spoke", required=True)
    p.add_argument("--tokens", type=int, default=0)
    p.add_argument("--dispatched", type=int, default=0)
    p.add_argument("--completed", default="")
    p.add_argument("--landed-before", type=int, default=0)
    p.add_argument("--landed-after", type=int, default=0)
    p.add_argument("--note", default="")
    p.add_argument("--json", action="store_true")

    for name in ("verdict", "should-continue"):
        q = sub.add_parser(name)
        q.add_argument("--root", default=".")
        q.add_argument("--spoke", default="")
        q.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)

    if args.cmd == "record":
        row = record(args.root, args.spoke, args.tokens,
                     [c for c in args.completed.split(",") if c],
                     args.landed_before, args.landed_after,
                     dispatched=args.dispatched, note=args.note)
        print(json.dumps(row, indent=2) if args.json else
              f"{row['spoke']}: landed={row['landed']} tokens={row['tokens']} "
              f"yield={row['yield_per_100k']} productive={row['productive']}")
        return 0

    if args.cmd == "verdict":
        v = verdict(args.root, args.spoke)
        if args.json:
            print(json.dumps(v, indent=2))
        else:
            print(f"\n{v['verdict'].upper()} over {v['rounds']} round(s)")
            print(f"  {v['why']}")
            if v.get("landed_total") is not None:
                print(f"  landed {v['landed_total']} for {v['tokens_total']} token(s)")
        return 0

    d = should_continue(args.root, args.spoke)
    print(json.dumps(d, indent=2) if args.json else
          f"{'CONTINUE' if d['continue'] else 'STOP'} -- {d['verdict']}: {d['why']}")
    return 0 if d["continue"] else 1


if __name__ == "__main__":
    sys.exit(main())
