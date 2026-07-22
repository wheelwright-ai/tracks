#!/bin/bash
#
# WAI SessionStart compact/resume injector — lightweight facts + pointer + rules digest.
# Fires on SessionStart source=compact or source=resume.
# Must NOT invoke wakeup-canonical.sh — a compacted session is not a new session;
# lane-registration and the full briefing must not re-run.
#

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
BASE="$PROJECT_DIR/WAI-Harness/spoke/local"
[[ -f "$BASE/WAI-State.json" ]] || BASE="$PROJECT_DIR/WAI-Spoke"
[[ ! -f "$BASE/WAI-State.json" ]] && exit 0

CR_FILE="$BASE/runtime/compact-resume.json"

python3 - "$CR_FILE" "$BASE" <<'PYEOF'
import json, sys
from pathlib import Path

cr_file, base = sys.argv[1], sys.argv[2]

cr = {}
try:
    cr = json.loads(Path(cr_file).read_text())
except Exception:
    pass

session_id       = cr.get('session_id', '')
track_path       = cr.get('lane_track_path', '')
base_val         = cr.get('base', base)
active_initiative = cr.get('active_initiative_id', '')
focus_lock       = cr.get('focus_lock', '')
savepoint_status = cr.get('savepoint_status', '')
in_progress_ids  = cr.get('in_progress_lug_ids', [])
in_progress_total = cr.get('in_progress_total', len(in_progress_ids))

has_data = any([session_id, track_path, active_initiative])

lines = [
    '<wai-compact-resume>',
    'Context compaction occurred — restoring WAI session awareness.',
    '',
]

if has_data:
    if session_id:         lines.append(f'Session:     {session_id}')
    if track_path:         lines.append(f'Track:       {track_path}')
    if base_val:           lines.append(f'BASE:        {base_val}')
    if active_initiative:  lines.append(f'Initiative:  {active_initiative}')
    if focus_lock:         lines.append(f'Focus-lock:  {focus_lock}')
    if savepoint_status:   lines.append(f'Savepoint:   {savepoint_status}')
    if in_progress_ids:
        _shown = len(in_progress_ids)
        _suffix = f'  (showing {_shown} of {in_progress_total})' if in_progress_total > _shown else ''
        lines.append(f'In-progress: {", ".join(in_progress_ids)}{_suffix}')
else:
    lines.append('(compact-resume.json not found — read WAI-State.json to restore session context)')

lines += [
    '',
    'ACTION: Invoke /wai-compact-resume to run the post-compaction recovery protocol.',
    '',
    'Rules digest (active — not cancelled by compaction):',
    '  Complexity gate:  2+ files or 6+ steps -> propose plan, wait for approval',
    '  Basher routing:   .claude* edits -> lug to Basher, not direct',
    '  P10 Autonomy:     pick best action and do it; pause only for destructive ops',
    '  P11 Lug-First:    persistent state -> lugs, never TaskCreate or session notes',
    '  Focus lock:       if set above, work only that initiative until cleared',
    '  Statusline+track: mandatory every turn -- read track-buffer.json before writing',
    '</wai-compact-resume>',
]

ctx = '\n'.join(lines)
print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': ctx}}))
PYEOF

exit 0
