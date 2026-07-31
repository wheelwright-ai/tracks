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
import time
import datetime as _dt

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


ACTIVATION_MANIFEST = "WAI-Harness/hub/local/registry/activation-manifest.json"


def probe_activation_liveness(root="."):
    """A mechanism claimed ACTIVE must have RUN. Presence is not liveness.

    WHY THIS PROBE EXISTS (session 139, and it is about the reporting layer, not
    the code). The agent told the operator "Herald is already active" on the
    evidence of a line in session-start.sh. Herald had 0 processes and 4 empty
    queues — it had never moved a single message in its life. In the same reply
    it reported the TasteGraph as "distributed to 16 spokes" on the evidence of
    a receipt file, when the tool that wrote that receipt explicitly never copies
    anything.

    Both were the same error, and it is the error this whole file exists to
    catch, committed by the thing doing the catching: EVIDENCE OF PRESENCE
    ACCEPTED AS EVIDENCE OF FUNCTION. The wheel already wrote the correct rule
    down — groups.json's propagation_contract requires "activation live
    (crontab -l / process check, NEVER file presence)" — and nothing anywhere
    enforced it. A rule stated once in a registry nobody executes is prose, and
    the converge consent gate already taught us prose is not a gate.

    So liveness here is only ever one of three OBSERVATIONS:
      cron    — the schedule actually holds an active (non-comment) entry
      process — something is running right now
      artifact— a timestamped output exists and is fresher than max_age_days
    Never "the tool file exists". A mechanism whose check cannot run is UNKNOWN,
    never GREEN, per this file's contract.
    """
    cmd = "python3 WAI-Harness/spoke/managed/tools/integrity_probe.py --probe activation-liveness"
    path = os.path.join(root, ACTIVATION_MANIFEST)
    if not os.path.isfile(path):
        return _result("activation-liveness", UNKNOWN,
                       "no activation-manifest.json — nothing declares what is claimed ACTIVE",
                       detail=[f"expected at {ACTIVATION_MANIFEST}"], cmd=cmd)
    try:
        entries = json.load(open(path)).get("mechanisms", [])
    except Exception as e:
        return _result("activation-liveness", UNKNOWN, f"unreadable manifest: {e}", cmd=cmd)

    try:
        crontab = subprocess.run(["crontab", "-l"], capture_output=True, text=True,
                                 timeout=15).stdout
    except Exception:
        crontab = ""
    active_cron = "\n".join(l for l in crontab.splitlines() if l.strip()
                            and not l.strip().startswith("#"))

    dead, unknown, live = [], [], 0
    for m in entries:
        name, kind, needle = m.get("name", "?"), m.get("evidence"), m.get("match", "")
        if kind == "cron":
            (live := live + 1) if needle in active_cron else dead.append(
                f"{name}: claimed active, NO active cron entry matching '{needle}'")
        elif kind == "process":
            try:
                ps = subprocess.run(["pgrep", "-fa", needle], capture_output=True,
                                    text=True, timeout=15).stdout.strip()
            except Exception:
                unknown.append(f"{name}: cannot run pgrep"); continue
            (live := live + 1) if ps else dead.append(
                f"{name}: claimed active, NO running process matching '{needle}'")
        elif kind == "artifact":
            p = os.path.join(root, needle)
            if not os.path.exists(p):
                dead.append(f"{name}: claimed active, artifact never produced ({needle})"); continue
            age_days = (time.time() - os.path.getmtime(p)) / 86400.0
            maxage = float(m.get("max_age_days", 7))
            (live := live + 1) if age_days <= maxage else dead.append(
                f"{name}: last ran {age_days:.1f}d ago, stale past {maxage}d ({needle})")
        else:
            unknown.append(f"{name}: unknown evidence kind {kind!r}")

    if dead:
        return _result("activation-liveness", RED,
                       f"{len(dead)} mechanism(s) claimed ACTIVE with no evidence of ever running",
                       detail=dead + unknown, cmd=cmd)
    if unknown:
        return _result("activation-liveness", UNKNOWN,
                       f"{len(unknown)} mechanism(s) could not be checked", detail=unknown, cmd=cmd)
    return _result("activation-liveness", GREEN,
                   f"{live} claimed-active mechanism(s) observed running", cmd=cmd)


