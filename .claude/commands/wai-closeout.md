### 3. Incomplete Work Capture

Document unfinished work with enough detail to resume: status, what's done, what remains, blockers, files, continuation instructions. Store in session-summary `incomplete_work` AND `_session_state.next_session_recommendation`.

If a session track exists, also read `open` items from the last 3 track points.

### 4–5. Run Closeout Script

```bash
tools/closeout.sh --modified-by {model_id} --track-path {current_track_path}
```

Handles automatically: version bump, `session_count++`, `last_closeout`/`last_modified_at`/`last_modified_by`, lug archival (`in_progress` → `completed` for status==completed lugs), `WAI-LugIndex.jsonl` regen, backlog scoring + `_work_queue` update.

Add `--dry-run` to preview without writing.

Review the printed summary, then complete the remaining AI-only fields:

**AI completes in WAI-State.json:**
- `_session_state.next_session_recommendation` = what the next session should focus on
- `_session_state.track_path` = current session track path (if not passed via `--track-path`)

**Capability check:** `test -d WAI-Spoke/lugs/bytype && echo BYTYPE_OK || echo FLAT_LUG` — if FLAT_LUG, skip 5b and 5c entirely.

### 5b. Adoption Marker Sync

For each implementation lug with `status = "implemented"`: check `_migration_state.adoption_markers` in extended state. If `adopted = false`, update to `true` with timestamp.

### 5c. Hub Routing (FRAMEWORK / SIGNAL / SPOKE lugs only)

Script handles LOCAL archival. For non-LOCAL lugs, AI routes manually:
- **FRAMEWORK** → completed + hub teachings (Step 9b)
- **SIGNAL** → `bytype/signal/delivered/` + hub bulletin (Step 9c)
- **SPOKE/{id}** → copy to hub incoming + complete locally

Move delivered signals from `undelivered/` to `delivered/`.

### 5d. Changelog Entries

For each resolved lug, append to `WAI-Spoke/runtime/spoke-changelog.jsonl`. See `wai-closeout-reference.md` for changelog entry format. Framework-internal changes go in CHANGELOG.md, not spoke-changelog.

### 6. Finalize Session Track

Write a final track point as the **terminal entry** — this is the marker wakeup Step 3b uses to detect a clean session. The entry MUST include both `event: "closeout"` and `completed: true`:

```json
{"event": "closeout", "completed": true, "session_id": "{session_id}", "ts": "{ISO-8601}", "phase": "review", "session_number": N}
```

Do NOT delete the track file — it's the permanent session record. A session without this terminal entry will show as INTERRUPTED on next wakeup.

### 7. Documentation Updates

Update `CHANGELOG.md` if applicable. Generate descriptive commit message.

### 7b. Docs Sync (When Protocol Changes)

**Trigger:** Session modified skills, protocol files, architecture, or lug schema.

1. Update README.md version string and skill list if changed
2. Regenerate `docs/llm-full.txt` — concatenate source files with `=== FILE: {path} ===` delimiters, target under 200KB
3. If no protocol changes: note "Skip 7b: no protocol changes"

### 8. Lug Dogfooding

Validate lugs created/modified this session (excluding session-summary and autosave). Check: PEV fields present? `perceive` points to real files? `execute` has concrete steps? `verify` defines done state? Self-contained? Present plan, wait for approval, fix gaps. Skip if no actionable lugs.

### 9. Outgoing Delivery

Check `WAI-Spoke/lugs/outgoing/` for queued deliveries. If hub connected: copy to hub incoming. If hub unreachable: note in next_session_recommendation.

### 9b. Teaching Generation + Hub Publish

**If no teaching-worthy changes:** Skip. Note "No new teachings."

**If changes exist:** Group into families, determine version bump, generate to `teachings/`. Hard gate: each teaching MUST include Prerequisites block, Batch Sequence block, and `safe_to_auto_adopt` flag (default `true`, `false` only for breaking changes). Enforce single-current rule. If hub connected: publish + archive + rewrite index.

