#!/usr/bin/env python3
"""harness_upgrade.py - the verify-apply-verify upgrade engine (v4 distribution).

The cutover gate: before WAI-Harness becomes the registered master, the path by
which a spoke (or the hub) PULLS the master's managed tree must be proven to work
and to be safe. This is that engine.

Model (matches the master layout):
  WAI-Harness/spoke/managed/   - manifest-controlled, MD5-verified, DISTRIBUTED.
                                 Overwritten on upgrade. Carries MANIFEST.json.
  WAI-Harness/spoke/local/     - per-spoke. NEVER touched by an upgrade.
  (hub/managed + hub/local mirror this for the hub.)

The engine only ever reads/writes under the target's `managed/` root. It cannot
touch `local/` by construction (it iterates the manifest's file list, all of which
are managed paths), so the per-spoke local guarantee holds mechanically.

Loop:
  1. verify-pre  -> home_map: per managed file, ADD / CHANGE / UNCHANGED vs master
                   (+ ORPHAN: a managed file in the target absent from the master).
                   --dry-run stops here: a full preview, zero writes.
  2. apply       -> copy each master managed file into the target managed root, and
                    RETIRE files the target's PREVIOUS manifest listed that the new
                    one does not (a retirement, never a purge — see apply()).
  3. verify-post -> recompute the target's md5s and assert they equal the master
                   MANIFEST. A mismatch is an upgrade FAILURE, not a silent pass.

Pure-ish core (filesystem only, no network): build_manifest, compute_home_map,
verify, apply, upgrade. CLI wraps with subcommands.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "MANIFEST.json"
VERSION_FILE = "VERSION"          # WAI-Harness root; same source of truth manifest_build reads
DEFAULT_VERSION = "4.0.0-pre"
DEFAULT_MASTER = "/home/mario/projects/wheelwright/mywheel/WAI-Harness"
MASTER_CONFIG = ".harness-master"   # per-spoke file under WAI-Harness/ holding the master path


def resolve_master(spoke_root=None, fallback=DEFAULT_MASTER):
    """Resolve the master wheel path PORTABLY (clone-and-run on any machine):
      1. $WAI_HARNESS_MASTER env (highest — set per machine)
      2. <spoke_root>/WAI-Harness/.harness-master file (per-spoke pin)
      3. fallback (the build-machine default)
    Returns the first that exists on disk, else the env/config value as-is (so a
    deliberate offline value still surfaces), else the fallback. Never raises."""
    env = os.environ.get("WAI_HARNESS_MASTER")
    if env:
        return env
    if spoke_root:
        cfg = Path(spoke_root) / "WAI-Harness" / MASTER_CONFIG
        if cfg.exists():
            try:
                val = cfg.read_text().strip()
                if val:
                    return val
            except OSError:
                pass
    return fallback

# build/runtime artifacts that are never source, never distributed, and whose
# bytes are non-deterministic (bytecode regenerates on import) — excluding them
# is what lets the master self-verify stably.
#
# MUST MIRROR manifest_build._EXCLUDE_DIRS. These two lists deciding different things is a
# split-brain: manifest_build decides what is ATTESTED, this decides what is COPIED, and a
# file attested-but-not-copied reads as `missing` while copied-but-not-attested reads as an
# orphan. The read-what-the-other-one-says fix belongs in
# bug-two-exclude-lists-can-drift-v1; until then, change BOTH or neither.
#
# "tests": the harness's own suite is NOT distributed (operator decision 2026-07-14) — it
# lives WITH the cut, versioned with it, so the suite can never drift from the harness it
# tests. A spoke runs the suite FROM the cut and keeps the execution record + results
# locally; it does not need to hold the tests to be tested by them. See
# manifest_build._EXCLUDE_DIRS for the full rationale and evidence.
_EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git", "runtime", "tests"}  # runtime: generated state (capabilities-effective.json), never distribute

# TWO DIFFERENT QUESTIONS, and one list cannot answer both:
#   _excluded()  = "do NOT copy this IN"  (not distributed)
#   _protected() = "do NOT delete this OUT" (the spoke's own state — never ours to remove)
#
# For __pycache__/.git/runtime the answers coincide: never copied, never deleted. They were
# never in ANY manifest, so retiring them is both impossible and unwanted — and `runtime/`
# especially is generated spoke state that a delete would destroy.
#
# `tests` is the case that separates them: it WAS distributed (172 files, every spoke holds
# them today) and is now not. It must be copied NO and deleted YES — otherwise every spoke
# keeps 172 orphaned test files forever, invisible to verify, exactly the stranding the
# retire mechanism was built this morning to end.
#
# Found by testing rather than reasoning: adding "tests" to _EXCLUDE_DIRS silently emptied
# the retire set (0 files, basher kept all 175), because compute_retire_set filtered by
# _excluded(). The retire set's definition is PRIOR MANIFEST MINUS NEW MANIFEST; filtering
# it by the CURRENT exclusion policy corrupts that definition.
_PROTECTED_DIRS = {"__pycache__", ".pytest_cache", ".git", "runtime"}


def _protected(rel):
    """True for paths a distribution must NEVER delete from a target.

    Deliberately NOT _excluded(): 'we no longer ship this' and 'this is the spoke's own
    state' are different claims. Only the latter earns immunity from retirement.
    """
    parts = rel.replace(os.sep, "/").split("/")
    return any(p in _PROTECTED_DIRS for p in parts) or parts[-1] in _EXCLUDE_NAMES
_EXCLUDE_SUFFIXES = (".pyc", ".pyo")
_EXCLUDE_NAMES = {".DS_Store"}


def _excluded(rel):
    parts = rel.split("/")
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


def _iter_files(root):
    """All files under root, as posix relpaths (excludes the manifest itself)."""
    root = Path(root)
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != MANIFEST_NAME:
            rel = p.relative_to(root).as_posix()
            if not _excluded(rel):
                yield rel


def build_manifest(managed_root, version=DEFAULT_VERSION, is_master=True,
                   default_owner="framework", generated_at="1970-01-01T00:00:00Z"):
    """Compute a MANIFEST for a managed root. Preserves owner/version from a prior
    MANIFEST.json where present; new files get default_owner + version. generated_at
    is injected (no wall-clock) so the manifest is reproducible/testable."""
    managed_root = Path(managed_root)
    prior = {}
    mpath = managed_root / MANIFEST_NAME
    if mpath.exists():
        try:
            prior = json.loads(mpath.read_text()).get("files", {})
        except (OSError, json.JSONDecodeError):
            prior = {}
    files = {}
    for rel in _iter_files(managed_root):
        p = managed_root / rel
        files[rel] = {
            "version": prior.get(rel, {}).get("version", version),
            "md5": _md5(p),
            "owner": prior.get(rel, {}).get("owner", default_owner),
        }
    return {"harness_version": version, "is_master": is_master,
            "generated_at": generated_at, "files": files}


def load_manifest(managed_root):
    return json.loads((Path(managed_root) / MANIFEST_NAME).read_text())


def _write_neutralized_manifest(src_manifest_dir, dst_manifest_dir):
    """Write the target's MANIFEST.json as a copy of the master's but with
    is_master:false. Only the master (canonical author) keeps is_master:true; a
    DISTRIBUTED spoke that read is_master:true would wrongly treat itself as the
    canonical author (bug fix-manifest-is-master-neutralized-on-distribute-v1).
    MANIFEST.json is excluded from _iter_files(), so it is never md5-compared --
    flipping this flag never affects verify()'s file-hash check (stays green)."""
    m = json.loads((Path(src_manifest_dir) / MANIFEST_NAME).read_text())
    m["is_master"] = False
    (Path(dst_manifest_dir) / MANIFEST_NAME).write_text(json.dumps(m, indent=2) + "\n")


def _prior_manifest_files(managed_root):
    """The file map the TARGET's own MANIFEST.json records — what a previous
    distribution attested this target should hold.

    Missing/unreadable -> {}: with no prior attestation nothing can be PROVEN
    retired, and retiring nothing is the safe default. A delete is never guessed.
    """
    p = Path(managed_root) / MANIFEST_NAME
    if not p.exists():
        return {}
    try:
        files = json.loads(p.read_text()).get("files", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}
    return files if isinstance(files, dict) else {}


def _is_within(root, rel):
    """True only when root/rel resolves to a real location UNDER root. Guards the
    one destructive operation in this engine: a relpath out of a manifest this
    engine did not author ('../..', an absolute path, a symlink escaping the tree)
    must never let a delete reach outside the target's managed root."""
    try:
        root_r = Path(root).resolve()
        target = (root_r / rel).resolve()
        return target != root_r and root_r in target.parents
    except (OSError, ValueError, RuntimeError):
        return False


def compute_retire_set(master_files, target_managed):
    """Files the target's PREVIOUS manifest listed that the master's NEW manifest
    does not — i.e. the files master RETIRED. This, and only this, is what apply()
    deletes (fix-verify-and-apply-orphan-and-deletion-semantics-v1).

    Deliberately NOT home_map['orphan']. An orphan is anything in the target absent
    from the master manifest, which legitimately includes spoke-local files no
    manifest ever attested; deleting those would be a PURGE (explicitly rejected).
    The previous manifest is the evidence that upgrades "unknown file" into "master
    used to ship this and no longer does" — a retirement. retire ⊆ orphan, always.
    """
    prior = _prior_manifest_files(target_managed)
    target_root = Path(target_managed)
    out = []
    for rel in sorted(prior):
        # _protected, NOT _excluded: the retire set is PRIOR MANIFEST MINUS NEW MANIFEST.
        # Filtering it by the CURRENT exclusion policy corrupts that definition — a file we
        # stopped shipping is exactly what must be retired, and _excluded() now contains
        # such a case (`tests`). Only the spoke's own state (runtime/, .git/) is immune.
        if rel in master_files or _protected(rel) or rel == MANIFEST_NAME:
            continue
        if _is_within(target_root, rel) and (target_root / rel).is_file():
            out.append(rel)
    return out


def retire(target_managed, retire_set):
    """Delete exactly the files compute_retire_set() proved retired. Returns
    {retired:[rel], errors:[{file,error}]}. Never prunes directories, never touches
    a path outside retire_set, and never fails SILENTLY: an unlink error is reported
    up into the upgrade report rather than swallowed."""
    target_root = Path(target_managed)
    retired, errors = [], []
    for rel in retire_set:
        try:
            (target_root / rel).unlink()
            retired.append(rel)
        except OSError as e:
            errors.append({"file": rel, "error": str(e)[:120]})
    return {"retired": retired, "errors": errors}


