#!/usr/bin/env python3
"""manifest_build.py — MD5 integrity manifest for the managed/ master (Stream F).

(impl-v4-harness-skeleton-v1) Walks spoke/managed/, computes an MD5 per file, and
writes MANIFEST.json: {harness_version, is_master, generated_at, files:{rel ->
{version, md5, owner}}}. This is the integrity contract that makes distribution
trustworthy two ways:

  - --verify reports any managed file whose on-disk MD5 no longer matches the
    recorded hash — i.e. an unauthorized edit to an agent-read-only file.
  - the recorded hashes are the basis for Basher's own-copy "upgrade-when-newer"
    check: a spoke pulls a managed file only when the master's hash differs.

build() and verify() are pure over an injected managed dir + manifest path, so
they are unit-testable and path-parameterized.

API:
  build(managed_dir, manifest_path, harness_version=..., now_iso=None) -> manifest
  verify(managed_dir, manifest_path) -> {"ok": bool, "mismatches": [...], "missing": [...], "new": [...]}
"""
import argparse
import hashlib
import json
import os
import sys

MANIFEST_NAME = "MANIFEST.json"
DEFAULT_OWNER = "basher"          # managed/ = Basher-distributed
DEFAULT_VERSION = "4.0.0-pre"
VERSION_FILE = "VERSION"          # single source of truth at the WAI-Harness root


class CutGateError(Exception):
    """Raised when the fail-closed cut gate refuses a manifest cut. build() is the
    ONE choke point for the gate (impl-consolidate-cut-gate-v1) -- every caller
    (this CLI, harness_upgrade.py's `manifest --write`) routes through build() and
    must treat this as a hard refusal, never a silent skip."""
    pass


def _run_cut_gate(managed_dir):
    """The single fail-closed cut gate. Runs the v3-path lint (mandatory -- an
    ImportError or a lint FAIL both raise CutGateError, never a silent skip) and,
    if present, the not-yet-built deprecation scan (also fail-closed once it
    exists; its ABSENCE is the only silent-skip permitted here).

    Raises CutGateError on any refusal. Returns None on a clean gate."""
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import v3_path_lint
    except Exception as e:  # noqa: BLE001 -- fail-closed: an unimportable lint refuses the cut
        raise CutGateError(
            "cut gate: v3_path_lint unavailable (%s) -- refusing to cut (fail-closed)" % e)

    rep = v3_path_lint.lint(managed_dir)
    if not rep["ok"]:
        lines = []
        for rel, hits in rep["violations"].items():
            first = hits[0] if hits else (None, None)
            lines.append(f"  {rel}: L{first[0]}: {first[1]}")
        raise CutGateError(
            "cut gate: v3-path lint FAILED -- NEW v3-husk (WAI-Spoke) sole-path reference(s), "
            "refusing to cut:\n" + "\n".join(lines))

    # Deprecation scan: a separate not-yet-built lug (impl-deprecation-scan-per-line-
    # and-docs-v1). Activates automatically once tools/deprecation_scan.py ships --
    # until then this arm is a silent no-op (the ONLY silent-skip in this gate; the
    # v3-lint arm above is never skippable).
    dep_scan_path = os.path.join(managed_dir, "tools", "deprecation_scan.py")
    if os.path.isfile(dep_scan_path):
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(dep_scan_path)))
            import deprecation_scan
        except Exception as e:  # noqa: BLE001 -- fail-closed once the tool exists
            raise CutGateError(
                "cut gate: deprecation_scan unavailable (%s) -- refusing to cut (fail-closed)" % e)
        dep_rep = deprecation_scan.scan(managed_dir)
        if not dep_rep.get("ok", True):
            raise CutGateError(
                "cut gate: deprecation scan FAILED -- refusing to cut: %s" % dep_rep)


def read_version(managed_dir, fallback=DEFAULT_VERSION):
    """Read the canonical harness version from the nearest VERSION file (walking up from
    managed_dir to the WAI-Harness root), so the manifest stamps the REAL version instead
    of a hardcoded constant. Bump that one file as the harness evolves. Fallback if absent."""
    d = os.path.abspath(managed_dir)
    for _ in range(4):  # managed -> spoke -> WAI-Harness -> (root)
        vf = os.path.join(d, VERSION_FILE)
        if os.path.isfile(vf):
            try:
                v = open(vf).read().strip()
                if v:
                    return v
            except OSError:
                pass
        d = os.path.dirname(d)
    return fallback