See `wai-closeout-reference.md` for teaching format details and hub publish layout.

### 9c. Hub Signal Bulletin (Target-Routed)

Deliver signals to `{hub_path}/WAI-Hub/signals/incoming/` with `target` field: `"hub"`, `"framework"`, `"spokes"`, or `"spokes/{id}"`.

Deliver: routed_to=SIGNAL lugs, impact>7 signals, plus backlog sweep of `bytype/signal/undelivered/`. Report: "Delivered N signals (M new, K already present). Targets: X hub, Y framework, Z spokes."

**Signal lifecycle:** arrive -> triage -> incorporate -> teach -> clear. Signals must not accumulate.

### 9d. Spoke Registry Update

Extract from WAI-State.json: `spoke_id`, `name`, `version`, `status`, `one_liner`, `session_count`, `last_closeout`. Write to `{hub_path}/WAI-Hub/registry/incoming/{spoke_id}.json` with `reported_at`. If hub unreachable: note, don't block.

### 10. Autosave Cleanup

Remove autosave checkpoints older than 3 sessions from `WAI-Spoke/.autosave/`. See `wai-closeout-reference.md` for cleanup script.

### 10b. Skill Sync

Sync canonical skill source to installed copy so the next session runs current skills:

```bash
\cp templates/commands/*.md .claude/commands/
```

Verify: `diff templates/commands/wai.md .claude/commands/wai.md && diff templates/commands/wai-full.md .claude/commands/wai-full.md` — no output = clean.

### 10c. Work Queue Update

Update `_work_queue` in `WAI-State.json`:
1. Mark completed lugs in `_work_queue.items` as `status: "done"` (match by id against items moved to `completed/` this session)
2. Run `python3 tools/score_backlog.py --update-state` to refresh readiness and queue_state counts
3. If `auto_chain` is true in session state and `ready_count > 0`: prepare next item for minimal context load (see `wai-reference.md` Minimal Context Load schema)

### 11. Completion Banner + Git Commit + Push

Display the banner **before** committing, then auto-proceed after 10s unless user cancels:

```
-- CLOSEOUT Session-{N} [{track_name}] {timestamp}
|  Accomplished: {bullets}  |  Incomplete: {list or "none"}
|  Version: v{old} -> v{new}  |  Context: {X}%  |  Signals: {N}
|  Ceremony: Full|Standard|Essential|Minimal  |  Commits: {N} files
-- Proceeding in 10s — reply cancel to stop.
```

Wait 10s. If user types `cancel`, `stop`, `abort`, `no`, or `wait` (case-insensitive): abort. On timeout or any other input (including questions): proceed. If user asks a question: answer it inline, then continue — do **not** re-present the banner.

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

```bash
git add -A
git commit -m "WAI Session [N]: [accomplishments] | [version] | also: {out-of-scope summary if any}"
git push origin main
```

**If push still fails after rebase:** merge conflict in WAI-State.json or another file. Surface the conflict, resolve manually (keep both sessions' `session_count` increments by taking the higher value), then push. Do NOT force-push.

**Critical:** `WAI-Spoke/WAI-State.json` listed explicitly first to guarantee staging. If Minimal ceremony, include `(minimal closeout — full deferred)` in message.

### 11b. Generate Ozi Brief

After commit, generate the pre-computed Ozi snapshot for the next wakeup:

```bash
python3 tools/generate_ozi_brief.py
```

### 11c. Generate Wakeup Brief

Generate the wakeup brief so the next session starts on fast path:

```bash
python3 tools/generate_wakeup_brief.py
```

### 11c. Generate Octo Brief (Hub Projects Only)

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
print('Octo brief written: WAI-Hub/octo-brief.json'
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

### 14. Verification

`git status` (clean), `git log --oneline -1`, `git tag -l | tail -1` (if production).

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

---

*Closeout = Save game. Next agent continues the adventure.*