#!/usr/bin/env python3
"""wai_assurance.py — periodic capability assurance: RUN the verification we already
built, maintain a last_green ledger, and flag REGRESSIONS (was-green -> now-red).

Operator s136: "delivered != verified; verification must happen periodically so
functionality is maintained across versions — without it it's hope and a dream."
We already HAVE the oracles (verification_spine, qa_suite_health, fleet_verify,
validate_canonical, the pytest suite) — but NOTHING was scheduled to run them. This
is the keystone of the WAI-QA design (impl-wai-qa-assurance-manifest-v1 +
-fleet-rollup): a deterministic runner + last_green ledger + regression detector.

Per spoke it runs a set of CAPABILITY oracles (each a deterministic check). For each:
  pass -> stamp last_green {ts, sha}; fail -> record red + (if previously green) a REGRESSION.
Ledger: {base}/runtime/assurance-ledger.json. Summary (for cockpit/wakeup) appended to the
hub AP store so the cockpit's events stream shows assurance the same way it shows AP.

Usage:
  wai_assurance.py --spoke <root> [--json] [--quick]
  wai_assurance.py --self
Exit 0 = all green/recovered; 1 = at least one REGRESSION (so a gate/cron can react).
"""
import argparse, datetime, json, os, subprocess, sys

def sh(cwd, *args, timeout=600):
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "")[-2000:], (p.stderr or "")[-1000:]
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:
        return 125, "", str(e)[:300]

def git_sha(root):
    rc, out, _ = sh(root, "git", "-C", root, "rev-parse", "--short", "HEAD")
    return out.strip() if rc == 0 else "unknown"

def capabilities(root, managed, quick):
    """Each capability = a deterministic oracle binding (id, kind, command).
    Bound to what we already HAVE; expandable to per-spec_contract rows later."""
    tools = os.path.join(managed, "tools")
    tests = os.path.join(managed, "tests")
    caps = []
    if os.path.isdir(tests) and any(f.startswith("test_") for f in os.listdir(tests)):
        # the managed pytest suite = the regression backbone
        sel = ["-x"] if quick else []
        caps.append(("pytest.managed-suite", "test",
                     ["python3", "-m", "pytest", tests, "-q", "--no-header", "-p", "no:cacheprovider", *sel]))
    # the spoke's NATIVE suite — repo-root tests/run.sh. For spokes (like basher) whose real
    # regression backbone is a shell gate-runner, NOT pytest under managed/tests, binding only
    # the pytest oracle leaves the actual product surface (lens/zellij/launcher/secrets) UNPROVEN
    # — delivered != verified. Generalizable: any spoke with tests/run.sh gets it bound. In quick
    # mode skip it (full gate-runner is slow); the closeout/pre-distribution proof runs it.
    native = os.path.join(root, "tests", "run.sh")
    if os.path.isfile(native) and not quick:
        caps.append(("tests.native-suite", "test", ["bash", native]))
    # validators — each invoked with its REAL CLI so results are accurate, not false reds
    bind = {
        "validate_canonical.py": ("validate.canonical", ["--spoke-path", root]),
        "v3_path_lint.py":       ("lint.v3-path",       ["--managed", managed]),
        "qa_suite_health.py":    ("qa.suite-health",    []),
    }
    for tool, (cid, extra) in bind.items():
        tp = os.path.join(tools, tool)
        if os.path.isfile(tp):
            caps.append((cid, "validator", ["python3", tp, *extra]))
    # fleet integrity/parity is a FLEET-scope oracle — only meaningful from the master
    fv = os.path.join(tools, "fleet_verify.py")
    if os.path.isfile(fv) and os.path.abspath(root) == "/home/mario/projects/wheelwright/mywheel":
        caps.append(("verify.fleet-parity", "fleet",
                     ["python3", fv, "--root", "/home/mario/projects",
                      "--master", os.path.join(root, "WAI-Harness")]))
    return caps

def inventory(root):
    """PILLAR 1 — what we have: count the production surface (specs/capabilities + delivered lugs)."""
    import glob as _g
    base = os.path.join(root, "WAI-Harness", "spoke", "local")
    specs = len(_g.glob(os.path.join(base, "lugs", "bytype", "spec", "*", "*.json")))
    completed = len(_g.glob(os.path.join(base, "lugs", "bytype", "*", "completed", "*.json")))
    return {"specs": specs, "completed_lugs": completed}

def runtime_health(spoke_id):
    """PILLAR 3 — is it up and running: reachability of the deployed surface. ADVISORY (dev
    servers aren't always up + prod URLs aren't registered yet) — never a regression-halt."""
    import json as _j, urllib.request
    reg = "/home/mario/projects/wheelwright/mywheel/WAI-Harness/hub/local/hub-registry.json"
    try:
        wheels = _j.load(open(reg)).get("wheels", [])
        w = next((x for x in wheels if x.get("wheel_id") == spoke_id), {})
    except Exception:
        w = {}
    url = w.get("prod_url") or w.get("deploy_url") or w.get("live_url")
    prod = bool(url)
    if not url:
        dev = w.get("dev") or {}
        port = dev.get("primary_port")
        if port:
            url = f"http://localhost:{port}/"
    if not url:
        return {"id": "runtime.deployment", "kind": "runtime", "pass": None, "note": "no-url (register prod_url)"}
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "wai-rigger"})
        code = urllib.request.urlopen(req, timeout=6).getcode()
        return {"id": "runtime.deployment", "kind": "runtime", "pass": (200 <= code < 400),
                "note": f"{'prod' if prod else 'dev'} {url} -> {code}", "prod": prod}
    except Exception as e:
        return {"id": "runtime.deployment", "kind": "runtime", "pass": False,
                "note": f"{'prod' if prod else 'dev'} {url} unreachable ({type(e).__name__})", "prod": prod}