def emit_lugs(results, root="."):
    """Turn every non-GREEN finding into a LUG, and close the lug when it clears.

    THE OPEN CIRCLE THIS SHUTS. Until now these probes only PRINTED. A finding
    reached the backlog when a human happened to read the output and happened to
    write it up — so pending-deploys sat YELLOW across a whole session and became
    work only because someone finally hand-authored a lug for it. Any control
    whose last mile is "and then somebody notices" fails exactly when attention is
    scarce, which is the same condition under which the finding matters most.
    (operator, s139: "the continual misses are concerning and need to be
    mitigated".)

    Both directions, or it is not a circle:
      non-GREEN -> ensure an open lug exists (idempotent; never duplicates)
      GREEN     -> close that lug if it is open (the finding is genuinely gone)

    The lug's `verify` is the probe's own `reproduce` command, so the landing
    condition is the thing that raised the alarm — it cannot drift from it.
    """
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    base = os.path.join(root, "WAI-Harness/spoke/local/lugs/bytype/impl")
    opened, closed = [], []
    for r in results:
        lug_id = f"impl-oracle-{r['probe']}-v1"
        open_p = os.path.join(base, "open", f"{lug_id}.json")
        done_p = os.path.join(base, "completed", f"{lug_id}.json")
        in_prog = os.path.join(base, "in_progress", f"{lug_id}.json")

        if r["status"] == GREEN:
            # circle closes: the alarm cleared, so retire its lug.
            if os.path.exists(open_p):
                try:
                    d = json.load(open(open_p))
                    d["status"] = "completed"
                    d["completed_at"] = now
                    d["_closed_by"] = f"integrity_probe: {r['probe']} returned GREEN ({r['headline']})"
                    os.makedirs(os.path.dirname(done_p), exist_ok=True)
                    json.dump(d, open(done_p, "w"), indent=2)
                    os.remove(open_p)
                    closed.append(lug_id)
                except Exception:
                    pass
            continue

        if r["status"] == UNKNOWN and not r.get("detail"):
            continue                      # nothing actionable to say yet
        if os.path.exists(open_p) or os.path.exists(in_prog):
            continue                      # already on the backlog — never duplicate

        os.makedirs(os.path.dirname(open_p), exist_ok=True)
        repro = r.get("reproduce") or ""
        json.dump({
            "id": lug_id, "type": "impl", "status": "open", "routed_to": "LOCAL",
            "created_at": now, "created_by": "integrity_probe --emit-lugs",
            "title": f"Standing oracle '{r['probe']}' is {r['status']}: {r['headline']}",
            "one_liner": (f"Raised automatically by integrity_probe. {r['headline']}. "
                          "This lug exists so the finding survives the log it was printed to."),
            "impact": 8 if r["status"] == RED else 5,
            "effort": "M", "effort_score": 3,
            "urgency": 5 if r["status"] == RED else 3,
            "model_fit": "sonnet",
            "model_fit_reason": "Bounded remediation against a probe that states its own reproduce command.",
            "va": "build", "execute_when": "now",
            "perceive": [f"Probe {r['probe']} reported {r['status']}: {r['headline']}"]
                        + [str(x) for x in (r.get("detail") or [])[:8]],
            "execute": ["Fix the underlying condition the probe names.",
                        "Re-run the probe; it must report GREEN.",
                        "Do NOT close this lug by hand — a GREEN probe run closes it automatically."],
            "verify": [f"cmd: {repro}" if repro else
                       "cmd: python3 WAI-Harness/spoke/managed/tools/integrity_probe.py --root . --brief"],
            "acceptance_criteria": [f"integrity_probe reports {r['probe']} as GREEN.",
                                    "The closure is produced by a probe run, not by hand-editing status."],
            "file_targets": ["WAI-Harness/spoke/managed/tools/integrity_probe.py"],
            "_improvement_lenses": {
                "skeptic": ("Auto-raised lugs can become noise. Mitigated three ways: one lug per PROBE "
                            "(not per occurrence), never duplicated while open, and auto-closed the moment "
                            "the probe goes GREEN — so a flapping condition does not accumulate."),
                "architect": ("The probe already computes the landing condition (its reproduce command); "
                              "reusing it as the lug's verify means the alarm and its definition of done "
                              "cannot drift apart."),
                "naive_reader": ("Something is wrong and it is on the backlog with the command that proves "
                                 "it. I do not have to have read a log at the right moment."),
            },
            "_oracle": {"probe": r["probe"], "status": r["status"], "first_seen": now},
        }, open(open_p, "w"), indent=2)
        opened.append(lug_id)
    return {"opened": opened, "closed": closed}


