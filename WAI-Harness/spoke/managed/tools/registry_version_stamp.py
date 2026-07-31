#!/usr/bin/env python3
"""Stamp PROVEN spoke harness versions into hub-registry.json from upgrade reports.

THE CONSUMER HALF OF THE VERSION CIRCLE.

`harness_upgrade.emit_upgrade_report` already posts a report into master's
`lugs/incoming/` after every distribution, and that report carries the three
things the registry needs: which spoke, which version, and whether the bytes
verified. The intake ceremony read those reports, mined them for friction, and
threw the version away. So the registry's `harness_version` column had exactly
one writer -- `conductor --certify`, a heavyweight periodic sweep -- and between
sweeps it drifted into fiction:

    registry said   pathfinder / ezorg / basher   4.14.10
    the spokes said (same day, byte-verified)     4.14.18
    registry said   mywheel                        4.6.4  (running 4.14.18)

A stale version column is worse than an empty one. "Is the fleet current?" is
answerable-looking, so nobody checks, and the answer is wrong.

EVIDENCE GATE. A report only stamps when it PROVED something:

    verify_post_ok is true   the applied bytes matched master's manifest
    outcome is not "fail"    validation did not regress the spoke

This mirrors conductor.py's own discipline (registry write is transactional with
the byte_verify that earned it, conductor.py:1427). A report that aborted, or
failed its post-verify, proves nothing about what is on that spoke's disk, and
recording its target version would launder an intention into a fact.

NEWEST WINS, NOT HIGHEST. The freshest qualifying report is the truth even if it
names a LOWER version -- that is a rollback, and a registry that refuses to
record rollbacks is a registry that lies in exactly the situation where being
wrong costs the most.

PROVENANCE IS THE POINT. Every stamp records source, timestamp and the lug id
that earned it, so `coverage()` can separate three states the old column could
not distinguish: proven (a report earned it), unproven (a version with no
evidence -- conductor's or hand-written, possibly stale), unknown (null).
Counting unproven as known is how the fiction survived.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

STAMP_SOURCE = "upgrade-report"
# The master never posts itself mail (harness_upgrade.emit_upgrade_report skips the
# self-delivery), so no report will ever prove the master's own row. Its MANIFEST is
# not second-hand evidence about the master -- it IS the master's declaration of what
# it cut, which is the definition of the version. Left unhandled, the authoring repo's
# own row is the most embarrassing lie in the file: mywheel read 4.6.4 while cutting
# 4.14.18.
SELF_SOURCE = "master-manifest"
PROVEN_SOURCES = (STAMP_SOURCE, SELF_SOURCE)

# Provenance keys written alongside the version. Grouped so a reader (and the
# coverage oracle) can tell an earned value from an inherited one.
K_VERSION = "harness_version"
K_SOURCE = "harness_version_source"
K_AT = "harness_version_at"
K_EVIDENCE = "harness_version_evidence"


def _load(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def find_repo_root(start=None):
    """Walk up for the repo that owns WAI-Harness/. Mirrors ceremony-lib's resolution."""
    cur = Path(start or Path(__file__).resolve()).resolve()
    for cand in [cur] + list(cur.parents):
        if (cand / "WAI-Harness").is_dir():
            return cand
    return Path.cwd()


def default_registry(root):
    return Path(root) / "WAI-Harness" / "hub" / "local" / "hub-registry.json"


def default_report_dirs(root):
    base = Path(root) / "WAI-Harness" / "spoke" / "local" / "lugs" / "bytype" / "upgrade-report"
    return [base / "open", base / "completed"]


def load_reports(dirs):
    """Read every upgrade-report lug in `dirs`. Unreadable files are skipped, not fatal.

    A malformed report must not stop the readable ones from stamping -- the whole
    point of this tool is that the registry stays as true as the evidence allows.
    """
    reports, unreadable = [], []
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            rep = _load(f)
            if isinstance(rep, dict):
                rep.setdefault("_path", str(f))
                reports.append(rep)
            else:
                unreadable.append(str(f))
    return reports, unreadable


def qualifies(rep):
    """(ok, reason) -- does this report PROVE a version is on that spoke's disk?"""
    if rep.get("type") != "upgrade-report":
        return False, "not an upgrade-report"
    if not rep.get(K_VERSION):
        return False, "no harness_version"
    if not (rep.get("spoke_path") or rep.get("spoke_id")):
        return False, "no spoke identity"
    if rep.get("outcome") == "fail":
        return False, "outcome=fail"
    if not rep.get("verify_post_ok"):
        return False, "verify_post_ok is not true"
    return True, "ok"


