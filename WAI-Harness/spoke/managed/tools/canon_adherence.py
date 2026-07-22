#!/usr/bin/env python3
"""canon_adherence.py — does what RUNS match what CANON says?

THE OPERATOR'S FRAME (s138): "Ozi should seek completeness and canonical
adherence and finally self-improvement." This tool is the canonical-adherence
instrument. Completeness lives in the coverage tools (tastegraph_compliance,
savepoint_walk); self-improvement is what you do with what these two report.

WHY THIS EXISTS. Commands live in THREE places and only one of them executes:

    templates/commands/        authored, deployed by nothing
    managed/.claude/commands/  canonical source deploy_commands.py ships FROM
    <spoke>/.claude/commands/  what the operator's slash commands resolve TO

An edit to the wrong layer changes nothing, and says nothing while doing so. No
error, no warning, a clean commit. On 2026-07-18 an audit found five drifted
pairs, two of which held a mandatory adversarial plan-review gate written ten days
earlier that had NEVER executed — it had been added to the template, which
deploys nowhere. The process everyone believed was protecting plans was not
running at all.

The same audit found the deployed layer trailing the canonical one, so even the
fixes made that day were not yet live until a deploy was run.

THE PRINCIPLE. Drift between authored and running is not a tidiness problem, it
is a truth problem: every layer that disagrees is a place where a belief about
the system is false. This tool reports each layer separately so the direction of
drift is visible, because direction decides the fix — canon ahead of deployed
means "deploy"; template ahead of canon means "an edit has been silently dead,
find out for how long".

Usage:
    canon_adherence.py check [--json]      # exits 1 on any drift
    canon_adherence.py explain             # what each layer is and why it drifts
"""

import argparse
import json
import os
import sys

TEMPLATES = "WAI-Harness/spoke/managed/templates/commands"
CANON = "WAI-Harness/spoke/managed/.claude/commands"
DEPLOYED = ".claude/commands"

CANON_HOOKS = "WAI-Harness/spoke/managed/.claude/hooks"
DEPLOYED_HOOKS = ".claude/hooks"


def _files(d):
    if not os.path.isdir(d):
        return {}
    out = {}
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if os.path.isfile(p) and not name.startswith("."):
            try:
                out[name] = open(p, "rb").read()
            except OSError:
                continue
    return out


def _retired_names():
    """Commands deliberately retired from canon — absence downstream is CORRECT.

    FALSE POSITIVE FIXED (s138): a retired command still sitting in a spoke's
    managed tree was reported as "NOT PROPAGATED" drift, i.e. as a capability the
    adopter was missing. It is the opposite — it is something they should not have.
    Four instruments this session produced confident, specific, wrong findings;
    this was the fourth, and it would have fired during a live demo.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import deploy_commands  # noqa: PLC0415
        return set(deploy_commands.RETIRED)
    except Exception:  # noqa: BLE001 — never fail a check on an optional import
        return set()


def _compare(root, a_rel, b_rel, label_a, label_b, only_ext=None):
    a, b = _files(os.path.join(root, a_rel)), _files(os.path.join(root, b_rel))
    for name in _retired_names():
        a.pop(name, None)
        b.pop(name, None)
    if only_ext:
        a = {k: v for k, v in a.items() if k.endswith(only_ext)}
        b = {k: v for k, v in b.items() if k.endswith(only_ext)}
    drifted = sorted(n for n in set(a) & set(b) if a[n] != b[n])
    return {
        "pair": f"{label_a} -> {label_b}",
        "drifted": drifted,
        "only_in_source": sorted(set(a) - set(b)),
        "only_in_target": sorted(set(b) - set(a)),
        "compared": len(set(a) & set(b)),
    }


def check(root):
    layers = [
        # Template ahead of canon is the DANGEROUS direction: an edit that never ran.
        _compare(root, TEMPLATES, CANON, "templates(authored)", "canon(source-of-truth)", ".md"),
        # Canon ahead of deployed is the RECOVERABLE direction: run a deploy.
        _compare(root, CANON, DEPLOYED, "canon(source-of-truth)", "deployed(what runs)", ".md"),
        _compare(root, CANON_HOOKS, DEPLOYED_HOOKS, "canon-hooks", "deployed-hooks"),
    ]
    total = sum(len(l["drifted"]) for l in layers)
    missing = sum(len(l["only_in_source"]) for l in layers)
    return {"ok": total == 0 and missing == 0, "drift_count": total,
            "undeployed_count": missing, "layers": layers}


def cmd_check(args, root):
    rep = check(root)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0 if rep["ok"] else 1

    print("CANONICAL ADHERENCE — does what runs match what canon says?")
    for l in rep["layers"]:
        state = "OK" if not l["drifted"] and not l["only_in_source"] else "DRIFT"
        print(f"\n  [{state}] {l['pair']}  ({l['compared']} compared)")
        for n in l["drifted"]:
            print(f"      differs:      {n}")
        for n in l["only_in_source"]:
            print(f"      NOT PROPAGATED: {n}")
        for n in l["only_in_target"]:
            print(f"      target-only:  {n}")

    if rep["ok"]:
        print("\n  No drift. What runs is what canon says.")
    else:
        print(f"\n  {rep['drift_count']} drifted, {rep['undeployed_count']} not propagated.")
        print("  Direction decides the fix:")
        print("    canon -> deployed drift    : run deploy_commands.py (recoverable)")
        print("    templates -> canon drift   : an edit may have been SILENTLY DEAD.")
        print("      Reconcile, then check how long it never ran — anything that")
        print("      depended on it was not actually protected.")
    return 0 if rep["ok"] else 1


def cmd_explain(args, root):
    print(__doc__)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Canonical adherence across command/hook layers")
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--json", action="store_true")
    sub.add_parser("explain")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    return {"check": cmd_check, "explain": cmd_explain}[args.cmd](args, root)


if __name__ == "__main__":
    sys.exit(main())
