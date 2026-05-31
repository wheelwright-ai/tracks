> Fast path: load `wai-closeout-slim.md` first. Load this file only when deep protocol is needed.
### 2. Intent Ceremony Gate

Read `WAI-Spoke/runtime/session-intent.json` if it exists. Map `intent` to ceremony level:

| intent | ceremony |
|--------|----------|
| `closeout` | Minimal |
| `implement` / `refinement` / `teachings` / `explore` | Standard |
| `full` | Full |
| absent / unknown | Standard |

Surface: `[Closeout] Intent at session start: {intent} → ceremony: {level}`

**Minimal** (intent=`closeout`): skip steps 8 (Dogfooding), 9b (Teaching Generation), 9c (Hub Signal Bulletin). Proceed: 3 → 4–5 → 5d → 6 → 7 → 10 → 11.

**Standard** / **Full**: run all steps.

**If intent=`implement`:** after lug archival (step 5), verify at least one lug transitioned `in_progress → completed` this session. If none: surface `Intent was implement but no lugs completed — expected?` and wait for acknowledgment before continuing.

---

**Disruption tracking** — accumulates per-step failures for remediation lug. Initialize before Step 3:

```bash
DISRUPTIONS=()
DISRUPTION_DETAILS=""
```

### 2b. Delta Ceremony Detection

Read `WAI-Spoke/runtime/closeout-fingerprint.json` (if present) to detect re-closeout within the same session. Set `DELTA_CLASS` and skip flags before any step runs.

```bash
python3 << 'PYEOF'
import json, os, subprocess, datetime

fingerprint_path = 'WAI-Spoke/runtime/closeout-fingerprint.json'
session_guard_path = 'WAI-Spoke/runtime/session-guard.json'

# Read current session ID
current_session = None
try:
    current_session = json.load(open(session_guard_path)).get('session_id')
except Exception:
    pass

# Defaults — assume FULL (no fingerprint or cross-session)
DELTA_CLASS = "FULL"
SKIP_VERSION_BUMP = False
SKIP_CHANGELOG = False
SKIP_TEACHINGS = False
SKIP_SKILL_SYNC = False
SKIP_TELEMETRY = False
SKIP_BRIEFS = False

if os.path.exists(fingerprint_path) and current_session:
    fp = json.load(open(fingerprint_path))
    same_session = fp.get('session_id') == current_session
    if same_session:
        SKIP_VERSION_BUMP = True  # always skip on re-closeout within same session
        # Classify delta since last closeout
        last_sha = fp.get('last_closeout_sha', '')
        if last_sha:
            result = subprocess.run(
                ['git', 'diff', '--name-only', last_sha, 'HEAD'],
                capture_output=True, text=True
            )
            changed = [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
            # Classify
            state_only = all(
                f.startswith('WAI-Spoke/') and any(f.endswith(x) for x in ['.json', '.jsonl'])
                for f in changed
            )
            has_py_sh = any(f.endswith(('.py', '.sh')) or 'tools/' in f for f in changed)
            has_docs = any(f.endswith(('.md', '.yaml', '.yml')) for f in changed)
            if not changed or state_only:
                DELTA_CLASS = "MICRO"
                SKIP_CHANGELOG = True
                SKIP_TEACHINGS = True
                SKIP_SKILL_SYNC = True
                SKIP_TELEMETRY = True
                SKIP_BRIEFS = True
            elif has_py_sh:
                DELTA_CLASS = "STANDARD"
                SKIP_CHANGELOG = False
            elif has_docs:
                DELTA_CLASS = "PATCH"
                SKIP_TEACHINGS = True

# Export as env vars for subsequent steps
exports = {
    'DELTA_CLASS': DELTA_CLASS,
    'SKIP_VERSION_BUMP': str(SKIP_VERSION_BUMP).lower(),
    'SKIP_CHANGELOG': str(SKIP_CHANGELOG).lower(),
    'SKIP_TEACHINGS': str(SKIP_TEACHINGS).lower(),
    'SKIP_SKILL_SYNC': str(SKIP_SKILL_SYNC).lower(),
    'SKIP_TELEMETRY': str(SKIP_TELEMETRY).lower(),
    'SKIP_BRIEFS': str(SKIP_BRIEFS).lower(),
}
for k, v in exports.items():
    print(f'export {k}={v}')
print(f'[closeout] Delta class: {DELTA_CLASS} | skip_version_bump={SKIP_VERSION_BUMP}')
PYEOF
```

Evaluate output with `eval $(python3 ... )` or source the exports. For MICRO delta: skip all ceremony steps — jump directly to step 11 (commit + push).

### 3. Incomplete Work Capture

Document unfinished work with enough detail to resume: status, what's done, what remains, blockers, files, continuation instructions. Store in session-summary `incomplete_work` AND `_session_state.next_session_recommendation`.