# build/runtime artifacts that are never source, never distributed, and whose
# bytes are non-deterministic (bytecode regenerates on import) — excluding them
# is what lets the master self-verify stably. Mirrors harness_upgrade._excluded.
# "tests": the harness's OWN suite is NOT distributed (operator decision 2026-07-14).
#   "Keep the tests where we keep the cut of the harness centrally - no point to
#    distributing them. The execution record can live locally and results. This way the
#    test suite is paired to the harness at all time. Also stops the unnecessary bytes
#    moving around."
#   The suite lives WITH the cut and is versioned with it, so a suite can never drift from
#   the harness it tests. A spoke does not need to HOLD the tests to be tested BY them:
#   it runs them from the cut and keeps the execution record + results locally.
#   Evidence it was never coherent to ship them: the shipped suite is 1204/0 on master and
#   97-failed/23-errors inside basher, because it tests master's tools against a tree with
#   no hub (bug-shipped-harness-suite-is-red-in-every-spoke-v1). 172 files / 1.0 MB per
#   spoke x16 = ~17 MB moved to be red on arrival.
#   NOTE this is a DIRECTORY-NAME match on any path component, and exactly one dir named
#   tests/ exists under managed/ (verified 2026-07-14). If a template ever needs to ship a
#   tests/ dir, this must become a rooted-prefix rule, not a name match.
_EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git", "runtime", "tests"}  # runtime: generated state (capabilities-effective.json), never distribute
_EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".db-wal", ".db-shm")
# Transient generated runtime state that a stray test/tool run can drop anywhere in the tree
# (e.g. a CWD-relative db_writer journal under tests/WAI-Spoke/). These are NEVER distributable
# source; excluding them by NAME makes a cut immune to pollution regardless of where it lands,
# without touching legitimately-tracked template dirs (templates/**/WAI-Spoke/).
# (impl-managed-tests-cwd-dbwriter-pollution-v1)
_EXCLUDE_NAMES = {".DS_Store", "events-journal.jsonl", "harness.db", "harness.db-wal", "harness.db-shm"}


def _excluded(rel):
    parts = rel.replace(os.sep, "/").split("/")
    if any(p in _EXCLUDE_DIRS for p in parts):
        return True
    if rel.endswith(_EXCLUDE_SUFFIXES):
        return True
    return parts[-1] in _EXCLUDE_NAMES


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk_managed(managed_dir):
    """Relative paths of every file under managed/, EXCEPT the manifest itself."""
    out = {}
    for dirpath, dirs, files in os.walk(managed_dir):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRS]  # prune cache dirs
        for name in files:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, managed_dir)
            if rel == MANIFEST_NAME:
                continue  # the manifest never hashes itself
            if _excluded(rel):
                continue  # never distribute bytecode/cache/OS cruft
            out[rel] = full
    return out


def build(managed_dir, manifest_path=None, harness_version=DEFAULT_VERSION, now_iso=None,
         master_sha=None, skip_lint=False, skip_lint_reason=None):
    """Compute MD5 per managed file and write MANIFEST.json. Idempotent: the same
    tree yields the same files map (only generated_at/master_sha move).

    now_iso/master_sha are INJECTED (not defaulted here) so build() stays pure and
    unit-testable — callers that want reproducible fixtures pass fixed values; the
    CLI (main()) is where a real cut defaults them to wall-clock time + the actual
    git HEAD (W4.1: manifest cut provenance — a cut with no timestamp/SHA cannot be
    traced back to the commit that produced it).

    build() is the SINGLE fail-closed cut gate (impl-consolidate-cut-gate-v1): every
    cut runs _run_cut_gate() before anything is written, unless skip_lint is set --
    and skip_lint REQUIRES a non-empty skip_lint_reason (the escape hatch is never
    silent; it is recorded IN the written manifest as cut_gate_skipped)."""
    if skip_lint:
        if not (skip_lint_reason and skip_lint_reason.strip()):
            raise CutGateError("--skip-lint requires an explicit non-empty reason string")
    else:
        _run_cut_gate(managed_dir)

    manifest_path = manifest_path or os.path.join(managed_dir, MANIFEST_NAME)
    # preserve recorded owner/version where present
    prior = {}
    if os.path.exists(manifest_path):
        try:
            prior = json.load(open(manifest_path)).get("files", {})
        except (ValueError, OSError):
            prior = {}
    files = {}
    for rel, full in sorted(_walk_managed(managed_dir).items()):
        files[rel] = {"version": prior.get(rel, {}).get("version", harness_version),
                      "md5": _md5(full),
                      "owner": prior.get(rel, {}).get("owner", DEFAULT_OWNER)}
    manifest = {"harness_version": harness_version, "is_master": True,
                "generated_at": now_iso, "master_sha": master_sha, "files": files}
    if skip_lint and skip_lint_reason:
        manifest["cut_gate_skipped"] = {"reason": skip_lint_reason.strip()}
    json.dump(manifest, open(manifest_path, "w"), indent=2)
    return manifest


