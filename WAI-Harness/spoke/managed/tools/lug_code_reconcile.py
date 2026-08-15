#!/usr/bin/env python3
"""lug_code_reconcile.py -- v5 warmup reconciles lug claims against the code (Ruling 20).

Ruling 20 (docs/wheelwright-v5-control-plane-directive.md, Part III, operator
verbatim): "On warm up of v5 it should identify incorrect behavior based on
expected behavior from the lugs it finds and reconciled to the code having
taken it through PEV process."

A completed lug is a CLAIM: "the code does X, and here is how you can check
that." The `verify` block it shipped with is the oracle it was closed against.
Nothing re-checks that claim after the session that made it ends -- an estate
drifts away from its own record silently. This tool re-runs the claim.

THE HONESTY RULE (same rule verification_objects.py enforces for Ruling 21):
this tool never invents a check. It never asks a model whether the code looks
right. It takes the lug's OWN verify block, classifies it with the same
regex-based, conservative classifier verify_ratchet.py uses to measure the
Ruling 21 ratio (verification_objects.migrate_v4_verify), and if -- and only
if -- every item in that block looks like a real, machine-executable command,
it runs those commands verbatim.

THREE OUTCOMES, always exactly one, never a binary pass/fail:

  RECONCILED     verify is executable, every command exited 0. The claim
                 still holds.
  DIVERGED       verify is executable, at least one command exited nonzero.
                 The code no longer does what the lug says -- the operator's
                 "incorrect behavior". Names which step failed.
  UNRECONCILABLE verify is prose (migrate_v4_verify says UNEXECUTABLE), OR a
                 command references a path that no longer exists on disk, OR
                 a command is refused by the safety deny-list, OR execution
                 timed out. UNRECONCILABLE is not a pass. It is a first-class
                 finding: the wheel is carrying a claim it has no way to
                 test. It must never render as green (see the assert in the
                 test suite, and note() below).

This tool NEVER reopens, mutates, or moves a lug. It is read-only over the
lug corpus, full stop. A DIVERGED verdict is a finding for a human -- the
code may be right and the lug's oracle may be stale; deciding which is not
this tool's call (see the operator's "descendant_prompt" on the shipping
lug: do not launder that judgement into a confident guess).

SAFETY. This tool executes commands written into lug files, by many agents,
over months, un-reviewed. It treats that corpus as hostile input:

  - Every command runs with a hard timeout (COMMAND_TIMEOUT_SECONDS).
  - Every command in a lug's verify block is scanned against DENY_PATTERNS
    BEFORE any command in that lug is run. One match refuses the WHOLE verify
    (not just the matched command) -- UNRECONCILABLE, reason "unsafe to
    execute". Nothing from that lug is ever executed, so a dangerous command
    that would only be reached as step 3 of 3 never gets the chance to run
    step 1 and step 2 first.
  - Every command is also scanned for referenced file/script paths that do
    not exist BEFORE execution; a missing path is UNRECONCILABLE, not a
    silent skip and not a DIVERGED.
  - Every command runs with cwd pinned to the repo root -- never a path
    outside it -- and shell=True is the only way a v4 verify string was ever
    going to run, so no extra escape surface is introduced beyond what the
    string already had.

INCREMENTAL BY GIT SHA (archeologist.py's contract, applied honestly here).
Archeologist can diff which of ITS OWN catalog rows are affected by a sha
change, because each row's evidence lives at the path it surveyed. This tool
cannot honestly do the same fine-grained trick: a lug's verify targets code
that can live anywhere in the tree, so a lug file being byte-identical does
NOT mean its target code is unchanged. The only sound cache-hit condition is
therefore the coarse one archeologist also falls back to: **the whole repo
sha is unchanged since the last run**. In that case NOTHING may have changed
anywhere the verify could observe, so re-running would be pure waste --
zero commands execute, prior results are re-emitted byte-for-byte. The
moment the sha moves at all, every completed lug's verify is re-run in
full; pretending a per-file diff could safely narrow that set would be
exactly the kind of confident-but-wrong shortcut this whole initiative
exists to refuse.

CLI:
  python3 tools/lug_code_reconcile.py reconcile [--repo .] [--base ...] [--json] [--force]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verification_objects as vo  # noqa: E402  -- reuse the Ruling 21 classifier

# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------

RECONCILED = "RECONCILED"
DIVERGED = "DIVERGED"
UNRECONCILABLE = "UNRECONCILABLE"
OUTCOMES = (RECONCILED, DIVERGED, UNRECONCILABLE)

COMMAND_TIMEOUT_SECONDS = 60

_ACTOR = {"model": "lug-code-reconcile", "provider": "deterministic"}
# Fixed timestamp handed to the pure classifier: classification of a given
# verify block must be a function of the block's content only.
_AT = "2026-01-01T00:00:00+00:00"

# ---------------------------------------------------------------------------
# Safety deny-list
# ---------------------------------------------------------------------------
# Matched against each command string. A hit refuses the ENTIRE lug's verify
# (every command in it), never a partial run. Word-boundary-guarded so
# substrings inside unrelated identifiers ("warmup", "confirm", "format")
# never false-positive.
DENY_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(?<![\w-])rm(?![\w-])"), "rm"),
    (re.compile(r"\bgit\s+push\b"), "git push"),
    (re.compile(r"\bgit\s+reset\b"), "git reset"),
    (re.compile(r"\bgit\s+clean\b"), "git clean"),
    (re.compile(r"\bgit\s+checkout\b"), "git checkout"),
    # Not in the operator's literal list, but a session-level hard constraint
    # of this very task ("No git writes. No commit, add, checkout, stash,
    # branch.") applies transitively to anything this tool executes on the
    # operator's behalf -- so these are refused too, for the same reason.
    (re.compile(r"\bgit\s+commit\b"), "git commit"),
    (re.compile(r"\bgit\s+add\b"), "git add"),
    (re.compile(r"\bgit\s+stash\b"), "git stash"),
    (re.compile(r"\bgit\s+branch\b"), "git branch"),
    (re.compile(r"(?<![\w-])mv(?![\w-])"), "mv"),
    (re.compile(r"(?<![\w-])dd(?![\w-])"), "dd"),
    (re.compile(r"(?<![\w-])chmod(?![\w-])"), "chmod"),
    (re.compile(r"(?<![\w-])curl(?![\w-])"), "curl"),
    (re.compile(r"(?<![\w-])wget(?![\w-])"), "wget"),
    (re.compile(r"(?<![\w-])sudo(?![\w-])"), "sudo"),
    # Shell redirection that WRITES a file: a bare '>' or '>>' not part of a
    # non-writing construct like '2>&1' (negative lookahead on '&').
    (re.compile(r"\d?>>?(?!&)"), "shell redirection that writes"),
]


def _deny_hit(command: str) -> Optional[str]:
    for pattern, label in DENY_PATTERNS:
        if pattern.search(command):
            return label
    return None


# ---------------------------------------------------------------------------
# Referenced-path existence check
# ---------------------------------------------------------------------------
# A command can be a syntactically real, safe command and STILL be
# unreconcilable if it names a script/fixture path that no longer exists --
# that is not a code regression, it is a broken oracle, and the operator's
# own wording ("names a path that no longer exists") puts it in
# UNRECONCILABLE, not DIVERGED.

_KNOWN_PATH_EXTENSIONS = (
    ".py", ".sh", ".json", ".jsonl", ".js", ".ts", ".mjs", ".cjs",
    ".md", ".yaml", ".yml", ".txt", ".toml", ".cfg", ".ini",
)


def _looks_like_path(token: str) -> bool:
    if not token or token.startswith("-"):
        return False
    if token.startswith("http://") or token.startswith("https://"):
        return False
    if "/" in token:
        return True
    return token.endswith(_KNOWN_PATH_EXTENSIONS)


def _strip_cmd_marker(command: str) -> str:
    """Strip a leading 'cmd:' marker.

    verification_objects._EXECUTABLE_PREFIX_RE recognizes a literal 'cmd:'
    token as one of its executable prefixes -- a convention some lug authors
    used to explicitly flag "the rest of this line is a real command". That
    marker is not itself shell syntax; running it verbatim fails with
    "cmd:: not found" (exit 127) on every single such lug, which would
    misreport a genuinely-passing oracle as DIVERGED. Strip it the same way
    the classifier already treats it -- as a marker, not a command token --
    before anything downstream (deny-list, path check, execution) sees the
    string.
    """
    stripped = command.lstrip()
    if stripped.startswith("cmd:"):
        return stripped[len("cmd:"):].lstrip()
    return command


def _referenced_missing_paths(command: str, repo_root: Path) -> List[str]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        # Unbalanced quotes etc. -- let execution itself surface the problem
        # rather than guessing; not a path-existence question.
        return []
    missing = []
    for tok in tokens[1:]:
        tok_clean = tok.rstrip(",;:")
        if not _looks_like_path(tok_clean):
            continue
        candidate = Path(tok_clean) if tok_clean.startswith("/") else (repo_root / tok_clean)
        if not candidate.exists():
            missing.append(tok_clean)
    return missing


def _referenced_paths_outside_repo(command: str, repo_root: Path) -> List[str]:
    """Path-like tokens that resolve outside repo_root -- an absolute path
    elsewhere on disk, or a '..'-escaping relative path. Existence is
    irrelevant here (an out-of-repo path that happens to exist, e.g. a
    sibling checkout, is exactly the dangerous case): 'Never run anything
    that touches a path outside this repo' is a hard constraint independent
    of whether the target happens to be there."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    repo_resolved = repo_root.resolve()
    outside = []
    for tok in tokens[1:]:
        tok_clean = tok.rstrip(",;:")
        if not _looks_like_path(tok_clean):
            continue
        is_absolute = tok_clean.startswith("/")
        escapes_upward = ".." in tok_clean.split("/")
        if not (is_absolute or escapes_upward):
            continue
        candidate = Path(tok_clean) if is_absolute else (repo_root / tok_clean)
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            outside.append(tok_clean)
            continue
        try:
            resolved.relative_to(repo_resolved)
        except ValueError:
            outside.append(tok_clean)
    return outside


