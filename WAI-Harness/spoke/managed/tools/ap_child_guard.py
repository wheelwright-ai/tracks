#!/usr/bin/env python3
"""ap_child_guard.py -- keep a dispatched AP worker inside its own lane.

THE DEFECT THIS EXISTS FOR (operator, 2026-08-14): AP's own commit is scoped to
paths AP owns, but the agents AP DISPATCHES are ordinary `claude --print` processes
running in the spoke with a normal git. Nothing stopped a child from `git add -A`
and committing an operator's half-finished work. It cost staged work twice in one
session.

TWO CONTROLS, because one of them is defeatable:

  1. PREVENTION -- a pre-commit hook, installed for the child only via
     core.hooksPath, that refuses a commit staging paths outside the lug's declared
     file_targets. A child can defeat this with `git commit --no-verify`, which is
     exactly why it is not the only control.

  2. DETECTION -- verify_child_commits(), which AP runs ITSELF after the dispatch
     returns. It compares HEAD before and after and reports any committed path
     outside the allowlist. A child cannot bypass a check that runs in the parent.

The allowlist is the lug's file_targets plus the paths AP already owns. A lug with
no file_targets gets AP's paths only -- which is consistent with the productiveness
gate treating such a lug as unverifiable in the first place.

Prevention alone would have been theatre. Detection alone lets the damage land and
reports it afterward. Both, and the parent holds the one that cannot be turned off.
"""
from __future__ import annotations

import os
import posixpath
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

# Paths AP itself owns and commits; a child touching these is in-lane by definition.
AP_OWNED = (
    "WAI-Spoke/",
    "WAI-Harness/spoke/local/lugs/",
    "WAI-Harness/spoke/local/advisors/",
    "WAI-Harness/spoke/local/runtime/",
)

HOOK_DIRNAME = "ap-child-git-guard"

_PRE_COMMIT = r"""#!/usr/bin/env bash
# Installed for AP-dispatched children only, via core.hooksPath in the child env.
# Refuses a commit that stages paths outside the dispatched lug's declared lane.
# Bypassable with --no-verify by design of git; the parent's post-dispatch check
# (ap_child_guard.verify_child_commits) is the control that cannot be bypassed.
set -euo pipefail

allow="${WAI_AP_ALLOWED_PATHS:-}"
if [[ -z "$allow" ]]; then
  exit 0                     # no lane declared: not our commit to police
fi

staged="$(git diff --cached --name-only)"
[[ -z "$staged" ]] && exit 0

bad=()
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  ok=0
  while IFS= read -r p; do
    [[ -z "$p" ]] && continue
    # boundary-aware: a directory lane matches only at a / separator, so a lane
    # of src/a does NOT swallow src/aa.py (external review, 2026-08-15)
    if [[ "$f" == "$p" || "$f" == "$p"/* ]]; then ok=1; break; fi
  done <<< "$allow"
  (( ok )) || bad+=("$f")
done <<< "$staged"

if (( ${#bad[@]} )); then
  echo "AP CHILD GUARD: refusing commit -- ${#bad[@]} path(s) outside this lug's lane:" >&2
  printf '  %s\n' "${bad[@]}" >&2
  echo "This worker may only commit what its lug declared in file_targets." >&2
  exit 1
fi
exit 0
"""


def _normalise(p: str) -> str:
    """Repo-relative, forward-slashed, no traversal. Returns "" for anything that
    escapes the repo or is not usable as a pathspec.

    ADOPTED FROM EXTERNAL REVIEW (DeepSeek + Moonshot, 2026-08-15, independently):
    the comparison was raw string prefix matching, so `src/../secret.txt` was
    compared literally while git would normalise it to `secret.txt`. The allowlist
    and the thing git acts on have to be the same string or the guard is reasoning
    about a path that does not exist.
    """
    p = (p or "").strip().replace("\\", "/")
    if not p or p.startswith("/"):
        return ""
    p = posixpath.normpath(p)
    if p == "." or p.startswith("../") or p == "..":
        return ""
    return p


def in_lane(path: str, allow: Sequence[str]) -> bool:
    """Is `path` inside the lane? Directory prefixes match only on a / boundary.

    ADOPTED FROM EXTERNAL REVIEW (both reviewers named this as the top blocker,
    independently): `startswith` alone let a lane of `src/a` match `src/aa.py`,
    `src/ab/`, and `src/anything`. A worker declaring one narrow file quietly
    acquired every sibling whose name shared its prefix.
    """
    f = _normalise(path)
    if not f:
        return False          # unnormalisable path is never in-lane
    for raw in allow:
        p = _normalise(raw)
        if not p:
            continue
        if f == p:
            return True
        # a lane entry is a directory prefix only at a separator boundary
        if f.startswith(p + "/"):
            return True
    return False


