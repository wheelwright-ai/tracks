#!/usr/bin/env python3
"""landing_ledger.py — an agreement is DONE when it has LANDED, provably, everywhere.

THE PRINCIPLE (operator, s138: "Landing these is equally as important as ideating
them"): a fleet-wide agreement that lives only in the canonical repo is not done —
it is stranded upstream. This session proved the failure mode four separate ways
(templates that never propagated a fix, a launcher fork the TUI silently ran,
preferences no session ever read, hooks registered but never distributed).

THE INSTRUMENT: a ledger of LANDINGS. Each landing = one agreement + a per-spoke
ORACLE — a shell command run inside the spoke that exits 0 if the agreement is
genuinely in force there. `check` sweeps the fleet (spoke paths from the hub
registry — never guessed) and renders the operator's stated format: a christmas
tree of GREEN / YELLOW / RED per spoke per landing.

  GREEN   oracle exit 0   — landed and in force
  YELLOW  oracle exit 10  — partially landed (the oracle itself decides why)
  RED     any other exit  — not landed / regressed
  n/a     spoke doesn't match the landing's `applies` filter

Registry: hub/local/landings.json. Verbs: add | check | report.
The fix for a RED cell is DISTRIBUTION WORK (route to Basher), never editing the
ledger. Oracles run READ-ONLY; an oracle that mutates a spoke is a defect.
"""
import argparse, json, os, subprocess, sys, datetime

LEDGER = "WAI-Harness/hub/local/landings.json"
HUB_REGISTRY = "WAI-Harness/hub/local/hub-registry.json"
G, Y, R = "\033[32mGREEN \033[0m", "\033[33mYELLOW\033[0m", "\033[31mRED   \033[0m"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path, default):
    if os.path.isfile(path):
        with open(path) as f:
            return json.load(f)
    return default


def spokes(reg_path):
    reg = load(reg_path, {})
    out = []
    for w in reg.get("wheels", []):
        p = w.get("path")
        if p and os.path.isdir(p):
            out.append({"id": w.get("wheel_id") or os.path.basename(p), "path": p,
                        "deprecated": bool(w.get("deprecated"))})
    return out


def applies(landing, sp):
    if sp["deprecated"]:
        return False
    f = landing.get("applies", "harnessed")
    if f == "all":
        return True
    if f == "harnessed":
        return os.path.isdir(os.path.join(sp["path"], "WAI-Harness", "spoke"))
    if isinstance(f, list):
        return sp["id"] in f
    return True


def run_oracle(landing, sp, timeout):
    cmd = landing["oracle"].replace("{spoke}", sp["path"])
    try:
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "RED", "oracle timeout"
    if r.returncode == 0:
        return "GREEN", ""
    if r.returncode == 10:
        return "YELLOW", (r.stdout or r.stderr).strip().splitlines()[-1][:80] if (r.stdout or r.stderr).strip() else "partial"
    tail = (r.stdout or r.stderr).strip().splitlines()
    return "RED", (tail[-1][:80] if tail else f"exit {r.returncode}")


def cmd_add(a):
    led = load(a.ledger, {"landings": {}})
    led["landings"][a.id] = {
        "id": a.id, "title": a.title, "agreed": a.agreed or _now(),
        "oracle": a.oracle, "applies": a.applies,
        "owner_of_fix": a.owner_of_fix, "added_at": _now(),
    }
    os.makedirs(os.path.dirname(a.ledger), exist_ok=True)
    tmp = a.ledger + ".tmp"
    with open(tmp, "w") as f:
        json.dump(led, f, indent=2, ensure_ascii=False)
    os.replace(tmp, a.ledger)
    print(f"landing defined: {a.id}")
    return 0


def cmd_check(a):
    led = load(a.ledger, {"landings": {}})
    lands = sorted(led.get("landings", {}).values(), key=lambda l: l["id"])
    if not lands:
        print("ledger empty — define landings with `add`")
        return 1
    sps = [s for s in spokes(a.hub_registry) if not s["deprecated"]]
    if a.spoke:
        sps = [s for s in sps if s["id"] == a.spoke or s["path"] == a.spoke]
    results, reds = {}, 0
    for sp in sps:
        row = {}
        for l in lands:
            if not applies(l, sp):
                row[l["id"]] = ("n/a", "")
                continue
            status, why = run_oracle(l, sp, a.timeout)
            row[l["id"]] = (status, why)
            if status == "RED":
                reds += 1
        results[sp["id"]] = row

    # The tree — operator's stated format: scannable indicators per spoke.
    ids = [l["id"] for l in lands]
    head = "SPOKE".ljust(22) + " ".join(i[:14].ljust(14) for i in ids)
    print(f"LANDING TREE — {len(lands)} agreement(s) x {len(sps)} spoke(s)   ({_now()})")
    print(head)
    mark = {"GREEN": G, "YELLOW": Y, "RED": R, "n/a": "  --  "}
    for sid, row in sorted(results.items()):
        cells = []
        for i in ids:
            st, _ = row[i]
            cells.append(mark[st].ljust(14) if st != "n/a" else "  --  ".ljust(14))
        print(sid[:21].ljust(22) + " ".join(c for c in cells))
    for sid, row in sorted(results.items()):
        for i, (st, why) in row.items():
            if st in ("RED", "YELLOW") and why:
                print(f"  {st:6} {sid} :: {i} :: {why}")
    snap = {"at": _now(), "spokes": {sid: {i: st for i, (st, _) in row.items()} for sid, row in results.items()}}
    hist = a.ledger.replace(".json", "-history.jsonl")
    with open(hist, "a") as f:
        f.write(json.dumps(snap) + "\n")
    tot = sum(1 for row in results.values() for st, _ in row.values() if st != "n/a")
    green = sum(1 for row in results.values() for st, _ in row.values() if st == "GREEN")
    print(f"\nlanded: {green}/{tot} cells GREEN | {reds} RED — every RED is distribution work, not ledger work")
    return 2 if reds and a.strict else 0


def cmd_report(a):
    hist = a.ledger.replace(".json", "-history.jsonl")
    if not os.path.isfile(hist):
        print("no check history yet")
        return 1
    rows = [json.loads(l) for l in open(hist) if l.strip()]
    print("LANDED-CELL TRAJECTORY (GREEN / total, per sweep)")
    for r in rows[-12:]:
        cells = [st for sp in r["spokes"].values() for st in sp.values() if st != "n/a"]
        g = sum(1 for c in cells if c == "GREEN")
        print(f"  {r['at']}  {g}/{len(cells)}  {'#' * int(20 * g / max(1, len(cells)))}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledger", default=LEDGER)
    ap.add_argument("--hub-registry", default=HUB_REGISTRY)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ad = sub.add_parser("add")
    ad.add_argument("--id", required=True)
    ad.add_argument("--title", required=True)
    ad.add_argument("--oracle", required=True, help="bash, {spoke} substituted; exit 0=GREEN 10=YELLOW else RED; READ-ONLY")
    ad.add_argument("--applies", default="harnessed")
    ad.add_argument("--owner-of-fix", default="basher", dest="owner_of_fix")
    ad.add_argument("--agreed", default=None)
    ck = sub.add_parser("check")
    ck.add_argument("--spoke", default=None)
    ck.add_argument("--timeout", type=int, default=30)
    ck.add_argument("--strict", action="store_true")
    sub.add_parser("report")
    a = ap.parse_args(argv)
    return {"add": cmd_add, "check": cmd_check, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
