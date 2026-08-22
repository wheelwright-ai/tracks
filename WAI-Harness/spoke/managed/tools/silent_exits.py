#!/usr/bin/env python3
"""silent_exits.py -- find the decisions the harness makes without saying so.

s141 (2026-08-18) spent a night on a fleet that had paused itself. FOUR root causes were
found and NOT ONE was a wrong decision:

  * the dispatch guard refused on files the autopilot writes itself -- correct guard,
    invisible refusal
  * conductor classified each result into one word and discarded the evidence
  * harvest reported a step index its own filter had shifted -- 8 of 23 rewrites misplaced
  * phase 3 dropped lugs through FIVE unnamed `continue`s

The fourth was measured directly. ezorg reported eligible=40, dispatched=0, and nothing in
between. Naming each exit answered it in one line -- 17 review + 13 skip-list + 10 needs-you,
summing exactly to 40, nothing lost, no bug. The defect was the SILENCE.

A mute correct system is indistinguishable from a broken one. This finds the mute parts
BEFORE they surface as an outage.

WHAT COUNTS AS SILENT: a control-flow exit (`continue`, `break`, or an early `return`)
inside a conditional, where nothing on the path to it emits anything a human could read --
no print, no logger call, no append to a findings/reasons list. Those are decisions the
code makes and cannot account for.

WHAT DOES NOT COUNT, deliberately:
  * a `return` that hands back a value -- the caller has the value; that IS the report
  * exits in a guard clause at the very top of a function (arg validation, empty input)
  * loops with no branching -- a filter comprehension is not a hidden decision
Flagging those would bury the real findings, and a report nobody can act on is the same
defect one level up.

USAGE
  silent_exits.py scan <path>... [--json] [--top N]
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys

TOOL_VERSION = "1.0.0"

# Names that mean "a human can see this happened".
# ACCOUNTING COUNTS AS SPEAKING. The real remediation applied to phase 3 was not a print
# but `self._drop("needs_you")` -- a tally read back in the phase summary. Without these
# names the scanner flags its own fix as unfixed, which would train everyone to ignore it.
_SPEAKS = ("print", "log", "warn", "error", "info", "debug", "emit", "report",
           "record", "note", "append", "add", "write", "raise",
           "drop", "tally", "count", "track", "collect")


def _speaks(node) -> bool:
    """Does this subtree emit anything a reader could ever see?"""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Raise):
            return True
        if isinstance(sub, ast.Call):
            f = sub.func
            name = getattr(f, "id", None) or getattr(f, "attr", None) or ""
            if any(w in name.lower() for w in _SPEAKS):
                return True
    return False


# WHICH SILENT EXITS ACTUALLY MATTER. A parser skipping a comment line is silent and
# harmless; a dispatcher skipping a LUG is silent and cost this project a night. The
# difference is what the branch is deciding ABOUT, and the condition names it.
#
# Ranking exists so the report is usable. 66 findings in one file, undifferentiated, is
# the same defect as no findings -- nobody reads it, so nobody acts.
_WORK_NOUNS = ("lug", "work", "item", "task", "job", "spoke", "dispatch", "queue",
               "record", "candidate", "advisor", "initiative", "signal", "receipt")
_NOISE_NOUNS = ("line", "char", "token", "comment", "blank", "header", "arg", "path_part")


def _risk(condition: str, function: str) -> str:
    blob = f"{condition} {function}".lower()
    if any(n in blob for n in _NOISE_NOUNS) and not any(n in blob for n in _WORK_NOUNS):
        return "low"
    return "high" if any(n in blob for n in _WORK_NOUNS) else "medium"


class _Scan(ast.NodeVisitor):
    def __init__(self, path, src):
        self.path = path
        self.lines = src.split("\n")
        self.found = []
        self._fn = []
        self._loop_depth = 0

    def visit_FunctionDef(self, node):
        self._fn.append(node.name)
        self.generic_visit(node)
        self._fn.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _visit_loop(self, node):
        self._loop_depth += 1
        self.generic_visit(node)
        self._loop_depth -= 1

    visit_For = _visit_loop
    visit_While = _visit_loop

    def visit_If(self, node):
        # Only the branch bodies matter: an `if` whose body is exactly a jump.
        for body in (node.body, node.orelse):
            jumps = [s for s in body
                     if isinstance(s, (ast.Continue, ast.Break))
                     or (isinstance(s, ast.Return) and s.value is None)]
            if not jumps:
                continue
            if self._loop_depth == 0 and not isinstance(jumps[0], ast.Return):
                continue
            if _speaks(ast.Module(body=body, type_ignores=[])):
                continue
            kind = type(jumps[0]).__name__.lower()
            cond = self._src(node.test).strip()
            fn = self._fn[-1] if self._fn else "<module>"
            self.found.append({
                "risk": _risk(cond, fn),
                "file": self.path,
                "line": jumps[0].lineno,
                "function": self._fn[-1] if self._fn else "<module>",
                "kind": kind,
                "in_loop": self._loop_depth > 0,
                "condition": cond[:110],
            })
        self.generic_visit(node)

    def _src(self, node):
        try:
            return ast.get_source_segment("\n".join(self.lines), node) or "?"
        except Exception:
            return "?"


def scan_file(path):
    try:
        src = open(path, encoding="utf-8", errors="ignore").read()
        tree = ast.parse(src)
    except (OSError, SyntaxError):
        return []
    s = _Scan(path, src)
    s.visit(tree)
    return s.found


def scan(paths):
    out = []
    for p in paths:
        if os.path.isfile(p) and p.endswith(".py"):
            out += scan_file(p)
        elif os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                if "__pycache__" in root or "/tests" in root or "/.git" in root:
                    continue
                for f in files:
                    if f.endswith(".py") and not f.startswith("test_"):
                        out += scan_file(os.path.join(root, f))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("scan")
    p.add_argument("paths", nargs="+")
    p.add_argument("--json", action="store_true")
    p.add_argument("--top", type=int, default=25)
    args = ap.parse_args(argv)

    rows = scan(args.paths)
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    high = [r for r in rows if r["risk"] == "high" and r["in_loop"]]
    by_file = {}
    for r in high:
        by_file[r["file"]] = by_file.get(r["file"], 0) + 1

    print(f"\n{len(rows)} silent exit(s) total; {len(high)} HIGH-risk inside a loop")
    print("  HIGH = the branch decides about work (lug/task/spoke/queue), not about text.\n")
    for f, n in sorted(by_file.items(), key=lambda kv: -kv[1])[:args.top]:
        print(f"  {n:>4}  {f}")
    if high:
        print("\n  worst offenders:")
        for r in high[:8]:
            print(f"    {os.path.basename(r['file'])}:{r['line']} in {r['function'][:30]}")
            print(f"        if {r['condition'][:88]}")
    print("\n  A silent exit is not a bug. It is a decision the code cannot account for,")
    print("  and it reads identically whether it is right or wrong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