def _sort_key(rep):
    # (created_at, id) so equal timestamps still order deterministically.
    return (str(rep.get("created_at") or ""), str(rep.get("id") or ""))


def best_reports(reports):
    """Newest qualifying report per spoke, keyed by realpath then wheel id.

    Returns (winners, rejected) where winners maps key -> report.
    """
    winners, rejected = {}, []
    for rep in reports:
        ok, why = qualifies(rep)
        if not ok:
            rejected.append({"id": rep.get("id"), "spoke": rep.get("spoke_id"), "reason": why})
            continue
        sp = rep.get("spoke_path")
        key = os.path.realpath(sp) if sp else f"id:{rep.get('spoke_id')}"
        cur = winners.get(key)
        if cur is None or _sort_key(rep) > _sort_key(cur):
            winners[key] = rep
    return winners, rejected


def _match_wheel(wheels, key, rep):
    """Resolve a report to its registry row: realpath first, wheel_id as fallback."""
    if not key.startswith("id:"):
        for w in wheels:
            p = w.get("path")
            if p and os.path.realpath(p) == key:
                return w
    sid = rep.get("spoke_id")
    if sid:
        for w in wheels:
            if w.get("wheel_id") == sid:
                return w
    return None


def plan(registry, reports):
    """Compute stamps without writing. Returns a plan dict (the --json contract)."""
    wheels = registry.get("wheels") or []
    winners, rejected = best_reports(reports)

    stamps, unmatched, skipped = [], [], []
    for key, rep in sorted(winners.items()):
        w = _match_wheel(wheels, key, rep)
        if w is None:
            unmatched.append({"spoke": rep.get("spoke_id"), "path": rep.get("spoke_path"),
                              "version": rep.get(K_VERSION), "evidence": rep.get("id")})
            continue

        have_at = w.get(K_AT) or ""
        new_at = str(rep.get("created_at") or "")
        # Never let an older report overwrite a newer one. Re-running over a
        # completed/ archive must be a no-op, not a time machine.
        if have_at and new_at and new_at < have_at:
            skipped.append({"wheel": w.get("wheel_id"), "reason": "registry has newer evidence",
                            "registry_at": have_at, "report_at": new_at})
            continue

        changed = (w.get(K_VERSION) != rep.get(K_VERSION)
                   or w.get(K_SOURCE) != STAMP_SOURCE
                   or w.get(K_EVIDENCE) != rep.get("id"))
        stamps.append({
            "wheel": w.get("wheel_id"),
            "path": w.get("path"),
            "was": w.get(K_VERSION),
            "now": rep.get(K_VERSION),
            "at": new_at,
            "evidence": rep.get("id"),
            "changed": changed,
        })

    return {"stamps": stamps, "unmatched": unmatched,
            "skipped": skipped, "rejected": rejected}


def apply_plan(registry, plan_obj):
    """Write the plan into `registry` in place. Returns the number of rows changed."""
    wheels = registry.get("wheels") or []
    by_id = {w.get("wheel_id"): w for w in wheels}
    n = 0
    for s in plan_obj["stamps"]:
        w = by_id.get(s["wheel"])
        if w is None:
            continue
        if not s["changed"]:
            # Still refresh provenance timestamp coherence, but nothing material moved.
            continue
        w[K_VERSION] = s["now"]
        w[K_SOURCE] = s.get("source") or STAMP_SOURCE
        w[K_AT] = s["at"]
        w[K_EVIDENCE] = s["evidence"]
        n += 1
    return n


def self_stamp(root, registry):
    """Stamp the master's OWN row from its manifest. Returns a stamp dict or None.

    Guarded on is_master: a spoke running this must never claim its manifest is
    authoritative for the fleet's copy of its version -- that is what its upgrade
    report is for, and that one carries a byte-verify this does not.
    """
    manifest = _load(Path(root) / "WAI-Harness" / "spoke" / "managed" / "MANIFEST.json", {})
    if not manifest.get("is_master"):
        return None
    ver = manifest.get(K_VERSION)
    if not ver:
        return None
    key = os.path.realpath(root)
    for w in registry.get("wheels") or []:
        p = w.get("path")
        if p and os.path.realpath(p) == key:
            return {
                "wheel": w.get("wheel_id"), "path": w.get("path"),
                "was": w.get(K_VERSION), "now": ver, "at": None,
                "evidence": "MANIFEST.json (is_master)", "source": SELF_SOURCE,
                "changed": (w.get(K_VERSION) != ver or w.get(K_SOURCE) != SELF_SOURCE),
            }
    return None


