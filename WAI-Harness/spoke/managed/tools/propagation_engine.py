#!/usr/bin/env python3
"""propagation_engine.py — the consumer the group propagation_contract never had.

THE IDEA (operator, 2026-07-22): a group is a local contract, certified across its
members, that starts with a primary spoke's vision for how the others relate and act.
When a milestone/event fires inside the group, members react along a waterfall of
decisioning authority — automatically, mindfully — so behaviours the operator would
otherwise repeat get actioned and confirmed without him.

WHAT WAS ALREADY BUILT (and this finishes):
  - groups.json carries members with role + authority (int, 1=highest) + powers, and
    propagation_contract rows: "when on_event fires, every member with role does action."
  - _authority_schema: lower number wins; conflicts route UP as lugs, never overwrite.
  - herald / incoming: the sanctioned cross-spoke delivery channel.
It was all a DOCUMENTED STUB with zero consumers. This is the consumer.

WHAT THIS IS, PRECISELY: the DETERMINISTIC half (Phase 1). It executes DECLARED rules.
It does not infer — an event in, matching rows found, reacting lugs filed on the
role-matching members, recorded to the group activity log, confirmation returned. The
INFERRED half (an advisor reading track files to DISCOVER propagation-worthy goals)
feeds rows/events into THIS engine; the LLM never becomes the transport.

FOUR INVARIANTS, because a coordination layer that gets these wrong is worse than none:
  1. SCOPE. A reacting member that fleet_scope excludes (client work, inactive,
     deprecated) is NEVER written to. Same authority the operator set for autopilot.
  2. AUTHORITY / DIRECTION. Source below the reactor in authority (lower number) issues
     a DIRECTIVE; source above issues a PROPOSAL (routes up, the reactor decides). A
     peer issues a request. We never let a low-authority member command a high one.
  3. DEDUP. A (group, event, reactor, dedup_key) already in the activity log does not
     fire twice. Re-emitting the same version-cut must be idempotent.
  4. RECORD + CONFIRM. Every reaction is appended to group-activity-log.jsonl and
     returned for an operator confirmation. Silent propagation is not allowed — the
     closed loop ("propagated X from A to B, done") is the whole value.

CLI:
    propagation_engine.py fire --event harness_version_cut --source mywheel \
        --version 4.14.6 [--group core] [--dry-run] [--json]
    propagation_engine.py rules [--group core]        # show declared rows
    propagation_engine.py log [--group core] [--limit 20]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(_TOOLS))

DEFAULT_MASTER = Path("/home/mario/projects/wheelwright/mywheel/WAI-Harness")
G, Y, R, B, DIM, OFF = "\033[32m", "\033[33m", "\033[31m", "\033[1m", "\033[2m", "\033[0m"


def _master() -> Path:
    return Path(os.environ.get("WAI_HARNESS_MASTER", str(DEFAULT_MASTER)))


def _hub_local() -> Path:
    return _master() / "hub" / "local"


def load_groups() -> dict:
    p = _hub_local() / "registry" / "groups.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"groups": []}


def load_registry() -> list:
    p = _hub_local() / "hub-registry.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("wheels", []) or []
    except (OSError, ValueError):
        return []


def _path_for(wheel_id: str, registry: list) -> str | None:
    for w in registry:
        if w.get("wheel_id") == wheel_id:
            return w.get("path")
    return None


def _in_scope(path: str, wheel_id: str) -> tuple[bool, str]:
    """Honor the same scope authority the operator set for autopilot."""
    try:
        import fleet_scope
        policy = fleet_scope.load_policy()
        reason = fleet_scope.exclusion_reason(path, wheel_id, policy)
        return (reason is None, reason or "")
    except Exception:
        # Fail CLOSED on the one rule that causes damage.
        if "/client-work/" in str(path) or "/_archive/" in str(path):
            return False, "client-work/_archive (fleet_scope unavailable, failing closed)"
        return True, ""


def _activity_log_path() -> Path:
    return _master() / "spoke" / "local" / "group-activity-log.jsonl"


def _already_fired(group_id: str, event: str, reactor: str, dedup_key: str) -> bool:
    """Has this reactor already reacted to this event+version? Group is deliberately
    NOT part of the match: a reactor does the work once regardless of which group
    triggered it (mywheel belongs to several overlapping groups). Keying on group
    let a refire re-deliver from a second group that never got logged the first time."""
    log = _activity_log_path()
    if not log.exists():
        return False
    try:
        for line in log.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if (r.get("event") == event and r.get("reactor") == reactor
                    and r.get("dedup_key") == dedup_key):
                return True
    except OSError:
        pass
    return False


def _authority_of(wheel_id: str, members: list) -> int:
    for m in members:
        if m.get("wheel_id") == wheel_id:
            return int(m.get("authority", 99))
    return 99


# A row's applies_to speaks in family terms ("children"); the engine computes direction
# ("directive"). This maps between them so a policy row reads the way the operator states it.
_TIER_OF = {"directive": "children", "proposal": "superiors", "request": "peers"}


def _direction(source_auth: int, reactor_auth: int) -> str:
    # Lower number = higher authority.
    if source_auth < reactor_auth:
        return "directive"       # source outranks reactor -> instruct
    if source_auth > reactor_auth:
        return "proposal"        # source is below reactor -> propose, reactor decides
    return "request"             # peers


def _slug(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:48]


def _build_reaction_lug(group_id, event, source, version, row, reactor, direction,
                        dedup_key, now_iso):
    action = row.get("action", "react to the group event")
    verification = row.get("verification", "")
    ver_s = f"-{_slug(version)}" if version else ""
    lug_id = f"group-{_slug(event)}{ver_s}-{_slug(row.get('role'))}-{_slug(reactor)}-v1"
    lug_type = "task" if direction == "directive" else "proposal"
    # 'proposal' has no bytype dir on most spokes; deliver to incoming/ (intake routes it).
    return lug_id, {
        "id": lug_id,
        "type": "task",                      # task is universally intakeable; direction carries the semantics
        "status": "open",
        "routed_to": "LOCAL",
        "created_at": now_iso,
        "created_by": f"propagation_engine (group={group_id}, event={event})",
        "title": f"[group:{group_id}] {direction}: {action}",
        "summary": (f"Group-propagated {direction} from {source} (authority-driven). Event '{event}'"
                    + (f" version {version}" if version else "")
                    + f". Your role '{row.get('role')}' reacts: {action}"),
        "_group_propagation": {
            "group": group_id, "event": event, "source": source, "version": version,
            "role": row.get("role"), "direction": direction, "dedup_key": dedup_key,
        },
        "perceive": [
            f"This lug was filed automatically by the group propagation engine because event '{event}' fired in group '{group_id}'.",
            f"Direction is '{direction}': " + (
                "the source outranks you in group authority — treat as an instruction to carry out."
                if direction == "directive" else
                "you outrank the source — treat as a PROPOSAL; you decide whether/how to adopt, and route your decision back."
                if direction == "proposal" else
                "peer request — coordinate, do not overwrite."),
        ],
        "execute": [action],
        "verify": [verification] if verification else ["Confirm the reaction is complete and record it."],
        "acceptance_criteria": [
            (verification or f"The '{row.get('role')}' reaction to {event} is complete") +
            "; a completion is delivered back so the group activity log closes the loop."],
        "file_targets": row.get("target_hint") or [
            "WAI-Harness/spoke/local/ — the reactor scopes the exact files at pickup per execute[]; "
            "this is a group directive, not a pre-scoped edit."],
        "impact": 7, "effort": "S", "model_fit": "sonnet",
        "model_fit_reason": "Reacting to a declared group event with a specific action + verification — scoped work.",
        "_improvement_lenses": {
            "skeptic": "Is this reaction actually warranted, or propagation noise? It fired from a DECLARED rule matched to your role, deduped against the group log — not inferred. If the rule itself is wrong, fix the row, not this lug.",
            "architect": "The group contract decided this, not an agent. The authority direction tells you whether it binds you or merely asks.",
            "naive_reader": f"Something happened in {source} that your role is supposed to respond to, so the group told you.",
        },
    }


def fire(event: str, source: str, version: str | None = None, group_filter: str | None = None,
         dry_run: bool = False, now_iso: str | None = None,
         dedup_key: str | None = None) -> dict:
    now_iso = now_iso or "PENDING"     # caller stamps real time; keep engine time-pure for resume-safety
    groups_doc = load_groups()
    registry = load_registry()
    # An explicit key lets an INFERRED firing (group_awareness, Phase 2) dedup on its own
    # proposal identity rather than on a version it does not have. Declared firings keep
    # the original version-or-event behaviour untouched.
    dedup_key = dedup_key or version or event
    result = {"event": event, "source": source, "version": version,
              "dry_run": dry_run, "reactions": [], "skipped": [], "groups_considered": []}
    # Cross-group dedup within one fire: mywheel belongs to several groups, so the
    # same reactor can match the same event+version in more than one. A reactor does
    # the work once; the FIRST group to claim it wins (groups are ordered with the
    # canonical/core group first). Without this, basher got two near-identical
    # "distribute the cut" directives from `core` and `wheelwright-product`.
    _seen_reactions: set = set()

    for grp in groups_doc.get("groups", []):
        gid = grp.get("group_id")
        if group_filter and gid != group_filter:
            continue
        members = grp.get("members", [])
        member_ids = {m.get("wheel_id") for m in members}
        # An event only propagates inside a group that contains its source (or a hub event).
        if source not in member_ids and source != "hub":
            continue
        result["groups_considered"].append(gid)
        rows = grp.get("propagation_contract", []) or []
        source_auth = _authority_of(source, members)

        for row in rows:
            if row.get("on_event") != event:
                continue
            want_role = row.get("role")
            want_capability = row.get("when_capability")
            # A POLICY row targets a whole tier rather than one role: role "*" matches every
            # member, and applies_to narrows by the authority relationship. This is what makes
            # "a directive every child adopts" expressible — spoke hygiene and synchronization
            # policy is issued once by the hub and lands on all members beneath it, instead of
            # needing one near-identical row per role.
            applies_to = row.get("applies_to", "all")
            for m in members:
                if want_role != "*" and m.get("role") != want_role:
                    continue
                reactor = m.get("wheel_id")
                if reactor == source:
                    continue                       # never react to your own emission
                m_direction = _direction(source_auth, int(m.get("authority", 99)))
                if applies_to != "all" and _TIER_OF.get(m_direction) != applies_to:
                    result["skipped"].append({"reactor": reactor,
                                              "reason": f"applies_to '{applies_to}', this member is a "
                                                        f"{_TIER_OF.get(m_direction)}"})
                    continue
                # Capability throttle: a row scoped to a capability reaches ONLY members
                # that declare it. This is what keeps a security_lib_update for 'stripe'
                # off the 4 products that don't integrate stripe — the over-propagation guard.
                if want_capability and want_capability not in (m.get("capabilities") or []):
                    result["skipped"].append({"reactor": reactor,
                                              "reason": f"lacks capability '{want_capability}'"})
                    continue
                _rk = (reactor, event, dedup_key)
                if _rk in _seen_reactions:
                    result["skipped"].append({"reactor": reactor,
                                              "reason": f"already reacting in a prior group (cross-group dedup)"})
                    continue
                path = _path_for(reactor, registry)
                if not path:
                    result["skipped"].append({"reactor": reactor, "reason": "no registry path"})
                    continue
                ok, why = _in_scope(path, reactor)
                if not ok:
                    result["skipped"].append({"reactor": reactor, "reason": f"out of scope: {why}"})
                    continue
                if _already_fired(gid, event, reactor, dedup_key):
                    result["skipped"].append({"reactor": reactor, "reason": "already fired (dedup)"})
                    continue
                direction = m_direction
                lug_id, lug = _build_reaction_lug(gid, event, source, version, row,
                                                  reactor, direction, dedup_key, now_iso)
                _seen_reactions.add(_rk)
                reaction = {"group": gid, "event": event, "source": source, "reactor": reactor,
                            "role": want_role, "direction": direction, "lug": lug_id,
                            "action": row.get("action"), "dedup_key": dedup_key,
                            "version": version, "path": path}
                if not dry_run:
                    inc = Path(path) / "WAI-Harness" / "spoke" / "local" / "lugs" / "incoming"
                    try:
                        inc.mkdir(parents=True, exist_ok=True)
                        (inc / f"{lug_id}.json").write_text(json.dumps(lug, indent=2))
                        _append_log({**reaction, "delivered_to": str(inc / f"{lug_id}.json")}, now_iso)
                    except OSError as e:
                        reaction["error"] = str(e)
                result["reactions"].append(reaction)
    return result


def _append_log(reaction: dict, now_iso: str) -> None:
    log = _activity_log_path()
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a") as fh:
            fh.write(json.dumps({**reaction, "ts": now_iso}) + "\n")
    except OSError:
        pass


# ── rendering ──────────────────────────────────────────────────────────────
def render_fire(res: dict) -> str:
    out = [f"{B}PROPAGATION{OFF}  event={res['event']} source={res['source']}"
           + (f" version={res['version']}" if res['version'] else "")
           + (f"  {Y}[DRY-RUN]{OFF}" if res['dry_run'] else "")]
    if not res["reactions"] and not res["skipped"]:
        out.append("  no declared rule matched this event in any group the source belongs to.")
        return "\n".join(out)
    for r in res["reactions"]:
        col = G if r["direction"] == "directive" else Y
        err = f"  {R}ERROR {r['error']}{OFF}" if r.get("error") else ""
        out.append(f"  {col}-> {r['reactor']:<26}{OFF} {r['direction']:<9} {r['action'][:60]}{err}")
    for s in res["skipped"]:
        out.append(f"  {DIM}   {s['reactor']:<26} skipped: {s['reason']}{OFF}")
    out.append(f"\n  {len(res['reactions'])} reaction(s) filed, {len(res['skipped'])} skipped. "
               f"Recorded to group-activity-log.jsonl.")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fire")
    f.add_argument("--event", required=True)
    f.add_argument("--source", required=True)
    f.add_argument("--version", default=None)
    f.add_argument("--group", default=None)
    f.add_argument("--dedup-key", default=None,
                   help="explicit dedup identity (defaults to version, then event)")
    f.add_argument("--dry-run", action="store_true")
    f.add_argument("--now", default=None, help="ISO timestamp (caller-supplied for real time)")
    f.add_argument("--json", action="store_true")
    r = sub.add_parser("rules")
    r.add_argument("--group", default=None)
    lg = sub.add_parser("log")
    lg.add_argument("--group", default=None)
    lg.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    if args.cmd == "fire":
        res = fire(args.event, args.source, args.version, args.group,
                   dry_run=args.dry_run, now_iso=args.now, dedup_key=args.dedup_key)
        print(json.dumps(res, indent=2) if args.json else render_fire(res))
        return 0
    if args.cmd == "rules":
        doc = load_groups()
        for grp in doc.get("groups", []):
            if args.group and grp.get("group_id") != args.group:
                continue
            print(f"{B}{grp.get('group_id')}{OFF}")
            for row in grp.get("propagation_contract", []) or []:
                print(f"  on {row.get('on_event'):<28} role={row.get('role'):<12} -> {row.get('action')}")
        return 0
    if args.cmd == "log":
        log = _activity_log_path()
        if not log.exists():
            print("(no group activity yet)")
            return 0
        lines = [l for l in log.read_text().splitlines() if l.strip()]
        for l in lines[-args.limit:]:
            try:
                r = json.loads(l)
                print(f"  {r.get('ts','?')[:19]}  {r.get('event'):<24} {r.get('source')} -> "
                      f"{r.get('reactor')} ({r.get('direction')})")
            except ValueError:
                continue
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
