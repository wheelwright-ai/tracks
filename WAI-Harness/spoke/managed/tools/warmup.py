#!/usr/bin/env python3
"""warmup.py -- establish a spoke's FLOOR before building anything new on top of it.

W2 of the LOW TRUST tenet (spec-low-trust-tenet-v1). The operator's framing,
2026-08-02: "we dont trust anything that predates the approach which forces a proper
review to build that trust before we build new functionality so we know the floor of
that spoke and establish a rapport along with the WAI harness -- this is our warmup
of a new project process."

WHAT A FLOOR IS. The set of things about this spoke that are true RIGHT NOW and can
be demonstrated on demand by someone who did not build them. Not what the spoke says
about itself. Not what it said in March. What survives a probe today.

WHY IT COMES FIRST. Building new functionality on an unestablished floor is how a
wheel accumulates confident fiction: each layer inherits the last layer's unchecked
claims as its own foundation, and the first honest measurement is then so expensive
that nobody takes it. Warmup makes the first measurement cheap by making it MANDATORY
and SMALL -- run once, at adoption, before the first new lug.

THE TWO-PARTY SHAPE (this is the rapport, and it is the whole design).

    DECLARE   the spoke states what it is and what it can do, from its OWN files
    PROBE     the harness independently checks each statement against the tree
    DELTA     the gap between the two IS the opening position

The delta is not a failure report. A spoke that declares six capabilities and can
prove two has a floor of two and an honest debt of four -- which is a better place
to start than a spoke that declared nothing and therefore "passed". The harness
learns what this spoke actually is; the spoke learns what it can defend. Neither
party gets to skip to trust.

THE GOODHART HOLE, CLOSED. The obvious cheat is to declare nothing and collect a
clean floor. So an EMPTY declaration is not ESTABLISHED -- it is EMPTY, a distinct
verdict that the gate treats exactly like UNKNOWN. You cannot buy a floor with
silence. The second cheat is a floor that never expires; a proof from six weeks ago
is a historical fact, not a current one, so floors carry a TTL and go STALE.

VERDICTS -- four, never collapsed to a boolean:

    ESTABLISHED  every declared item is either proven or explicitly admitted unproven,
                 at least one item is PROVEN, and the record is within its TTL
    INCOMPLETE   probes ran; something declared is neither proven nor admitted
    EMPTY        nothing meaningful was declared -- silence is not a floor
    UNKNOWN      warmup has never run here, or the record is stale/unreadable

A spoke is CLEARED to build new functionality only at ESTABLISHED. Everything else
routes to floor_gate.py, which refuses the dispatch and says which probe to fix.

PROBES are generic across every spoke -- they check the harness contract, not the
product. Each returns proven / unproven / failed, and `unproven` is never rounded
toward either neighbour: it means the check could not be decided here, which is a
third thing and must stay a third thing.

CLI:
    warmup.py --root DIR declare [--json]      what the spoke says about itself
    warmup.py --root DIR probe [--json]        what the harness can independently prove
    warmup.py --root DIR run [--apply] [--ttl-days N]   full ceremony; writes the floor
    warmup.py --root DIR first-look [--apply]  the wider review: map the code, re-check
                                               the record, rank what needs a human
    warmup.py --root DIR status [--json]       read the floor record; ESTABLISHED?

Exit codes: 0 ESTABLISHED, 1 INCOMPLETE, 2 UNKNOWN or EMPTY.
Exit-0 is reserved for a floor that is currently, demonstrably standing.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import trust_epoch as te

try:
    from wai_paths import resolve_wai_root
except Exception:  # pragma: no cover
    resolve_wai_root = None


FLOOR_FILE = "floor.json"
DEFAULT_TTL_DAYS = 30

PROVEN = "proven"
UNPROVEN = "unproven"
FAILED = "failed"

ESTABLISHED = "ESTABLISHED"
INCOMPLETE = "INCOMPLETE"
EMPTY = "EMPTY"
UNKNOWN = "UNKNOWN"


def _now():
    return datetime.now(timezone.utc)


def base_dir(root, mode=None):
    return te.base_dir(root, mode)


def floor_path(root, mode=None):
    return os.path.join(base_dir(root, mode), te.TRUST_DIR, FLOOR_FILE)


def _read_json(path, default=None):
    try:
        with open(path) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------- DECLARE


def declare(root, mode=None):
    """What the spoke says about itself, read from its own files. No judgement here.

    Deliberately credulous -- this half of the ceremony is the spoke's testimony and
    is recorded verbatim. The probing half is where it meets resistance.
    """
    base = base_dir(root, mode)
    state = _read_json(os.path.join(base, "WAI-State.json"), {}) or {}
    wheel = state.get("wheel", {}) if isinstance(state.get("wheel"), dict) else {}

    items = []

    # TIER 0 first, because it is what everything else is reasoned about with.
    tracks = glob.glob(os.path.join(base, "sessions", "*", "track.jsonl"))
    items.append({
        "id": "track",
        "declares": (f"it holds {len(tracks)} session track(s) recording why it did what it did"
                     if tracks else "it holds no session track -- no record of its own reasoning"),
        "value": len(tracks),
    })

    name = wheel.get("name") or state.get("name")
    items.append({
        "id": "identity",
        "declares": f"this spoke is '{name}'" if name else "this spoke has no declared name",
        "value": name,
    })

    goal = wheel.get("goal") or state.get("goal")
    items.append({
        "id": "goal",
        "declares": f"its goal is: {goal}" if goal else "no goal is declared",
        "value": goal,
    })

    version = (wheel.get("version") or state.get("version")
               or (state.get("_harness", {}) or {}).get("base_version"))
    items.append({
        "id": "harness",
        "declares": f"it runs harness/spoke version {version}" if version else "no version declared",
        "value": version,
    })

    tests = sorted(glob.glob(os.path.join(root, "**", "test_*.py"), recursive=True))
    tests = [t for t in tests if ".worktrees" not in t and "node_modules" not in t]
    items.append({
        "id": "tests",
        "declares": f"it owns {len(tests)} test file(s)" if tests else "it owns no test files",
        "value": len(tests),
    })

    advisors_dir = os.path.join(root, "WAI-Harness", "spoke", "advisors")
    advisors = sorted(
        os.path.basename(p) for p in glob.glob(os.path.join(advisors_dir, "*"))
        if os.path.isdir(p)
    )
    items.append({
        "id": "advisors",
        "declares": f"it has {len(advisors)} advisor(s) on the bench",
        "value": advisors,
    })

    items.append({
        "id": "history",
        "declares": "its completed work is a record of things that happened",
        "value": len(te.completed_lug_paths(root, mode)),
    })

    return {
        "declared_at": te._iso(_now()),
        "items": items,
        "meaningful": bool(name) and bool(tests or advisors),
    }


# ------------------------------------------------------------------ PROBE


def _probe_identity(root, mode, declaration):
    name = _decl_value(declaration, "identity")
    if not name:
        return FAILED, "WAI-State.json declares no wheel.name -- the spoke cannot say what it is"
    return PROVEN, f"wheel.name = {name} present in WAI-State.json"


def _probe_goal(root, mode, declaration):
    goal = _decl_value(declaration, "goal")
    if not goal:
        return FAILED, "no wheel.goal on disk -- a spoke with no goal cannot be said to be on course"
    if len(str(goal).strip()) < 20:
        return UNPROVEN, f"goal present but too terse to check intent against ({len(str(goal))} chars)"
    return PROVEN, f"wheel.goal present ({len(str(goal))} chars)"


def _probe_harness(root, mode, declaration):
    if resolve_wai_root is None:
        return UNPROVEN, "wai_paths unavailable -- harness layout could not be resolved"
    base, resolved = resolve_wai_root(root, mode)
    if not base or resolved in (None, "none"):
        return FAILED, "no harness tree resolvable at this root"
    if not os.path.isdir(base):
        return FAILED, f"resolved base does not exist: {base}"
    return PROVEN, f"harness mode {resolved}, base {os.path.relpath(base, root)}"


def _probe_tests(root, mode, declaration, run_tests=True, timeout=600):
    """The strongest generic oracle a spoke owns: does its own suite pass, today?

    Collection-only is NOT accepted as proof. A suite that imports cleanly and fails
    every assertion collects fine, and treating collection as a pass is exactly the
    green-that-did-not-earn-itself this tenet exists to remove.
    """
    count = _decl_value(declaration, "tests") or 0
    if not count:
        return UNPROVEN, "no test files found -- nothing to run, so nothing is proven either way"
    if not run_tests:
        return UNPROVEN, f"{count} test file(s) present but the suite was not run (--no-tests)"
    target = _suite_root(root)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", target],
            cwd=root, capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return UNPROVEN, "pytest not installed in this environment"
    except subprocess.TimeoutExpired:
        return UNPROVEN, f"suite exceeded {timeout}s -- a timeout is not a pass and not a failure"
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    summary = tail[-1] if tail else "no output"
    if proc.returncode == 0:
        return PROVEN, f"suite passed: {summary}"
    if proc.returncode == 5:
        return UNPROVEN, "pytest collected no tests at that path"
    if proc.returncode == 4:
        # Usage/collection error: the runner could not start. That is a broken
        # harness, not a failing suite, and must not be reported as either.
        return UNPROVEN, f"pytest usage error (exit 4) -- suite could not be run: {summary}"
    return FAILED, f"suite failed (exit {proc.returncode}): {summary}"


MIN_POST_EPOCH_TURNS = 10

_SESSION_DATE = re.compile(r"session-(\d{8})[-_]?(\d{4})?")


def _session_started_after(session_id, epoch):
    """Did this session start after the trust epoch? Unparseable ids are PRE-epoch.

    Defaulting an undatable session to post-epoch would let anything with an odd
    name into the graded window, which is the direction that flatters the score.
    Undatable therefore means legacy.
    """
    m = _SESSION_DATE.search(session_id or "")
    if not m:
        return False
    stamp = m.group(1) + (m.group(2) or "0000")
    try:
        started = datetime.strptime(stamp, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return started >= epoch.replace(hour=0, minute=0, second=0, microsecond=0)


def _probe_track(root, mode, declaration):
    """TIER 0. The record of WHY, and the only artefact here that cannot be rebuilt.

    Everything else a spoke owns can be re-derived: code can be re-read, lugs
    re-scanned, versions re-stamped. The reasoning behind a decision exists in
    exactly one place, and if the turn that held it was written floor-only, it is
    gone -- not degraded, gone. That asymmetry is why this probe is constitutional
    and why its gap cannot be admitted away like the others.

    Measured via track_judgment_coverage (adopted from basher, change lug
    change-canon-track-judgment-layer-decay-v1): rich turns carry reasoning, floor
    turns carry only what the hook could capture mechanically.
    """
    base = base_dir(root, mode)
    sessions = os.path.join(base, "sessions")
    if not os.path.isdir(sessions) or not glob.glob(
            os.path.join(sessions, "*", "track.jsonl")):
        return FAILED, "no session track on disk -- this spoke has no record of its own reasoning"
    try:
        import track_judgment_coverage as _tjc  # noqa: PLC0415
    except Exception:  # pragma: no cover
        return UNPROVEN, "track exists but track_judgment_coverage is unavailable to grade it"
    try:
        sessions = _tjc.scan_spoke(base)
        all_time = _tjc.summarise(sessions)
    except Exception as exc:  # noqa: BLE001
        return UNPROVEN, f"track present but could not be graded: {exc}"
    if all_time.get("turns", 0) == 0:
        return FAILED, "track files exist but hold zero turns"

    # C4 APPLIED TO THE TRACK ITSELF. The all-time figure is the honest scar and it
    # is reported below without exception -- but it CANNOT be the gate. mywheel
    # measured 50% over 1017 turns on 2026-08-02, and reaching 80% all-time would
    # take 1513 consecutive flawless turns. A criterion nobody can ever satisfy is
    # not a gate, it is a brick, and a brick gets deleted rather than obeyed (the
    # same reasoning that keeps FLOOR_WORK unblocked in floor_gate).
    #
    # So the grade is taken over POST-EPOCH sessions -- the only turns anyone can
    # still influence -- exactly as trust_epoch quarantines pre-epoch completions.
    # Two guards stop this being a Goodhart narrowing: the legacy scar is always
    # printed alongside, and too small a post-epoch sample is UNPROVEN rather than
    # PROVEN, so no spoke reaches its floor by having written nothing since.
    epoch = te.epoch_of(root, mode)
    post = {sid: rec for sid, rec in sessions.items()
            if epoch is None or _session_started_after(sid, epoch)}
    post_turns = sum(r.get("turns", 0) for r in post.values())
    post_rich = sum(r.get("rich", 0) for r in post.values())
    post_pct = round(100 * post_rich / post_turns) if post_turns else 0

    scar = (f"legacy scar {all_time.get('pct', 0)}% over {all_time.get('turns', 0)} "
            f"pre-epoch turns, unrecoverable")
    malformed = all_time.get("malformed", 0)
    if malformed:
        return FAILED, (f"{malformed} malformed track line(s) -- whole sessions are "
                        f"unreadable; run track_repair.py ({scar})")
    if epoch is None:
        return UNPROVEN, f"no trust epoch, so no post-epoch window to grade ({scar})"
    if post_turns < MIN_POST_EPOCH_TURNS:
        return UNPROVEN, (f"only {post_turns} post-epoch turn(s) -- too few to grade; "
                          f"a floor is not earned by writing nothing ({scar})")
    detail = f"{post_pct}% of {post_turns} post-epoch turns carry reasoning ({scar})"
    if post_pct < 50:
        return FAILED, f"judgment layer is the exception, not the rule -- {detail}"
    if post_pct < 80:
        return UNPROVEN, f"judgment layer is decaying -- {detail}"
    return PROVEN, f"judgment layer intact -- {detail}"


def _suite_root(root):
    """Where this spoke's tests actually live -- the managed tools dir if present,
    otherwise the repo root. Hardcoding one path made the probe report a broken
    runner as a failing suite on any spoke shaped differently."""
    tools = os.path.join("WAI-Harness", "spoke", "managed", "tools")
    return tools if os.path.isdir(os.path.join(root, tools)) else "."


def _probe_advisors(root, mode, declaration):
    """An advisor that has never run is not a capability. It is an intention.

    Delegates to oracle_liveness, which reads an advisor's own state file rather
    than inferring from file mtimes. The mtime heuristic this replaced graded
    `proofer` as merely stale when its scan_state.json said runs: 0 -- it had never
    run once, and the mtime of that very file was what covered for it.
    """
    names = _decl_value(declaration, "advisors") or []
    if not names:
        return UNPROVEN, "no advisors on the bench -- nothing claimed, nothing to check"
    try:
        import oracle_liveness as _ol  # noqa: PLC0415
    except Exception:  # pragma: no cover
        return UNPROVEN, "oracle_liveness unavailable -- advisor health could not be checked"
    report = _ol.check(root)
    c = report["counts"]
    detail = (f"{c[_ol.LIVE]} live, {c[_ol.LATE]} late, {c[_ol.SILENT]} silent, "
              f"{c[_ol.NEVER]} never ran, {c[_ol.UNSCHEDULED]} unscheduled "
              f"(of {report['total']})")
    if report["silent_total"]:
        return FAILED, f"advisors: {detail} -- silence outranks a red result"
    if c[_ol.LATE] or c[_ol.UNSCHEDULED]:
        return UNPROVEN, f"advisors: {detail}"
    return PROVEN, f"advisors: {detail}"


def _probe_history(root, mode, declaration):
    """The trust_epoch scan, folded in. Quarantine is a finding, not a failure."""
    scan = te.scan(root, mode)
    if not scan["epoch_stamped"]:
        return FAILED, "no trust epoch stamped -- every completion is untrusted by default"
    c = scan["counts"]
    parts = (f"proven {c[te.CLASS_PROVEN]}, provisional {c[te.CLASS_PROVISIONAL]}, "
             f"quarantined {c[te.CLASS_QUARANTINED]}, unfalsifiable {c[te.CLASS_UNFALSIFIABLE]}")
    if scan["trust_ratio"] is None:
        return UNPROVEN, f"epoch stamped, but nothing post-epoch to measure yet ({parts})"
    return PROVEN, f"trust ratio {scan['trust_ratio_display']} over {scan['post_epoch_population']} post-epoch ({parts})"


PROBES = {
    "track": _probe_track,
    "identity": _probe_identity,
    "goal": _probe_goal,
    "harness": _probe_harness,
    "tests": _probe_tests,
    "advisors": _probe_advisors,
    "history": _probe_history,
}

# CRITICALITY -- not all gaps cost the same, and a floor that treats them as
# interchangeable lets the cheapest one be closed while the dearest one rots.
# Operator, 2026-08-02: "There should be a priority applied to items understanding
# their importance to how the harness functions. Top of list is the track file so
# we have a record of our discussions we can look back on and mine."
#
#   T0 CONSTITUTIONAL  losing it destroys the ability to reason about everything
#                      else, and it is UNRECOVERABLE. Code can be re-read; a
#                      deleted or empty track cannot be reconstructed from
#                      anything, at any cost, ever. NOT ADMITTABLE.
#   T1 STRUCTURAL      the spoke cannot be operated safely without it
#   T2 EVIDENTIAL      it can operate, but its claims cannot be checked
#   T3 OPERATIONAL     quality and throughput degrade
TIERS = {
    "track": 0,
    "identity": 1,
    "harness": 1,
    "tests": 1,
    "goal": 2,
    "history": 2,
    "advisors": 3,
}
TIER_NAMES = {0: "CONSTITUTIONAL", 1: "STRUCTURAL", 2: "EVIDENTIAL", 3: "OPERATIONAL"}
NOT_ADMITTABLE_AT_OR_BELOW = 0


def tier_of(probe_id):
    """Unknown probes are STRUCTURAL, not OPERATIONAL. A probe nobody classified
    is more likely to matter than not, and defaulting downward is how new checks
    quietly become optional."""
    return TIERS.get(probe_id, 1)


def is_admittable(probe_id):
    return tier_of(probe_id) > NOT_ADMITTABLE_AT_OR_BELOW


def _decl_value(declaration, item_id):
    for item in declaration.get("items", []):
        if item.get("id") == item_id:
            return item.get("value")
    return None


def probe(root, mode=None, declaration=None, run_tests=True):
    declaration = declaration or declare(root, mode)
    results = []
    for item in declaration["items"]:
        fn = PROBES.get(item["id"])
        if fn is None:
            results.append({"id": item["id"], "verdict": UNPROVEN,
                            "evidence": "no probe defined for this declaration"})
            continue
        if item["id"] == "tests":
            verdict, evidence = fn(root, mode, declaration, run_tests=run_tests)
        else:
            verdict, evidence = fn(root, mode, declaration)
        results.append({
            "id": item["id"],
            "declares": item["declares"],
            "verdict": verdict,
            "evidence": evidence,
            "tier": tier_of(item["id"]),
            "tier_name": TIER_NAMES.get(tier_of(item["id"]), "STRUCTURAL"),
            "admittable": is_admittable(item["id"]),
        })
    # Worst-and-most-critical first: the reader must meet a constitutional gap
    # before an operational one, whatever order the probes happened to run in.
    _rank = {FAILED: 0, UNPROVEN: 1, PROVEN: 2}
    results.sort(key=lambda r: (r["tier"], _rank.get(r["verdict"], 1), r["id"]))
    return {"probed_at": te._iso(_now()), "results": results}


# ------------------------------------------------------------------ FLOOR


def verdict_for(declaration, probes, admitted=None):
    """Fold probe results into one of the four verdicts. No boolean anywhere.

    `admitted` is the set of probe ids the operator has explicitly accepted as
    unproven. An admission is a recorded decision, not a silence -- it keeps an
    honest spoke buildable without letting an unexamined gap pass as fine.
    """
    admitted = set(admitted or [])
    results = probes.get("results", [])
    if not declaration.get("meaningful") or not results:
        return EMPTY
    proven = [r for r in results if r["verdict"] == PROVEN]
    if not proven:
        return INCOMPLETE
    # A TIER 0 gap is never cleared by an admission. Admission is the operator
    # saying "I accept this is unproven and will build anyway"; for the track that
    # sentence cannot be honoured, because the reasoning lost while it is unproven
    # is not recoverable later at any price. Everything else can be admitted, then
    # repaid. This one cannot, so the option is not offered.
    open_gaps = [r for r in results
                 if r["verdict"] != PROVEN
                 and not (r["id"] in admitted and is_admittable(r["id"]))]
    return ESTABLISHED if not open_gaps else INCOMPLETE


def first_look(root, mode=None, apply=False, run_tests=False, force=False):
    """THE WALK (Ruling 38). Warmup establishes the floor; this establishes the MAP.

    The floor answers "can this spoke defend what it says about itself". The walk
    answers the question a first-run user actually has: what IS this, what is
    unproven, what is nearly done, and what needs me. Ten of the twelve v5
    mechanisms had zero callers until this call existed -- six phases certified and
    nothing about using a spoke changed, because the parts were built and the walk
    between them was not.

    Ruling 35 is enforced here rather than trusted: this never raises and never
    returns a blocking verdict. A walk that could refuse would make the map an
    obstacle, and an obstacle gets routed around.
    """
    try:
        import v5_walk  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return {"status": "UNAVAILABLE",
                "reason": f"the wider review is not installed here ({type(exc).__name__})"}
    try:
        result = v5_walk.walk(root, mode, run_tests=run_tests, force=force, apply=apply)
        priorities = result.pop("_priorities", {})
        return {"status": "OK", "walk": result, "priorities": priorities,
                "explanation": v5_walk.otto_explain(result, priorities)}
    except Exception as exc:  # noqa: BLE001
        # Belt and braces: v5_walk guards every step internally, so reaching here
        # means the walk itself could not start. Still a GAP, still not a block.
        return {"status": "GAP", "reason": f"{type(exc).__name__}: {str(exc)[:300]}"}


def run(root, mode=None, apply=False, ttl_days=DEFAULT_TTL_DAYS,
        admitted=None, run_tests=True, walk=True):
    declaration = declare(root, mode)
    probes = probe(root, mode, declaration, run_tests=run_tests)
    admitted = sorted(set(admitted or []))
    verdict = verdict_for(declaration, probes, admitted)

    now = _now()
    record = {
        "verdict": verdict,
        "established_at": te._iso(now),
        "expires_at": te._iso(now + timedelta(days=ttl_days)),
        "ttl_days": ttl_days,
        "trust_epoch": te.read_state(root, mode).get("trust_epoch"),
        "admitted_unproven": admitted,
        "declaration": declaration,
        "probes": probes,
        "delta": [
            {"id": r["id"], "declares": r.get("declares"), "verdict": r["verdict"],
             "evidence": r["evidence"], "tier": r["tier"],
             "tier_name": r["tier_name"], "admittable": r["admittable"]}
            for r in probes["results"] if r["verdict"] != PROVEN
        ],
        "blocking_tier0": [
            r["id"] for r in probes["results"]
            if r["verdict"] != PROVEN and r["tier"] == 0
        ],
        "certified_by": None,
        "_note": ("certified_by is null until an independent party signs this floor; "
                  "an unsigned floor is the spoke's own testimony about itself"),
    }
    if walk:
        # Only the COMPACT view is folded into the floor record. The full walk is
        # already on disk under the spoke's v5 dir, and duplicating a few thousand
        # findings into floor.json would make the floor unreadable to defend a
        # convenience nobody asked for.
        fl = first_look(root, mode, apply=apply, run_tests=False)
        record["first_look"] = {
            "status": fl.get("status"),
            "reason": fl.get("reason"),
            "summary": (fl.get("walk") or {}).get("priorities_summary"),
            "gaps": (fl.get("walk") or {}).get("gaps"),
            "incremental": (fl.get("walk") or {}).get("incremental"),
            "saved_to": (fl.get("walk") or {}).get("saved_to"),
            "explanation": fl.get("explanation"),
        }
    if apply:
        path = floor_path(root, mode)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            json.dump(record, handle, indent=2)
            handle.write("\n")
        record["written_to"] = path
    return record


def status(root, mode=None):
    """Read the floor record and answer the only question the gate asks.

    Staleness is evaluated HERE rather than trusted from the stored verdict, so a
    record that was ESTABLISHED in June cannot present itself as ESTABLISHED today.
    """
    record = _read_json(floor_path(root, mode))
    if not isinstance(record, dict):
        return {"verdict": UNKNOWN, "reason": "no floor record -- warmup has never run here",
                "cleared_to_build": False}
    stored = record.get("verdict", UNKNOWN)
    expires = te._parse_ts(record.get("expires_at"))
    if expires is None:
        return {"verdict": UNKNOWN, "reason": "floor record carries no usable expiry",
                "cleared_to_build": False, "record": record}
    if _now() > expires:
        age_days = (_now() - expires).days
        return {"verdict": UNKNOWN, "stored_verdict": stored,
                "reason": f"floor is STALE -- expired {age_days}d ago ({record.get('expires_at')})",
                "cleared_to_build": False, "record": record}
    return {
        "verdict": stored,
        "reason": f"floor {stored}, valid until {record.get('expires_at')}",
        "cleared_to_build": stored == ESTABLISHED,
        "expires_at": record.get("expires_at"),
        "delta": record.get("delta", []),
        "record": record,
    }


# ------------------------------------------------------------------ RENDER


_MARK = {PROVEN: "+", UNPROVEN: "?", FAILED: "!"}


def render(record):
    lines = [f"FLOOR: {record['verdict']}"]
    for r in record["probes"]["results"]:
        lock = "" if r["admittable"] else "  (NOT ADMITTABLE)"
        lines.append(f"  [{_MARK.get(r['verdict'], '?')}] T{r['tier']} {r['tier_name']:<15}"
                     f" {r['id']:<10} {r['verdict']:<10} {r['evidence']}{lock}")
    if record.get("admitted_unproven"):
        lines.append(f"  admitted unproven: {', '.join(record['admitted_unproven'])}")
    ignored = [a for a in record.get("admitted_unproven", []) if not is_admittable(a)]
    if ignored:
        lines.append(f"  ! admission REFUSED for tier-0: {', '.join(ignored)} "
                     "-- constitutional gaps cannot be admitted away")
    if record.get("blocking_tier0"):
        lines.append(f"  ! TIER 0 BLOCKING: {', '.join(record['blocking_tier0'])}")
    if record["verdict"] != ESTABLISHED:
        lines.append(f"  NOT cleared to build -- {len(record['delta'])} open gap(s)")
    lines.append(f"  valid until {record['expires_at']} ({record['ttl_days']}d)")

    # THE WALK, rendered for a person who has never heard of any of this (Ruling 12).
    # It goes AFTER the floor because the floor is the harness talking to itself and
    # this is the harness talking to the user; a first-run reader who stops at the
    # first thing they understand should still land on the ranked list.
    fl = record.get("first_look") or {}
    if fl.get("explanation"):
        lines.append("")
        lines.append(fl["explanation"])
    elif fl.get("status") in ("GAP", "UNAVAILABLE"):
        lines.append(f"  wider review: not available here -- {fl.get('reason', 'unknown')}")
    return "\n".join(lines)


_EXIT = {ESTABLISHED: 0, INCOMPLETE: 1, EMPTY: 2, UNKNOWN: 2}


def _main(argv=None):
    # Global flags are attached to EVERY subparser as well as the root, so
    # `status --json` and `--json status` both work. The first version accepted
    # only the second form and exited 2 with the JSON on stderr, which a shell
    # caller reads as an empty string -- the wakeup hook rendered a blank line
    # instead of the floor and nothing anywhere said why. Caught 2026-08-02 by
    # running the hook rather than trusting that it worked.
    # The sub-level copy defaults to SUPPRESS. Without it argparse re-applies the
    # subparser's own defaults over the namespace, so `--root X status` would parse
    # root back to "." -- a silent wrong-directory read, which is worse than the
    # crash it replaces.
    top = argparse.ArgumentParser(add_help=False)
    top.add_argument("--root", default=".")
    top.add_argument("--mode", default=None)
    top.add_argument("--json", action="store_true")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS)
    common.add_argument("--mode", default=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     parents=[top])
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("declare", parents=[common])
    p_probe = sub.add_parser("probe", parents=[common])
    p_probe.add_argument("--no-tests", action="store_true")

    p_run = sub.add_parser("run", parents=[common])
    p_run.add_argument("--apply", action="store_true")
    p_run.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    p_run.add_argument("--admit", action="append", default=[],
                       help="probe id explicitly accepted as unproven (repeatable)")
    p_run.add_argument("--no-tests", action="store_true")
    p_run.add_argument("--no-first-look", action="store_true",
                       help="skip the wider code/claims review (floor only)")

    p_fl = sub.add_parser("first-look", parents=[common])
    p_fl.add_argument("--apply", action="store_true",
                      help="also file the top items that need a decision as work items")
    p_fl.add_argument("--force", action="store_true", help="ignore the incremental cache")
    p_fl.add_argument("--with-tests", action="store_true")

    sub.add_parser("status", parents=[common])
    args = parser.parse_args(argv)

    if args.cmd == "declare":
        out = declare(args.root, args.mode)
        print(json.dumps(out, indent=2) if args.json else
              "\n".join(f"  {i['id']:<10} {i['declares']}" for i in out["items"]))
        return 0

    if args.cmd == "probe":
        out = probe(args.root, args.mode, run_tests=not args.no_tests)
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            for r in out["results"]:
                print(f"  [{_MARK.get(r['verdict'], '?')}] {r['id']:<10} {r['verdict']:<10} {r['evidence']}")
        return 0

    if args.cmd == "first-look":
        out = first_look(args.root, args.mode, apply=args.apply,
                         run_tests=args.with_tests, force=args.force)
        if args.json:
            print(json.dumps(out, indent=2, default=str))
        elif out.get("explanation"):
            print(out["explanation"])
        else:
            print(f"wider review unavailable: {out.get('reason', 'unknown')}")
        return 0

    if args.cmd == "run":
        record = run(args.root, args.mode, apply=args.apply, ttl_days=args.ttl_days,
                     admitted=args.admit, run_tests=not args.no_tests,
                     walk=not args.no_first_look)
        print(json.dumps(record, indent=2) if args.json else render(record))
        return _EXIT.get(record["verdict"], 2)

    out = status(args.root, args.mode)
    if args.json:
        payload = dict(out)
        payload.pop("record", None)
        print(json.dumps(payload, indent=2))
    else:
        print(f"FLOOR: {out['verdict']} -- {out['reason']}")
        for gap in out.get("delta", []):
            print(f"  [{_MARK.get(gap['verdict'], '?')}] {gap['id']:<10} {gap['evidence']}")
    return _EXIT.get(out["verdict"], 2)


if __name__ == "__main__":
    raise SystemExit(_main())
