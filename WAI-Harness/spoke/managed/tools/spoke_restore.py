#!/usr/bin/env python3
"""spoke_restore.py — per-spoke declarative restore: verify / restore / oracle.

The restore contract lives IN WAI-Harness/spoke/basher.json (restore.items[]),
validated by WAI-Harness/spoke/managed/schemas/restore-contract.schema.json.
There is NO separate restore-contract.json (two-canons guard).

Modes:
  --verify   schema-validate basher.json, verify tracked items (MANIFEST md5
             sample / git index), and run the gitignore-coverage check: every
             non-comment non-negation pattern in the root .gitignore + every
             .gitignore under WAI-Harness/ must literal-match (exact string)
             some item's pattern field — any tier counts. Uncovered pattern =
             exit nonzero naming the pattern.
  --restore  run each regenerable item's regen_cmd (cwd = repo root, continue
             past failures but record them), print the external-needs
             checklist and the ephemeral accepted-loss list, and — when any
             external item exists — write a needs-restore-<spoke_id>-<YYYYMMDD>
             task lug into WAI-Harness/spoke/local/lugs/incoming/.
  --oracle   exit 0 only when tracked verified AND all regen_cmds succeeded
             AND externals explicitly listed; nonzero otherwise, stating why.

Assurance doctrine: nothing silent — every action, skip, failure and unmet
need is printed.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

TIERS = ("tracked", "regenerable", "external", "ephemeral")
MANIFEST_SAMPLE = 12  # deterministic md5 sample size for tracked/manifest verify


def log(msg):
    print(f"[spoke_restore] {msg}")
    sys.stdout.flush()


def default_root():
    # <root>/WAI-Harness/spoke/managed/tools/spoke_restore.py
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "..", "..", "..", ".."))


def contract_path(root):
    return os.path.join(root, "WAI-Harness", "spoke", "basher.json")


def schema_path(root):
    return os.path.join(root, "WAI-Harness", "spoke", "managed", "schemas",
                        "restore-contract.schema.json")


def load_contract(root):
    path = contract_path(root)
    log(f"loading contract: {path}")
    with open(path) as f:
        return json.load(f)


def get_items(contract):
    return (contract.get("restore") or {}).get("items") or []


# --------------------------------------------------------------------------
# schema validation
# --------------------------------------------------------------------------

def structural_check(contract):
    """Hand-rolled fallback mirroring restore-contract.schema.json."""
    errors = []
    for key in ("schema_version", "spoke", "restore"):
        if key not in contract:
            errors.append(f"missing top-level key: {key}")
    if not (contract.get("spoke") or {}).get("wheel_id"):
        errors.append("spoke.wheel_id missing/empty")
    items = get_items(contract)
    if not items:
        errors.append("restore.items missing or empty")
    required_by_tier = {
        "tracked": ("pattern", "verify"),
        "regenerable": ("pattern", "regen_cmd"),
        "external": ("need", "satisfier"),
        "ephemeral": ("pattern", "note"),
    }
    for i, it in enumerate(items):
        where = f"items[{i}] (id={it.get('id', '?')})"
        if not it.get("id"):
            errors.append(f"{where}: missing id")
        tier = it.get("tier")
        if tier not in TIERS:
            errors.append(f"{where}: bad tier {tier!r}")
            continue
        for field in required_by_tier[tier]:
            if not it.get(field):
                errors.append(f"{where}: tier {tier} requires {field}")
        if tier == "tracked" and it.get("verify") not in ("manifest", "git"):
            errors.append(f"{where}: verify must be manifest|git")
    return errors


def validate_schema(contract, root):
    errors = []
    spath = schema_path(root)
    used = "hand-rolled structural check"
    try:
        import jsonschema  # type: ignore
        with open(spath) as f:
            schema = json.load(f)
        used = f"jsonschema against {spath}"
        validator = jsonschema.Draft7Validator(schema)
        for err in sorted(validator.iter_errors(contract), key=str):
            errors.append(f"schema: {'/'.join(str(p) for p in err.absolute_path)}: {err.message}")
    except ImportError:
        log("jsonschema not importable — falling back to structural check")
        errors.extend(f"structural: {e}" for e in structural_check(contract))
    except FileNotFoundError:
        log(f"WARNING schema file missing ({spath}) — falling back to structural check")
        used = "hand-rolled structural check (schema file missing)"
        errors.extend(f"structural: {e}" for e in structural_check(contract))
    # cross-item constraint JSON Schema cannot express: unique ids
    seen, dupes = set(), set()
    for it in get_items(contract):
        iid = it.get("id")
        if iid in seen:
            dupes.add(iid)
        seen.add(iid)
    for d in sorted(dupes):
        errors.append(f"duplicate item id: {d}")
    log(f"schema validation ({used}): {'PASS' if not errors else f'{len(errors)} error(s)'}")
    for e in errors:
        log(f"  ERROR {e}")
    return not errors


# --------------------------------------------------------------------------
# tracked verification
# --------------------------------------------------------------------------

def verify_manifest(root):
    """Compare a deterministic sample of MANIFEST md5s against the managed tree."""
    managed = os.path.join(root, "WAI-Harness", "spoke", "managed")
    mpath = os.path.join(managed, "MANIFEST.json")
    if not os.path.isfile(mpath):
        log(f"MANIFEST not found ({mpath}) — manifest verify SKIPPED")
        return True
    with open(mpath) as f:
        manifest = json.load(f)
    files = manifest.get("files") or {}
    if not files:
        log("MANIFEST has no files{} map — manifest verify SKIPPED")
        return True
    paths = sorted(files)
    step = max(1, len(paths) // MANIFEST_SAMPLE)
    sample = paths[::step][:MANIFEST_SAMPLE]
    bad = []
    for rel in sample:
        want = (files[rel] or {}).get("md5")
        fpath = os.path.join(managed, rel)
        if not os.path.isfile(fpath):
            bad.append(f"{rel}: missing on disk")
            continue
        with open(fpath, "rb") as f:
            got = hashlib.md5(f.read()).hexdigest()
        if want and got != want:
            bad.append(f"{rel}: md5 {got} != manifest {want}")
    log(f"manifest verify: sampled {len(sample)}/{len(paths)} entries -> "
        f"{'PASS' if not bad else 'FAIL'}")
    for b in bad:
        log(f"  MISMATCH {b}")
    return not bad


def verify_git(root, pattern):
    """Tracked/git item: the pattern's base path must have files in the git index."""
    base = pattern.replace("/**", "").rstrip("/*")
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "--", base],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        log(f"git verify {pattern}: git unavailable ({e}) — FAIL")
        return False
    ok = out.returncode == 0 and bool(out.stdout.strip())
    log(f"git verify {pattern} (base {base}): "
        f"{'PASS (' + str(len(out.stdout.splitlines())) + ' tracked files)' if ok else 'FAIL (no tracked files)'}")
    return ok