If a session track exists, also read `open` items from the last 3 track points.

### 4–5. Run Closeout Script

```bash
tools/closeout.sh --modified-by {model_id} --track-path {current_track_path}
```

*Skip version bump if `SKIP_VERSION_BUMP=true` — already done this session. Pass `--skip-version-bump` flag to `closeout.sh`.*

Handles automatically: version bump (unless skipped), `session_count++`, `last_closeout`/`last_modified_at`/`last_modified_by`, lug archival (`in_progress` → `completed` for status==completed lugs), `WAI-LugIndex.jsonl` regen, backlog scoring + `_work_queue` update.

**AI sets `outcome` on each lug before archival** (Fleet Index field — `WAI-Lug-Schema-Spec.md § Fleet Index Fields`):
- `shipped` — delivered as specified, verify steps passed
- `shipped_with_rework` — delivered but required rework beyond original scope
- `abandoned` — closed without delivery
- `superseded` — replaced by another lug; also set `superseded_by: <new_lug_id>`

Add `--dry-run` to preview without writing.

Review the printed summary, then complete the remaining AI-only fields:

**AI completes in WAI-State.json:**
- `_session_state.next_session_recommendation` = what the next session should focus on
- `_session_state.track_path` = current session track path (if not passed via `--track-path`)

**Capability check:** `test -d WAI-Spoke/lugs/bytype && echo BYTYPE_OK || echo FLAT_LUG` — if FLAT_LUG, skip 5b and 5c entirely.

**Disruption capture (step 4–5):** If `tools/closeout.sh` exits non-zero or output contains `ERROR`/`FAIL`:
```bash
DISRUPTIONS+=("closeout.sh")
DISRUPTION_DETAILS+="[STEP 4-5] closeout.sh failed or reported errors\n"
```

---

**WAVE 1 — parallel dispatch** (after closeout.sh completes)

Wave 1 agents write to disjoint files — no conflict risk. Dispatch all three in parallel using the Agent tool, then wait for all before proceeding to Step 6:

- **Agent A:** Step 5b (Adoption Marker Sync)
- **Agent B:** Step 5c (Hub Routing — non-LOCAL lugs only)
- **Agent C:** Step 5d (Changelog Entries)

---

### 5b. Adoption Marker Sync

For each implementation lug with `status = "implemented"`: check `_migration_state.adoption_markers` in extended state. If `adopted = false`, update to `true` with timestamp.

### 5c. Hub Routing (FRAMEWORK / SIGNAL / SPOKE lugs only)

Script handles LOCAL archival. For non-LOCAL lugs, AI routes manually:
- **FRAMEWORK** → completed + hub teachings (Step 9b)
- **SPOKE/{id}** → copy to hub incoming + complete locally

User-alert signals generated this session are handled in Step 9c — write directly to `{hub_path}/WAI-Hub/signals/inbox/`. Do not use `routed_to: "SIGNAL"` (deprecated).

### 5d. Changelog Entries

For each resolved lug, append to `WAI-Spoke/runtime/spoke-changelog.jsonl`. See `wai-closeout-reference.md` for changelog entry format. Framework-internal changes go in CHANGELOG.md, not spoke-changelog.

### 6. Finalize Session Track

Write a final track point as the **terminal entry** — this is the marker wakeup Step 3b uses to detect a clean session. The entry MUST include both `event: "closeout"` and `completed: true`:

```json
{"event": "closeout", "completed": true, "session_id": "{session_id}", "ts": "{ISO-8601}", "phase": "review", "session_number": N}
```

Do NOT delete the track file — it's the permanent session record. A session without this terminal entry will show as INTERRUPTED on next wakeup.

**Ledger terminal entry:** After writing the track.jsonl closeout event, also append a final row to `wai_track_ledger.md` in the session directory:

```
| {n} | {HH:MM UTC} | closeout | Session closed — {N} turns, {lug_count} lugs worked |
```

If the ledger file doesn't exist, skip this step silently — do not create it at closeout. Degraded-mode creation happens at session-start or first turn.

**Session end event (activity instrumentation):** After writing the terminal track entry, emit a `session_end` event:

```python
import subprocess, json

event = {
    "event_type": "session_end",
    "session_kind": "user",
    "wheel_id": "{wheel_id}",
    "session_id": "{session_id}",
    "duration_ms": None,                        # optional: elapsed wall-clock ms
    "outcome": "clean",                         # clean | incomplete | interrupted
    "lug_refs": ["{completed_lug_id}", ...]     # ids of lugs completed this session
}
subprocess.run(["python3", "tools/emit_activity_event.py", json.dumps(event)], check=False)
```

**Track mirroring (activity instrumentation):** After session_end is emitted, mirror the full track to activity_events:

```bash
python3 tools/mirror_track_to_events.py --session-id {session_id}
# Gracefully skipped if SUPABASE_REST unset — events are queued locally.
```

