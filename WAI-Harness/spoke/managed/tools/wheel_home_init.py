#!/usr/bin/env python3
"""wheel_home_init.py -- Ozi instantiates a wheel's home when the first spoke of a
brand-new wheel finds no hub.

THE GAP (operator, Ruling 15, docs/wheelwright-v5-control-plane-directive.md Part III):
"For a new wheel the hub may not exist when the first spoke is formed. Instruction on
benefit and need must be given by Ozi to instantiate a home for the harness and hub
that manages this wheel." Every onboarding path assumed a hub is already reachable --
the wakeup surface reads a hub base, the registry of record is hub-side, and capacity
and provider-accounting roles all read hub state. A first spoke on a fresh machine
therefore woke into a harness whose control plane had nowhere to live.

THE SHAPE OF THIS FIX (Ruling 12 + Ruling 15 + Ruling 11 + Doctrine 4).
Ruling 12: a new user needs no WAI knowledge for a clean first session, and Ozi
guides warmup. Ruling 15 extends that: warmup must be able to CREATE the wheel's
control plane, not merely connect to one. Ruling 11: the created hub runs at the
CORE capability profile -- stdlib only, complete rather than crippled -- and every
feature must declare what it needs and what enhances it, so degradation is visible,
never silent. Doctrine 4: a first wakeup explains rather than surprises.

FOUR VERBS, in the order a real warmup uses them:
    detect        pure check, no side effects -- is a hub reachable from here?
    explain       Ozi's plain-language benefit/need text -- no jargon, ever
    plan          advised decision: what would be created, and where (no writes)
    instantiate   creates the wheel's home (only with --apply; dry-run by default)
    decline       records declining as a SUPPORTED, visible outcome (not an error)
    wakeup_surface  what a warmup ceremony should print, either way (used by the
                    SessionStart hook wired at .claude/hooks/wakeup-canonical.sh --
                    see that file's "Wheel home" section for the live caller)

DECISION IS ADVISED, NOT AUTOMATIC. `instantiate` and `decline` both require
--apply to write anything; without it they return exactly what WOULD happen. A
warmup ceremony calling this module must show the plan before acting on it.

DURABLE ATTRIBUTION (directive Section 28). Instantiating a wheel's home is itself
a transition worth remembering -- it is the wheel's own origin story. `instantiate`
records one attributed, append-only entry (creator, owner, originating spoke,
initiative/parent lineage, timestamp) to the new hub's own pathgraph, plus a
human-readable mirror line in hub-evolution.log matching the format every other
hub-evolution entry in this codebase already uses.

CLI:
    wheel_home_init.py --root DIR detect [--json]
    wheel_home_init.py --root DIR explain
    wheel_home_init.py --root DIR plan --spoke-id ID [--json]
    wheel_home_init.py --root DIR instantiate --spoke-id ID [--apply] [--json]
                        [--spoke-name NAME] [--model M] [--provider P]
                        [--initiative-id ID] [--lug-id ID]
    wheel_home_init.py --root DIR decline [--apply] [--json]
    wheel_home_init.py --root DIR status [--json]
    wheel_home_init.py --root DIR wakeup-line [--json]

Exit codes: 0 always for read-only verbs (detect/explain/plan/status/wakeup-line).
instantiate/decline exit 0 on success, 1 if --apply was requested but the write
failed for a reason this module can name (e.g. hub already exists).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from wai_paths import resolve_wai_root
except Exception:  # pragma: no cover
    resolve_wai_root = None


NO_HUB = "NO_HUB"
HUB_OK = "HUB_OK"

DECISION_FILE = "wheel-home-decision.json"

# What a hub gives a wheel, and what stays broken without one -- plain language,
# no WAI vocabulary. Kept as structured data (not just prose) so the wakeup line
# and the decline record can both name capabilities by name, per acceptance
# criterion "declining leaves a wakeup surface naming the unavailable capabilities
# by name" -- a free-text sentence cannot be asserted on reliably; a list can.
CAPABILITIES_LOST_WITHOUT_HUB = [
    {
        "name": "shared project list",
        "detail": "no master list of which projects exist and where they live -- "
                  "a second project you start later will not know this one exists, "
                  "and this one will not know about it",
    },
    {
        "name": "shared work budget",
        "detail": "nothing coordinates how much AI work each project is allowed to "
                  "do, so running several projects side by side has no shared limit",
    },
    {
        "name": "usage accounting across projects",
        "detail": "no shared record of AI usage across projects -- you would have "
                  "to piece that together by hand",
    },
    {
        "name": "project-to-project handoff",
        "detail": "no mailbox between projects -- if two projects need to pass "
                  "work to each other, there is nowhere for that handoff to land",
    },
]


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


def base_dir(root, mode=None):
    if resolve_wai_root is not None:
        base, _ = resolve_wai_root(root, mode)
        if base:
            return base
    return os.path.join(root, "WAI-Harness", "spoke", "local")


def _read_json(path, default=None):
    try:
        with open(path) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def state_path(root, mode=None):
    return os.path.join(base_dir(root, mode), "WAI-State.json")


def decision_path(root, mode=None):
    return os.path.join(base_dir(root, mode), "runtime", DECISION_FILE)


# --------------------------------------------------------------------- DETECT


def detect(root, mode=None):
    """Pure check: does this wheel have a reachable home? No side effects.

    Three signals, checked in order -- any one failing is enough to call it
    NO_HUB, and the reason recorded is the FIRST one that failed so the caller
    knows exactly what is missing rather than a generic "no":
      1. WAI-State.json declares wheel.hub_path
      2. that path exists on disk
      3. it holds a readable hub-registry.json (checked at hub_path/local/ first,
         matching the v4 hub layout, then hub_path/ directly for tolerance)
    """
    checked_at = _iso(_now())
    state = _read_json(state_path(root, mode), {}) or {}
    wheel = state.get("wheel", {}) if isinstance(state.get("wheel"), dict) else {}
    hub_path = wheel.get("hub_path") or state.get("hub_path") or ""

    if not hub_path:
        return {
            "state": NO_HUB, "hub_path": None, "registry_path": None,
            "reason": "WAI-State.json declares no wheel.hub_path -- this spoke has "
                      "never been told where its wheel's home is",
            "checked_at": checked_at,
        }
    if not os.path.isdir(hub_path):
        return {
            "state": NO_HUB, "hub_path": hub_path, "registry_path": None,
            "reason": f"wheel.hub_path is declared ({hub_path}) but nothing exists "
                      "there",
            "checked_at": checked_at,
        }
    registry_path = None
    for cand in (os.path.join(hub_path, "local", "hub-registry.json"),
                 os.path.join(hub_path, "hub-registry.json")):
        if os.path.isfile(cand):
            registry_path = cand
            break
    if registry_path is None:
        return {
            "state": NO_HUB, "hub_path": hub_path, "registry_path": None,
            "reason": f"hub_path exists ({hub_path}) but holds no hub-registry.json "
                      "-- not a real hub, or a hub that never finished forming",
            "checked_at": checked_at,
        }
    registry = _read_json(registry_path, None)
    if not isinstance(registry, dict) or not isinstance(registry.get("wheels"), list):
        return {
            "state": NO_HUB, "hub_path": hub_path, "registry_path": registry_path,
            "reason": f"hub-registry.json at {registry_path} is unreadable or "
                      "missing its wheels[] list",
            "checked_at": checked_at,
        }
    return {
        "state": HUB_OK, "hub_path": hub_path, "registry_path": registry_path,
        "reason": f"registry readable at {registry_path} "
                  f"({len(registry['wheels'])} wheel(s) known)",
        "checked_at": checked_at,
    }


# -------------------------------------------------------------------- EXPLAIN


def explain():
    """Ozi's benefit-and-need explanation. Plain language, no WAI vocabulary --
    a brand-new user reading this has never heard of Wheelwright, a wheel, a
    spoke, or a hub, and must not need to."""
    caps = "\n".join(f"  - {c['name']}: {c['detail']}" for c in CAPABILITIES_LOST_WITHOUT_HUB)
    body = textwrap.dedent("""\
        This project has no home yet.

        Right now this project keeps track of its own work just fine. But it has
        no shared place where it -- and any other projects you start later -- can
        be known about together. That shared place is what's missing, and this is
        the first project, so nothing has created it yet.

        Without it, these stay broken:
        __CAPS__

        None of this stops you from working right now, today, alone. This project
        will keep running fine on its own. The moment you add a second project, or
        want to see everything in one place, these are exactly what you'd be
        missing -- and they are quiet failures, not loud ones: nothing crashes,
        things just silently don't connect.

        Creating this shared home takes one decision: where should it live? By
        default it is created right inside this project, next to its own working
        files -- nothing is installed, nothing outside this project changes, and
        no account or network access is required. It is a handful of new files.

        You can also decide not to create it now. That's a fine choice, not an
        error -- this project keeps working either way, and it will keep telling
        you, plainly, which of the things above stay unavailable until you change
        your mind.
    """).strip()
    return body.replace("__CAPS__", caps)


# ----------------------------------------------------------------------- PLAN


def _hub_paths(root):
    hub_root = os.path.join(root, "WAI-Harness", "hub")
    hub_local = os.path.join(hub_root, "local")
    return hub_root, hub_local


def plan(root, spoke_id, mode=None):
    """What would be created, and where. No side effects."""
    hub_root, hub_local = _hub_paths(root)
    creates = [
        os.path.join(hub_local, "hub-registry.json"),
        os.path.join(hub_local, "hub-profile.json"),
        os.path.join(hub_local, "capabilities.json"),
        os.path.join(hub_local, "teachings_repo", "spoke", "current", ".gitkeep"),
        os.path.join(hub_local, "teachings_repo", "cross_spoke", "current", ".gitkeep"),
        os.path.join(hub_local, "teachings_repo", "hub-only", "current", ".gitkeep"),
        os.path.join(hub_local, "pathgraph", "origin-transitions.jsonl"),
        os.path.join(hub_local, "hub-evolution.log"),
    ]
    updates = [
        f"{state_path(root, mode)} -- wheel.hub_path set to {hub_root}",
    ]
    return {
        "hub_root": hub_root,
        "registry_seeded_with": spoke_id,
        "capability_profile": "CORE (stdlib only -- complete, not crippled)",
        "creates": creates,
        "updates": updates,
    }


# --------------------------------------------------------------- INSTANTIATE


def _default_capabilities(now_iso):
    return {
        "_purpose": "Which control-plane features this wheel can run, and what "
                    "each one needs. Navigator owns this file (Ruling 11).",
        "profile": "CORE",
        "_profiles": {
            "CORE": "stdlib only -- complete, not crippled",
            "STANDARD": "CORE + LiteLLM / provider API keys",
            "FULL": "STANDARD + local models, hub MCP",
        },
        "features": {
            "registry": {
                "requires": [], "enhanced_by": [], "available": True,
                "description": "registry of record for every spoke of this wheel",
            },
            "capacity_allocation": {
                "requires": [], "enhanced_by": ["litellm"], "available": True,
                "description": "capacity allocation across spokes",
            },
            "provider_accounting": {
                "requires": [], "enhanced_by": ["litellm"], "available": True,
                "description": "provider usage accounting across spokes",
            },
            "cross_spoke_delivery": {
                "requires": [], "enhanced_by": [], "available": True,
                "description": "lug delivery between spokes via incoming/outgoing",
            },
            "local_models": {
                "requires": ["local model runtime"], "enhanced_by": [],
                "available": False,
                "description": "FULL profile only -- not present at CORE",
            },
            "hub_mcp": {
                "requires": ["hub MCP transport"], "enhanced_by": [],
                "available": False,
                "description": "FULL profile only -- not present at CORE",
            },
        },
        "instantiated_at": now_iso,
    }


def instantiate(root, spoke_id, spoke_path=None, spoke_name=None, mode=None,
                 apply=False, actor_model="unknown", actor_provider="unknown",
                 initiative_id=None, lug_id=None):
    """Create the wheel's home. Dry-run (returns what WOULD be written) unless
    apply=True. Refuses to overwrite an existing hub -- instantiate is a
    ONE-TIME event; a hub that already exists is not this function's problem."""
    existing = detect(root, mode)
    if existing["state"] == HUB_OK:
        return {
            "applied": False,
            "error": f"a hub already exists at {existing['hub_path']} -- refusing "
                     "to instantiate over it",
        }

    hub_root, hub_local = _hub_paths(root)
    now = _now()
    now_iso = _iso(now)
    spoke_path = spoke_path or os.path.abspath(root)

    registry = {
        "_purpose": "Hub project registry - tracks wheels connected to this hub",
        "_structure_version": "4.0",
        "metadata": {
            "created_at": now_iso,
            "last_updated_at": now_iso,
            "hub_fingerprint": None,
            "description": "Auto-managed registry of wheels known to this hub, "
                           "instantiated by wheel_home_init.py",
        },
        "wheels": [
            {
                "wheel_id": spoke_id,
                "spoke_id": spoke_id,
                "path": spoke_path,
                "type": "harness-home",
                "status": "active",
                "one_liner": spoke_name or f"First spoke of this wheel ({spoke_id})",
                "role": "master+hub",
                "registered_at": now_iso[:10],
                "note": "instantiated by wheel_home_init.py -- this wheel's own hub",
            }
        ],
        "teaching_history": [],
        "statistics": {
            "total_wheels": 1, "active_wheels": 1, "last_teach": None,
            "total_learnings_received": 0, "total_signals_received": 0,
        },
    }
    capabilities = _default_capabilities(now_iso)
    hub_profile = {
        "_purpose": "This wheel's hub-level profile.",
        "created_at": now_iso,
        "created_by": {"model": actor_model, "provider": actor_provider},
        "hub_config": {"hub_path": hub_root, "capability_profile": "CORE"},
    }
    transition = {
        "event": "wheel-home-instantiated",
        "at": now_iso,
        "creator": {"model": actor_model, "provider": actor_provider},
        "owner": spoke_id,
        "last_modifier": {"model": actor_model, "provider": actor_provider},
        "originating_spoke": spoke_id,
        "initiative_id": initiative_id,
        "parent_lug": lug_id,
        "hub_root": hub_root,
        "note": "Ozi explained benefit and need; the decision to instantiate was "
                "accepted; this wheel's home was created from that decision.",
    }

    result = {
        "hub_root": hub_root, "registry": registry, "capabilities": capabilities,
        "hub_profile": hub_profile, "transition": transition, "applied": False,
    }
    if not apply:
        return result

    os.makedirs(hub_local, exist_ok=True)
    for sub in ("teachings_repo/spoke/current", "teachings_repo/cross_spoke/current",
                "teachings_repo/hub-only/current", "pathgraph"):
        os.makedirs(os.path.join(hub_local, sub), exist_ok=True)
    for sub in ("teachings_repo/spoke/current", "teachings_repo/cross_spoke/current",
                "teachings_repo/hub-only/current"):
        open(os.path.join(hub_local, sub, ".gitkeep"), "a").close()

    for name, payload in (("hub-registry.json", registry),
                           ("capabilities.json", capabilities),
                           ("hub-profile.json", hub_profile)):
        with open(os.path.join(hub_local, name), "w") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")

    trans_path = os.path.join(hub_local, "pathgraph", "origin-transitions.jsonl")
    with open(trans_path, "a") as handle:
        handle.write(json.dumps(transition) + "\n")

    log_path = os.path.join(hub_local, "hub-evolution.log")
    with open(log_path, "a") as handle:
        handle.write(f"{now_iso} - Hub evolution log entry\n")
        handle.write("-" * 40 + "\n")
        handle.write("Event: wheel-home-instantiated\n")
        handle.write(f"Originating spoke: {spoke_id}\n")
        handle.write(f"Created by: {actor_model} / {actor_provider}\n")
        handle.write("Status: Complete\n\n")

    sp = state_path(root, mode)
    state = _read_json(sp, {}) or {}
    wheel = state.get("wheel")
    if not isinstance(wheel, dict):
        wheel = {}
        state["wheel"] = wheel
    wheel["hub_path"] = hub_root
    with open(sp, "w") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")

    # Instantiating clears any earlier decline record -- the wheel now has a
    # home, so a stale "declined" marker must not keep telling the wakeup
    # surface capabilities are unavailable that are now, in fact, available.
    dp = decision_path(root, mode)
    if os.path.exists(dp):
        os.remove(dp)

    result["applied"] = True
    result["written"] = {
        "hub_local": hub_local, "state_path": sp,
        "transitions_path": trans_path, "log_path": log_path,
    }
    return result


