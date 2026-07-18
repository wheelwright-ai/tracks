#!/usr/bin/env python3
"""
tastegraph_vector.py — the TasteGraph vector middleman.

WHY THIS EXISTS
---------------
Session 137 measured TasteGraph's actual behavioural effect and found it near
non-binding: preferences that appear ONLY in TasteGraph (not also in CLAUDE.md
or agent memory) had close to zero compliance. Three structural causes:

  1. ONCE-ONLY INJECTION. The whole graph is rendered at SessionStart and never
     again, while CLAUDE.md sits permanently in the system prompt. A preference
     that matters at turn 40 was delivered at turn 0 and has long since scrolled
     out of relevance.
  2. TRUNCATION. Preference bodies were cut mid-sentence with an ellipsis, so
     the agent acted on fragments that LOOKED complete.
  3. CAPPING. 33 preferences were dropped entirely to hold a line budget —
     silently, including the trust and alignment categories.

The operator's fix (s137 t4-t5, ratified at 92%): stop shipping the whole graph
at session start, and instead select a SMALL relevant slice at each firing
moment, sharded by ACTIVITY VECTOR rather than by topic. Topic categories
("work_style", "communication") require judgment to match against a task.
Activity vectors are knowable at dispatch time and match deterministically.

  A turn is not one action. Selection must fire per-activity, not per-turn.

WHAT THIS IS NOT
----------------
Not an LLM selector. Selection is deterministic tag matching, on purpose: an
LLM selector introduces a NEW way to lose a preference silently, which is the
exact failure being fixed. Model judgment is reserved for the caller.

Not a formatter. Its job is to make work LAND — see the `closure` vector, which
carries open threads and their landing conditions, not just phrasing rules.

DESIGN RULES (all load-bearing, do not "simplify" them away)
------------------------------------------------------------
  * NEVER TRUNCATE a preference body. If the budget is tight, drop whole
    preferences and log them. A fragment that looks complete is worse than a
    visible absence.
  * ALWAYS LOG DROPS, not just selections. A selector that silently discards is
    indistinguishable from one that has nothing to say — that ambiguity is what
    hid TasteGraph's ineffectiveness for months.
  * FIRE UNCONDITIONALLY. Anything that depends on the agent REMEMBERING to
    invoke it reproduces the failure it fixes. Hook-driven vectors must be
    wired into the ceremony, never left to agent discretion.

Usage:
    tastegraph_vector.py select --vector presentation [--context "..."]
    tastegraph_vector.py select --vector closure --format prompt
    tastegraph_vector.py vectors
    tastegraph_vector.py audit [--session session-YYYYMMDD-HHMM]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

VECTOR_SPEC_VERSION = "1.0.0"

# ── The six activity vectors ────────────────────────────────────────────────
#
# Five came from the operator (s137 t5); Closure was added because those
# preferences fire at one unmistakable moment yet are currently scattered
# across three topic categories, which is part of why they get missed.
#
# `categories` matches a preference's `category` field exactly.
# `id_contains` matches substrings in a preference `id` — this is what lets a
# preference belong to more than one vector, which is deliberate: forcing a
# strict taxonomy would lose preferences at the boundaries.

VECTORS = {
    "awareness": {
        "when": "Orienting: session start, resuming, picking up a thread, "
                "surveying state. Fires BEFORE deciding what to work on.",
        "categories": ["engagement", "temporal", "environment", "meta"],
        "id_contains": ["inbox", "recap", "orient", "wakeup", "resume",
                        "what-to-work-on", "working-queue", "entry-point"],
    },
    "research": {
        "when": "Investigating: reading code, tracing a bug, gathering evidence "
                "before forming a conclusion.",
        "categories": ["approach", "audience"],
        "id_contains": ["verif", "source", "registry", "evidence", "measure",
                        "falsif", "advisor-framing", "research"],
    },
    "decision": {
        "when": "Choosing: weighing options, prioritising, judging risk, "
                "deciding whether to act alone or ask.",
        "categories": ["risk_tolerance", "alignment", "alignment_gates",
                       "prioritization", "trust", "cost_sensitivity"],
        "id_contains": ["autonomous", "initiative", "scope", "approval",
                        "revenue", "priorit", "gate", "ask", "recommend"],
    },
    "execution": {
        "when": "Doing: editing code, running tools, creating lugs, "
                "committing. Fires DURING the work.",
        "categories": ["work_style", "workflow"],
        "id_contains": ["lug", "edit", "implement", "quality-bar", "git",
                        "verification", "commit", "test"],
    },
    "presentation": {
        "when": "Composing output for the operator. Fires while writing the "
                "reply, NOT at turn start — this is where adherence failed "
                "most often in s137.",
        "categories": ["communication", "output_format", "aesthetic",
                       "accessibility"],
        "id_contains": ["format", "emoji", "bars", "colou", "color", "render",
                        "altitude", "brief", "density", "voice"],
    },
    "closure": {
        "when": "Ending: savepoint, closeout, handoff, or any moment work must "
                "LAND rather than be described. Carries open threads and their "
                "landing conditions, not just phrasing rules.",
        "categories": ["notification_preferences"],
        "id_contains": ["closeout", "savepoint", "exit", "handoff", "closing",
                        "definitive", "next-step", "causal-chain", "restatement",
                        "persistence", "land"],
    },
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def find_spoke_root(start=None):
    """Walk up looking for a WAI-Harness/ marker (v4), or the legacy v3 one."""
    cur = os.path.abspath(start or os.getcwd())
    while True:
        for marker in ("WAI-Harness", "WAI-Spoke"):
            if os.path.isdir(os.path.join(cur, marker)):
                return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def resolve_hub_path(spoke_root, local):
    """
    Resolve the hub from WAI-State's wheel.hub_path — the SAME contract
    generate_wakeup_brief.py uses.

    FLEET-FATAL BUG FIXED (s138, caught by Fable review): this used to hardcode
    <spoke_root>/WAI-Harness/hub/local/, a directory that exists on exactly ONE
    of the 16 active spokes (mywheel, which IS the hub). On every other spoke
    the graph would never load, the tool would exit 3 every turn, and the hook
    would print its DEGRADED banner forever. Loud-by-design is still broken.
    """
    try:
        with open(os.path.join(local, "WAI-State.json")) as fh:
            hub = json.load(fh).get("wheel", {}).get("hub_path")
        if hub:
            return os.path.expanduser(hub)
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    # Fallback: the in-repo hub, correct only when this spoke IS the hub.
    return os.path.join(spoke_root, "WAI-Harness", "hub")


def paths(spoke_root):
    harness = os.path.join(spoke_root, "WAI-Harness")
    local = os.path.join(harness, "spoke", "local")
    return {
        # Graph is hub-owned (fleet taste). Local override is read first so a
        # spoke can carry spoke-specific taste without forking the hub file.
        "org_graph": os.path.join(
            resolve_hub_path(spoke_root, local), "local", "tastegraph-org.json"),
        "local_graph": os.path.join(local, "tastegraph.json"),
        "digest": os.path.join(local, "resident", "digest.json"),
        "vector_log": os.path.join(local, "runtime", "tastegraph-vector-calls.jsonl"),
    }


def _collect_prefs(obj, acc):
    """Preferences are nested; find every object carrying id + category."""
    if isinstance(obj, dict):
        if "id" in obj and "category" in obj:
            acc.append(obj)
        for v in obj.values():
            _collect_prefs(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _collect_prefs(v, acc)
    return acc


def load_prefs(p):
    """Load preferences from local graph then hub graph. Local wins on id."""
    prefs, seen, sources = [], set(), []
    for key in ("local_graph", "org_graph"):
        path = p[key]
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as e:
            print(f"[vector] WARN: could not read {path}: {e}", file=sys.stderr)
            continue
        sources.append(path)
        for pref in _collect_prefs(data, []):
            pid = pref.get("id")
            if pid and pid not in seen:
                seen.add(pid)
                prefs.append(pref)
    return prefs, sources


def is_verified(pref):
    """
    The graph's cardinal rule: inferred/observed preferences are NOT applied
    without operator confirmation. Only stated/verified ones bind.
    """
    v = (pref.get("verification") or pref.get("confidence") or "").lower()
    if v in ("inferred", "observed", "guess", "low"):
        return False
    return True


def is_deferred(pref, now=None):
    """True while a DEFER verdict from tastegraph_accounting.py is still active.

    An unparseable defer_until is treated as NOT deferred: a malformed date must
    never silently suppress a preference from delivery. Fail toward delivering.
    """
    raw = pref.get("defer_until")
    if not raw or not isinstance(raw, str):
        return False
    try:
        until = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    return until > (now or datetime.now(timezone.utc))


def match_vector(pref, vector):
    """Deterministic. Returns (matched, reason)."""
    spec = VECTORS[vector]
    cat = (pref.get("category") or "").lower()
    if cat in spec["categories"]:
        return True, f"category:{cat}"
    pid = (pref.get("id") or "").lower()
    for frag in spec["id_contains"]:
        if frag in pid:
            return True, f"id_contains:{frag}"
    return False, None


def select(prefs, vector):
    """
    Returns (selected, dropped). Every preference lands in exactly one list —
    the two together always account for the whole graph, which is what makes
    the drop log auditable.
    """
    selected, dropped = [], []
    now = datetime.now(timezone.utc)
    for pref in prefs:
        if not is_verified(pref):
            dropped.append({"id": pref.get("id"), "reason": "unverified"})
            continue
        if is_deferred(pref, now):
            # Suppressed by tastegraph_accounting.py's DEFER verdict. Dropped
            # (not silently omitted) so the suppression stays auditable in the
            # drop log alongside every other exclusion.
            dropped.append({"id": pref.get("id"), "reason": "deferred",
                            "until": pref.get("defer_until")})
            continue
        matched, why = match_vector(pref, vector)
        if matched:
            selected.append({**pref, "_matched_by": why})
        else:
            dropped.append({"id": pref.get("id"), "reason": "vector_mismatch"})
    return selected, dropped


def load_open_threads(p):
    """
    Closure vector carries the Resident's open threads — the LANDING half.

    Returns (threads, degraded_reason). A quiet empty list would be the exact
    failure this tool exists to prevent: a closure vector with no threads looks
    identical to a clean desk, so a broken digest would read as "nothing left
    to land". Callers MUST surface degraded_reason.
    """
    path = p["digest"]
    if not os.path.isfile(path):
        return [], f"resident digest not found at {path} — open threads UNKNOWN, not zero"
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        return [], f"resident digest unreadable ({e}) — open threads UNKNOWN, not zero"
    if "open_threads" not in data:
        return [], "resident digest has no open_threads key (schema drift?) — UNKNOWN, not zero"
    return data.get("open_threads") or [], None


def log_call(p, record):
    """Append-only telemetry. Selections AND drops, so it is farmable later."""
    path = p["vector_log"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def render_prompt(vector, selected, threads, degraded=None):
    """Human/agent-readable. NEVER truncates a preference body."""
    out = [f"TASTEGRAPH — {vector.upper()} vector ({len(selected)} preference(s) in force)",
           f"  fires when: {VECTORS[vector]['when']}", ""]
    if not selected:
        out.append("  (no preferences match this vector)")
    for pref in selected:
        out.append(f"- {pref.get('id')} [{pref.get('key') or pref.get('category')}]")
        # Full body, never elided. Wrapping is the reader's problem; a
        # mid-sentence cut is the agent's problem, and that is the worse one.
        for line in str(pref.get("value", "")).splitlines() or [""]:
            out.append(f"    {line}")
    if vector == "closure" and degraded:
        out += ["", f"CLOSURE DEGRADED: {degraded}",
                "Do NOT read this as a clear desk. Establish open threads another way."]
    if vector == "closure" and threads:
        out += ["", f"OPEN THREADS ({len(threads)}) — each needs a landing "
                    "condition CHECKED, then executed or routed.",
                "An open thread without its landing condition is chatter."]
        for t in threads:
            txt = t if isinstance(t, str) else (t.get("text") or t.get("thread") or str(t))
            out.append(f"  - {txt}")
    return "\n".join(out)


def cmd_select(args, spoke_root, p):
    vector = args.vector.lower()
    if vector not in VECTORS:
        print(f"[vector] unknown vector '{vector}'. Known: {', '.join(VECTORS)}",
              file=sys.stderr)
        return 2

    prefs, sources = load_prefs(p)
    if not prefs:
        # Loud on absent. Silence is how TasteGraph's ineffectiveness hid for
        # months; an empty graph must never look like an empty result.
        print("[vector] ERROR: no preferences loaded — graph missing or "
              f"unreadable. Looked in: {p['local_graph']}, {p['org_graph']}",
              file=sys.stderr)
        return 3

    selected, dropped = select(prefs, vector)
    threads, degraded = load_open_threads(p) if vector == "closure" else ([], None)

    if not args.no_log:
        log_call(p, {
            "ts": _now(),
            "spec_version": VECTOR_SPEC_VERSION,
            "vector": vector,
            "session": args.session,
            "turn": args.turn,
            "context": args.context,
            "total_prefs": len(prefs),
            "selected_count": len(selected),
            "dropped_count": len(dropped),
            "selected_ids": [s.get("id") for s in selected],
            "dropped": dropped,
            "open_threads": len(threads),
            "closure_degraded": degraded,
            "sources": sources,
        })

    if args.format == "json":
        print(json.dumps({
            "vector": vector,
            "spec_version": VECTOR_SPEC_VERSION,
            "selected": selected,
            "dropped": dropped,
            "open_threads": threads,
            "closure_degraded": degraded,
        }, indent=2, ensure_ascii=False))
    else:
        print(render_prompt(vector, selected, threads, degraded))
    return 0


def cmd_vectors(args, spoke_root, p):
    prefs, _ = load_prefs(p)
    print(f"TASTEGRAPH VECTORS (spec {VECTOR_SPEC_VERSION}) — "
          f"{len(prefs)} preference(s) in graph\n")
    covered = set()
    for name, spec in VECTORS.items():
        sel, _drop = select(prefs, name)
        covered |= {s.get("id") for s in sel}
        print(f"  {name:<13} {len(sel):>3} pref(s)   {spec['when'][:60]}")
    # Coverage check: a preference matching NO vector can never fire. That is
    # the silent-loss failure this tool exists to prevent, so surface it.
    orphans = [pr.get("id") for pr in prefs
               if is_verified(pr) and pr.get("id") not in covered]
    print(f"\n  verified preferences reachable by >=1 vector: "
          f"{len(covered)}/{len([x for x in prefs if is_verified(x)])}")
    if orphans:
        print(f"  ORPHANED (match no vector, can never fire): {len(orphans)}")
        for o in orphans:
            print(f"    - {o}")
    return 0


def cmd_audit(args, spoke_root, p):
    path = p["vector_log"]
    if not os.path.isfile(path):
        print(f"[vector] no telemetry yet at {path}")
        return 0
    rows = []
    with open(path) as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if args.session:
        rows = [r for r in rows if r.get("session") == args.session]
    print(f"VECTOR CALLS: {len(rows)}")
    by_vec = {}
    for r in rows:
        by_vec.setdefault(r.get("vector"), []).append(r)
    for vec, rs in sorted(by_vec.items()):
        sel = sum(r.get("selected_count", 0) for r in rs)
        drop = sum(r.get("dropped_count", 0) for r in rs)
        print(f"  {vec:<13} calls={len(rs):<4} selected={sel:<5} dropped={drop}")
    never = [v for v in VECTORS if v not in by_vec]
    if never:
        # A vector that never fires is indistinguishable from one with nothing
        # to say. Naming them is the whole point of the audit.
        print(f"\n  NEVER FIRED: {', '.join(never)}")
        print("  A vector that never fires is not wired in. Check the ceremony.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="TasteGraph vector middleman")
    ap.add_argument("--spoke-path", help="spoke root (auto-detected if omitted)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("select", help="select the preferences for one vector")
    s.add_argument("--vector", required=True, help=", ".join(VECTORS))
    s.add_argument("--context", default=None, help="what is happening (logged)")
    s.add_argument("--session", default=os.environ.get("WAI_SESSION"))
    s.add_argument("--turn", type=int, default=None)
    s.add_argument("--format", choices=["prompt", "json"], default="prompt")
    s.add_argument("--no-log", action="store_true", help="skip telemetry")

    sub.add_parser("vectors", help="list vectors + coverage, flag orphans")

    a = sub.add_parser("audit", help="summarise vector telemetry")
    a.add_argument("--session", default=None)

    args = ap.parse_args(argv)
    spoke_root = find_spoke_root(args.spoke_path)
    p = paths(spoke_root)

    return {"select": cmd_select, "vectors": cmd_vectors,
            "audit": cmd_audit}[args.cmd](args, spoke_root, p)


if __name__ == "__main__":
    sys.exit(main())