**Track-point `sentiment` field (optional):** Each track point may include `"sentiment": "frustration" | "delight" | null` — set by the agent at the moment of writing the point when the user signal in the turn is strong. Never inferred retroactively. Default `null`. See `wai-track-generate-reference.md` for the full schema.

---

**WAVE 2 — parallel dispatch** (after terminal track entry written)

Wave 2 agents write to disjoint paths — no coordination needed. Dispatch in parallel, wait for all before Step 10 (Skill Sync):

- **Agent A:** Steps 6b + 6c (Cartographer Observation + Assay Write)
- **Agent B:** Step 9 (Outgoing lug delivery)
- **Agent C:** Step 9c (User Signal Delivery)
- **Agent D:** Step 9d (Spoke Registry Update)

> **Note:** Step 9b (Teaching Generation) is NOT in this wave — it depends on Step 8 (Dogfooding) completing first.

---

### 6b. Cartographer Observation

After the session track is finalized, record a structured usage observation so Navigator can build local model performance history.

```bash
python3 tools/write_cartographer_obs.py {track_path}
```

### 6c. Assay Write + Hub Delivery

After the Cartographer observation, write `assay_full.json` for this session and deliver it to hub:navigator.
PII-free: captures only model IDs, provider names, tool names, work_type labels, lug IDs — never message content.

```bash
python3 tools/write_assay.py {track_path}
```

### 7. Documentation Updates

*Skip if `SKIP_CHANGELOG=true` — already done this session.*

Update `CHANGELOG.md` if applicable. Generate descriptive commit message.

### 7b. Docs Sync (When Protocol Changes)

**Trigger:** Session modified skills, protocol files, architecture, or lug schema.

1. Update README.md version string and skill list if changed
2. `framework/docs/llms-full.md` is regenerated automatically by `tools/closeout.sh` Step 6 — verify it updated (check timestamp or line count changed)
3. If no protocol changes: note "Skip 7b: no protocol changes"

### 8. Lug Dogfooding

Validate lugs created/modified this session (excluding session-summary and autosave). For each lug, check:

- PEV fields present? `perceive` points to real files? `execute` has concrete steps? `verify` defines done state? Self-contained?
- **verify testable?** Heuristic: `verify` length > 50 chars AND contains at least one action verb (`run`, `check`, `confirm`, `open`, `call`, `assert`, `create`). If fails: flag `non-testable verify`.
- **verify actually run?** Scan session track (`WAI-Spoke/sessions/{session_id}/track.jsonl`) for a `verification` event that references this lug id. If absent: flag `verify steps not recorded as run`.

For each flagged lug, surface:
```
{lug_id}: {flag} — [Y]es, I ran it / [S]kip / [A]dd verify steps now
```
- `Y` — record a `{"event": "verification", "lug_id": "{id}", "ts": "..."}` entry in track, continue.
- `S` — continue (flag noted in session summary).
- `A` — open inline edit of the lug's `verify` field before closing out.

Present plan, wait for approval, fix gaps. Skip if no actionable lugs.

### 9. Outgoing Delivery

**Primary delivery is immediate** — cross-spoke lugs MUST be delivered at creation time, not here. Step 9 is a safety-net sweep for any that slipped through (interrupted sessions, draft lugs promoted late, edge cases).

Scan `WAI-Spoke/lugs/outgoing/` for any `.json` file where `delivered_at` is absent OR `status` is not `"delivered"`:

1. **Pre-delivery quality check** — lug must have ALL of: non-empty `perceive`, non-empty `execute`, non-empty `verify`, `destination_wheel_id` set and non-empty, `acceptance_criteria` as a non-empty list, `effort_score` (integer), `model_fit` present. For `impl`/`feature`/`task` lugs: `target_files` or `files_to_edit` must be present.
   - Any check fails → log `DELIVERY BLOCKED: {lug_id} — missing: {fields}` and skip. Do not deliver incomplete lugs.
2. Look up `destination_wheel_id` in the hub registry → get spoke `path`.
3. Copy lug to `{target_path}/WAI-Spoke/lugs/incoming/{filename}`.
4. In the local outgoing copy: set `"status": "delivered"`, add `"delivered_at": "{iso_timestamp}"`.
5. Log: `Delivered: {lug_id} → {target_spoke}`.

If hub registry is unreachable: note all undelivered lugs in `next_session_recommendation`. Do not block closeout.

Report: `Outgoing sweep: N delivered, M blocked (quality), K already delivered.`

### 9b. Teaching Generation + Hub Publish

*Skip if `SKIP_TEACHINGS=true` — already done this session.*

**If no teaching-worthy changes:** Skip. Note "No new teachings."

**If changes exist:** Group into families, determine version bump, generate to `teachings/`. Hard gate: each teaching MUST include Prerequisites block, Batch Sequence block, and `safe_to_auto_adopt` flag (default `true`, `false` only for breaking changes). Enforce single-current rule. If hub connected: publish + archive + rewrite index.