# -------------------------------------------------------------------- DECLINE


def decline(root, mode=None, capabilities=None, apply=False):
    """Record declining as a SUPPORTED, visible outcome -- not an error."""
    names = capabilities or [c["name"] for c in CAPABILITIES_LOST_WITHOUT_HUB]
    record = {
        "decision": "declined",
        "at": _iso(_now()),
        "capabilities_unavailable": names,
    }
    if not apply:
        return record
    base = base_dir(root, mode)
    os.makedirs(os.path.join(base, "runtime"), exist_ok=True)
    path = decision_path(root, mode)
    with open(path, "w") as handle:
        json.dump(record, handle, indent=2)
        handle.write("\n")
    record["written_to"] = path
    return record


def read_decision(root, mode=None):
    return _read_json(decision_path(root, mode))


# --------------------------------------------------------------------- STATUS


def status(root, mode=None):
    d = detect(root, mode)
    if d["state"] == HUB_OK:
        return {"state": HUB_OK, "detail": d}
    decision = read_decision(root, mode)
    if isinstance(decision, dict) and decision.get("decision") == "declined":
        return {"state": "DECLINED", "detail": d, "decision": decision}
    return {"state": "UNDECIDED", "detail": d}


# --------------------------------------------------------------- WAKEUP LINE


