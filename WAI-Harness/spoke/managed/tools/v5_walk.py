#!/usr/bin/env python3
"""v5_walk.py -- THE WALK. The sequence that turns twelve v5 tools into one harness.

Ruling 38 (docs/wheelwright-v5-control-plane-directive.md), measured at ratification:
ten of twelve v5 mechanisms had ZERO callers. Six phases certified and nothing about
using a spoke changed. "That is a toolbox, not a harness. The parts exist; the walk
between them does not."

THIS MODULE IS THE WALK. Five steps, in order, each degrading rather than blocking:

    1. DERIVE THE GRAPH        what code is here, what tests touch it, what ran
    2. RECONCILE THE CLAIMS    re-run what the record says was proved
    3. SURFACE UNPROVEN CORE   Ruling 37: silence on a CORE component is an ALARM
    4. HARVEST WHAT IS CLOSE   Ruling 33.3: runway, not debt
    5. RANK WHAT NEEDS A HUMAN Ruling 26: one list, never twelve outputs

RULING 35 IS THE LOAD-BEARING CONSTRAINT: building is never blocked on the graph.
A missing input -- no lug corpus, no tests, no catalog, no git -- is REPORTED AS A GAP
and the walk continues to the next step. There is no input whose absence stops this,
and no step that can raise. A walk that can refuse to walk would be routed around, and
a mechanism that gets routed around is a mechanism that does not exist.

RULING 26 IS THE OUTPUT CONSTRAINT. The walk does not hand anyone twelve tool outputs
to assemble. It produces FINDINGS in one shape, which Ozi ranks into one list, and
which Otto renders in words a first-run user can act on. The rendered text NEVER names
a tool -- `plain_guard()` enforces that mechanically, not by convention, because a
convention about wording is a convention that lapses.

RULING 28 IS THE DELETION CONSTRAINT. Nothing here deletes anything. Unreachable code
gets a DISPOSITION and DEPRECATE routes to `wave()`, which does nothing at all unless a
human passes --authorise --apply, and which writes a receipt naming every path it
removed. Never silently, never automatically, at any confidence.

CLI:
    v5_walk.py --root DIR walk [--apply] [--json] [--force] [--with-tests]
    v5_walk.py --root DIR explain [--json]         re-render the last walk
    v5_walk.py --root DIR wave [--authorise --apply]   the deletion wave + receipt
    v5_walk.py --root DIR wiring [--json]          which mechanisms are wired, and why

Exit codes: 0 walked (with or without gaps), 2 the walk itself could not be recorded.
A gap is never an error exit -- see Ruling 35.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --------------------------------------------------------------------------------------
# Doctrine constants
# --------------------------------------------------------------------------------------

WALK_DIR = "v5"
WALK_LATEST = "walk-latest.json"
WALK_STATE = "walk-state.json"
GRAPH_LATEST = "pathgraph-latest.json"
NEXT_ACTIONS = "next-actions.json"
WAVES_DIR = "waves"

OK = "OK"
GAP = "GAP"
REUSED = "REUSED"

HARNESS = "harness"
OPERATOR = "operator"

# Ruling 37: criticality is assigned from the cost of a SILENT failure, and the four
# CORE components were named at ratification. Each is matched against derived code
# nodes by filename fragment -- deliberately crude, because the alternative is a
# hand-maintained registry that goes stale the first time a file moves, and a stale
# registry reports a CORE component as absent, which is the loudest wrong answer here.
CORE_COMPONENTS = (
    {
        "id": "session-record",
        "plain": "the written record of each working session",
        "cost_of_silence": "a conversation that was never written down cannot be "
                           "reconstructed from anything, at any price",
        "match": ("track", "session"),
    },
    {
        "id": "savepoint",
        "plain": "the ability to stop and pick up exactly where you left off",
        "cost_of_silence": "work in flight is lost with the session that held it",
        "match": ("savepoint",),
    },
    {
        "id": "work-record",
        "plain": "the record of work items and what was promised about them",
        "cost_of_silence": "the project keeps its plans and forgets which ones landed",
        "match": ("lug",),
    },
    {
        "id": "code-map",
        "plain": "the map of this codebase and what proves each part of it",
        "cost_of_silence": "every later judgement is made against a map nobody checked",
        "match": ("pathgraph", "graph"),
    },
)

# The twelve v5 mechanisms, and where each is called from. This registry is the
# answer to "is it wired", checked by a test rather than asserted in prose. A
# mechanism may be DELIBERATELY UNWIRED, but only with a reason recorded here --
# silence about a mechanism is what produced the toolbox in the first place.
MECHANISM_WIRING = {
    "wheel_home_init": {"wired": True, "step": "graph",
                        "note": "step 0 of the walk: does this wheel have a home yet"},
    "pathgraph_derive": {"wired": True, "step": "graph",
                         "note": "step 1: derives the graph and the entry-point set"},
    "lug_code_reconcile": {"wired": True, "step": "reconcile",
                           "note": "step 2: re-runs each completed claim's own oracle"},
    "verification_objects": {"wired": True, "step": "core",
                             "note": "step 3: coverage of CORE components, honesty rule applied"},
    "verify_ratchet": {"wired": True, "step": "core",
                       "note": "step 3: how much of the record can be re-tested at all"},
    "lug_v5": {"wired": True, "step": "harvest",
               "note": "step 4: reads open work in v5 shape without writing it"},
    "lug_lifecycle": {"wired": True, "step": "harvest",
                      "note": "step 4: what the legal next move is for each open item"},
    "confirmer": {"wired": True, "step": "harvest",
                  "note": "step 4: which open items pass review as they stand"},
    "claim_triage": {"wired": True, "step": "harvest",
                     "note": "step 4: unprovable claims sorted into retire/link/runway"},
    "bursar": {"wired": True, "step": "rank",
               "note": "step 5: the ready-backlog demand model behind the ranking"},
    "spoke_advisor": {"wired": True, "step": "rank",
                      "note": "step 5: one verdict on where this spoke actually stands"},
    "phase_certify": {
        "wired": False,
        "step": None,
        "note": "DELIBERATELY UNWIRED. phase_certify runs BOTH benches (a greenfield "
                "recreate plus a brownfield snapshot) to gate a v5 PHASE of the "
                "restructuring initiative. It is a build gate for the initiative, not a "
                "mechanism of a spoke's runtime: an adopting spoke has no phases to "
                "certify, and running two bench suites on every warmup would cost "
                "minutes for an answer that is always 'not applicable here'. Wiring it "
                "into the walk would be wiring for the metric's sake -- exactly the "
                "Goodhart move this initiative exists to refuse.",
    },
}

# Anything matching these never appears in user-facing text. Mechanical, not editorial.
_TOOL_TOKEN_RE = re.compile(
    r"\b(" + "|".join(sorted(MECHANISM_WIRING, key=len, reverse=True)) + r")(\.py)?\b"
)
_ANY_PY_RE = re.compile(r"[\w./\\-]*\.py\b")

# Fingerprint ignores everything under a spoke's runtime dirs: the walk writes there
# itself, so counting them would make every run look changed and incrementality would
# never engage. Ruling 24 -- CODE is the substrate; runtime state is not the substrate.
FINGERPRINT_IGNORE = (
    "WAI-Harness/spoke/local/",
    "WAI-Harness/hub/local/",
    ".worktrees/",
)


# --------------------------------------------------------------------------------------
# Small helpers -- none of these raise
# --------------------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path, default=None):
    try:
        with open(path) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def _write_json(path, payload) -> bool:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            json.dump(payload, handle, indent=2, default=str)
            handle.write("\n")
        return True
    except OSError:
        return False


def base_dir(root, mode=None) -> str:
    """The spoke's runtime base. Falls back to a plain path when no harness layout is
    resolvable, because a project with no WAI history must still be walkable."""
    try:
        import trust_epoch as te  # noqa: PLC0415
        return te.base_dir(root, mode)
    except Exception:  # noqa: BLE001
        for candidate in ("WAI-Harness/spoke/local", "WAI-Harness/spoke", "."):
            p = os.path.join(root, candidate)
            if os.path.isdir(p):
                return p
        return root


def walk_dir(root, mode=None) -> str:
    return os.path.join(base_dir(root, mode), WALK_DIR)


def fingerprint(root) -> dict:
    """A cheap, honest answer to 'has the CODE moved since last time'.

    git HEAD plus a hash of the dirty set is exact where git exists. Where it does
    not, a bounded mtime/size digest is used -- weaker, and labelled weaker, because
    an incremental decision made on an unstated basis is how stale results get
    presented as fresh.
    """
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=20)
        if head.returncode == 0:
            dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                                   capture_output=True, text=True, timeout=60)
            lines = []
            for line in (dirty.stdout or "").splitlines():
                path = line[3:].strip()
                if any(path.startswith(p) or ("/" + p) in path for p in FINGERPRINT_IGNORE):
                    continue
                lines.append(line)
            digest = hashlib.sha256("\n".join(sorted(lines)).encode()).hexdigest()[:16]
            return {"basis": "git", "sha": head.stdout.strip(), "dirty_digest": digest,
                    "dirty_count": len(lines)}
    except Exception:  # noqa: BLE001
        pass
    h = hashlib.sha256()
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "__pycache__", "node_modules", ".venv")]
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            full = os.path.join(dirpath, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            h.update(f"{os.path.relpath(full, root)}:{st.st_mtime_ns}:{st.st_size}".encode())
            count += 1
            if count > 20000:
                break
    return {"basis": "mtime", "sha": None, "dirty_digest": h.hexdigest()[:16],
            "dirty_count": count}


def plain_guard(text: str) -> str:
    """Ruling 12's constraint, enforced mechanically.

    A first-run user must not need to know a single tool name. Wording discipline
    decays; a substitution that runs on every render does not. Any mechanism name and
    any module filename that reaches user-facing text is replaced here rather than
    trusted not to appear -- so the guarantee holds even for text this module has
    never seen, which is exactly the text most likely to leak one.
    """
    text = _TOOL_TOKEN_RE.sub("this harness", text)
    text = _ANY_PY_RE.sub("a code file", text)
    return text


# --------------------------------------------------------------------------------------
# STANCE -- Ruling 39. Findings are facts; ranking is a judgement about intent.
# --------------------------------------------------------------------------------------
#
# The defect this fixes, in one sentence: the first look produced a confident ranked
# list with no idea what the project was FOR. On a legacy codebase under review it
# recommended building; on a project being retired it recommended coverage. Both
# useless, both authoritative-looking.
#
# So the two halves are separated IN CODE. `collect_findings()` returns facts -- 86%
# untested, 6 drifted, 281 described and never built -- and those are true whatever
# anybody intends. `rank_findings()` takes facts plus a STANCE and returns an order.
# There is no path that produces an order without naming the stance it used, including
# the no-stance case, which names itself.
#
# The orderings below are EXPLICIT LISTS, not weights. A weighting scheme cannot be
# read: nobody can look at four coefficients and say why unbuilt ideas come first under
# legacy and eleventh under stabilising. A list can be read by anyone, diffed between
# stances, and argued with -- which is the point, because it encodes a judgement.

# Every finding carries a TOPIC. Kind alone is too coarse: `runway` covers both "281
# ideas nobody built" and "9 items ready to start", and those two are exactly the pair
# that swaps ends between legacy and growing. Ranking on kind would make the stance
# decorative.
_TOPIC_BY_ID = {
    "unbuilt-intent": "unbuilt-ideas",
    "ready-to-build": "nearly-done",
    "underspecified-work": "underspecified",
    "adopt-candidates": "adopt",
    "untested-code": "coverage-debt",
    "weak-proof-ratio": "coverage-debt",
    "diverged-claims": "drift",
    "unverifiable-claims": "unprovable",
    "backfill-blocking-active": "unprovable",
    "linkable-claims": "unprovable",
    "deprecate-wave": "dead-code",
    "undecided-candidates": "dead-code",
    "no-goal": "direction",
    "thin-evidence": "direction",
    "no-entry-points": "missing-map",
    "no-lug-corpus": "missing-map",
    "home-absent": "housekeeping",
    "older-format-items": "housekeeping",
}
_TOPIC_BY_PREFIX = (
    ("core-unproven-", "silent-failure"),
    ("core-absent-", "silent-failure"),
    ("gap-", "walk-gap"),
)
TOPIC_FALLBACK = "housekeeping"

# Plain-language names, so a topic can appear in text a first-run user reads.
TOPIC_PLAIN = {
    "unbuilt-ideas": "ideas written down and never built",
    "nearly-done": "work that is ready to start right now",
    "underspecified": "work that needs one more detail before anyone can pick it up",
    "adopt": "finished code nothing has been switched on to use",
    "coverage-debt": "code with nothing checking it",
    "drift": "finished work that no longer does what it said",
    "unprovable": "claims nobody can re-check",
    "dead-code": "code nothing reaches any more",
    "direction": "what this project is for",
    "missing-map": "missing inputs the review needed",
    "silent-failure": "parts whose failure would be silent",
    "housekeeping": "small tidying",
    "walk-gap": "parts of the review that could not run",
}

ALL_TOPICS = tuple(TOPIC_PLAIN)


def topic_of(fid, kind=None) -> str:
    if fid in _TOPIC_BY_ID:
        return _TOPIC_BY_ID[fid]
    for prefix, topic in _TOPIC_BY_PREFIX:
        if str(fid).startswith(prefix):
            return topic
    return TOPIC_FALLBACK


# The four stances. Each `order` is the complete topic list, most important first.
# Every stance lists every topic, so there is no implicit tail and no topic whose
# position is an accident of omission.
STANCES = {
    "legacy": {
        "id": "legacy",
        "label": "a legacy project being reviewed",
        "question_option": "It is old, and I am reviewing it rather than developing it",
        "means": "You are deciding what this project was and whether it still earns its "
                 "keep. Ideas nobody built are the interesting pile, because they are "
                 "the record of what people meant to do. Code with no tests is expected "
                 "here and is not urgent, and a build plan is the last thing you want.",
        "order": (
            "unbuilt-ideas", "adopt", "dead-code", "direction", "drift", "unprovable",
            "missing-map", "silent-failure", "coverage-debt", "underspecified",
            "nearly-done", "housekeeping", "walk-gap",
        ),
    },
    "stabilising": {
        "id": "stabilising",
        "label": "a project being made reliable",
        "question_option": "It works, and I want it to stop surprising me",
        "means": "You are closing the gap between what this project claims and what it "
                 "does. Work that no longer does what it said leads, then anything that "
                 "would fail silently, then code with nothing checking it. Ideas nobody "
                 "built are noise right now.",
        "order": (
            "drift", "silent-failure", "coverage-debt", "unprovable", "missing-map",
            "nearly-done", "underspecified", "direction", "dead-code", "adopt",
            "housekeeping", "unbuilt-ideas", "walk-gap",
        ),
    },
    "growing": {
        "id": "growing",
        "label": "a project being built out",
        "question_option": "It is going somewhere, and I want to add to it",
        "means": "You are adding capability. Work already ready to start leads, then "
                 "finished code nothing switched on -- the cheapest capability available, "
                 "since it is already written. Missing tests are a debt you can carry for "
                 "now.",
        "order": (
            "nearly-done", "adopt", "unbuilt-ideas", "underspecified", "direction",
            "drift", "silent-failure", "dead-code", "missing-map", "unprovable",
            "housekeeping", "coverage-debt", "walk-gap",
        ),
    },
    "winding-down": {
        "id": "winding-down",
        "label": "a project being retired",
        "question_option": "It is being wound down or handed over",
        "means": "Only what still runs matters. Anything that has drifted or could fail "
                 "silently is worth knowing about because something still depends on it. "
                 "Almost everything else drops to nothing -- nobody is going to test, "
                 "sharpen or build any of it.",
        "order": (
            "drift", "silent-failure", "unprovable", "dead-code", "housekeeping",
            "missing-map", "coverage-debt", "direction", "nearly-done",
            "underspecified", "adopt", "unbuilt-ideas", "walk-gap",
        ),
    },
}

DECLINED = "declined"

# What the list is ranked by when nobody has said what the project is for. Said out
# loud rather than implied, because the failure mode Ruling 39 names is a confident
# priority the tool cannot actually justify.
COST_AND_RISK_NOTE = (
    "You have not said what this project is for, so this list is ordered by cost and "
    "risk only: what would hurt most if it were wrong, biggest first. It is NOT ordered "
    "by what moves you toward anything, because nothing here knows what you are aiming "
    "at. Say what this project is for and the same facts come back in a different order."
)

STANCE_FILE = "stance.json"


def stance_path(root, mode=None) -> str:
    return os.path.join(walk_dir(root, mode), STANCE_FILE)


def read_stance(root, mode=None) -> dict:
    """What this project has said about itself, if anything.

    `asked` is stored separately from `stance` on purpose. Declining is a real answer
    and has to be remembered as one -- if only the stance were stored, a decline would
    be indistinguishable from never having been asked, and the question would come
    back every session. That is the ceremony Ruling 12 forbids, arrived at by accident.
    """
    rec = _read_json(stance_path(root, mode), None)
    if not isinstance(rec, dict):
        return {"stance": None, "asked": False, "answered_at": None}
    st = rec.get("stance")
    if st not in STANCES and st != DECLINED:
        st = None
    return {"stance": st, "asked": bool(rec.get("asked")),
            "answered_at": rec.get("answered_at")}


def record_stance(root, mode=None, stance=None) -> dict:
    """Store the answer once. `stance=None` or DECLINED both record a decline."""
    value = stance if stance in STANCES else DECLINED
    rec = {"schema": "v5-stance-1", "stance": value, "asked": True,
           "answered_at": _now_iso(),
           "note": "Asked once. Change it at any time; nothing re-asks on its own."}
    _write_json(stance_path(root, mode), rec)
    return {"stance": value, "asked": True, "answered_at": rec["answered_at"]}


def should_ask_stance(root, mode=None) -> bool:
    return not read_stance(root, mode)["asked"]


def stance_question(width: int = 78) -> str:
    """One question, in plain words, with both consequences stated.

    Deliberately not a ceremony: no wizard, no required field, no second screen. It is
    a paragraph with four options and a stated way to ignore it, and it is asked once
    whatever the answer -- including no answer at all.
    """
    lines = []
    lines.append("-" * width)
    lines.append("ONE QUESTION, AND YOU CAN SKIP IT")
    lines.append("-" * width)
    lines.append("What is this project for right now? I only ask once.")
    lines.append("")
    for key in ("legacy", "stabilising", "growing", "winding-down"):
        s = STANCES[key]
        lines.append(f"  {key:<13} {s['question_option']}")
    lines.append("")
    lines.append("If you answer, the same facts come back in a different order: what I")
    lines.append("put first changes completely between a project you are retiring and one")
    lines.append("you are building out.")
    lines.append("")
    lines.append("If you skip it, you still get the full list -- ordered by cost and risk")
    lines.append("alone, and labelled as such. Nothing is withheld and nothing waits on")
    lines.append("you. I will not ask again either way.")
    lines.append("-" * width)
    return plain_guard("\n".join(lines))


# --------------------------------------------------------------------------------------
# Findings -- one shape, whatever produced them (Ruling 26)
# --------------------------------------------------------------------------------------

def finding(fid, kind, severity, owner, plain, why, evidence=None, count=None):
    return {
        "id": fid,
        "kind": kind,
        "topic": topic_of(fid, kind),
        "severity": severity,      # 5 alarm .. 1 informational
        "owner": owner,            # HARNESS: actionable unattended. OPERATOR: needs a human.
        "plain": plain,            # the sentence a first-run user reads
        "why": why,                # what it costs to leave it
        "count": count,
        "evidence": evidence or {},
    }


def _step(step_id, title, status, headline, detail=None, data=None, findings=None,
          seconds=None):
    return {
        "id": step_id,
        "title": title,
        "status": status,
        "headline": headline,
        "detail": detail,
        "data": data or {},
        "findings": findings or [],
        "seconds": seconds,
    }


def _guarded(step_id, title, fn, *args, **kwargs):
    """Ruling 35 in code. A step that raises becomes a GAP and the walk continues.

    There is deliberately no re-raise path and no strict mode. A strict mode is a
    setting somebody turns on once, and then the walk blocks a build -- which is the
    exact arrangement Ruling 35 forbids.
    """
    started = time.time()
    try:
        step = fn(*args, **kwargs)
        step["seconds"] = round(time.time() - started, 2)
        return step
    except Exception as exc:  # noqa: BLE001
        return _step(
            step_id, title, GAP,
            f"could not be completed here: {type(exc).__name__}",
            detail=str(exc)[:400],
            findings=[finding(
                f"gap-{step_id}", "walk_gap", 2, OPERATOR,
                f"One part of the review could not run here ({title.lower()}).",
                "Everything else still ran; this part reported itself rather than "
                "stopping the rest.",
                evidence={"error": f"{type(exc).__name__}: {str(exc)[:200]}"},
            )],
            seconds=round(time.time() - started, 2),
        )


# --------------------------------------------------------------------------------------
# STEP 1 -- derive the graph
# --------------------------------------------------------------------------------------

def step_graph(root, mode, out_dir, run_tests=False, prev_snapshot=None):
    import pathgraph_derive as pg  # noqa: PLC0415

    findings = []
    data = {}

    # Step 0, folded in: does this wheel have a home? A spoke with no home has no
    # place to put anything the rest of the walk produces.
    try:
        import wheel_home_init as whi  # noqa: PLC0415
        home = whi.detect(root, mode)
        data["home"] = {"state": home.get("state"), "reason": home.get("reason")}
        if home.get("state") == getattr(whi, "NO_HUB", "NO_HUB"):
            findings.append(finding(
                "home-absent", "wheel_home", 3, OPERATOR,
                "This project is not yet attached to a shared home.",
                "It can work entirely on its own; attaching later adds cross-project "
                "coordination and shared settings.",
                evidence={"state": home.get("state")},
            ))
    except Exception as exc:  # noqa: BLE001
        data["home"] = {"state": "UNKNOWN", "reason": f"{type(exc).__name__}"}

    # Entry points first (Ruling 28.2): without a declared entry-point set, unreachable
    # code is an opinion dressed as analysis, and this tool reports UNAVAILABLE instead.
    ep_path = os.path.join(out_dir, "entry-points.json")
    try:
        nodes = pg.scan_project(Path(root))
        registry = pg.derive_entry_points_registry(Path(root), nodes)
        _write_json(ep_path, registry)
        data["entry_points"] = len(registry.get("entry_points", []) or [])
    except Exception as exc:  # noqa: BLE001
        ep_path = None
        data["entry_points_error"] = f"{type(exc).__name__}: {exc}"[:200]

    lugs_dir = os.path.join(base_dir(root, mode), "lugs")
    if not os.path.isdir(lugs_dir):
        lugs_dir = None
        findings.append(finding(
            "no-lug-corpus", "missing_input", 1, HARNESS,
            "There is no existing record of past work here to lay over the code.",
            "Nothing is lost -- the map is built from the code itself. Past intent "
            "simply has nothing to contribute yet.",
        ))

    snapshot = pg.derive_graph(
        Path(root),
        entry_points_file=ep_path,
        lugs_dir=lugs_dir,
        run_tests_flag=run_tests,
    )
    fi = snapshot.get("functional_identity", {})

    delta = None
    if prev_snapshot:
        try:
            delta = pg.diff_snapshots(prev_snapshot, snapshot)
            snapshot["delta"] = delta
        except Exception:  # noqa: BLE001
            delta = None

    _write_json(os.path.join(out_dir, GRAPH_LATEST), snapshot)

    nodes_n = fi.get("node_count") or 0
    tested = fi.get("tested_count") or 0
    untested = max(0, nodes_n - tested)
    data["functional_identity"] = fi

    if nodes_n and untested:
        pct = round(100 * untested / nodes_n)
        findings.append(finding(
            "untested-code", "coverage", 3 if pct >= 50 else 2, OPERATOR,
            f"{untested} of {nodes_n} code files have no test that touches them "
            f"({pct}%).",
            "A part with no test is a part nobody can check after it changes. "
            "This is the cheapest signal available and it needs no judgement call.",
            evidence={"untested": untested, "total": nodes_n},
            count=untested,
        ))

    dead = snapshot.get("dead_code", {}) or {}
    if dead.get("status") == "UNAVAILABLE":
        findings.append(finding(
            "no-entry-points", "missing_input", 2, OPERATOR,
            "Nothing here declares where this project starts running, so unused code "
            "cannot be identified.",
            "Without a starting point, 'nothing calls this' is a guess. Declaring the "
            "entry points turns it into a decidable question.",
        ))
    else:
        by_disp = {"DEPRECATE": [], "ADOPT": [], "UNDECIDED": []}
        for cand in dead.get("candidates", []) or []:
            by_disp.setdefault(cand.get("disposition", "UNDECIDED"), []).append(cand)
        data["dispositions"] = {k: len(v) for k, v in by_disp.items()}
        if by_disp["DEPRECATE"]:
            findings.append(finding(
                "deprecate-wave", "dead_code", 2, OPERATOR,
                f"{len(by_disp['DEPRECATE'])} file(s) look superseded and nothing "
                f"reaches them.",
                "They can be removed, but only when you say so -- nothing here deletes "
                "anything on its own.",
                evidence={"paths": [c.get("path") for c in by_disp["DEPRECATE"][:20]]},
                count=len(by_disp["DEPRECATE"]),
            ))
        if by_disp["ADOPT"]:
            findings.append(finding(
                "adopt-candidates", "dead_code", 3, OPERATOR,
                f"{len(by_disp['ADOPT'])} file(s) look sound and finished but nothing "
                f"uses them.",
                "This project has a documented habit of building something correct and "
                "never switching it on. This is that pile, and it is usually the "
                "cheapest value on the list.",
                evidence={"paths": [c.get("path") for c in by_disp["ADOPT"][:20]]},
                count=len(by_disp["ADOPT"]),
            ))
        if by_disp["UNDECIDED"]:
            findings.append(finding(
                "undecided-candidates", "dead_code", 1, OPERATOR,
                f"{len(by_disp['UNDECIDED'])} unreachable file(s) have no honest verdict "
                f"yet.",
                "Left visible on purpose rather than assumed to be waste.",
                count=len(by_disp["UNDECIDED"]),
            ))

    headline = (f"{nodes_n} code file(s), {tested} covered by a test, "
                f"{fi.get('test_edge_count', 0)} test link(s)")
    if delta:
        data["delta_summary"] = {k: len(v) if isinstance(v, list) else v
                                 for k, v in delta.items()}
    return _step("graph", "Map the code", OK, headline, data=data, findings=findings)


# --------------------------------------------------------------------------------------
# STEP 2 -- reconcile the claims against the code
# --------------------------------------------------------------------------------------

def step_reconcile(root, mode, force=False):
    import lug_code_reconcile as lcr  # noqa: PLC0415

    base = Path(base_dir(root, mode))
    if not (base / "lugs").is_dir():
        return _step("reconcile", "Re-check what the record claims", GAP,
                     "no record of past work here, so nothing to re-check",
                     findings=[])

    report = lcr.reconcile(Path(root), base, force=force)
    counts = report.get("counts", {})
    findings = []
    diverged = counts.get("DIVERGED", 0)
    unreconcilable = counts.get("UNRECONCILABLE", 0)
    reconciled = counts.get("RECONCILED", 0)

    if diverged:
        findings.append(finding(
            "diverged-claims", "diverged", 4, OPERATOR,
            f"{diverged} finished item(s) no longer do what they said they did.",
            "Each of these shipped with its own check, and that check now fails. "
            "Either the code moved or the check went stale -- deciding which is a "
            "judgement call, so it is yours.",
            evidence={"ids": (report.get("diverged_ids") or [])[:20]},
            count=diverged,
        ))
    if unreconcilable:
        findings.append(finding(
            "unverifiable-claims", "unverifiable", 3, OPERATOR,
            f"{unreconcilable} finished item(s) cannot be re-checked at all.",
            "They were closed against a description rather than something a machine "
            "can run. That is not a pass and it is not a failure -- it is a claim "
            "nobody can test.",
            count=unreconcilable,
        ))

    status = REUSED if report.get("skipped") and not report.get("executed") else OK
    headline = (f"{report.get('total', 0)} finished item(s): {reconciled} still hold, "
                f"{diverged} drifted, {unreconcilable} untestable")
    if status == REUSED:
        headline += "  (nothing changed since last time -- reused)"
    return _step("reconcile", "Re-check what the record claims", status, headline,
                 data={"counts": counts, "executed": report.get("executed"),
                       "skipped": report.get("skipped"), "sha": report.get("sha")},
                 findings=findings)


# --------------------------------------------------------------------------------------
# STEP 3 -- surface unproven CORE components (Ruling 37)
# --------------------------------------------------------------------------------------

def _core_targets(snapshot):
    """Map each CORE component onto the code nodes that implement it here."""
    nodes = (snapshot or {}).get("nodes", {}) or {}
    states = (snapshot or {}).get("node_states", {}) or {}
    out = []
    for comp in CORE_COMPONENTS:
        matched = []
        for rel_path, node in nodes.items():
            if node.get("kind") == "test":
                continue
            stem = os.path.basename(rel_path).lower()
            if any(frag in stem for frag in comp["match"]):
                matched.append(rel_path)
        tested = [p for p in matched if (states.get(p) or {}).get("tested") == "TESTED"]
        proven = [p for p in matched if (states.get(p) or {}).get("proof") == "PROVEN"]
        out.append({"component": comp, "paths": matched,
                    "tested": tested, "proven": proven})
    return out


def _carries_harness(root, mode) -> bool:
    """Does this project actually take on the responsibilities CORE describes?

    Ruling 28.5: greenfield must not read as failure. The four CORE components are
    the WHEEL's responsibilities -- session record, savepoints, work record, code
    map. A four-file script that has never adopted any of that is not failing four
    critical checks; it simply has not taken those duties on. Reporting it as four
    alarms is the exact instrument-teaching-you-to-ignore-it failure 28.5 names, and
    it was the first thing this walk did wrong on a greenfield tree.
    """
    base = base_dir(root, mode)
    return os.path.isdir(os.path.join(base, "sessions")) or os.path.isfile(
        os.path.join(base, "WAI-State.json"))


def step_core(root, mode, snapshot):
    import verification_objects as vo  # noqa: PLC0415

    findings = []
    carries = _carries_harness(root, mode)
    data = {"components": [], "carries_harness": carries}

    targets = []
    coverage_targets = []
    for entry in _core_targets(snapshot):
        comp = entry["component"]
        targets.append(entry)
        for p in entry["paths"][:50]:
            coverage_targets.append({"kind": "code", "ref": p})

    # verification_objects owns the honesty rule: a verification that cannot be
    # executed never moves its target out of UNCOVERED. Building the verification
    # set from the derived test edges keeps that rule applying to REAL evidence
    # rather than to a declaration about evidence.
    verifications = []
    for edge in (snapshot or {}).get("test_edges", []) or []:
        verifications.append({
            "id": f"edge::{edge.get('test_path')}::{edge.get('code_path')}",
            "executability": ("EXECUTABLE" if edge.get("strength") == "strong"
                              else "UNEXECUTABLE"),
            "coverage": [{"kind": "code", "ref": edge.get("code_path")}],
        })
    coverage = {}
    if coverage_targets:
        coverage = vo.compute_coverage(verifications, coverage_targets)
    data["coverage_summary"] = {
        "targets": len(coverage_targets),
        "uncovered": sum(1 for v in coverage.values() if v["status"] == "UNCOVERED"),
        "weak": sum(1 for v in coverage.values() if v["status"] == "WEAKLY_COVERED"),
        "redundant": sum(1 for v in coverage.values()
                         if v["status"] == "REDUNDANTLY_COVERED"),
    }

    for entry in targets:
        comp = entry["component"]
        record = {"id": comp["id"], "plain": comp["plain"],
                  "files": len(entry["paths"]), "tested": len(entry["tested"]),
                  "proven": len(entry["proven"])}
        data["components"].append(record)
        if not entry["paths"]:
            if carries:
                findings.append(finding(
                    f"core-absent-{comp['id']}", "core_absent", 4, OPERATOR,
                    f"Nothing here implements {comp['plain']}.",
                    f"This project keeps the kind of history that depends on it, so "
                    f"its absence is a real gap: {comp['cost_of_silence']}.",
                ))
            continue
        if not entry["tested"]:
            findings.append(finding(
                f"core-unproven-{comp['id']}", "core_unproven", 5, OPERATOR,
                f"Nothing checks {comp['plain']} -- and it is one of the few parts "
                f"whose failure would be silent.",
                f"{comp['cost_of_silence'].capitalize()}. A part like that cannot sit "
                f"unchecked: no news is the failure mode, not the healthy state.",
                evidence={"files": entry["paths"][:10]},
                count=len(entry["paths"]),
            ))

    # verify_ratchet: how much of the record can be re-tested at all, with a floor
    # that only rises.
    try:
        import verify_ratchet as vr  # noqa: PLC0415
        measured = vr.measure(Path(root))
        data["verify_ratchet"] = measured
        ratio = measured.get("ratio")
        if ratio is not None and ratio < 0.5 and measured.get("total"):
            findings.append(finding(
                "weak-proof-ratio", "proof_ratio", 3, OPERATOR,
                f"Only {round(ratio * 100)}% of finished work here shipped a check a "
                f"machine can re-run.",
                "The rest was closed against a description. Those claims can never be "
                "re-tested, so they age into folklore rather than into evidence.",
                evidence={"executable": measured.get("executable"),
                          "total": measured.get("total")},
            ))
    except Exception as exc:  # noqa: BLE001
        data["verify_ratchet_error"] = f"{type(exc).__name__}: {exc}"[:200]

    alarms = sum(1 for f in findings if f["severity"] >= 5)
    present = sum(1 for c in data["components"] if c["files"])
    if not carries:
        headline = (f"{present} of {len(data['components'])} responsibilities are "
                    f"taken on here; the rest are not this project's job yet")
    else:
        headline = (f"{len(data['components'])} critical part(s) examined, {alarms} with "
                    f"nothing checking them")
    return _step("core", "Check the parts that fail silently", OK, headline,
                 data=data, findings=findings)


# --------------------------------------------------------------------------------------
# STEP 4 -- harvest what is nearly done (Ruling 33.3: runway, not debt)
# --------------------------------------------------------------------------------------

_ACTOR = {"model": "v5-walk", "provider": "deterministic"}
_FIXED_AT = "2026-01-01T00:00:00+00:00"   # pure inputs: no clock inside the migration

# Review failures that say nothing about the WORK -- only that an older record was
# written before these fields existed. See the comment at the call site: separating
# these is what stops the review reporting a 100% failure rate that means nothing.
_SHAPE_ONLY_CHECKS = frozenset({"schema_valid", "model_profile_complete"})


def _open_lug_paths(base: Path, limit=400):
    out = []
    lugs = base / "lugs"
    if not lugs.is_dir():
        return out
    for sub in ("bytype", "incoming"):
        d = lugs / sub
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*.json")):
            parts = {x.lower() for x in p.parts}
            if "completed" in parts or "archive" in parts or "archived" in parts:
                continue
            out.append(p)
            if len(out) >= limit:
                return out
    return out


def step_harvest(root, mode, snapshot):
    import lug_v5  # noqa: PLC0415
    import lug_lifecycle  # noqa: PLC0415
    import confirmer  # noqa: PLC0415

    base = Path(base_dir(root, mode))
    findings = []
    data = {}

    paths = _open_lug_paths(base)
    data["open_examined"] = len(paths)
    ready_now, needs_work, invalid, shape_only = [], [], [], []
    for p in paths:
        rec = _read_json(p)
        if not isinstance(rec, dict):
            continue
        try:
            v5 = lug_v5.migrate_v4_lug(rec, _ACTOR, _FIXED_AT)
        except Exception:  # noqa: BLE001
            invalid.append(p.name)
            continue
        state = v5.get("state")
        # lug_lifecycle answers "what is the legal next move from here" -- the
        # difference between an item that is one step from done and one that is not
        # started is the whole point of harvesting.
        try:
            legal = sorted(lug_v5.TRANSITIONS.get(state, frozenset()))
        except Exception:  # noqa: BLE001
            legal = []
        if state in ("READY_TO_REVIEW", "IMPLEMENTATION_REVIEW"):
            try:
                report = confirmer.review(v5, _FIXED_AT, _ACTOR)
                if report.get("outcome") == "APPROVE":
                    ready_now.append({"id": v5.get("id"), "reason": "approved as it stands"})
                else:
                    failed = {c.get("name") for c in report.get("findings", [])}
                    # MEASURED on the basher clone: 193 of 193 open items were rejected,
                    # every one of them for carrying an older item TYPE and no model
                    # profile -- fields the newer format wants and the older one never
                    # had. Reporting that as "your work is underspecified" would be a
                    # false finding at 100% rate, and a false finding at 100% rate is
                    # how an instrument teaches people to ignore it. So the two are
                    # separated: a shape mismatch inherited from the older format is
                    # the harness's problem, and only a genuinely missing acceptance
                    # criterion, check or forecast is the author's.
                    if failed and failed <= _SHAPE_ONLY_CHECKS:
                        shape_only.append(v5.get("id"))
                    else:
                        needs_work.append({
                            "id": v5.get("id"),
                            "missing": sorted(failed - _SHAPE_ONLY_CHECKS),
                            "reason": report.get("reason", "")[:200],
                        })
            except Exception:  # noqa: BLE001
                needs_work.append({"id": v5.get("id"), "missing": [],
                                   "reason": "could not be reviewed"})
        data.setdefault("next_moves", {}).setdefault(state or "UNKNOWN", 0)
        data["next_moves"][state or "UNKNOWN"] += 1
        data.setdefault("_legal_sample", legal)

    data["ready_now"] = len(ready_now)
    data["needs_work"] = len(needs_work)
    data["shape_only"] = len(shape_only)
    data["rework_causes_available"] = sorted(getattr(lug_lifecycle, "REWORK_CAUSES", []))

    if shape_only:
        findings.append(finding(
            "older-format-items", "migration", 1, HARNESS,
            f"{len(shape_only)} open item(s) are recorded in the older format.",
            "Nothing is wrong with them and nothing is lost. They are converted as "
            "they are touched rather than in one sweep, so no bulk rewrite is needed.",
            count=len(shape_only),
        ))

    if ready_now:
        findings.append(finding(
            "ready-to-build", "runway", 4, HARNESS,
            f"{len(ready_now)} open item(s) are complete enough to start on right now.",
            "They already say what to do, how to tell it worked, and what it costs. "
            "Nothing is waiting on you for these.",
            evidence={"ids": [r["id"] for r in ready_now[:20]]},
            count=len(ready_now),
        ))
    if needs_work:
        findings.append(finding(
            "underspecified-work", "runway", 2, OPERATOR,
            f"{len(needs_work)} open item(s) are missing something concrete -- how "
            f"you would know they worked, or what they are expected to cost.",
            "They are partway down the runway, not lost. Each needs one specific "
            "thing added before anyone could pick it up and finish it.",
            evidence={"sample": needs_work[:10]},
            count=len(needs_work),
        ))

    # Unbuilt intent: the overlay's UNRESOLVED set (Ruling 25) -- things described and
    # never built -- plus claim_triage's backfill bucket over finished-but-unprovable.
    overlay = (snapshot or {}).get("overlay", {}) or {}
    unresolved = overlay.get("backlog_candidates", []) or []
    data["unbuilt_intent"] = len(unresolved)
    if unresolved:
        findings.append(finding(
            "unbuilt-intent", "runway", 3, OPERATOR,
            f"{len(unresolved)} thing(s) were described here and never built.",
            "This is runway, not debt: the thinking is already done and recorded. "
            "Each one is a decision to land it or let it go.",
            count=len(unresolved),
        ))

    try:
        import claim_triage as ct  # noqa: PLC0415
        triaged = ct.triage(
            lugs_root=base / "lugs",
            catalog_path=base / "archeologist" / "catalog.jsonl",
            tests_root=Path(root) / "WAI-Harness" / "spoke" / "managed" / "tests",
            reconcile_path=base / "lug-reconcile" / "results.jsonl",
        )
        data["triage"] = {k: v for k, v in triaged.items()
                          if k.endswith("_count") or k.endswith("_source")}
        if triaged.get("link_count"):
            findings.append(finding(
                "linkable-claims", "runway", 2, HARNESS,
                f"{triaged['link_count']} unprovable claim(s) have a likely matching "
                f"test already in the tree.",
                "Connecting a claim to the test that already covers it is mechanical "
                "and needs nobody's opinion.",
                count=triaged["link_count"],
            ))
        if triaged.get("depended_upon_backfill_count"):
            findings.append(finding(
                "backfill-blocking-active", "runway", 3, OPERATOR,
                f"{triaged['depended_upon_backfill_count']} unprovable claim(s) are "
                f"depended on by work that is still active.",
                "Active work is resting on claims nobody can check.",
                count=triaged["depended_upon_backfill_count"],
            ))
    except Exception as exc:  # noqa: BLE001
        data["triage_error"] = f"{type(exc).__name__}: {exc}"[:200]

    headline = (f"{len(ready_now)} item(s) ready to start, {len(needs_work)} need "
                f"sharpening, {len(shape_only)} in the older format, "
                f"{len(unresolved)} never built")
    return _step("harvest", "Find what is nearly done", OK, headline,
                 data=data, findings=findings)


# --------------------------------------------------------------------------------------
# STEP 5 -- rank what needs the operator
# --------------------------------------------------------------------------------------

def step_rank(root, mode, snapshot, prior_findings):
    import bursar  # noqa: PLC0415
    import spoke_advisor as sa  # noqa: PLC0415

    base = Path(base_dir(root, mode))
    findings = []
    data = {}

    # Field names are read from the demand model's OWN dataclass, not guessed. The
    # first version of this call guessed `ready_count`/`ready_effort`, got None for
    # both, and rendered "0 items ready to work" over a real backlog -- a fabricated
    # zero, which is worse than an error because it looks like an answer.
    demand = None
    ready_count = ready_effort = blocked_effort = None
    try:
        demand = bursar.compute_ready_backlog(base / "lugs")
        ready_count = demand.count
        ready_effort = demand.total_effort
        blocked_effort = demand.blocked_effort
        data["backlog"] = {
            "ready_count": ready_count,
            "ready_effort": ready_effort,
            "blocked_effort": blocked_effort,
            "forecast_confidence": demand.forecast_confidence,
            "max_age_days": demand.max_age_days,
            "weighted_impact": demand.weighted_impact,
        }
    except Exception as exc:  # noqa: BLE001
        data["backlog_error"] = f"{type(exc).__name__}: {exc}"[:200]

    state = _read_json(os.path.join(str(base), "WAI-State.json"), {}) or {}
    wheel = state.get("wheel", {}) if isinstance(state.get("wheel"), dict) else {}
    goal = wheel.get("goal") or state.get("goal")

    snap = sa.SpokeSnapshot(
        spoke_id=str(wheel.get("name") or os.path.basename(os.path.abspath(root))),
        goals_declared=bool(goal),
        ready_count=int(ready_count or 0),
        ready_effort=float(ready_effort or 0.0),
        blocked_effort=float(blocked_effort or 0.0),
        forecast_confidence=getattr(demand, "forecast_confidence", None),
    )
    verdict = sa.evaluate(snap)
    data["verdict"] = {"verdict": verdict.verdict,
                       "performance_score": verdict.performance_score,
                       "utilization": verdict.utilization,
                       "recommendation": verdict.recommendation,
                       "gap": verdict.gap,
                       "evidence": list(verdict.evidence)[:8]}

    if not goal:
        # The instrument raised this itself, unprompted, before Ruling 39 named it:
        # everything else can be ranked by cost and risk and nothing can be ranked by
        # whether it moves you anywhere. The stance is where that answer now goes, so
        # once one is recorded this stops being a top-four alarm and becomes the much
        # smaller thing it actually is -- a coarse answer given, a specific one not.
        declared = read_stance(root, mode)
        if declared["stance"] in STANCES:
            findings.append(finding(
                "no-goal", "direction", 2, OPERATOR,
                f"You have said this is {STANCES[declared['stance']]['label']}, but not "
                f"in one sentence what it is for.",
                "The list below is already ordered around that answer. A specific "
                "sentence would sharpen it further, and nothing is blocked without one.",
            ))
        else:
            findings.append(finding(
                "no-goal", "direction", 4, OPERATOR,
                "This project has not written down what it is for.",
                "Everything below can be ranked by cost and risk, but nothing can be "
                "ranked by whether it moves you toward anything. One sentence fixes it.",
            ))
    if verdict.verdict == "INVESTIGATE":
        findings.append(finding(
            "thin-evidence", "direction", 2, HARNESS,
            "There is not yet enough measured history here to judge how this project "
            "is doing.",
            "That is expected on a first run. It resolves by itself as work moves "
            "through.",
            evidence={"reason": verdict.gap or verdict.recommendation},
        ))

    if ready_count is None:
        headline = "the size of the ready backlog could not be measured here"
    else:
        headline = (f"{ready_count} item(s) ready to work "
                    f"({round(float(ready_effort or 0), 1)} effort), "
                    f"{round(float(blocked_effort or 0), 1)} effort blocked")
    data["prior_finding_count"] = len(prior_findings)
    return _step("rank", "Decide what comes first", OK, headline,
                 data=data, findings=findings)


# --------------------------------------------------------------------------------------
# OZI -- one ranked list, split by who has to act (Ruling 26)
# --------------------------------------------------------------------------------------

def collect_findings(walk_result: dict) -> list:
    """The FACTS, in the order the walk produced them. No judgement applied.

    Ruling 39's first half. Nothing here knows or cares what the project is for:
    281 things described and never built is 281 things described and never built
    whether you are retiring the project or growing it. Every finding is stamped
    with its topic here, so a finding that predates the topic map (or arrives from
    somewhere else entirely) still ranks rather than silently vanishing.
    """
    findings = []
    for step in walk_result.get("steps", []):
        for f in step.get("findings", []):
            if "topic" not in f:
                f = dict(f, topic=topic_of(f.get("id", ""), f.get("kind")))
            findings.append(f)
    return findings


def rank_findings(findings: list, stance=None) -> list:
    """Ruling 39's second half: the JUDGEMENT, and it needs a stance to exist.

    With a stance, the topic's position in that stance's explicit order dominates and
    severity only breaks ties inside a topic. That is the whole mechanism: the same
    facts, re-sorted by what the project is for.

    With no stance (never asked, or declined) this falls back to exactly what it did
    before -- severity, then size, then id -- which is cost and risk and nothing else.
    That fallback is honest only because everything that renders it says so; see
    COST_AND_RISK_NOTE.
    """
    spec = STANCES.get(stance)
    if spec:
        position = {t: i for i, t in enumerate(spec["order"])}
        tail = len(spec["order"])

        def key(f):
            topic = f.get("topic") or topic_of(f.get("id", ""), f.get("kind"))
            return (position.get(topic, tail), -f.get("severity", 0),
                    -(f.get("count") or 0), f.get("id", ""))
    else:
        def key(f):
            return (-f.get("severity", 0), -(f.get("count") or 0), f.get("id", ""))

    ordered = sorted(findings, key=key)
    return [dict(f, rank=i) for i, f in enumerate(ordered, 1)]


def ozi_prioritise(walk_result: dict, stance=None) -> dict:
    """Ozi's single job here: consume the walk and emit ONE ranked list.

    Not twelve tool outputs side by side -- that is the firehose Ruling 26 forbids,
    reassembled by accident. Deterministic either way, so two runs over the same state
    and the same stance produce the same list and a human can tell when something moved.
    """
    findings = collect_findings(walk_result)
    ranked = rank_findings(findings, stance)
    spec = STANCES.get(stance)

    return {
        "ranked_at": _now_iso(),
        "stance": spec["id"] if spec else (DECLINED if stance == DECLINED else None),
        "stance_label": spec["label"] if spec else None,
        "ranked_by": ("what this project is for" if spec else "cost and risk only"),
        "ranking_basis_note": None if spec else COST_AND_RISK_NOTE,
        "stance_order": list(spec["order"]) if spec else None,
        "ranked": ranked,
        "i_can_do": [f for f in ranked if f["owner"] == HARNESS],
        "needs_you": [f for f in ranked if f["owner"] == OPERATOR],
        "alarms": [f for f in ranked if f.get("severity", 0) >= 5],
    }


# --------------------------------------------------------------------------------------
# OTTO -- explain it to somebody who has never heard of any of this (Ruling 12)
# --------------------------------------------------------------------------------------

_SEV_WORD = {5: "urgent", 4: "important", 3: "worth doing", 2: "when convenient",
             1: "for information"}


def _wrap(text, width):
    words, line, out = str(text).split(), "", []
    for w in words:
        if line and len(line) + 1 + len(w) > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out


def otto_explain(walk_result: dict, priorities: dict, width: int = 78) -> str:
    """The only text a first-run user has to read.

    Passed through plain_guard() at the end, so no tool name and no module filename
    can reach it whatever the findings contain.
    """
    name = walk_result.get("project") or "this project"
    lines = []
    lines.append("=" * width)
    lines.append(f"FIRST LOOK AT {str(name).upper()}")
    lines.append("=" * width)
    lines.append("")
    lines.append("I read the code first and the paperwork second, because the code is")
    lines.append("the only part that cannot be wrong about itself. Here is what I found,")
    lines.append("what it means, and what I would do next.")
    lines.append("")

    # Ruling 39, rendered. The facts above this line hold whatever the answer; the
    # ORDER below it does not, and the reader is told which one they are getting.
    spec = STANCES.get(priorities.get("stance"))
    if spec:
        lines.append("HOW THIS IS ORDERED")
        lines.append(f"  You told me this is {spec['label']}.")
        for chunk in _wrap(spec["means"], width - 2):
            lines.append(f"  {chunk}")
        lines.append("  The findings themselves would be the same either way -- what")
        lines.append("  changes is which one I put first.")
        lines.append("")
    else:
        lines.append("HOW THIS IS ORDERED")
        for chunk in _wrap(COST_AND_RISK_NOTE, width - 2):
            lines.append(f"  {chunk}")
        lines.append("")

    lines.append("WHAT I LOOKED AT")
    for step in walk_result.get("steps", []):
        mark = {OK: "done", GAP: "could not", REUSED: "unchanged"}.get(step["status"], "done")
        lines.append(f"  - {step['title']}: {step['headline']}")
        if step["status"] == GAP:
            lines.append("      (reported as a gap and the review carried on -- a missing")
            lines.append("       input is never allowed to stop the rest)")
        elif step["status"] == REUSED:
            lines.append("      (nothing had changed since the last look, so I reused it)")
    lines.append("")

    alarms = priorities.get("alarms", [])
    if alarms:
        lines.append("READ THIS FIRST")
        for a in alarms:
            lines.append(f"  ! {a['plain']}")
            lines.append(f"    {a['why']}")
        lines.append("")

    needs_you = priorities.get("needs_you", [])
    lines.append("WHAT NEEDS YOU  (ranked, most costly to ignore first)")
    if not needs_you:
        lines.append("  Nothing. Everything found here can be handled without you.")
    for i, f in enumerate(needs_you[:8], 1):
        lines.append(f"  {i}. [{_SEV_WORD.get(f['severity'], 'worth doing')}] {f['plain']}")
        lines.append(f"     Why it matters: {f['why']}")
    if len(needs_you) > 8:
        lines.append(f"  ... and {len(needs_you) - 8} more, in the saved list below.")
    lines.append("")

    mine = priorities.get("i_can_do", [])
    lines.append("WHAT I CAN DO WITHOUT ASKING")
    if not mine:
        lines.append("  Nothing right now -- every open item needs a decision from you.")
    for i, f in enumerate(mine[:6], 1):
        lines.append(f"  {i}. {f['plain']}")
    lines.append("")

    lines.append("THE ONE THING TO DO NEXT")
    first = (needs_you or priorities.get("ranked") or [None])[0]
    if first:
        lines.append(f"  {first['plain']}")
        lines.append(f"  {first['why']}")
    else:
        lines.append("  Nothing is pressing. Start on whatever you came here to do.")
    lines.append("")

    lines.append("HOW TO READ THIS AGAIN")
    lines.append(f"  The full ranked list is saved at: {walk_result.get('saved_to', 'n/a')}")
    lines.append("  Nothing was deleted, changed, or decided on your behalf. Removal of")
    lines.append("  anything only happens when you explicitly authorise it, and it leaves")
    lines.append("  a receipt naming every file.")
    lines.append("=" * width)
    if priorities.get("ask_stance"):
        lines.append("")
        lines.append(stance_question(width))
    return plain_guard("\n".join(lines))


# --------------------------------------------------------------------------------------
# THE WALK
# --------------------------------------------------------------------------------------

def walk(root, mode=None, run_tests=False, force=False, apply=False, stance=None) -> dict:
    """Run the five steps. Never raises. Never blocks. Always produces a result."""
    root = os.path.abspath(root)
    out_dir = walk_dir(root, mode)
    started = time.time()

    fp = fingerprint(root)
    state = _read_json(os.path.join(out_dir, WALK_STATE), {}) or {}
    prev = _read_json(os.path.join(out_dir, WALK_LATEST))
    prev_graph = _read_json(os.path.join(out_dir, GRAPH_LATEST))
    unchanged = (not force and state.get("fingerprint") == fp
                 and isinstance(prev, dict) and isinstance(prev_graph, dict))

    steps = []
    if unchanged:
        # INCREMENTAL. The code has not moved, so re-deriving the map would burn time
        # to produce the identical bytes. The map is reused and SAID to be reused --
        # a silent reuse is indistinguishable from a fresh answer, which is how stale
        # results get trusted.
        reused = dict(next(s for s in prev["steps"] if s["id"] == "graph"))
        reused["status"] = REUSED
        reused["headline"] = reused["headline"] + "  (unchanged since last look -- reused)"
        reused["seconds"] = 0.0
        steps.append(reused)
        snapshot = prev_graph
    else:
        graph_step = _guarded("graph", "Map the code", step_graph, root, mode, out_dir,
                              run_tests=run_tests, prev_snapshot=prev_graph)
        steps.append(graph_step)
        snapshot = _read_json(os.path.join(out_dir, GRAPH_LATEST)) or {}

    steps.append(_guarded("reconcile", "Re-check what the record claims",
                          step_reconcile, root, mode, force=force))
    steps.append(_guarded("core", "Check the parts that fail silently",
                          step_core, root, mode, snapshot))
    steps.append(_guarded("harvest", "Find what is nearly done",
                          step_harvest, root, mode, snapshot))
    prior = [f for s in steps for f in s.get("findings", [])]
    steps.append(_guarded("rank", "Decide what comes first",
                          step_rank, root, mode, snapshot, prior))

    # The stance is READ, never inferred and never defaulted to something plausible.
    # An explicit `stance=` argument is for callers that want to see the same facts
    # under another stance without changing what the project has said about itself.
    stored = read_stance(root, mode)
    effective = stance if stance is not None else stored["stance"]

    result = {
        "schema": "v5-walk-1",
        "walked_at": _now_iso(),
        "stance": effective if effective in STANCES else (
            DECLINED if effective == DECLINED else None),
        "stance_asked": stored["asked"],
        "root": root,
        "project": _project_name(root, mode),
        "fingerprint": fp,
        "incremental": bool(unchanged),
        "seconds": round(time.time() - started, 2),
        "steps": steps,
        "gaps": [s["id"] for s in steps if s["status"] == GAP],
        "saved_to": os.path.join(out_dir, NEXT_ACTIONS),
    }
    priorities = ozi_prioritise(result, effective)
    priorities["ask_stance"] = not stored["asked"]
    result["priorities_summary"] = {
        "total": len(priorities["ranked"]),
        "stance": priorities["stance"],
        "ranked_by": priorities["ranked_by"],
        "alarms": len(priorities["alarms"]),
        "needs_you": len(priorities["needs_you"]),
        "i_can_do": len(priorities["i_can_do"]),
    }

    # Lugs are filed BEFORE the record is written, so what is on disk says what
    # actually happened. Writing the record first left `lugs_emitted: null` beside
    # five lugs that had in fact been filed -- a record that disagrees with the tree.
    if apply:
        result["lugs_emitted"] = emit_needs_you_lugs(root, mode, priorities)

    _write_json(os.path.join(out_dir, WALK_LATEST), result)
    _write_json(os.path.join(out_dir, NEXT_ACTIONS), priorities)
    _write_json(os.path.join(out_dir, WALK_STATE),
                {"fingerprint": fp, "walked_at": result["walked_at"]})

    result["_priorities"] = priorities
    return result


def _project_name(root, mode=None):
    state = _read_json(os.path.join(base_dir(root, mode), "WAI-State.json"), {}) or {}
    wheel = state.get("wheel", {}) if isinstance(state.get("wheel"), dict) else {}
    return wheel.get("name") or os.path.basename(os.path.abspath(root))


# --------------------------------------------------------------------------------------
# Ruling 26 / Ruling 19: the operator's items become LUGS, not a report
# --------------------------------------------------------------------------------------

def emit_needs_you_lugs(root, mode, priorities, limit=5) -> list:
    """Top operator findings become `needs-you` lugs in the incoming queue.

    Ruling 19: a question for the operator lives in a lug, because a lug can be
    tracked, aged and resolved, while a line in a report can only be read. Ids are
    deterministic, so a second walk over unchanged state re-writes nothing.
    """
    base = base_dir(root, mode)
    incoming = os.path.join(base, "lugs", "incoming")
    written = []
    for f in priorities.get("needs_you", [])[:limit]:
        lug_id = f"needs-you-first-look-{f['id']}-v1"
        path = os.path.join(incoming, lug_id + ".json")
        if os.path.exists(path):
            continue
        payload = {
            "id": lug_id,
            "type": "needs-you",
            "status": "open",
            "title": f["plain"][:160],
            "created_at": _now_iso(),
            "origin": "first-look review of this project's code",
            "criticality": "CORE" if f["severity"] >= 5 else "STANDARD",
            "perceive": [f["plain"], f["why"]],
            "execute": ["Decide: act on this, schedule it, or record why it is fine."],
            "verify": ["The decision is recorded on this item and its status moves off open."],
            "acceptance_criteria": ["a recorded decision, not a silent close"],
            "evidence": f.get("evidence", {}),
        }
        if _write_json(path, payload):
            written.append(lug_id)
    return written


# --------------------------------------------------------------------------------------
# THE DELETION WAVE (Ruling 28 / 31.1) -- authorised, receipted, never automatic
# --------------------------------------------------------------------------------------

def wave(root, mode=None, authorise=False, apply=False) -> dict:
    """Action the DEPRECATE dispositions -- and ONLY under explicit authorisation.

    Three deliberate refusals, each of which has a name in the directive:
      - no authorisation, no action (Ruling 28: never auto-delete at any confidence)
      - no plan without a derived graph (a deletion list from nowhere is a guess)
      - no removal without a receipt naming the path, its size and its reason
    Passing --authorise alone still removes nothing: it prints the plan. Removal
    requires --authorise AND --apply, together, from a human.
    """
    out_dir = walk_dir(root, mode)
    snapshot = _read_json(os.path.join(out_dir, GRAPH_LATEST))
    if not isinstance(snapshot, dict):
        return {"status": "NO_GRAPH", "authorised": authorise, "removed": [],
                "reason": "no derived map on disk yet -- take a first look before removing anything"}

    dead = snapshot.get("dead_code", {}) or {}
    candidates = [c for c in (dead.get("candidates") or [])
                  if c.get("disposition") == "DEPRECATE"]
    plan = []
    for c in candidates:
        rel = c.get("path")
        full = os.path.join(root, rel) if rel else None
        if not rel or not full or not os.path.isfile(full):
            continue
        if rel.startswith(".git") or "/.git/" in rel:
            continue
        try:
            data = open(full, "rb").read()
        except OSError:
            continue
        plan.append({
            "path": rel,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "reason": c.get("disposition_reason") or c.get("evidence")
                      or "unreachable from every declared entry point and marked superseded",
            "safe_to_act": c.get("safe_to_act"),
        })

    if not authorise:
        return {"status": "PLAN_ONLY", "authorised": False, "planned": plan,
                "removed": [],
                "reason": "nothing is removed without explicit authorisation"}
    if not apply:
        return {"status": "AUTHORISED_DRY_RUN", "authorised": True, "planned": plan,
                "removed": [],
                "reason": "authorisation recorded; pass --apply to actually remove"}

    removed, failed = [], []
    for item in plan:
        full = os.path.join(root, item["path"])
        try:
            os.remove(full)
            removed.append(item)
        except OSError as exc:
            failed.append(dict(item, error=str(exc)))

    receipt = {
        "schema": "v5-deletion-wave-1",
        "wave_id": f"wave-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}",
        "authorised": True,
        "authorised_by": "operator (--authorise --apply)",
        "executed_at": _now_iso(),
        "root": os.path.abspath(root),
        "graph_from": snapshot.get("root"),
        "removed_count": len(removed),
        "removed": removed,
        "failed": failed,
        "note": "Every path above was unreachable from every declared entry point and "
                "carried a DEPRECATE disposition. Each is recorded with its exact size "
                "and content hash so the removal is reversible from version control and "
                "auditable without it.",
    }
    receipt_path = os.path.join(out_dir, WAVES_DIR, receipt["wave_id"] + ".json")
    _write_json(receipt_path, receipt)
    receipt["status"] = "APPLIED"
    receipt["receipt_path"] = receipt_path
    return receipt


# --------------------------------------------------------------------------------------
# Wiring report -- the answer to "does every mechanism have a caller"
# --------------------------------------------------------------------------------------

def wiring_report() -> dict:
    wired = {k: v for k, v in MECHANISM_WIRING.items() if v["wired"]}
    unwired = {k: v for k, v in MECHANISM_WIRING.items() if not v["wired"]}
    return {
        "total": len(MECHANISM_WIRING),
        "wired": len(wired),
        "deliberately_unwired": len(unwired),
        "mechanisms": MECHANISM_WIRING,
        "contract": "Every mechanism is either called by the walk, or recorded here as "
                    "deliberately unwired WITH a reason. There is no third category.",
    }


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--mode", default=None)
    sub = parser.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("walk", help="run the five-step first look")
    w.add_argument("--json", action="store_true")
    w.add_argument("--force", action="store_true", help="ignore the incremental cache")
    w.add_argument("--with-tests", action="store_true", help="execute the test suite too")
    w.add_argument("--apply", action="store_true",
                   help="also file the top operator items as work items")
    w.add_argument("--stance", default=None, choices=sorted(STANCES) + [DECLINED],
                   help="rank as if the project were this, without recording it")

    s = sub.add_parser("stance", help="what this project is for, and how it is ranked")
    s.add_argument("--set", dest="set_stance", default=None,
                   choices=sorted(STANCES), help="record the answer (asked once)")
    s.add_argument("--decline", action="store_true",
                   help="record that you would rather not say; ranking stays cost-and-risk")
    s.add_argument("--json", action="store_true")

    e = sub.add_parser("explain", help="re-render the last first look")
    e.add_argument("--json", action="store_true")

    v = sub.add_parser("wave", help="the authorised deletion wave")
    v.add_argument("--authorise", action="store_true")
    v.add_argument("--apply", action="store_true")

    g = sub.add_parser("wiring", help="which mechanisms are wired, and why")
    g.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "walk":
        result = walk(args.root, args.mode, run_tests=args.with_tests,
                      force=args.force, apply=args.apply, stance=args.stance)
        priorities = result.pop("_priorities")
        if args.json:
            print(json.dumps({"walk": result, "priorities": priorities},
                             indent=2, default=str))
        else:
            print(otto_explain(result, priorities))
        return 0

    if args.cmd == "stance":
        if args.set_stance or args.decline:
            rec = record_stance(args.root, args.mode,
                                None if args.decline else args.set_stance)
        else:
            rec = read_stance(args.root, args.mode)
        if args.json:
            print(json.dumps(rec, indent=2))
            return 0
        if not rec["asked"]:
            print(stance_question())
            return 0
        if rec["stance"] == DECLINED:
            print("You chose not to say what this project is for.")
            print("")
            print("\n".join(_wrap(COST_AND_RISK_NOTE, 78)))
        else:
            spec = STANCES[rec["stance"]]
            print(f"This project is {spec['label']}.")
            print("")
            print("\n".join(_wrap(spec["means"], 78)))
            print("")
            print("In that light I look at things in this order:")
            for i, t in enumerate(spec["order"], 1):
                print(f"  {i:>2}. {TOPIC_PLAIN.get(t, t)}")
        return 0

    if args.cmd == "explain":
        out_dir = walk_dir(args.root, args.mode)
        result = _read_json(os.path.join(out_dir, WALK_LATEST))
        priorities = _read_json(os.path.join(out_dir, NEXT_ACTIONS))
        if not result or not priorities:
            print("No first look has been taken here yet.")
            return 2
        print(json.dumps(priorities, indent=2) if args.json
              else otto_explain(result, priorities))
        return 0

    if args.cmd == "wave":
        report = wave(args.root, args.mode, authorise=args.authorise, apply=args.apply)
        print(json.dumps(report, indent=2, default=str))
        return 0

    report = wiring_report()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for name, info in sorted(report["mechanisms"].items()):
            mark = "WIRED   " if info["wired"] else "UNWIRED "
            print(f"{mark} {name:<24} {info['note'][:100]}")
        print(f"\n{report['wired']}/{report['total']} wired, "
              f"{report['deliberately_unwired']} deliberately unwired with a reason")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
