#!/bin/bash
#
# Wheelwright SessionStart Hook
# Automatically briefs the user when Claude Code starts a new session
#

set -e

PROJECT_DIR="${WAI_PROJECT_DIR:-${CODEX_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-.}}}"
STATE_FILE="$PROJECT_DIR/WAI-Spoke/WAI-State.json"

# Exit silently if WAI-Spoke doesn't exist (not a wheel project)
[[ ! -f "$STATE_FILE" ]] && exit 0

# Detect if this is a new session FIRST
LAST_SESSION_ID=$(jq -r '._session_state.last_session_id // ""' "$STATE_FILE")
CURRENT_SESSION_ID=$(jq -r '._session_state.current_session.session_id // ""' "$STATE_FILE" 2>/dev/null || echo "")

# Determine session ID and whether this is new session
if [[ -z "$CURRENT_SESSION_ID" || "$LAST_SESSION_ID" == "$CURRENT_SESSION_ID" ]]; then
  # New session - generate fresh ID and reset protocol flag
  SESSION_ID="$(whoami)-$(date +%Y-%m-%d-%H%M%S)"
  NEW_SESSION=true
  TMP_RESET=$(mktemp)
  jq '._session_state.protocol_completed = false' "$STATE_FILE" > "$TMP_RESET"
  mv "$TMP_RESET" "$STATE_FILE"
else
  # Continuing existing session - keep current ID
  SESSION_ID="$CURRENT_SESSION_ID"
  NEW_SESSION=false
fi

# Check if protocol already completed this session
PROTOCOL_COMPLETED=$(jq -r '._session_state.protocol_completed // false' "$STATE_FILE" 2>/dev/null || echo "false")
if [[ "$PROTOCOL_COMPLETED" == "true" ]]; then
  # Already ran - show brief status instead of full briefing
  PROJECT_NAME=$(jq -r '.wheel.name // "Unknown Project"' "$STATE_FILE")
  TURN_COUNT=$(jq -r '._session_state.current_session.turn_count // 0' "$STATE_FILE")
  echo "✓ WAI Context Active | $PROJECT_NAME | Turn $TURN_COUNT"
  exit 0
fi

# Read project state
PROJECT_NAME=$(jq -r '.wheel.name // "Unknown Project"' "$STATE_FILE")
CURRENT_PHASE=$(jq -r '.context.current_phase // "Unknown Phase"' "$STATE_FILE")
LAST_MODIFIED_BY=$(jq -r '._session_state.last_modified_by // "Unknown"' "$STATE_FILE")
LAST_MODIFIED_AT=$(jq -r '._session_state.last_modified_at // "Unknown"' "$STATE_FILE")

# Get recent high-impact decisions (impact >= 8)
RECENT_DECISIONS=$(jq -r '
  .decisions
  | map(select(.impact >= 8))
  | sort_by(.date)
  | reverse
  | .[0:3]
  | map("- " + .decision + " (impact: " + (.impact|tostring) + ")")
  | join("\n")
' "$STATE_FILE")

# Get next actions
NEXT_ACTIONS=$(jq -r '
  .context.next_actions
  | .[0:5]
  | map("- " + .)
  | join("\n")
' "$STATE_FILE")

# Check for uncommitted changes
cd "$PROJECT_DIR"
UNCOMMITTED_COUNT=$(git status --short 2>/dev/null | wc -l || echo "0")
UNCOMMITTED_FILES=$(git status --short 2>/dev/null | head -10 || echo "")

# Build briefing message
BRIEFING="## 🎡 Wheelwright Context Loaded ✓

**Project:** $PROJECT_NAME
**Last session:** $LAST_MODIFIED_AT by $LAST_MODIFIED_BY
**Current phase:** $CURRENT_PHASE

**Recent changes:**
$RECENT_DECISIONS

**Next actions:**
$NEXT_ACTIONS
"

# Add uncommitted changes warning if present
if [[ $UNCOMMITTED_COUNT -gt 0 ]]; then
  BRIEFING="$BRIEFING

## ⚠️ Uncommitted Changes Detected

I see $UNCOMMITTED_COUNT uncommitted changes from the previous session:
$UNCOMMITTED_FILES

**Recommendation:** These look like work-in-progress from the last session.
Would you like to:
- **Resume previous session** - Continue where we left off
- **Start fresh** - I'll help closeout the previous session first
- **Review changes** - Show me what changed before deciding
"
else
  BRIEFING="$BRIEFING

Working tree clean ✓ - Ready for new work!
"
fi

# Initialize conversation log for new session
CONVERSATION_LOG="$PROJECT_DIR/WAI-Spoke/WAI-Session-Log.jsonl"

# Clear old log if this is a new session
if [[ "$NEW_SESSION" == "true" ]]; then
  rm -f "$CONVERSATION_LOG"
fi

# Write session guard to runtime file (gitignored) — keeps WAI-State.json clean between commits
RUNTIME_DIR="$PROJECT_DIR/WAI-Spoke/runtime"
GUARD_FILE="$RUNTIME_DIR/session-guard.json"
mkdir -p "$RUNTIME_DIR"
printf '{"session_id":"%s","protocol_completed":true,"protocol_last_run":"%s","started_at":"%s"}\n' \
  "$SESSION_ID" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$GUARD_FILE"

# Output briefing to Claude
echo "$BRIEFING"

exit 0
