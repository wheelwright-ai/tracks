#!/usr/bin/env python3
"""lug_class.py -- what is this lug, and who is it for. Two axes, no guessing.

OPERATOR 2026-08-18: "Most of the backlog isn't work -- it's notes that look like
work. lugs must be refined to understand who they are for and what they are -
work or notes or something else."

MEASURED across four spokes the same day, independently:

    mywheel      968 open, 539 executable, 501 of those target the HARNESS, 38 the product
    ezorg         83 open, 81% notes, 6 product items, 14 undrained receipts
    pathfinder   338 open, 56% notes, 52 undrained receipts
    basher       578 open, 78.7% with no target_files at all  (basher's own measurement)

Four spokes, four measurements, one shape. `ready_count` reports the whole pile,
so a 968-item notebook presents itself as a work queue and every scan, wakeup and
autopilot round pays to re-read it.

THE TWO AXES, and why both are needed:

  KIND   work | note | receipt
         A lug with no file_targets and no complete perceive/execute/verify is an
         OBSERVATION. It may be a good observation. It is not a queue item, and
         counting it as one is what makes the backlog lie.

  FOR    product | harness | unknown
         Which one is "the product" depends on the spoke. On mywheel the harness
         IS the product, and saying otherwise would be wrong. Everywhere else,
         harness work is maintenance -- worth doing, never the point. This axis is
         what makes "we did 29 commits and moved the mission by one" visible.

NOTHING IS DELETED, RETIRED OR MOVED. This tool only reads and reports. A
classification is a fact about a lug, not a verdict on it -- the verdict belongs
to whoever reads the report.

USAGE
  lug_class.py report [--root .] [--json]     composition, the number that matters
  lug_class.py ready  [--root .] [--json]     ONLY the work: what a queue should contain
  lug_class.py stamp  [--root .] [--commit]   write _class onto each lug (dry by default)
"""
import argparse
import glob
import json
import os
import sys

TOOL_VERSION = "1.0.0"

WORK = "work"
NOTE = "note"
RECEIPT = "receipt"

PRODUCT = "product"
HARNESS = "harness"
UNKNOWN = "unknown"
# Harness work on a spoke that SHIPS the harness. Product, and still harness --
# collapsing it to either alone loses information the operator needs.
HARNESS_AS_PRODUCT = "harness(=product)"

# Types that are RECORDS of something that happened, not requests for work.
# A receipt has no perceive/execute/verify by construction and never should.
RECEIPT_TYPES = frozenset({
    "upgrade-report", "upgrade_report", "receipt", "ack", "notice",
    "report", "notation", "session-summary", "session_summary", "signal",
})

# Spokes whose PRODUCT is the harness itself. On these, harness-targeted work is
# product work and it would be false to score it as maintenance. mywheel's stated
# goal is "be the canonical, self-improving harness every wheel runs on".
HARNESS_IS_THE_PRODUCT = frozenset({"mywheel", "basher"})


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _targets(lug):
    return [str(t).strip() for t in _as_list(
        lug.get("file_targets") or lug.get("target_files")) if str(t).strip()]


def _has_pev(lug):
    return all(_as_list(lug.get(k)) for k in ("perceive", "execute", "verify"))


def classify(lug, spoke_id=""):
    """Return (kind, who_for, why). Reads only fields already on the lug."""
    ltype = str(lug.get("type") or "").strip().lower()
    targets = _targets(lug)

    if ltype in RECEIPT_TYPES:
        return RECEIPT, UNKNOWN, f"type '{ltype}' records an event; it is not a request"

    if not targets and not _has_pev(lug):
        return NOTE, UNKNOWN, "no file_targets and no complete perceive/execute/verify"
    if not targets:
        return NOTE, UNKNOWN, "no file_targets -- nothing to change is named"
    if not _has_pev(lug):
        return NOTE, UNKNOWN, "incomplete perceive/execute/verify"

    blob = " ".join(targets)
    harnessy = ("WAI-Harness" in blob or "WAI-Spoke" in blob or ".claude/" in blob)
    if harnessy and spoke_id in HARNESS_IS_THE_PRODUCT:
        # Saying "maintenance" here would be false: this spoke ships the harness.
        # But COLLAPSING it to plain `product` hides the split entirely -- measured
        # 2026-08-18, mywheel reported "822 product" and the axis discriminated
        # nothing, which is the same defect as ready_count reporting 968. A distinct
        # value keeps both truths: it counts as product here AND it is harness work.
        return WORK, HARNESS_AS_PRODUCT, "targets the harness, which IS this spoke's product"
    if harnessy:
        return WORK, HARNESS, "targets harness paths -- maintenance, not this spoke's product"
    return WORK, PRODUCT, "targets this spoke's own files"