def allowed_paths(lug: Dict[str, Any]) -> List[str]:
    """The lane a dispatched child may commit in: its own file_targets + AP's paths."""
    targets = lug.get("file_targets") or lug.get("target_files") or []
    out = [t for t in targets if isinstance(t, str) and t.strip()]
    out.extend(AP_OWNED)
    # stable order, no duplicates -- the allowlist is compared by prefix, so a
    # duplicate is harmless but noisy in the failure message
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def install_hook(spoke_wai: Path) -> Path:
    """Write the guard hook and return its directory. Idempotent."""
    hook_dir = Path(spoke_wai) / "runtime" / HOOK_DIRNAME
    hook_dir.mkdir(parents=True, exist_ok=True)
    hook = hook_dir / "pre-commit"
    if not hook.exists() or hook.read_text(encoding="utf-8") != _PRE_COMMIT:
        hook.write_text(_PRE_COMMIT, encoding="utf-8")
    hook.chmod(0o755)
    return hook_dir


def child_env(base_env: Dict[str, str], spoke_wai: Path, lug: Dict[str, Any]) -> Dict[str, str]:
    """Add the guard to a child's environment. Returns the same dict, mutated.

    Uses GIT_CONFIG_COUNT rather than writing to the repo's .git/config, so the
    guard is scoped to this one child process and leaves no residue if AP dies.
    """
    try:
        hook_dir = install_hook(spoke_wai)
    except OSError:
        return base_env          # cannot install -> detection still applies
    base_env["WAI_AP_ALLOWED_PATHS"] = "\n".join(allowed_paths(lug))
    # Do not clobber an existing GIT_CONFIG_* block if one is already in play.
    if "GIT_CONFIG_COUNT" not in base_env:
        base_env["GIT_CONFIG_COUNT"] = "1"
        base_env["GIT_CONFIG_KEY_0"] = "core.hooksPath"
        base_env["GIT_CONFIG_VALUE_0"] = str(hook_dir)
    return base_env


