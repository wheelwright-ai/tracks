#!/usr/bin/env python3
"""phase_certify.py — the phase gate. Runs BOTH benches and refuses to certify without them.

WHY THIS EXISTS
---------------
Migration doctrine 5 says "a phase certifies only when both benches pass." Until now that
was a sentence in a document and a human running two commands in the right order. Two gaps
made it weaker than it reads:

  1. bench_assert built the attachment POINT for bench results but nothing ever READ it
     before letting a phase advance. Its own docstring says so.
  2. Phase 0 certified with "Assertions: none declared" on both benches. Drift-absence
     alone is a condition a phase that built NOTHING would also satisfy.

This tool closes both. It reads the declared assertions for the phase, runs both benches
with them, attaches both results, and exits non-zero unless every one of these holds:

  - both benches ran
  - both report drift=False
  - every declared assertion passed
  - the phase has an assertions entry at all

That last one matters most. An undeclared phase is REFUSED, not defaulted to an empty
assertion list -- defaulting to empty is exactly how Phase 0 certified without any.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not decide the tree is quiet. A brownfield bench run while files are changing
reports real drift, and that is correct behaviour, not a false alarm. Settle the tree
first (Ruling 16: commit before every phase completion) and run it again.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
TOOLS = REPO / "WAI-Harness/spoke/managed/tools"
ASSERTIONS = REPO / "WAI-Harness/spoke/managed/registry/v5-phase-assertions.json"
BASE = REPO / "WAI-Harness/spoke/local"

BENCHES = ("brownfield", "greenfield")


class GateRefused(RuntimeError):
    """The gate cannot run honestly -- distinct from the gate running and failing."""


def load_assertions(phase: str) -> dict:
    if not ASSERTIONS.exists():
        raise GateRefused(f"no assertions registry at {ASSERTIONS}")
    reg = json.loads(ASSERTIONS.read_text())
    entry = reg.get(str(phase))
    if entry is None:
        raise GateRefused(
            f"phase {phase} has no entry in {ASSERTIONS.name}. "
            "Declare what must be true for this phase before certifying it -- "
            "an undeclared phase is refused, never defaulted to zero assertions."
        )
    for bench in BENCHES:
        if bench not in entry:
            raise GateRefused(f"phase {phase} declares no assertions for the {bench} bench")
    return entry


def find_cert_lug(phase: str) -> Path:
    for state in ("in_progress", "completed", "open"):
        p = BASE / f"lugs/bytype/completion/{state}/cert-v5-phase{phase}-v1.json"
        if p.exists():
            return p
    raise GateRefused(f"no certification lug cert-v5-phase{phase}-v1 found in any status dir")


def run_bench(root: Path, bench: str, asserts: list[str], cert_lug: Path, workdir: Path) -> dict:
    before = workdir / f"phase-{bench}-before.json"
    after = workdir / f"phase-{bench}-after.json"

    snap = subprocess.run(
        [sys.executable, str(TOOLS / "bench_snapshot.py"), "--root", str(root),
         "--out", str(before), "--label", bench],
        capture_output=True, text=True, timeout=900,
    )
    if snap.returncode != 0:
        return {"bench": bench, "ran": False, "error": (snap.stderr or snap.stdout).strip()[:500]}

    cmd = [sys.executable, str(TOOLS / "bench_assert.py"), "--root", str(root),
           "--snapshot", str(before), "--out", str(after),
           "--attach-to-lug", str(cert_lug), "--bench-label", bench]
    for a in asserts:
        cmd += ["--assert", a]

    res = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    out = {"bench": bench, "ran": True, "returncode": res.returncode,
           "stdout": (res.stdout or "").strip()[-600:]}
    if after.exists():
        data = json.loads(after.read_text())
        out["drift"] = data.get("drift")
        out["assertions"] = data.get("assertions") or []
        out["assertions_all_pass"] = data.get("assertions_all_pass")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", required=True)
    ap.add_argument("--brownfield-root", default=str(REPO))
    ap.add_argument("--greenfield-root", default="/home/mario/projects/wheelwright/v5-dogfood")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        entry = load_assertions(args.phase)
        cert_lug = find_cert_lug(args.phase)
    except GateRefused as exc:
        print(f"[phase-certify] REFUSED: {exc}", file=sys.stderr)
        return 3

    roots = {"brownfield": Path(args.brownfield_root), "greenfield": Path(args.greenfield_root)}
    results = {}

    # Bench outputs go OUTSIDE the scanned trees. Writing them inside makes the tool's own
    # output land in the comparison window and register as drift -- observed and traced
    # once already; not repeating it.
    with tempfile.TemporaryDirectory(prefix="phase-certify-") as tmp:
        workdir = Path(tmp)
        for bench in BENCHES:
            root = roots[bench]
            if not root.exists():
                results[bench] = {"bench": bench, "ran": False, "error": f"root does not exist: {root}"}
                continue
            results[bench] = run_bench(root, bench, entry[bench], cert_lug, workdir)

    failures: list[str] = []
    for bench in BENCHES:
        r = results[bench]
        if not r.get("ran"):
            failures.append(f"{bench}: did not run — {r.get('error', 'unknown')}")
            continue
        if r.get("drift") is not False:
            failures.append(f"{bench}: drift={r.get('drift')} (expected False)")
        failed_asserts = [a for a in (r.get("assertions") or []) if not a.get("pass")]
        for a in failed_asserts:
            failures.append(f"{bench}: assertion failed — {a.get('expr', a)}")
        if not (r.get("assertions") or []):
            failures.append(f"{bench}: zero assertions evaluated — declared list did not reach the bench")

    verdict = "CERTIFIED" if not failures else "NOT CERTIFIED"
    payload = {"phase": args.phase, "title": entry.get("title"), "verdict": verdict,
               "cert_lug": str(cert_lug.relative_to(REPO)), "benches": results, "failures": failures}

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"[phase-certify] phase {args.phase} — {entry.get('title', '')}")
        for bench in BENCHES:
            r = results[bench]
            n_ok = sum(1 for a in (r.get("assertions") or []) if a.get("pass"))
            n_all = len(r.get("assertions") or [])
            print(f"  {bench:<11} ran={r.get('ran')} drift={r.get('drift')} assertions={n_ok}/{n_all}")
        if failures:
            print("  failures:")
            for f in failures:
                print(f"    - {f}")
        print(f"  verdict: {verdict}")

    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
