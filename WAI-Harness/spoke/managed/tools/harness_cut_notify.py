#!/usr/bin/env python3
"""harness_cut_notify.py — when mywheel cuts a new harness version, let the group decide
where it goes.

THE RELOCATION (operator, 2026-07-22): "mywheel could have a natural place as the hub and
harness distributor — cutting a new version it should know where to push, apply it, and
which spokes to ignore, wait for a pull. Relocate some logic to this mechanism."

Before this, the "where does a cut go" decision was scattered: the nightly sweep, the AP
round's round-1 pull, the hand-run fleet sweep — each answered it its own way, and one of
them reached client sites. This makes the GROUP CONTRACT the single answerer. A cut fires
`harness_version_cut` into the propagation engine, which already knows the members, their
roles, the authority waterfall, and (crucially) fleet-scope. What comes back is the
distribution PLAN:

  APPLY      in-scope members behind the cut whose policy is push -> the distributor is
             directed (via the engine's reaction lug) to deliver.
  WAIT-PULL  in-scope members whose per-spoke policy defers to self-pull at SessionStart
             (production_gate / wait_for_pull) -> left alone; they pull themselves.
  IGNORE     out-of-scope members (client work, inactive, deprecated) -> never touched.

It only fires when VERSION actually changed since the last cut it propagated (recorded in
the group activity log), so re-running after an ordinary MANIFEST recut is a safe no-op —
this is NOT wired to fire on every recut, only a real new cut.

    harness_cut_notify.py plan                 # show the plan, fire nothing
    harness_cut_notify.py notify [--force]      # fire the cut into the engine (idempotent)
"""
from __future__ import annotations

import argparse
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


def current_version() -> str | None:
    try:
        return (_master() / "VERSION").read_text().strip()
    except OSError:
        return None


def _registry() -> list:
    try:
        return json.loads((_master() / "hub" / "local" / "hub-registry.json").read_text()).get("wheels", [])
    except (OSError, ValueError):
        return []


def _member_version(path: str) -> str | None:
    try:
        return (Path(path) / "WAI-Harness" / "VERSION").read_text().strip()
    except OSError:
        return None


def _policy(wheel: dict) -> str:
    """push | wait-pull, from the operator-owned per-spoke policy layer."""
    pol = wheel.get("policy") or {}
    # production sites and explicit wait_for_pull defer to their own SessionStart pull.
    if pol.get("production_gate") or pol.get("ap_mode") == "off" or pol.get("wait_for_pull"):
        return "wait-pull"
    return "push"


def plan(version: str | None = None) -> dict:
    import propagation_engine as pe
    import fleet_scope
    version = version or current_version()
    registry = _registry()
    reg_by_id = {w.get("wheel_id"): w for w in registry}
    policy_pol = fleet_scope.load_policy()

    # Ask the engine (dry-run) who reacts to the cut — that is the in-scope, role-matched set.
    fired = pe.fire("harness_version_cut", "mywheel", version=version, dry_run=True)
    # The engine returns the distributor reaction(s); expand the distribution target set to
    # every in-scope member that is BEHIND the cut, classified by policy.
    apply_now, wait_pull, ignore = [], [], []
    groups = pe.load_groups()
    member_ids = set()
    for g in groups.get("groups", []):
        if "mywheel" in {m.get("wheel_id") for m in g.get("members", [])}:
            member_ids |= {m.get("wheel_id") for m in g.get("members", [])}
    for wid in sorted(member_ids):
        if wid == "mywheel":
            continue
        w = reg_by_id.get(wid)
        if not w:
            continue
        path = w.get("path", "")
        in_scope = fleet_scope.exclusion_reason(path, wid, policy_pol) is None
        mv = _member_version(path)
        behind = mv != version
        if not in_scope:
            ignore.append({"wheel_id": wid, "reason": "out of scope (client/inactive/deprecated)"})
        elif not behind:
            pass  # already current — nothing to do, not a distribution target
        elif _policy(w) == "wait-pull":
            wait_pull.append({"wheel_id": wid, "at": mv})
        else:
            apply_now.append({"wheel_id": wid, "at": mv})
    # Registry-wide ignore view: spokes that exist but are NOT in any of mywheel's
    # distribution groups are implicitly out of the cut's reach — the operator's "which
    # spokes to ignore." This is where the client sites and inactive spokes live, and why
    # a group-driven cut can never reach them (unlike the raw fleet sweep that once did).
    not_in_my_groups = []
    for w in registry:
        wid = w.get("wheel_id")
        if wid and wid != "mywheel" and wid not in member_ids:
            not_in_my_groups.append({"wheel_id": wid, "reason": "not in any mywheel distribution group"})
    return {"version": version, "engine_reactions": fired["reactions"],
            "apply_now": apply_now, "wait_pull": wait_pull, "ignore": ignore,
            "outside_groups": not_in_my_groups}


def last_propagated_version() -> str | None:
    import propagation_engine as pe
    log = pe._activity_log_path()
    if not log.exists():
        return None
    latest = None
    try:
        for line in log.read_text().splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("event") == "harness_version_cut" and r.get("version"):
                latest = r.get("version")
    except OSError:
        pass
    return latest


def render_plan(p: dict) -> str:
    out = [f"{B}HARNESS CUT {p['version']}{OFF} — group distribution plan"]
    out.append(f"  {G}APPLY (push, behind, in-scope):{OFF} "
               + (", ".join(f"{a['wheel_id']}({a['at']})" for a in p["apply_now"]) or "none"))
    out.append(f"  {Y}WAIT-PULL (self-heals at SessionStart):{OFF} "
               + (", ".join(w["wheel_id"] for w in p["wait_pull"]) or "none"))
    out.append(f"  {DIM}IGNORE (out of scope): "
               + (", ".join(i["wheel_id"] for i in p["ignore"]) or "none") + OFF)
    outside = p.get("outside_groups") or []
    if outside:
        names = ", ".join(i["wheel_id"] for i in outside[:12])
        more = f" +{len(outside)-12}" if len(outside) > 12 else ""
        out.append(f"  {DIM}OUTSIDE mywheel's groups (unreachable by a cut): {names}{more}{OFF}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    n = sub.add_parser("notify")
    n.add_argument("--force", action="store_true", help="fire even if VERSION is unchanged since last propagation")
    n.add_argument("--now", default=None)
    args = ap.parse_args()

    ver = current_version()
    if args.cmd == "plan":
        print(render_plan(plan(ver)))
        return 0

    # notify
    import propagation_engine as pe
    last = last_propagated_version()
    if not args.force and last == ver:
        print(f"harness_cut_notify: {ver} already propagated (last={last}); no-op. Use --force to re-fire.")
        return 0
    res = pe.fire("harness_version_cut", "mywheel", version=ver, dry_run=False, now_iso=args.now)
    print(render_plan(plan(ver)))
    print()
    print(pe.render_fire(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
