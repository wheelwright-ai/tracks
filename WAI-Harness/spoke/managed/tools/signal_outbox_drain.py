#!/usr/bin/env python3
"""Consume the hub signal outbox — the hop that was never built.

WHY THIS EXISTS
---------------
`WAI-Harness/hub/WAI-Hub/signals/outbox/` had three writers and NO reader.
Measured 2026-08-16: 18 signals, oldest 2026-06-26 (~7 weeks), `processed/`
empty, and a grep for any reader of `signals/outbox` across the whole harness
returned zero hits. Writers are ozi_autopilot.py (routes uncleared signals
there), wheel-tender.sh, and hub deliver_patterns.py.

So the signal loop produced records nobody consumed. A recurring conductor
harness-gap signal could fire five times and reach no one — the produce hop
worked, the deliver hop did not exist, and nothing reported the gap because an
outbox that only grows looks exactly like an outbox that is keeping up.

THE CONTRACT (decided from what is actually in there, not invented)
-------------------------------------------------------------------
Measured routing of the 18-signal backlog:

    SPOKE/<id>   12   addressed to a specific spoke  -> DELIVER to its inbox
    SIGNAL        3   hub-scoped                     -> DELIVER to hub inbox
    FRAMEWORK     3   framework is deprecated        -> DELIVER to the curator

Twelve of eighteen name a destination spoke, so this is a DELIVERY queue, not
an operator review queue. Delivered signals move to `processed/` with a
`_delivery` stamp, which is also what makes the drain idempotent.

SAFETY
------
Dry-run is the DEFAULT. Nothing moves without --apply. That is deliberate: the
first run of a consumer against a seven-week backlog is exactly where a bad
resolver would scatter 18 files into wrong inboxes, and there is no reader to
notice. Delivery copies first and only then moves the source, so an interrupted
run duplicates rather than loses.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

CURATOR = "mywheel"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_registry(hub_root: Path) -> dict:
    """wheel_id -> repo path, from the hub registry when one is present."""
    out: dict[str, str] = {}
    reg = hub_root / "local" / "hub-registry.json"
    if not reg.is_file():
        return out
    try:
        data = json.loads(reg.read_text())
    except Exception:
        return out
    for w in data.get("wheels", []) or []:
        wid, path = w.get("wheel_id"), w.get("path")
        if wid and path:
            out[wid] = path
    return out


def resolve_spoke_root(wheel_id: str, registry: dict, repo_root: Path) -> Path | None:
    """Where does <wheel_id> live?

    Registry first, then the conventional sibling layout. Returns None rather
    than guessing — an unresolvable destination must leave the signal in the
    outbox, because a signal delivered to the wrong spoke is worse than one
    still waiting.
    """
    if wheel_id in registry:
        p = Path(registry[wheel_id]).expanduser()
        if p.is_dir():
            return p
    if wheel_id == CURATOR and repo_root.is_dir():
        return repo_root
    for parent in (repo_root.parent, repo_root.parent.parent):
        cand = parent / wheel_id
        if cand.is_dir() and (cand / "WAI-Harness").is_dir():
            return cand
    return None


def destination_for(sig: dict, hub_root: Path, registry: dict, repo_root: Path):
    """(kind, directory, note) for one signal, or (kind, None, why-not)."""
    routed = str(sig.get("routed_to") or "").strip()

    if routed.upper().startswith("SPOKE/"):
        wheel_id = routed.split("/", 1)[1].strip()
        root = resolve_spoke_root(wheel_id, registry, repo_root)
        if root is None:
            return ("spoke", None, f"unresolvable spoke '{wheel_id}'")
        return ("spoke", root / "WAI-Harness" / "spoke" / "local" / "lugs" / "incoming",
                f"spoke {wheel_id}")

    if routed.upper() == "SIGNAL":
        # SIGNAL means deliver to the hub inbox. It has been mistaken for "skip"
        # before; it is not a no-op routing.
        return ("hub", hub_root / "WAI-Hub" / "signals" / "inbox", "hub inbox")

    if routed.upper() == "FRAMEWORK":
        # The framework wheel is deprecated; the curator absorbed its role, so
        # FRAMEWORK-routed signals go to the curator rather than nowhere.
        root = resolve_spoke_root(CURATOR, registry, repo_root)
        if root is None:
            return ("framework", None, "curator unresolvable")
        return ("framework", root / "WAI-Harness" / "spoke" / "local" / "lugs" / "incoming",
                f"curator {CURATOR} (FRAMEWORK deprecated)")

    return ("unknown", None, f"unrecognised routed_to {routed!r}")


def drain(hub_root: Path, repo_root: Path, apply: bool) -> dict:
    outbox = hub_root / "WAI-Hub" / "signals" / "outbox"
    processed = hub_root / "WAI-Hub" / "signals" / "processed"
    registry = _load_registry(hub_root)

    report = {"scanned": 0, "delivered": 0, "skipped": 0, "apply": apply, "items": []}
    if not outbox.is_dir():
        report["error"] = f"no outbox at {outbox}"
        return report

    for path in sorted(outbox.glob("*.json")):
        report["scanned"] += 1
        row = {"file": path.name}
        try:
            sig = json.loads(path.read_text())
        except Exception as e:
            row.update(action="skip", why=f"unparseable: {e}")
            report["skipped"] += 1
            report["items"].append(row)
            continue

        kind, dest, note = destination_for(sig, hub_root, registry, repo_root)
        row.update(id=sig.get("id") or path.stem, routed_to=sig.get("routed_to"),
                   kind=kind, note=note)

        if dest is None:
            row.update(action="skip", why=note)
            report["skipped"] += 1
            report["items"].append(row)
            continue

        row["dest"] = str(dest)
        if not apply:
            row["action"] = "would-deliver"
            report["delivered"] += 1
            report["items"].append(row)
            continue

        try:
            dest.mkdir(parents=True, exist_ok=True)
            processed.mkdir(parents=True, exist_ok=True)
            sig.setdefault("_delivery", {})
            sig["_delivery"] = {"delivered_at": _now(), "by": "signal_outbox_drain",
                                "to": str(dest), "routed_to": sig.get("routed_to")}
            # Write the destination copy BEFORE removing the source, so an
            # interrupted run leaves a duplicate rather than a hole.
            (dest / path.name).write_text(json.dumps(sig, indent=2))
            shutil.move(str(path), str(processed / path.name))
            row["action"] = "delivered"
            report["delivered"] += 1
        except Exception as e:
            row.update(action="skip", why=f"delivery failed: {e}")
            report["skipped"] += 1
        report["items"].append(row)

    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hub-root", default=None,
                    help="path to WAI-Harness/hub (default: resolved from this file)")
    ap.add_argument("--repo-root", default=None)
    ap.add_argument("--apply", action="store_true",
                    help="actually deliver; without this it is a dry run")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    here = Path(__file__).resolve()
    repo_root = Path(args.repo_root).expanduser() if args.repo_root \
        else here.parents[4]
    hub_root = Path(args.hub_root).expanduser() if args.hub_root \
        else repo_root / "WAI-Harness" / "hub"

    report = drain(hub_root, repo_root, args.apply)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if not report.get("error") else 1

    if report.get("error"):
        print(f"[signal_outbox_drain] {report['error']}", file=sys.stderr)
        return 1

    mode = "APPLIED" if args.apply else "DRY RUN (use --apply to deliver)"
    print(f"[signal_outbox_drain] {mode}")
    for row in report["items"]:
        act = row.get("action", "?")
        mark = {"delivered": "->", "would-deliver": " ~", "skip": " !"}.get(act, "  ")
        print(f"  {mark} {row.get('id', row['file'])[:64]}")
        print(f"      routed_to={row.get('routed_to')}  {row.get('note') or row.get('why','')}")
    print(f"  scanned={report['scanned']}  "
          f"{'delivered' if args.apply else 'deliverable'}={report['delivered']}  "
          f"skipped={report['skipped']}")
    # A skip is not a failure of the run, but it IS unfinished business — the
    # whole reason this file exists is that unread things went unreported.
    return 0


if __name__ == "__main__":
    sys.exit(main())