# ---------------------------------------------------------------------------
# Per-lug reconciliation
# ---------------------------------------------------------------------------


def _make_result(lug_id: str, path: str, outcome: str, sha: str, **extra: Any) -> Dict[str, Any]:
    assert outcome in OUTCOMES, f"unknown outcome {outcome!r}"
    result = {
        "id": lug_id,
        "path": path,
        "outcome": outcome,
        "sha": sha,
    }
    result.update(extra)
    return result


def reconcile_lug(lug_dict: Dict[str, Any], lug_path: str, repo_root: Path, sha: str) -> Dict[str, Any]:
    """Reconcile a single completed lug's verify block against the code.

    Pure with respect to the filesystem it inspects (only reads); executes
    subprocesses only for verify blocks that pass BOTH the deny-list and the
    referenced-path pre-checks. Never mutates lug_dict or any lug file.
    """
    lug_id = lug_dict.get("id") or Path(lug_path).stem

    v5 = vo.migrate_v4_verify(lug_dict, _ACTOR, _AT)
    if v5.get("executability") != "EXECUTABLE":
        return _make_result(
            lug_id, lug_path, UNRECONCILABLE, sha,
            reason=v5.get("unexecutable_reason") or "verify is not machine-executable",
        )

    commands: List[str] = [_strip_cmd_marker(c) for c in v5["oracle"]["commands"]]

    # Pre-check 1: deny-list, over ALL commands before any run.
    for idx, cmd in enumerate(commands):
        hit = _deny_hit(cmd)
        if hit:
            return _make_result(
                lug_id, lug_path, UNRECONCILABLE, sha,
                reason="unsafe to execute",
                unsafe_step=idx,
                unsafe_command=cmd,
                unsafe_pattern=hit,
            )

    # Pre-check 2: paths that would take execution outside the repo, over
    # ALL commands before any run. Checked BEFORE existence, because an
    # out-of-repo path that exists (a sibling checkout) is the dangerous
    # case existence-checking alone would happily let through.
    for idx, cmd in enumerate(commands):
        outside = _referenced_paths_outside_repo(cmd, repo_root)
        if outside:
            return _make_result(
                lug_id, lug_path, UNRECONCILABLE, sha,
                reason=f"referenced path is outside the repo: {outside[0]}",
                outside_repo_step=idx,
                outside_repo_command=cmd,
                outside_repo_paths=outside,
            )

    # Pre-check 3: referenced-path existence, over ALL commands before any run.
    for idx, cmd in enumerate(commands):
        missing = _referenced_missing_paths(cmd, repo_root)
        if missing:
            return _make_result(
                lug_id, lug_path, UNRECONCILABLE, sha,
                reason=f"referenced path does not exist: {missing[0]}",
                missing_step=idx,
                missing_command=cmd,
                missing_paths=missing,
            )

    # Execute, in order, stopping at the first failure.
    for idx, cmd in enumerate(commands):
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return _make_result(
                lug_id, lug_path, UNRECONCILABLE, sha,
                reason=f"verify timed out after {COMMAND_TIMEOUT_SECONDS}s",
                timeout_step=idx,
                timeout_command=cmd,
            )
        if proc.returncode != 0:
            return _make_result(
                lug_id, lug_path, DIVERGED, sha,
                failed_step=idx,
                failed_command=cmd,
                exit_code=proc.returncode,
                stderr_excerpt=(proc.stderr or "")[-2000:],
                stdout_excerpt=(proc.stdout or "")[-2000:],
                total_steps=len(commands),
            )

    return _make_result(lug_id, lug_path, RECONCILED, sha, total_steps=len(commands))