def coverage(registry):
    """How much of the version column is EARNED?

    proven    a qualifying upgrade report put it there, or the master's own
              manifest did (see SELF_SOURCE)
    unproven  a version is present with no provenance -- conductor's, or typed by
              hand, and unfalsifiable from here. NOT the same as known.
    unknown   null / absent
    """
    wheels = registry.get("wheels") or []
    active = [w for w in wheels if w.get("status") == "active"]
    def bucket(ws):
        p = sum(1 for w in ws if w.get(K_SOURCE) in PROVEN_SOURCES and w.get(K_VERSION))
        u = sum(1 for w in ws if w.get(K_VERSION) and w.get(K_SOURCE) not in PROVEN_SOURCES)
        k = sum(1 for w in ws if not w.get(K_VERSION))
        return {"proven": p, "unproven": u, "unknown": k, "total": len(ws)}
    return {"all": bucket(wheels), "active": bucket(active)}


def run(root=None, registry_path=None, report_dirs=None, apply=False):
    root = Path(root or find_repo_root())
    registry_path = Path(registry_path or default_registry(root))
    report_dirs = report_dirs or default_report_dirs(root)

    registry = _load(registry_path)
    if not isinstance(registry, dict):
        return {"ok": False, "error": f"registry unreadable: {registry_path}"}

    reports, unreadable = load_reports(report_dirs)
    p = plan(registry, reports)

    # The master's own row, from its manifest -- appended last so a real report
    # about the master (there should never be one) would already hold the slot.
    self_s = self_stamp(root, registry)
    if self_s and not any(s["wheel"] == self_s["wheel"] for s in p["stamps"]):
        p["stamps"].append(self_s)
    p["self_stamped"] = bool(self_s)

    p["unreadable_reports"] = unreadable
    p["reports_seen"] = len(reports)
    p["registry"] = str(registry_path)
    p["applied"] = 0
    p["coverage_before"] = coverage(registry)

    if apply:
        n = apply_plan(registry, p)
        if n:
            tmp = registry_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
            tmp.replace(registry_path)
        p["applied"] = n

    p["coverage_after"] = coverage(registry)
    p["ok"] = True
    return p


def _print_human(p):
    if not p.get("ok"):
        print(f"registry_version_stamp: ERROR {p.get('error')}", file=sys.stderr)
        return
    changed = [s for s in p["stamps"] if s["changed"]]
    print(f"registry_version_stamp  reports={p['reports_seen']}  "
          f"matched={len(p['stamps'])}  would-change={len(changed)}  applied={p['applied']}")
    for s in p["stamps"]:
        mark = "*" if s["changed"] else " "
        print(f"  {mark} {s['wheel']:<30} {str(s['was']):>9} -> {s['now']:<9} ({s['evidence']})")
    for u in p["unmatched"]:
        print(f"  ! {str(u['spoke']):<30} reported {u['version']} but is NOT in the registry")
    for s in p["skipped"]:
        print(f"  - {str(s['wheel']):<30} skipped: {s['reason']}")
    cb, ca = p["coverage_before"]["active"], p["coverage_after"]["active"]
    print(f"  version truth (active wheels): proven {cb['proven']}->{ca['proven']}  "
          f"unproven {cb['unproven']}->{ca['unproven']}  unknown {cb['unknown']}->{ca['unknown']}  "
          f"of {ca['total']}")
    if p["rejected"]:
        print(f"  {len(p['rejected'])} report(s) did not qualify as proof "
              f"(see --json for reasons)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", help="repo root (default: auto-detect)")
    ap.add_argument("--registry", help="path to hub-registry.json")
    ap.add_argument("--reports", nargs="*", help="upgrade-report dirs to read")
    ap.add_argument("--apply", action="store_true", help="write the registry (default: dry run)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args(argv)

    p = run(root=a.root, registry_path=a.registry, report_dirs=a.reports, apply=a.apply)
    if a.json:
        print(json.dumps(p, indent=2))
    else:
        _print_human(p)
    return 0 if p.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
