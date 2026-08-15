#!/usr/bin/env python3
"""commitment_register.py -- the answer to "you will forget and we will never return".

W7 of the LOW TRUST tenet (spec-low-trust-tenet-v1).

THE OPERATOR'S OBJECTION, VERBATIM, 2026-08-02: "im of course concerned we wont
finish it - you will forget and we will never return to it to verify its impact and
evolve it."

He is right, and the correct response is not a promise. An agent promising to
remember is a control that depends on the agent complying, which corollary C1 of
this tenet already rules is not a control at all. The register is the structural
answer instead.

WHY A LUG WAS NOT ENOUGH. This spoke holds 952 open lugs. Anything filed there is
technically remembered and practically gone -- 359 of them are waiting on the
operator and the top of that queue has not moved in weeks. A commitment dropped into
a 952-item backlog has been forgotten in every sense that matters; it merely leaves
a body. The register is deliberately TINY, separate, and rendered unconditionally.

FOUR PROPERTIES, each closing one way commitments die:

  1. NAMED AND FEW. A commitment is a sentence, an owner, and a landing condition.
     If the register grows past a couple of dozen it has become a backlog and has
     stopped working; `check` says so rather than quietly scaling.

  2. MACHINE-LANDED. Every commitment carries a condition a machine can evaluate --
     the same landing kinds the track already uses (file_exists, file_contains,
     command, lug_completed, commit). A commitment that only a human can mark done
     is one the human must remember to mark, which is the original problem wearing
     a checkbox. `manual` exists, must state why, and is reported separately.

  3. AGED, AND THE AGE IS THE POINT. Every commitment carries how many days it has
     been open. Age is not a retire verdict -- it is a visibility multiplier. The
     oldest OPEN commitment is surfaced by name at every wakeup, so "we never
     returned to it" becomes a sentence the wheel says out loud, unprompted.

  4. IMPACT IS A SEPARATE GATE FROM LANDING. This is the half that makes it evolve
     rather than merely complete. A commitment may declare a MEASURE -- a command
     whose numeric output is sampled when the commitment is made (`baseline`) and
     re-sampled after it lands (`effect`). Landing without a measured effect is
     status LANDED_UNMEASURED, which is NOT done. The operator asked to "verify its
     impact and evolve it"; a to-do list cannot do that, and a to-do list is what
     this would have been without the measure.

STATUSES:
    OPEN                landing condition is false
    LANDED_UNMEASURED   condition true, but a declared measure has never been re-read
    LANDED              condition true; no measure declared, or the measure was read
    REGRESSED           condition was true and has gone false again

REGRESSED is checked on every run rather than trusted from the file, because a
commitment that landed and then quietly came undone is the exact failure this whole
tenet exists to catch, and it would otherwise sit in the register reading LANDED
forever.

CLI:
    commitment_register.py --root DIR add --id ID --text T --landing JSON [--measure CMD]
    commitment_register.py --root DIR check [--json]
    commitment_register.py --root DIR measure --id ID       re-read a landed measure
    commitment_register.py --root DIR line                  one line for the wakeup

Exit codes: 0 nothing open, 1 open commitments exist, 2 a REGRESSED one exists.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import trust_epoch as te


REGISTER_FILE = "commitments.json"
CROWDING_LIMIT = 24  # past this the register has become a backlog and says so

OPEN = "OPEN"
LANDED = "LANDED"
LANDED_UNMEASURED = "LANDED_UNMEASURED"
REGRESSED = "REGRESSED"

SEVERITY = {REGRESSED: 0, OPEN: 1, LANDED_UNMEASURED: 2, LANDED: 3}


def _now():
    return datetime.now(timezone.utc)


def register_path(root, mode=None):
    return os.path.join(te.base_dir(root, mode), te.TRUST_DIR, REGISTER_FILE)


def read(root, mode=None):
    path = register_path(root, mode)
    try:
        with open(path) as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {"commitments": []}
    if not isinstance(data, dict):
        return {"commitments": []}
    data.setdefault("commitments", [])
    return data


def write(root, data, mode=None):
    path = register_path(root, mode)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    return path


# ------------------------------------------------------------- LANDING


def evaluate_landing(root, landing):
    """Return (bool_landed, evidence). Unknown kinds are NOT landed.

    Defaulting an unrecognised landing kind to True would let a typo mark work
    complete, which is the cheapest possible way to fake this whole register.
    """
    if not isinstance(landing, dict):
        return False, "landing is not an object"
    kind = landing.get("kind")

    if kind == "file_exists":
        p = os.path.join(root, landing.get("path", ""))
        return os.path.exists(p), f"file_exists {landing.get('path')}"

    if kind == "file_contains":
        p = os.path.join(root, landing.get("path", ""))
        needle = landing.get("needle", "")
        try:
            with open(p) as handle:
                return needle in handle.read(), f"file_contains {landing.get('path')}"
        except OSError:
            return False, f"file_contains: cannot read {landing.get('path')}"

    if kind == "lug_completed":
        lug_id = landing.get("id", "")
        import glob as _glob
        hits = _glob.glob(os.path.join(te.base_dir(root), "lugs", "bytype", "*",
                                       "completed", f"{lug_id}.json"))
        return bool(hits), f"lug_completed {lug_id}"

    if kind == "commit":
        sha = landing.get("sha", "")
        try:
            proc = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor",
                                   sha, "HEAD"], capture_output=True, timeout=30)
            return proc.returncode == 0, f"commit {sha} ancestor of HEAD"
        except (OSError, subprocess.TimeoutExpired):
            return False, f"commit {sha}: git unavailable"

    if kind == "command":
        cmd = landing.get("cmd", "")
        try:
            proc = subprocess.run(cmd, shell=True, cwd=root, capture_output=True,
                                  text=True, timeout=landing.get("timeout", 600))
            return proc.returncode == 0, f"command exited {proc.returncode}"
        except (OSError, subprocess.TimeoutExpired):
            return False, "command did not complete"

    if kind == "manual":
        # Never auto-lands, by construction. Reported separately so a register full
        # of manual conditions is visibly a register that is not doing its job.
        return False, f"manual: {landing.get('note', 'no reason given')}"

    return False, f"unknown landing kind {kind!r} -- treated as NOT landed"


_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def sample_measure(root, measure):
    """Run a measure command and pull the FIRST number out of its stdout.

    Deliberately crude and deliberately numeric: the point is a before/after that
    cannot be argued with. A measure that prints prose returns None, which reads as
    unmeasured rather than as an improvement.
    """
    if not measure:
        return None, "no measure declared"
    try:
        proc = subprocess.run(measure, shell=True, cwd=root, capture_output=True,
                              text=True, timeout=900)
    except (OSError, subprocess.TimeoutExpired):
        return None, "measure did not complete"
    match = _NUM.search(proc.stdout or "")
    if not match:
        return None, f"measure produced no number (exit {proc.returncode})"
    return float(match.group()), (proc.stdout or "").strip().splitlines()[-1][:120]


# ------------------------------------------------------------------ API


def add(root, commitment_id, text, landing, measure=None, owner=None, mode=None):
    data = read(root, mode)
    if any(c["id"] == commitment_id for c in data["commitments"]):
        return {"added": False, "reason": "id already registered"}
    baseline, baseline_note = (None, "no measure declared")
    if measure:
        baseline, baseline_note = sample_measure(root, measure)
    data["commitments"].append({
        "id": commitment_id,
        "text": text,
        "landing": landing,
        "measure": measure,
        "baseline": baseline,
        "baseline_note": baseline_note,
        "effect": None,
        "owner": owner or "unassigned",
        "opened_at": te._iso(_now()),
        "landed_at": None,
    })
    write(root, data, mode)
    return {"added": True, "id": commitment_id, "baseline": baseline}


def _age_days(iso):
    parsed = te._parse_ts(iso)
    return None if parsed is None else max(0, (_now() - parsed).days)


def check(root, mode=None, run_landings=True):
    data = read(root, mode)
    rows = []
    changed = False
    for c in data["commitments"]:
        landed, evidence = (evaluate_landing(root, c.get("landing"))
                            if run_landings else (bool(c.get("landed_at")), "not evaluated"))
        was_landed = bool(c.get("landed_at"))

        if landed and not was_landed:
            c["landed_at"] = te._iso(_now())
            changed = True
        elif not landed and was_landed:
            c["landed_at"] = None
            changed = True

        if not landed:
            status = REGRESSED if was_landed else OPEN
        elif c.get("measure") and c.get("effect") is None:
            status = LANDED_UNMEASURED
        else:
            status = LANDED

        rows.append({
            "id": c["id"], "text": c["text"], "status": status,
            "owner": c.get("owner"), "age_days": _age_days(c.get("opened_at")),
            "evidence": evidence, "measure": c.get("measure"),
            "baseline": c.get("baseline"), "effect": c.get("effect"),
            "landing_kind": (c["landing"].get("kind")
                             if isinstance(c.get("landing"), dict) else None),
        })
    if changed:
        write(root, data, mode)

    rows.sort(key=lambda r: (SEVERITY[r["status"]], -(r["age_days"] or 0)))
    counts = {s: sum(1 for r in rows if r["status"] == s)
              for s in (REGRESSED, OPEN, LANDED_UNMEASURED, LANDED)}
    unfinished = [r for r in rows if r["status"] in (OPEN, REGRESSED, LANDED_UNMEASURED)]
    manual_only = [r for r in rows if r["landing_kind"] == "manual"]
    return {
        "checked_at": te._iso(_now()),
        "total": len(rows),
        "counts": counts,
        "oldest_open": (max((r for r in rows if r["status"] == OPEN),
                            key=lambda r: r["age_days"] or 0, default=None)),
        "unfinished": len(unfinished),
        "manual_landings": len(manual_only),
        "crowded": len(rows) > CROWDING_LIMIT,
        "rows": rows,
    }


def measure(root, commitment_id, mode=None):
    """Re-read a landed commitment's measure and record the effect."""
    data = read(root, mode)
    for c in data["commitments"]:
        if c["id"] != commitment_id:
            continue
        if not c.get("measure"):
            return {"measured": False, "reason": "no measure declared"}
        value, note = sample_measure(root, c["measure"])
        c["effect"] = value
        c["effect_note"] = note
        c["measured_at"] = te._iso(_now())
        write(root, data, mode)
        delta = (None if value is None or c.get("baseline") is None
                 else round(value - c["baseline"], 3))
        return {"measured": True, "id": commitment_id, "baseline": c.get("baseline"),
                "effect": value, "delta": delta, "note": note}
    return {"measured": False, "reason": "unknown commitment id"}