# ---------------------------------------------------------------------------
# Corpus walk
# ---------------------------------------------------------------------------


def find_completed_lugs(base: Path) -> List[Path]:
    """Every completed lug for the spoke -- the population of "done" claims
    Ruling 20 exists to re-check. Read-only glob; never a hub root, never a
    non-'completed' status bucket (open/in_progress/etc. are not claims of
    done yet, so reconciling them would be answering a different question)."""
    return sorted(Path(p) for p in glob.glob(str(base / "lugs" / "bytype" / "*" / "completed" / "*.json")))


def _git(repo_root: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=False)
    return out.stdout.strip()


def current_sha(repo_root: Path) -> str:
    sha = _git(repo_root, "rev-parse", "HEAD")
    return sha if sha else "UNKNOWN"


# ---------------------------------------------------------------------------
# State I/O (incremental-by-sha cache)
# ---------------------------------------------------------------------------


def state_paths(base: Path) -> Dict[str, Path]:
    d = base / "lug-reconcile"
    return {"dir": d, "state": d / "state.json", "results": d / "results.jsonl"}


def load_state(state_path: Path) -> Dict[str, Any]:
    if not state_path.is_file():
        return {}
    try:
        return json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state_path: Path, state: Dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")


def load_results(results_path: Path) -> List[Dict[str, Any]]:
    if not results_path.is_file():
        return []
    rows = []
    with results_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_results(results_path: Path, rows: List[Dict[str, Any]]) -> None:
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with results_path.open("w") as f:
        for row in sorted(rows, key=lambda r: r["id"]):
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")


