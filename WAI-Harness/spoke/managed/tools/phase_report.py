#!/usr/bin/env python3
"""phase_report.py — assemble a phase certification report FROM EVIDENCE.

WHY THIS EXISTS
---------------
The operator asked what landed in a phase and how it was verified on both the
greenfield and brownfield benches. That question gets asked once per phase, nine
times, and the honest answer is not something to write by hand each time --- a
hand-written report is a claim, and a claim is exactly what Doctrine 1 refuses to
admit ("admission by evidence, not declaration").

So the report is GENERATED from the certification lug's attached evidence. If a
bench never ran, the report says so in the place the result would have been. There
is no prose path that can assert a pass the evidence does not carry.

Migration doctrine 5 (both benches, every phase) is the contract this renders.

USAGE
    python3 phase_report.py --phase 0
    python3 phase_report.py --lug <path> --out docs/v5-phase0-certification-report.md
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

BASE = "WAI-Harness/spoke/local"

# Every bench required by doctrine 5. A phase that reports on fewer is incomplete
# by construction, not by opinion.
REQUIRED_BENCHES = ("greenfield", "brownfield")


def _find_lug(phase: int) -> Path:
    for state in ("in_progress", "completed", "open"):
        p = Path(f"{BASE}/lugs/bytype/completion/{state}/cert-v5-phase{phase}-v1.json")
        if p.exists():
            return p
    raise SystemExit(f"no certification lug found for phase {phase}")


def load_needs_you(initiative_id: str | None) -> list[dict]:
    """Open `needs-you` lugs for this initiative — the canonical home for operator questions.

    Operator directive (s140): "The questions should be kept in lugs themselves that
    require user review under this v5 initiative lets use the solutions we have in hand."

    An earlier draft stored questions in a field on the certification lug. That was a
    second, weaker copy of a mechanism the wheel already has: `needs-you` is an existing
    lug type with a lifecycle, so a question asked that way can be tracked, aged, and
    RESOLVED. A question in a report field can only be read. The report reads the lugs;
    it does not own them.
    """
    if not initiative_id:
        return []
    out = []
    for p in sorted(Path(f"{BASE}/lugs/bytype/needs-you/open").glob("*.json")):
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        if d.get("initiative_id") == initiative_id:
            out.append(d)
    return out


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return ""


def _bench_block(label: str, result: dict | None) -> list[str]:
    """Render one bench. Absence is reported, never smoothed over."""
    out = [f"### {label.capitalize()} bench", ""]
    if not result:
        out += [
            f"**NOT RUN.** No `bench_results.{label}` is attached to the certification lug.",
            "Doctrine 5 requires both benches, so this phase is not certified.",
            "",
        ]
        return out

    drift = result.get("drift")
    verdict = "no drift" if drift is False else ("DRIFT DETECTED" if drift is True else "unknown")
    out += [
        f"- Root: `{result.get('snapshot_root', 'unknown')}`",
        f"- Captured: {result.get('captured_at', 'unknown')}",
        f"- Result: **{verdict}**",
    ]

    assertions = result.get("assertions") or []
    if assertions:
        passed = sum(1 for a in assertions if a.get("pass"))
        out.append(f"- Assertions: {passed}/{len(assertions)} pass")
        for a in assertions:
            mark = "PASS" if a.get("pass") else "FAIL"
            # bench_assert names the assertion 'spec'. Reading 'expr' first fell through to
            # the whole dict, so every line rendered as a raw repr -- unreadable, which
            # defeats the point of a report someone is meant to skim.
            spec = a.get("spec") or a.get("expr") or a
            out.append(f"    - [{mark}] `{spec}`")
            if not a.get("pass") and a.get("detail"):
                out.append(f"        {a['detail']}")
    else:
        out.append("- Assertions: none declared for this phase")

    for key, title in (("manifest_diff", "File manifest"), ("lug_count_diff", "Lug counts"),
                       ("oracle_diff", "Oracle verdicts")):
        d = result.get(key)
        if d:
            out.append(f"- {title}: {json.dumps(d)[:400]}")
    out.append("")
    return out


def build(lug_path: Path) -> str:
    lug = json.loads(lug_path.read_text())
    phase = lug.get("phase", "?")
    bench = lug.get("bench_results") or {}
    gates = lug.get("gate_oracles") or {}
    evidence = lug.get("evidence") or {}

    certified = all(
        isinstance(bench.get(b), dict) and bench[b].get("drift") is False
        for b in REQUIRED_BENCHES
    )

    L: list[str] = []
    L += [f"# Wheelwright v5 — Phase {phase} certification report", ""]
    L += [
        f"**Verdict:** {'CERTIFIED' if certified else 'NOT CERTIFIED'}",
        f"**Certification lug:** `{lug.get('id')}`",
        f"**Initiative:** `{lug.get('initiative_id')}`",
        f"**Commit:** `{lug.get('git_sha', _git('rev-parse', 'HEAD'))[:12]}`",
        "",
        "Generated from the certification lug's attached evidence by `phase_report.py`.",
        "Nothing here is asserted in prose — a bench that did not run says so where its",
        "result would be.",
        "",
        "---",
        "",
    ]

    # SYNTHESIS FIRST. The operator may read only this section and never reach the body
    # (tastegraph: communication-synthesis-first-he-may-never-read-the-body). Written so
    # that reading nothing else is still enough to act, object, or redirect. This is not a
    # preface to the report -- it is the report, and the rest is the supporting evidence.
    L += ["## In short", ""]
    if certified:
        L += [
            f"Phase {phase} is **finished and proven**. It was tested two ways: on a brand-new",
            "project that had never seen this system before, and on this project itself, before",
            "and after. Neither showed unintended change.",
        ]
    else:
        L += [
            f"Phase {phase} is **not finished**. The evidence needed to call it done is missing",
            "or shows unexplained change. What is missing is listed at the end of this document.",
        ]
    L += ["", f"It covered {len(lug.get('covers_lugs', []))} piece(s) of work:", ""]
    for lid in lug.get("covers_lugs", []):
        L.append(f"- `{lid}`")
    gate = lug.get("open_gate") or {}
    if gate:
        state = gate.get("state", "unknown")
        L += ["", f"**Waiting on a person:** {gate.get('item', 'unspecified')} — {state}."]
        if gate.get("operator_action") and state != "CLEARED":
            L.append(f"What to do: {gate['operator_action']}")
    L += ["", "Everything below is the supporting evidence.", "", "---", ""]

    L += ["## What this phase covers", ""]
    for lid in lug.get("covers_lugs", []):
        L.append(f"- `{lid}`")
    L.append("")

    L += ["## How it was verified — both benches", "",
          "Migration doctrine 5: *a phase certifies only when both benches pass.*",
          "Greenfield is a spoke that has never seen v4 or v5, which is what makes the",
          "first-run experience observable. Brownfield is mywheel itself, snapshotted",
          "before and asserted after.", ""]
    for b in REQUIRED_BENCHES:
        L += _bench_block(b, bench.get(b))

    L += ["## Gate oracles", "",
          "Doctrine 3: a phase is done only when the gate oracles return clean over",
          "everything it touched, and every new mechanism named its consuming circle.", ""]
    if gates:
        for name, res in sorted(gates.items()):
            L.append(f"- **{name}**: {json.dumps(res)[:300]}")
    else:
        L.append("- NOT ATTACHED. No gate oracle results are recorded on the lug.")
    L.append("")

    circles = evidence.get("new_mechanisms_and_their_circles") or {}
    L += ["## New mechanisms and the circle each one serves", "",
          "Doctrine 3 rejects a producer with no consumer at the gate.", ""]
    if circles:
        for mech, circle in sorted(circles.items()):
            L += [f"- `{mech}`", f"    - {circle}"]
    else:
        L.append("- NONE DECLARED. Any mechanism this phase created is unclaimed.")
    L.append("")

    # OPEN QUESTIONS. Operator directive (s140): "Dont stop to ask me questions or share
    # updates push those into the report file for each phase and open questions deffered
    # till morning when possible." Questions accumulate HERE instead of interrupting him.
    # A question that only exists in a chat message is lost the moment the session ends;
    # a question in the phase report is still there in the morning.
    questions = load_needs_you(lug.get("initiative_id"))
    L += ["## Open questions — needs-you lugs on this initiative", ""]
    if questions:
        L += ["Answer whenever. Nothing below blocks the phase unless it says so.",
              "Each one is a live `needs-you` lug — answering it resolves the lug, not just a line in a report.", ""]
        for i, q in enumerate(questions, 1):
            L.append(f"{i}. **{q.get('title', q.get('id'))}**  (`{q.get('id')}`)")
            for key, label in (("decision_needed", "Decision"), ("why_only_you", "Why only you"),
                               ("blocking", "BLOCKING"), ("recommendation", "My recommendation"),
                               ("the_action", "What to say"),
                               ("what_happened_meanwhile", "What I did in the meantime")):
                if q.get(key):
                    L.append(f"    - {label}: {q[key]}")
            opts = q.get("options")
            if isinstance(opts, dict):
                for k, v in opts.items():
                    L.append(f"        - {k}: {v}")
    else:
        L.append("None open. Nothing on this initiative currently needs a decision only the operator can make.")
    L.append("")

    other = {k: v for k, v in evidence.items() if k != "new_mechanisms_and_their_circles"}
    if other:
        L += ["## Other recorded evidence", ""]
        for k, v in sorted(other.items()):
            L.append(f"- **{k}**: {json.dumps(v)[:300]}")
        L.append("")

    if not certified:
        L += ["## Why this is not certified yet", ""]
        for b in REQUIRED_BENCHES:
            r = bench.get(b)
            if not isinstance(r, dict):
                L.append(f"- `{b}` bench has no attached result.")
            elif r.get("drift") is not False:
                L.append(f"- `{b}` bench reports drift={r.get('drift')} — investigate before certifying.")
        L.append("")

    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # Phase ids are STRINGS, not ints. Ruling 24's inversion inserted phase "4.5" between
    # 4 and 5, and int() rejected it — the tool refused to report on the keystone phase.
    ap.add_argument("--phase")
    ap.add_argument("--lug")
    ap.add_argument("--out")
    args = ap.parse_args(argv)

    if args.lug:
        lug_path = Path(args.lug)
    elif args.phase is not None:
        lug_path = _find_lug(args.phase)
    else:
        raise SystemExit("pass --phase or --lug")

    report = build(lug_path)
    out = Path(args.out) if args.out else Path(f"docs/v5-phase{json.loads(lug_path.read_text()).get('phase')}-certification-report.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print(f"[phase-report] wrote {out} ({len(report.splitlines())} lines)")
    return 0 if "**Verdict:** CERTIFIED" in report else 1


if __name__ == "__main__":
    raise SystemExit(main())
