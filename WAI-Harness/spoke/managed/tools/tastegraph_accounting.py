#!/usr/bin/env python3
"""TasteGraph learning accounting — the third leg of the preference lifecycle.

tastegraph_harvest_check.py gates INTAKE. tastegraph_grade.py measures ADHERENCE
for one version. Neither ever revisits a preference once it has landed, so the
graph could only ever grow. This tool closes that: every preference periodically
comes up for review and receives exactly one of four verdicts —

    ADOPT      correct and now evidenced      -> stamp last_verified, may raise confidence
    ADAPT      intent right, wording drifted  -> rewrite value in place, keep prior_value
    REINFORCE  correct but NOT being followed -> keep as-is, raise priority, count the miss
    DEFER      cannot be judged right now     -> dated suppression, reversible

"retire" is deliberately absent. Age alone is never a retire verdict (standing
operator doctrine); DEFER carries that load reversibly and with a date.

WHY THIS EXISTS AT ALL: tastegraph-org.json has carried a written
verification_policy ("re-verify every 30 sessions or on explicit contradiction")
since it was created, and nothing ever implemented it. 43 of 110 preferences
have never been re-checked since the day they were written.

CADENCE IS DATE-BASED, NEVER SESSION-COUNT-BASED. The written policy says "every
30 sessions", but WAI-State.json session_count reads 1 while the spoke is
demonstrably on session 138 — the counter is broken. A cadence keyed to it would
look correct in review, pass its tests, and never fire once. That is the exact
failure class this tool exists to end, so it must not reproduce it. See
test_cadence_ignores_broken_session_count.

Usage:
    tastegraph_accounting.py due  [--json]      read-only; exit 1 if any due
    tastegraph_accounting.py run  [--apply]     conduct the accounting
    tastegraph_accounting.py ledger [--limit N] read back the history

`run` without --apply is a dry run: it computes and prints verdicts but writes
nothing. Nothing mutates the graph unless --apply is passed.
"""

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from tastegraph_vector import (  # noqa: E402
        find_spoke_root, resolve_hub_path, _collect_prefs,
    )
except ImportError:  # pragma: no cover - vector tool is a hard sibling dependency
    print("[accounting] FATAL: tastegraph_vector.py not importable "
          "(expected as a sibling in managed/tools/)", file=sys.stderr)
    raise

VERDICTS = ("adopt", "adapt", "reinforce", "defer")

# TIER VOCABULARY SPLIT (found by adversarial cold-read audit, s138):
# verification_policy uses tiers  stated / observed / inferred / CONFIRMED
# the preference data uses tiers  stated / observed / inferred / VERIFIED
# "confirmed" and "verified" are the same concept under two names, and neither
# file knows about the other's spelling. Normalising here rather than editing
# either file keeps both readable and stops a lookup silently missing.
TIER_ALIASES = {"confirmed": "verified"}

# Days between reviews, by (normalised) confidence tier. These are the FALLBACK.
# The graph's own verification_policy is the intended source of truth, but today
# it expresses cadence as prose in SESSION units ("re-verify every 30 sessions"),
# which is both unparseable and denominated in a counter that is broken. Until a
# migration writes interval_days into the policy, these values are what actually
# governs. `policy audit` reports exactly this state so it cannot hide.
DEFAULT_INTERVALS = {
    "verified": 180,
    "stated": 90,
    "observed": 60,
    "inferred": 30,
}

# Refactor trigger thresholds. These convert "at some point a refactor might be
# needed" from an intention into a condition that actually fires.
REFACTOR_REINFORCE_RATIO = 0.30   # correct but ignored => delivery is broken
REFACTOR_ADAPT_RATIO = 0.30       # per-category; our model of the operator is wrong
REFACTOR_MIN_CATEGORY_N = 3       # below this a category cannot trip (noise floor)
REFACTOR_COMPLIANCE_FLOOR = 0.60  # only evaluable once the compliance oracle exists


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat()