**Before promoting to spoke/codebase/templates/:** Run `test-bench/teaching-verify.sh teachings/<file>.teaching` against each new teaching. PASS required before distribution.

**Scope boundary:** Hub publish = file writes to `{hub_path}/` via the filesystem only. Never run `git add`, `git commit`, or any git command inside `{hub_path}`. Hub commits are the hub's own responsibility at its next session.

See `wai-closeout-reference.md` for teaching format details and hub publish layout.

**Disruption capture (step 9b):** If `test-bench/teaching-verify.sh` was run and exited non-zero:
```bash
DISRUPTIONS+=("teaching-verify")
DISRUPTION_DETAILS+="[STEP 9b] teaching-verify.sh: one or more teachings failed verification\n"
```

### 9b-2. Spoke Telemetry Rollup

*Skip if `SKIP_TELEMETRY=true` — already done this session.*

Run spoke-telemetry-closeout skill (templates/commands/spoke-telemetry-closeout.md):
1. Read session track.jsonl → extract model_telemetry entries
2. Aggregate into model_usage[] by model_id
3. Compute dominant_model, work_type_distribution, peak_hour_utc
4. Write rollup to `WAI-Spoke/telemetry/session-{session_id}-rollup.json`
5. Deliver rollup to hub Assessor inbox: `{hub_path}/WAI-Hub/advisors/assessor/inbox/{session_id}-rollup.json`
   If hub unreachable: note in session record, do not block.

Report: "Telemetry rollup written for session {session_id}. Delivered to Assessor."

**Disruption capture (step 9b-2):** If hub delivery failed (unreachable or write error):
```bash
DISRUPTIONS+=("telemetry-delivery")
DISRUPTION_DETAILS+="[STEP 9b-2] Telemetry rollup hub delivery failed — hub may be unreachable\n"
```

### 9c. User Signal Delivery

Deliver any user-alert signals generated during this session to the hub inbox.

**What qualifies:** `type: "signal"` lugs created this session where the user must read and decide — things no agent can resolve without human input. Framework fixes use `task`/`implementation` lugs with `routed_to: "FRAMEWORK"` and are NOT signals.

**If any signal lugs were created during the session:**

```bash
SIGNAL_INBOX="{hub_path}/WAI-Hub/signals/inbox"
mkdir -p "$SIGNAL_INBOX"

# For each signal lug in bytype/signal/ or created inline this session:
cp WAI-Spoke/lugs/bytype/signal/open/{id}.json "$SIGNAL_INBOX/{id}.json"
# Skip if already present (dedup by filename)
```

Or, if the signal was generated inline (not written to bytype/):

```python
import json
from datetime import datetime, timezone

signal = {
    "id": "{id}",
    "type": "signal",
    "title": "{title}",
    "body": "{what the user needs to know}",
    "source_spoke": "{wheel.name from WAI-State.json}",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "status": "open",
    "session_id": "{session_id}"
}
with open("{hub_path}/WAI-Hub/signals/inbox/{id}.json", "w") as f:
    json.dump(signal, f, indent=2)
```

Report: "Delivered N user signal(s) to hub inbox." or "No user signals this session."

**Signal lifecycle:** open (hub inbox) → user reads at session start → user or agent marks `status: "acknowledged"` → archived to `hub/WAI-Hub/signals/processed/`.

**Note:** The old `bytype/signal/undelivered/` → `delivered/` mechanism is retired. Existing legacy signals there are not re-delivered. New user alerts go directly to `hub/WAI-Hub/signals/inbox/`.

### 9d. Spoke Registry Update

Extract from WAI-State.json: `spoke_id`, `name`, `version`, `status`, `one_liner`, `session_count`, `last_closeout`. Write to `{hub_path}/WAI-Hub/registry/incoming/{spoke_id}.json` with `reported_at`. If hub unreachable: note, don't block.

### 10. Skill Sync

*Skip if `SKIP_SKILL_SYNC=true` — already done this session.*

Sync canonical skill source to installed copy so the next session runs current skills:

```bash
\cp templates/commands/*.md .claude/commands/
```

Verify: `diff templates/commands/wai.md .claude/commands/wai.md && diff templates/commands/wai-full.md .claude/commands/wai-full.md` — no output = clean.

**Disruption capture (step 10):** If diff check shows divergence between `templates/commands/` and `.claude/commands/`:
```bash
DISRUPTIONS+=("skill-sync")
DISRUPTION_DETAILS+="[STEP 10] Skill sync diverged — .claude/commands/ out of date with templates/\n"
```

### 10c. Work Queue Update

Update `_work_queue` in `WAI-State.json`:
1. Mark completed lugs in `_work_queue.items` as `status: "done"` (match by id against items moved to `completed/` this session)
2. If `auto_chain` was set this session (user chose [A] at Step 9) and `ready_count > 0`: run this script:

```python
import json, datetime, os

# Load work queue
state = json.load(open('WAI-Spoke/WAI-State.json'))
wq = state.get('_work_queue', {})
items = wq.get('items', [])
completed_this_session = []  # fill from lugs moved to completed/ this session

# Find next ready item (exclude just-completed)
next_item = next(
    (item for item in sorted(items, key=lambda x: x.get('roi', 0), reverse=True)
     if item.get('readiness') == 'ready' and item.get('id') not in completed_this_session),
    None
)

# Write UAT track entry for the completed lug
session_id = state.get('_session_state', {}).get('current_session_id', 'unknown')
track_path = f'WAI-Spoke/sessions/{session_id}/track.jsonl'
if os.path.exists(track_path) and completed_this_session:
    uat_entry = {
        'turn_type': 'uat',
        'lug_id': completed_this_session[0],
        'acceptance': 'accepted',
        'notes': 'Auto-chain mode: lug completed, queuing next item',
        'auto_chained': True,
        'next_item_id': next_item.get('id') if next_item else None,
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()
    }
    with open(track_path, 'a') as f:
        f.write(json.dumps(uat_entry) + '\n')
    print(f'UAT track entry written for {completed_this_session[0]}')

# Write chain_target_lug to wakeup-brief.json
brief_path = 'WAI-Spoke/wakeup-brief.json'
if os.path.exists(brief_path):
    brief = json.load(open(brief_path))
    brief['chain_target_lug'] = next_item if next_item else None
    with open(brief_path, 'w') as f:
        json.dump(brief, f, indent=2)
    if next_item:
        print(f'Auto-chain: next session will load {next_item["id"]} (ROI {next_item.get("roi")})')
    else:
        print('Auto-chain: queue empty -- chain_target_lug set to null')
```

**UAT Track Schema:**
```json
{
  "turn_type": "uat",
  "lug_id": "string -- the completed lug id",
  "acceptance": "accepted|deferred|rejected",
  "notes": "string -- brief description of what was accepted",
  "auto_chained": "boolean -- true if auto_chain mode was active",
  "next_item_id": "string|null -- the id of the next queued lug",
  "timestamp": "ISO-8601"
}
```

If no next ready item after completion: `chain_target_lug` is set to `null` — no error. Offer `[R]eview refinements` or exit to normal closeout.

### 10d. Session Status Update

Before committing, mark the session clean in WAI-State and verify savepoints:

```bash
python3 -c "
import json, datetime, os, glob
state_path = 'WAI-Spoke/WAI-State.json'
ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
with open(state_path, 'r') as f:
    state = json.load(f)

# --- Savepoint clear gate ---
# Closeout closes the arc — a pending savepoint is no longer valid.
# Clear _savepoint unconditionally so next wakeup does not offer stale resume.
savepoint = state.get('_savepoint') or {}
if savepoint.get('status') == 'pending':
    print(f"  Savepoint cleared (arc closed): lug_id={savepoint.get('lug_id')}")
state['_savepoint'] = {}

# --- Session status ---
if '_session_status' not in state:
    state['_session_status'] = {}
state['_session_status']['status'] = 'clean'
state['_session_status']['clean_at'] = ts
state['_session_status']['interrupted_at'] = state['_session_status'].get('interrupted_at')
state['_session_status']['interrupted_session'] = None
with open(state_path, 'w') as f:
    json.dump(state, f, indent=2)
print(f'_session_status.status = clean @ {ts}')
"
```

### DISRUPTION SURFACE

Check before committing. Zero disruptions = zero output, zero overhead.

```bash
if [[ ${#DISRUPTIONS[@]} -gt 0 ]]; then
  REMEDIATION_ID=$(python3 -c "import random,string; print(''.join(random.choices('0123456789abcdef',k=12)))")
  python3 - <<EOF
import json, datetime, os
session_id = open('WAI-Spoke/runtime/session-guard.json').read() if os.path.exists('WAI-Spoke/runtime/session-guard.json') else '{}'
try:
    session_id = json.loads(session_id).get('session_id', 'unknown')
except Exception:
    session_id = 'unknown'
lug = {
    'id': '${REMEDIATION_ID}',
    'type': 'impl',
    'status': 'open',
    'priority': 'P1',
    'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'title': f'Remediate closeout disruptions — session {session_id}',
    'perceive': '${DISRUPTION_DETAILS}'.strip(),
    'execute': ['Review each disruption listed in perceive', 'Run diagnostics on each failed step', 'Re-run closeout when resolved'],
    'verify': ['Re-run /wai-closeout and confirm DISRUPTIONS is empty']
}
os.makedirs('WAI-Spoke/lugs/bytype/impl/open', exist_ok=True)
json.dump(lug, open(f'WAI-Spoke/lugs/bytype/impl/open/${REMEDIATION_ID}.json', 'w'), indent=2)
EOF
  echo "⚠ DISRUPTIONS DETECTED: ${#DISRUPTIONS[@]} failure(s)"
  for d in "${DISRUPTIONS[@]}"; do echo "  - $d"; done
  echo "  Remediation lug: ${REMEDIATION_ID}"
  echo "  You may want to address these before exiting — lug is committed with this session."
fi
```