def compute_clean_retire_set(master_files, target_managed, local_allow=None):
    """CLEAN-REPLACE retire set: EVERY managed file the master manifest does not list,
    not just the ones a prior manifest attested. This is the operator's 2026-07-24
    model — managed/ is a transient install workspace, never a home for spoke-local
    authoring — so a file the master does not ship is legacy cruft or a stranded local
    edit, and either way it must not survive the update. That is the whole guarantee:
    after a clean apply, managed == master exactly (modulo the two immunities below).

    This is deliberately WIDER than compute_retire_set() (which is prior-manifest-minus-
    new and refuses to touch never-attested files). It is only safe under the clean model,
    where nothing legitimately spoke-local lives in managed/, so it is OPT-IN (apply
    clean=True), not the default, until OQ1 relocates local files out of managed/.

    TWO IMMUNITIES, never purged:
      - _protected(rel): the spoke's own state (runtime/, .git/, MANIFEST).
      - local_allow: caller-supplied pins (e.g. basher.json .live_hooks.local_allow[])
        that are still legitimately local until their persistent home exists.
    """
    allow = set(local_allow or ())
    target_root = Path(target_managed)
    if not target_root.exists():
        return []
    out = []
    for rel in sorted(_iter_files(target_managed)):
        if rel in master_files or _protected(rel) or rel == MANIFEST_NAME or rel in allow:
            continue
        if _is_within(target_root, rel) and (target_root / rel).is_file():
            out.append(rel)
    return out


def compute_home_map(master_managed, target_managed):
    """Diff the master MANIFEST against the target's current managed files.
    Returns {add, change, unchanged, orphan, retire} lists of relpaths. No writes."""
    master_files = load_manifest(master_managed)["files"]
    target_root = Path(target_managed)
    add, change, unchanged = [], [], []
    for rel, meta in master_files.items():
        tp = target_root / rel
        if not tp.exists():
            add.append(rel)
        elif _md5(tp) != meta["md5"]:
            change.append(rel)
        else:
            unchanged.append(rel)
    # orphans: managed files present in the target but not in the master manifest
    present = set(_iter_files(target_managed)) if target_root.exists() else set()
    orphan = sorted(present - set(master_files))
    # retire: the PROVEN-retired subset of those orphans (previous manifest attested
    # them, the new one does not). The only bucket apply() is allowed to delete.
    return {"add": sorted(add), "change": sorted(change),
            "unchanged": sorted(unchanged), "orphan": orphan,
            "retire": compute_retire_set(master_files, target_managed)}


def verify(managed_root, manifest):
    """Recompute md5s under managed_root and compare to manifest. Returns
    {ok, mismatches:[{file,expected,actual}], missing:[file]}."""
    root = Path(managed_root)
    mismatches, missing = [], []
    for rel, meta in manifest["files"].items():
        p = root / rel
        if not p.exists():
            missing.append(rel)
            continue
        actual = _md5(p)
        if actual != meta["md5"]:
            mismatches.append({"file": rel, "expected": meta["md5"], "actual": actual})
    return {"ok": not mismatches and not missing, "mismatches": mismatches, "missing": missing}


def apply(master_managed, target_managed, manifest, report=None, clean=False,
          local_allow=None):
    """Bring the target's managed root to the master manifest: copy every manifest
    file in, then RETIRE the files the target's previous manifest listed that this
    manifest does not. Only writes under target_managed; never touches a sibling
    local/ tree. Returns the count WRITTEN (retirements land in `report`).

    clean=True switches the retire set from prior-manifest-minus-new (the default,
    conservative, never touches never-attested files) to compute_clean_retire_set()
    (EVERY orphan, so managed ends == master exactly). This is the operator's
    clean-replace model; it is opt-in because it only becomes safe once nothing
    spoke-local lives in managed/. local_allow pins survive either way.

    Retirement exists because apply() previously only ever copied, so master could
    not RETIRE a file: 4.6.6 dropped templates/claude/settings.json in master and
    basher, having pulled 4.6.6, still had it. Worse, the stranded file was then
    absent from files[] — an orphan — which verify() dropped from its verdict, so
    the half-landed pull reported clean both ways. Deletion and detection are one
    contract (fix-verify-and-apply-orphan-and-deletion-semantics-v1).

    SCOPE, and it is the whole safety argument: the delete set is the PREVIOUS
    MANIFEST's file list minus this one — never "everything not in the manifest".
    managed/ may hold legitimately spoke-local files no manifest ever attested;
    removing those would be a purge. See compute_retire_set().
    """
    master_root, target_root = Path(master_managed), Path(target_managed)
    # Resolve the retire set BEFORE anything is written: the target's own
    # MANIFEST.json is the ONLY record of what a previous distribution attested,
    # and _write_neutralized_manifest() overwrites it at the end of this function.
    if clean:
        retire_set = compute_clean_retire_set(manifest["files"], target_managed,
                                              local_allow=local_allow)
    else:
        retire_set = compute_retire_set(manifest["files"], target_managed)
    written = 0
    for rel in manifest["files"]:
        src, dst = master_root / rel, target_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        written += 1
    res = retire(target_managed, retire_set)
    if report is not None:
        report["retired"] = res["retired"]
        report["retire_errors"] = res["errors"]
    # carry the manifest, but neutralize is_master on the target: a distributed spoke
    # is not the canonical author (bug fix-manifest-is-master-neutralized-on-distribute-v1).
    _write_neutralized_manifest(master_root, target_root)
    return written


def upgrade(master_managed, target_managed, dry_run=False, expect_version=None,
            validate=True, spoke_root=None, clean=False, local_allow=None):
    """The full verify-apply-validate loop. Returns a structured report.

    Safety: the master must self-verify (every file's md5 matches its own MANIFEST)
    BEFORE anything is applied — a corrupt/half-cut master is never distributed.
    This is the floor that makes a real cutover safe to automate.

    Version gate: when expect_version is set, the master's harness_version MUST match
    or the upgrade ABORTS (writes nothing) — the version analog of the corruption gate.
    This stops a 'pull vX' from silently bringing vY (the CSRP-4.2.0 desync class:
    impl-harness-couple-version-cut-and-adoption-gate-v1).
    """
    manifest = load_manifest(master_managed)
    home_map = compute_home_map(master_managed, target_managed)
    # In clean-replace mode the effective retire set is EVERY orphan, not just the
    # prior-manifest subset. Surface it (preview + change count) so a dry-run shows
    # exactly what a clean apply would purge before anything is written.
    if clean:
        home_map["clean_retire"] = compute_clean_retire_set(
            manifest["files"], target_managed, local_allow=local_allow)
    effective_retire = home_map.get("clean_retire") if clean else home_map["retire"]
    # a pending retirement is a real pending change: if master retired a file and
    # changed nothing else, add+change is 0 while the target is genuinely NOT current.
    report = {"dry_run": dry_run, "home_map": home_map, "clean": clean,
              "changes_pending": (len(home_map["add"]) + len(home_map["change"])
                                  + len(effective_retire))}

    # version gate (beside the corruption gate; surfaced on dry-run too so a preview
    # reveals a version desync / premature adoption before anything is applied)
    actual_version = manifest.get("harness_version")
    report["master_version"] = actual_version
    if expect_version is not None and actual_version != expect_version:
        report["verify_version"] = {"ok": False, "expected": expect_version, "actual": actual_version}
        report["applied"] = 0
        report["verify_post"] = None
        report["ok"] = False
        report["aborted"] = (f"master at {actual_version}, expected {expect_version} — "
                             "refusing (version desync / premature adoption)")
        return report
    if expect_version is not None:
        report["verify_version"] = {"ok": True, "expected": expect_version, "actual": actual_version}

    # verify-master gate (skipped on dry-run since dry-run writes nothing anyway,
    # but still reported so a preview surfaces a bad master)
    master_check = verify(master_managed, manifest)
    report["verify_master"] = master_check
    if not master_check["ok"]:
        report["applied"] = 0
        report["verify_post"] = None
        report["ok"] = False
        report["aborted"] = "master failed self-verification — refusing to distribute a corrupt master"
        return report

    if dry_run:
        report["applied"] = 0
        report["verify_post"] = None
        report["ok"] = True   # a preview always "succeeds"; it asserts nothing applied
        return report

    # DOES IT STILL WORK — the question md5 cannot ask (operator model 2026-07-22:
    # validation runs at upgrade time and is validated by the spoke that took it).
    # verify_post proves the bytes landed; it cannot notice that they landed broken.
    # A cut this week rolled 28 command files back two months and verify_post would
    # have passed it, because those were exactly the bytes it meant to copy.
    #
    # THE GATE IS A REGRESSION LEDGER, NOT A HEALTH BAR. Baseline first, then compare.
    # Every spoke in this fleet carries pre-existing failures — the shipped spoke-side
    # suite is red everywhere today — so a gate that fails on absolute health would
    # block every upgrade from the first day and be routed around by the second.
    # What an upgrade is answerable for is what it BROKE: a check that passed before
    # it and fails after. Pre-existing failures are still reported, never hidden, and
    # they simply are not this upgrade's crime.
    spoke = spoke_root or _spoke_root_of(target_managed)
    baseline = run_validation(spoke) if validate else None

    report["applied"] = apply(master_managed, target_managed, manifest, report=report,
                              clean=clean, local_allow=local_allow)
    report["verify_post"] = verify(target_managed, manifest)
    report["ok"] = report["verify_post"]["ok"]

    if validate:
        after = run_validation(spoke)
        before_status = {c.get("check"): c.get("status") for c in (baseline or {}).get("checks", [])}
        regressions = [c["check"] for c in after.get("checks", [])
                       if c.get("status") == "fail" and before_status.get(c["check"]) == "pass"]
        preexisting = [c["check"] for c in after.get("checks", [])
                       if c.get("status") == "fail" and before_status.get(c["check"]) != "pass"]
        after["baseline_outcome"] = (baseline or {}).get("outcome")
        after["regressions"] = regressions
        after["preexisting_failures"] = preexisting
        after["verdict"] = ("regressed" if regressions
                            else "clean-with-preexisting" if preexisting
                            else after.get("outcome", "skip"))
        report["validation"] = after
        if regressions:
            report["ok"] = False
            report["aborted"] = ("upgrade BROKE validation on the receiving spoke: "
                                 + ", ".join(regressions))
    return report


def _spoke_root_of(managed_dir):
    """<root>/WAI-Harness/spoke/managed -> <root>. The spoke that took the upgrade."""
    return str(Path(managed_dir).resolve().parents[2])


def run_validation(spoke_root):
    """Run the validation suite, or say honestly that it could not run.

    Never raises and never reports `pass` for a suite that did not execute — the
    entire reason this exists is that something was reporting success on evidence
    that could not support it.
    """
    try:
        import harness_validate
    except Exception as exc:
        return {"outcome": "skip", "summary": f"validator unavailable: {exc}",
                "checks": [], "failed": [], "skipped": ["*"]}
    try:
        return harness_validate.validate(spoke_root)
    except Exception as exc:
        return {"outcome": "fail", "summary": f"validator raised: {type(exc).__name__}: {exc}",
                "checks": [], "failed": ["validator"], "skipped": []}


