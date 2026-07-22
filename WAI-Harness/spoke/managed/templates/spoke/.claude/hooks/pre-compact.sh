#!/bin/bash
#
# WAI PreCompact Hook — State Preservation
# Saves critical context before Claude compacts the conversation.
#

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
# v4-first base (guarded v3 fallback) keyed by WAI-State.json, never a bare dir. Without
# this, a v4-only spoke read a non-existent WAI-Spoke/WAI-State.json (silent no-op) AND
# the flag write below mkdir'd a phantom WAI-Spoke/runtime — recreating the v3 husk.
BASE="$PROJECT_DIR/WAI-Harness/spoke/local"; PC_MODE="v4"
[[ -f "$BASE/WAI-State.json" ]] || { BASE="$PROJECT_DIR/WAI-Spoke"; PC_MODE="v3"; }
STATE_FILE="$BASE/WAI-State.json"

# Exit silently if not a WAI project
[[ ! -f "$STATE_FILE" ]] && exit 0

RUNTIME_DIR="$BASE/runtime"
ERR_LOG="$RUNTIME_DIR/track-errors.log"

# ── W1b: session/lane identity (best-effort; READ-ONLY resolve — never creates a lane;
# lane creation is UserPromptSubmit/SessionStart's job, not PreCompact's). ──────────────
_PC_INPUT=$(timeout 2 cat 2>/dev/null || true)
_PC_SID=$(printf '%s' "$_PC_INPUT" | python3 -c "import json,sys
try: print(json.load(sys.stdin).get('session_id',''))
except Exception: print('')" 2>/dev/null)
_PC_TRANSCRIPT=$(printf '%s' "$_PC_INPUT" | python3 -c "import json,sys
try: print(json.load(sys.stdin).get('transcript_path',''))
except Exception: print('')" 2>/dev/null)
[[ -z "$_PC_SID" && -n "$_PC_TRANSCRIPT" ]] && _PC_SID=$(basename "$_PC_TRANSCRIPT" .jsonl)

LANE_DIR=""; LANE_TRACK=""
_WG="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/worktree_guard.py"
if [[ -n "$_PC_SID" && -f "$_WG" ]]; then
  _PC_LANE_JSON=$(python3 "$_WG" lane-resolve --session "$_PC_SID" --base "$BASE" --no-create 2>/dev/null)
  LANE_DIR=$(printf '%s' "$_PC_LANE_JSON" | python3 -c "import json,sys
try:
    d=json.load(sys.stdin)
    print((d or {}).get('lane_dir',''))
except Exception:
    print('')" 2>/dev/null)
  LANE_TRACK=$(printf '%s' "$_PC_LANE_JSON" | python3 -c "import json,sys
try:
    d=json.load(sys.stdin)
    print((d or {}).get('track_path',''))
except Exception:
    print('')" 2>/dev/null)
fi

# ── W1b (1): defensive flush_buffer.py call BEFORE compaction — best-effort, never
# blocks. Uses the lane's own private buffer/track when a lane is registered; otherwise
# the shared buffer + flush_buffer.py's own legacy track resolution (WAI_TRACK_PATH left
# unset), exactly matching pre-existing single-session behavior. ──────────────────────
_PC_BUF="$RUNTIME_DIR/track-buffer.json"
[[ -n "$LANE_DIR" && -f "$LANE_DIR/track-buffer.json" ]] && _PC_BUF="$LANE_DIR/track-buffer.json"
if [[ -f "$_PC_BUF" ]]; then
  if [[ -n "$LANE_TRACK" ]]; then
    WAI_TRACK_PATH="$LANE_TRACK" python3 "$PROJECT_DIR/.claude/hooks/flush_buffer.py" "$STATE_FILE" "$_PC_BUF" "$PROJECT_DIR" 2>>"$ERR_LOG" \
      || printf '%s pre-compact flush_buffer failed (lane=%s)\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${_PC_SID:-none}" >> "$ERR_LOG" 2>/dev/null
  else
    python3 "$PROJECT_DIR/.claude/hooks/flush_buffer.py" "$STATE_FILE" "$_PC_BUF" "$PROJECT_DIR" 2>>"$ERR_LOG" \
      || printf '%s pre-compact flush_buffer failed (no lane)\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$ERR_LOG" 2>/dev/null
  fi
fi

# ── W1b (2): defensive auto_eject_savepoint.py call BEFORE compaction — best-effort,
# never blocks. Savepoints are already keyed by session id (inherently lane-safe: two
# concurrent sessions never share a savepoint file since ids differ). ─────────────────
_AE="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/auto_eject_savepoint.py"
if [[ -n "$_PC_SID" && -f "$_AE" ]]; then
  python3 "$_AE" --session "$_PC_SID" --root "$PROJECT_DIR" --mode "$PC_MODE" >/dev/null 2>>"$ERR_LOG" \
    || printf '%s pre-compact auto_eject_savepoint failed (session=%s)\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$_PC_SID" >> "$ERR_LOG" 2>/dev/null
fi

TRACK_PATH=$(jq -r '._session_state.track_path // ""' "$STATE_FILE" 2>/dev/null)
TRACK_TURNS=0
if [[ -n "$TRACK_PATH" && -f "$PROJECT_DIR/$TRACK_PATH" ]]; then
  TRACK_TURNS=$(wc -l < "$PROJECT_DIR/$TRACK_PATH" 2>/dev/null || echo 0)
fi

ACTIVE_LUGS=$(ls "$BASE"/lugs/bytype/*/open/*.json "$BASE"/lugs/bytype/*/in_progress/*.json 2>/dev/null | wc -l)

cat << COMPACT
<wai-pre-compact>
Context compaction occurring. Key state preserved:
- Track: $TRACK_PATH ($TRACK_TURNS turns recorded)
- Active lugs: $ACTIVE_LUGS items across bytype/
- State: $STATE_FILE (last session: $(jq -r '._session_state.last_session_id // "unknown"' "$STATE_FILE" 2>/dev/null))
- Next actions: $(jq -r '._session_state.next_session_recommendation // "none"' "$STATE_FILE" 2>/dev/null | head -c 200)

After compaction: Re-read WAI-State.json and recent track entries to rebuild context.
Rules still active: P1-Persist, P2-Verify, P3-Steward, P10-Autonomy, P11-Lug-First.
</wai-pre-compact>
COMPACT

# Write flag so user-prompt-submit.sh re-orients the model after compaction —
# under the RESOLVED base (v4 spoke/local/runtime), never a phantom WAI-Spoke/runtime.
# Always written at the SHARED path (unchanged from pre-W1b behavior) so the existing
# consumer (user-prompt-submit.sh, out of scope for this lug) keeps working unmodified;
# ADDITIONALLY lane-scoped when a lane is registered, per this lug's lane-isolation intent.
mkdir -p "$RUNTIME_DIR"
printf 'true' > "$RUNTIME_DIR/compacted.flag"
if [[ -n "$LANE_DIR" ]]; then
  mkdir -p "$LANE_DIR" 2>/dev/null
  printf 'true' > "$LANE_DIR/compacted.flag" 2>/dev/null
fi

# ── Compaction-proof resume pointer (impl-compact-resume-wiring-v1) ──────────────────
# Persist the facts a compacted session loses (session id, lane track path, active
# initiative, savepoint status, in-progress lugs) so compact-resume-inject.sh can
# restore them on SessionStart source=compact. Best-effort + presence-guarded; a
# failure here NEVER blocks compaction (|| true). Python does the JSON write so free
# text never hits shell encoding. Prefer the lane track, fall back to the shared track.
CR_TRACK="${LANE_TRACK:-$TRACK_PATH}"
python3 - "$STATE_FILE" "$BASE" "$RUNTIME_DIR/compact-resume.json" "${_PC_SID:-}" "${CR_TRACK:-}" 2>>"$ERR_LOG" <<'CRPY' || true
import json, sys, glob, os, datetime
state_file, base, out, sid, track = sys.argv[1:6]
try:
    st = json.loads(open(state_file).read())
except Exception:
    st = {}
sp = st.get('_savepoint', {}) or {}
init = sp.get('initiative_id') \
    or (st.get('_strategic_initiatives', {}) or {}).get('governing_initiative', '') \
    or ''
# Bound the injection: most-recently-touched first, cap the list, keep an honest
# total. A compacted session re-orients on the CURRENT few, not every stale lug.
_paths = glob.glob(os.path.join(base, 'lugs', 'bytype', '*', 'in_progress', '*.json'))
def _mtime(p):
    try: return os.path.getmtime(p)
    except OSError: return 0.0
_paths.sort(key=_mtime, reverse=True)
in_prog_total = len(_paths)
in_prog = [os.path.basename(p)[:-5] for p in _paths[:10]]
rec = {
    'ts': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'session_id': sid,
    'lane_track_path': track,
    'base': base,
    'active_initiative_id': init,
    'focus_lock': sp.get('focus_directive') or '',
    'savepoint_status': sp.get('status') or '',
    'in_progress_lug_ids': in_prog,
    'in_progress_total': in_prog_total,
}
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, 'w').write(json.dumps(rec, indent=2))
CRPY

exit 0