def verify_tracked(contract, root):
    ok = True
    tracked = [it for it in get_items(contract) if it.get("tier") == "tracked"]
    if not tracked:
        log("no tracked items declared — tracked verify FAIL (contract incomplete)")
        return False
    for it in tracked:
        mode = it.get("verify")
        log(f"tracked item {it.get('id')}: verify={mode}")
        if mode == "manifest":
            ok = verify_manifest(root) and ok
        elif mode == "git":
            ok = verify_git(root, it.get("pattern", "")) and ok
        else:
            log(f"  ERROR unknown verify mode {mode!r}")
            ok = False
    return ok


# --------------------------------------------------------------------------
# gitignore coverage
# --------------------------------------------------------------------------

def gitignore_patterns(root):
    files = []
    top = os.path.join(root, ".gitignore")
    if os.path.isfile(top):
        files.append(top)
    wai = os.path.join(root, "WAI-Harness")
    for r, dirs, fs in os.walk(wai):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules")]
        if ".gitignore" in fs:
            files.append(os.path.join(r, ".gitignore"))
    pats = {}
    for f in sorted(files):
        with open(f) as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#") or s.startswith("!"):
                    continue
                pats.setdefault(s, []).append(os.path.relpath(f, root))
    log(f"gitignore scan: {len(files)} file(s), {len(pats)} unique non-comment "
        f"non-negation pattern(s)")
    return pats


def coverage_check(contract, root):
    pats = gitignore_patterns(root)
    declared = {it["pattern"] for it in get_items(contract) if it.get("pattern")}
    uncovered = [p for p in sorted(pats) if p not in declared]
    if uncovered:
        log(f"gitignore coverage: FAIL — {len(uncovered)} uncovered pattern(s):")
        for p in uncovered:
            log(f"  UNCOVERED {p!r} (from {', '.join(pats[p])})")
        return False
    log(f"gitignore coverage: PASS — all {len(pats)} patterns covered by items[]")
    return True


# --------------------------------------------------------------------------
# reporting helpers (nothing silent)
# --------------------------------------------------------------------------

def print_externals(contract):
    ext = [it for it in get_items(contract) if it.get("tier") == "external"]
    log(f"external needs checklist ({len(ext)} item(s)) — the spoke CANNOT "
        f"self-satisfy these; supply via the named satisfier:")
    for it in ext:
        log(f"  EXTERNAL {it['id']}: need={it.get('need')} | satisfier={it.get('satisfier')}")
    return ext


