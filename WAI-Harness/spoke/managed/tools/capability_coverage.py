#!/usr/bin/env python3
"""What can this wheel actually do right now — probed, not declared.

WHY
---
capabilities-graph.json and capability-registry-canonical.md are hand-maintained.
Hand-maintained descriptions of a live system drift, and this repo proved the cost
on 2026-08-01: README.md sat eight minor harness versions stale while a second
portrait drifted independently, both read as authoritative, nothing detecting
either. The capability registry has exactly the same shape and exactly the same
exposure — as of writing, capabilities-graph.json still stamps harness_version
"4.0.0-pre" and is_master false on a repo running 4.14.x as master.

A registry that claims capabilities the spoke no longer has is canon lying. That is
worse than no registry, because an agent trusts it.

The idea is borrowed from OKF/Adeptly (ShopDevX/adeptlydev refreshes its feature
catalogue by querying the installed CLI): derive the list from the live thing, not
from a document about the thing.

WHAT IT EMITS
-------------
Three sets, which are the whole point:
  present  declared AND observable on disk        — real
  dead     declared but NOT observable            — canon lying; the finding
  unknown  observable but NOT declared            — capability nobody wrote down

Plus a usage read: of the capabilities present, which were actually exercised in
recent session tracks. That number is secondary colour and never gates anything —
using a capability for its own sake is not a virtue.

USAGE
    python3 capability_coverage.py --spoke-root . [--json] [--sessions N]

Exit: 0 no dead entries, 1 dead entries found, 2 bad input.
"""

import argparse
import json
import re
import sys
from pathlib import Path

GRAPH = "WAI-Harness/spoke/managed/capabilities-graph.json"

# Where each KIND of capability is observable on disk. The probe is the authority.
PROBES = {
    "command": ("`.claude/commands/{name}.md",
                "WAI-Harness/spoke/managed/.claude/commands/{name}.md",
                "WAI-Harness/spoke/managed/templates/commands/{name}.md"),
    "skill":   (".claude/skills/{name}/SKILL.md",
                ".claude/skills/{name}.md",
                "WAI-Harness/spoke/managed/.claude/skills/{name}/SKILL.md"),
    "agent":   (".claude/agents/{name}.md",
                "WAI-Harness/spoke/managed/.claude/agents/{name}.md"),
    "hook":    (".claude/hooks/{name}.sh",
                "WAI-Harness/spoke/managed/.claude/hooks/{name}.sh"),
    "tool":    ("WAI-Harness/spoke/managed/tools/{name}.py",
                "WAI-Harness/hub/local/tools/{name}.py"),
}


def observable(root, kind, name):
    """Return the path proving this capability exists, or None.

    A declared name may already carry its extension (`post-tool-use.sh`,
    `flush_buffer.py`), so the suffix in the probe pattern is tried both appended
    and stripped. The first version of this probe did NOT do that and reported 13
    live hooks as DEAD — a false alarm about the repo that was really a defect in
    the instrument. A monitor's first output is evidence about the monitor; that
    lesson is why this function is written the long way.
    """
    for pattern in PROBES.get(kind, ()):
        pattern = pattern.lstrip("`")
        for candidate in (pattern.format(name=name),
                          pattern.format(name=Path(name).stem)):
            p = root / candidate
            if p.exists():
                return str(p.relative_to(root))
        # name already carries an extension: try it in place of the pattern's
        base, _, tail = pattern.partition("{name}")
        if tail and Path(name).suffix:
            p = root / (base + name)
            if p.exists():
                return str(p.relative_to(root))
    return None


def probe_inventory(root):
    """Everything observable, regardless of what anyone declared."""
    found = {}
    for kind, patterns in PROBES.items():
        for pattern in patterns:
            pattern = pattern.lstrip("`")
            base, _, tail = pattern.partition("{name}")
            base_dir = root / base
            if not base_dir.exists():
                continue
            for entry in base_dir.iterdir():
                if tail.startswith("/"):          # skill dir form
                    if entry.is_dir() and (entry / tail.lstrip("/")).exists():
                        found.setdefault(kind, set()).add(entry.name)
                elif entry.is_file() and entry.name.endswith(tail):
                    found.setdefault(kind, set()).add(entry.name[: -len(tail)] if tail else entry.stem)
    return found


