#!/bin/bash
#
# Thin SessionStart wrapper for Wheelwright spokes.
# If the canonical spoke hook exists, delegate to it. Otherwise exit quietly.
#

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
CANONICAL="$PROJECT_DIR/WAI-Spoke/hooks/session-start.sh"

# v4 concurrency: if another live session exists for this spoke, isolate this one in
# a git worktree (worktree_guard handles detection — single-session is zero-cost).
# Presence-guarded: no-op in spokes where worktree_guard.py is not distributed.
[ -f "$PROJECT_DIR/tools/worktree_guard.py" ] && python3 "$PROJECT_DIR/tools/worktree_guard.py" 2>/dev/null

if [[ -x "$CANONICAL" ]]; then
  exec "$CANONICAL"
fi

exit 0