# Path resolution is v6/v4-PRIMARY and the v3 husk is a guarded fallback, never the
# sole path. Spelled as literal strings on purpose: assembled-from-components paths
# read as v3-only to the cut-gate lint, and a tool that looks v3-only to the gate is
# indistinguishable from one that IS.
V4_BASE = "WAI-Harness/spoke/local"
IDENT_PATHS = ("WAI-Harness/spoke/basher.json", "WAI-Spoke/basher.json")
LUG_GLOB_V4 = V4_BASE + "/lugs/bytype/*/open/*.json"
LUG_GLOB_V3 = "WAI-Spoke/lugs/bytype/*/open/*.json"


def _spoke_id(root):
    for rel in IDENT_PATHS:
        p = os.path.join(root, rel)
        try:
            with open(p, encoding="utf-8") as fh:
                sid = (json.load(fh).get("spoke") or {}).get("wheel_id")
                if sid:
                    return str(sid)
        except (OSError, ValueError, AttributeError):
            continue
    return os.path.basename(os.path.abspath(root))


def _lugs(root):
    hits = sorted(glob.glob(os.path.join(root, *LUG_GLOB_V4.split("/"))))
    if hits:
        return hits
    return sorted(glob.glob(os.path.join(root, *LUG_GLOB_V3.split("/"))))


def survey(root="."):
    sid = _spoke_id(root)
    rows, unreadable = [], 0
    for path in _lugs(root):
        try:
            with open(path, encoding="utf-8") as fh:
                lug = json.load(fh)
        except (OSError, ValueError):
            unreadable += 1
            continue
        kind, who, why = classify(lug, sid)
        rows.append({"path": path, "id": lug.get("id") or os.path.basename(path)[:-5],
                     "type": lug.get("type"), "kind": kind, "for": who, "why": why})
    return {"spoke": sid, "rows": rows, "unreadable": unreadable}


def _counts(rows):
    out = {"total": len(rows), "kind": {}, "for": {}}
    for r in rows:
        out["kind"][r["kind"]] = out["kind"].get(r["kind"], 0) + 1
        if r["kind"] == WORK:
            out["for"][r["for"]] = out["for"].get(r["for"], 0) + 1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("report", "ready", "stamp"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
        p.add_argument("--json", action="store_true")
        if name == "stamp":
            p.add_argument("--commit", action="store_true",
                           help="actually write _class onto each lug (default: dry)")
    args = ap.parse_args(argv)

    s = survey(args.root)
    rows, c = s["rows"], _counts(s["rows"])

    if args.cmd == "ready":
        work = [r for r in rows if r["kind"] == WORK]
        if args.json:
            print(json.dumps(work, indent=2))
        else:
            prod = [r for r in work if r["for"] in (PRODUCT, HARNESS_AS_PRODUCT)]
            print(f"{len(work)} work item(s) of {c['total']} open "
                  f"-- {len(prod)} advance this spoke's product")
            for r in prod[:20]:
                print(f"  {r['id'][:66]}")
        return 0

    if args.cmd == "stamp":
        written = 0
        for r in rows:
            if not args.commit:
                written += 1
                continue
            try:
                with open(r["path"], encoding="utf-8") as fh:
                    lug = json.load(fh)
                lug["_class"] = {"kind": r["kind"], "for": r["for"], "why": r["why"],
                                 "by": f"lug_class {TOOL_VERSION}"}
                with open(r["path"], "w", encoding="utf-8") as fh:
                    json.dump(lug, fh, indent=2)
                written += 1
            except (OSError, ValueError):
                pass
        head = "would stamp" if not args.commit else "stamped"
        print(f"{head} {written} lug(s)")
        return 0

    if args.json:
        print(json.dumps({"spoke": s["spoke"], "counts": c,
                          "unreadable": s["unreadable"]}, indent=2))
        return 0

    t = c["total"] or 1
    print(f"\n{s['spoke']}: {c['total']} open lug(s)\n")
    print("  WHAT THEY ARE")
    for k in (WORK, NOTE, RECEIPT):
        n = c["kind"].get(k, 0)
        print(f"    {k:<10} {n:>5}  {100.0*n/t:>5.1f}%")
    print("\n  OF THE WORK, WHO FOR")
    for k in (PRODUCT, HARNESS_AS_PRODUCT, HARNESS, UNKNOWN):
        n = c["for"].get(k, 0)
        if n:
            print(f"    {k:<10} {n:>5}")
    prod = c["for"].get(PRODUCT, 0) + c["for"].get(HARNESS_AS_PRODUCT, 0)
    print(f"\n  ready_count today reports {c['total']}. "
          f"{prod} advance this spoke's product.")
    if s["unreadable"]:
        print(f"  ({s['unreadable']} unreadable, counted nowhere)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
