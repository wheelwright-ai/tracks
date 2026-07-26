#!/usr/bin/env python3
"""group_awareness.py — Phase 2: the self-interrogating group-awareness advisor.

THE IDEA (operator, 2026-07-22): a spoke already writes down its goals, decisions and
insights every turn. Some of those are things the GROUP should know — and today the
operator is the transport: he reads one spoke's notes and repeats the instruction to
another. This closes that loop. The spoke reads its own track, spots what its group
needs to know, and routes it along the authority waterfall — with a confirmation back.

PHASE 1 vs PHASE 2, the one distinction that matters:
  Phase 1 (propagation_engine.py) = DECLARED propagation. An event fires, matching
  contract rows route reactions. Deterministic, oracle-tested, no LLM.
  Phase 2 (this) = INFERRED propagation. An LLM reads the track corpus and DISCOVERS
  what is worth propagating. It emits PROPOSALS ONLY.

  The LLM is never the transport. It proposes; this module gates the proposals
  deterministically and hands delivery to the Phase-1 engine or the herald incoming/
  channel. Every delivery is recorded to group-activity-log.jsonl. That separation is
  the whole safety argument: a hallucinated proposal fails a gate, it does not reach
  a sibling spoke.

FIVE GATES, because the primary risk here is OVER-PROPAGATION (the archie-flood
failure mode: every spoke inferring and broadcasting drowns the group in lugs):
  1. EVIDENCE.  Every proposal must cite track turns that actually exist in the brief
     it was given. A citation that is not in the corpus is a hallucination and the
     proposal dies. This is the anti-fabrication oracle.
  2. THRESHOLD. impact >= 6 AND confidence >= 0.70. Interesting is not propagatable.
  3. AUTHORITY. Direction is computed from groups.json, never claimed by the LLM. A
     product proposing to the hub routes UP as a proposal; the hub instructs downward
     as a directive. Members whose powers do not include filing cross-spoke lugs
     cannot propagate at all. An event that is not DECLARED in a shared group is
     rejected — the LLM cannot invent events, only fire ones the contract knows.
  4. DEDUP.    A dedup_key already in the group activity log never fires twice, so
     re-running the advisor over the same track is idempotent.
  5. CAP.      A hard per-run ceiling (default 3). A run that wants to say twenty
     things is noise by construction.

FLOW:
    group_awareness.py brief   > writes last-brief.json  (the corpus + the rules + the bar)
    <LLM advisor reads the brief, writes proposals.json>
    group_awareness.py ingest --proposals proposals.json [--dry-run]

CLI:
    group_awareness.py brief [--root .] [--limit 60] [--json]
    group_awareness.py ingest --proposals FILE [--root .] [--dry-run] [--json]
    group_awareness.py status [--root .]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TOOLS))

import propagation_engine as pe  # noqa: E402

G, Y, R, B, DIM, OFF = "\033[32m", "\033[33m", "\033[31m", "\033[1m", "\033[2m", "\033[0m"

MIN_IMPACT = int(os.environ.get("WAI_GROUP_AWARENESS_MIN_IMPACT", "6"))
MIN_CONFIDENCE = float(os.environ.get("WAI_GROUP_AWARENESS_MIN_CONFIDENCE", "0.70"))
PER_RUN_CAP = int(os.environ.get("WAI_GROUP_AWARENESS_CAP", "3"))

# Powers that authorize a member to put a lug in someone else's incoming/. A member
# holding none of these has no propagation seat at all.
FILING_POWERS = {
    "file_lugs_to_any_member_incoming",
    "file_lugs_to_member_incoming",
    "author_canonical_source",
    "distribute_managed_copies_fleet_wide",
    "write_managed_trees_of_member_spokes",
}

KINDS = ("event", "direct", "rule")


# ── identity ───────────────────────────────────────────────────────────────
def _advisor_dir(root: Path) -> Path:
    return root / "WAI-Harness" / "spoke" / "advisors" / "group-awareness"


def self_id(root: Path, registry: list | None = None) -> str:
    """Resolve THIS spoke's wheel_id by matching its path in the hub registry.

    Path-match, not a state field: WAI-State.json carries no wheel_id on most spokes,
    and the registry path is the same identity the propagation engine delivers to.
    """
    registry = registry if registry is not None else pe.load_registry()
    rp = str(root.resolve()).rstrip("/")
    for w in registry:
        if str(w.get("path", "")).rstrip("/") == rp:
            return w.get("wheel_id") or root.name
    return root.name


def memberships(wheel_id: str, groups_doc: dict) -> list:
    """Every group this spoke belongs to, with its own seat resolved."""
    out = []
    for grp in groups_doc.get("groups", []) or []:
        for m in grp.get("members", []) or []:
            if m.get("wheel_id") == wheel_id:
                out.append({"group": grp, "member": m})
                break
    return out


def _member_of(grp: dict, wheel_id: str) -> dict | None:
    for m in grp.get("members", []) or []:
        if m.get("wheel_id") == wheel_id:
            return m
    return None


# ── the corpus ─────────────────────────────────────────────────────────────
_MINE_FIELDS = ("focus", "user_intent", "action", "outcome", "decisions", "insights", "open")


def _read_track(root: Path, limit: int) -> list:
    """The most recent track turns, newest sessions first, flattened oldest->newest.

    Only the judgment fields — the agent's own reasoning about what it did and decided.
    Raw assistant_text/thinking are deliberately excluded: they are long, and what the
    group needs to know lives in the structured fields.
    """
    sess_dir = root / "WAI-Harness" / "spoke" / "local" / "sessions"
    if not sess_dir.is_dir():
        return []
    files = sorted((p for p in sess_dir.glob("*/track.jsonl") if p.is_file()),
                   key=lambda p: p.parent.name, reverse=True)
    rows: list = []
    for f in files:
        if len(rows) >= limit:
            break
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        session = f.parent.name
        for line in reversed(lines):
            if len(rows) >= limit:
                break
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            # Real track files carry the occasional bare string or array line from older
            # writers. A malformed corpus must never crash the advisor — it just has less
            # to read.
            if not isinstance(r, dict):
                continue
            entry = {"session": session, "turn": r.get("turn")}
            has = False
            for k in _MINE_FIELDS:
                v = r.get(k)
                if v:
                    entry[k] = v
                    has = True
            if has:
                rows.append(entry)
    rows.reverse()
    return rows


def _goal_of(path: str | None) -> str | None:
    """A member's stated goal, read-only. Sovereignty-safe: we never write there."""
    if not path:
        return None
    try:
        d = json.loads((Path(path) / "WAI-Harness" / "spoke" / "local"
                        / "WAI-State.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    w = d.get("wheel", {}) or {}
    return w.get("goal") or w.get("description") or None


def seen_keys(master_root: Path | None = None) -> set:
    """Every dedup_key already recorded in the group activity log."""
    log = pe._activity_log_path()
    keys: set = set()
    if not log.exists():
        return keys
    try:
        for line in log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("dedup_key"):
                keys.add(r["dedup_key"])
    except OSError:
        pass
    return keys


def dedup_key(wheel_id: str, kind: str, target: str, action: str) -> str:
    """Stable key over (source, kind, target, normalized action).

    Normalized so a reworded restatement of the same proposal still collides: the
    advisor re-reads the same track every run and will phrase it differently.
    """
    norm = re.sub(r"[^a-z0-9 ]+", " ", str(action).lower())
    # Keep content words AND anything carrying a digit: dropping short tokens wholesale
    # would collide "upgrade to v2" with "upgrade to v3" — a false dedup that silently
    # swallows the second, genuinely different, proposal.
    norm = " ".join(sorted(set(w for w in norm.split()
                               if len(w) > 3 or any(c.isdigit() for c in w))))
    h = hashlib.sha1(f"{wheel_id}|{kind}|{target}|{norm}".encode()).hexdigest()[:12]
    return f"ga-{kind}-{pe._slug(target)}-{h}"


def build_brief(root: Path, limit: int = 60) -> dict:
    """Everything the advisor needs to interrogate itself, and nothing it must guess."""
    groups_doc = pe.load_groups()
    registry = pe.load_registry()
    me = self_id(root, registry)
    mine = memberships(me, groups_doc)

    groups_view = []
    declared_events: set = set()
    for entry in mine:
        grp, member = entry["group"], entry["member"]
        rules = grp.get("propagation_contract", []) or []
        for r in rules:
            if r.get("on_event"):
                declared_events.add(r["on_event"])
        peers = []
        for m in grp.get("members", []) or []:
            if m.get("wheel_id") == me:
                continue
            p = pe._path_for(m.get("wheel_id"), registry)
            peers.append({
                "wheel_id": m.get("wheel_id"), "role": m.get("role"),
                "authority": m.get("authority"), "capabilities": m.get("capabilities") or [],
                "direction_from_me": pe._direction(int(member.get("authority", 99)),
                                                   int(m.get("authority", 99))),
                "goal": _goal_of(p),
            })
        groups_view.append({
            "group_id": grp.get("group_id"),
            "my_role": member.get("role"),
            "my_authority": member.get("authority"),
            "my_powers": member.get("powers") or [],
            "my_capabilities": member.get("capabilities") or [],
            "peers": peers,
            "declared_rules": [{"on_event": r.get("on_event"), "role": r.get("role"),
                                "action": r.get("action"),
                                "when_capability": r.get("when_capability")} for r in rules],
        })

    brief = {
        "self": {"wheel_id": me, "path": str(root.resolve()), "goal": _goal_of(str(root))},
        "groups": groups_view,
        "declared_events": sorted(declared_events),
        "track_corpus": _read_track(root, limit),
        "already_propagated": sorted(seen_keys()),
        "gates": {
            "min_impact": MIN_IMPACT, "min_confidence": MIN_CONFIDENCE,
            "per_run_cap": PER_RUN_CAP,
            "evidence": "every proposal must cite {session, turn} pairs present in track_corpus",
            "authority": "direction is computed from groups.json, never claimed by you",
            "events": "kind=event may only name an event in declared_events",
        },
        "proposal_schema": {
            "kind": "event | direct | rule",
            "event": "(kind=event) one of declared_events — the contract routes the reactors",
            "target": "(kind=direct|rule) the wheel_id that should receive it",
            "group": "the group_id this travels in",
            "action": "the concrete thing the receiver should do",
            "why": "why the group needs this — one sentence",
            "verification": "how the receiver proves it is done",
            "impact": "int 1-10", "confidence": "float 0-1",
            "evidence": "[{session, turn}] — the track turns this was inferred from",
        },
    }
    return brief


# ── the gates ──────────────────────────────────────────────────────────────
def gate(prop: dict, ctx: dict) -> dict:
    """Judge one proposal. Pure — no I/O, no side effects, so the oracle is honest.

    Returns {verdict: accept|reject, reason, ...resolved routing fields}.
    """
    kind = prop.get("kind")
    if kind not in KINDS:
        return {"verdict": "reject", "reason": f"unknown kind '{kind}'"}

    # 1. EVIDENCE — the anti-fabrication gate.
    ev = prop.get("evidence") or []
    corpus = ctx["corpus_index"]
    cited = [e for e in ev if (str(e.get("session")), str(e.get("turn"))) in corpus]
    if not cited:
        return {"verdict": "reject",
                "reason": "no evidence citing a track turn present in the brief corpus"}

    # 2. THRESHOLD
    try:
        impact = int(prop.get("impact", 0))
        confidence = float(prop.get("confidence", 0))
    except (TypeError, ValueError):
        return {"verdict": "reject", "reason": "impact/confidence not numeric"}
    if impact < ctx["min_impact"] or confidence < ctx["min_confidence"]:
        return {"verdict": "reject",
                "reason": f"below bar (impact {impact}<{ctx['min_impact']} or "
                          f"confidence {confidence}<{ctx['min_confidence']})"}

    # 3. AUTHORITY
    gid = prop.get("group")
    seat = ctx["seats"].get(gid)
    if not seat:
        return {"verdict": "reject", "reason": f"not a member of group '{gid}'"}
    powers = set(seat["member"].get("powers") or [])
    # Powers are free-text-ish; match on prefix so a power carrying a parenthetical
    # operator note still counts.
    if not any(any(p.startswith(fp) for fp in FILING_POWERS) for p in powers):
        return {"verdict": "reject",
                "reason": f"role '{seat['member'].get('role')}' holds no lug-filing power in '{gid}'"}

    if kind == "event":
        event = prop.get("event")
        if event not in ctx["declared_events"]:
            return {"verdict": "reject",
                    "reason": f"event '{event}' is not declared in any of my groups "
                              f"(propose kind=rule instead)"}
        target = None
        direction = "contract"          # the contract's rows decide who reacts
    else:
        target = prop.get("target")
        if kind == "rule":
            # A new contract row is a change to the group's own constitution: it can only
            # be authored by the group's authority-1 seat. Route it there, whatever the
            # LLM named as target.
            target = ctx["authority_head"].get(gid)
            if not target:
                return {"verdict": "reject", "reason": f"group '{gid}' has no authority head"}
        tm = _member_of(seat["group"], target) if target else None
        if not tm:
            return {"verdict": "reject",
                    "reason": f"target '{target}' is not a member of group '{gid}'"}
        direction = pe._direction(int(seat["member"].get("authority", 99)),
                                  int(tm.get("authority", 99)))

    if not str(prop.get("action") or "").strip():
        return {"verdict": "reject", "reason": "empty action"}

    # 4. DEDUP
    key = dedup_key(ctx["me"], kind, target or prop.get("event") or gid, prop.get("action"))
    if key in ctx["seen"]:
        return {"verdict": "reject", "reason": "already propagated (dedup)", "dedup_key": key}

    return {"verdict": "accept", "reason": "", "dedup_key": key, "kind": kind,
            "group": gid, "target": target, "direction": direction,
            "event": prop.get("event"), "impact": impact, "confidence": confidence,
            "evidence": cited}


def _build_inferred_lug(prop: dict, g: dict, ctx: dict, now_iso: str) -> tuple:
    """The lug an inferred proposal becomes. Says plainly that it was INFERRED."""
    kind, gid, target = g["kind"], g["group"], g["target"]
    direction = g["direction"]
    action = prop.get("action")
    lug_id = f"group-inferred-{pe._slug(ctx['me'])}-{g['dedup_key'][3:]}-v1"
    ev_s = "; ".join(f"{e.get('session')}#{e.get('turn')}" for e in g["evidence"])

    if kind == "rule":
        title = f"[group:{gid}] proposal: add a propagation rule — {action}"
        execute = [
            f"Evaluate adding this propagation_contract row to group '{gid}': {action}",
            "If adopted, add the row to WAI-Harness/hub/local/registry/groups.json and let "
            "propagation_engine.py carry it from then on.",
            "If declined, record the reason back to the proposing member's incoming/.",
        ]
        targets = ["WAI-Harness/hub/local/registry/groups.json"]
    else:
        title = f"[group:{gid}] {direction}: {action}"
        execute = [action]
        targets = prop.get("file_targets") or [
            "the receiver scopes exact files at pickup per execute[]; this is an inferred "
            "group item, not a pre-scoped edit."]

    verification = prop.get("verification") or "Confirm the action is complete and record it."
    return lug_id, {
        "id": lug_id,
        "type": "task",
        "status": "open",
        "routed_to": "LOCAL",
        "created_at": now_iso,
        "created_by": f"group_awareness advisor on {ctx['me']} (inferred from track)",
        "title": title,
        "summary": (f"INFERRED group propagation from {ctx['me']} ({direction}). "
                    f"{prop.get('why') or action} "
                    f"Inferred from this spoke's own track record: {ev_s}."),
        "_group_propagation": {
            "group": gid, "source": ctx["me"], "target": target, "kind": kind,
            "direction": direction, "dedup_key": g["dedup_key"], "inferred": True,
            "confidence": g["confidence"], "evidence": g["evidence"],
        },
        "perceive": [
            f"This lug was inferred by {ctx['me']}'s group-awareness advisor reading its own "
            f"track record — it is NOT a declared contract rule firing.",
            f"Direction is '{direction}': " + (
                "the source outranks you in group authority — treat as an instruction."
                if direction == "directive" else
                "you outrank the source — this is a PROPOSAL; you decide whether to adopt, "
                "and route your decision back."
                if direction == "proposal" else
                "peer request — coordinate, do not overwrite."),
            f"Evidence (source spoke's track turns): {ev_s}",
        ],
        "execute": execute,
        "verify": [verification],
        "acceptance_criteria": [
            verification + "; a completion is delivered back to "
            f"{ctx['me']}'s lugs/incoming/ so the group activity log closes the loop."],
        "file_targets": targets,
        "impact": g["impact"], "effort": "S", "model_fit": "sonnet",
        "model_fit_reason": "Acting on a scoped group item with a stated verification.",
        "_improvement_lenses": {
            "skeptic": ("This was INFERRED by an LLM, not declared by the contract — so the "
                        "first question is whether the evidence actually supports it. The "
                        "cited track turns are listed; if they do not, decline and say so."),
            "architect": ("Inference discovered it; the deterministic channel delivered it. "
                          "The authority direction, not the proposing agent, decides whether "
                          "this binds you."),
            "naive_reader": (f"{ctx['me']} noticed something in its own notes that you should "
                             f"know about, and told you."),
        },
    }


def ingest(proposals: list, root: Path, dry_run: bool = False,
           now_iso: str | None = None, brief: dict | None = None) -> dict:
    """Gate every proposal, then deliver the survivors through the deterministic channel."""
    now_iso = now_iso or "PENDING"
    brief = brief or _load_last_brief(root)
    if brief is None:
        return {"error": "no brief on disk — run `group_awareness.py brief` first",
                "accepted": [], "rejected": [], "delivered": []}

    groups_doc = pe.load_groups()
    registry = pe.load_registry()
    me = brief.get("self", {}).get("wheel_id") or self_id(root, registry)
    mine = memberships(me, groups_doc)

    seats, authority_head, declared_events = {}, {}, set()
    for entry in mine:
        gid = entry["group"].get("group_id")
        seats[gid] = entry
        head, best = None, 99
        for m in entry["group"].get("members", []) or []:
            a = int(m.get("authority", 99))
            if a < best:
                head, best = m.get("wheel_id"), a
        authority_head[gid] = head
        for r in entry["group"].get("propagation_contract", []) or []:
            if r.get("on_event"):
                declared_events.add(r["on_event"])

    ctx = {
        "me": me,
        "seats": seats,
        "authority_head": authority_head,
        "declared_events": declared_events,
        "seen": seen_keys(),
        "min_impact": MIN_IMPACT,
        "min_confidence": MIN_CONFIDENCE,
        "corpus_index": {(str(e.get("session")), str(e.get("turn")))
                         for e in brief.get("track_corpus", [])},
    }

    res = {"source": me, "dry_run": dry_run, "accepted": [], "rejected": [],
           "delivered": [], "capped": 0}

    # Rank before capping so the cap keeps the best, not the first the LLM happened to write.
    ordered = sorted(proposals, key=lambda p: (-int(p.get("impact") or 0),
                                               -float(p.get("confidence") or 0)))
    for prop in ordered:
        g = gate(prop, ctx)
        if g["verdict"] != "accept":
            res["rejected"].append({"action": str(prop.get("action"))[:80],
                                    "kind": prop.get("kind"), "reason": g["reason"]})
            continue
        if len(res["accepted"]) >= PER_RUN_CAP:
            res["capped"] += 1
            res["rejected"].append({"action": str(prop.get("action"))[:80],
                                    "kind": prop.get("kind"),
                                    "reason": f"per-run cap of {PER_RUN_CAP} reached"})
            continue
        ctx["seen"].add(g["dedup_key"])       # in-run dedup as well as cross-run
        res["accepted"].append({**g, "action": prop.get("action"), "why": prop.get("why")})

    for a in res["accepted"]:
        if a["kind"] == "event":
            # Hand the whole routing decision to Phase 1. The advisor named an event the
            # contract already declares; the contract decides who reacts and how.
            fired = pe.fire(a["event"], source=me, version=None, group_filter=a["group"],
                            dry_run=dry_run, now_iso=now_iso, dedup_key=a["dedup_key"])
            reactions = fired.get("reactions", [])
            # A firing that reached nobody (the only role-matching member was the source
            # itself, or every reactor was out of scope) writes no activity-log row of its
            # own — so without this, its dedup_key is never recorded and the advisor
            # re-proposes the identical item on every future run. Record the no-op.
            if not reactions and not dry_run:
                pe._append_log({"group": a["group"], "event": a["event"], "source": me,
                                "reactor": None, "role": "event", "direction": "contract",
                                "lug": None, "action": a["action"],
                                "dedup_key": a["dedup_key"], "version": None,
                                "path": None, "inferred": True,
                                "confidence": a["confidence"],
                                "outcome": "no_reactor"}, now_iso)
            res["delivered"].append({"kind": "event", "event": a["event"],
                                     "group": a["group"], "dedup_key": a["dedup_key"],
                                     "reactions": reactions,
                                     "skipped": fired.get("skipped", [])})
            continue

        target_path = pe._path_for(a["target"], registry)
        if not target_path:
            res["delivered"].append({"kind": a["kind"], "target": a["target"],
                                     "error": "no registry path"})
            continue
        ok, why = pe._in_scope(target_path, a["target"])
        if not ok:
            res["delivered"].append({"kind": a["kind"], "target": a["target"],
                                     "error": f"out of scope: {why}"})
            continue
        lug_id, lug = _build_inferred_lug(a, a, ctx, now_iso)
        rec = {"kind": a["kind"], "target": a["target"], "group": a["group"],
               "direction": a["direction"], "lug": lug_id, "dedup_key": a["dedup_key"]}
        if not dry_run:
            inc = Path(target_path) / "WAI-Harness" / "spoke" / "local" / "lugs" / "incoming"
            try:
                inc.mkdir(parents=True, exist_ok=True)
                (inc / f"{lug_id}.json").write_text(json.dumps(lug, indent=2))
                pe._append_log({"group": a["group"], "event": "inferred_propagation",
                                "source": me, "reactor": a["target"],
                                "role": a["kind"], "direction": a["direction"],
                                "lug": lug_id, "action": a["action"],
                                "dedup_key": a["dedup_key"], "version": None,
                                "path": target_path, "inferred": True,
                                "confidence": a["confidence"],
                                "delivered_to": str(inc / f"{lug_id}.json")}, now_iso)
            except OSError as e:
                rec["error"] = str(e)
        res["delivered"].append(rec)
    return res


# ── disk plumbing ──────────────────────────────────────────────────────────
def _brief_path(root: Path) -> Path:
    return _advisor_dir(root) / "last-brief.json"


def _load_last_brief(root: Path) -> dict | None:
    try:
        return json.loads(_brief_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_brief(root: Path, brief: dict) -> Path:
    p = _brief_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(brief, indent=2))
    return p


# ── rendering ──────────────────────────────────────────────────────────────
def render_brief(brief: dict) -> str:
    s = brief["self"]
    out = [f"{B}GROUP AWARENESS BRIEF{OFF}  {s['wheel_id']}"]
    for g in brief["groups"]:
        out.append(f"  {B}{g['group_id']}{OFF}  role={g['my_role']} authority={g['my_authority']} "
                   f"peers={len(g['peers'])} rules={len(g['declared_rules'])}")
    out.append(f"  track corpus: {len(brief['track_corpus'])} turn(s) | "
               f"declared events: {len(brief['declared_events'])} | "
               f"already propagated: {len(brief['already_propagated'])}")
    out.append(f"  bar: impact>={brief['gates']['min_impact']} "
               f"confidence>={brief['gates']['min_confidence']} cap={brief['gates']['per_run_cap']}")
    return "\n".join(out)


def render_ingest(res: dict) -> str:
    if res.get("error"):
        return f"{R}{res['error']}{OFF}"
    out = [f"{B}GROUP AWARENESS INGEST{OFF}  source={res['source']}"
           + (f"  {Y}[DRY-RUN]{OFF}" if res["dry_run"] else "")]
    for d in res["delivered"]:
        if d.get("error"):
            out.append(f"  {R}x {d.get('target') or d.get('event')}: {d['error']}{OFF}")
        elif d["kind"] == "event":
            n = len(d.get("reactions", []))
            out.append(f"  {G}-> event {d['event']}{OFF} fired in {d['group']}: {n} reaction(s)")
        else:
            out.append(f"  {G}-> {d['target']:<24}{OFF} {d['direction']:<9} {d['lug']}")
    for r in res["rejected"]:
        out.append(f"  {DIM}   rejected [{r['kind']}]: {r['reason']}{OFF}")
    out.append(f"\n  {len(res['accepted'])} accepted, {len(res['rejected'])} rejected"
               + (f" ({res['capped']} over cap)" if res["capped"] else "")
               + ". Recorded to group-activity-log.jsonl.")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("brief")
    b.add_argument("--root", default=".")
    b.add_argument("--limit", type=int, default=60)
    b.add_argument("--out", default=None,
                   help="write the brief here instead of into --root's advisor dir. Lets the hub "
                        "run a sibling's advisor read-only, without writing to its tree.")
    b.add_argument("--json", action="store_true")
    i = sub.add_parser("ingest")
    i.add_argument("--proposals", required=True)
    i.add_argument("--root", default=".")
    i.add_argument("--brief", default=None,
                   help="brief to validate evidence against (default: --root's last-brief.json)")
    i.add_argument("--dry-run", action="store_true")
    i.add_argument("--now", default=None, help="ISO timestamp (caller-supplied)")
    i.add_argument("--json", action="store_true")
    st = sub.add_parser("status")
    st.add_argument("--root", default=".")
    args = ap.parse_args()
    root = Path(getattr(args, "root", ".")).resolve()

    if args.cmd == "brief":
        brief = build_brief(root, args.limit)
        if args.out:
            p = Path(args.out)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(brief, indent=2))
        else:
            p = _write_brief(root, brief)
        print(json.dumps(brief, indent=2) if args.json
              else render_brief(brief) + f"\n  written: {p}")
        return 0

    if args.cmd == "ingest":
        try:
            raw = json.loads(Path(args.proposals).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"{R}cannot read proposals: {e}{OFF}")
            return 1
        props = raw.get("proposals", raw) if isinstance(raw, dict) else raw
        if not isinstance(props, list):
            print(f"{R}proposals must be a list (or an object with a 'proposals' list){OFF}")
            return 1
        supplied = None
        if args.brief:
            try:
                supplied = json.loads(Path(args.brief).read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"{R}cannot read brief: {e}{OFF}")
                return 1
        res = ingest(props, root, dry_run=args.dry_run, now_iso=args.now, brief=supplied)
        print(json.dumps(res, indent=2) if args.json else render_ingest(res))
        return 1 if res.get("error") else 0

    if args.cmd == "status":
        brief = _load_last_brief(root)
        print(render_brief(brief) if brief else "(no brief yet — run `brief`)")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
