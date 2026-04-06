#!/bin/bash
#
# WAI Session Hook — thin trigger for wakeup protocol
# Runs BEFORE Claude sees the user's message on first turn.
# Injects directive to run /wai skill. All logic lives in wai.md.
#

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
STATE_FILE="$PROJECT_DIR/WAI-Spoke/WAI-State.json"

# Exit silently if not a WAI project
[[ ! -f "$STATE_FILE" ]] && exit 0

# Session guard uses a runtime file (gitignored) to avoid dirtying WAI-State.json
RUNTIME_DIR="$PROJECT_DIR/WAI-Spoke/runtime"
GUARD_FILE="$RUNTIME_DIR/session-guard.json"
mkdir -p "$RUNTIME_DIR"

# Post-compaction closeout hardening: one-shot injection if compacted flag set
if [[ -f "$GUARD_FILE" ]] && jq -e '.compacted == true' "$GUARD_FILE" > /dev/null 2>&1; then
  TMP=$(mktemp)
  jq 'del(.compacted)' "$GUARD_FILE" > "$TMP" && mv "$TMP" "$GUARD_FILE"
  echo '<wai-post-compact>Context was compacted. Read templates/commands/wai-closeout.md before proceeding with closeout.</wai-post-compact>'
fi

# Read guard state (if exists)
GUARD_SESSION_ID=""
GUARD_COMPLETED="false"
if [[ -f "$GUARD_FILE" ]]; then
  GUARD_SESSION_ID=$(jq -r '.session_id // ""' "$GUARD_FILE" 2>/dev/null || echo "")
  GUARD_COMPLETED=$(jq -r '.protocol_completed // false' "$GUARD_FILE" 2>/dev/null || echo "false")
fi

# Detect new session: compare guard's session_id vs state's last_session_id
LAST_SESSION_ID=$(jq -r '._session_state.last_session_id // ""' "$STATE_FILE" 2>/dev/null || echo "")

# New session if guard is empty or matches the last committed session
if [[ -z "$GUARD_SESSION_ID" || "$GUARD_SESSION_ID" == "$LAST_SESSION_ID" ]]; then
  # Generate a fresh session ID for this session
  NEW_SESSION_ID="session-$(date +%Y%m%d-%H%M)"
  printf '{"session_id":"%s","protocol_completed":false,"started_at":"%s"}\n' \
    "$NEW_SESSION_ID" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$GUARD_FILE"
  GUARD_COMPLETED="false"
fi

# Skip if protocol already ran this session
[[ "$GUARD_COMPLETED" == "true" ]] && exit 0

# Mark protocol as triggered (in runtime file only — WAI-State.json stays clean)
TMP=$(mktemp)
jq '.protocol_completed = true |
    .protocol_last_run = (now | strftime("%Y-%m-%dT%H:%M:%SZ"))' "$GUARD_FILE" > "$TMP" && mv "$TMP" "$GUARD_FILE"

# Inject wakeup directive — agent follows /wai skill (wai.md), no bash script needed
cat << 'EOF'
<wai-session-start>
CRITICAL: This is your first turn in a new session. Before responding to the user:

1. Run your WAI wakeup protocol by following the /wai skill (templates/commands/wai.md).
   Produce the full WAI Point briefing: project identity, active work, context health, next actions.

2. If briefing shows autosave checkpoints (incomplete work from previous session):
   Ask: Resume [task]? (Green Light to resume / Red Light to inspect / skip)

3. If briefing shows pending teachings in seed/ingest/:
   Prioritize review before other work. Follow (deprecated - auto-discovery on wakeup) skill.

4. Then respond to the user's message.

EXCEPTION: If the user's message is a closeout command ("closeout", "/wai-closeout", "/wai-shipit"),
skip the wakeup briefing entirely and proceed directly to closeout. Do NOT say "Wake complete."
</wai-session-start>
EOF

exit 0