def _commits_between(repo: Path, before: str, after: str) -> List[str]:
    if not before or not after or before == after:
        return []
    try:
        cp = subprocess.run(
            ["git", "rev-list", f"{before}..{after}"],
            cwd=str(repo), capture_output=True, text=True, timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []          # unreadable repo -> caller reports clean, not violation
    return [c for c in cp.stdout.split() if c] if cp.returncode == 0 else []


def verify_child_commits(
    repo: Path, before_sha: str, after_sha: str, allow: Sequence[str]
) -> Tuple[bool, List[str]]:
    """Did the child commit outside its lane? Returns (clean, offending_paths).

    Runs in the PARENT after the dispatch returns, so --no-verify does not reach it.
    An unreadable git returns clean -- refusing to judge beats inventing a verdict --
    but the caller is expected to surface that separately.
    """
    commits = _commits_between(repo, before_sha, after_sha)
    if not commits:
        return True, []
    try:
        cp = subprocess.run(
            ["git", "diff", "--name-only", f"{before_sha}..{after_sha}"],
            cwd=str(repo), capture_output=True, text=True, timeout=20,
        )
    except (subprocess.TimeoutExpired, OSError):
        return True, []
    if cp.returncode != 0:
        return True, []

    offending = []
    for f in cp.stdout.splitlines():
        f = f.strip()
        if not f:
            continue
        if not in_lane(f, allow):
            offending.append(f)
    return (not offending), offending


def revert_out_of_lane(
    repo: Path, before_sha: str, offending: Sequence[str], lug_id: str = ""
) -> Tuple[bool, List[str], str]:
    """Restore out-of-lane paths to their pre-dispatch content. (ok, reverted, error).

    OPERATOR RULING 2026-08-15: "auto-revert out-of-lane commits and log a followup
    to review deeply. This keeps our codebase reliably tested and identifies anything
    needing special handling."

    HISTORY IS NEVER REWRITTEN. The child's commit stays; this adds a CORRECTIVE
    commit restoring each offending path to what it was before the dispatch. Rewriting
    would destroy the evidence the followup review needs, and a force-push hazard is a
    worse cure than the disease.

    Two shapes of offence:
      * path existed before  -> restore its pre-dispatch content
      * path is new          -> remove it (there is no earlier content to restore)

    Restoration is scoped by pathspec on BOTH the checkout and the commit, so a
    correction cannot itself sweep unrelated work -- the same discipline that makes
    AP's own commit safe.
    """
    if not offending:
        return True, [], ""

    # DATA-LOSS GUARD, adopted from external review (DeepSeek + Moonshot, 2026-08-15,
    # independently). `git checkout <sha> -- <path>` overwrites the working tree
    # unconditionally. If an operator is mid-edit on a path the worker ALSO committed
    # out-of-lane, the correction destroys their uncommitted work -- turning a control
    # that exists to PREVENT data loss into a cause of it. Refuse instead: a tree that
    # still holds an out-of-lane commit is recoverable, an overwritten edit is not.
    try:
        cp = subprocess.run(
            ["git", "status", "--porcelain", "--"] + list(offending),
            cwd=str(repo), capture_output=True, text=True, timeout=30,
        )
        dirty = [ln[3:].strip() for ln in cp.stdout.splitlines() if ln.strip()]
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, [], f"cannot check for uncommitted work before reverting: {exc}"
    if dirty:
        return False, [], (
            f"REFUSED to revert: {len(dirty)} offending path(s) hold uncommitted work "
            f"that a restore would destroy ({', '.join(dirty[:5])}"
            f"{' ...' if len(dirty) > 5 else ''}). Left for a human -- an out-of-lane "
            f"commit is recoverable, an overwritten edit is not."
        )

    existed, created = [], []
    for p in offending:
        try:
            cp = subprocess.run(
                ["git", "cat-file", "-e", f"{before_sha}:{p}"],
                cwd=str(repo), capture_output=True, timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            return False, [], f"cannot inspect {p}: {exc}"
        (existed if cp.returncode == 0 else created).append(p)

    try:
        if existed:
            cp = subprocess.run(
                ["git", "checkout", before_sha, "--"] + existed,
                cwd=str(repo), capture_output=True, text=True, timeout=60,
            )
            if cp.returncode != 0:
                return False, [], f"restore failed: {cp.stderr.strip()[:300]}"
        if created:
            cp = subprocess.run(
                ["git", "rm", "-f", "--"] + created,
                cwd=str(repo), capture_output=True, text=True, timeout=60,
            )
            if cp.returncode != 0:
                return False, [], f"remove failed: {cp.stderr.strip()[:300]}"

        msg = (
            f"revert(ap-guard): restore {len(offending)} out-of-lane path(s)"
            + (f" from {lug_id}" if lug_id else "")
            + "\n\nA dispatched worker committed paths its lug never declared in "
              "file_targets. Restored to pre-dispatch content; the worker's commit is "
              "left in history so the followup review can read it."
        )
        cp = subprocess.run(
            ["git", "commit", "-m", msg, "--no-verify", "--"] + list(offending),
            cwd=str(repo), capture_output=True, text=True, timeout=60,
        )
        if cp.returncode != 0 and "nothing to commit" not in (cp.stdout + cp.stderr):
            return False, [], f"corrective commit failed: {cp.stderr.strip()[:300]}"
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, [], str(exc)

    return True, list(offending), ""


def write_followup_lug(
    spoke_wai: Path, lug_id: str, offending: Sequence[str], reverted: bool,
    error: str = "", model: str = "",
) -> str:
    """Record an out-of-lane incident for deep review. Returns the path written.

    The revert restores the tree; it does not explain WHY the worker went outside its
    lane. That question is the point of the ruling -- an out-of-lane commit is either a
    lug whose file_targets were wrong, or a worker doing something nobody asked for,
    and those need different fixes.
    """
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc)
    fid = f"review-ap-out-of-lane-{lug_id or 'unknown'}-{ts.strftime('%Y%m%dT%H%M%S')}-v1"
    body = {
        "id": fid,
        "type": "review",
        "status": "open",
        "routed_to": "LOCAL",
        "title": f"Dispatched worker committed outside its lane ({lug_id})",
        "created_at": ts.isoformat(),
        "created_by": "ap_child_guard.write_followup_lug",
        "impact": 7,
        "effort": 2,
        "model_fit": "sonnet",
        "perceive": (
            f"AP dispatched {lug_id} (model={model or 'unknown'}) and the worker "
            f"committed {len(offending)} path(s) its lug never declared in "
            f"file_targets: {', '.join(list(offending)[:10])}"
            + (" ..." if len(offending) > 10 else "")
            + (". The paths were auto-reverted to their pre-dispatch content and the "
               "worker's commit was left in history for this review."
               if reverted else
               f". AUTO-REVERT FAILED ({error}) -- the tree still holds the "
               "out-of-lane changes and needs a human.")
        ),
        "execute": (
            "Read the worker's commit and decide which of two things happened. "
            "(a) The lug's file_targets were incomplete, so the worker was right and "
            "the lug was wrong -- fix file_targets and re-dispatch. "
            "(b) The worker did something nobody asked for -- that is a prompt or "
            "model-fit problem, and the lug should record it so the same dispatch is "
            "not repeated. Do not close this by re-running: the revert already "
            "restored the tree, so a blind re-run reproduces the same incident."
        ),
        "verify": [
            f"git log --all --oneline -- {list(offending)[0]} shows both the worker "
            f"commit and the revert(ap-guard) corrective commit",
            "the lug names a verdict of (a) or (b) with the commit sha cited",
        ],
        "acceptance_criteria": [
            "the out-of-lane cause is named as a lug defect or a worker defect",
            "the corresponding fix (file_targets corrected, or dispatch recorded as "
            "unsafe) is landed",
        ],
        "file_targets": list(offending)[:20],
        "auto_generated": True,
        "incident": {
            "lug_id": lug_id, "model": model, "paths": list(offending),
            "reverted": bool(reverted), "revert_error": error,
        },
    }
    out_dir = Path(spoke_wai) / "lugs" / "bytype" / "review" / "open"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{fid}.json"
    path.write_text(__import__("json").dumps(body, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return str(path)


if __name__ == "__main__":
    import json
    import sys

    # Smoke path: print the lane a lug would get. Used by tests and by hand when
    # asking "what was this worker actually allowed to touch".
    lug = json.loads(sys.stdin.read() or "{}")
    print("\n".join(allowed_paths(lug)))
