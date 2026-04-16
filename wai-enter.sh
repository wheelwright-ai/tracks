#!/bin/bash
#
# wai-enter.sh — WAI pre-tool launch wrapper
#
# Runs before the AI tool: generates fresh wakeup brief, optional checks,
# anomaly detection. Guarantees WAKEUP_BRIEF=FRESH on every tool entry.
#
# Usage:
#   ./wai-enter.sh           # launches claude (default)
#   ./wai-enter.sh gemini    # launches gemini
#   ./wai-enter.sh codex     # launches codex
#

PROJECT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

# ── Not a WAI project? Launch tool directly ──────────────────────────────────
if [[ ! -f "$PROJECT_DIR/WAI-Spoke/WAI-State.json" ]]; then
    exec "${1:-claude}"
fi

echo "[wai-enter] Preparing session..."

# ── 1. Generate fresh wakeup brief ──────────────────────────────────────────
if [[ -f "$PROJECT_DIR/tools/generate_wakeup_brief.py" ]]; then
    if python3 "$PROJECT_DIR/tools/generate_wakeup_brief.py"; then
        echo "[wai-enter] Brief: ready"
    else
        echo "[wai-enter] Brief: generation failed — wakeup will use live scan"
    fi
else
    echo "[wai-enter] Brief: generator not found (feature-wai-generate-wakeup-brief-v1 not yet built)"
fi

# ── 2. Refresh stale context feeds in background ────────────────────────────
EXPEDITER_STATE="$PROJECT_DIR/WAI-Spoke/advisors/expediter/scan_state.json"
if [[ -f "$EXPEDITER_STATE" && -f "$PROJECT_DIR/tools/advisor_context_refresh.py" ]]; then
    LAST_RUN=$(python3 -c "
import json
try:
    s = json.load(open('$EXPEDITER_STATE'))
    print(s.get('last_run_at','')[:10])
except:
    print('')
" 2>/dev/null || echo "")
    TODAY=$(date +%Y-%m-%d)
    if [[ -n "$LAST_RUN" && "$LAST_RUN" != "$TODAY" ]]; then
        mkdir -p "$HOME/.claude/logs"
        python3 "$PROJECT_DIR/tools/advisor_context_refresh.py" \
            --quiet --spoke-path "$PROJECT_DIR" \
            >> "$HOME/.claude/logs/context-refresh-$(date +%Y%m%d).log" 2>&1 &
        echo "[wai-enter] Feeds: refreshing in background (last: $LAST_RUN)"
    fi
fi

# ── 3. Run basher doctor audit if available ──────────────────────────────────
if command -v basher >/dev/null 2>&1; then
    BASHER_OUT=$(basher doctor audit 2>&1) || true
    BASHER_EXIT=$?
    if [[ $BASHER_EXIT -ne 0 ]] || echo "$BASHER_OUT" | grep -qiE 'fixed|changed|updated|repaired'; then
        mkdir -p "$PROJECT_DIR/WAI-Spoke/runtime"
        python3 -c "
import json, datetime
result = {
    'run_at': datetime.datetime.now().isoformat(),
    'output': '''$BASHER_OUT'''[:500],
    'exit_code': $BASHER_EXIT,
    'changes_detected': True
}
with open('$PROJECT_DIR/WAI-Spoke/runtime/basher-audit-result.json', 'w') as f:
    json.dump(result, f, indent=2)
" 2>/dev/null || true
        echo "[wai-enter] Basher: config changes detected — see wakeup blurb"
    else
        echo "[wai-enter] Basher: OK"
    fi
fi

# ── 4. Detect anomalies outside WAI-Spoke/ (read-only) ──────────────────────
ANOMALIES=0

# session-* dirs at project root (not inside WAI-Spoke/)
for d in "$PROJECT_DIR"/session-*/; do
    [[ -d "$d" ]] || continue
    NAME=$(basename "$d")
    TS=$(date +%s)
    python3 -c "
import json, datetime
lug = {
    'id': 'signal-pre-wrapper-anomaly-${TS}-v1',
    'type': 'signal',
    'status': 'undelivered',
    'title': 'Anomaly: session dir at project root: $NAME',
    'source': 'pre-wrapper-scan',
    'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'description': 'Found $d outside WAI-Spoke/sessions/. Likely misplaced. Verify and move or delete.'
}
import os; os.makedirs('$PROJECT_DIR/WAI-Spoke/lugs/bytype/signal/undelivered', exist_ok=True)
with open('$PROJECT_DIR/WAI-Spoke/lugs/bytype/signal/undelivered/signal-pre-wrapper-anomaly-${TS}-v1.json', 'w') as f:
    json.dump(lug, f, indent=2)
" 2>/dev/null && ANOMALIES=$((ANOMALIES + 1))
done

# track.jsonl at project root
if [[ -f "$PROJECT_DIR/track.jsonl" ]]; then
    TS=$(date +%s)
    python3 -c "
import json, datetime
lug = {
    'id': 'signal-pre-wrapper-anomaly-${TS}-v1',
    'type': 'signal',
    'status': 'undelivered',
    'title': 'Anomaly: track.jsonl found at project root',
    'source': 'pre-wrapper-scan',
    'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'description': 'Found track.jsonl at $PROJECT_DIR root — should be under WAI-Spoke/sessions/.'
}
import os; os.makedirs('$PROJECT_DIR/WAI-Spoke/lugs/bytype/signal/undelivered', exist_ok=True)
with open('$PROJECT_DIR/WAI-Spoke/lugs/bytype/signal/undelivered/signal-pre-wrapper-anomaly-${TS}-v1.json', 'w') as f:
    json.dump(lug, f, indent=2)
" 2>/dev/null && ANOMALIES=$((ANOMALIES + 1))
fi

[[ $ANOMALIES -gt 0 ]] && echo "[wai-enter] Anomalies: $ANOMALIES signal lug(s) created — handle at wakeup"

# ── 5. Auto-fix inside WAI-Spoke/ only ──────────────────────────────────────
# Ensure runtime/ exists
mkdir -p "$PROJECT_DIR/WAI-Spoke/runtime"

# Fix misplaced session dirs under WAI-Spoke/ (not under sessions/)
for d in "$PROJECT_DIR/WAI-Spoke/session-"*/; do
    [[ -d "$d" ]] || continue
    NAME=$(basename "$d")
    mkdir -p "$PROJECT_DIR/WAI-Spoke/sessions"
    mv "$d" "$PROJECT_DIR/WAI-Spoke/sessions/$NAME" 2>/dev/null \
        && echo "[wai-enter] Fixed: moved $NAME → WAI-Spoke/sessions/"
done

# Fix hook permissions
if [[ -d "$PROJECT_DIR/.claude/hooks" ]]; then
    chmod +x "$PROJECT_DIR/.claude/hooks/"*.sh 2>/dev/null || true
fi

# ── 6. Launch tool ──────────────────────────────────────────────────────────
TOOL="${1:-}"
if [[ -z "$TOOL" ]]; then
    read -r -p "[wai-enter] Tool to launch (claude/gemini/codex): " TOOL
fi

if ! command -v "$TOOL" >/dev/null 2>&1; then
    echo "[wai-enter] ERROR: tool '$TOOL' not found in PATH"
    exit 1
fi

echo "[wai-enter] Launching $TOOL..."
"$TOOL"

# ── 7. Post-exit: regenerate brief for next session ─────────────────────────
if [[ -f "$PROJECT_DIR/wai-exit.sh" ]]; then
    "$PROJECT_DIR/wai-exit.sh"
fi