### 11. Completion Banner + Git Commit + Push

Display the banner **before** committing, then auto-proceed after 10s unless user cancels:

```
-- CLOSEOUT Session-{N} [{track_name}] {timestamp}
|  Accomplished: {bullets}  |  Incomplete: {list or "none"}
|  Version: v{old} -> v{new}  |  Context: {X}%  |  Signals: {N}
|  Ceremony: Full|Standard|Essential|Minimal  |  Commits: {N} files
-- Commit on next tool call — type cancel to abort.
```

Commit proceeds on the next tool call. If user types `cancel`, `stop`, `abort`, `no`, or `wait` (case-insensitive): abort. If user asks a question: answer it inline, then continue — do **not** re-present the banner.

**Pre-commit: concurrent session check**

```bash
# Fetch remote state (no merge)
git fetch origin 2>/dev/null || true

# Check if remote is ahead
REMOTE_AHEAD=$(git rev-list HEAD..origin/main --count 2>/dev/null || echo 0)
if [[ "$REMOTE_AHEAD" -gt 0 ]]; then
    echo "Remote has $REMOTE_AHEAD new commit(s) — pulling before commit to avoid conflict..."
    git pull --rebase origin main
    echo "Rebase complete. Review any conflicts before proceeding."
fi

# Check if WAI-State.json was externally modified since session start
# (another concurrent session already closed out and updated it)
STATE_SHA_NOW=$(git show HEAD:WAI-Spoke/WAI-State.json 2>/dev/null | md5sum | cut -c1-8 || echo "new")
STATE_SHA_SESSION=$(git show "$(cat WAI-Spoke/runtime/session-guard.json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_start_sha","HEAD"))' 2>/dev/null || echo HEAD)":WAI-Spoke/WAI-State.json 2>/dev/null | md5sum | cut -c1-8 || echo "unknown")
if [[ "$STATE_SHA_NOW" != "$STATE_SHA_SESSION" && "$STATE_SHA_SESSION" != "unknown" ]]; then
    echo "WAI-State.json was modified by another session since this session started."
    echo "Review the diff before proceeding:"
    git diff HEAD WAI-Spoke/WAI-State.json 2>/dev/null || true
fi
```

**Classify working tree changes:**

```bash
git status --short
```

- **In-scope:** files explicitly touched this session (from track, lug target_files, or known session artifacts like `WAI-State.json`, session track, runtime logs)
- **Out-of-scope:** everything else (hook event logs, advisor outputs, files from concurrent sessions)

If out-of-scope files exist, append to the commit message: `| also: {file list or count} (hook/advisor artifacts)`

**Pre-commit lug verify gate:**

Check for lugs moved to `completed/` this session that have no `verify` field:

```bash
python3 -c "
import json, glob, os, sys
no_verify = []
for p in glob.glob('WAI-Spoke/lugs/bytype/*/completed/*.json'):
    try:
        lug = json.load(open(p))
        if not lug.get('verify'):
            no_verify.append(lug.get('id', os.path.basename(p)))
    except Exception:
        pass
if no_verify:
    print(f'WARN:{len(no_verify)}:' + ','.join(no_verify))
"
```

If output starts with `WARN:`: append `| ⚠ {N} lug(s) completed without verify steps` to the commit message.

**Pre-commit public sync check:**

```bash
python3 tools/check_public_sync.py
```

If output is not `OK`: run `python3 tools/check_public_sync.py --fix` and include the synced files in the commit. Prevents `shared/codebase/tools/` from drifting behind `tools/`.

```bash
git add -A
git commit -m "WAI Session [N]: [accomplishments] | [version] | also: {out-of-scope summary if any}"
if ! git push origin main; then
    echo "⚠ CRITICAL: git push failed — commit exists locally, remote NOT updated"
    DISRUPTIONS+=("git-push [CRITICAL]")
    DISRUPTION_DETAILS+="[STEP 11 CRITICAL] git push failed — commit exists locally, remote not updated\n"
    echo "Resolve and re-run: git push origin main"
fi
```