def emit_upgrade_report(spoke_root, master_root, rep, master_version=None):
    """The receiving spoke writes its own upgrade report, and posts it to master.

    THE PRODUCER HALF OF THE CIRCLE. The consumer — the upgrade-report intake
    ceremony — has been fully built and wired into wakeup for months, and has
    never once received input, because the only thing that wrote a report was a
    copy-paste JSON template inside an adoption ceremony, on v3 paths, addressed
    to a repo that is deprecated. Half a circle looks exactly like a whole one
    from the half that works.

    Two writes, deliberately:
      LOCAL   the receiving spoke keeps its own record — it took the upgrade, so
              the evidence lives where the consequences do.
      MASTER  a copy into master's lugs/incoming/, the sanctioned cross-spoke
              channel, so master learns a spoke broke WITHOUT having to ask.

    Returns {local, delivered, ok}. Never raises: a report that cannot be written
    must not turn a successful upgrade into a failed one, and must not be silent
    about failing either — the error is returned.
    """
    validation = rep.get("validation") or {}
    # The report grades what the UPGRADE did, which is why it reads `verdict` (the
    # regression comparison) rather than `outcome` (absolute health). A spoke that
    # arrived broken and left equally broken did not have a failed upgrade — and
    # saying it did would train everyone to ignore the report.
    outcome = {
        "regressed": "fail",
        "clean-with-preexisting": "partial",
        "pass": "pass",
        "fail": "fail",
        "skip": "partial",
    }.get(validation.get("verdict") or validation.get("outcome"), "partial")
    if not rep.get("ok"):
        outcome = "fail"

    spoke_id = os.path.basename(os.path.abspath(spoke_root))
    stamp = datetime.now(timezone.utc)
    lug_id = f"upgrade-report-{spoke_id}-{stamp.strftime('%Y%m%dT%H%M%S')}-v1"
    failed_checks = [c for c in validation.get("checks", []) if c.get("status") == "fail"]

    # EMPTY-PAYLOAD GUARD. An upgrade report earns its delivery when something HAPPENED —
    # files applied, an abort, a retirement, or a validation that actually ran. A report with
    # none of those says only "the emitter fired", and a channel carrying that is worse than a
    # silent one: it reads as a working circle. Identity counts too — a spoke that cannot name
    # itself has not produced a non-empty payload. Empty => log locally, deliver nothing.
    nothing_happened = (not rep.get("applied") and not rep.get("aborted")
                        and not rep.get("retired") and not validation)
    no_identity = not spoke_id or spoke_id in ("unknown", "", ".", "/")
    if nothing_happened or no_identity:
        why = "unresolvable spoke_id" if no_identity else \
            "nothing applied, no abort, no retirement, validation did not run"
        print(f"[upgrade-report] {lug_id} NOT written or delivered — empty payload ({why})",
              file=sys.stderr)
        return {"local": None, "delivered": None, "ok": True,
                "errors": [], "skipped_empty": why}

    lug = {
        "id": lug_id,
        "type": "upgrade-report",
        "status": "open",
        "routed_to": "SIGNAL" if outcome == "fail" else "LOCAL",
        "title": (f"Upgrade to {master_version or 'unknown'} on {spoke_id} — "
                  f"validation {outcome.upper()}"),
        "created_at": stamp.isoformat(),
        "created_by": "harness_upgrade.emit_upgrade_report",
        "spoke_id": spoke_id,
        "spoke_path": str(Path(spoke_root).resolve()),
        "harness_version": master_version,
        "outcome": outcome,
        "applied": rep.get("applied", 0),
        "retired": rep.get("retired", []),
        "verify_post_ok": bool((rep.get("verify_post") or {}).get("ok")),
        "aborted": rep.get("aborted"),
        "validation": validation,
        # An upgrade that ABORTED before validation and one that RAN validation and
        # failed it are different failures with different owners — the first is
        # usually a bad or mid-edit master, the second a bad cut. The first live
        # report this circle ever produced was the aborted kind and read as
        # "validation not run — no detail", which names neither.
        "summary": (
            f"{rep.get('applied', 0)} file(s) applied; "
            f"bytes {'verified' if (rep.get('verify_post') or {}).get('ok') else 'MISMATCHED'}; "
            + (f"ABORTED before validation: {rep['aborted']}" if rep.get("aborted") and not validation
               else f"validation {validation.get('verdict') or validation.get('outcome') or 'did not run'}"
                    f" — {validation.get('summary', 'no detail')}")),
        "friction_points": [
            {"step": c.get("check"), "issue": c.get("detail"),
             "suggestion": "; ".join(c.get("evidence") or []) or "see validation detail"}
            for c in failed_checks
        ],
        "impact": 9 if outcome == "fail" else 3,
        "effort": 2,
    }

    result = {"local": None, "delivered": None, "ok": True, "errors": []}
    local_dir = Path(spoke_root) / "WAI-Harness" / "spoke" / "local" / \
        "lugs" / "bytype" / "upgrade-report" / "open"
    try:
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / f"{lug_id}.json"
        local_path.write_text(json.dumps(lug, indent=2), encoding="utf-8")
        result["local"] = str(local_path)
    except OSError as exc:
        result["ok"] = False
        result["errors"].append(f"local write failed: {exc}")

    # Delivering into a sibling's incoming/ is the sanctioned cross-spoke channel.
    # Skipped when the spoke IS master — master does not post itself mail.
    try:
        # master_root arrives BOTH ways in this codebase: as a repo root and as a
        # <repo>/WAI-Harness dir (resolve_master returns the latter). Normalising is
        # not cosmetic — the first live run wrote to <repo>/WAI-Harness/WAI-Harness/...,
        # a path nothing reads, so the report was "delivered" to nobody.
        master_repo = Path(master_root)
        if master_repo.name == "WAI-Harness":
            master_repo = master_repo.parent
        master_incoming = master_repo / "WAI-Harness" / "spoke" / "local" / "lugs" / "incoming"
        if master_repo.resolve() != Path(spoke_root).resolve():
            master_incoming.mkdir(parents=True, exist_ok=True)
            delivered = master_incoming / f"{lug_id}.json"
            delivered.write_text(json.dumps(lug, indent=2), encoding="utf-8")
            result["delivered"] = str(delivered)
    except OSError as exc:
        result["ok"] = False
        result["errors"].append(f"delivery to master failed: {exc}")

    return result


def _receipts_dir(master_root):
    return Path(master_root) / "hub" / "local" / "maintenance" / "receipts"


