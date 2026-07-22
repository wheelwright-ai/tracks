#!/usr/bin/env python3
"""harness_pullcheck.py - the spoke-side wakeup pull-check (impl-dist-spoke-pullcheck-v1).

SessionStart's existing pull-on-spin-up (harness_upgrade.pull) brings a spoke to whatever
the master's managed/ tree currently holds, with no notion of per-group certification --
it syncs to master's raw HEAD. This tool is the missing half: before pulling, resolve this
spoke's GROUP (hub-registry.json + groups.json, same membership model
distribution_circuit_check.py already reads) and ask the A1 availability gate
(harness_availability.py) what version is AVAILABLE for that group. The pull then goes
through harness_upgrade.pull()'s existing expect_version contract: it refuses (writes
nothing) unless master's CURRENT harness_version equals exactly what was certified, so a
cut that moved past AVAILABLE without being re-certified is never pulled -- pull-first
adoption, gated to the certified release train instead of master's raw HEAD.

Fail-open where no group/availability data exists (no group resolved, or the group has
never had a version marked AVAILABLE): falls back to today's ungated pull, unchanged. No
group has been marked AVAILABLE in production as of this writing (impl-dist-availability-
gate-v1 shipped the mechanism, not any data), so gating strictly on it fleet-wide would
silently stop the self-heal pull-on-spin-up for every spoke. Once an operator marks a
group's version AVAILABLE, spokes in that group start being gated by it automatically --
no further code change needed.
"""
import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harness_upgrade as hu  # noqa: E402


def _semver_key(version_str):
    """Loose semver ordering: numeric dot/hyphen components sort as ints, sort as
    strings otherwise. Mirrors track_prompt_freshness_check._semver_key."""
    parts = []
    for p in re.split(r"[.\-]", str(version_str or "")):
        try:
            parts.append((0, int(p)))
        except ValueError:
            parts.append((1, p))
    return tuple(parts)


def _load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return None


def resolve_wheel_id(spoke_root, registry_wheels):
    """spoke_root -> wheel_id via hub-registry.json path match (realpath, so a
    worktree checkout of a registered spoke still resolves)."""
    rp = os.path.realpath(spoke_root)
    for w in registry_wheels or []:
        p = w.get("path")
        if p and os.path.realpath(p) == rp:
            return w.get("wheel_id")
    return None


def resolve_group(wheel_id, groups):
    """wheel_id -> group_id, first membership match. Mirrors
    distribution_circuit_check._group_for_spoke (same first-match simplification for
    a spoke that legitimately holds membership in more than one group, e.g. basher)."""
    if not wheel_id:
        return None
    for g in groups or []:
        for m in g.get("members", []):
            if m.get("wheel_id") == wheel_id:
                return g.get("group_id")
    return None


def _load_availability_module(master_root):
    """Import harness_availability.py from its live location under
    master_root/hub/local/tools -- its module-level STORE path is derived from
    __file__, so importing it from there (rather than vendoring a copy) is what
    makes it read the real registry/harness-availability.json. None on any failure
    (missing hub tree, e.g. a spoke-only master pin) -- fail-open, never fatal."""
    try:
        path = Path(master_root) / "hub" / "local" / "tools" / "harness_availability.py"
        if not path.exists():
            return None
        spec = importlib.util.spec_from_file_location("harness_availability", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def _local_version(spoke_root):
    """This spoke's currently-running harness version. WAI-Harness/VERSION is the
    single source of truth harness_upgrade._stamp_harness_version writes; fall back
    to the spoke's own managed MANIFEST.json when VERSION is missing/stale-empty."""
    vf = Path(spoke_root) / "WAI-Harness" / "VERSION"
    if vf.exists():
        v = vf.read_text().strip()
        if v:
            return v
    manifest = _load_json(Path(spoke_root) / "WAI-Harness" / "spoke" / "managed" / hu.MANIFEST_NAME)
    if manifest:
        return manifest.get("harness_version")
    return None


def check(spoke_root, master_root=None, dry_run=False, validate=True):
    """Resolve this spoke's group, query hub AVAILABLE for it, and pull gated by
    that version. Returns {"gate": {...}, "pull": <harness_upgrade.pull() report or
    None>}. Presence-guarded throughout: a missing hub tree, registry, or groups
    file degrades to "no group resolved" rather than raising.
    """
    master_root = master_root or hu.resolve_master(spoke_root)
    wh = Path(spoke_root) / "WAI-Harness"
    if not wh.is_dir():
        return {"gate": {"decision": "no-harness"}, "pull": None}

    registry = _load_json(Path(master_root) / "hub" / "local" / "hub-registry.json") or {}
    groups_doc = _load_json(Path(master_root) / "hub" / "local" / "registry" / "groups.json") or {}
    wheel_id = resolve_wheel_id(spoke_root, registry.get("wheels", []))
    group = resolve_group(wheel_id, groups_doc.get("groups", []))

    available = None
    if group:
        ha = _load_availability_module(master_root)
        if ha is not None:
            try:
                available = ha.available_version(group)
            except Exception:
                available = None

    local_version = _local_version(spoke_root) or "0"
    gate = {"wheel_id": wheel_id, "group": group,
            "local_version": local_version, "available_version": available}

    expect_version = None
    if available:
        if _semver_key(local_version) > _semver_key(available):
            # Ahead of what this group has certified -- never a downgrade pull.
            gate["decision"] = "ahead-of-available"
            return {"gate": gate, "pull": None}
        expect_version = available
        gate["decision"] = "gated"
    else:
        # No group resolved, or the group has no AVAILABLE cut recorded yet: today's
        # unconditioned pull-on-spin-up (no regression while availability data is
        # still being populated fleet-wide).
        gate["decision"] = "ungated"

    rep = hu.pull(spoke_root, master_root, dry_run=dry_run,
                  expect_version=expect_version, validate=validate)
    return {"gate": gate, "pull": rep}


def main(argv):
    ap = argparse.ArgumentParser(
        description="spoke-side wakeup pull-check: gate SessionStart's pull by hub "
                     "AVAILABLE for this spoke's group (falls back to the unconditioned "
                     "pull when no group/AVAILABLE data is resolvable)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="resolve group -> query AVAILABLE -> gated pull")
    c.add_argument("--spoke-root", default=".")
    c.add_argument("--master", default=None,
                   help="master path; default resolves via $WAI_HARNESS_MASTER -> "
                        ".harness-master -> built-in")
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--no-validate", action="store_true",
                   help="skip post-apply validation, threaded through to harness_upgrade.pull")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        rep = check(args.spoke_root, args.master, dry_run=args.dry_run,
                    validate=not args.no_validate)
        print(json.dumps(rep, indent=2))
        pull_status = (rep.get("pull") or {}).get("status")
        return 0 if pull_status not in ("failed", "version-desync") else 1
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