**If push still fails after rebase:** merge conflict in WAI-State.json or another file. Surface the conflict, resolve manually (keep both sessions' `session_count` increments by taking the higher value), then push. Do NOT force-push.

**Critical:** `WAI-Spoke/WAI-State.json` listed explicitly first to guarantee staging. If Minimal ceremony, include `(minimal closeout — full deferred)` in message.

---

**Write closeout fingerprint** (immediately after `git push` succeeds):

```bash
python3 -c "
import json, datetime, subprocess, os
session_guard = 'WAI-Spoke/runtime/session-guard.json'
session_id = None
try:
    session_id = json.load(open(session_guard)).get('session_id')
except Exception:
    pass
sha = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
fp = {
    'session_id': session_id,
    'last_closeout_sha': sha,
    'last_closeout_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'steps_completed': ['version_bump', 'changelog', 'teachings', 'skill_sync', 'telemetry', 'briefs']
}
os.makedirs('WAI-Spoke/runtime', exist_ok=True)
with open('WAI-Spoke/runtime/closeout-fingerprint.json', 'w') as f:
    json.dump(fp, f, indent=2)
print(f'Fingerprint written: session={session_id}, sha={sha[:8]}')
"
```

---

**WAVE 3 — background dispatch** (after git push succeeds)

Wave 3 are post-commit decorators — failure is non-blocking; the next session regenerates briefs on demand. Dispatch as background agents (`run_in_background: true`) and proceed immediately to Step 12 verification without waiting:

- **Background Agent A:** Step 11a (GitNexus Maintenance — reindex if needed)
- **Background Agent B:** Step 11b (Generate Ozi Brief)
- **Background Agent C:** Step 11c (Generate Wakeup Brief)

---

**Note:** Push failure handling is integrated into the `git push` block above (explicit `if !` check) — the disruption lug is created and surfaced before step 12 verification.

### 11a. GitNexus Maintenance

Skip this step entirely if `which gitnexus` returns empty (tool not installed).

1. Run: `git diff --name-only HEAD~1 HEAD` — capture the list of files changed in the commit just made.

2. Evaluate reindex need — **YES** if changed files include: new/deleted/renamed `.py`, `.sh`, `.js`, `.ts` files; changes to `tools/` or `templates/` directories; any import/export signature changes. **NO** if only `.jsonl`, `.json` data files, comments, docs, or `CLAUDE.md` changed.

3. If reindex needed: run `gitnexus analyze`. If new directories or `.claude/skills/` paths appear in the changed file list, also run `gitnexus analyze --skills`.

4. Evaluate wiki regen need — **YES** if: new module or feature directory added, major refactor with renamed directories, or new service boundaries. **NO** for routine commits within existing structure.

5. If wiki regen needed: run `gitnexus wiki --force --base-url https://api.anthropic.com/v1 --model claude-sonnet-4-6`. Then run `python3 tools/generate_structure_context.py`. Then commit: `git add StructureContext.md .gitnexus/wiki/ && git commit -m 'chore: refresh gitnexus wiki + StructureContext'`.

6. Append to closeout log: `GitNexus: [reindexed|skipped] | wiki: [regenerated|skipped]`

### 11b. Generate Ozi Brief

*Skip if `SKIP_BRIEFS=true` — already done this session.*

After commit, generate the pre-computed Ozi snapshot for the next wakeup:

```bash
python3 tools/generate_ozi_brief.py
```

### 11c. Generate Wakeup Brief

*Skip if `SKIP_BRIEFS=true` — already done this session.*

Generate the wakeup brief so the next session starts on fast path:

```bash
python3 tools/generate_wakeup_brief.py
```

**Disruption capture (step 11c):** If `generate_wakeup_brief.py` exits non-zero:
```bash
DISRUPTIONS+=("wakeup-brief")
DISRUPTION_DETAILS+="[STEP 11c] generate_wakeup_brief.py failed — next session uses full wakeup path\n"
```

### 11d. Generate Octo Brief (Hub Projects Only)

**Skip if not a hub project.** Detect: `wheel.node_type == "hub"` in WAI-State.json OR `WAI-Hub/` directory exists.

After Ozi brief, generate `WAI-Hub/octo-brief.json` — a pre-computed fleet snapshot.

```bash
python3 -c "
import json, datetime, os, glob

if not os.path.isdir('WAI-Hub'):
    print('Not a hub project — skipping Octo brief.')
    exit(0)

fleet = {'green': 0, 'yellow': 0, 'red': 0, 'red_spoke_names': [], 'yellow_spoke_names': []}
gs_path = 'WAI-Hub/advisors/gardener/scan_state.json'
if os.path.isfile(gs_path):
    gs = json.load(open(gs_path))
    for spoke in gs.get('spokes', {}).values():
        health = spoke.get('health', 'unknown')
        name = spoke.get('name', spoke.get('id', ''))
        if health == 'green': fleet['green'] += 1
        elif health == 'yellow':
            fleet['yellow'] += 1
            fleet['yellow_spoke_names'].append(name)
        else:
            fleet['red'] += 1
            fleet['red_spoke_names'].append(name)

priority = []
sp_path = 'WAI-Hub/advisors/spinner/spoke_spinner.json'
if os.path.isfile(sp_path):
    sp = json.load(open(sp_path))
    ranked = sorted(sp.get('spokes', {}).items(), key=lambda x: x[1].get('urgency', 0), reverse=True)[:5]
    priority = [s[0] for s in ranked]

adv = {'gardener_last_run_at': None, 'spinner_last_scored_at': None, 'cartographer_last_scan_at': None}
if os.path.isfile(gs_path):
    adv['gardener_last_run_at'] = json.load(open(gs_path)).get('last_run_at')
if os.path.isfile(sp_path):
    adv['spinner_last_scored_at'] = json.load(open(sp_path)).get('last_scored_at')
cs_path = 'WAI-Hub/advisors/cartographer/scan_state.json'
if os.path.isfile(cs_path):
    adv['cartologist_last_scan_at'] = json.load(open(cs_path)).get('last_scan_at')

sig = {'undelivered_by_target': {}, 'incoming_count': 0}
for f in glob.glob('WAI-Hub/signals/by-target/*/*.json'):
    target = os.path.basename(os.path.dirname(f))
    sig['undelivered_by_target'][target] = sig['undelivered_by_target'].get(target, 0) + 1
sig['incoming_count'] = len(glob.glob('WAI-Hub/signals/incoming/*.json'))

brief = {
    'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'fleet_snapshot': fleet,
    'priority_order': priority,
    'advisor_state': adv,
    'signal_pipeline': sig,
    'next_triumvirate_run': None
}
os.makedirs('WAI-Hub', exist_ok=True)
with open('WAI-Hub/octo-brief.json', 'w') as f:
    json.dump(brief, f, indent=2)
print('Octo brief written: WAI-Hub/octo-brief.json')
"
```

### 12. Verification

Verify: `git status` (clean), `git log --oneline -1`, `git tag -l | tail -1` (if production).

Print: `-- Session saved. Next wakeup loads exactly where we left off.`

If Minimal: add `Context was critical — full ceremony deferred. Run /wai-closeout next session.`

If the session was launched via a GUI tool (VS Code, Cursor) or directly without `wai-enter.sh`, add:
`If you didn't use wai-enter.sh to launch: run ./wai-exit.sh now to keep the wakeup brief fresh. Without it, non-hook tools (codex, gemini) will read stale queue/signal data next session.`

### 13. Release Tag (Production Releases Only)

Skip if not production. Tag `v$VERSION`, push tag. If tag exists: stop and report conflict.

---

## Automated Closeout Protocol

Applies to Tender and any automated agent that performs work on a spoke without a human in the loop. The ceremony is minimal but must produce the same measurable artifacts as a human session so Surveyor and Gardener see valid events.

### Mandatory (automated runs must always do these)

| Step | What | How |
|---|---|---|
| State update | `WAI-State._session_state.last_closeout` = ISO 8601 timestamp | Python update to WAI-State.json |
| State update | `WAI-State.session_count += 1` | Same write |
| State update | `WAI-State.wheel.last_updated` = same timestamp (if key exists) | Same write |
| Track | Create `WAI-Spoke/sessions/session-{date}-tender-{HHmm}/track.jsonl` | Single-entry JSONL |
| Commit | `git add WAI-Spoke/WAI-State.json WAI-Spoke/sessions/{dir}/` then commit | Message: `chore: tender automated closeout {ts} — s={n} t={n} l={n}` |

### Minimal track entry schema

```json
{
  "ts": "2026-04-16T03:00:00Z",
  "session": "session-20260416-tender-0300",
  "type": "automated-tender",
  "summary": "Tender pass: signals=2, teachings=1, lugs=0",
  "signals_processed": 2,
  "teachings_adopted": 1,
  "lugs_executed": 0
}
```

### Optional (skip in automated runs unless the pass specifically produced them)

- Signal extraction — only if Tender created new signals
- Teaching generation — only if Tender completed a lug that requires one
- Version bump — automated runs do not bump version
- Full session summary — omit; track entry is sufficient

### What automated closeout must NOT do

- Read or modify any file outside the spoke's `WAI-Spoke/` directory and the spoke's own git index
- Include unintended files in git commit (only `WAI-State.json` + session track directory)
- Skip the ceremony when no work was done — state + track must always be written so Surveyor sees the run

---

## Success Criteria

- Quality gates pass (if production)
- Autosave lugs reconciled into session-summary
- Signals extracted (impact >= 8)
- Incomplete work documented
- Version incremented, state updated
- Lug status synced, index regenerated
- Session track finalized
- Lugs dogfooded (if applicable)
- Teachings generated (if applicable)
- Committed and pushed
- Release tag applied (if production)
- **All target_files for completed lugs were verified to exist on disk**
- Disruption remediation lug created and committed (if any failures detected)

---

*Closeout = Save game. Next agent continues the adventure.*