def wakeup_surface(root, mode=None):
    """What a warmup ceremony should show, either way. This is the function the
    live SessionStart hook (wakeup-canonical.sh) calls -- see its "Wheel home"
    section. `show=False` when a hub is reachable (nothing to say); otherwise
    `lines` is ready to print verbatim and `state` distinguishes an operator who
    has already declined (quiet reminder, capabilities named) from one who has
    never been asked (the advised-decision prompt)."""
    s = status(root, mode)
    if s["state"] == HUB_OK:
        return {"show": False, "state": HUB_OK, "lines": []}
    if s["state"] == "DECLINED":
        caps = ", ".join(s["decision"].get("capabilities_unavailable") or [])
        lines = [
            "  Wheel home: none (declined) -- unavailable: " + caps,
            "    Reconsider: python3 WAI-Harness/spoke/managed/tools/"
            "wheel_home_init.py --root . instantiate --spoke-id <id> --apply",
        ]
        return {"show": True, "state": "DECLINED", "lines": lines}
    lines = [
        "  Wheel home: NOT YET CREATED -- this wheel has no hub "
        f"({s['detail']['reason']}).",
        "    Ozi should explain before acting: python3 WAI-Harness/spoke/managed/"
        "tools/wheel_home_init.py --root . explain",
        "    Then either instantiate (--apply) or decline (--apply) -- see that "
        "tool's --help.",
    ]
    return {"show": True, "state": "UNDECIDED", "lines": lines}


