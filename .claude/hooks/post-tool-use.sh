#!/bin/bash
#
# WAI PostToolUse Hook — Python syntax check on Write/Edit. Always exits 0 — advisory only.
#
# CIRCLE: edit-feedback (immediate) — complements the Stop-scoped test-gate circle.
# Rebuilt by circle-audit s138 (change-enforcement-surface-reconciliation-s138-v1):
# the former activity-event emission and lug->Supabase sync stages were removed —
# both consumers (spoke/local/db/activity.py, tools/supabase_lug_sync.py) never
# existed on v4 spokes, making the old three-stage hook a PHANTOM circle. If the
# activity/lug-sync circle is rebuilt, add those stages back WITH their consumers
# in the same change, and declare it in circle_audit.py's CIRCLES table.
#

input=$(cat)
tool=$(echo "$input" | jq -r '.tool_name // ""')
[[ "$tool" != "Write" && "$tool" != "Edit" ]] && exit 0

file_path=$(echo "$input" | jq -r '.tool_input.file_path // ""')
[[ -z "$file_path" || ! -f "$file_path" ]] && exit 0

# Observe-only collision recording (change-isolation-is-a-value-curve-...-v1 step 0).
# Records WHICH paths this session touches so the real overlap rate between concurrent
# sessions can be measured before any isolation gate is built on a guess. It gates nothing
# and cannot fail this hook: backgrounded, output discarded, always-true.
_PC="${CLAUDE_PROJECT_DIR:-.}/WAI-Harness/spoke/managed/tools/path_claims.py"
_PC_BASE="${CLAUDE_PROJECT_DIR:-.}/WAI-Harness/spoke/local"
if [[ -f "$_PC" && -d "$_PC_BASE" ]]; then
  # Pass the Claude Code session id so attribution resolves from the LANE REGISTRY rather
  # than from newest-track. This spoke had eight session dirs written in one evening while
  # exactly one lane was live; mtime picked a dead stub.
  _PC_SID=$(echo "$input" | jq -r '.session_id // ""' 2>/dev/null)
  (python3 "$_PC" --base "$_PC_BASE" observe --root "${CLAUDE_PROJECT_DIR:-.}" \
      --cc-session-id "$_PC_SID" >/dev/null 2>&1 &) || true
fi

if [[ "$file_path" == *.py ]]; then
  RESULT=$(python3 -m py_compile "$file_path" 2>&1)
  if [[ $? -ne 0 ]]; then
    echo "<post-tool-warning>"
    echo "Python syntax error in $file_path:"
    echo "$RESULT"
    echo "</post-tool-warning>"
  fi
fi

exit 0
