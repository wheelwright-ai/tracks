#!/usr/bin/env python3
"""fleet_scope.py — which spokes may automation touch?

THE HOLE THIS FILLS (operator directive, restated 2026-07-22)
"we need to lock in what spokes to do this on. I've asked to not do client/ folder
projects or inactive projects before. You are wasting time and effort on them and
in fact it's disruptive to auto deploy to them."

Every fan-out tool answered that question for itself. core_ap_run.sh read
core-projects.json (correct, 10 spokes). `basher doctor --all` walked the whole
hub registry and touched 33 — including six live client sites. The upgrade sweep
carried a hand-typed list. Three answers, one of them harmful.

This is the single answer. The policy lives in DATA
(hub/local/registry/fleet-scope.json) so the operator moves one line to change
what automation may reach; this module is only the reader.

CLIENT WORK IS NEVER IN SCOPE BY DEFAULT. A push to a client repo deploys a live
site. An explicit per-invocation opt-in (--allow) exists for the case the operator
names a client spoke himself, and it is deliberately noisy about what it allowed.

    python3 fleet_scope.py --list                  in-scope wheel_ids + paths
    python3 fleet_scope.py --list --paths-only     one path per line (shell-friendly)
    python3 fleet_scope.py --check <path>          exit 0 in scope, 1 out of scope
    python3 fleet_scope.py --why <path>            print the reason it is excluded
    python3 fleet_scope.py --list --allow hines    include otherwise-excluded matches
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_DEFAULT_MASTER = Path("/home/mario/projects/wheelwright/mywheel/WAI-Harness")


def _hub_local(master: Path | None = None) -> Path:
    m = master or Path(os.environ.get("WAI_HARNESS_MASTER", str(_DEFAULT_MASTER)))
    return m / "hub" / "local"


def load_policy(master: Path | None = None) -> dict:
    p = _hub_local(master) / "registry" / "fleet-scope.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # No policy file: fail CLOSED on the one rule that can cause damage.
        return {"exclude_path_patterns": ["/client-work/", "/_archive/"],
                "exclude_paths": [], "inactive": [], "active": [],
                "_degraded": "fleet-scope.json unreadable — client-work still excluded"}


def load_registry(master: Path | None = None) -> list:
    p = _hub_local(master) / "hub-registry.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("wheels", []) or []
    except (OSError, json.JSONDecodeError):
        return []


def exclusion_reason(path: str, wheel_id: str, policy: dict, allow: list | None = None) -> str | None:
    """Return why this spoke is out of scope, or None if it is in scope."""
    allow = allow or []
    norm = str(path).rstrip("/")
    if any(a and (a in norm or a == wheel_id) for a in allow):
        return None                                    # explicit per-run opt-in
    if wheel_id and wheel_id in (policy.get("active") or []):
        # Active wins over the inactive list, but NEVER over a path exclusion:
        # a client site named in active[] would still be a live deploy target.
        pass
    for pat in policy.get("exclude_path_patterns") or []:
        if pat in norm + "/":
            return f"path matches excluded pattern {pat!r}: " + str(
                (policy.get("exclude_reasons") or {}).get(pat, "excluded by policy"))
    for ex in policy.get("exclude_paths") or []:
        if norm == str(ex).rstrip("/"):
            return f"excluded path: " + str(
                (policy.get("exclude_reasons") or {}).get(ex, "excluded by policy"))
    if wheel_id and wheel_id in (policy.get("inactive") or []):
        return "listed inactive in fleet-scope.json (move it out of inactive[] to re-enable)"
    active = policy.get("active") or []
    if active and wheel_id and wheel_id not in active:
        return "not listed in fleet-scope.json active[]"
    return None


def in_scope(master: Path | None = None, allow: list | None = None) -> list:
    policy = load_policy(master)
    out = []
    for w in load_registry(master):
        path, wid = w.get("path", ""), w.get("wheel_id", "")
        if not path:
            continue
        if exclusion_reason(path, wid, policy, allow) is None:
            out.append({"wheel_id": wid, "path": path})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--paths-only", action="store_true")
    ap.add_argument("--check", metavar="PATH")
    ap.add_argument("--why", metavar="PATH")
    ap.add_argument("--allow", action="append", default=[],
                    help="wheel_id or path fragment to admit despite policy (per-invocation)")
    ap.add_argument("--master", default=None)
    args = ap.parse_args()
    master = Path(args.master) if args.master else None

    if args.check or args.why:
        target = str(Path(args.check or args.why).resolve())
        policy = load_policy(master)
        wid = next((w.get("wheel_id", "") for w in load_registry(master)
                    if str(w.get("path", "")).rstrip("/") == target.rstrip("/")), "")
        reason = exclusion_reason(target, wid, policy, args.allow)
        if args.why:
            print(reason or f"IN SCOPE ({wid or 'unregistered'})")
        return 1 if reason else 0

    rows = in_scope(master, args.allow)
    if args.paths_only:
        for r in rows:
            print(r["path"])
    else:
        for r in rows:
            print(f"{r['wheel_id']:<32} {r['path']}")
        if args.allow:
            print(f"\n[fleet_scope] --allow admitted: {', '.join(args.allow)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
