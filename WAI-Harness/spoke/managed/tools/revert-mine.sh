#!/usr/bin/env bash
# revert-mine — the DESTRUCTIVE-side safety net for concurrent sessions.
#
# commit-mine.sh guards the ADD side (`git add -A` sweeping another lane's files).
# This is its symmetric twin for the hole that actually caused data loss
# (basher s260617-231315): a blind `git checkout -- <file>` / `git restore` /
# `git reset --hard` / `git clean -fd` SILENTLY discards another live lane's
# uncommitted hunks. CSRP pillar P3.
#
# Rule: NEVER blind-discard. Snapshot the current dirty state to a recovery ref
# FIRST (recoverable via `git stash apply <ref>` or `git show`), THEN perform the
# revert on only the named paths. If you lose work, it is in refs/recovery/.
#
# Usage:
#   revert-mine -- <path> ...     # snapshot, then `git checkout -- <paths>`
#   revert-mine --reset-hard      # snapshot, then `git reset --hard`
#   revert-mine --clean           # snapshot (incl. untracked), then `git clean -fd`
#   revert-mine --check <path>    # report whether <path> carries uncommitted hunks (no action)
#   revert-mine --list            # list existing recovery refs
set -euo pipefail

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "revert-mine: not in a git repo" >&2; exit 1; }
ts="$(date -u +%Y%m%dT%H%M%SZ)"
lane="$(basename "$REPO")"
recref="refs/recovery/${lane}-${ts}"

snapshot() {
  # git stash create makes a commit object WITHOUT touching the working tree.
  # Capture tracked changes; also note untracked for --clean.
  #
  # FAIL CLOSED, and note WHY this one is the worst of the set: snapshot() is the
  # single safety net for ALL THREE destructive modes (--reset-hard, --clean, and
  # `-- <path>`). The old `2>/dev/null || true` collapsed two states that mean
  # opposite things:
  #
  #   rc=0, empty output  -> tree really is clean. Nothing to save. Proceed.
  #   rc!=0, empty output -> stash create FAILED. Nothing was saved. DO NOT proceed.
  #
  # Both printed "working tree clean — nothing to snapshot" and returned success, so
  # the second one told the operator their work was safe and then destroyed it.
  # Reproduced against the post-fix tree by an independent verifier 2026-08-15:
  # `revert-mine --reset-hard` with a failing stash create printed "working tree
  # clean", exited 0, discarded an uncommitted tracked line, and left refs/recovery/
  # empty. Triggers are ordinary, not contrived -- an unresolved merge ("Cannot save
  # the current index state") or a failing required clean-filter both do it.
  #
  # Keep stderr instead of discarding it: refusing without saying why just moves the
  # dead end one step later.
  local obj rc=0 err
  err="$(mktemp)"
  obj="$(git -C "$REPO" stash create "revert-mine snapshot ${ts}" 2>"$err")" || rc=$?
  if [ "$rc" -ne 0 ]; then
    echo "revert-mine: REFUSING — 'git stash create' failed (rc=${rc}), so NOTHING was" >&2
    echo "  saved to $recref and the destructive step below would be unrecoverable." >&2
    sed 's/^/  git: /' "$err" >&2
    rm -f "$err"
    exit 1
  fi
  rm -f "$err"
  if [ -n "$obj" ]; then
    git -C "$REPO" update-ref "$recref" "$obj"
    echo "revert-mine: snapshot saved -> $recref"
    echo "  recover with:  git stash apply $recref      (or: git show $recref)"
  else
    echo "revert-mine: working tree clean (tracked) — nothing to snapshot."
  fi
}

mode="${1:-}"
case "$mode" in
  --check)
    shift; p="${1:?revert-mine --check <path>}"
    if ! git -C "$REPO" diff --quiet -- "$p" || ! git -C "$REPO" diff --cached --quiet -- "$p"; then
      echo "revert-mine: $p HAS uncommitted hunks — revert via 'revert-mine -- $p' (snapshots first), not raw git checkout."
      exit 3
    fi
    echo "revert-mine: $p is clean."
    ;;
  --list)
    git -C "$REPO" for-each-ref --sort=-creatordate --format='%(refname)  %(creatordate:iso)' refs/recovery/ || echo "(none)"
    ;;
  --reset-hard)
    snapshot; echo "revert-mine: git reset --hard"; git -C "$REPO" reset --hard
    ;;
  --clean)
    # snapshot tracked AND stage untracked into the snapshot so clean is recoverable.
    #
    # FAIL CLOSED. This `add` is the ONLY thing that puts untracked files inside the
    # snapshot, and the `git clean -fd` below deletes untracked files unrecoverably.
    # `|| true` here meant: add fails silently -> snapshot misses the untracked files
    # -> clean destroys them with no recovery ref. The guarantee this line exists to
    # provide was cancelled by its own error handling. Measured 2026-08-15 with a
    # required clean-filter that breaks only `git add`: pre-fix rc=0 (SUCCESS) and the
    # untracked file GONE. Refuse instead.
    if ! git -C "$REPO" add -A -- . >/dev/null 2>&1; then
      echo "revert-mine: REFUSING --clean — could not stage untracked files, so the" >&2
      echo "  snapshot would not contain them and 'git clean -fd' would destroy them." >&2
      echo "  Run 'git -C \"$REPO\" add -A -- .' by hand to see the real error." >&2
      exit 1
    fi
    snapshot
    # A failed reset is not data loss (clean skips staged paths) but it IS a silent
    # wrong outcome: nothing gets cleaned and the operator is told it was.
    if ! git -C "$REPO" reset -q >/dev/null 2>&1; then
      echo "revert-mine: WARNING — unstage failed; files remain staged and 'clean -fd'" >&2
      echo "  will skip them. Snapshot is saved; nothing was destroyed." >&2
    fi
    echo "revert-mine: git clean -fd"; git -C "$REPO" clean -fd
    ;;
  --)
    shift
    [ "$#" -gt 0 ] || { echo "revert-mine: name the path(s) to revert" >&2; exit 2; }
    snapshot
    echo "revert-mine: git checkout -- $*"
    git -C "$REPO" checkout -- "$@"
    ;;
  *)
    echo "revert-mine: usage: revert-mine [-- <path>... | --reset-hard | --clean | --check <path> | --list]" >&2
    exit 2
    ;;
esac