def verify(managed_dir, manifest_path=None):
    """Compare on-disk managed files against the recorded manifest.
    mismatches = recorded file whose hash changed (unauthorized edit);
    missing = recorded file now absent; new = on-disk file not in the manifest (an
    ORPHAN: managed code no cut ever attested).

    ALL THREE fail the verdict (fix-verify-and-apply-orphan-and-deletion-semantics-v1).
    `new` used to be computed, returned, and then dropped from `ok` -- so verify()
    SAW an unrecorded managed file and reported ok:True anyway. That silent drop is
    what let a half-landed change read clean:

      - new managed code committed WITHOUT a recut passed manifest_integrity_precommit
        (the exact drift its own docstring exists to block) and then never shipped,
        because distribution only ever copies files the manifest lists;
      - a migration (a mass move-and-retire) half-landed with every gate green.

    An unattested file breaks the integrity contract exactly as much as an edited
    one: the manifest cannot vouch for bytes it never hashed. The remedy is always
    a recut (or removing the stray file) -- never a silent pass. If a managed file
    must legitimately go unhashed, exclude it BY NAME via _EXCLUDE_* above, where
    the exemption is explicit, reviewable, and applies to a named path; never by
    quietly widening `ok`."""
    manifest_path = manifest_path or os.path.join(managed_dir, MANIFEST_NAME)
    recorded = json.load(open(manifest_path)).get("files", {})
    on_disk = _walk_managed(managed_dir)
    mismatches, missing = [], []
    for rel, meta in recorded.items():
        full = on_disk.get(rel)
        if not full:
            missing.append(rel)
        elif _md5(full) != meta.get("md5"):
            mismatches.append(rel)
    new = [rel for rel in on_disk if rel not in recorded]
    return {"ok": not (mismatches or missing or new), "mismatches": mismatches,
            "missing": missing, "new": new}


def _git_sha(path, fallback=None):
    """Best-effort git HEAD SHA of the repo containing `path` — the cut provenance
    stamp (which commit produced this manifest). Never raises."""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else fallback
    except Exception:
        return fallback


def main(argv=None):
    import datetime as _dt
    ap = argparse.ArgumentParser(description="build or verify the managed/ MD5 manifest")
    ap.add_argument("managed_dir")
    ap.add_argument("--manifest-path", default=None)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--harness-version", default=None,
                    help="default reads the VERSION file at the WAI-Harness root (bump that to evolve)")
    ap.add_argument("--now-iso", default=None,
                    help="cut timestamp; default is real wall-clock UTC (fixed value = reproducible test fixture)")
    ap.add_argument("--master-sha", default=None,
                    help="master git HEAD SHA at cut; default resolves via `git rev-parse HEAD` in managed_dir's repo")
    ap.add_argument("--parity-strict", action="store_true",
                    help="fail the cut (exit 1) if path_parity_check finds a NEW unpaired "
                         "v3-husk-path resolver vs its baseline (P12 followup #4)")
    ap.add_argument("--skip-lint", action="store_true",
                    help="escape hatch past the fail-closed cut gate; REQUIRES --skip-lint-reason")
    ap.add_argument("--skip-lint-reason", default=None,
                    help="non-empty reason recorded into the manifest as cut_gate_skipped "
                         "(required when --skip-lint is set)")
    a = ap.parse_args(argv)
    if a.verify:
        res = verify(a.managed_dir, a.manifest_path)
        print(json.dumps(res, indent=2))
        return 0 if res["ok"] else 1
    version = a.harness_version or read_version(a.managed_dir)
    now_iso = a.now_iso or _dt.datetime.now(_dt.timezone.utc).isoformat()
    master_sha = a.master_sha or _git_sha(a.managed_dir)
    try:
        m = build(a.managed_dir, a.manifest_path, version, now_iso, master_sha,
                  skip_lint=a.skip_lint, skip_lint_reason=a.skip_lint_reason)
    except CutGateError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"[manifest_build] {len(m['files'])} managed file(s) hashed -> "
          f"{a.manifest_path or os.path.join(a.managed_dir, MANIFEST_NAME)}")
    parity_rc = _run_parity_gate(a.managed_dir)
    _run_ceremony_gates(a.managed_dir)  # advisory: ceremony drift + token budget
    return 1 if (a.parity_strict and parity_rc != 0) else 0


def _run_ceremony_gates(managed_dir):
    """Run the ceremony guards AT THE CUT (initiative-optimize-ceremonies-v1):
    token-budget (ceremonies stay lean) + drift (templates mirror canonical).
    Advisory, best-effort — surfaced at cut so re-bloat/drift can't land silently."""
    import subprocess
    for tool, args in (
        ("ceremony_token_budget.py", ["--commands", os.path.join(managed_dir, ".claude", "commands")]),
        ("ceremony_drift_check.py", ["--root", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(managed_dir))))]),
    ):
        gate = os.path.join(managed_dir, "tools", tool)
        if not os.path.isfile(gate):
            continue
        try:
            r = subprocess.run([sys.executable, gate, *args], capture_output=True, text=True)
        except OSError:
            continue
        out = (r.stdout or "").strip()
        if out:
            print(out.splitlines()[0])  # one-line summary at cut


def _run_parity_gate(managed_dir):
    """Run the v3->v4 path-parity regression gate AT THE CUT (P12 followup #4). Always
    runs (advisory), so a NEW unpaired v3-husk-path is surfaced the moment it is cut;
    --parity-strict promotes it to a hard cut failure. Best-effort: a missing gate tool
    never breaks the manifest build."""
    gate = os.path.join(managed_dir, "tools", "path_parity_check.py")
    if not os.path.isfile(gate):
        return 0
    import subprocess
    try:
        r = subprocess.run([sys.executable, gate, managed_dir, "--check"],
                           capture_output=True, text=True)
    except OSError:
        return 0
    out = (r.stdout or "").strip()
    if out:
        print(out)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
