#!/usr/bin/env python3
"""git_hygiene.py — the ACT arm of spoke git hygiene (self-healing).

dead_end_scan.py DETECTS carryover and hygiene_run.py SIGNALS it, but both are
strictly READ-ONLY. When a session auto-ejects or crashes, nothing ever heals the
tree: generated-runtime churn piles up uncommitted (247+ files is normal), the
session branch drifts ahead of main, and local main goes stale vs origin. Closeout
has the logic but only runs on a clean exit — the exact case that fails is the
crash. This is the arm that ACTS, innately and safely.

What it does (in order), all idempotent:

  1. CLASSIFY the uncommitted tree into three buckets by deterministic path rules:
       runtime  — self-owned generated state (session tracks, lug state, advisor
                  snapshots, WAI-State, capability/taste graphs, hub-local
                  registries). SAFE to auto-commit; keeping it tracked preserves
                  restore-safety (the spoke "brain" stays in git).
       blocked  — .claude/**, **/managed/**, MANIFEST.json, .mcp.json, CLAUDE.md,
                  AGENTS.md, WAI-Harness/dev/**. These are AUTHORED distribution
                  source. NEVER auto-committed — an authored change buried under a
                  "chore(hygiene)" sweep loses its real message and (on a spoke)
                  bypasses Basher. Surfaced for a human / recut.
       unknown  — anything else (genuinely novel source). Surfaced, never committed.

  2. COMMIT only the runtime bucket, with explicit `git add -- <path>` (never
     `git add -A`), under a standard chore(hygiene) message. The commit runs the
     SECURITY gates (secret scan + JSON-parse validity) but skips the AUTHORING
     gates (manifest-integrity, lug lens-compliance) via --no-verify: those judge
     how a lug was *written*, and must never block the tool from persisting the
     current on-disk state of lugs authored elsewhere (otherwise one in-flight
     non-compliant lug wedges the whole self-heal). A secret or corrupt-JSON file
     still hard-aborts the commit.

  3. REUNIFY main by fast-forward ONLY: if the current branch is ahead of main and
     origin/main is a strict ancestor of the branch tip (a clean FF, no divergence),
     advance origin/main and local main to the tip. A pure FF over already-pushed
     commits is reversible and conflict-free. If main has diverged, it is SURFACED,
     never force-pushed.

Safety rails:
  * Respects the CSRP convergence merge-lock ({BASE}/runtime/converge.lock): if
    another session holds a live lease, reunify is skipped (that session is the lead).
  * `--dry-run` computes and reports intended actions without touching anything.
  * `--best-effort` swallows every exception and always exits 0 — safe to call from
    a session-start hook where a failure must never block launch.
  * `--no-push` commits + fast-forwards local main but leaves origin untouched.

CLI:
  python3 git_hygiene.py heal   --base BASE [--root .] [--session-id SID]
                                [--dry-run] [--best-effort] [--no-push] [--json]
  python3 git_hygiene.py classify --base BASE [--root .] [--json]
  python3 git_hygiene.py status   --base BASE [--root .] [--json]
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

CO_AUTHOR = "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"

# ── path classification ──────────────────────────────────────────────────────
# BLOCKED wins over everything: authored distribution source is never swept. Every
# rule below matches ANYWHERE in the tree, not just at the repo root — a nested
# `.../lugs/.claude/hooks/x.sh` or `.../advisors/CLAUDE.md` sits under a runtime
# prefix and would otherwise be auto-committed, so basenames + segments are matched
# by basename / substring, never by exact whole-path equality.
BLOCKED_BASENAMES = {"MANIFEST.json", ".mcp.json", "CLAUDE.md", "AGENTS.md"}
BLOCKED_PREFIXES = (".claude/", "WAI-Harness/dev/")


def _is_blocked(path):
    if os.path.basename(path) in BLOCKED_BASENAMES:  # authored basename, any depth
        return True
    if any(path.startswith(p) for p in BLOCKED_PREFIXES):
        return True
    # managed/ or .claude/ as a segment ANYWHERE in the tree (spoke, hub, nested)
    if "/managed/" in path or path.startswith("managed/"):
        return True
    if "/.claude/" in path:
        return True
    return False


def _runtime_prefixes(base):
    """Directory prefixes whose contents are self-owned generated runtime state."""
    return (
        f"{base}/runtime/",
        f"{base}/advisors/",
        f"{base}/sessions/",
        f"{base}/lugs/",
        f"{base}/capabilitygraph/",
        f"{base}/maintenance/",
        f"{base}/initiatives/",
        f"{base}/savepoints/",
        f"{base}/seed/ingest/processed/",
        "WAI-Harness/hub/local/",       # hub-side generated state (ap-runs, registries, advisor logs)
        "WAI-Harness/spoke/advisors/",  # advisor context snapshots outside local
    )


def _runtime_files(base):
    """Exact generated-state files at the base root."""
    return (
        f"{base}/WAI-State.json",
        f"{base}/capabilities-graph-local.json",
        f"{base}/tastegraph.json",
        f"{base}/readiness-metrics.jsonl",
        f"{base}/wakeup-brief.json",
    )


def _porcelain_paths(root):
    """Return the set of changed paths from `git status --short` (post-arrow for renames).

    `--untracked-files=all` is required: without it git collapses an untracked
    directory to a single `dir/` entry, so per-file classification (and therefore
    the runtime auto-commit) would miss brand-new advisor snapshots / lug files.
    """
    # -z + core.quotePath=false → literal UTF-8 paths with NO octal-escaping or
    # surrounding quotes, so a runtime file with a unicode/space/control-char name
    # is passed to `git add` verbatim (an escaped pathspec matches nothing and would
    # abort the whole runtime commit). In -z output each entry is `XY PATH\0`; a
    # rename/copy adds the source as an extra `\0`-terminated field we skip.
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", "status", "--porcelain", "-z",
         "--untracked-files=all"],
        capture_output=True, text=True, cwd=root,
    )
    entries = result.stdout.split("\0")
    paths = []
    i = 0
    while i < len(entries):
        entry = entries[i]
        if len(entry) < 3:
            i += 1
            continue
        xy, path = entry[:2], entry[3:]  # classify by DESTINATION path
        if path:
            paths.append(path)
        i += 2 if xy[0] in ("R", "C") else 1  # skip the source field for renames/copies
    return paths


def classify(root, base):
    """Bucket the uncommitted tree into runtime / blocked / unknown.

    BLOCKED is checked first so authored distribution source is never swept into a
    runtime auto-commit, regardless of master status.
    """
    prefixes = _runtime_prefixes(base)
    files = set(_runtime_files(base))
    runtime, blocked, unknown = [], [], []
    for path in _porcelain_paths(root):
        if _is_blocked(path):
            blocked.append(path)
        elif path in files or any(path.startswith(p) for p in prefixes):
            runtime.append(path)
        else:
            unknown.append(path)
    return {"runtime": runtime, "blocked": blocked, "unknown": unknown}


# ── git helpers ──────────────────────────────────────────────────────────────
def _git(root, *args, check=False):
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=root, check=check,
    )


def _current_branch(root):
    return _git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def _rev(root, ref):
    r = _git(root, "rev-parse", "--short", ref)
    return r.stdout.strip() if r.returncode == 0 else None


def _is_ancestor(root, maybe_ancestor, descendant):
    return _git(root, "merge-base", "--is-ancestor", maybe_ancestor, descendant).returncode == 0


def _find_tool(root, name):
    for rel in (f"WAI-Harness/spoke/managed/tools/{name}", f"tools/{name}"):
        p = os.path.join(root, rel)
        if os.path.exists(p):
            return p
    return None


def _security_gates_pass(root):
    """Run ONLY the gates that apply to machine-generated runtime state churn:
    the SECRET scan and JSON-parse validity. The full pre-commit chain also runs
    manifest-integrity and lug lens-compliance gates — those are AUTHORING quality
    checks (was this lug written well?) and must NOT block the hygiene tool from
    persisting the current on-disk state of lugs authored elsewhere. But a secret
    or a corrupt-JSON runtime file must still hard-abort. Returns (ok, [failures]).
    Presence-guarded: an absent gate is skipped, not treated as a failure.
    """
    failures = []
    scanner = _find_tool(root, "secret_precommit_scan.py")
    if scanner:
        r = subprocess.run(["python3", scanner, "--staged"],
                           capture_output=True, text=True, cwd=root)
        if r.returncode != 0:
            failures.append("secret_precommit_scan: " + (r.stdout + r.stderr).strip()[:400])
    parse_gate = _find_tool(root, "lug_json_parse_gate.py")
    if parse_gate:
        r = subprocess.run(["python3", parse_gate, "--root", root],
                           capture_output=True, text=True, cwd=root)
        if r.returncode != 0:
            failures.append("lug_json_parse_gate: " + (r.stdout + r.stderr).strip()[:400])
    return (not failures, failures)


# ── CSRP merge-lock awareness ────────────────────────────────────────────────
def _converge_lock_live(root, base, session_id):
    """True if ANOTHER session holds a live convergence lease (skip reunify).

    Fail-OPEN (returns False) on a missing/unparseable lock: a corrupt or
    mid-write lock must never permanently wedge reunify, and the FF-only,
    non-force push is the backstop (a real concurrent main write is rejected
    server-side). The whole comparison lives inside the try so a naive
    timestamp can't raise past this function.
    """
    lock_path = os.path.join(root, base, "runtime", "converge.lock")
    try:
        lock = json.loads(open(lock_path).read())
        if lock.get("session_id") == session_id:
            return False  # our own lease never blocks us
        exp = str(lock.get("lease_expires", ""))
        expires = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        if expires.tzinfo is None:                       # naive → assume UTC
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > datetime.now(timezone.utc)
    except Exception:
        return False


# ── reunify (fast-forward only) ──────────────────────────────────────────────
def reunify_status(root, session_id, base):
    """Assess whether main can be cleanly fast-forwarded to the current branch tip."""
    branch = _current_branch(root)
    out = {"branch": branch, "action": None, "reason": None,
           "tip": _rev(root, "HEAD")}
    if branch in ("main", "HEAD", ""):
        out["reason"] = "on-main-or-detached"
        return out
    if _converge_lock_live(root, base, session_id):
        out["reason"] = "converge-lock-held-by-other-session"
        return out
    # Is main already at the tip? (nothing to do)
    behind = _git(root, "rev-list", "--count", f"main..{branch}").stdout.strip()
    origin_behind = _git(root, "rev-list", "--count", f"origin/main..{branch}").stdout.strip()
    if behind == "0" and origin_behind == "0":
        out["reason"] = "already-reunified"
        return out
    # Clean FF requires origin/main to be a strict ancestor of the branch tip.
    origin_ff = _is_ancestor(root, "origin/main", branch)
    local_ff = _is_ancestor(root, "main", branch)
    if origin_ff and local_ff:
        out["action"] = "ff"
        out["origin_behind"] = origin_behind
        out["local_behind"] = behind
    else:
        out["reason"] = "diverged-non-ff"  # surfaced, never force-pushed
    return out


def do_reunify(root, status, do_push):
    """Execute a clean fast-forward. Caller guarantees status['action']=='ff'.

    Push FIRST, then move local main only if the remote ACCEPTED the fast-forward.
    Our local origin/main tracking ref may be stale (no fetch); the remote is the
    source of truth. If origin actually diverged, the non-force push is rejected and
    we leave local main where it is, rather than advancing it past a remote that
    refused the update.
    """
    branch = status["branch"]
    result = {"local_main": False, "origin_main": False, "errors": []}
    remote_ok = True
    if do_push:
        r = _git(root, "push", "origin", f"{branch}:main")
        if r.returncode == 0:
            result["origin_main"] = True
        else:
            remote_ok = False
            result["errors"].append(f"push origin {branch}:main: {r.stderr.strip()}")
    if remote_ok:  # advance local main (not checked out — current branch != main)
        r = _git(root, "branch", "-f", "main", branch)
        if r.returncode == 0:
            result["local_main"] = True
        else:
            result["errors"].append(f"local branch -f main: {r.stderr.strip()}")
    return result


# ── heal (the ACT) ───────────────────────────────────────────────────────────
def heal(root, base, session_id, dry_run=False, do_push=True):
    report = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "committed": 0,
        "commit_sha": None,
        "blocked": [],
        "unknown": [],
        "reunify": None,
    }
    buckets = classify(root, base)
    report["blocked"] = buckets["blocked"]
    report["unknown"] = buckets["unknown"]
    runtime = buckets["runtime"]

    # 1. Commit runtime bucket — SCOPED to the runtime pathspec at BOTH stage and
    #    commit. Scoping the commit (not just the add) is the safety-critical part:
    #    if a blocked/unknown file was already staged in the index by another
    #    process before heal ran, a bare `git commit` would sweep it in. Passing the
    #    runtime pathspec to `git commit` guarantees ONLY runtime paths are recorded,
    #    regardless of prior index state.
    if runtime and not dry_run:
        # Stage each explicitly; -A on a pathspec picks up deletions + new files too.
        add = _git(root, "add", "-A", "--", *runtime)
        if add.returncode != 0:
            report["add_error"] = add.stderr.strip()
        else:
            # Did staging the runtime pathspec actually produce runtime changes?
            staged = _git(root, "diff", "--cached", "--name-only", "--", *runtime).stdout.strip()
            if staged:
                # Security/validity gates only (secret scan + JSON parse). A secret
                # or corrupt-JSON runtime file hard-aborts; the AUTHORING gates
                # (manifest-integrity, lug lens-compliance) are skipped via
                # --no-verify because they must not block persisting machine state.
                ok, gate_failures = _security_gates_pass(root)
                if not ok:
                    report["commit_error"] = "security-gate blocked: " + " | ".join(gate_failures)
                    # Leave a clean index on abort — never strand the runtime staged.
                    _git(root, "reset", "-q", "--", *runtime)
                else:
                    msg = (
                        f"chore(hygiene): auto-heal runtime churn [{session_id}]\n\n"
                        f"{len(runtime)} runtime path(s) committed by git_hygiene.\n"
                        f"surfaced (not committed): {len(buckets['blocked'])} blocked, "
                        f"{len(buckets['unknown'])} unknown.\n\n{CO_AUTHOR}"
                    )
                    # Pathspec → partial commit of ONLY these paths; --no-verify
                    # skips the authoring gates (secret+parse already run above).
                    c = _git(root, "commit", "--no-verify", "-m", msg, "--", *runtime)
                    if c.returncode == 0:
                        report["committed"] = len(staged.splitlines())
                        report["commit_sha"] = _rev(root, "HEAD")
                    else:
                        report["commit_error"] = c.stderr.strip()
                        _git(root, "reset", "-q", "--", *runtime)  # clean index on abort
    elif runtime and dry_run:
        report["committed"] = len(runtime)  # would-commit count

    # 2. Reunify main (fast-forward only).
    rstat = reunify_status(root, session_id, base)
    report["reunify"] = rstat
    if rstat.get("action") == "ff" and not dry_run:
        report["reunify"]["result"] = do_reunify(root, rstat, do_push)

    return report


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="Spoke git hygiene — the ACT arm.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("heal", "classify", "status"):
        p = sub.add_parser(name)
        p.add_argument("--base", required=True, help="Spoke BASE (e.g. WAI-Harness/spoke/local)")
        p.add_argument("--root", default=".", help="Repo root")
        p.add_argument("--json", action="store_true")
        if name == "heal":
            p.add_argument("--session-id", default="unknown")
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--best-effort", action="store_true",
                           help="Swallow all errors, always exit 0 (for hooks)")
            p.add_argument("--no-push", action="store_true")
    args = ap.parse_args(argv)

    try:
        base = args.base.rstrip("/")
        if args.cmd == "classify":
            out = classify(args.root, base)
            if args.json:
                print(json.dumps(out, indent=2))
            else:
                for k in ("runtime", "blocked", "unknown"):
                    print(f"{k}: {len(out[k])}")
            return 0
        if args.cmd == "status":
            out = reunify_status(args.root, "unknown", base)
            print(json.dumps(out, indent=2) if args.json else out.get("reason") or out.get("action"))
            return 0
        # heal
        rep = heal(args.root, base, args.session_id,
                   dry_run=args.dry_run, do_push=not args.no_push)
        if args.json:
            print(json.dumps(rep, indent=2))
        else:
            ru = rep["reunify"] or {}
            ru_desc = ru.get("action") or ru.get("reason")
            print(f"[git_hygiene] committed={rep['committed']} "
                  f"blocked={len(rep['blocked'])} unknown={len(rep['unknown'])} "
                  f"reunify={ru_desc}")
        return 0
    except Exception as e:  # noqa: BLE001
        if getattr(args, "best_effort", False):
            print(f"[git_hygiene] best-effort skip: {e}", file=sys.stderr)
            return 0
        raise


if __name__ == "__main__":
    sys.exit(main())
