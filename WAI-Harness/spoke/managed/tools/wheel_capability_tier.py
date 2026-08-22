#!/usr/bin/env python3
"""wheel_capability_tier.py — a wheel's tier is DETECTED, never declared.

WHY
---
Measured 2026-08-17: hub-registry.json holds 35 wheels with NO capability tier;
`current_phase` is free text with inconsistent values; 24 of 35 carry no
`policy`; there are 20+ distinct keyset shapes. Anything routing work to a
wheel by what the wheel SAYS about itself is routing on marketing. This tool
derives the tier from structural evidence on disk — what the wheel HAS, not
what it claims — and writes the detection back to the registry with the
evidence named. It must never read a declared tier field.

THE TIERS (cumulative — a wheel is tier N only if EVERY tier 1..N has at
least one detected capability; a gap at tier 2 caps the wheel at tier 1 even
when tier-3 capabilities are present):

  1 harness-present   it carries the machinery: a kernel entry point, or a
                      lug tree the kernel can work
  2 verified-operation the machinery is exercised: tests exist, and a harness
                      mode is detectable (hook or managed MANIFEST)
  3 self-improving    it watches itself: advisors on disk, and CI workflows

VERBS
-----
  scan [--registry PATH]          detect + print, mutate nothing (default)
  scan --write [--registry PATH]  write capability_tier + capability_tier_evidence
                                  back into the registry
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

TOOL_VERSION = "1.0.0"

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_DEFAULT_REGISTRY = os.path.join(
    _DEFAULT_ROOT, "WAI-Harness", "hub", "local", "hub-registry.json")


def _is_dir(p):
    return os.path.isdir(p)


def _is_file(p):
    return os.path.isfile(p)


def _any_glob(pat):
    return bool(glob.glob(pat))


# Each capability: (name, detector over the wheel root -> evidence path or None).
# Detectors return the path that proves the capability, never a bare True.
def _kernel(root):
    p = os.path.join(root, "WAI-Harness", "kernel", "bin", "wai")
    return p if _is_file(p) else None


def _lug_tree(root):
    p = os.path.join(root, "WAI-Harness", "spoke", "local", "lugs", "bytype")
    return p if _is_dir(p) else None


def _tests(root):
    for rel in (("WAI-Harness", "spoke", "managed", "tests"),
                ("WAI-Harness", "hub", "managed", "tests"),
                ("WAI-Harness", "kernel", "tests")):
        d = os.path.join(root, *rel)
        if _is_dir(d) and glob.glob(os.path.join(d, "test_*.py")):
            return d
    return None


def _harness_mode(root):
    hook = os.path.join(root, ".claude", "hooks", "harness_mode.sh")
    if _is_file(hook):
        return hook
    manifest = os.path.join(root, "WAI-Harness", "spoke", "managed", "MANIFEST.json")
    return manifest if _is_file(manifest) else None


def _advisors(root):
    for rel in (("WAI-Harness", "spoke", "local", "advisors"),
                ("WAI-Harness", "hub", "managed", "advisors"),
                ("WAI-Spoke", "advisors")):
        d = os.path.join(root, *rel)
        if _is_dir(d) and os.listdir(d):
            return d
    return None


def _ci(root):
    d = os.path.join(root, ".github", "workflows")
    if _is_dir(d) and glob.glob(os.path.join(d, "*.yml")) + glob.glob(os.path.join(d, "*.yaml")):
        return d
    return None


TIERS = [
    ("harness-present", {"kernel": _kernel, "lug_tree": _lug_tree}),
    ("verified-operation", {"tests": _tests, "harness_mode": _harness_mode}),
    ("self-improving", {"advisors": _advisors, "ci": _ci}),
]


def detect_tier(root):
    """Pure detection. Returns (tier:int, evidence:dict). Never reads any
    declared field — the only input is the filesystem under `root`. Cumulative:
    the first tier with NO detected capability caps the result."""
    evidence = {}
    tier = 0
    gapped = False
    for level, (label, caps) in enumerate(TIERS, start=1):
        found = {}
        for name, detector in caps.items():
            try:
                proof = detector(root)
            except OSError:
                proof = None
            if proof:
                found[name] = os.path.relpath(proof, root)
        evidence[label] = found
        if not found:
            gapped = True  # cumulative: a gap caps every tier above it,
        elif not gapped:   # but detection still REPORTS what exists above the gap
            tier = level
    return tier, evidence


def scan_registry(registry_path, write=False):
    with open(registry_path, encoding="utf-8") as f:
        reg = json.load(f)
    rows = []
    changed = False
    for wheel in reg.get("wheels", []):
        wid = wheel.get("wheel_id") or wheel.get("spoke_id") or "?"
        path = wheel.get("path") or ""
        if not path or not os.path.isdir(path):
            rows.append({"wheel": wid, "tier": None, "note": "path missing on disk"})
            continue
        tier, evidence = detect_tier(path)
        rows.append({"wheel": wid, "tier": tier})
        if write:
            if wheel.get("capability_tier") != tier or \
               wheel.get("capability_tier_evidence") != evidence:
                wheel["capability_tier"] = tier
                wheel["capability_tier_evidence"] = evidence
                changed = True
    if write and changed:
        tmp = registry_path + ".tmp-wheel-capability-tier"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(reg, f, indent=2)
            f.write("\n")
        os.replace(tmp, registry_path)
    return rows, changed


def main(argv=None):
    ap = argparse.ArgumentParser(description="detect (never declare) wheel capability tiers")
    ap.add_argument("--registry", default=_DEFAULT_REGISTRY)
    ap.add_argument("--write", action="store_true",
                    help="write capability_tier + evidence back (default: print only)")
    args = ap.parse_args(argv)
    rows, changed = scan_registry(args.registry, write=args.write)
    dist = {}
    for r in rows:
        dist[r["tier"]] = dist.get(r["tier"], 0) + 1
    for r in rows:
        note = r.get("note", "")
        print("  {:24s} tier {} {}".format(r["wheel"], r["tier"],
                                           "({})".format(note) if note else ""))
    print("wheel_capability_tier — {} wheels: {}".format(
        len(rows), ", ".join("{} x{}".format(k, v) for k, v in sorted(
            dist.items(), key=lambda kv: (kv[0] is None, kv[0])))))
    if args.write:
        print("registry {}".format("updated" if changed else "already current"))
    else:
        print("dry-run — pass --write to record into the registry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
