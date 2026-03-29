#!/bin/bash
#
# WAI PreToolUse Guard — Block destructive commands
# Prevents rm -rf /, force-push, and other dangerous operations.
#

# Read the tool input from stdin
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null)

# Block patterns
if echo "$COMMAND" | grep -qE '^\s*rm\s+-rf\s+/\s*$'; then
  echo "BLOCKED: rm -rf / is never allowed"
  exit 2
fi

if echo "$COMMAND" | grep -qE 'git\s+push\s+--force|git\s+push\s+-f'; then
  echo "BLOCKED: git push --force is not allowed. Use regular push."
  exit 2
fi

exit 0
