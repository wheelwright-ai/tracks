#!/usr/bin/env python3
"""integrity_probe — run every standing oracle and report what is silently wrong.

WHY THIS EXISTS
---------------
Operator, 2026-07-26: "Our error detection got worse, too basic problems are not getting
seen — that learning has to get caught sooner than by the user."

He is right, and the evidence is one session's worth of findings that all share a shape.
None of these were errors. Every one was a SILENCE:

  - restore reported "live hooks current" while the hook sat undeployed on two spokes.
    Caught by a one-off manual audit that someone happened to think of.
  - master self-verification failed, correctly refusing to distribute, and 23 upgrade
    attempts aborted into reports nobody read. The fleet sat 3 versions behind for 4 days.
  - the dispatcher ignored 68 lugs whose routed_to was spelled differently. Not rejected —
    ignored, with no event and no count.
  - 7 lugs were addressed to repos that no longer exist. One sat 991 hours.

A correct internal decision whose outcome reaches nobody is indistinguishable from no
decision at all. Each of those was found by a human asking the right question on the right
day. This tool asks all of them, every time, so the finding arrives before the operator does.

CONTRACT
--------
Each probe returns GREEN / YELLOW / RED plus a one-line reason and the command that
reproduces it. A probe that cannot run returns UNKNOWN — never GREEN. An unrunnable check
is not a passing check, and treating it as one is how this class of bug survives.
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import subprocess
import sys

GREEN, YELLOW, RED, UNKNOWN = "GREEN", "YELLOW", "RED", "UNKNOWN"


def _result(name, status, headline, detail=None, cmd=None):
    return {"probe": name, "status": status, "headline": headline,
            "detail": detail or [], "reproduce": cmd}


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------- probes

def probe_routing(root="."):
    """Lugs the dispatcher cannot see, and routing values nothing understands."""
    tool = os.path.join(root, "WAI-Harness/spoke/managed/tools/routing_vocab.py")
    cmd = "python3 WAI-Harness/spoke/managed/tools/routing_vocab.py --audit"
    if not os.path.isfile(tool):
        return _result("routing", UNKNOWN, "routing_vocab.py not found", cmd=cmd)
    try:
        rv = _load(tool, "routing_vocab")
        rep = rv.audit(root)
    except Exception as e:
        return _result("routing", UNKNOWN, f"audit failed: {type(e).__name__}: {e}", cmd=cmd)

    detail = [f"{rep['lugs']} live lugs, {rep['dispatchable']} dispatchable"]
    if rep["unresolvable"]:
        detail += [f"UNRESOLVABLE {r['lug']}: {r['note']}"
                   for r in rep["unresolvable_detail"][:5]]
        return _result("routing", RED,
                       f"{rep['unresolvable']} lug(s) carry a routing value nothing understands",
                       detail, cmd)
    if rep["deprecated_targets"]:
        return _result("routing", YELLOW,
                       f"{rep['deprecated_targets']} lug(s) routed at a deprecated name",
                       detail, cmd)
    return _result("routing", GREEN, "every live lug resolves to a canonical destination",
                   detail, cmd)


def probe_master_selfverify(root="."):
    """Master must verify against its own MANIFEST, or NOTHING reaches the fleet."""
    cmd = "python3 -c \"import json,importlib.util;from pathlib import Path;...\"  (see harness_upgrade.verify)"
    tool = os.path.join(root, "WAI-Harness/spoke/managed/tools/harness_upgrade.py")
    manifest = os.path.join(root, "WAI-Harness/spoke/managed/MANIFEST.json")
    if not (os.path.isfile(tool) and os.path.isfile(manifest)):
        return _result("master-selfverify", UNKNOWN, "master managed tree not found", cmd=cmd)
    try:
        from pathlib import Path
        hu = _load(tool, "harness_upgrade")
        man = json.load(open(manifest))
        if not man.get("is_master"):
            return _result("master-selfverify", GREEN, "not the master — nothing to verify", cmd=cmd)
        r = hu.verify(Path(os.path.join(root, "WAI-Harness/spoke/managed")), man)
    except Exception as e:
        return _result("master-selfverify", UNKNOWN,
                       f"verify failed to run: {type(e).__name__}: {e}", cmd=cmd)

    if r.get("ok"):
        return _result("master-selfverify", GREEN,
                       f"master {man.get('harness_version')} verifies — distribution open", cmd=cmd)
    mm = r.get("mismatches", []) or []
    missing = r.get("missing", []) or []
    detail = [f"drifted: {m.get('file')}" for m in mm[:6]] + [f"missing: {m}" for m in missing[:4]]
    detail.append("FLEET DISTRIBUTION IS STALLED until MANIFEST is recut")
    return _result("master-selfverify", RED,
                   f"master fails self-verification — {len(mm)} drifted, {len(missing)} missing",
                   detail, cmd)


def probe_live_hooks(root="."):
    """Live hooks must be byte-identical to managed canon, or a fix never reaches a session."""
    tool = os.path.join(root, "WAI-Harness/hub/local/tools/fleet_hygiene_scan.py")
    cmd = "python3 WAI-Harness/hub/local/tools/fleet_hygiene_scan.py"
    if not os.path.isfile(tool):
        return _result("live-hooks", UNKNOWN, "fleet_hygiene_scan.py not found", cmd=cmd)
    try:
        fh = _load(tool, "fleet_hygiene_scan")
        reg = json.load(open(os.path.join(root, "WAI-Harness/hub/local/hub-registry.json")))
    except Exception as e:
        return _result("live-hooks", UNKNOWN, f"{type(e).__name__}: {e}", cmd=cmd)

    drift, checked = [], 0
    for w in reg.get("wheels", []):
        if w.get("status") != "active" or not w.get("path") or not os.path.isdir(w["path"]):
            continue
        try:
            lh = fh.scan_live_hooks(w["path"])
        except Exception:
            continue
        if lh is None:
            continue
        checked += 1
        if lh["verdict"] == "stale":
            drift.append(f"{w['wheel_id']}: {', '.join((lh['stale'] + lh['missing'])[:3])}")
    if not checked:
        return _result("live-hooks", UNKNOWN, "no spoke had managed hook canon to compare", cmd=cmd)
    if drift:
        return _result("live-hooks", RED,
                       f"{len(drift)} active spoke(s) running stale hooks", drift[:6], cmd)
    return _result("live-hooks", GREEN, f"{checked} active spoke(s) byte-current", cmd=cmd)


def probe_pending_deploys(root="."):
    """Deploy-connected spokes holding unpushed commits — withheld, and waiting on a human."""
    tool = os.path.join(root, "WAI-Harness/hub/local/scripts/wai_hygiene.py")
    cmd = "python3 WAI-Harness/hub/local/scripts/wai_hygiene.py --fleet --dry-run --json"
    if not os.path.isfile(tool):
        return _result("pending-deploys", UNKNOWN, "wai_hygiene.py not found", cmd=cmd)
    try:
        p = subprocess.run([sys.executable, tool, "--fleet", "--dry-run", "--live-min", "0",
                            "--json"], cwd=root, capture_output=True, text=True, timeout=300)
        rows = json.loads(p.stdout or "[]")
    except Exception as e:
        return _result("pending-deploys", UNKNOWN, f"{type(e).__name__}: {e}", cmd=cmd)

    held = []
    for r in rows:
        pd = r.get("push_decision") or {}
        if pd.get("deploy_connected") and pd.get("ahead") and not pd.get("autopush"):
            held.append(f"{os.path.basename(r['spoke'].rstrip('/'))}: {pd['ahead']} commit(s)")
    if held:
        return _result("pending-deploys", YELLOW,
                       f"{len(held)} live site(s) have reviewed-pending commits", held[:8], cmd)
    return _result("pending-deploys", GREEN, "no production deploy is waiting on review", cmd=cmd)


def probe_terminal_dirs(root="."):
    """Two terminal lug dirs means every reader has to believe the right one."""
    cmd = "find WAI-Harness/spoke/local/lugs/bytype -type d -name done"
    dirs = glob.glob(os.path.join(root, "WAI-Harness/spoke/local/lugs/bytype/*/done"))
    if dirs:
        n = sum(len(glob.glob(os.path.join(d, "*.json"))) for d in dirs)
        return _result("terminal-dirs", RED,
                       f"{len(dirs)} legacy done/ dir(s) present holding {n} lug(s)",
                       [os.path.relpath(d, root) for d in dirs], cmd)
    return _result("terminal-dirs", GREEN, "completed/ is the only terminal dir", cmd=cmd)


PROBES = (probe_master_selfverify, probe_routing, probe_live_hooks,
          probe_pending_deploys, probe_terminal_dirs)

RANK = {RED: 0, UNKNOWN: 1, YELLOW: 2, GREEN: 3}


def run_all(root="."):
    results = []
    for fn in PROBES:
        try:
            results.append(fn(root))
        except Exception as e:                        # a probe must never break the caller
            results.append(_result(fn.__name__, UNKNOWN,
                                   f"probe crashed: {type(e).__name__}: {e}"))
    results.sort(key=lambda r: RANK.get(r["status"], 1))
    worst = results[0]["status"] if results else UNKNOWN
    return {"verdict": worst, "probes": results,
            "counts": {s: sum(1 for r in results if r["status"] == s)
                       for s in (RED, YELLOW, UNKNOWN, GREEN)}}


def render(rep, brief=False):
    """Wakeup-brief lines. Silent when everything is green and --brief is set, so the
    banner only grows when there is something to say."""
    out = []
    if brief:
        bad = [r for r in rep["probes"] if r["status"] in (RED, YELLOW, UNKNOWN)]
        if not bad:
            return []
        for r in bad:
            mark = {RED: "RED", YELLOW: "YEL", UNKNOWN: "UNK"}[r["status"]]
            out.append(f"  [{mark}] {r['probe']}: {r['headline']}")
        return out
    out.append(f"INTEGRITY PROBE — verdict {rep['verdict']}   "
               + "  ".join(f"{k}={v}" for k, v in rep["counts"].items() if v))
    for r in rep["probes"]:
        out.append(f"  [{r['status']:<7}] {r['probe']:<20} {r['headline']}")
        for d in r["detail"]:
            out.append(f"              {d}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="integrity_probe — standing silent-failure oracles")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--brief", action="store_true",
                    help="only non-green lines, for the wakeup banner")
    a = ap.parse_args(argv)
    rep = run_all(a.root)
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        for line in render(rep, brief=a.brief):
            print(line)
    return 0 if rep["verdict"] in (GREEN, YELLOW) else 1


if __name__ == "__main__":
    sys.exit(main())
