#!/usr/bin/env python3
"""spoke_pulse.py — does this spoke need YOU, or can automation keep working it?

THE QUESTION (operator, 2026-07-22)
"how will we know when a spoke needs a user more than automation workers so we
don't force busy work? A health score based on advisors within it perhaps would
help — showing me scouts are being generated and run and improvement is driven."

Sending workers at a spoke that has nothing runnable is busy work: it burns
tokens, produces scout-churn, and reports motion as progress. The signal that
prevents it is not "is there a backlog" — every spoke has a backlog — it is
whether the spoke's own machinery is TURNING:

    CREW       are there advisors, are they fundable (a prompt to scan from),
               and did any of them actually run recently?
    DISCOVERY  are scouts being generated?  (the crew looking outward)
    LANDING    are scouts and lugs being FINISHED?  (looking outward is not
               improvement until something closes)
    AUTONOMY   what share of the open backlog a worker can actually dispatch —
               from work_split, the same source spoke_readiness uses.

Each is scored 0-25. The total is a health score, but the VERDICT is what the
operator reads:

    AUTOPILOT   the loop turns on its own — send workers
    MIXED       it turns, but something is dragging — workers OK, watch the note
    NEEDS YOU   automation cannot help until a human does one specific thing

NEEDS YOU is never a vague low score. It always names the ONE action, because a
verdict a human cannot act on is just a number. The commonest by far is an empty
or retired crew: no advisor with a prompt means no discovery is possible at all,
and no amount of worker time will change that.

Deliberately NOT merged into spoke_readiness: that tool answers "will the spoke
operate" (harness) and "what is the next action" (backlog). This answers "who
should do the next stretch of work, a person or a worker". Same family, different
question — merging them is what made the old green light meaningless.

    python3 spoke_pulse.py --root <spoke>        one spoke, human-readable
    python3 spoke_pulse.py --fleet               every in-scope spoke, table
    python3 spoke_pulse.py --fleet --json        machine contract
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TOOLS))

WINDOW_DAYS = 7
G, Y, R, B, DIM, OFF = "\033[32m", "\033[33m", "\033[31m", "\033[1m", "\033[2m", "\033[0m"


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------
def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _advisor_entries(raw):
    """schedule-index.json ships in two shapes; normalise (see fleet fix 2026-07-22)."""
    if isinstance(raw, dict):
        entries = raw.get("advisors")
        if isinstance(entries, list):
            return entries
        return [v for v in raw.values() if isinstance(v, dict) and v.get("advisor_id")]
    return raw if isinstance(raw, list) else []


def crew_signals(spoke: Path) -> dict:
    adv_dir = spoke / "WAI-Harness" / "spoke" / "advisors"
    entries = _advisor_entries(_load(adv_dir / "schedule-index.json"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    registered = fundable = retired = ran_recent = never = 0
    for e in entries:
        if not isinstance(e, dict):
            continue
        aid = e.get("advisor_id")
        if not aid:
            continue
        registered += 1
        d = adv_dir / aid
        contract = _load(d / "contract.json") or {}
        if contract.get("retired") or contract.get("status") == "retired" or contract.get("fund") is False:
            retired += 1
            continue
        if (d / "context_prompt.md").exists() or (d / "charter.md").exists():
            fundable += 1
        last = e.get("last_run_at")
        if not last:
            never += 1
            continue
        try:
            when = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when >= cutoff:
                ran_recent += 1
        except ValueError:
            pass
    return {"registered": registered, "fundable": fundable, "retired": retired,
            "ran_recent": ran_recent, "never_run": never}


def lug_signals(spoke: Path) -> dict:
    base = spoke / "WAI-Harness" / "spoke" / "local" / "lugs" / "bytype"
    cutoff = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    created = completed = scouts_created = scouts_completed = 0
    if not base.is_dir():
        return {"created": 0, "completed": 0, "scouts_created": 0, "scouts_completed": 0}
    for f in glob.iglob(str(base / "*" / "*" / "*.json")):
        d = _load(Path(f))
        if not isinstance(d, dict):
            continue
        is_scout = bool(d.get("advisor_scout")) or "advisor-scout" in str(d.get("id", ""))
        if str(d.get("created_at") or "")[:10] >= cutoff:
            created += 1
            if is_scout:
                scouts_created += 1
        if "/completed/" in f:
            stamps = [str(d.get(k) or "")[:10] for k in
                      ("completed_at", "closed_at", "finished_at", "updated_at")]
            if any(s >= cutoff for s in stamps if s):
                completed += 1
                if is_scout:
                    scouts_completed += 1
    return {"created": created, "completed": completed,
            "scouts_created": scouts_created, "scouts_completed": scouts_completed}


def autonomy(spoke: Path) -> dict:
    """Dispatchable share of the backlog — reuse work_split, the same source
    spoke_readiness reads, so two tools never disagree about one number."""
    try:
        import work_split  # noqa
        out = subprocess.run(
            [sys.executable, str(_TOOLS / "work_split.py"), "--spoke-root", str(spoke), "--json"],
            capture_output=True, text=True, timeout=120)
        d = json.loads(out.stdout) if out.stdout.strip() else {}
    except Exception:
        d = {}
    def _count(v):
        # work_split returns needs_you as a LIST of lugs, not a count — reading it
        # as an int silently yielded 0 and made every spoke look fully autonomous.
        if isinstance(v, list):
            return len(v)
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0

    runnable = _count(d.get("runnable_now") if d.get("runnable_now") is not None
                      else d.get("runnable"))
    needs_you = _count(d.get("needs_you"))
    total = _count(d.get("total_lugs") if d.get("total_lugs") is not None else d.get("total"))
    ratio = d.get("autonomy_ratio")
    if ratio is None and total:
        ratio = runnable / total
    return {"runnable_now": runnable, "needs_you": needs_you,
            "total_lugs": total, "autonomy_ratio": float(ratio or 0.0)}


def goal_set(spoke: Path) -> bool:
    st = _load(spoke / "WAI-Harness" / "spoke" / "local" / "WAI-State.json") or {}
    wheel = st.get("wheel") or {}
    g = wheel.get("goal") or st.get("goal")
    return bool(isinstance(g, str) and g.strip())


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------
def score(spoke_path: str) -> dict:
    spoke = Path(spoke_path)
    crew = crew_signals(spoke)
    lugs = lug_signals(spoke)
    auto = autonomy(spoke)
    has_goal = goal_set(spoke)

    # CREW /25 — can this spoke discover anything at all?
    if crew["fundable"] == 0:
        crew_pts = 0
    else:
        crew_pts = min(15, crew["fundable"] * 3) + (10 if crew["ran_recent"] else 0)

    # DISCOVERY /25 — is the crew looking outward?
    sc = lugs["scouts_created"]
    discovery_pts = 25 if sc >= 5 else (18 if sc >= 3 else (10 if sc >= 1 else 0))

    # LANDING /25 — is anything actually finishing? Looking is not improving.
    comp = lugs["completed"]
    landing_pts = 25 if comp >= 10 else (18 if comp >= 5 else (10 if comp >= 1 else 0))
    if lugs["scouts_created"] and not lugs["scouts_completed"]:
        landing_pts = max(0, landing_pts - 8)          # generating, not landing

    # AUTONOMY /25 — can a worker act without a human first?
    ratio = auto["autonomy_ratio"]
    autonomy_pts = int(min(25, round(ratio * 50)))     # 0.5+ ratio saturates

    total = crew_pts + discovery_pts + landing_pts + autonomy_pts

    # ---- verdict: named, actionable, never a bare number --------------------
    if crew["fundable"] == 0:
        verdict, why = "NEEDS YOU", (
            f"no funded advisor ({crew['registered']} registered, {crew['retired']} retired) — "
            "discovery is impossible, workers can only chew the existing backlog")
        action = "define at least one advisor with a context_prompt.md or charter.md"
    elif not has_goal and lugs["completed"] == 0:
        verdict, why = "NEEDS YOU", (
            "no stated goal and nothing finished — autopilot has neither direction nor traction")
        action = "set wheel.goal in WAI-State.json"
    elif auto["runnable_now"] < 5 and lugs["completed"] < 5:
        # STARVED — and the "and" matters. A low dispatchable RATIO on its own is
        # not a needs-you signal: every backlog carries receipts, notices and epics
        # that were never dispatchable, so the ratio sits under 25% on healthy
        # spokes. Judging on ratio alone told the operator to pull workers off
        # spokes that had just finished twenty lugs — the metric flattering itself.
        # Only an absolute shortage of runnable work AND no recent landings means
        # workers have nothing to do.
        verdict, why = "NEEDS YOU", (
            f"only {auto['runnable_now']} dispatchable lug(s) and {lugs['completed']} finished "
            f"in {WINDOW_DAYS}d — workers would idle or churn")
        action = "author file_targets/PEV on the top lugs, or retire the dead ones"
    elif lugs["completed"] == 0 and lugs["created"] > 0:
        verdict, why = "MIXED", (
            f"{lugs['created']} lugs created in {WINDOW_DAYS}d and none finished — "
            "generating, not landing")
        action = "check the spoke's AP log for dispatch timeouts before sending more workers"
    elif crew["ran_recent"] == 0 and crew["never_run"] == crew["registered"]:
        verdict, why = "MIXED", "crew is funded but has never run — first scouts still pending"
        action = "let one autopilot round warm the crew, then re-read"
    elif not has_goal:
        # It IS landing work, so workers help — but without a stated goal they
        # prioritise by score alone, which is how a spoke drifts into busy work.
        verdict, why = "MIXED", (
            f"turning ({lugs['completed']} finished in {WINDOW_DAYS}d) but no stated goal — "
            "workers prioritise by score alone, which drifts toward busy work")
        action = "set wheel.goal in WAI-State.json — one line, and it steers every round after"
    else:
        verdict, why = "AUTOPILOT", (
            f"{crew['fundable']} funded advisor(s), {lugs['scouts_created']} scout(s) in "
            f"{WINDOW_DAYS}d, {lugs['completed']} lug(s) finished, {ratio:.0%} dispatchable")
        action = "none — send workers"

    return {"spoke": spoke.name, "path": str(spoke), "score": total, "verdict": verdict,
            "why": why, "next_human_action": action, "has_goal": has_goal,
            "components": {"crew": crew_pts, "discovery": discovery_pts,
                           "landing": landing_pts, "autonomy": autonomy_pts},
            "crew": crew, "lugs": lugs, "autonomy": auto, "window_days": WINDOW_DAYS}


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------
def _colour(v: str) -> str:
    return {"AUTOPILOT": G, "MIXED": Y, "NEEDS YOU": R}.get(v, "")


def render_one(r: dict) -> str:
    c = r["components"]
    return "\n".join([
        f"{B}{r['spoke']}{OFF}  {_colour(r['verdict'])}{r['verdict']}{OFF}  score {r['score']}/100",
        f"  why       {r['why']}",
        f"  do next   {r['next_human_action']}",
        f"  crew      {c['crew']}/25   {r['crew']['fundable']} funded, "
        f"{r['crew']['retired']} retired, {r['crew']['ran_recent']} ran in {r['window_days']}d",
        f"  discovery {c['discovery']}/25   {r['lugs']['scouts_created']} scouts created",
        f"  landing   {c['landing']}/25   {r['lugs']['completed']} lugs finished "
        f"({r['lugs']['scouts_completed']} of them scouts)",
        f"  autonomy  {c['autonomy']}/25   {r['autonomy']['runnable_now']} of "
        f"{r['autonomy']['total_lugs']} dispatchable",
    ])


def render_fleet(rows: list) -> str:
    order = {"NEEDS YOU": 0, "MIXED": 1, "AUTOPILOT": 2}
    rows = sorted(rows, key=lambda r: (order.get(r["verdict"], 3), -r["score"]))
    out = [f"{B}SPOKE PULSE{OFF}  {DIM}who should do the next stretch of work — "
           f"a person or a worker  ({WINDOW_DAYS}d window){OFF}", ""]
    out.append(f"  {DIM}spoke                    verdict      score  crew disc land auto{OFF}")
    for r in rows:
        c = r["components"]
        out.append(f"  {r['spoke']:<24} {_colour(r['verdict'])}{r['verdict']:<11}{OFF}"
                   f"  {r['score']:>3}   {c['crew']:>4} {c['discovery']:>4} "
                   f"{c['landing']:>4} {c['autonomy']:>4}")
    out.append("")
    needs = [r for r in rows if r["verdict"] == "NEEDS YOU"]
    if needs:
        out.append(f"  {B}THESE NEED YOU — workers cannot help until you act{OFF}")
        for r in needs:
            out.append(f"   • {B}{r['spoke']}{OFF}: {r['why']}")
            out.append(f"     -> {r['next_human_action']}")
        out.append("")
    ready = [r["spoke"] for r in rows if r["verdict"] == "AUTOPILOT"]
    if ready:
        out.append(f"  {G}Send workers at:{OFF} {', '.join(ready)}")
    out += ["",
            f"  {DIM}crew  funded advisors + did any run recently (0 = discovery impossible){OFF}",
            f"  {DIM}disc  scouts generated — the crew looking outward{OFF}",
            f"  {DIM}land  lugs finished — looking outward is not improvement until work closes{OFF}",
            f"  {DIM}auto  share of the backlog a worker can dispatch without a human first{OFF}"]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=None)
    ap.add_argument("--fleet", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.fleet:
        try:
            import fleet_scope
            targets = [w["path"] for w in fleet_scope.in_scope()]
        except Exception:
            print("fleet_scope unavailable — pass --root", file=sys.stderr)
            return 2
        rows = [score(t) for t in targets if (Path(t) / "WAI-Harness").is_dir()]
        print(json.dumps(rows, indent=2) if args.json else render_fleet(rows))
        return 0

    r = score(args.root or ".")
    print(json.dumps(r, indent=2) if args.json else render_one(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