def line(report):
    """One unconditional wakeup line. Names the oldest open commitment, because a
    count alone is something a reader learns to skip past."""
    c = report["counts"]
    if not report["total"]:
        return "Commitments: none registered"
    if c[REGRESSED]:
        return f"Commitments: ⚠ {c[REGRESSED]} REGRESSED -- landed work has come undone"
    if c[OPEN]:
        oldest = report["oldest_open"]
        tail = f" (oldest {oldest['age_days']}d: {oldest['id']})" if oldest else ""
        return (f"Commitments: {c[OPEN]} open, {c[LANDED_UNMEASURED]} landed-unmeasured, "
                f"{c[LANDED]} done{tail}")
    if c[LANDED_UNMEASURED]:
        return (f"Commitments: all landed, but {c[LANDED_UNMEASURED]} never measured "
                "-- landing is not impact")
    return f"Commitments: all {c[LANDED]} landed and measured"


def render(report):
    out = [line(report), ""]
    for r in report["rows"]:
        if r["status"] == LANDED:
            continue
        age = f"{r['age_days']}d" if r["age_days"] is not None else "?"
        out.append(f"  [{r['status']:<17}] {age:>4}  {r['id']}")
        out.append(f"        {r['text']}")
        out.append(f"        landing: {r['evidence']}")
        if r["status"] == LANDED_UNMEASURED:
            out.append(f"        measure never re-read (baseline {r['baseline']}) -- run: measure --id {r['id']}")
    if report["crowded"]:
        out.append(f"  ! {report['total']} commitments -- past {CROWDING_LIMIT} this is a "
                   "backlog, not a register, and it has stopped working")
    if report["manual_landings"]:
        out.append(f"  ! {report['manual_landings']} commitment(s) land only by human "
                   "judgement -- those depend on someone remembering")
    return "\n".join(out)


