#!/usr/bin/env python3
"""Drain upgrade-report receipts into work, then archive them.

WHY THIS EXISTS AS CODE.

`harness_upgrade.py` writes an upgrade-report per spoke per cut into
`lugs/bytype/upgrade-report/open/`. A consumer was specified -- the
`wai-upgrade-report-intake` ceremony -- and it is complete and correct prose.
It is also invoked by NOTHING: measured 2026-08-18, zero references from any
hook, settings.json, managed tool or the kernel, and it was already on the
list of 18 commands with no live caller.

So the producer ran every upgrade and the consumer never ran once. 314 receipts
accumulated in the OPEN work backlog -- 30% of every open lug on this spoke --
each one a machine's validation result that no human ever needed to action as
"work". Half a circle looks exactly like a whole one from the half that works.

A receipt is not work. It is an observation with a disposition:

  pass     nothing broke, nothing was already broken   -> archive
  partial  checks failed, but they failed BEFORE too   -> one deduped debt lug
           per check name, then archive. The cut is not answerable for damage
           it did not cause.
  fail     a check that PASSED before now fails        -> one bug lug per
           REGRESSION, then archive.

Ported from `.claude/commands/wai-upgrade-report-intake.md`, which stays as the
human-readable contract. The logic here is that ceremony's Steps 2-5; where the
two ever disagree, the ceremony is the spec and this is the defect.

USAGE
  upgrade_report_intake.py drain [--root .] [--dry-run]
  upgrade_report_intake.py status [--root .] [--json]

`--dry-run` is honest: it reports what WOULD happen and writes nothing at all.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys

TOOL_VERSION = "1.0.0"


def _base(root):
    v4 = os.path.join(root, "WAI-Harness", "spoke", "local")
    return v4 if os.path.isdir(v4) else os.path.join(root, "WAI-Spoke")


def _slug(t):
    return re.sub(r"[^a-z0-9]+", "-", str(t).lower()).strip("-")[:40]


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _reports(base):
    d = os.path.join(base, "lugs", "bytype", "upgrade-report", "open")
    if not os.path.isdir(d):
        return []
    return sorted(
        os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json"))


def _is_transient_freeze(report):
    """A master that was briefly un-shippable is not a broken spoke.

    When master's self-verification aborts on a dirty managed/ tree, EVERY
    spoke pulling in that window emits outcome:fail with an empty validation
    block. Opening a bug per spoke for that would bury the queue in copies of
    a condition that self-heals on the next cut.
    """
    v = report.get("validation") or {}
    if v.get("checks") or v.get("regressions"):
        return False
    blob = " ".join(str(report.get(k, "")) for k in ("summary", "one_liner", "title")).lower()
    return ("self-verification" in blob or "corrupt master" in blob
            or "mismatched" in blob or "aborted before validation" in blob)


def _write_lug(path, payload, dry_run):
    if os.path.exists(path):
        return False                      # dedup: same finding already open
    if dry_run:
        return True
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return True


def drain(root=".", dry_run=False):
    base = _base(root)
    out = {"scanned": 0, "archived": 0, "bugs_opened": 0, "debt_opened": 0,
           "transient": 0, "by_outcome": {}, "unparseable": 0}
    dst_dir = os.path.join(base, "lugs", "bytype", "upgrade-report", "completed")

    for path in _reports(base):
        out["scanned"] += 1
        try:
            with open(path, encoding="utf-8") as fh:
                report = json.load(fh)
        except (OSError, ValueError):
            out["unparseable"] += 1
            continue                      # never delete what we cannot read

        outcome = str(report.get("outcome") or "partial")
        out["by_outcome"][outcome] = out["by_outcome"].get(outcome, 0) + 1
        spoke_id = report.get("spoke_id", "unknown")
        version = report.get("harness_version", "unknown")
        validation = report.get("validation") or {}
        regressions = validation.get("regressions") or []
        preexisting = validation.get("preexisting_failures") or []
        failed = [c for c in (validation.get("checks") or [])
                  if c.get("status") == "fail"]

        # `declined` is a guard refusing a pull before anything was applied -- nothing
        # broke, nothing is owed. It is counted and archived, and deliberately opens no
        # lug. It gets its own branch rather than falling through the fail/partial pair,
        # because falling through is what adversarial review measured on 2026-08-22: an
        # unhandled outcome reached the archive at line 186 having opened nothing, and the
        # nine live bug-upgrade-*-broke-* lugs this path has produced would have stopped
        # appearing with no signal that the circle had gone quiet.
        if outcome == "declined":
            out["declined"] = out.get("declined", 0) + 1
        elif outcome == "fail" and _is_transient_freeze(report):
            out["transient"] += 1         # archive, open nothing
        elif outcome == "fail":
            for check in [c for c in failed if c.get("check") in regressions]:
                name = check.get("check")
                lug_id = "bug-upgrade-{}-broke-{}-on-{}-v1".format(
                    _slug(version), _slug(name), _slug(spoke_id))
                p = os.path.join(base, "lugs", "bytype", "bug", "open", lug_id + ".json")
                if _write_lug(p, {
                        "id": lug_id, "type": "bug", "status": "open",
                        "routed_to": "LOCAL", "created_at": _now(),
                        "created_by": "upgrade_report_intake",
                        "title": "Upgrade {} broke {} on {}".format(version, name, spoke_id),
                        "impact": 8,
                        "impact_basis": ("a spoke is broken right now by a shipped cut; "
                                         "the next agent on it loses hours to a harness "
                                         "that no longer works"),
                        "_source_report": report.get("id"),
                        "verify": ["cmd: " + str(check.get("command") or
                                                 "python3 WAI-Harness/spoke/managed/tools/"
                                                 "spoke_health_check.py . --quick")],
                    }, dry_run):
                    out["bugs_opened"] += 1
        elif outcome == "partial":
            for name in preexisting:
                lug_id = "impl-validation-debt-{}-v1".format(_slug(name))
                p = os.path.join(base, "lugs", "bytype", "impl", "open", lug_id + ".json")
                if _write_lug(p, {
                        "id": lug_id, "type": "impl", "status": "open",
                        "routed_to": "LOCAL", "created_at": _now(),
                        "created_by": "upgrade_report_intake",
                        "title": "Validation debt: {} was already failing".format(name),
                        "impact": 5,
                        "impact_basis": ("pre-existing failure, not caused by this cut; "
                                         "costs a clarification loop each time it is "
                                         "re-encountered"),
                        "_source_report": report.get("id"),
                        "verify": ["cmd: python3 WAI-Harness/spoke/managed/tools/"
                                   "spoke_health_check.py . --quick"],
                    }, dry_run):
                    out["debt_opened"] += 1

        if not dry_run:
            os.makedirs(dst_dir, exist_ok=True)
            shutil.move(path, os.path.join(dst_dir, os.path.basename(path)))
        out["archived"] += 1

    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("drain", "status"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
        p.add_argument("--json", action="store_true")
        if name == "drain":
            p.add_argument("--dry-run", action="store_true",
                           help="report what would happen; write nothing")
    args = ap.parse_args(argv)

    if args.cmd == "status":
        base = _base(args.root)
        counts = {}
        for path in _reports(base):
            try:
                with open(path, encoding="utf-8") as fh:
                    o = str(json.load(fh).get("outcome") or "partial")
            except (OSError, ValueError):
                o = "unparseable"
            counts[o] = counts.get(o, 0) + 1
        total = sum(counts.values())
        if args.json:
            print(json.dumps({"open": total, "by_outcome": counts}, indent=2))
        else:
            print("upgrade-report backlog: {} open".format(total))
            for k, v in sorted(counts.items()):
                print("  {:<12} {:>4}".format(k, v))
        return 0

    res = drain(args.root, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        head = "would drain" if args.dry_run else "drained"
        print("{} {} report(s): {} archived, {} bug(s), {} debt lug(s), "
              "{} transient-freeze, {} unparseable".format(
                  head, res["scanned"], res["archived"], res["bugs_opened"],
                  res["debt_opened"], res["transient"], res["unparseable"]))
        for k, v in sorted(res["by_outcome"].items()):
            print("  {:<10} {}".format(k, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
