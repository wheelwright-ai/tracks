#!/usr/bin/env python3
"""assurance_sweep.py — turn instrument findings into work Ozi can dispatch.

THE THIRD DUTY. The operator's standing mission for Ozi (s138) is completeness,
canonical adherence, and finally SELF-IMPROVEMENT. The first two now have
deterministic instruments — tastegraph_compliance.py and savepoint_walk.py for
completeness, canon_adherence.py for adherence. The third had no mechanism at
all, which is a specific and predictable failure: two good instruments that
nobody runs quietly become two more things that were true once.

WHY THIS SHAPE. Ozi is a dispatch engine over lugs. It does not read reports and
it does not act on prose — it grooms, scores and dispatches lugs from the
backlog. So a finding that is not a lug is invisible to it, no matter how
correct. This tool exists to cross exactly that gap: run the instruments, and
write each finding into the backlog in the only form the engine can act on.

THE DESIGN RULE THAT MATTERS MOST. This sweep never decides that work is
obsolete, never retires anything, and never edits a savepoint. It OPENS lugs
describing what an instrument found, with the instrument's own command recorded
so the next agent can re-run it rather than trusting this one. Everything here is
additive and revertible; the judgement stays with whoever picks the lug up.

IDEMPOTENCE IS LOAD-BEARING. A scheduled sweep that re-opens the same finding
every run would bury the backlog it is meant to improve — the fastest way to make
an assurance loop worthless is to make its output noise. Lug ids are derived
deterministically from the finding, so a repeat sweep updates rather than
duplicates.

Usage:
    assurance_sweep.py run [--dry-run] [--json]
    assurance_sweep.py status
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)

LUG_DIR = "WAI-Harness/spoke/local/lugs/bytype/{type}/open"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _run(cmd, root):
    try:
        p = subprocess.run(cmd, shell=True, cwd=root, capture_output=True,
                           text=True, timeout=300)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (subprocess.TimeoutExpired, OSError) as e:
        return 99, str(e)[:300]


# ---- instruments ------------------------------------------------------------
# Each returns a list of findings. A finding is a dict the lug writer understands.
# An instrument that cannot run reports THAT as a finding rather than staying
# silent — silence is indistinguishable from health, which is the failure mode
# this whole line of work exists to remove.

def probe_canon_adherence(root):
    rc, out = _run(f"python3 {TOOLS}/canon_adherence.py --root . check --json", root)
    if rc == 99:
        return [{"kind": "instrument-broken", "instrument": "canon_adherence",
                 "detail": out[:300], "severity": "high"}]
    try:
        rep = json.loads(out)
    except json.JSONDecodeError:
        return [{"kind": "instrument-broken", "instrument": "canon_adherence",
                 "detail": "output was not JSON", "severity": "high"}]
    if rep.get("ok"):
        return []
    findings = []
    for layer in rep.get("layers", []):
        for name in layer.get("drifted", []):
            findings.append({
                "kind": "canon-drift", "instrument": "canon_adherence",
                "detail": f"{name} differs across {layer['pair']}",
                "severity": "high" if "templates" in layer["pair"] else "medium",
                "recheck": "python3 WAI-Harness/spoke/managed/tools/canon_adherence.py --root . check",
            })
        for name in layer.get("only_in_source", []):
            findings.append({
                "kind": "canon-not-propagated", "instrument": "canon_adherence",
                "detail": f"{name} exists in {layer['pair'].split(' -> ')[0]} but never reached the target",
                "severity": "high",
                "recheck": "python3 WAI-Harness/spoke/managed/tools/canon_adherence.py --root . check",
            })
    return findings


def probe_savepoint_trail(root):
    rc, out = _run(
        f"python3 {TOOLS}/savepoint_walk.py --root . walk --json", root)
    if rc == 99:
        return [{"kind": "instrument-broken", "instrument": "savepoint_walk",
                 "detail": out[:300], "severity": "high"}]
    try:
        rep = json.loads(out)
    except json.JSONDecodeError:
        return [{"kind": "instrument-broken", "instrument": "savepoint_walk",
                 "detail": "output was not JSON", "severity": "high"}]

    findings = []
    for r in rep.get("results", []):
        if r.get("verdict") == "drifted":
            findings.append({
                "kind": "work-drifted", "instrument": "savepoint_walk",
                "detail": f"[{r.get('savepoint')}] {r.get('what')} — {r.get('why')}",
                "severity": "high",
                "recheck": "python3 WAI-Harness/spoke/managed/tools/savepoint_walk.py "
                           "--root . walk --run-commands",
            })
    # Coverage is reported as ONE finding, never one per uncheckable entry —
    # 328 lugs would be a denial-of-service on the operator's backlog.
    unevidenced = rep.get("claimed_verified_but_uncheckable", 0)
    if unevidenced:
        findings.append({
            "kind": "trail-unevidenced", "instrument": "savepoint_walk",
            "detail": f"{unevidenced} work entries claim verified=true with no re-runnable check "
                      f"(trail checkable ratio {rep.get('checkable_ratio', 0):.0%})",
            "severity": "medium",
            "recheck": "python3 WAI-Harness/spoke/managed/tools/savepoint_walk.py --root . coverage",
        })
    return findings


def probe_thread_landing(root):
    rc, out = _run(f"python3 {TOOLS}/thread_landing.py check", root)
    if rc == 99:
        return [{"kind": "instrument-broken", "instrument": "thread_landing",
                 "detail": out[:300], "severity": "medium"}]
    for line in out.splitlines():
        if "landed" in line and "open" in line:
            return [{"kind": "threads-open", "instrument": "thread_landing",
                     "detail": line.strip(), "severity": "low",
                     "recheck": "python3 WAI-Harness/spoke/managed/tools/thread_landing.py "
                                "--run-commands check"}]
    return []


PROBES = [probe_canon_adherence, probe_savepoint_trail, probe_thread_landing]


# ---- lug writing ------------------------------------------------------------

# Volatile substrings that must NOT contribute to a lug's identity. A finding's
# detail carries live numbers ("55 work entries", "13%"), and hashing those made
# the id change every time the metric moved.
_VOLATILE = re.compile(r"\d+")


def _lug_id(f):
    """Deterministic id — a repeat sweep must UPDATE, never duplicate.

    CAUGHT BY DOGFOODING, s138. The first version hashed the raw detail, which
    embeds the current measurement. So "94 entries claim verified=true" and "55
    entries claim verified=true" were DIFFERENT findings by id, and the sweep
    opened a fresh lug every time the number moved — three of them within an
    hour, describing one unchanged problem.

    That is precisely the backlog-burying failure this id scheme exists to
    prevent, and the idempotence tests missed it because they used a fixed detail
    string while real findings carry a moving one. Identity now comes from what
    the finding IS (instrument, kind, and the detail with digits stripped), never
    from its current magnitude.
    """
    stable = _VOLATILE.sub("#", f["detail"][:120])
    h = hashlib.sha1(f"{f['instrument']}|{f['kind']}|{stable}".encode()).hexdigest()[:8]
    return f"assurance-{f['kind']}-{h}-v1"


def _file_targets(f):
    """Where the fix will land.

    An auto-generated lug must meet the SAME completeness bar as a hand-written
    one (taste-user-007) — the lug gate enforces this, and it is right to: a lug
    with no target is a note, and a backlog of notes is what the gate exists to
    prevent. So each finding kind declares where remediation actually happens.
    """
    kind = f.get("kind")
    if kind in ("canon-drift", "canon-not-propagated"):
        # The drifted file name is embedded in the detail as the first token.
        name = f["detail"].split()[0]
        return [f"WAI-Harness/spoke/managed/.claude/commands/{name}",
                f"WAI-Harness/spoke/managed/templates/commands/{name}",
                f".claude/commands/{name}"]
    if kind == "trail-unevidenced":
        return ["WAI-Harness/spoke/local/initiatives/savepoints/",
                "WAI-Harness/spoke/managed/tools/validate_savepoint.py"]
    if kind == "work-drifted":
        return ["WAI-Harness/spoke/local/initiatives/savepoints/"]
    if kind == "threads-open":
        return ["WAI-Harness/spoke/local/resident/digest.json",
                "WAI-Harness/spoke/managed/tools/thread_landing.py"]
    if kind == "instrument-broken":
        return [f"WAI-Harness/spoke/managed/tools/{f.get('instrument', 'unknown')}.py"]
    return ["WAI-Harness/spoke/managed/tools/assurance_sweep.py"]


def _to_lug(f):
    lid = _lug_id(f)
    sev = f.get("severity", "medium")
    return {
        "id": lid,
        "type": "task",
        "title": f"[assurance] {f['kind']}: {f['detail'][:90]}",
        "status": "open",
        "va": "fix",
        "routed_to": "LOCAL",
        "model_fit": "sonnet",
        "model_fit_reason": "Sonnet: the instrument states the defect precisely and the recheck "
                            "command is recorded; this is bounded remediation, not design.",
        "effort": "S",
        "roi": {"high": 7, "medium": 5, "low": 3}.get(sev, 5),
        "created_at": _now(),
        "source": "assurance_sweep",
        "instrument": f["instrument"],
        "perceive": [
            f"{f['instrument']} reported: {f['detail']}",
            "Opened automatically by assurance_sweep.py, which exists to close Ozi's third duty — "
            "self-improvement. An instrument finding that never becomes a lug is invisible to the "
            "dispatch engine no matter how correct it is.",
            "This lug asserts nothing beyond what the instrument reported. Re-run the recheck "
            "command below rather than trusting this description.",
        ],
        "execute": [
            "Re-run the recheck command to confirm the finding still holds — it may already be fixed.",
            "If it holds, remediate the underlying cause, not the symptom.",
            "If the finding is WRONG, fix the instrument; a false finding is a defect in the "
            "instrument and silently closing the lug leaves it to fire again.",
        ],
        "verify": [
            f"recheck passes: {f.get('recheck', 'see instrument')}",
            "the fix addresses the cause, not the report",
        ],
        "acceptance_criteria": [
            "the instrument no longer reports this finding",
            "the recheck command is recorded in the completion evidence",
        ],
        "file_targets": _file_targets(f),
        "recheck_command": f.get("recheck"),
        "_improvement_lenses": {
            "skeptic": "Auto-opened lugs are backlog spam unless each one is real and de-duplicated. "
                       "Id is derived from the finding so repeats update rather than pile up, and "
                       "coverage is one lug rather than one per entry.",
            "architect": "The sweep only OPENS work; it never retires, never edits a savepoint, and "
                         "never decides something is obsolete. Judgement stays with whoever picks "
                         "this up.",
            "naive_reader": "An automated check found something that looks wrong. Re-run the command "
                            "in verify to see for yourself before changing anything.",
        },
        "notes": f"severity={sev}. Auto-generated; safe to close if the recheck passes.",
    }


def sweep(root, dry_run=False):
    findings = []
    for probe in PROBES:
        try:
            findings.extend(probe(root))
        except Exception as e:  # noqa: BLE001 — one broken probe must not kill the sweep
            findings.append({"kind": "instrument-broken", "instrument": probe.__name__,
                             "detail": str(e)[:200], "severity": "high"})

    written, updated = [], []
    for f in findings:
        lug = _to_lug(f)
        d = os.path.join(root, LUG_DIR.format(type=lug["type"]))
        path = os.path.join(d, f"{lug['id']}.json")
        exists = os.path.exists(path)
        if dry_run:
            (updated if exists else written).append(lug["id"])
            continue
        os.makedirs(d, exist_ok=True)
        if exists:
            # Preserve any human edits; refresh only what the instrument owns.
            cur = json.load(open(path))
            cur["perceive"] = lug["perceive"]
            cur["last_seen_at"] = _now()
            json.dump(cur, open(path, "w"), indent=2, ensure_ascii=False)
            updated.append(lug["id"])
        else:
            json.dump(lug, open(path, "w"), indent=2, ensure_ascii=False)
            written.append(lug["id"])

    return {"ok": True, "findings": len(findings), "opened": written,
            "refreshed": updated, "dry_run": dry_run,
            "detail": findings}


def cmd_run(args, root):
    rep = sweep(root, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return 0
    tag = "[dry-run] " if rep["dry_run"] else ""
    print(f"{tag}assurance sweep — {rep['findings']} finding(s)")
    print(f"  opened {len(rep['opened'])} lug(s), refreshed {len(rep['refreshed'])}")
    for f in rep["detail"]:
        print(f"    [{f.get('severity', '?'):6s}] {f['instrument']}: {f['detail'][:96]}")
    if not rep["findings"]:
        print("  No findings. Instruments ran and reported clean.")
    return 0


def cmd_status(args, root):
    d = os.path.join(root, LUG_DIR.format(type="task"))
    n = len([f for f in os.listdir(d) if f.startswith("assurance-")]) if os.path.isdir(d) else 0
    print(f"open assurance lugs: {n}")
    print("Ozi dispatches these like any other lug — that is the point. A finding that")
    print("is not a lug is invisible to the engine, however correct it is.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Turn instrument findings into dispatchable lugs")
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--json", action="store_true")
    sub.add_parser("status")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    return {"run": cmd_run, "status": cmd_status}[args.cmd](args, root)


if __name__ == "__main__":
    sys.exit(main())