def usage_from_tracks(root, limit):
    """Names appearing in recent session tracks — evidence of real use."""
    sessions = root / "WAI-Harness" / "spoke" / "local" / "sessions"
    used, read = set(), []
    if not sessions.is_dir():
        return used, read
    dirs = sorted((d for d in sessions.iterdir() if d.is_dir()), reverse=True)[:limit]
    for d in dirs:
        track = d / "track.jsonl"
        if not track.exists():
            continue
        read.append(d.name)
        try:
            body = track.read_text(errors="replace")
        except OSError:
            continue
        for token in re.findall(r"[A-Za-z0-9_\-]{4,}", body):
            used.add(token)
    return used, read


def run(spoke_root=".", sessions=10):
    root = Path(spoke_root).resolve()
    graph_path = root / GRAPH
    if not graph_path.exists():
        return {"error": f"no capability graph at {GRAPH}", "ok": False}

    graph = json.loads(graph_path.read_text())
    declared = graph.get("entries", [])

    present, dead, unprobeable = [], [], []
    for e in declared:
        name, kind = e.get("name"), e.get("kind", "command")
        record = {"id": e.get("id"), "name": name, "kind": kind}
        if kind not in PROBES:
            # An abstract capability ("Claim-is-not-evidence gate on completion
            # records") has no file to point at. Calling it DEAD would be a false
            # accusation dressed as rigour — the tool would be claiming knowledge
            # it does not have. Report the honest third state instead.
            unprobeable.append({**record, "detail": f"kind '{kind}' has no file-level probe"})
            continue
        proof = observable(root, kind, name) if name else None
        if proof:
            present.append({**record, "proof": proof})
        else:
            dead.append({**record, "detail": "declared but not observable on disk"})

    declared_names = {(e.get("kind", "command"), e.get("name")) for e in declared}
    unknown = []
    for kind, names in probe_inventory(root).items():
        for n in sorted(names):
            if (kind, n) not in declared_names:
                unknown.append({"name": n, "kind": kind,
                                "detail": "observable but not declared"})

    used_tokens, sessions_read = usage_from_tracks(root, sessions)
    exercised = [p for p in present if p["name"] in used_tokens]

    stamped = graph.get("harness_version")
    actual = (root / "WAI-Harness" / "VERSION")
    actual = actual.read_text().strip() if actual.exists() else None

    return {
        "graph_harness_version": stamped,
        "actual_harness_version": actual,
        "graph_stamp_stale": bool(stamped and actual and stamped != actual),
        "declared": len(declared),
        "present": len(present),
        "dead": dead,
        "unprobeable": unprobeable,
        "unknown": unknown,
        "coverage": {
            "exercised": len(exercised),
            "of_present": len(present),
            "sessions_read": sessions_read,
        },
        "ok": not dead,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spoke-root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sessions", type=int, default=10)
    a = ap.parse_args()

    if not Path(a.spoke_root).is_dir():
        sys.stderr.write(f"not a directory: {a.spoke_root}\n")
        return 2

    r = run(a.spoke_root, a.sessions)
    if r.get("error"):
        sys.stderr.write(r["error"] + "\n")
        return 2

    if a.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"capability coverage — {r['declared']} declared, "
              f"{r['present']} present, {len(r['dead'])} DEAD, "
              f"{len(r['unprobeable'])} unprobeable, "
              f"{len(r['unknown'])} undeclared")
        if r["graph_stamp_stale"]:
            print(f"  graph stamps harness {r['graph_harness_version']} "
                  f"but VERSION is {r['actual_harness_version']}")
        for d in r["dead"][:25]:
            print(f"  [DEAD]    {d['kind']}/{d['name']} — {d['detail']}")
        if len(r["dead"]) > 25:
            print(f"  ... and {len(r['dead']) - 25} more dead entries")
        for u in r["unknown"][:15]:
            print(f"  [unknown] {u['kind']}/{u['name']}")
        if len(r["unknown"]) > 15:
            print(f"  ... and {len(r['unknown']) - 15} more undeclared")
        c = r["coverage"]
        print(f"  exercised recently: {c['exercised']}/{c['of_present']} "
              f"across {len(c['sessions_read'])} session(s)")
        print("OK" if r["ok"] else f"CANON LYING: {len(r['dead'])} declared capability(ies) do not exist")

    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