# ---------------------------------------------------------------------------
# Top-level reconcile
# ---------------------------------------------------------------------------


def reconcile(repo_root: Path, base: Path, force: bool = False) -> Dict[str, Any]:
    sha = current_sha(repo_root)
    paths = state_paths(base)
    state = load_state(paths["state"])
    prev_results = load_results(paths["results"])

    if not force and prev_results and state.get("last_sha") == sha:
        # Whole-tree sha is unchanged since the last run: nothing anywhere
        # the corpus's verifies could observe has moved. Re-emit the prior
        # results byte-for-byte; execute nothing.
        results = prev_results
        executed = 0
        skipped = len(results)
    else:
        lug_paths = find_completed_lugs(base)
        results = []
        for p in lug_paths:
            try:
                lug_dict = json.loads(p.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                results.append(_make_result(p.stem, str(p), UNRECONCILABLE, sha,
                                             reason=f"lug file unreadable: {type(exc).__name__}"))
                continue
            results.append(reconcile_lug(lug_dict, str(p), repo_root, sha))
        executed = len(results)
        skipped = 0
        write_results(paths["results"], results)
        write_state(paths["state"], {"last_sha": sha, "reconciled_at": time.time()})

    counts = {o: 0 for o in OUTCOMES}
    diverged_ids = []
    unreconcilable_ids = []
    for r in results:
        counts[r["outcome"]] += 1
        if r["outcome"] == DIVERGED:
            diverged_ids.append(r["id"])
        elif r["outcome"] == UNRECONCILABLE:
            unreconcilable_ids.append(r["id"])

    return {
        "sha": sha,
        "total": len(results),
        "executed": executed,
        "skipped": skipped,
        "counts": counts,
        "diverged_ids": sorted(diverged_ids),
        "unreconcilable_ids": sorted(unreconcilable_ids),
        "results": results,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resolve_repo(repo: str) -> Path:
    return Path(repo).resolve()


def _resolve_base(repo_root: Path, base: Optional[str]) -> Path:
    if base is None:
        return repo_root / "WAI-Harness" / "spoke" / "local"
    p = Path(base)
    return p if p.is_absolute() else (repo_root / p)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("reconcile", help="reconcile every completed lug's verify against the code")
    r.add_argument("--repo", default=".")
    r.add_argument("--base", default=None, help="defaults to <repo>/WAI-Harness/spoke/local")
    r.add_argument("--json", action="store_true")
    r.add_argument("--force", action="store_true", help="ignore the sha cache and re-run everything")

    args = ap.parse_args(argv)

    if args.cmd == "reconcile":
        repo_root = _resolve_repo(args.repo)
        base = _resolve_base(repo_root, args.base)
        out = reconcile(repo_root, base, force=args.force)
        summary = {k: v for k, v in out.items() if k != "results"}
        if args.json:
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            print(f"[lug-code-reconcile] sha={out['sha']} total={out['total']} "
                  f"executed={out['executed']} skipped={out['skipped']}")
            print(f"  RECONCILED:     {out['counts'][RECONCILED]}")
            print(f"  DIVERGED:       {out['counts'][DIVERGED]}")
            print(f"  UNRECONCILABLE: {out['counts'][UNRECONCILABLE]}")
            if out["diverged_ids"]:
                print("  diverged lug ids:")
                for lug_id in out["diverged_ids"]:
                    print(f"    - {lug_id}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