# ------------------------------------------------------------------------ CLI


def _main(argv=None):
    # Two-tier flag setup (same fix as warmup.py's _main -- see its comment):
    # `top` carries the REAL defaults and is parsed at the top level, so
    # `--root X detect` and `detect --root X` both work. `common` is attached
    # to every subparser with default=SUPPRESS, so a subcommand that does NOT
    # repeat --root/--mode/--json never re-applies "." over a value the top
    # level already set -- without SUPPRESS here, argparse silently resets
    # --root to "." on every call shaped like `--root X detect`, which is the
    # exact form a caller (and this file's own docstring) uses everywhere.
    top = argparse.ArgumentParser(add_help=False)
    top.add_argument("--root", default=".")
    top.add_argument("--mode", default=None)
    top.add_argument("--json", action="store_true")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS)
    common.add_argument("--mode", default=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], parents=[top])
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("detect", parents=[common])
    sub.add_parser("explain", parents=[common])

    p_plan = sub.add_parser("plan", parents=[common])
    p_plan.add_argument("--spoke-id", required=True)

    p_inst = sub.add_parser("instantiate", parents=[common])
    p_inst.add_argument("--spoke-id", required=True)
    p_inst.add_argument("--spoke-name", default=None)
    p_inst.add_argument("--spoke-path", default=None)
    p_inst.add_argument("--apply", action="store_true")
    p_inst.add_argument("--model", default="unknown")
    p_inst.add_argument("--provider", default="unknown")
    p_inst.add_argument("--initiative-id", default=None)
    p_inst.add_argument("--lug-id", default=None)

    p_dec = sub.add_parser("decline", parents=[common])
    p_dec.add_argument("--apply", action="store_true")

    sub.add_parser("status", parents=[common])
    sub.add_parser("wakeup-line", parents=[common])

    args = parser.parse_args(argv)

    if args.cmd == "detect":
        out = detect(args.root, args.mode)
        print(json.dumps(out, indent=2) if args.json else
              f"{out['state']}: {out['reason']}")
        return 0

    if args.cmd == "explain":
        print(explain())
        return 0

    if args.cmd == "plan":
        out = plan(args.root, args.spoke_id, args.mode)
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(f"Would create hub at: {out['hub_root']}")
            for c in out["creates"]:
                print(f"  + {c}")
            for u in out["updates"]:
                print(f"  ~ {u}")
        return 0

    if args.cmd == "instantiate":
        out = instantiate(
            args.root, args.spoke_id, spoke_path=args.spoke_path,
            spoke_name=args.spoke_name, mode=args.mode, apply=args.apply,
            actor_model=args.model, actor_provider=args.provider,
            initiative_id=args.initiative_id, lug_id=args.lug_id,
        )
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            if out.get("error"):
                print(f"REFUSED: {out['error']}")
            elif out["applied"]:
                print(f"Instantiated wheel home at {out['hub_root']}")
                for k, v in out["written"].items():
                    print(f"  {k}: {v}")
            else:
                print(f"DRY RUN -- would instantiate wheel home at {out['hub_root']} "
                      "(pass --apply to write)")
        return 1 if out.get("error") else 0

    if args.cmd == "decline":
        out = decline(args.root, args.mode, apply=args.apply)
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print("Declined -- unavailable capabilities: " +
                  ", ".join(out["capabilities_unavailable"]))
            if out.get("written_to"):
                print(f"  recorded at {out['written_to']}")
            elif not args.apply:
                print("  DRY RUN -- pass --apply to record this decision")
        return 0

    if args.cmd == "status":
        out = status(args.root, args.mode)
        print(json.dumps(out, indent=2) if args.json else
              f"{out['state']}")
        return 0

    if args.cmd == "wakeup-line":
        out = wakeup_surface(args.root, args.mode)
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            for line in out["lines"]:
                print(line)
        return 0

    return 0  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(_main())