def process(root, quick=False):
    res = {"spoke": root, "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "sha": git_sha(root), "capabilities": [], "regressions": [], "green": 0, "red": 0}
    managed = os.path.join(root, "WAI-Harness", "spoke", "managed")
    if not os.path.isdir(managed):
        managed = os.path.join(root, "WAI-Spoke")  # v3 fallback (rare)
    base = os.path.join(root, "WAI-Harness", "spoke", "local")
    if not os.path.isdir(base):
        base = os.path.join(root, "WAI-Spoke")
    ledger_path = os.path.join(base, "runtime", "assurance-ledger.json")
    prior = {}
    try:
        prior = {c["id"]: c for c in json.load(open(ledger_path)).get("capabilities", [])}
    except Exception:
        pass

    for cid, kind, cmd in capabilities(root, managed, quick):
        rc, out, err = sh(root, *cmd)
        ok = (rc == 0)
        row = {"id": cid, "kind": kind, "pass": ok, "rc": rc,
               "checked_at": res["ts"], "checked_sha": res["sha"]}
        was_green = prior.get(cid, {}).get("last_green") is not None
        prev_ok = prior.get(cid, {}).get("pass")
        if ok:
            row["last_green"] = {"ts": res["ts"], "sha": res["sha"]}
            res["green"] += 1
        else:
            # keep the historical last_green so we can see WHEN it last worked
            row["last_green"] = prior.get(cid, {}).get("last_green")
            row["fail_excerpt"] = (out + err).strip()[-300:]
            res["red"] += 1
            if was_green or prev_ok:  # it worked before, now it doesn't = REGRESSION
                res["regressions"].append(cid)
                row["regression"] = True
        res["capabilities"].append(row)

    # PILLAR 1 (what we have) + PILLAR 3 (up & running) — advisory, regression-exempt
    res["inventory"] = inventory(root)
    rt = runtime_health(os.path.basename(root.rstrip("/")))
    rt["checked_at"] = res["ts"]
    res["runtime"] = rt
    res["capabilities"].append(rt)

    if not os.path.isdir(os.path.dirname(ledger_path)):
        os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
    json.dump({"updated_at": res["ts"], "sha": res["sha"], "inventory": res["inventory"],
               "runtime": res["runtime"], "capabilities": res["capabilities"]},
              open(ledger_path, "w"), indent=2)

    # mirror a one-line summary into the hub AP store so the cockpit surfaces assurance
    store = os.path.join("/home/mario/projects/wheelwright/mywheel",
                         "WAI-Harness", "hub", "local", "ap-runs", "events.jsonl")
    try:
        if os.path.isdir(os.path.dirname(store)):
            ev = {"ts": res["ts"], "run_id": "assurance", "spoke": os.path.basename(root.rstrip("/")),
                  "kind": "assurance", "green": res["green"], "red": res["red"],
                  "regressions": len(res["regressions"]), "regression_ids": res["regressions"],
                  "inventory": res["inventory"], "runtime": res["runtime"].get("note")}
            with open(store, "a") as f:
                f.write(json.dumps(ev) + "\n")
    except Exception:
        pass
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spoke"); ap.add_argument("--self", action="store_true")
    ap.add_argument("--quick", action="store_true"); ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = "/home/mario/projects/wheelwright/mywheel" if a.self else a.spoke
    if not root:
        ap.error("need --spoke or --self")
    r = process(root, quick=a.quick)
    if a.json:
        print(json.dumps(r, indent=2))
    else:
        inv = r.get("inventory", {}); rt = r.get("runtime", {})
        print(f"Proofer (proof test) {os.path.basename(root.rstrip('/'))}:")
        print(f"  pillar1 inventory : {inv.get('specs','?')} specs, {inv.get('completed_lugs','?')} delivered lugs")
        print(f"  pillar2 retention : green={r['green']} red={r['red']} "
              f"regressions={len(r['regressions'])}{(' -> ' + ','.join(r['regressions'])) if r['regressions'] else ''}")
        print(f"  pillar3 runtime   : {rt.get('note','n/a')} ({'UP' if rt.get('pass') else ('?' if rt.get('pass') is None else 'DOWN')})")
        for c in r["capabilities"]:
            lg = (c.get("last_green") or {}).get("ts", "never")[:19]
            if c.get("pass") is None:
                verdict, flag = "ADVS", f" ({c.get('note','advisory')})"
            elif c["pass"]:
                verdict, flag = "PASS", ""
            else:
                verdict = "FAIL"
                flag = " !!REGRESSION" if c.get("regression") else (f" ({c.get('note')})" if c.get("note") else f" (red; last_green {lg})")
            print(f"   {verdict}  {c['id']:26}{flag}")
    return 1 if r["regressions"] else 0

if __name__ == "__main__":
    sys.exit(main())
