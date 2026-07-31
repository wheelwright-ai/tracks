#!/usr/bin/env python3
"""contract_duplication_scan.py — find one rule written down in two places.

THE DEFECT CLASS THIS EXISTS FOR. Three separate failures on 2026-07-31 were the
same shape: a contract defined twice, in modules that disagreed.

  landing        two gates each had their own idea of "landed", so three checks
                 passed while 17 commits sat off canon
  chain verdict  the halt rule was enumerated per verdict type, so CLEAN was
                 printed over a halted run — fixed for REFUTED, recurred for
                 UNVERIFIABLE, recurred again for PROCESS-FAULT
  bytype shape   the skeleton builder and the validator disagreed on required
                 folders, so a freshly scaffolded spoke failed its own structure
                 check by construction

Each was found reactively, after it caused damage. This finds them first.

DISAGREEMENT IS THE SIGNAL, NOT DUPLICATION. Two copies that happen to agree are
latent risk and are reported as such. Two copies that DISAGREE are a live bug:
somewhere in the wheel, two tools are giving different answers about the same
thing right now. Measured on first run: 4 of 5 lifecycle contracts disagreed,
including TERMINAL_STATES, where work_split counts a lug in state "done" as
finished and routing_vocab counts it as live.

It reads CONSTANT-shaped definitions only. That is deliberate: a shared constant
is how this wheel writes its contracts, and widening to every duplicated literal
would bury the signal in noise.

Usage:
    contract_duplication_scan.py                 # human report
    contract_duplication_scan.py --json
    contract_duplication_scan.py --fail-on-disagree     # exit 1 for a gate
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import re
import sys

_DEF = re.compile(r'^([A-Z][A-Z0-9_]{5,})\s*=\s*([\(\{\[].*?[\)\}\]])', re.M | re.S)
_LIT = re.compile(r'"([^"]+)"|\'([^\']+)\'')

# Names that are configuration rather than contract — duplication here is
# expected and says nothing about correctness.
_IGNORE = {"REQUIRED_FIELDS", "PROVIDERS", "TIER_ORDER", "CHECKS", "PROBES"}


def literals(body: str) -> tuple:
    return tuple(sorted({a or b for a, b in _LIT.findall(body)}))


def scan(root: str = ".", patterns=("WAI-Harness/**/tools/*.py",)) -> dict:
    found = collections.defaultdict(dict)
    for pattern in patterns:
        for f in glob.glob(os.path.join(root, pattern), recursive=True):
            if "__pycache__" in f or "/tests/" in f:
                continue
            try:
                src = open(f, encoding="utf-8").read()
            except Exception:  # noqa: BLE001
                continue
            for m in _DEF.finditer(src):
                name = m.group(1)
                if name in _IGNORE:
                    continue
                found[name][os.path.basename(f)] = literals(m.group(2))

    disagree, agree = [], []
    for name, mods in found.items():
        if len(mods) < 2:
            continue
        distinct = {v for v in mods.values()}
        entry = {"contract": name, "modules": sorted(mods),
                 "definitions": {k: list(v) for k, v in mods.items()}}
        (disagree if len(distinct) > 1 else agree).append(entry)

    return {"ok": True,
            "disagree": sorted(disagree, key=lambda e: -len(e["modules"])),
            "agree": sorted(agree, key=lambda e: e["contract"]),
            "disagree_count": len(disagree), "agree_count": len(agree)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail-on-disagree", action="store_true")
    a = ap.parse_args(argv)
    rep = scan(a.root)

    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        print("CONTRACT DUPLICATION — %d disagreeing, %d agreeing-but-duplicated"
              % (rep["disagree_count"], rep["agree_count"]))
        print()
        for e in rep["disagree"]:
            print("  DISAGREE  %-24s across %d module(s)"
                  % (e["contract"], len(e["modules"])))
            for mod, vals in e["definitions"].items():
                print("      %-34s %s" % (mod, ", ".join(vals)[:88]))
        if rep["agree"]:
            print()
            print("  latent (copies agree today, nothing keeps them in step):")
            for e in rep["agree"]:
                print("      %-24s %s" % (e["contract"], ", ".join(e["modules"])[:70]))
    return 1 if (a.fail_on_disagree and rep["disagree_count"]) else 0


if __name__ == "__main__":
    sys.exit(main())