def paths(spoke_root):
    harness = os.path.join(spoke_root, "WAI-Harness")
    local = os.path.join(harness, "spoke", "local")
    hub_local = os.path.join(resolve_hub_path(spoke_root, local), "local")
    return {
        "org_graph": os.path.join(hub_local, "tastegraph-org.json"),
        "local_graph": os.path.join(local, "tastegraph.json"),
        "ledger": os.path.join(hub_local, "tastegraph-accounting.jsonl"),
        "compliance": os.path.join(
            harness, "spoke", "managed", "tools", "tastegraph_compliance.py"),
        # The lock MUST live beside the graph it guards, not in spoke-local
        # runtime. The graph is hub-owned and shared by every spoke in the
        # fleet; a spoke-local lock would have each spoke serialising against
        # its OWN file while concurrently writing the SAME hub graph — which is
        # not a lock at all. (Caught in review before first run.)
        "lock": os.path.join(hub_local, ".tastegraph-accounting.lock"),
        "signal_dir": os.path.join(local, "lugs", "bytype", "signal", "open"),
    }


def parse_ts(value):
    """Parse an ISO-ish timestamp; return None if absent or unparseable.

    Unparseable is deliberately treated the same as absent — DUE — rather than
    swallowed as 'recently checked'. A malformed date must never buy a
    preference an exemption from review.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def tier_of(pref):
    """Normalised confidence tier, resolving the confirmed/verified split."""
    raw = (pref.get("confidence") or pref.get("verification") or "stated").lower()
    return TIER_ALIASES.get(raw, raw)


def intervals_from_policy(graph):
    """Read review intervals from the graph's own verification_policy.

    Returns (intervals, policy_state) where policy_state is one of:
      "machine-readable"  the policy supplied at least one interval_days
      "prose-only"        the policy exists but specifies no parseable interval
      "absent"            no verification_policy at all

    Today every real graph returns "prose-only": the policy names all four tiers
    but expresses cadence as "re-verify every 30 sessions", which is unparseable
    AND denominated in the broken session counter. So DEFAULT_INTERVALS governs.
    That is a defensible fallback but it must never be mistaken for the policy
    being honoured — cmd_policy reports the distinction explicitly.
    """
    out = dict(DEFAULT_INTERVALS)
    policy = graph.get("verification_policy")
    if not isinstance(policy, dict):
        return out, "absent"

    found = False
    for tier, spec in policy.items():
        if not isinstance(spec, dict):
            continue
        days = spec.get("interval_days")
        if isinstance(days, int) and days > 0:
            out[TIER_ALIASES.get(tier.lower(), tier.lower())] = days
            found = True
    return out, ("machine-readable" if found else "prose-only")


def contradiction_ids(graph):
    """Preference ids with a recorded contradiction — always immediately due.

    DATA MODEL (defined here because nothing else defines it — the policy prose
    says "or on explicit contradiction" but no contradiction store has ever
    existed). Two shapes are accepted so a future writer can use either:

      graph["contradictions"] = [{"pref_id": "...", "ts": "...", "note": "..."}]
      pref["contradicted_by"]  = "session-... turn-N" (any truthy value)

    Both are absent from every graph today, so this returns an empty set and
    contradiction-triggered review is inert until something writes one.
    """
    out = set()
    for rec in graph.get("contradictions") or []:
        if isinstance(rec, dict) and rec.get("pref_id"):
            out.add(rec["pref_id"])
    for pref in _collect_prefs(graph, []):
        if pref.get("contradicted_by") and pref.get("id"):
            out.add(pref["id"])
    return out


def is_due(pref, intervals, contradicted, now):
    """Return (due: bool, reason: str). Date-based only."""
    pid = pref.get("id")
    if pid in contradicted:
        return True, "contradiction recorded"

    # Review scheduling reads defer_until_review; delivery suppression reads
    # defer_until. A "cannot judge yet" defer reschedules the review WITHOUT
    # silencing the preference.
    for key in ("defer_until_review", "defer_until"):
        until = parse_ts(pref.get(key))
        if until and until > now:
            return False, f"review deferred until {pref[key]}"

    last = parse_ts(pref.get("last_verified"))
    if last is None:
        # Null/unparseable means never re-checked since creation -> due now.
        return True, "never verified"

    tier = tier_of(pref)
    interval = intervals.get(tier, DEFAULT_INTERVALS["stated"])
    age_days = (now - last).days
    if age_days >= interval:
        return True, f"{age_days}d since review (tier {tier}, interval {interval}d)"
    return False, f"reviewed {age_days}d ago (interval {interval}d)"


def compliance_available(p):
    """The oracle is optional. Its absence must be reported, never papered over."""
    return os.path.isfile(p["compliance"])


def evidence_quality(p):
    return "measured" if compliance_available(p) else "no-compliance-signal"


def build_bundle(pref, reason, p):
    """The evidence a reviewing agent needs to judge ONE preference.

    WHO ASSIGNS THE VERDICT: an agent, not this tool. Python cannot judge whether
    a stated operator preference still reflects intent — that is the reasoning
    the model_fit calls for. So this tool follows the sibling convention set by
    tastegraph_grade.py (which ingests agent-prepared --scores): `bundle` emits
    the evidence, an agent judges, `run --verdicts` validates and writes back.

    That split is what makes the tool deterministic and unit-testable while
    keeping the judgement where judgement belongs.
    """
    return {
        "pref_id": pref.get("id"),
        "category": pref.get("category"),
        "key": pref.get("key"),
        "value": pref.get("value"),
        "confidence": tier_of(pref),
        "source": pref.get("source"),
        "created_at": pref.get("created_at"),
        "last_verified": pref.get("last_verified"),
        "reinforce_count": pref.get("reinforce_count") or 0,
        "due_reason": reason,
        "evidence_quality": evidence_quality(p),
        "constraints": {
            "allowed_verdicts": list(VERDICTS),
            "may_auto_adopt": tier_of(pref) != "inferred",
            "note": ("inferred preferences require operator confirmation before "
                     "adoption (graph cardinal rule); age alone is never grounds "
                     "to retire — DEFER is the parking verdict"),
        },
    }


def baseline_verdict(pref, reason, p, compliance=None):
    """The mechanical fallback when no agent verdicts are supplied.

    With a per-preference compliance verdict from tastegraph_compliance.py this
    becomes a genuine discrimination rather than a shrug:

        compliant     -> ADOPT      correct AND demonstrably followed
        violated      -> REINFORCE  correct but NOT followed; count the miss
        unmeasurable  -> DEFER      no deterministic detector; cannot judge

    Without that signal, age alone cannot tell ADOPT from REINFORCE — a
    preference untouched for 200 days looks identical whether it is being
    obeyed perfectly or ignored completely. So it defers and says why.

    ADAPT is never auto-proposed: rewriting the operator's own words is not a
    date comparison's call, and never a detector's either.
    """
    if tier_of(pref) == "inferred":
        return "defer", ("inferred preferences require operator confirmation "
                         "before adoption (graph cardinal rule)")
    if not compliance_available(p):
        return "defer", ("no compliance signal available "
                         "(tastegraph_compliance.py absent) — cannot distinguish "
                         "adopt from reinforce on age alone")

    verdict = (compliance or {}).get("verdict")
    if verdict == "compliant":
        return "adopt", "measured compliant in the sampled session(s)"
    if verdict == "violated":
        n = (compliance or {}).get("violation_count", 0)
        return "reinforce", (f"measured VIOLATED ({n} occurrence(s)) — the "
                             f"preference is right but is not being followed")
    return "defer", ("no deterministic detector for this preference — "
                     "unmeasurable, not assumed passing")


def load_verdicts(path):
    """Load and validate an agent-prepared verdict file.

    Shape: {"<pref_id>": {"verdict": "adopt|adapt|reinforce|defer",
                          "reason": "...", "new_value": <required for adapt>}}
    Raises ValueError on any unknown verdict — an out-of-set verdict must fail
    loudly, never be silently coerced into the nearest legal one.
    """
    with open(path) as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("verdict file must be an object keyed by pref_id")
    for pid, spec in data.items():
        if not isinstance(spec, dict):
            raise ValueError(f"{pid}: verdict entry must be an object")
        v = spec.get("verdict")
        if v not in VERDICTS:
            raise ValueError(f"{pid}: verdict {v!r} not in {VERDICTS}")
        if v == "adapt" and spec.get("new_value") is None:
            raise ValueError(f"{pid}: adapt requires new_value")
        if v == "adopt" and spec.get("_tier") == "inferred":
            raise ValueError(f"{pid}: inferred preferences may not be auto-adopted")
    return data


def apply_verdict(pref, verdict, now, note=None, defer_days=90, new_value=None,
                  defer_scope="review"):
    """Mutate a preference dict in place per its verdict. Returns a change record."""
    if verdict not in VERDICTS:
        raise ValueError(f"unknown verdict {verdict!r}; must be one of {VERDICTS}")

    prior_conf = pref.get("confidence")
    prior_value = pref.get("value")
    change = {"prior_confidence": prior_conf, "new_confidence": prior_conf,
              "prior_value": None}

    if verdict == "adopt":
        pref["last_verified"] = _iso(now)
        if tier_of(pref) == "stated":
            pref["confidence"] = "verified"
            change["new_confidence"] = "verified"

    elif verdict == "adapt":
        if new_value is None:
            raise ValueError("adapt requires new_value")
        change["prior_value"] = prior_value
        pref["value"] = new_value
        pref["last_verified"] = _iso(now)

    elif verdict == "reinforce":
        pref["last_verified"] = _iso(now)
        pref["reinforce_count"] = int(pref.get("reinforce_count") or 0) + 1

    elif verdict == "defer":
        # TWO KINDS OF DEFER, and conflating them is dangerous.
        #
        #   scope="review"    "I cannot judge this yet." The preference is still
        #                     in force and MUST keep being delivered. Only the
        #                     next review is rescheduled.
        #   scope="delivery"  "This is questionable — park it." Suppressed from
        #                     delivery vectors until the date.
        #
        # The mechanical baseline always defers for REVIEW. Without this split,
        # a single baseline run over the 43 never-verified preferences would
        # stamp delivery-suppression on all of them and silently gut the
        # operator's entire TasteGraph for 90 days. Only an explicit agent
        # verdict may choose "delivery".
        pref["defer_until_review"] = _iso(now + timedelta(days=defer_days))
        if defer_scope == "delivery":
            pref["defer_until"] = _iso(now + timedelta(days=defer_days))
        change["defer_scope"] = defer_scope

    if note:
        pref["accounting_note"] = note
    return change


def append_ledger(p, entries):
    """Append-only. The graph holds current state; only history shows trajectory."""
    path = p["ledger"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def write_graph(p, graph_path, graph):
    """Atomic, lock-guarded write. Never leave a partially-updated graph."""
    os.makedirs(os.path.dirname(p["lock"]), exist_ok=True)
    lock_f = open(p["lock"], "a+")
    try:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        tmp = graph_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(graph, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, graph_path)
    finally:
        fcntl.flock(lock_f, fcntl.LOCK_UN)
        lock_f.close()


def check_refactor_trigger(entries, compliance_score=None):
    """Evaluate approach-level drift across the whole run.

    Returns a list of tripped conditions. Individual preference verdicts answer
    'is this learning still right'; this answers 'is our whole approach still
    right', which no per-preference verdict can see.
    """
    tripped = []
    total = len(entries)
    if total:
        reinforce = sum(1 for e in entries if e["verdict"] == "reinforce")
        if reinforce / total >= REFACTOR_REINFORCE_RATIO:
            tripped.append({
                "condition": "reinforce_ratio",
                "value": round(reinforce / total, 3),
                "threshold": REFACTOR_REINFORCE_RATIO,
                "meaning": ("preferences are correct but systematically ignored — "
                            "the DELIVERY mechanism is the problem, not the wording"),
            })

        by_cat = {}
        for e in entries:
            cat = e.get("category") or "uncategorised"
            by_cat.setdefault(cat, []).append(e["verdict"])
        for cat, verdicts in by_cat.items():
            adapt = sum(1 for v in verdicts if v == "adapt")
            # MIN_N floor: without it a category with one due preference trips
            # at 100% on a single ADAPT — a guaranteed false positive.
            if len(verdicts) >= REFACTOR_MIN_CATEGORY_N and \
                    adapt / len(verdicts) >= REFACTOR_ADAPT_RATIO:
                tripped.append({
                    "condition": "adapt_ratio_in_category",
                    "category": cat,
                    "value": round(adapt / len(verdicts), 3),
                    "threshold": REFACTOR_ADAPT_RATIO,
                    "meaning": f"our model of the operator in '{cat}' is wrong",
                })

    if compliance_score is not None and compliance_score < REFACTOR_COMPLIANCE_FLOOR:
        tripped.append({
            "condition": "compliance_floor",
            "value": compliance_score,
            "threshold": REFACTOR_COMPLIANCE_FLOOR,
            "meaning": "measured adherence is below the floor across the graph",
        })
    return tripped


def write_refactor_signal(p, tripped, run_id, now):
    """Propose an approach-level refactor. Never attempt one automatically."""
    os.makedirs(p["signal_dir"], exist_ok=True)
    sig_id = f"signal-tastegraph-refactor-{now.strftime('%Y%m%d-%H%M%S')}-v1"
    path = os.path.join(p["signal_dir"], f"{sig_id}.json")
    conditions = ", ".join(t["condition"] for t in tripped)
    lug = {
        "id": sig_id,
        "type": "signal",
        "status": "open",
        "routed_to": "LOCAL",
        "source_spoke": "mywheel",
        "title": f"TasteGraph refactor trigger fired: {conditions}",
        "created_at": _iso(now),
        "impact": 8,
        "effort": "M",
        "summary": ("The learning accounting detected approach-level drift. "
                    "Individual preference edits will not fix this — the "
                    "approach itself needs review."),
        "perceive": [
            "Accounting run %s tripped %d refactor condition(s): %s"
            % (run_id, len(tripped), json.dumps(tripped, ensure_ascii=False))
        ],
        "execute": ["Review the tripped conditions and decide whether to refactor "
                    "the approach, adjust the thresholds, or accept the drift."],
        "verify": ["An operator ruling is recorded on this signal."],
        "tripped": tripped,
        "run_id": run_id,
        "notes": "Auto-written by tastegraph_accounting.py. Proposal only.",
    }
    with open(path, "w") as fh:
        json.dump(lug, fh, indent=2, ensure_ascii=False)
    return path


def load_graph(path):
    with open(path) as fh:
        return json.load(fh)


def collect_due(graph, p, now):
    intervals, _policy_state = intervals_from_policy(graph)
    contradicted = contradiction_ids(graph)
    due = []
    for pref in _collect_prefs(graph, []):
        ok, reason = is_due(pref, intervals, contradicted, now)
        if ok:
            due.append((pref, reason))
    return due


# ---- commands ---------------------------------------------------------------

def cmd_due(args, p):
    if not os.path.isfile(p["org_graph"]):
        print(f"[accounting] no graph at {p['org_graph']}", file=sys.stderr)
        return 0
    graph = load_graph(p["org_graph"])
    now = _now()
    due = collect_due(graph, p, now)
    total = len(_collect_prefs(graph, []))

    if args.json:
        print(json.dumps({
            "due": len(due), "total": total,
            "evidence_quality": evidence_quality(p),
            "items": [{"id": pref.get("id"), "reason": r} for pref, r in due],
        }, indent=2, ensure_ascii=False))
    elif due:
        print(f"TasteGraph accounting: {len(due)} of {total} preference(s) due")
        for pref, reason in due[:10]:
            print(f"  - {pref.get('id')}: {reason}")
        if len(due) > 10:
            print(f"  ... and {len(due) - 10} more")
        if not compliance_available(p):
            print("  NOTE: no compliance oracle — verdicts will be evidence-light")
    else:
        print(f"TasteGraph accounting: clear (0 of {total} due)")

    return 1 if due else 0


def cmd_run(args, p):
    if not os.path.isfile(p["org_graph"]):
        print(f"[accounting] no graph at {p['org_graph']}", file=sys.stderr)
        return 2
    graph = load_graph(p["org_graph"])
    now = _now()
    run_id = f"acct-{now.strftime('%Y%m%d-%H%M%S')}"
    due = collect_due(graph, p, now)
    if args.limit:
        due = due[:args.limit]

    # Optional measured compliance, keyed by pref_id. Absent -> baseline defers.
    compliance = {}
    if getattr(args, "compliance", None):
        try:
            compliance = json.load(open(args.compliance)).get("results", {})
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"[accounting] compliance file unreadable: {e}", file=sys.stderr)
            return 2

    supplied = {}
    if args.verdicts:
        try:
            supplied = load_verdicts(args.verdicts)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"[accounting] verdict file rejected: {e}", file=sys.stderr)
            return 2

    eq = evidence_quality(p)
    entries = []
    for pref, reason in due:
        pid = pref.get("id")
        spec = supplied.get(pid)
        if spec:
            verdict = spec["verdict"]
            why = spec.get("reason") or "agent verdict"
            new_value = spec.get("new_value")
            # Enforce the cardinal rule at write time, not just at parse time —
            # the parser cannot know the tier without the graph.
            if verdict == "adopt" and tier_of(pref) == "inferred":
                print(f"[accounting] REJECTED: {pid} is inferred and may not be "
                      f"auto-adopted (graph cardinal rule)", file=sys.stderr)
                return 2
            # Only an explicit agent verdict may suppress delivery.
            defer_scope = spec.get("defer_scope", "review")
            source = "agent"
        else:
            verdict, why = baseline_verdict(pref, reason, p,
                                            compliance.get(pid))
            new_value = None
            defer_scope = "review"  # baseline NEVER silences a preference
            source = "baseline"

        change = apply_verdict(pref, verdict, now, note=why,
                               defer_days=args.defer_days,
                               new_value=new_value,
                               defer_scope=defer_scope) if args.apply else {
            "prior_confidence": pref.get("confidence"),
            "new_confidence": pref.get("confidence"), "prior_value": None}
        entries.append({
            "ts": _iso(now), "run_id": run_id, "pref_id": pid,
            "category": pref.get("category"), "verdict": verdict,
            "verdict_source": source,
            "evidence_quality": eq, "due_reason": reason, "reason": why,
            **change,
        })

    tripped = check_refactor_trigger(entries)

    if args.apply:
        write_graph(p, p["org_graph"], graph)
        append_ledger(p, entries)
        if tripped:
            sig = write_refactor_signal(p, tripped, run_id, now)
            print(f"REFACTOR TRIGGER FIRED -> {sig}")

    counts = {v: sum(1 for e in entries if e["verdict"] == v) for v in VERDICTS}
    if args.json:
        print(json.dumps({"run_id": run_id, "applied": bool(args.apply),
                          "processed": len(entries), "verdicts": counts,
                          "evidence_quality": eq, "refactor_tripped": tripped,
                          "entries": entries}, indent=2, ensure_ascii=False))
    else:
        mode = "APPLIED" if args.apply else "DRY RUN (no writes; pass --apply)"
        print(f"TasteGraph accounting {run_id} — {mode}")
        print(f"  processed: {len(entries)}   evidence: {eq}")
        for v in VERDICTS:
            print(f"  {v:10s} {counts[v]}")
        for e in entries[:15]:
            print(f"    [{e['verdict']:9s}] {e['pref_id']} — {e['reason']}")
        if len(entries) > 15:
            print(f"    ... and {len(entries) - 15} more (use --json for all)")
        if tripped and not args.apply:
            print(f"  REFACTOR TRIGGER would fire: "
                  f"{', '.join(t['condition'] for t in tripped)}")
    return 0


def cmd_bundle(args, p):
    """Emit evidence bundles for an agent to judge. This is the input to `run`."""
    graph = load_graph(p["org_graph"])
    now = _now()
    due = collect_due(graph, p, now)
    if args.limit:
        due = due[:args.limit]
    bundles = [build_bundle(pref, reason, p) for pref, reason in due]
    print(json.dumps({
        "generated_at": _iso(now),
        "count": len(bundles),
        "evidence_quality": evidence_quality(p),
        "instructions": (
            "Assign exactly one verdict per preference from allowed_verdicts. "
            "Return {pref_id: {verdict, reason, new_value?}} and feed it to "
            "`tastegraph_accounting.py run --verdicts <file> --apply`. "
            "new_value is REQUIRED for adapt. Never adopt an inferred preference."),
        "bundles": bundles,
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_policy(args, p):
    """Report whether the graph's verification_policy is actually governing.

    Exists because the policy LOOKS authoritative while being unenforceable
    prose. Silence about that would reproduce, one level up, the exact failure
    this whole tool was built to end.
    """
    graph = load_graph(p["org_graph"])
    intervals, state = intervals_from_policy(graph)
    policy = graph.get("verification_policy") or {}
    data_tiers = sorted({tier_of(x) for x in _collect_prefs(graph, [])})
    policy_tiers = sorted(TIER_ALIASES.get(k.lower(), k.lower()) for k in policy)

    print(f"verification_policy state: {state}")
    if state == "prose-only":
        print("  WARNING: the policy names tiers but supplies no interval_days.")
        print("  Its cadence is prose in SESSION units, which is unparseable and")
        print("  keyed to a counter that reads 1 on session 138. The defaults")
        print("  below are what actually governs — the policy is NOT honoured.")
    print(f"  policy tiers (normalised): {policy_tiers}")
    print(f"  data tiers   (normalised): {data_tiers}")
    if set(policy_tiers) != set(data_tiers):
        print(f"  TIER MISMATCH — aliases applied: {TIER_ALIASES}")
    print("  intervals in force (days):")
    for tier, days in sorted(intervals.items()):
        print(f"    {tier:10s} {days}")
    return 0


def cmd_ledger(args, p):
    if not os.path.isfile(p["ledger"]):
        print("TasteGraph accounting ledger: empty (no accounting has run)")
        return 0
    with open(p["ledger"]) as fh:
        lines = [json.loads(l) for l in fh if l.strip()]
    for e in lines[-args.limit:]:
        print(f"{e['ts']}  [{e['verdict']:9s}] {e['pref_id']} — {e.get('reason', '')}")
    print(f"({len(lines)} total entries)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="TasteGraph learning accounting")
    ap.add_argument("--spoke-path", help="spoke root (auto-detected if omitted)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("due", help="read-only; exit 1 if any preference is due")
    d.add_argument("--json", action="store_true")

    b = sub.add_parser("bundle", help="emit evidence bundles for an agent to judge")
    b.add_argument("--limit", type=int, default=None)

    r = sub.add_parser("run", help="conduct the accounting")
    r.add_argument("--compliance", default=None,
                   help="tastegraph_compliance.py check --json output; supplies "
                        "the measured signal that separates adopt from reinforce")
    r.add_argument("--verdicts", default=None,
                   help="agent-prepared verdict file; omit for the "
                        "conservative mechanical baseline")
    r.add_argument("--apply", action="store_true",
                   help="actually write (default is a dry run)")
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--defer-days", type=int, default=90)
    r.add_argument("--json", action="store_true")

    sub.add_parser("policy", help="report whether verification_policy governs")

    g = sub.add_parser("ledger", help="read back accounting history")
    g.add_argument("--limit", type=int, default=20)

    args = ap.parse_args(argv)
    p = paths(find_spoke_root(args.spoke_path))
    return {"due": cmd_due, "bundle": cmd_bundle, "run": cmd_run,
            "policy": cmd_policy, "ledger": cmd_ledger}[args.cmd](args, p)


if __name__ == "__main__":
    sys.exit(main())
