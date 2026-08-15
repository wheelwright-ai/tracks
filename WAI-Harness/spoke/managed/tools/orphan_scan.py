#!/usr/bin/env python3
"""orphan_scan.py -- find code that was BUILT, TESTED, and CALLED BY NOTHING.

THE CLASS, NOT THE INSTANCE. Session 140 fixed five defects by hand. Three of them were
the same failure wearing different clothes:

    merge_provenance   11 green tests, zero callers, for one commit
    hub_intel          populated by a fork merge, consumed by nothing in canonical Ozi
    heartbeats         a reader with no production writer

Fixing those one at a time is the languishing. This tool detects the SHAPE.

WHY TESTS MAKE IT WORSE, NOT BETTER. An unreferenced function is easy to notice -- nothing
mentions it. A function referenced ONLY by its own test is nearly invisible: coverage counts
it, the suite goes green, and every dashboard reports health. That is the exact state
merge_provenance was in, and the exact state the whole 1449-unprovable-completions problem
is in one level up. So UNWIRED (tested but never called in production) is reported as the
SEVERER finding, ahead of UNREFERENCED.

WHY IT ALSO READS NON-PYTHON. In this estate a tool is routinely invoked by NAME from a
hook, a ceremony markdown file, a JSON config or a cron line -- never imported. A pure
import-graph scan would report most of `managed/tools/` as dead and be confidently,
uselessly wrong. Any textual mention outside the defining file counts as a reference.

WHAT IT DELIBERATELY DOES NOT DO. It does not delete anything, and it does not decide.
"Unreferenced" is a question, not a verdict: an entry point, a CLI subcommand, and a
deliberately-staged mechanism all look identical from here. The output is a ranked list for
a human or a lug, which is the same discipline the isolation curve got -- measure first,
act on evidence, never on the scan's say-so alone.

Usage:
    python3 orphan_scan.py --root . [--json] [--include DIR ...] [--min-lines N]
Exit: 0 always (a report, never a gate)
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

# Where we look for DEFINITIONS. Scanning the whole repo for definitions would drown the
# report in vendored code and one-off scripts.
DEFAULT_INCLUDES = [
    "WAI-Harness/spoke/managed/tools",
    "WAI-Harness/hub/managed/tools",
]

# Where we look for REFERENCES: everything, because a tool is as often named in a hook or
# a ceremony as it is imported.
REFERENCE_EXTS = {".py", ".sh", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".jsonl"}

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".worktrees", ".venv", "venv",
             ".certify-9f08-extract", "archive", ".gitnexus"}

# Names that are references to the language, not to our code.
DUNDER = re.compile(r"^__.*__$")


def _is_test_file(path: str) -> bool:
    base = os.path.basename(path)
    return base.startswith("test_") or base.endswith("_test.py") or "/tests/" in path


def iter_files(root: Path, exts=None):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if exts and os.path.splitext(name)[1] not in exts:
                continue
            yield Path(dirpath) / name


def collect_definitions(root: Path, includes: list, min_lines: int) -> dict:
    """Public module-level functions and classes, per file.

    Private names (leading underscore) are excluded: they are internal by declaration, and
    an unused helper inside one module is a lint concern rather than an estate concern.
    """
    defs = {}
    for inc in includes:
        base = root / inc
        if not base.is_dir():
            continue
        for path in iter_files(base, {".py"}):
            rel = str(path.relative_to(root))
            if _is_test_file(rel):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for node in tree.body:  # module level only
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                name = node.name
                if name.startswith("_") or DUNDER.match(name):
                    continue
                span = (getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno + 1
                if span < min_lines:
                    continue
                defs.setdefault(name, []).append({"file": rel, "line": node.lineno,
                                                  "lines": span,
                                                  "kind": type(node).__name__})
    return defs


def collect_references(root: Path, names: set) -> dict:
    """name -> {"prod": [files], "test": [files]}, excluding the defining file itself.

    Whole-word matching only. Substring matching would let `assess` be "referenced" by the
    word `assessment` in a doc, which is how a scan quietly stops finding anything.
    """
    refs = {n: {"prod": set(), "test": set(), "counts": {}} for n in names}
    if not names:
        return refs
    # TOKENIZE ONCE PER FILE, then intersect with the symbol set.
    #
    # The first version built one giant alternation regex over every symbol name and ran it
    # against every file. That is O(symbols x file bytes) in the regex engine and it did not
    # finish in ten minutes on this estate. Extracting identifiers once per file and taking a
    # set intersection is O(file bytes) and finishes in seconds -- same answer, because both
    # forms match whole words only.
    word = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    for path in iter_files(root, REFERENCE_EXTS):
        rel = str(path.relative_to(root))
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        bucket = "test" if _is_test_file(rel) else "prod"
        # COUNT, do not just detect. A defining file necessarily contains its own symbol
        # name once, on the `def` line. Treating that as a self-reference made EVERY symbol
        # look structurally used and drove the orphan count to zero -- a 0% cruft report
        # that was pure artifact. Occurrences are counted so the definition line can be
        # subtracted later.
        counts = Counter(word.findall(text))
        for token in set(counts) & names:
            refs[token][bucket].add(rel)
            refs[token]["counts"][rel] = counts[token]
    return refs


def scan(root: Path, includes: list, min_lines: int = 4) -> dict:
    defs = collect_definitions(root, includes, min_lines)
    refs = collect_references(root, set(defs))

    # FOUR states, not three. The three-state version reported 35% of this estate as
    # orphaned and that number was WRONG: it excluded same-file references, so any function
    # called only by its own module's main() -- step_harvest in v5_walk.py, every cmd_* in
    # an argparse dispatcher -- was counted as unreferenced. Those are ordinary internal
    # structure, not cruft. A cruft number inflated by normal code is worse than no number,
    # because it is the one people quote.
    unwired, unreferenced, internal, wired = [], [], [], []
    for name, sites in defs.items():
        own = {s["file"] for s in sites}
        prod = refs[name]["prod"] - own
        test = refs[name]["test"] - own
        # Self-reference means MORE mentions in the defining file than there are
        # definitions of it there -- i.e. at least one mention that is not the `def` line.
        defs_here = {}
        for site in sites:
            defs_here[site["file"]] = defs_here.get(site["file"], 0) + 1
        self_ref = any(refs[name]["counts"].get(f, 0) > defs_here[f] for f in own)
        entry = {"symbol": name, "defined": sites,
                 "prod_refs": sorted(prod), "test_refs": sorted(test),
                 "self_referenced": self_ref}
        if prod:
            wired.append(entry)
        elif self_ref:
            # SELF-REFERENCE OUTRANKS TEST-REFERENCE. Checking `test` first put every
            # argparse handler that also has a test into the unwired bucket -- cmd_survey is
            # dispatched by archeologist's own main and is plainly live. Being tested does
            # not make a structurally-used function an orphan, and counting it as one
            # inflates the exact number this tool exists to make trustworthy.
            internal.append(entry)
        elif test:
            # The dangerous one: green tests, no caller ANYWHERE, not even its own module.
            # Looks like coverage. Is not use. This is the merge_provenance state.
            unwired.append(entry)
        else:
            unreferenced.append(entry)

    # Rank by size: a 200-line orphan is a different problem from a 5-line one.
    for group in (unwired, unreferenced):
        group.sort(key=lambda e: -max(s["lines"] for s in e["defined"]))

    total = len(defs)
    # ORPHAN = mentioned NOWHERE, including its own file. internal_only is deliberately
    # excluded: it is ordinary structure. unwired is counted because tested-but-uncalled is
    # a genuine finding, and it is reported separately so the two never blur.
    orphaned = len(unwired) + len(unreferenced)
    return {
        "root": str(root),
        "symbols_scanned": total,
        "wired": len(wired),
        "internal_only_count": len(internal),
        "unwired_count": len(unwired),
        "unreferenced_count": len(unreferenced),
        "orphan_fraction": (orphaned / total) if total else None,
        "unwired": unwired,
        "unreferenced": unreferenced,
        "internal_only": internal,
        "verdict": (
            "no definitions found -- check --include" if not total else
            f"{len(unwired)} tested-but-uncalled, {len(unreferenced)} referenced nowhere, "
            f"{len(internal)} internal-only, of {total} public symbols"
        ),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--include", action="append", default=None,
                    help="directory to scan for DEFINITIONS (repeatable)")
    ap.add_argument("--min-lines", type=int, default=4,
                    help="ignore definitions shorter than this (default 4)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    report = scan(root, args.include or DEFAULT_INCLUDES, args.min_lines)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"orphan scan: {report['verdict']}")
    frac = report["orphan_fraction"]
    print(f"  wired         : {report['wired']}")
    print(f"  internal-only : {report['internal_only_count']}  (ordinary structure, NOT cruft)")
    print(f"  orphaned      : {report['unwired_count'] + report['unreferenced_count']}"
          + (f" ({frac:.0%} of public symbols)" if frac is not None else ""))
    if report["unwired"]:
        print("\n  TESTED BUT NEVER CALLED IN PRODUCTION -- the merge_provenance shape:")
        for e in report["unwired"][:args.top]:
            d = e["defined"][0]
            print(f"    {e['symbol']:<38} {d['lines']:>4}L  {d['file']}")
    if report["unreferenced"]:
        print("\n  REFERENCED NOWHERE (a question, not a verdict -- entry points look like this):")
        for e in report["unreferenced"][:args.top]:
            d = e["defined"][0]
            print(f"    {e['symbol']:<38} {d['lines']:>4}L  {d['file']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