def _master_head_sha(master_root):
    """Best-effort git HEAD SHA of the master repo, used as a receipt fallback
    when the master's own MANIFEST.json predates the master_sha field. Never raises."""
    try:
        r = subprocess.run(["git", "-C", str(master_root), "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
    except Exception:
        return None


def committed_cut_ok(master_root):
    """G5: distribute only from a committed, clean cut.

    Refuses distribution unless ALL three hold:
      1. Clean CUT: `git status --porcelain -- spoke/managed` is empty — the
         PAYLOAD being shipped is fully committed. Deliberately scoped to the
         managed tree, NOT the whole repo: the harness writes a session track on
         every turn and lugs land in incoming/ unbidden, so a repo-wide check is
         unsatisfiable during a live session and the guard would never pass. A
         guard that can never pass protects nothing — it silently means the fleet
         never receives canon.
      2. Manifest-matches-tree: manifest_build.verify(spoke/managed) is ok — the
         recorded MANIFEST md5s match the committed managed files. This is the
         REAL staleness guard: a managed file committed WITHOUT a recut would
         pass the clean-tree check yet ship bytes the manifest never attested.
      3. Provenance sha reachable: MANIFEST.master_sha is non-empty AND an
         ancestor-or-equal of HEAD (git merge-base --is-ancestor). A cut stamped
         from a divergent/abandoned commit (not on this HEAD's history) is
         refused. (Equality with HEAD is unsatisfiable for the very commit that
         writes the manifest — content-addressing self-reference — so ancestor
         reachability is the correct, satisfiable provenance invariant.)

    Fail-closed: any git failure, a missing/unreadable MANIFEST.json, an import
    failure, or any other unexpected error returns ok=False — an unverifiable
    master tree must never distribute. Never raises.

    Returns (ok, reason, sha, branch). sha/branch are best-effort (may be ""
    when unresolved) so a caller can still log identity alongside an abort.
    """
    master_root = Path(master_root)
    managed = master_root / "spoke" / "managed"
    sha, branch = "", ""
    try:
        # 1. clean CUT — scoped to spoke/managed, the payload actually being shipped.
        #
        # This was an unscoped repo-wide `git status --porcelain`, which made the
        # guard UNSATISFIABLE during any live session: the harness writes the
        # session track.jsonl on EVERY turn, and lugs arrive in incoming/ on their
        # own, so the tree goes dirty within seconds of any commit. The tool also
        # wrote its own receipts into that tree (fixed separately). A guard that
        # can never pass protects nothing — it just means the fleet never gets
        # distributed to, which is exactly what happened: 29 spokes sat on a
        # pre-4.7.0 hook for months, being told to run a /shipit that would shrink
        # their own skills, because a track file was dirty.
        #
        # The invariant this check exists to enforce is "do not ship an
        # uncommitted/unattested PAYLOAD", not "the repo has no unrelated runtime
        # churn". A dirty session track has zero bearing on the bytes in
        # spoke/managed. Check 2 below (manifest md5s vs the committed managed
        # tree) remains the real integrity guard and is unchanged, as does check 3
        # (provenance sha reachable from HEAD).
        st = subprocess.run(["git", "-C", str(master_root), "status", "--porcelain",
                             "--", str(managed)],
                            capture_output=True, text=True, timeout=10)
        if st.returncode != 0:
            return False, f"git status failed: {st.stderr.strip()[:200]}", sha, branch
        if st.stdout.strip():
            first_lines = "; ".join(st.stdout.strip().splitlines()[:3])
            return False, (f"managed cut dirty (uncommitted payload — commit or recut "
                           f"before distributing): {first_lines}"), sha, branch

        hr = subprocess.run(["git", "-C", str(master_root), "rev-parse", "HEAD"],
                            capture_output=True, text=True, timeout=10)
        if hr.returncode != 0 or not hr.stdout.strip():
            return False, f"git rev-parse HEAD failed: {hr.stderr.strip()[:200]}", sha, branch
        sha = hr.stdout.strip()

        br = subprocess.run(["git", "-C", str(master_root), "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True, timeout=10)
        branch = br.stdout.strip() if br.returncode == 0 else ""

        manifest_path = managed / MANIFEST_NAME
        if not manifest_path.exists():
            return False, f"master MANIFEST.json not found at {manifest_path}", sha, branch

        # 2. manifest matches the committed managed tree (the real staleness guard)
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import manifest_build as _mb
        except Exception as e:  # fail-closed: an unimportable gate refuses the cut
            return False, f"manifest_build unavailable ({e}) — refusing (fail-closed)", sha, branch
        vres = _mb.verify(str(managed))
        if not vres.get("ok"):
            detail = f"mismatches={vres.get('mismatches')} missing={vres.get('missing')}"
            return False, ("MANIFEST does not match the committed managed tree "
                           f"(recut+commit before distributing): {detail}"), sha, branch

        # 3. provenance sha is reachable from HEAD (ancestor-or-equal)
        try:
            manifest_sha = json.loads(manifest_path.read_text()).get("master_sha")
        except (OSError, json.JSONDecodeError) as e:
            return False, f"master MANIFEST.json unreadable: {e}", sha, branch
        if not manifest_sha:
            return False, "MANIFEST.master_sha is empty (no cut provenance recorded)", sha, branch
        anc = subprocess.run(["git", "-C", str(master_root), "merge-base",
                             "--is-ancestor", str(manifest_sha), sha],
                            capture_output=True, text=True, timeout=10)
        if anc.returncode != 0:
            return False, (f"MANIFEST.master_sha {manifest_sha} is not an ancestor of "
                           f"HEAD {sha} (cut from a divergent/abandoned commit)"), sha, branch

        return True, "clean committed cut", sha, branch
    except Exception as e:  # noqa: BLE001 — fail-closed: unverifiable tree never distributes
        return False, f"committed_cut_ok error: {e}", sha, branch


CANON_REF = "origin/main"
CANON_OVERRIDE_ENV = "WAI_ALLOW_NONCANON_DISTRIBUTION"


def canon_cut_ok(master_root, canon_ref=CANON_REF):
    """Refuse to distribute from a master tree that is BEHIND its own canon.

    committed_cut_ok() proves the payload is committed, recut and cut from a commit
    reachable from HEAD. All three can hold on a feature branch, which is how the
    fleet came to be served content older than canon under a version number NEWER
    than canon (basher, 2026-07-30):

        master worktree on session-20260719-work-split, VERSION 4.14.31, no pull-gate
        canon        on main,                          VERSION 4.14.30, gate present

    The pull is upgrade-when-newer, so every spoke was stamped 4.14.31 with content
    predating 4.14.30 and could never afterwards reach the fix. It reported ok:true.
    The missing invariant is not about the payload at all -- it is that the tree
    being published must CONTAIN canon.

    A distribution that ships the wrong bytes silently is worse than one that
    refuses, so this fails CLOSED when canon resolves and HEAD does not contain it.
    It fails OPEN only when canon cannot be resolved at all -- a clone with no
    remote, or an offline machine -- because there a refusal would brick a spoke
    that has no way to satisfy the check. Set WAI_ALLOW_NONCANON_DISTRIBUTION=1 to
    publish deliberately from a non-canon tree (a pre-release cut being dogfooded);
    the reason is returned either way so callers can log which case they took.

    Returns (ok, reason).
    """
    master_root = Path(master_root)
    try:
        # Distinguish "not version-controlled at all" from "behind canon" explicitly,
        # rather than letting both fall out of the same failed rev-parse. A master
        # distributed as an extracted tarball has no git history to be behind, and is
        # the same case as an offline clone: nothing to compare, so nothing to enforce.
        inside = subprocess.run(["git", "-C", str(master_root), "rev-parse",
                                 "--is-inside-work-tree"],
                                capture_output=True, text=True, timeout=10)
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return True, "master is not a git work tree (tarball or unpacked cut); not enforced"
        canon = subprocess.run(["git", "-C", str(master_root), "rev-parse", "--verify",
                                "-q", canon_ref],
                               capture_output=True, text=True, timeout=10)
        if canon.returncode != 0 or not canon.stdout.strip():
            # No canon to compare against -- fail OPEN, see docstring.
            return True, f"canon ref {canon_ref} unresolvable (offline or no remote); not enforced"
        canon_sha = canon.stdout.strip()
        contains = subprocess.run(["git", "-C", str(master_root), "merge-base",
                                   "--is-ancestor", canon_sha, "HEAD"],
                                  capture_output=True, text=True, timeout=10)
        if contains.returncode == 0:
            return True, f"tree contains {canon_ref}"

        behind = subprocess.run(["git", "-C", str(master_root), "rev-list", "--count",
                                 f"HEAD..{canon_sha}"], capture_output=True, text=True, timeout=10)
        n = (behind.stdout or "").strip() or "?"
        head_branch = subprocess.run(["git", "-C", str(master_root), "rev-parse",
                                      "--abbrev-ref", "HEAD"],
                                     capture_output=True, text=True, timeout=10)
        br = (head_branch.stdout or "").strip() or "?"
        reason = (f"master tree is on '{br}', which does NOT contain {canon_ref} "
                  f"({n} canon commit(s) missing) -- distributing would serve pre-canon "
                  f"content, and an upgrade-when-newer pull would then pin every spoke "
                  f"above canon so it could never receive the real cut")
        if os.environ.get(CANON_OVERRIDE_ENV) == "1":
            return True, f"OVERRIDDEN via {CANON_OVERRIDE_ENV}=1: {reason}"
        return False, reason
    except Exception as e:  # noqa: BLE001 — same fail-closed posture as committed_cut_ok
        return False, f"canon_cut_ok error: {e}"


def _load_registry_path_map(master_root):
    """Best-effort realpath(entry.path) -> wheel_id map from hub-registry.json.
    Missing/unreadable registry -> empty map (never raises)."""
    reg_path = Path(master_root) / "hub" / "local" / "hub-registry.json"
    try:
        data = json.loads(reg_path.read_text())
    except Exception:
        return {}
    out = {}
    for entry in data.get("wheels", []) or []:
        try:
            p = entry.get("path")
            wid = entry.get("wheel_id")
            if p and wid:
                out[os.path.realpath(p)] = wid
        except Exception:
            continue
    return out


def _resolve_receipt_identity(spoke_root, master_root):
    """Resolve the TRUE identity behind spoke_root for receipt-keying purposes
    (bug fix-receipt-identity-wheel-id-v1). The prior implementation used the
    raw directory basename as identity, so a pull from a git worktree checkout
    (path .../mywheel/.worktrees/<session>) wrote receipts keyed by the session
    dir name, and any non-registry dir name could leak into latest.json — the
    index certify() consumes as if it were a canonical spoke.

    Returns (identity, index_ok) where index_ok is False for worktree pulls
    (transient dev checkouts get an individual receipt file for provenance,
    but must NOT be written into latest.json / masquerade as a spoke)."""
    rp = os.path.realpath(spoke_root)
    registry_map = _load_registry_path_map(master_root)
    if rp in registry_map:
        return registry_map[rp], True
    if ".worktrees" in Path(rp).parts:
        # Transient worktree pull — segregate: receipt file only, no index entry.
        return f"_worktree:{Path(rp).name}", False
    # Unmatched, non-worktree path — quarantine: visible but never masquerading
    # as a real spoke (still indexed, but under an unmistakably non-canonical key).
    return f"_unmatched:{Path(rp).name}", True


def _write_receipt(spoke_root, master_root, status, ok, master_version, master_sha,
                    files_checked, mismatches, branch=None, sha=None):
    """Persist a verify receipt so EVERY pull sweep — including a same-version
    'current' no-op — is provable, not merely reported (F7: 34/34 verify_post
    discarded on the current-spoke early-return). One file per spoke per sweep
    under hub/local/maintenance/receipts/, plus a latest-index keyed by spoke
    name that certify() consumes to reference the receipt backing a
    certification (P-COVER: the receipt has a downstream consumer by
    construction). Best-effort: a receipt write failure must never break a
    good pull.

    branch/sha (optional): the distributing master's git branch + HEAD sha at
    the moment of a verified committed-cut distribution (G5). When provided by
    the caller (e.g. harness_distribute_fleet after committed_cut_ok()), they
    are recorded as distributed_from_branch/distributed_from_sha so a receipt
    is provable cut-provenance, not just file/version identity."""
    from datetime import datetime, timezone as _tz
    ts = datetime.now(_tz.utc).isoformat()
    identity, index_ok = _resolve_receipt_identity(spoke_root, master_root)
    receipt_id = f"{identity}-{ts.replace(':', '').replace('+00:00', 'Z')}"
    receipt = {
        "receipt_id": receipt_id,
        "spoke": identity,
        "spoke_path": str(Path(spoke_root).resolve()),
        "ts": ts,
        "status": status,
        "ok": ok,
        "master_version": master_version,
        "master_sha": master_sha,
        "files_checked": files_checked,
        "mismatches": mismatches,
    }
    if branch is not None:
        receipt["distributed_from_branch"] = branch
    if sha is not None:
        receipt["distributed_from_sha"] = sha
    try:
        rdir = _receipts_dir(master_root)
        rdir.mkdir(parents=True, exist_ok=True)
        (rdir / f"{receipt_id}.json").write_text(json.dumps(receipt, indent=2) + "\n")
        if index_ok:
            idx_path = rdir / "latest.json"
            try:
                idx = json.loads(idx_path.read_text()) if idx_path.exists() else {}
            except Exception:
                idx = {}
            idx[identity] = receipt
            idx_path.write_text(json.dumps(idx, indent=2) + "\n")
    except Exception:  # noqa: BLE001 — receipt persistence must never break a good pull
        pass
    return receipt


def pull(spoke_root, master_root=None, side="spoke", dry_run=False, expect_version=None,
         branch=None, sha=None, validate=True):
    """Pull-on-spin-up entry point — the session-start self-update.

    branch/sha (optional, G5): the distributing master's git branch + HEAD sha,
    when the caller has already verified committed_cut_ok() (e.g. a fleet
    distribution pass). Threaded straight through to _write_receipt() as
    distributed_from_branch/distributed_from_sha; ignored (None) for the
    ordinary per-spoke pull-on-spin-up caller, which never resolves a cut.

    Cheap by design: computes the home-map first and returns a no-op when the
    spoke is already current (the overwhelming common case), so it is safe to
    call on every session start. Only when files are add/changed does it run the
    full verify-apply-verify upgrade. NEVER touches local/ (managed-only).
    Presence-guarded: a no-op (never an error) when this spoke has no WAI-Harness
    or the master is unreachable — so a clone-and-run / offline spoke just keeps
    running its own copy.

    status: no-harness | no-master | current | behind(dry_run) | upgraded | failed
    """
    if master_root is None:
        master_root = resolve_master(spoke_root)
    wh = Path(spoke_root) / "WAI-Harness"
    if not wh.is_dir():
        return {"pulled": 0, "status": "no-harness", "current": None}
    master_managed = _resolve_managed(master_root, side)
    if not (Path(master_managed) / MANIFEST_NAME).exists():
        return {"pulled": 0, "status": "no-master", "current": None}
    # Canon gate BEFORE anything else: the master publishes its WORKING TREE, so a
    # master sitting on a feature branch serves that branch to the whole fleet. That
    # is not hypothetical -- it shipped pre-canon content under a higher version
    # number and pinned every spoke above canon (see canon_cut_ok). The ordinary
    # per-spoke pull is precisely the path that never resolved a cut and so never
    # ran committed_cut_ok(), which is why nothing caught it. Refuse loudly here:
    # a wrong-bytes success is worse than a visible abort.
    canon_ok, canon_reason = canon_cut_ok(master_root)
    if not canon_ok:
        return {"pulled": 0, "status": "noncanon-master", "current": False, "ok": False,
                "canon_reason": canon_reason,
                "aborted": (f"refusing to pull from a non-canon master: {canon_reason} "
                            f"(set {CANON_OVERRIDE_ENV}=1 to publish deliberately)")}
    # Version gate FIRST: a spoke told to pull vX against a vY master must abort loudly,
    # not silently bring vY — independent of whether it is current/behind/dry-run.
    if expect_version is not None:
        actual_version = load_manifest(master_managed).get("harness_version")
        if actual_version != expect_version:
            return {"pulled": 0, "status": "version-desync", "current": False, "ok": False,
                    "master_version": actual_version, "expected": expect_version,
                    "aborted": (f"master at {actual_version}, expected {expect_version} — "
                                "refusing (version desync / premature adoption)")}
    target_managed = _resolve_managed(wh, side)
    hm = compute_home_map(master_managed, target_managed)
    # A pending RETIREMENT counts as pending work. Without it, a cut whose only change
    # is a retired file leaves add+change at 0, so this returns the cheap "current"
    # no-op and the retirement never lands on the spoke — the file survives forever,
    # invisible (it is absent from the master manifest, so nothing else looks at it).
    pending = len(hm["add"]) + len(hm["change"]) + len(hm["retire"])
    master_manifest = load_manifest(master_managed)
    master_version = master_manifest.get("harness_version")
    master_sha = master_manifest.get("master_sha") or _master_head_sha(master_root)
    if pending == 0:
        # Managed is current — but the ACTIVE slash-command dir and ACTIVE hooks can
        # still have drifted (P0 of initiative-optimize-ceremonies-v1: operators ran
        # stale ceremonies; F8 of plan-wheel-integrity-v1: session-start.sh drifted on
        # master while every other spoke's active hook stayed frozen at init-time).
        # Re-deploy is cheap + idempotent (copies only on diff).
        # F7: a "current" no-op is a REAL verify (home_map found zero add/change) —
        # persist the same receipt a real apply would, so this branch is provable too.
        _write_receipt(spoke_root, master_root, status="current", ok=True,
                       master_version=master_version, master_sha=master_sha,
                       files_checked=len(master_manifest.get("files", {})), mismatches=0,
                       branch=branch, sha=sha)
        return {"pulled": 0, "status": "current", "current": True,
                "commands_deployed": _deploy_active_commands(spoke_root),
                "hooks_deployed": _deploy_active_hooks(spoke_root),
                "settings_deployed": _deploy_active_settings(spoke_root),
                "trees_deployed": _deploy_active_trees(spoke_root),
                # Stamp on the current branch too: managed can match while VERSION /
                # wheel.harness_version still advertise an older cut. Idempotent (no-ops
                # when already correct), so this is what SELF-HEALS a spoke that pulled
                # before the stamp existed -- without it, "current" spokes stay lying.
                "version_stamped": _stamp_harness_version(spoke_root, master_version),
                # Same self-heal argument, applied to LOCAL DATA. Gating migrations on
                # files-changed means a spoke that pulled the code before a migration
                # existed -- or whose migration failed once -- would never correct
                # itself, because it is "current" forever after. Migrators are
                # idempotent and no-op fast when nothing is out of shape, so an upgrade
                # becomes a standing migration + health + correction pass rather than a
                # one-shot that only fires on the cut that introduced it.
                "local_migrations": _post_upgrade_local_migrations(spoke_root, master_managed),
                "master_version": master_version}
    if dry_run:
        return {"pulled": 0, "status": "behind", "pending": pending,
                "current": False, "dry_run": True, "home_map": hm,
                "master_version": master_version}
    rep = upgrade(master_managed, target_managed, dry_run=False, expect_version=expect_version,
                  validate=validate, spoke_root=spoke_root)
    # The spoke that TOOK the upgrade writes the report — automatically, on v4 paths,
    # to master. Not from a paragraph of copy-paste instructions in a ceremony, and
    # not to the deprecated framework repo. Exactly one producer, and this is it.
    report_out = None
    if validate:
        try:
            report_out = emit_upgrade_report(spoke_root, master_root, rep, master_version)
        except Exception as exc:  # a report is evidence, never a gate on the upgrade
            report_out = {"ok": False, "errors": [f"emit raised: {exc}"]}
    out = {"pulled": rep.get("applied", 0),
           "status": "upgraded" if rep.get("ok") else "failed",
           "current": bool(rep.get("ok")), "ok": rep.get("ok"),
           "validation": rep.get("validation"), "upgrade_report": report_out,
           "verify_post": rep.get("verify_post"), "aborted": rep.get("aborted"),
           # what master retired on this pull (and any unlink that failed) — surfaced
           # so a retirement is reported, never a silent disappearance
           "retired": rep.get("retired", []), "retire_errors": rep.get("retire_errors", [])}
    # Overwrite audit (change-autopilot-headless-dispatch-reverts-managed-edits-every-
    # lug-v1): every pull that reaches the apply path leaves a durable JSONL record of
    # WHAT it replaced, so an intended overwrite and an accidental clobber are
    # distinguishable after the fact — the absence of any such record is why the
    # silent-revert defect went undiagnosed. The file lists come straight from the
    # home-map computed above (add/change = files written, retire = files deleted).
    # Best-effort: an audit line must never fail (or gate) the pull itself.
    try:
        _log_dir = Path(spoke_root) / "WAI-Harness" / "spoke" / "local" / "runtime"
        _log_dir.mkdir(parents=True, exist_ok=True)
        _audit = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "trigger": os.path.basename(sys.argv[0] or "") or "harness_upgrade",
            "status": out["status"],
            "master_version": master_version,
            "applied": out["pulled"],
            "files": {"add": hm["add"], "change": hm["change"], "retire": hm["retire"]},
        }
        with open(_log_dir / "managed-overwrites.jsonl", "a", encoding="utf-8") as _fh:
            _fh.write(json.dumps(_audit) + "\n")
    except Exception:
        pass
    # F7: persist the applied/failed branch's real verify_post receipt too (previously
    # discarded — verify_post was returned in the report but never landed anywhere
    # durable, so a 34/34-spoke sweep left zero provable evidence).
    vp = rep.get("verify_post") or {}
    _write_receipt(spoke_root, master_root, status=out["status"], ok=bool(out["ok"]),
                   master_version=rep.get("master_version", master_version), master_sha=master_sha,
                   files_checked=len(master_manifest.get("files", {})),
                   mismatches=len(vp.get("mismatches", [])) + len(vp.get("missing", [])),
                   branch=branch, sha=sha)
    # Deploy + migrate atomically: once a managed upgrade lands, run the one-shot,
    # idempotent LOCAL data migrations the new managed code expects (e.g. relocating
    # legacy savepoints to the initiative-scoped home). Best-effort: a migration
    # failure is reported but never turns a good file-sync into a failed pull.
    if out["ok"] and out["pulled"]:
        out["local_migrations"] = _post_upgrade_local_migrations(spoke_root, master_managed)
    # Refresh the active slash-command dir + active hooks from the freshly-pulled
    # canonical so the operator never invokes a stale ceremony and the spoke's LIVE
    # hooks never lag a canon hook fix (idempotent; best-effort; F8/W4.2).
    out["commands_deployed"] = _deploy_active_commands(spoke_root)
    out["hooks_deployed"] = _deploy_active_hooks(spoke_root)
    out["settings_deployed"] = _deploy_active_settings(spoke_root)
    # agents/ + skills/ + workflows/ — distributed since forever, never deployed
    # live until now (see _deploy_active_tree).
    out["trees_deployed"] = _deploy_active_trees(spoke_root)
    # Record the master's HEAD SHA + version so harness_converge contribute knows
    # the baseline (P7: cross-spoke convergence base tracking).
    if out["ok"] and out["pulled"]:
        _record_harness_base(spoke_root, master_root, out.get("master_version")
                             or master_version)
        # Make the spoke ADVERTISE what it just pulled. Gated on ok+pulled for the same
        # reason as the base record: a failed/aborted sync must never bump the stamp.
        out["version_stamped"] = _stamp_harness_version(
            spoke_root, out.get("master_version") or master_version)
    return out


def _stamp_harness_version(spoke_root, master_version):
    """Stamp the pulled harness version into WAI-Harness/VERSION.

    Why this exists: pull() syncs spoke/managed/** (so MANIFEST.json arrives carrying the
    master's harness_version) but VERSION lives ABOVE managed/ at the WAI-Harness root, so
    it was never in the sync's file scope. A spoke could therefore complete a green 4.6.5
    pull while VERSION still read 4.4.3 (basher, 2026-07-14: MANIFEST=4.6.5, VERSION=4.4.3).

    The teeth: manifest_build.read_version() treats VERSION as "the single source of truth"
    and walks up to it. So a stale VERSION is not cosmetic -- the next local manifest recut
    reads 4.4.3 and stamps the spoke's identity BACK DOWN, silently undoing the upgrade.
    VERSION is harness-root, master-owned data; keeping it truthful is squarely the
    distribution mechanism's job.

    SCOPE, deliberately: this does NOT touch spoke/local/WAI-State.json's
    wheel.harness_version, even though that field is stale on pulled spokes too
    (basher read 1.1). spoke/local/** is the SPOKE's sovereign tree and pull is the
    MASTER's mechanism -- test_harness_pull.py::test_local_tree_never_touched pins that
    boundary deliberately. Who stamps WAI-State is an ownership decision, not a bug fix:
    see bug-pull-leaves-wai-state-harness-version-stale-v1.

    Reports what it did rather than failing the pull (a good file-sync must not be undone by
    a version write), but never fails SILENTLY: errors surface in the pull report."""
    rep = {"version_file": None, "ok": True}
    try:
        vf = Path(spoke_root) / "WAI-Harness" / VERSION_FILE
        prior = vf.read_text().strip() if vf.exists() else None
        if prior != master_version:
            vf.write_text(str(master_version) + "\n")
            rep["version_file"] = {"from": prior, "to": master_version}
        else:
            rep["version_file"] = {"unchanged": prior}
    except Exception as e:  # noqa: BLE001 — reported, never fatal
        rep["ok"] = False
        rep["version_file"] = {"error": str(e)[:120]}
    return rep


def _record_harness_base(spoke_root, master_root, master_version):
    """Record the master HEAD SHA + version into local runtime after a successful pull.
    Enables harness_converge.py contribute to compute the correct diff base (P7)."""
    try:
        import subprocess as _sp
        r = _sp.run(["git", "-C", str(master_root), "rev-parse", "HEAD"],
                    capture_output=True, text=True, timeout=10)
        sha = r.stdout.strip() if r.returncode == 0 else None
        from datetime import datetime, timezone as _tz
        data = {
            "master_sha": sha,
            "master_version": master_version,
            "master_root": str(master_root),
            "recorded_at": datetime.now(_tz.utc).isoformat(),
        }
        base_path = Path(spoke_root) / "WAI-Harness" / "spoke" / "local" / "runtime" / "harness-base.json"
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.write_text(json.dumps(data, indent=2) + "\n")
    except Exception:  # best-effort; never fails a pull
        pass


def _deploy_active_commands(spoke_root):
    """Best-effort: sync <spoke_root>/.claude/commands from the managed canonical via
    deploy_commands.py. Never raises — a deploy failure must not break a good pull."""
    try:
        import importlib
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        deploy_commands = importlib.import_module("deploy_commands")
        rep = deploy_commands.deploy(str(spoke_root), dry_run=False)
        return {"synced": len(rep.get("copied", [])), "pruned": len(rep.get("pruned", [])),
                "ok": rep.get("ok", False)}
    except Exception as e:  # noqa: BLE001 — best-effort, never fatal
        return {"ok": False, "error": str(e)[:120]}


def _deploy_active_hooks(spoke_root):
    """Best-effort: sync <spoke_root>/.claude/hooks from the ONE canonical hook
    source, <spoke_root>/WAI-Harness/spoke/managed/.claude/hooks. Mirrors
    _deploy_active_commands: overwrites a stale active hook (md5 diff), preserves
    any active-only local hook not present in managed, never creates from nothing
    if managed is absent. Never raises — a deploy failure must not break a good
    pull. This is the fix for F8 (plan-wheel-integrity-v1): active hooks were
    deployed ONCE at init and never again, so a canon hook fix (like
    bug-9c793efcb604's track fix) reached every spoke's managed/ dir but never
    its LIVE hooks."""
    try:
        managed_hooks = Path(spoke_root) / "WAI-Harness" / "spoke" / "managed" / ".claude" / "hooks"
        active_hooks = Path(spoke_root) / ".claude" / "hooks"
        if not managed_hooks.is_dir():
            return {"ok": False, "error": f"managed hooks dir not found: {managed_hooks}"}
        active_hooks.mkdir(parents=True, exist_ok=True)
        copied, current = [], []
        managed_names = set()
        for src in sorted(p for p in managed_hooks.iterdir()
                          if p.is_file() and not p.name.startswith(".")):
            managed_names.add(src.name)
            dst = active_hooks / src.name
            if dst.exists() and _md5(dst) == _md5(src):
                current.append(src.name)
                continue
            shutil.copy2(src, dst)
            if src.suffix == ".sh":
                dst.chmod(0o755)
            copied.append(src.name)
        preserved_local = sorted(
            p.name for p in active_hooks.glob("*")
            if p.is_file() and p.name not in managed_names and not p.name.startswith(".")
        )
        return {"ok": True, "synced": len(copied), "copied": copied,
                "already_current": len(current), "preserved_local": preserved_local}
    except Exception as e:  # noqa: BLE001 — best-effort, never fatal
        return {"ok": False, "error": str(e)[:120]}


def _deploy_active_tree(spoke_root, subdir):
    """Best-effort RECURSIVE sync of <spoke_root>/.claude/<subdir> from the managed
    canonical, for the subtrees that had no deploy path at all.

    _deploy_active_hooks/_deploy_active_commands covered hooks/ and commands/, and
    _deploy_active_settings covered settings.json. Nothing covered agents/, skills/
    or workflows/ — so those shipped into every spoke's managed/ tree on every cut
    and were never deployed to the LIVE .claude/ dir. A spoke ran whatever it had
    at init, forever. Measured on basher at 4.14.12 (2026-07-26): hooks 20/20 and
    commands 109/110 in sync, but agents 0/8, skills 0/24, workflows 0/2 — basher
    was missing its own ozi-nightly.md agent and both fable-review workflows.

    Recursive because these are not flat: skills live at skills/<name>/SKILL.md
    (and skills/generated/<name>/SKILL.md), unlike hooks/ which is one level.

    Same contract as _deploy_active_hooks: overwrite a stale live file (md5 diff),
    PRESERVE any live-only file managed does not know about, never create from
    nothing when managed is absent, never raise.
    """
    try:
        managed_dir = Path(spoke_root) / "WAI-Harness" / "spoke" / "managed" / ".claude" / subdir
        active_dir = Path(spoke_root) / ".claude" / subdir
        if not managed_dir.is_dir():
            return {"ok": True, "skipped": f"no managed .claude/{subdir}"}
        active_dir.mkdir(parents=True, exist_ok=True)
        copied, current, managed_rel = [], [], set()
        for src in sorted(p for p in managed_dir.rglob("*") if p.is_file()):
            rel = src.relative_to(managed_dir)
            if any(part.startswith(".") for part in rel.parts):
                continue
            managed_rel.add(str(rel))
            dst = active_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() and _md5(dst) == _md5(src):
                current.append(str(rel))
                continue
            shutil.copy2(src, dst)
            if src.suffix in (".sh", ".js"):
                try:
                    dst.chmod(0o755)
                except OSError:
                    pass
            copied.append(str(rel))
        preserved_local = sorted(
            str(p.relative_to(active_dir)) for p in active_dir.rglob("*")
            if p.is_file() and str(p.relative_to(active_dir)) not in managed_rel
            and not any(part.startswith(".") for part in p.relative_to(active_dir).parts)
        )
        return {"ok": True, "synced": len(copied), "copied": copied[:20],
                "already_current": len(current), "preserved_local": preserved_local[:20]}
    except Exception as e:  # noqa: BLE001 — best-effort, never fatal
        return {"ok": False, "error": str(e)[:120]}


# The .claude subtrees that were distributed but never deployed live.
_ACTIVE_TREES = ("agents", "skills", "workflows")


def _deploy_active_trees(spoke_root):
    return {sub: _deploy_active_tree(spoke_root, sub) for sub in _ACTIVE_TREES}


_SETTINGS_LIST_MERGE_KEYS = {
    ("permissions", "allow"), ("permissions", "deny"), ("permissions", "ask"),
}


def _is_hook_event_list(path, managed_val, local_val):
    """True for hooks.<Event> (e.g. ('hooks','PreToolUse')) — a list of
    {matcher, hooks:[...]} registration blocks."""
    return (len(path) == 2 and path[0] == "hooks"
            and isinstance(managed_val, list) and isinstance(local_val, list))


def _merge_hook_event_list(managed_val, local_val):
    """UNION hook registrations BY MATCHER — managed first, then local-only matchers.

    Why by matcher and not by position: these lists were previously replaced
    wholesale, so a spoke's local hook was silently destroyed and, worse, CONFLATED
    with whatever master happened to put at the same index. Observed on basher
    2026-07-14: its PreToolUse[1] was {matcher: AskUserQuestion -> askquestion.sh};
    master's PreToolUse[1] was {matcher: Write|Edit|... -> pre-write-guard.sh}. The
    pull replaced slot [1] and the spoke lost its AskUserQuestion registration
    entirely — a green pull that quietly broke a working feature.

    Matcher is the registration's identity (it is what Claude Code dispatches on), so
    same-matcher = same registration and managed wins it; a matcher only local knows
    is a local-only registration and is preserved. This is what
    _deploy_active_settings' docstring has always PROMISED ("local-only hook
    registrations" preserved) and what it never actually did.
    """
    merged = list(managed_val)
    managed_matchers = {e.get("matcher") for e in managed_val if isinstance(e, dict)}
    for e in local_val:
        if not isinstance(e, dict):
            continue
        if e.get("matcher") not in managed_matchers:
            merged.append(e)   # local-only registration: preserve
    return merged


def _merge_settings_value(path, managed_val, local_val):
    """Additive-merge one (managed, local) pair at `path` (tuple of keys so far).

    Rule: managed is authoritative for keys it defines; any key present ONLY in
    local is preserved untouched. dict fields (e.g. `hooks`, `permissions`) merge
    key-by-key with this same rule, recursively. List-valued permission fields
    (permissions.allow/deny/ask) UNION rather than replace: managed entries first
    (in managed order), then any local-only extras appended (local order),
    deduplicated — so a locally-added deny/ask rule can never be silently dropped
    by a managed sync. hooks.<Event> lists UNION BY MATCHER for the same reason
    (see _merge_hook_event_list). All other lists are managed-authoritative
    (replaced), same as every non-permissions managed key.
    """
    if path in _SETTINGS_LIST_MERGE_KEYS and isinstance(managed_val, list) and isinstance(local_val, list):
        merged = list(managed_val)
        seen = set(json.dumps(v, sort_keys=True) for v in merged)
        for v in local_val:
            k = json.dumps(v, sort_keys=True)
            if k not in seen:
                merged.append(v)
                seen.add(k)
        return merged
    if _is_hook_event_list(path, managed_val, local_val):
        return _merge_hook_event_list(managed_val, local_val)
    if isinstance(managed_val, dict) and isinstance(local_val, dict):
        return _merge_settings_dict(managed_val, local_val, path)
    # Scalars, mismatched types, or other lists: managed wins.
    return managed_val


def _merge_settings_dict(managed, local, path=()):
    """Additive-merge two dicts: managed-authoritative per-key, local-only keys kept."""
    out = dict(local)  # start from local so local-only keys survive untouched
    for k, mv in managed.items():
        if k in local:
            out[k] = _merge_settings_value(path + (k,), mv, local[k])
        else:
            out[k] = mv
    return out


def _deploy_active_settings(spoke_root):
    """Best-effort: additive-merge <spoke_root>/.claude/settings.json from the
    managed canonical, <spoke_root>/WAI-Harness/spoke/managed/.claude/settings.json.

    Mirrors _deploy_active_hooks / _deploy_active_commands (managed -> live,
    presence-guarded, never raises), but unlike those file-copy deploys this one
    is a structural JSON merge (see session-start.sh's basher self-heal for the
    prior art on ADDITIVE, never-replace settings merges): managed values are
    authoritative for the keys managed defines, but any key/entry present ONLY in
    the live settings (local-only) is preserved — including local-only top-level
    keys, local-only permission rules (allow/deny/ask lists are UNIONed, managed
    entries first), and local-only hook registrations. A settings deploy failure
    must never break a good pull.
    """
    try:
        managed_settings = (Path(spoke_root) / "WAI-Harness" / "spoke" / "managed" /
                            ".claude" / "settings.json")
        active_settings = Path(spoke_root) / ".claude" / "settings.json"
        if not managed_settings.is_file():
            return {"ok": True, "merged": False, "created": False,
                    "skipped": "no managed settings.json"}
        managed_data = json.loads(managed_settings.read_text())
        active_settings.parent.mkdir(parents=True, exist_ok=True)
        if not active_settings.is_file():
            active_settings.write_text(json.dumps(managed_data, indent=2) + "\n")
            return {"ok": True, "merged": False, "created": True}
        local_data = json.loads(active_settings.read_text())
        merged = _merge_settings_dict(managed_data, local_data)
        if merged != local_data:
            active_settings.write_text(json.dumps(merged, indent=2) + "\n")
        return {"ok": True, "merged": True, "created": False}
    except Exception as e:  # noqa: BLE001 — best-effort, never fatal
        return {"ok": False, "merged": False, "created": False, "error": str(e)[:120]}


# LOCAL MIGRATORS — the upgrade's self-running migration, health and correction pass.
#
# Each entry is a tool in spoke/managed/tools/ honouring the shared contract:
#   <tool> --root <spoke> --json            -> {"ok": bool, "errors": [...], ...}
#   <tool> --root <spoke> --verify --json   -> {"clean": bool, ...}
# and it MUST be idempotent — a no-op when nothing is out of shape.
#
# `summary_fields` are the counters lifted into the pull report so an operator can
# see what an upgrade actually corrected without reading a subprocess log.
_LOCAL_MIGRATORS = (
    ("savepoint_migrate.py", ("relocated", "initiatives_created")),
    # Stamps missing lug dispositions and refreshes the derived ready-queue cache,
    # so the operator/Ozi work split is answerable on every spoke straight after an
    # upgrade rather than only where someone happened to run the expediter.
    ("disposition_migrate.py", ("stamped", "cache_refreshed")),
)


def _post_upgrade_local_migrations(spoke_root, master_managed):
    """Run idempotent LOCAL data migrations after a managed upgrade lands.

    Keeps the file-sync (apply()) strictly managed-only; this is the deliberate,
    gated step that brings a spoke's LOCAL data into the shape the freshly-applied
    managed code expects. Each migrator is idempotent (a no-op when nothing legacy
    remains) and isolated (one failure never blocks the others or the pull).

    Registry-driven rather than one block per migrator: an upgrade is a migration,
    health-check and correction pass, and adding a correction should mean adding a
    row to _LOCAL_MIGRATORS, not copying twenty lines of subprocess plumbing.
    """
    results = {}
    for tool_name, summary_fields in _LOCAL_MIGRATORS:
        tool = Path(master_managed) / "tools" / tool_name
        if not tool.exists():
            continue
        key = tool_name[:-3] if tool_name.endswith(".py") else tool_name
        try:
            run = subprocess.run([sys.executable, str(tool),
                                  "--root", str(spoke_root), "--json"],
                                 capture_output=True, text=True, timeout=300)
            rep = json.loads(run.stdout) if run.stdout.strip() else {
                "ok": False, "errors": ["no output"]}
            ver = subprocess.run([sys.executable, str(tool),
                                  "--root", str(spoke_root), "--verify", "--json"],
                                 capture_output=True, text=True, timeout=120)
            post = json.loads(ver.stdout) if ver.stdout.strip() else None

            summary = {field: rep.get(field) for field in summary_fields}
            summary["clean"] = (post or {}).get("clean")
            summary["ok"] = rep.get("ok")
            # Surface the reason, not just the verdict — a migration that failed
            # silently during a fleet fan-out is indistinguishable from one that
            # had nothing to do.
            if rep.get("errors"):
                summary["errors"] = rep["errors"][:3]
            results[key] = summary
        except Exception as e:  # noqa: BLE001 — best-effort, must not break pull
            results[key] = {"ok": False, "error": str(e)}

    # WAI-State.wheel.harness_version, stamped HERE and not in apply().
    #
    # A spoke that advertises the wrong version pulls the wrong migrations, so this
    # is not cosmetic -- nurturator sat at VERSION 4.13.1 / WAI-State 1.1 after a
    # green upgrade. _stamp_harness_version deliberately leaves it alone because
    # pull() syncs managed-only and test_local_tree_never_touched pins that boundary.
    #
    # This function is the local-data step: it exists precisely to bring spoke/local
    # into the shape the freshly-applied managed code expects, and already writes
    # there via the migrators above. Stamping from here respects the boundary the
    # test protects instead of widening apply()'s reach.
    results["state_version"] = _stamp_state_version(spoke_root, master_managed)
    return results


def _stamp_state_version(spoke_root, master_managed):
    """Align WAI-State.wheel.harness_version with the harness the spoke now runs."""
    try:
        version = (Path(master_managed).parent.parent / VERSION_FILE)
        if not version.exists():
            version = Path(master_managed).parent / VERSION_FILE
        target = str(version.read_text().strip())

        state_path = Path(spoke_root) / "WAI-Harness" / "spoke" / "local" / "WAI-State.json"
        if not state_path.exists():
            state_path = Path(spoke_root) / "WAI-Spoke" / "WAI-State.json"
        if not state_path.exists():
            return {"ok": False, "error": "WAI-State.json not found"}

        state = json.loads(state_path.read_text())
        prior = (state.get("wheel") or {}).get("harness_version")
        if str(prior) == target:
            return {"ok": True, "unchanged": prior}
        state.setdefault("wheel", {})["harness_version"] = target
        state_path.write_text(json.dumps(state, indent=2) + "\n")
        return {"ok": True, "from": prior, "to": target}
    except Exception as e:  # noqa: BLE001 — reported, never fatal
        return {"ok": False, "error": str(e)[:120]}


# Lug taxonomy + core dirs for the EMPTY per-spoke local skeleton (mirrors
# harness_init). A fresh install scaffolds this rather than copying the master's
# local/ — see install() for why (master local/ holds the master's own work-state).
_LUG_TYPES = ("bug", "chain", "decision", "epic", "feature", "fix", "foundation",
              "hypothesis", "idea", "impl", "implementation", "notation", "other",
              "session-summary", "signal", "spec", "task", "work")
_LUG_STATUSES = ("open", "in_progress", "completed")
_LOCAL_SKELETON_DIRS = (
    "sessions", "runtime", "savepoints", "initiatives", "bolts", "teachings", "kpi",
    "signals/incoming", "signals/processed", "seed/ingest/processed",
    "lugs/incoming/processed", "lugs/incoming/completed", "lugs/outgoing",
)


def _scaffold_local_skeleton(local_root):
    """Create an EMPTY per-spoke local/ tree (dirs + .gitkeep, no data files), so a
    fresh spoke starts with its OWN empty work-state and never inherits the master's
    lugs/sessions/state. Idempotent."""
    local_root = Path(local_root)
    dirs = list(_LOCAL_SKELETON_DIRS)
    for t in _LUG_TYPES:
        for s in _LUG_STATUSES:
            dirs.append(f"lugs/bytype/{t}/{s}")
    for d in dirs:
        (local_root / d).mkdir(parents=True, exist_ok=True)
        (local_root / d / ".gitkeep").touch()


# ---------------------------------------------------------------- managed ignore
#
# impl-harness-ignore-untrack-regenerable-advisor-runtime-state-v1.
#
# THE SPOKE ROOT .gitignore IS WHAT GIT READS. A WAI-Harness/.gitignore only ever
# governed paths BELOW itself and was invisible to anyone reading the repo's
# ignore rules, so shipping one looked like the problem was handled while the
# churn kept arriving. Operator decision 2026-06-14: manage the root file, retire
# the harness-local copy.
#
# A .gitignore CHANGE ALONE DOES NOTHING FOR ALREADY-TRACKED FILES, which is why
# this ships with untrack_regenerable(): the dated advisor snapshots were tracked,
# so git dutifully reported them modified every session no matter what the ignore
# file said. Measured 2026-07-31: 499 of 641 untracked source files across the
# fleet were regenerable advisor/runtime state, and 20 more were tracked-and-
# rewritten in the master alone.
_IGNORE_BEGIN = "# === WAI managed: regenerable advisor/runtime state (idempotent block) ==="
_IGNORE_END = "# === end WAI managed block ==="

# Scoped STRICTLY to regenerable globs. Durable advisor config (context_prompt.md,
# registry.json), lugs, WAI-State.json and track history must never match — an
# untracking sweep that ate work-state would be far worse than the churn it fixes.
MANAGED_IGNORE_GLOBS = [
    "WAI-Harness/spoke/local/runtime/",
    "WAI-Harness/spoke/local/wakeup-brief.json",
    "WAI-Harness/spoke/advisors/*/scan_state.json",
    "WAI-Harness/spoke/advisors/*/passes.jsonl",
    "WAI-Harness/spoke/advisors/*/vectors.jsonl",
    "WAI-Harness/spoke/advisors/*/findings-log.jsonl",
    # dated CONTEXT snapshots — rewritten every session; the dominant churn.
    "WAI-Harness/spoke/advisors/*/context/snapshot-*",
    "WAI-Harness/hub/local/WAI-Hub/advisors/*/context/snapshot-*",
    "WAI-Harness/spoke/advisors/*/expeditions/*.json",
    # v3 coexist spokes keep their regenerable state under WAI-Spoke/.
    "WAI-Spoke/runtime/",
    "WAI-Spoke/advisors/*/scan_state.json",
    "WAI-Spoke/advisors/*/context/snapshot-*",
]


def write_managed_ignore(spoke_root):
    """Write the managed block into the SPOKE ROOT .gitignore, idempotently.

    Everything outside the delimited block is preserved verbatim — a spoke's own
    project rules are none of the harness's business, and clobbering them is how a
    managed file earns a reputation nobody can undo.
    """
    import re as _re
    p = Path(spoke_root) / ".gitignore"
    block = "\n".join([_IGNORE_BEGIN] + MANAGED_IGNORE_GLOBS + [_IGNORE_END]) + "\n"
    existing = p.read_text() if p.exists() else ""
    pattern = _re.compile(
        _re.escape(_IGNORE_BEGIN) + r".*?" + _re.escape(_IGNORE_END) + r"\n?",
        _re.S)
    if pattern.search(existing):
        new = pattern.sub(block, existing)
    elif _IGNORE_BEGIN in existing:
        # An older un-terminated block: replace from the marker to end-of-section
        # rather than appending a second one and ignoring twice.
        head = existing.split(_IGNORE_BEGIN)[0]
        new = head + block
    else:
        new = (existing.rstrip("\n") + "\n\n" if existing.strip() else "") + block
    if new != existing:
        p.write_text(new)
        return True
    return False


def untrack_regenerable(spoke_root):
    """git rm --cached the regenerable files git is still tracking.

    Idempotent and non-destructive: --cached leaves every file on disk, and
    --ignore-unmatch makes a spoke that never tracked them a no-op. Returns the
    number of paths untracked so the caller can report it rather than guess.
    """
    import subprocess as _sp
    n = 0
    for glob in MANAGED_IGNORE_GLOBS:
        if glob.endswith("/"):
            glob = glob + "**"
        try:
            before = _sp.run(["git", "-C", str(spoke_root), "ls-files", glob],
                             capture_output=True, text=True, timeout=60).stdout
            hits = [x for x in before.splitlines() if x.strip()]
            if not hits:
                continue
            _sp.run(["git", "-C", str(spoke_root), "rm", "--cached", "-q",
                     "--ignore-unmatch", "--"] + hits,
                    capture_output=True, text=True, timeout=120)
            n += len(hits)
        except Exception:  # noqa: BLE001 -- never fail an upgrade over hygiene
            continue
    return n


def retire_harness_local_gitignore(harness_root):
    """Remove the WAI-Harness/.gitignore the harness used to ship.

    It governed only paths below itself and was invisible where anyone actually
    looks, so it read as coverage while providing almost none."""
    p = Path(harness_root) / ".gitignore"
    if p.exists():
        try:
            p.unlink()
            return True
        except OSError:
            return False
    return False


def install(master_root, spoke_root, include_hub=False):
    """NON-DESTRUCTIVE v4 install: drop a `WAI-Harness/` folder into an existing
    spoke, beside its v3 `WAI-Spoke/`. Both then coexist; which runs depends on
    which hub folder you invoke. Nothing outside `<spoke>/WAI-Harness/` is written.

    - fresh (no WAI-Harness yet): copy the master's managed/ serving tree into
      <spoke>/WAI-Harness/spoke/managed and SCAFFOLD an empty local/ skeleton.
      The master's local/ is NOT copied: on a live master (e.g. mywheel, itself an
      active spoke) local/ holds the master's own work-state (lugs, sessions, WAI-
      State), and cloning it would contaminate every new spoke with that context.
    - re-install (WAI-Harness exists): run the verify-apply-verify upgrade on its
      managed tree (local untouched).

    Returns a report incl. the pre-existing top-level entries observed before and
    after, so the caller can assert non-destruction.
    """
    master_root, spoke_root = Path(master_root), Path(spoke_root)
    harness = spoke_root / "WAI-Harness"
    pre_existing = sorted(p.name for p in spoke_root.iterdir()) if spoke_root.exists() else []

    report = {"spoke_root": str(spoke_root), "fresh": not harness.exists(),
              "pre_existing": pre_existing}

    if not harness.exists():
        # fresh install: copy ONLY the master's managed/ serving tree (so the install
        # matches the manifest exactly), then scaffold an EMPTY local/ skeleton. We must
        # NOT copy the master's local/ — it is the master's per-spoke work-state and
        # would contaminate the new spoke (see docstring).
        _ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".DS_Store")
        shutil.copytree(master_root / "spoke" / "managed", harness / "spoke" / "managed", ignore=_ignore)
        # copytree carried the master MANIFEST verbatim (is_master:true) -- neutralize it
        # on the installed spoke (bug fix-manifest-is-master-neutralized-on-distribute-v1).
        _write_neutralized_manifest(master_root / "spoke" / "managed", harness / "spoke" / "managed")
        _scaffold_local_skeleton(harness / "spoke" / "local")
        if include_hub and (master_root / "hub").exists():
            shutil.copytree(master_root / "hub" / "managed", harness / "hub" / "managed", ignore=_ignore)
            _write_neutralized_manifest(master_root / "hub" / "managed", harness / "hub" / "managed")
            # hub local/ regenerates from its advisors; ship just an empty marker
            (harness / "hub" / "local").mkdir(parents=True, exist_ok=True)
            (harness / "hub" / "local" / ".gitkeep").touch()
        # The invariant is unchanged — the installed spoke's local/ churn must never
        # dirty the tracked tree — but it is enforced where git actually reads it.
        # This used to copy the master .gitignore to WAI-Harness/.gitignore, which
        # governs only paths below itself and sits where nobody looks: it read as
        # coverage while providing almost none.
        report["installed"] = "fresh"
        report["gitignore_shipped"] = False
    else:
        # re-install = upgrade the managed tree in place
        up = upgrade(master_root / "spoke" / "managed", harness / "spoke" / "managed")
        report["installed"] = "upgrade"
        report["upgrade"] = up

    # ---- managed ignore: root .gitignore + untrack what git already tracks ----
    # Runs on BOTH paths (fresh install and in-place upgrade). An upgrade is where
    # this matters most: the fleet is already installed, already tracking the
    # regenerable files, and already dirtying every session over them.
    report["gitignore_block_written"] = write_managed_ignore(spoke_root)
    report["untracked_regenerable"] = untrack_regenerable(spoke_root)
    report["harness_gitignore_retired"] = retire_harness_local_gitignore(harness)

    # verify the installed managed tree against the master manifest
    report["verify"] = verify(harness / "spoke" / "managed",
                              load_manifest(master_root / "spoke" / "managed"))
    if include_hub and (harness / "hub" / "managed").exists():
        report["verify_hub"] = verify(harness / "hub" / "managed",
                                      load_manifest(master_root / "hub" / "managed"))

    report["post_existing"] = sorted(p.name for p in spoke_root.iterdir())
    # non-destruction: every pre-existing top-level entry still present, WAI-Harness added
    report["non_destructive"] = (set(pre_existing) <= set(report["post_existing"])
                                 and "WAI-Harness" in report["post_existing"])
    report["ok"] = report["verify"]["ok"] and report["non_destructive"]
    return report


# --- CLI --------------------------------------------------------------------

def _resolve_managed(root, side):
    """root may be a WAI-Harness root, a spoke/hub root, or a managed dir itself."""
    p = Path(root)
    if (p / MANIFEST_NAME).exists():
        return p
    for cand in (p / side / "managed", p / "managed"):
        if cand.exists():
            return cand
    return p / side / "managed"


def main(argv):
    ap = argparse.ArgumentParser(description="verify-apply-verify harness upgrade engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("manifest", help="(re)generate a MANIFEST.json for a managed root")
    g.add_argument("--managed", required=True)
    g.add_argument("--version", default=DEFAULT_VERSION)
    g.add_argument("--generated-at", default="1970-01-01T00:00:00Z")
    g.add_argument("--owner", default="framework")
    g.add_argument("--write", action="store_true")
    g.add_argument("--skip-lint", action="store_true",
                   help="skip the v3-path cut gate (escape hatch; default runs it on --write); "
                        "REQUIRES --skip-lint-reason")
    g.add_argument("--skip-lint-reason", default=None,
                   help="non-empty reason recorded into the manifest as cut_gate_skipped "
                        "(required when --skip-lint is set)")

    for name in ("home-map", "upgrade"):
        s = sub.add_parser(name, help=f"{name} master -> target")
        s.add_argument("--master", required=True)
        s.add_argument("--target", required=True)
        s.add_argument("--side", default="spoke", choices=["spoke", "hub"])
        if name == "upgrade":
            s.add_argument("--dry-run", action="store_true")
            s.add_argument("--no-validate", action="store_true",
                           help="skip post-apply validation (bytes-only, pre-4.14.4 behaviour)")
            s.add_argument("--expect-version", default=None,
                           help="abort (write nothing) if the master harness_version != this")
            s.add_argument("--clean", action="store_true",
                           help="CLEAN-REPLACE: purge every managed file the master does not "
                                "ship (not just prior-manifest orphans), so managed ends == "
                                "master exactly. Protected state + local_allow pins survive. "
                                "The operator's clean-replace model; opt-in until local files "
                                "are relocated out of managed/.")

    p = sub.add_parser("pull", help="pull-on-spin-up: bring this spoke's managed current from master (cheap no-op when current)")
    p.add_argument("--spoke-root", default=".")
    p.add_argument("--master", default=None,
                   help="master path; default resolves via $WAI_HARNESS_MASTER -> .harness-master -> built-in")
    p.add_argument("--side", default="spoke", choices=["spoke", "hub"])
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-validate", action="store_true",
                   help="skip post-apply validation (bytes-only, pre-4.14.4 behaviour)")
    p.add_argument("--expect-version", default=None,
                   help="abort (write nothing) if the master harness_version != this — guards against a 'pull vX' silently bringing vY")

    v = sub.add_parser("verify", help="verify a managed root against its MANIFEST")
    v.add_argument("--managed", required=True)
    v.add_argument("--side", default="spoke", choices=["spoke", "hub"])

    vd = sub.add_parser("validate", help="does this spoke still work (the check md5 cannot make)")
    vd.add_argument("--spoke-root", default=".")

    i = sub.add_parser("install", help="non-destructively add WAI-Harness/ to a spoke")
    i.add_argument("--master", required=True, help="WAI-Harness master root")
    i.add_argument("--spoke", required=True, help="target spoke root (WAI-Harness/ is added here)")
    i.add_argument("--with-hub", action="store_true", help="also install the hub tree")

    args = ap.parse_args(argv)

    if args.cmd == "install":
        rep = install(args.master, args.spoke, include_hub=args.with_hub)
        print(json.dumps(rep, indent=2))
        return 0 if rep["ok"] else 1

    if args.cmd == "manifest":
        # CUT GATE: single fail-closed choke, consolidated into manifest_build._run_cut_gate
        # (impl-consolidate-cut-gate-v1 -- this subcommand no longer runs its own separate
        # lint; it routes through the ONE gate manifest_build.py owns). Escape: --skip-lint,
        # but ONLY with a non-empty --skip-lint-reason -- never a silent skip.
        if args.write:
            if args.skip_lint:
                if not (args.skip_lint_reason and args.skip_lint_reason.strip()):
                    print("--skip-lint requires an explicit non-empty --skip-lint-reason",
                          file=sys.stderr)
                    return 1
            else:
                try:
                    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                    import manifest_build
                except Exception as e:  # fail-closed: an unimportable gate refuses the cut
                    print(f"cut gate: manifest_build unavailable ({e}) -- refusing to cut "
                          "(fail-closed)", file=sys.stderr)
                    return 1
                try:
                    manifest_build._run_cut_gate(args.managed)
                except manifest_build.CutGateError as e:
                    print(str(e), file=sys.stderr)
                    return 1
        m = build_manifest(args.managed, version=args.version,
                           default_owner=args.owner, generated_at=args.generated_at)
        if args.write and args.skip_lint and args.skip_lint_reason:
            m["cut_gate_skipped"] = {"reason": args.skip_lint_reason.strip()}
        if args.write:
            (Path(args.managed) / MANIFEST_NAME).write_text(json.dumps(m, indent=2) + "\n")
            print(f"wrote {Path(args.managed) / MANIFEST_NAME} ({len(m['files'])} files)")
        else:
            print(json.dumps(m, indent=2))
        return 0

    if args.cmd == "home-map":
        master = _resolve_managed(args.master, args.side)
        target = _resolve_managed(args.target, args.side)
        hm = compute_home_map(master, target)
        print(json.dumps(hm, indent=2))
        return 0

    if args.cmd == "upgrade":
        master = _resolve_managed(args.master, args.side)
        target = _resolve_managed(args.target, args.side)
        rep = upgrade(master, target, dry_run=args.dry_run, expect_version=args.expect_version,
                      validate=not args.no_validate, clean=args.clean)
        print(json.dumps(rep, indent=2))
        return 0 if rep["ok"] else 1

    if args.cmd == "pull":
        rep = pull(args.spoke_root, args.master, side=args.side, dry_run=args.dry_run,
                   expect_version=args.expect_version, validate=not args.no_validate)
        print(json.dumps(rep, indent=2))
        return 0 if rep.get("status") not in ("failed", "version-desync") else 1

    if args.cmd == "validate":
        r = run_validation(args.spoke_root)
        print(json.dumps(r, indent=2))
        return 0 if r.get("outcome") != "fail" else 1

    if args.cmd == "verify":
        managed = _resolve_managed(args.managed, args.side)
        r = verify(managed, load_manifest(managed))
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 1

    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