def print_ephemeral(contract):
    eph = [it for it in get_items(contract) if it.get("tier") == "ephemeral"]
    log(f"ephemeral accepted-loss list ({len(eph)} item(s)) — declared, skipped:")
    for it in eph:
        log(f"  EPHEMERAL {it['id']}: pattern={it.get('pattern')!r} | {it.get('note')}")
    return eph


def write_needs_lug(contract, root, externals):
    spoke_id = (contract.get("spoke") or {}).get("wheel_id", "unknown-spoke")
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    lug_id = f"needs-restore-{spoke_id}-{day}"
    incoming = os.path.join(root, "WAI-Harness", "spoke", "local", "lugs", "incoming")
    os.makedirs(incoming, exist_ok=True)
    path = os.path.join(incoming, f"{lug_id}.json")
    lug = {
        "id": lug_id,
        "type": "task",
        "status": "open",
        "title": f"Restore of {spoke_id}: {len(externals)} external need(s) unmet",
        "summary": ("spoke_restore.py --restore regenerated what it could; these "
                    "external machine-layer needs remain unmet: "
                    + "; ".join(f"{it['id']}: {it.get('need')} (satisfier: {it.get('satisfier')})"
                                for it in externals)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "authored_by": "spoke_restore.py",
    }
    with open(path, "w") as f:
        json.dump(lug, f, indent=2)
        f.write("\n")
    log(f"wrote needs-lug: {path}")
    return path


# --------------------------------------------------------------------------
# modes
# --------------------------------------------------------------------------

def run_regens(contract, root):
    regens = [it for it in get_items(contract) if it.get("tier") == "regenerable"]
    failures = []
    log(f"running {len(regens)} regenerable item(s) in items[] order (cwd={root}):")
    for it in regens:
        cmd = it.get("regen_cmd", "")
        log(f"  REGEN {it['id']}: {cmd}")
        try:
            proc = subprocess.run(cmd, shell=True, cwd=root,
                                  capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as e:
            log(f"    FAILED (exception: {e}) — continuing")
            failures.append((it["id"], str(e)))
            continue
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            detail = detail[-1] if detail else f"exit {proc.returncode}"
            log(f"    FAILED (exit {proc.returncode}: {detail}) — continuing")
            failures.append((it["id"], f"exit {proc.returncode}: {detail}"))
        else:
            log("    ok")
    if failures:
        log(f"regen summary: {len(failures)}/{len(regens)} FAILED: "
            + ", ".join(i for i, _ in failures))
    else:
        log(f"regen summary: all {len(regens)} succeeded")
    return failures


def mode_verify(contract, root):
    log(f"--verify (root={root})")
    ok = validate_schema(contract, root)
    ok = verify_tracked(contract, root) and ok
    ok = coverage_check(contract, root) and ok
    log(f"--verify result: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def mode_restore(contract, root):
    log(f"--restore (root={root})")
    failures = run_regens(contract, root)
    externals = print_externals(contract)
    print_ephemeral(contract)
    if externals:
        write_needs_lug(contract, root, externals)
    else:
        log("no external items declared — no needs-lug written")
    if failures:
        log(f"--restore result: PARTIAL — {len(failures)} regen failure(s) recorded above")
        return 1
    log("--restore result: COMPLETE (externals remain a machine-layer/operator task; see checklist + needs-lug)")
    return 0


def mode_oracle(contract, root):
    log(f"--oracle (root={root})")
    reasons = []
    if not validate_schema(contract, root):
        reasons.append("contract failed schema validation")
    if not verify_tracked(contract, root):
        reasons.append("tracked items not verified")
    if not coverage_check(contract, root):
        reasons.append("gitignore coverage incomplete")
    failures = run_regens(contract, root)
    if failures:
        reasons.append("regen failures: " + ", ".join(i for i, _ in failures))
    externals = print_externals(contract)  # explicit listing is the requirement
    print_ephemeral(contract)
    log(f"externals explicitly listed: {len(externals)}")
    if reasons:
        log("--oracle result: FAIL — " + "; ".join(reasons))
        return 1
    log("--oracle result: PASS (tracked verified + regenerables regenerated + externals listed)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--verify", action="store_true",
                      help="validate contract + tracked + gitignore coverage")
    mode.add_argument("--restore", action="store_true",
                      help="regenerate, report externals/ephemeral, file needs-lug")
    mode.add_argument("--oracle", action="store_true",
                      help="deterministic pass/fail for a completed restore")
    ap.add_argument("--root", default=None,
                    help="repo root (default: derived from this script's location)")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root) if args.root else default_root()
    try:
        contract = load_contract(root)
    except (OSError, json.JSONDecodeError) as e:
        log(f"FATAL cannot load contract: {e}")
        return 1
    if args.verify:
        return mode_verify(contract, root)
    if args.restore:
        return mode_restore(contract, root)
    return mode_oracle(contract, root)


if __name__ == "__main__":
    sys.exit(main())
