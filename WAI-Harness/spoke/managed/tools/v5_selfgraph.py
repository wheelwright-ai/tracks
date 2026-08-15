#!/usr/bin/env python3
"""v5_selfgraph.py -- derive the PathGraph over the v5 build itself, and let it indict us.

impl-v5-the-v5-build-must-live-in-its-own-pathgraph-v1 (Ruling 33 + Doctrine 3).

WHY THIS EXISTS. Doctrine 3 says every mechanism must serve a circle. The v5 initiative
built a graph, a circle auditor, provenance classes and a capability resolver -- and served
none of its own. We would have found out whether any of it works on real material only
after distributing it to fourteen spokes.

THE UNUSUAL PASS CONDITION. This tool is required to report something WRONG with our own
build, and `assess` exits non-zero if it cannot. A clean sheet here is not good news; it is
evidence the instrument is blind. Every other check in this repo tries to come back green.
This one fails when it does.

WHAT IS DISCOVERED VS COLLABORATED HERE (Ruling 33):
  DISCOVERED    the v5 tools and their tests, scanned from disk by pathgraph_derive.
  COLLABORATED  the 39 rulings. A ruling is intent -- why a mechanism exists, what was
                rejected, what landing looks like. It is derivable from no amount of code
                reading, which is exactly what makes it the half a naive rebuild destroys.
  RESULT        test execution against those nodes.

RULING -> NODE IS AUTHORED, NOT INFERRED. The map below is hand-written and that is
deliberate. Guessing the mapping from text similarity would manufacture attachments nobody
decided, and a collaborated node's whole value is that a person meant it. An unmapped ruling
is reported as unattached rather than being quietly attached to something plausible.

A ruling mapped to a file that does not exist becomes RUNWAY, never a node asserting the
file is there (Ruling 34.3, already enforced by merge_provenance).

Usage:
    python3 v5_selfgraph.py rulings [--json]        parse the rulings + their status
    python3 v5_selfgraph.py store --out PATH        write the collaborated store
    python3 v5_selfgraph.py assess [--json]         derive + report; NONZERO if all green
Exit: 0 ok | 1 assess found no weakness (the instrument is blind) | 2 error
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
DIRECTIVE = "docs/wheelwright-v5-control-plane-directive.md"

# The v5 mechanisms. Explicit rather than globbed: "which tools are the v5 build" is a
# judgement about scope, and a glob would silently absorb every future tool into the
# self-assessment and dilute exactly the signal this is meant to sharpen.
V5_TOOLS = [
    "WAI-Harness/spoke/managed/tools/pathgraph_derive.py",
    "WAI-Harness/spoke/managed/tools/pathgraph_generate.py",
    "WAI-Harness/spoke/managed/tools/circle_audit.py",
    "WAI-Harness/spoke/managed/tools/circle_findings_bridge.py",
    "WAI-Harness/spoke/managed/tools/capability_coverage.py",
    "WAI-Harness/spoke/managed/tools/compute_capability_gaps.py",
    "WAI-Harness/spoke/managed/tools/resolve_capabilities_graph.py",
    "WAI-Harness/spoke/managed/tools/v5_selfgraph.py",
]

# Ruling -> the node it governs. Authored. Absence is reported, never guessed.
RULING_NODES = {
    22: "WAI-Harness/spoke/managed/tools/pathgraph_derive.py",
    24: "WAI-Harness/spoke/managed/tools/pathgraph_derive.py",
    25: "WAI-Harness/spoke/managed/tools/pathgraph_derive.py",
    26: "WAI-Harness/spoke/managed/tools/circle_findings_bridge.py",
    27: "WAI-Harness/spoke/managed/tools/pathgraph_derive.py",
    28: "WAI-Harness/spoke/managed/tools/pathgraph_derive.py",
    29: "WAI-Harness/spoke/managed/tools/pathgraph_derive.py",
    31: "WAI-Harness/spoke/managed/tools/pathgraph_derive.py",
    32: "WAI-Harness/spoke/managed/tools/pathgraph_derive.py",
    33: "WAI-Harness/spoke/managed/tools/pathgraph_derive.py",
    34: "WAI-Harness/spoke/managed/tools/pathgraph_derive.py",
    37: "WAI-Harness/spoke/managed/tools/circle_audit.py",
    # Deliberately mapped to a file that does NOT exist. Ruling 36 requires reviewers to
    # run as isolated subagents and nothing implements it, so the graph should surface it
    # as RUNWAY rather than let it pass unnoticed as merely "unattached".
    36: "WAI-Harness/spoke/managed/tools/review_isolation.py",
}


def _read_directive(root: Path) -> str:
    path = root / DIRECTIVE
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def parse_ruling_status(text: str) -> dict:
    """Ruling number -> status string, expanded from the index table's ranges.

    The table writes ranges with an EN DASH ("1-6" is really "1–6"). Matching only the
    ASCII hyphen silently produced zero statuses on the first attempt, which would have
    reported every ruling as unknown -- the sort of quiet miss that reads as data.
    """
    status = {}
    body = text.split("## Ruling status index", 1)[-1]
    # Only the FIRST contiguous table after the heading. The document contains later
    # tables whose first column is also numeric (the phase list), and scanning the whole
    # remainder read phase names as ruling statuses -- rulings 1-11 came back with values
    # like "Architecture and schema". Wrong data that looks like data is worse than none.
    lines, table = body.splitlines(), []
    started = False
    for line in lines:
        if line.lstrip().startswith("|"):
            started = True
            table.append(line)
        elif started:
            break
    for cells in re.findall(r"^\|([^|]+)\|([^|]+)\|", "\n".join(table), re.M):
        label, state = cells[0].strip(), cells[1].strip()
        if not re.match(r"^[0-9]", label):
            continue
        span = re.match(r"^(\d+)\s*[–\-]\s*(\d+)$", label)
        if span:
            for n in range(int(span.group(1)), int(span.group(2)) + 1):
                status[n] = state
        elif label.isdigit():
            status[int(label)] = state
    return status


def parse_rulings(text: str, max_ruling: int = 39) -> list:
    """The top-level numbered rulings, with their first line as the statement.

    Only column-zero list items count. Nested sub-lists restart at 1 and would otherwise
    be read as rulings 1..n all over again -- the first parse found 46 "rulings" in a
    39-ruling document for exactly that reason.
    """
    status = parse_ruling_status(text)
    body = text.split("## Ruling status index", 1)[-1]
    out, seen = [], set()
    for m in re.finditer(r"^(\d{1,2})\. (.+)$", body, re.M):
        num = int(m.group(1))
        if num in seen or num > max_ruling:
            continue
        seen.add(num)
        statement = re.sub(r"\*\*|>|`", "", m.group(2)).strip()
        out.append({
            "ruling": num,
            "statement": statement[:400],
            "status": status.get(num, "LIVE"),
            "node": RULING_NODES.get(num),
        })
    return sorted(out, key=lambda r: r["ruling"])


def build_store(rulings: list) -> list:
    """Rulings as COLLABORATED records, in merge_provenance's shape.

    A ruling with no authored node is skipped here and counted separately: attaching it to
    a guess would be manufacturing a decision nobody made.
    """
    records = []
    for r in rulings:
        if not r["node"]:
            continue
        records.append({
            "path": r["node"],
            "why": f"Ruling {r['ruling']}: {r['statement']}",
            "rejected": [],
            "landing_condition": f"{r['node']} exists and its tests pass",
            "origin": {"session": "v5-control-plane-directive",
                       "said_at": f"ruling-{r['ruling']}",
                       "status": r["status"]},
        })
    return records


def assess(root: Path, store_path: str) -> dict:
    """Derive over the v5 tools and report what the graph says about our own build."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import pathgraph_derive as pg

    rulings = parse_rulings(_read_directive(root))
    Path(store_path).parent.mkdir(parents=True, exist_ok=True)
    Path(store_path).write_text(json.dumps(build_store(rulings), indent=2), encoding="utf-8")

    snapshot = pg.derive_graph(root, run_tests_flag=False, collaborated_file=store_path)
    fi = snapshot["functional_identity"]

    present = [t for t in V5_TOOLS if (root / t).is_file()]
    missing = [t for t in V5_TOOLS if not (root / t).is_file()]
    untested = [t for t in present
                if snapshot["node_states"].get(t, {}).get("tested") != "TESTED"]
    unattached = [r["ruling"] for r in rulings if not r["node"]]

    # WEAKNESSES. Each is a real defect in OUR build, derived from the graph rather than
    # asserted. If this list is empty the instrument is not looking hard enough.
    weaknesses = []
    for t in missing:
        weaknesses.append({"kind": "MECHANISM_MISSING", "detail": t})
    for t in untested:
        weaknesses.append({"kind": "V5_TOOL_UNTESTED", "detail": t})
    for item in snapshot["runway"]:
        weaknesses.append({"kind": "RULING_UNBUILT", "detail": item["path"],
                           "why": item.get("why", "")[:160]})
    if unattached:
        weaknesses.append({
            "kind": "RULINGS_GOVERN_NO_NODE",
            "detail": f"{len(unattached)} of {len(rulings)} rulings attach to no mechanism",
            "rulings": unattached,
        })
    for rec in snapshot["provenance_rejected"]:
        weaknesses.append({"kind": "PROVENANCE_REJECTED",
                           "detail": "; ".join(rec.get("reasons", []))})

    return {
        "rulings_parsed": len(rulings),
        "rulings_attached": len(rulings) - len(unattached),
        "v5_tools_present": len(present),
        "v5_tools_missing": missing,
        "collaborated_count": fi.get("collaborated_count"),
        "runway_count": fi.get("runway_count"),
        "node_count": fi.get("node_count"),
        "weaknesses": weaknesses,
        "verdict": (
            f"{len(weaknesses)} weakness(es) in the v5 build itself"
            if weaknesses else
            "NO WEAKNESS FOUND -- treat as instrument failure, not as health"
        ),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rulings")
    p_store = sub.add_parser("store")
    p_store.add_argument("--out", default="WAI-Harness/spoke/local/pathgraph/v5-collaborated.json")
    p_assess = sub.add_parser("assess")
    p_assess.add_argument("--store", default="WAI-Harness/spoke/local/pathgraph/v5-collaborated.json")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    if args.cmd == "rulings":
        rulings = parse_rulings(_read_directive(root))
        print(json.dumps(rulings, indent=2) if args.json
              else "\n".join(f"{r['ruling']:>3} [{r['status']:<18}] "
                             f"{'-> ' + os.path.basename(r['node']) if r['node'] else '(unattached)'}"
                             for r in rulings))
        return 0

    if args.cmd == "store":
        rulings = parse_rulings(_read_directive(root))
        out = root / args.out if not os.path.isabs(args.out) else Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        records = build_store(rulings)
        out.write_text(json.dumps(records, indent=2), encoding="utf-8")
        print(f"wrote {len(records)} collaborated record(s) -> {out}")
        return 0

    store = args.store if os.path.isabs(args.store) else str(root / args.store)
    report = assess(root, store)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"v5 self-graph: {report['verdict']}")
        print(f"  rulings parsed/attached : {report['rulings_parsed']}/{report['rulings_attached']}")
        print(f"  v5 tools present        : {report['v5_tools_present']}")
        print(f"  collaborated / runway   : {report['collaborated_count']} / {report['runway_count']}")
        for w in report["weaknesses"]:
            print(f"  [{w['kind']}] {w['detail']}")
    # NONZERO WHEN CLEAN. Inverted on purpose: this instrument's failure mode is silence.
    return 1 if not report["weaknesses"] else 0


if __name__ == "__main__":
    sys.exit(main())
