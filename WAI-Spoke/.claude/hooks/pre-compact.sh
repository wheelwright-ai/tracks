#!/bin/bash
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
STATE_FILE="$PROJECT_DIR/WAI-Spoke/WAI-State.json"
[[ ! -f "$STATE_FILE" ]] && exit 0
TRACK_PATH=$(jq -r '._session_state.track_path // ""' "$STATE_FILE" 2>/dev/null)
TRACK_TURNS=0
[[ -n "$TRACK_PATH" && -f "$PROJECT_DIR/$TRACK_PATH" ]] && TRACK_TURNS=$(wc -l < "$PROJECT_DIR/$TRACK_PATH" 2>/dev/null || echo 0)
ACTIVE_LUGS=$(ls "$PROJECT_DIR"/WAI-Spoke/lugs/bytype/*/open/*.json "$PROJECT_DIR"/WAI-Spoke/lugs/bytype/*/in_progress/*.json 2>/dev/null | wc -l)
cat << COMPACT
<wai-pre-compact>
Context compaction. State preserved:
- Track: $TRACK_PATH ($TRACK_TURNS turns)
- Active lugs: $ACTIVE_LUGS
- State: WAI-Spoke/WAI-State.json
After compaction: Re-read WAI-State.json and recent track entries.
</wai-pre-compact>
COMPACT
exit 0