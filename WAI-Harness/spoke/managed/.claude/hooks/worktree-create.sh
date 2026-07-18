#!/bin/bash
# WorktreeCreate hook (basher) — Level-2 of the worktree partnership.
#
# When Claude Code creates a NATIVE worktree, route it through basher's
# worktree_guard so CC ADOPTS basher's .worktrees/<name> (on a session/<name>
# branch, lane-registered) instead of creating its own under .git/worktrees. Result:
# ONE worktree, basher's lifecycle (reaping + convergence + the CC-activeWorktreeSession
# janitor), and Claude Code's in-session UX — partner, not compete.
#
# Contract (Claude Code docs, verified 2026-07-08): stdin JSON carries
# {worktree_name, worktree_path, cwd, session_id, ...}; the hook is FULLY responsible
# for `git worktree add`; on success it prints the created ABSOLUTE path to stdout and
# exits 0. ANY non-zero exit ABORTS CC's worktree creation entirely — so this hook
# ALWAYS exits 0 with a valid path: basher's when possible, else CC's own default
# (never break worktree creation, even in a non-basher repo).
input=$(cat)
_get(){ echo "$input" | jq -r ".$1 // empty" 2>/dev/null; }
name="$(_get worktree_name)"
cc_path="$(_get worktree_path)"
cwd="$(_get cwd)"
repo="${CLAUDE_PROJECT_DIR:-${cwd:-$PWD}}"
wg="$repo/WAI-Harness/spoke/managed/tools/worktree_guard.py"

emit_fallback(){ # create CC's own default worktree so creation never fails, then return it
  if [ -n "$cc_path" ]; then
    if [ ! -d "$cc_path" ]; then
      git -C "$repo" worktree add "$cc_path" ${name:+-b "worktree-$name"} >/dev/null 2>&1 || true
    fi
    echo "$cc_path"
  fi
  exit 0
}

# Non-basher repo, missing name, or no jq -> don't intercept; let CC have its default.
command -v jq >/dev/null 2>&1 || emit_fallback
[ -n "$name" ] && [ -f "$wg" ] || emit_fallback

# Route through basher: .worktrees/<name> on session/<name>, lane-registered.
wt="$(python3 "$wg" wt-new "$name" --repo "$repo" 2>/dev/null | python3 -c 'import sys,json
try:
    print(json.load(sys.stdin).get("worktree",""))
except Exception:
    print("")' 2>/dev/null)"
if [ -n "$wt" ] && [ -d "$wt" ]; then
  echo "$wt"
  exit 0
fi
emit_fallback
