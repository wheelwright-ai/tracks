#!/bin/bash
#
# PreToolUse Guard (file-write tools) — CSRP cross-worktree write protection.
#
# The Bash guard (pre-tool-guard.sh) fails-closed on shared-main GIT writes, but it exits
# for any non-Bash tool — so a Write/Edit/MultiEdit/NotebookEdit straight into another
# session's `.worktrees/<other>/...` path (or the shared main checkout from an isolated
# lane) was UNGUARDED. That is the one hole in "never overwrite another worktree": a raw
# file write bypasses every git-scoped check. This guard closes it MECHANICALLY.
#
# Rule (fail-safe): resolve the write target's absolute path, then BLOCK when it lands in a
# tree that is not THIS session's:
#   - into `.worktrees/<name>/` where <name> != this lane's worktree  -> sibling lane
#   - from an isolated lane, into the shared main tree (under the repo root, outside
#     .worktrees/)                                                     -> shared main
# Allowed: writes inside this session's own tree, and anything outside the repo family
# (e.g. ~/.claude memory, /tmp scratchpad). Non-file tools and unresolvable paths pass.
# Standing operator directive (Mario 2026-07-13): CSRP is enforced, not chosen.
#
# Stderr + exit 2 blocks the action; exit 0 allows.

input=$(cat)
tool=$(echo "$input" | jq -r '.tool_name // ""')

case "$tool" in
  Write|Edit|MultiEdit|NotebookEdit) ;;
  *) exit 0 ;;
esac

# Target path: Write/Edit/MultiEdit use file_path; NotebookEdit uses notebook_path.
target=$(echo "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // ""')
[ -z "$target" ] && exit 0

_audit() {
  local log="${CLAUDE_PROJECT_DIR:-.}/WAI-Harness/spoke/local/runtime/guard-audit.log"
  mkdir -p "$(dirname "$log")" 2>/dev/null
  printf '%s | %s | %s | %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$(printf '%s' "$target" | cut -c1-120)" "$2" >> "$log" 2>/dev/null || true
}

# Normalize target to an absolute, symlink-free-ish path (parent must exist for realpath;
# fall back to lexical join for not-yet-created files).
case "$target" in
  /*) abs="$target" ;;
  *)  abs="${CLAUDE_PROJECT_DIR:-$PWD}/$target" ;;
esac
absdir=$(cd "$(dirname "$abs")" 2>/dev/null && pwd)
[ -n "$absdir" ] && abs="$absdir/$(basename "$abs")"

cpd="${CLAUDE_PROJECT_DIR:-$PWD}"
# Own worktree name + the repo's main root (strip /.worktrees/<name> if isolated).
case "$cpd" in
  */.worktrees/*)
    main_root="${cpd%/.worktrees/*}"
    own_name="${cpd##*/.worktrees/}"; own_name="${own_name%%/*}"
    isolated=1 ;;
  *)
    main_root="$cpd"; own_name=""; isolated=0 ;;
esac

# Only police writes inside this repo family; anything else (memory, /tmp, other repos) passes.
case "$abs/" in
  "$main_root"/*) ;;
  *) exit 0 ;;
esac

# Allowed: writes inside THIS session's own tree.
case "$abs/" in
  "$cpd"/*) exit 0 ;;
esac

# Into a worktree that is not ours?
case "$abs" in
  "$main_root"/.worktrees/*)
    other="${abs#"$main_root"/.worktrees/}"; other="${other%%/*}"
    if [ "$other" != "$own_name" ]; then
      echo "BLOCKED (CSRP): refusing to write into another session's worktree ($main_root/.worktrees/$other/...)." >&2
      echo "  You are in lane '${own_name:-main}'. Never overwrite another lane's tree — deliver a lug to its incoming/, or make the change in your OWN worktree and let the convergence lead reconcile." >&2
      _audit "XWT_SIBLING_WRITE" "write into sibling worktree '$other' blocked (own='$own_name')"
      exit 2
    fi
    exit 0 ;;
esac

# From an isolated lane, a write to the SHARED MAIN tree (under repo root, outside .worktrees).
if [ "$isolated" = 1 ]; then
  echo "BLOCKED (CSRP): refusing to write the shared main tree ($abs) from isolated lane '$own_name'." >&2
  echo "  Work in your own worktree; the convergence lead merges lanes into main via git, never by direct file writes." >&2
  _audit "XWT_SHARED_MAIN_WRITE" "write to shared main from isolated lane '$own_name' blocked"
  exit 2
fi

exit 0
