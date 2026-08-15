#!/usr/bin/env python3
"""Documentation gets the same oracle the code already has.

WHY
---
Every other corpus here has a deterministic verifier: manifest_build --verify for
the managed tree, lug_gate for lugs, the test suite for code. Prose had none — and
on 2026-08-01 that cost real money. README.md sat stamped harness v4.6.4 while
WAI-Harness/VERSION read 4.14.34 (769 commits of drift), and a second portrait at
dev/root-docs/KnowMe.md carried its own 4.6.5 edition. Both were being read as
authoritative by agents. Nothing detected either condition.

WHAT IT CHECKS (structure only — meaning is a model's job, deliberately)
-----------------------------------------------------------------------
  stale-version   a doc stamping a harness version behind WAI-Harness/VERSION
  broken-link     a relative markdown link that resolves to nothing
  missing-type    an enforced doc with no `type:` in YAML frontmatter
  no-updated      an enforced doc with no `updated:` date
  contradiction   a doc carrying an unresolved "> **Contradiction:**" notice
                  (reported, never failed — the notice is the CORRECT state;
                  silence between disagreeing docs is the defect)

The split is imported from OKF (coleam00/cole-medin-knowledge-base): the script
proves structure, an LLM judges meaning, and neither pretends to do the other's
job. A lint that tried to assess whether prose is TRUE would be the same
unearned-green this repo keeps finding.

SCOPE, AND WHY IT STARTS SMALL
------------------------------
ENFORCED is the set that must pass today — the portraits an outside agent is
handed first. The wider corpus is scanned in --report mode so the backlog is
visible without a big-bang migration that would either block every commit or get
switched off. A gate nobody can satisfy gets bypassed, and a bypassed gate is
worse than no gate because it reports green.

USAGE
    python3 doc_integrity_lint.py [--root .] [--json] [--report] [--enforce PATH ...]

Exit: 0 clean, 1 findings in the enforced set, 2 bad input.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Docs an agent is handed first. These must pass version + link checks.
ENFORCED = ("README.md", "AGENTS.md", "CLAUDE.md")

# Frontmatter is required only of the PORTRAIT and the knowledge corpus — not of
# agent-instruction files. AGENTS.md and CLAUDE.md are distributed from templates;
# demanding frontmatter there would fork every spoke's copy from its template to
# satisfy a lint, which trades one drift problem for another.
FRONTMATTER_REQUIRED = ("README.md",)

# Additionally scanned in --report mode.
REPORT_GLOBS = ("WAI-Harness/dev/root-docs/*.md", "reviews/**/*.md")

VERSION_FILE = "WAI-Harness/VERSION"

# "harness v4.6.4", "harness `v4.6.4`", "harness **`v4.6.4`**", "v4.6.4"
VERSION_RE = re.compile(r"harness[^\n]{0,12}?v(\d+)\.(\d+)\.(\d+)", re.I)
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
CONTRADICTION_RE = re.compile(r">\s*\*\*Contradiction:\*\*", re.I)
STUB_MARKERS = ("superseded", "no longer maintained")


def parse_version(text):
    try:
        return tuple(int(x) for x in text.strip().split("."))
    except (ValueError, AttributeError):
        return None


def is_stub(body):
    return any(m in body[:600].lower() for m in STUB_MARKERS)


def frontmatter(body):
    m = FRONTMATTER_RE.match(body)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def check_doc(path, root, canon_version, enforced):
    """Return a list of findings for one document."""
    findings = []
    try:
        body = path.read_text(errors="replace")
    except OSError as e:
        return [{"path": str(path.relative_to(root)), "rule": "unreadable",
                 "detail": str(e), "enforced": enforced}]

    rel = str(path.relative_to(root))
    stub = is_stub(body)

    # stale-version — the failure that motivated the tool.
    #
    # Compared at MAJOR.MINOR, not patch. The s140 failure was 4.6 against 4.14 —
    # a doc describing a different generation of the harness. A patch-level lag is
    # not drift, it is Tuesday: this repo cut four patches in one evening, and a
    # lint that demanded a README edit per patch would be pure noise, then bypassed,
    # then reporting green over the real thing. Sensitivity IS the design.
    if canon_version:
        for m in VERSION_RE.finditer(body):
            stamped = tuple(int(g) for g in m.groups())
            if stamped[:2] < canon_version[:2]:
                findings.append({
                    "path": rel, "rule": "stale-version", "enforced": enforced,
                    "detail": (f"stamps harness v{'.'.join(map(str, stamped))} but "
                               f"{VERSION_FILE} is {'.'.join(map(str, canon_version))}"),
                })
                break  # one finding per doc; the first stale stamp is the signal

    # broken-link
    for link in LINK_RE.findall(body):
        if link.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = (path.parent / link.split("#", 1)[0]).resolve()
        if not target.exists():
            findings.append({"path": rel, "rule": "broken-link", "enforced": enforced,
                             "detail": f"link target does not exist: {link}"})

    # frontmatter — stubs are pointers, not documents, and are exempt
    needs_fm = enforced and rel in FRONTMATTER_REQUIRED
    if not stub and needs_fm:
        fm = frontmatter(body)
        if not fm.get("type"):
            findings.append({"path": rel, "rule": "missing-type", "enforced": True,
                             "detail": "no `type:` in YAML frontmatter"})
        if not fm.get("updated"):
            findings.append({"path": rel, "rule": "no-updated", "enforced": True,
                             "detail": "no `updated:` in YAML frontmatter"})

    # contradiction — informational; the notice existing is the CORRECT state
    if CONTRADICTION_RE.search(body):
        findings.append({"path": rel, "rule": "contradiction", "enforced": False,
                         "detail": "carries an explicit contradiction notice"})

    return findings


def run(root, extra_enforced=(), report=False):
    root = Path(root).resolve()
    canon_version = None
    vf = root / VERSION_FILE
    if vf.exists():
        canon_version = parse_version(vf.read_text())

    enforced_paths = []
    for name in tuple(ENFORCED) + tuple(extra_enforced):
        p = root / name
        if p.exists():
            enforced_paths.append(p)

    scanned = {p.resolve(): True for p in enforced_paths}
    if report:
        for g in REPORT_GLOBS:
            for p in root.glob(g):
                if p.is_file() and p.resolve() not in scanned:
                    scanned[p.resolve()] = False

    findings = []
    for path, is_enforced in scanned.items():
        findings.extend(check_doc(path, root, canon_version, is_enforced))

    blocking = [f for f in findings if f.get("enforced")]
    return {
        "canon_version": ".".join(map(str, canon_version)) if canon_version else None,
        "docs_scanned": len(scanned),
        "enforced": len(enforced_paths),
        "findings": findings,
        "blocking": len(blocking),
        "ok": not blocking,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--report", action="store_true",
                    help="also scan the wider corpus, non-blocking")
    ap.add_argument("--enforce", action="append", default=[], metavar="PATH",
                    help="add a doc to the enforced set (repeatable)")
    a = ap.parse_args()

    if not Path(a.root).is_dir():
        sys.stderr.write(f"not a directory: {a.root}\n")
        return 2

    result = run(a.root, a.enforce, a.report)

    if a.json:
        print(json.dumps(result, indent=2))
    else:
        v = result["canon_version"] or "unknown"
        print(f"doc integrity — canon harness {v}, "
              f"{result['docs_scanned']} doc(s) scanned, "
              f"{result['enforced']} enforced")
        for f in result["findings"]:
            mark = "FAIL" if f.get("enforced") else "note"
            print(f"  [{mark}] {f['path']}: {f['rule']} — {f['detail']}")
        print("OK" if result["ok"] else f"BLOCKING: {result['blocking']} finding(s)")

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
