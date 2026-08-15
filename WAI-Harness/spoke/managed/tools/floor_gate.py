#!/usr/bin/env python3
"""floor_gate.py -- no new functionality is built on a floor nobody has established.

W3 of the LOW TRUST tenet (spec-low-trust-tenet-v1). W1 (trust_epoch) says what is
trusted. W2 (warmup) establishes the floor. Neither of them stops anything. This
does, and it is the only file in the set that converts the tenet from a description
into a constraint.

THE RULE. A lug that ADDS capability may not be dispatched while the spoke's floor
is anything other than ESTABLISHED and in-date. A lug that BUILDS THE FLOOR always
may, no matter how bad the floor is.

WHY THE SECOND HALF IS NOT A LOOPHOLE -- it is the reason the gate survives. A gate
that blocks everything on a spoke with no floor also blocks the work that would
create the floor. That spoke is bricked, someone disables the gate at 2am, and the
tenet dies of usefulness. So the gate is directional: it never blocks the path out.

    BUILD       impl, feature, epic, spec-of-new-behaviour   -> BLOCKED off-floor
    FLOOR_WORK  fix, bug, test, chore, audit, trust/warmup/  -> ALWAYS allowed
                certification/assurance work by id or tag
    NEUTRAL     notation, signal, report, task, question     -> allowed

OVERRIDE IS RECORDED, NEVER SILENT. There is an escape hatch, because a gate with
no hatch is a gate that gets deleted rather than obeyed. Every override writes a row
to override-ledger.jsonl with a mandatory reason, and the count is surfaced in the
floor status. An override rate is a measurement of how well the floor matches
reality -- a spoke overriding constantly does not have a strict gate, it has a wrong
floor, and the ledger is how that becomes visible instead of folklore.

WHAT THIS GATE DOES NOT DO. It does not judge whether the work is good, correct, or
wanted. It answers exactly one question -- is there a proven floor under this? --
and refuses to answer any other, because a gate that grows opinions becomes a thing
people route around.

CLI:
    floor_gate.py --root DIR check LUG.json [--json]
    floor_gate.py --root DIR check-all [--dir PATH] [--json]
    floor_gate.py --root DIR override LUG_ID --reason TEXT
    floor_gate.py --root DIR ledger [--json]

Exit codes: 0 allowed, 1 blocked, 2 floor unknown/stale (also blocked -- but a
different reason, and the caller is told which).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import trust_epoch as te
import warmup as wu


LEDGER_FILE = "override-ledger.jsonl"

ALLOWED = "ALLOWED"
BLOCKED = "BLOCKED"

BUILD = "BUILD"
FLOOR_WORK = "FLOOR_WORK"
NEUTRAL = "NEUTRAL"

BUILD_TYPES = {"impl", "feature", "epic", "implement", "implementation"}
FLOOR_TYPES = {"fix", "bug", "test", "chore", "audit", "hygiene", "recert",
               "certification", "assurance", "warmup"}
# An id or tag containing any of these means the lug's purpose IS the floor.
FLOOR_MARKERS = ("trust", "warmup", "floor", "certif", "assurance", "recert",
                 "verify", "oracle", "audit", "hygiene")


def _now():
    return datetime.now(timezone.utc)


def ledger_path(root, mode=None):
    return os.path.join(te.base_dir(root, mode), te.TRUST_DIR, LEDGER_FILE)


def read_ledger(root, mode=None):
    path = ledger_path(root, mode)
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def overridden_ids(root, mode=None):
    return {row.get("lug_id") for row in read_ledger(root, mode) if row.get("lug_id")}


def override(root, lug_id, reason, mode=None, actor=None):
    """Record an override. A reason is mandatory -- an unexplained override is a
    silent failure wearing a permission slip."""
    if not reason or not str(reason).strip():
        raise ValueError("override requires a reason")
    path = ledger_path(root, mode)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    row = {
        "lug_id": lug_id,
        "reason": str(reason).strip(),
        "actor": actor or os.environ.get("USER") or "unknown",
        "at": te._iso(_now()),
        "floor_verdict_at_override": wu.status(root, mode).get("verdict"),
    }
    with open(path, "a") as handle:
        handle.write(json.dumps(row) + "\n")
    return row


def classify_work(lug):
    """BUILD / FLOOR_WORK / NEUTRAL. Floor markers win over the type.

    An `impl` lug whose whole subject is the certification gate is floor work, and
    typing it BUILD would deadlock exactly the spokes that most need to escape.
    """
    text = " ".join(str(lug.get(k, "")) for k in ("id", "title")).lower()
    tags = [str(t).lower() for t in (lug.get("tags") or [])]
    if any(m in text for m in FLOOR_MARKERS) or any(
            m in t for t in tags for m in FLOOR_MARKERS):
        return FLOOR_WORK
    ltype = str(lug.get("type", "")).lower()
    if ltype in FLOOR_TYPES:
        return FLOOR_WORK
    if ltype in BUILD_TYPES:
        return BUILD
    return NEUTRAL


def check(root, lug, mode=None, floor=None):
    """Rule on one lug. Pure -- writes nothing, dispatches nothing."""
    floor = floor if floor is not None else wu.status(root, mode)
    lug_id = lug.get("id", "<unidentified>")
    work = classify_work(lug)

    if work != BUILD:
        return {
            "lug_id": lug_id, "work_class": work, "disposition": ALLOWED,
            "floor_verdict": floor["verdict"],
            "reason": f"{work} is never blocked -- the gate must not block the path out",
        }

    if floor.get("cleared_to_build"):
        return {
            "lug_id": lug_id, "work_class": work, "disposition": ALLOWED,
            "floor_verdict": floor["verdict"],
            "reason": f"floor {floor['verdict']} and in date",
        }

    if lug_id in overridden_ids(root, mode):
        return {
            "lug_id": lug_id, "work_class": work, "disposition": ALLOWED,
            "floor_verdict": floor["verdict"], "overridden": True,
            "reason": "recorded override in override-ledger.jsonl",
        }

    gaps = floor.get("delta") or []
    remedy = (f"run warmup and close: {', '.join(g['id'] for g in gaps)}"
              if gaps else "run: warmup.py --root . run --apply")
    return {
        "lug_id": lug_id, "work_class": work, "disposition": BLOCKED,
        "floor_verdict": floor["verdict"],
        "reason": f"floor is {floor['verdict']} -- {floor.get('reason', '')}".strip(),
        "remedy": remedy,
    }


def check_all(root, lug_dir=None, mode=None):
    floor = wu.status(root, mode)
    if lug_dir:
        paths = sorted(glob.glob(os.path.join(lug_dir, "*.json")))
    else:
        paths = sorted(glob.glob(os.path.join(
            te.base_dir(root, mode), "lugs", "bytype", "*", "open", "*.json")))
    rulings = []
    for path in paths:
        try:
            with open(path) as handle:
                lug = json.load(handle)
        except (OSError, ValueError):
            continue
        if not isinstance(lug, dict):
            continue
        ruling = check(root, lug, mode, floor=floor)
        ruling["path"] = path
        rulings.append(ruling)
    blocked = [r for r in rulings if r["disposition"] == BLOCKED]
    return {
        "floor_verdict": floor["verdict"],
        "cleared_to_build": bool(floor.get("cleared_to_build")),
        "total": len(rulings),
        "blocked": len(blocked),
        "allowed": len(rulings) - len(blocked),
        "by_class": {
            k: sum(1 for r in rulings if r["work_class"] == k)
            for k in (BUILD, FLOOR_WORK, NEUTRAL)
        },
        "override_count": len(read_ledger(root, mode)),
        "rulings": rulings,
    }


def _exit_for(floor_verdict, disposition):
    if disposition == ALLOWED:
        return 0
    return 2 if floor_verdict in (wu.UNKNOWN, wu.EMPTY) else 1


def _main(argv=None):
    # Global flags accepted before OR after the subcommand. The sub-level copy uses
    # SUPPRESS so it cannot re-default --root back to "." over an explicit value.
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

    p_check = sub.add_parser("check", parents=[common])
    p_check.add_argument("lug")

    p_all = sub.add_parser("check-all", parents=[common])
    p_all.add_argument("--dir", default=None)

    p_over = sub.add_parser("override", parents=[common])
    p_over.add_argument("lug_id")
    p_over.add_argument("--reason", required=True)

    sub.add_parser("ledger", parents=[common])
    args = parser.parse_args(argv)

    if args.cmd == "check":
        with open(args.lug) as handle:
            lug = json.load(handle)
        ruling = check(args.root, lug, args.mode)
        if args.json:
            print(json.dumps(ruling, indent=2))
        else:
            print(f"{ruling['disposition']}: {ruling['lug_id']} [{ruling['work_class']}]")
            print(f"  {ruling['reason']}")
            if ruling.get("remedy"):
                print(f"  remedy: {ruling['remedy']}")
        return _exit_for(ruling["floor_verdict"], ruling["disposition"])

    if args.cmd == "check-all":
        out = check_all(args.root, args.dir, args.mode)
        if args.json:
            payload = dict(out)
            payload.pop("rulings", None)
            print(json.dumps(payload, indent=2))
        else:
            print(f"floor {out['floor_verdict']} | {out['total']} open | "
                  f"{out['blocked']} BLOCKED | {out['allowed']} allowed")
            print(f"  build {out['by_class'][BUILD]} | floor-work "
                  f"{out['by_class'][FLOOR_WORK]} | neutral {out['by_class'][NEUTRAL]}")
            if out["override_count"]:
                print(f"  ! {out['override_count']} recorded override(s)")
        if out["blocked"] == 0:
            return 0
        return 2 if out["floor_verdict"] in (wu.UNKNOWN, wu.EMPTY) else 1

    if args.cmd == "override":
        row = override(args.root, args.lug_id, args.reason, args.mode)
        print(json.dumps(row, indent=2) if args.json else
              f"override recorded for {row['lug_id']}: {row['reason']}")
        return 0

    rows = read_ledger(args.root, args.mode)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{len(rows)} recorded override(s)")
        for row in rows:
            print(f"  {row.get('at')}  {row.get('lug_id')}  {row.get('reason')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