DEPRECATED_ROOTS = ("/home/mario/projects/wheelwright/framework",
                    "/home/mario/projects/wheelwright/hub")


def probe_deprecated_repo_refs(root="."):
    """Nothing scheduled may execute out of a DEPRECATED repo.

    Both deprecated roots still exist on disk, which is precisely why 49 files
    could point at them for months while every advisor run "succeeded" against
    dead data. Deleting them was considered and REJECTED on inspection: they
    hold 3,853 uncommitted files and 2 unpushed commits between them, and live
    references remain outside mywheel (basher/tests/run.sh, minder tests,
    ezorg/update_state.sh). Removing them would destroy work and break siblings.

    So the risk is monitored instead of removed. The thing that actually hurts
    is EXECUTION out of a dead repo — a daily cron entry was running
    hub/tools/triumvirate_refresh.sh until 2026-07-27 — so that is what this
    watches: the schedule. A file merely mentioning the path is not the defect.
    """
    cmd = "crontab -l | grep -v '^\\s*#' | grep -E 'wheelwright/(framework|hub)/'"
    try:
        crontab = subprocess.run(["crontab", "-l"], capture_output=True, text=True,
                                 timeout=15).stdout
    except Exception as e:
        return _result("deprecated-repo-refs", UNKNOWN, f"cannot read crontab: {e}", cmd=cmd)
    live = [l.strip() for l in crontab.splitlines()
            if l.strip() and not l.strip().startswith("#")
            and any(f"{d}/" in l for d in DEPRECATED_ROOTS)]
    if live:
        return _result("deprecated-repo-refs", RED,
                       f"{len(live)} scheduled job(s) execute out of a DEPRECATED repo",
                       [l[:120] for l in live[:5]], cmd)
    return _result("deprecated-repo-refs", GREEN,
                   "no scheduled job executes out of a deprecated repo", cmd=cmd)


PROBES = (probe_master_selfverify, probe_routing, probe_live_hooks,
          probe_pending_deploys, probe_terminal_dirs, probe_activation_liveness,
          probe_deprecated_repo_refs)

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
    ap.add_argument("--emit-lugs", action="store_true",
                    help="raise a lug for every non-GREEN finding and close it when the probe "
                         "goes GREEN — so a finding survives the log it was printed to")
    a = ap.parse_args(argv)
    rep = run_all(a.root)
    if a.emit_lugs:
        rep["lugs"] = emit_lugs(rep["probes"], a.root)
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        for line in render(rep, brief=a.brief):
            print(line)
        if a.emit_lugs:
            lg = rep.get("lugs") or {}
            if lg.get("opened"):
                print(f"  lugs OPENED : {', '.join(lg['opened'])}")
            if lg.get("closed"):
                print(f"  lugs CLOSED : {', '.join(lg['closed'])}")
            if not lg.get("opened") and not lg.get("closed"):
                print("  lugs: no change (findings already on the backlog)")
    return 0 if rep["verdict"] in (GREEN, YELLOW) else 1


if __name__ == "__main__":
    sys.exit(main())
