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
    exec "${1:-claude}" "${@:2}"
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

# ── 5b. Interrupted session recovery prompt ──────────────────────────────────
# Scans last 5 sessions from past 7 days. For the most recent unclosed session,
# prints a formatted recovery block with a paste-ready resume prompt.
_SESSIONS_DIR="$PROJECT_DIR/WAI-Spoke/sessions"
_RUNTIME_PATTERNS="WAI-State\.json|wakeup-brief\.json|ozi-brief\.json|scan_state\.json"

if [[ -d "$_SESSIONS_DIR" ]]; then
  mapfile -t _SESS_LIST < <(ls -1d "$_SESSIONS_DIR"/session-*/ 2>/dev/null | sort -r | head -5)
  for _SESS_PATH in "${_SESS_LIST[@]}"; do
    [[ -d "$_SESS_PATH" ]] || continue
    _SESS_ID=$(basename "$_SESS_PATH")
    _TRACK="$_SESS_PATH/track.jsonl"
    [[ -f "$_TRACK" ]] || continue
    _EVENTS=$(wc -l < "$_TRACK" 2>/dev/null || echo 0)
    [[ "$_EVENTS" -le 1 ]] && continue
    _LAST=$(tail -1 "$_TRACK" 2>/dev/null)
    echo "$_LAST" | grep -qE '"event"\s*:\s*"(closeout|completed)"' && continue
    echo "$_LAST" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('completed') else 1)" 2>/dev/null && continue

    _LAST_ACTION=$(tail -1 "$_TRACK" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    parts = []
    if d.get('event'): parts.append(d['event'])
    if d.get('summary'): parts.append(d['summary'][:80])
    elif d.get('description'): parts.append(d['description'][:80])
    print(' — '.join(parts) if parts else 'unknown')
except: print('unknown')
" 2>/dev/null || echo "unknown")

    _IP_LUGS=$(find "$PROJECT_DIR/WAI-Spoke/lugs/bytype" -path "*/in_progress/*.json" 2>/dev/null | head -1)
    _IP_LUG_STR="none"
    if [[ -n "$_IP_LUGS" ]]; then
      _IP_LUG_STR=$(python3 -c "
import json, os
try:
    d = json.load(open('$_IP_LUGS'))
    print(d.get('id','?') + ' — ' + d.get('title','?')[:60])
except: print(os.path.basename('$_IP_LUGS'))
" 2>/dev/null || echo "$(basename "$_IP_LUGS")")
    fi

    _UNCOMMITTED=$(git -C "$PROJECT_DIR" diff --name-only HEAD 2>/dev/null | grep -vE "($_RUNTIME_PATTERNS)" || true)
    _UNCOMMITTED_COUNT=$(echo "$_UNCOMMITTED" | grep -c . 2>/dev/null || echo 0)
    _FIRST_FILE=$(echo "$_UNCOMMITTED" | head -1)
    if [[ "$_UNCOMMITTED_COUNT" -gt 1 ]]; then
      _CODE_CHANGES="$_FIRST_FILE (+$((_UNCOMMITTED_COUNT - 1)) more)"
    elif [[ "$_UNCOMMITTED_COUNT" -eq 1 ]]; then
      _CODE_CHANGES="$_FIRST_FILE"
    else
      _CODE_CHANGES="none"
    fi

    echo ""
    echo "──────────────────────────────────────────────────────────"
    echo "⚠  Interrupted work — $_SESS_ID"
    echo ""
    echo "  Last action : $_LAST_ACTION"
    echo "  In-progress : $_IP_LUG_STR"
    echo "  Code changes: $_CODE_CHANGES"
    echo ""
    echo "  ── Paste to resume ──────────────────────────────────────"
    printf "  Resume interrupted session %s. Last action: %s.\n" "$_SESS_ID" "$_LAST_ACTION"
    [[ "$_IP_LUG_STR" != "none" ]] && printf "  In-progress: %s.\n" "$_IP_LUG_STR"
    [[ "$_UNCOMMITTED_COUNT" -gt 0 ]] && printf "  %s uncommitted file(s) — verify changes are complete before continuing.\n" "$_UNCOMMITTED_COUNT"
    echo "  ──────────────────────────────────────────────────────────"
    break
  done
fi

# ── 6. Launch tool ──────────────────────────────────────────────────────────
TOOL="${1:-}"
if [[ -z "$TOOL" ]]; then
    read -r -p "[wai-enter] Tool to launch (claude/gemini/codex/uvx): " TOOL
fi

if ! command -v "$TOOL" >/dev/null 2>&1; then
    echo "[wai-enter] ERROR: tool '$TOOL' not found in PATH"
    exit 1
fi

echo "[wai-enter] Launching $TOOL..."
"$TOOL" "${@:2}"

# ── 7. Post-exit: regenerate brief for next session ─────────────────────────
if [[ -f "$PROJECT_DIR/wai-exit.sh" ]]; then
    "$PROJECT_DIR/wai-exit.sh"
fi