def exit_code(report):
    if report["counts"][REGRESSED]:
        return 2
    return 1 if report["counts"][OPEN] or report["counts"][LANDED_UNMEASURED] else 0


def _main(argv=None):
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

    p_add = sub.add_parser("add", parents=[common])
    p_add.add_argument("--id", required=True, dest="cid")
    p_add.add_argument("--text", required=True)
    p_add.add_argument("--landing", required=True, help="JSON landing object")
    p_add.add_argument("--measure", default=None)
    p_add.add_argument("--owner", default=None)

    p_check = sub.add_parser("check", parents=[common])
    p_check.add_argument("--no-run", action="store_true")

    p_meas = sub.add_parser("measure", parents=[common])
    p_meas.add_argument("--id", required=True, dest="cid")

    sub.add_parser("line", parents=[common])
    args = parser.parse_args(argv)

    if args.cmd == "add":
        out = add(args.root, args.cid, args.text, json.loads(args.landing),
                  args.measure, args.owner, args.mode)
        print(json.dumps(out, indent=2) if args.json else
              f"registered {args.cid} (baseline {out.get('baseline')})")
        return 0 if out.get("added") else 1

    if args.cmd == "measure":
        out = measure(args.root, args.cid, args.mode)
        print(json.dumps(out, indent=2) if args.json else
              f"{args.cid}: baseline {out.get('baseline')} -> effect {out.get('effect')} "
              f"(delta {out.get('delta')})")
        return 0 if out.get("measured") else 1

    report = check(args.root, args.mode, run_landings=not getattr(args, "no_run", False))
    if args.cmd == "line":
        print(json.dumps({"line": line(report)}, indent=2) if args.json else line(report))
        return exit_code(report)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report))
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(_main())
