# WAI Closeout

Save session state so the next agent can pick up where we left off.

---

## Execution Context

- **Nodes:** spoke, hub
- **Paths Required:** spoke_path (current directory with WAI-Spoke/)

---

## Closeout Procedure

**Before beginning:** Ask **Is this a production release? (y/n)**
- **Yes:** Run full closeout + quality gates + git tag `v{version}`
- **No:** Run standard closeout, skip gates and tagging

Read `_session_state.last_closeout` from `WAI-State.json` and store as `old_last_closeout`. Step 5 will overwrite it; Step 9b needs the old value.

### 0. Context Assessment

Check current context usage %. Determine ceremony level:

| Context at closeout | Ceremony level | What to run |
|---|---|---|
| < 60% | **Full** | All steps, full banner, no shortcuts |
| 60–79% | **Standard** | All steps, compact banner, skip verbose doc updates |
| 80–89% | **Essential** | Lug reconciliation → version bump → state update → banner → commit. Skip signal extraction detail, skip session log review. |
| ≥ 90% | **Minimal** | Version bump + state update → one-line banner → commit. Flag in banner: "Context critical — full closeout deferred." |

Announce at the start of closeout: **"Context at X% — running [Full/Standard/Essential/Minimal] ceremony."**

### 0b. Quality Gates (Production Releases Only)

Skip if not a production release.

**0a. File Hygiene:** Scan for AI sprawl (`temp_*`, `*.bak`, `*.tmp`, `debug_*`, `scratch_*`, `old_*`, `*.orig`). Delete temp files, ask about unknowns. Report findings.

**0b. Breaking Changes:** Check for API signature changes, removed functions, config format changes. Document in CHANGELOG.md. Confirm user acknowledges.

**0c. Tests:** Auto-detect and run (`pytest`, `npm test`, `make test`). Non-zero exit = abort.

**0d. Linting:** Auto-detect and run (`ruff`, `eslint`). Non-zero exit = abort.

**0e. Benchmarks:** Detect and run available benchmarks. On regression: offer abort / acknowledge / update baseline.

```bash
# Wheelwright WEI benchmark (preferred)
if [ -f "benchmarks/runner/benchmark_runner.py" ]; then
    python3 benchmarks/runner/benchmark_runner.py small --persist
    python3 benchmarks/runner/benchmark_runner.py medium --persist
    # Regression check
    python3 -c "
import json
lines = [l for l in open('benchmarks/benchmark-results.jsonl') if l.strip()]
if len(lines) >= 2:
    prev, curr = json.loads(lines[-2]), json.loads(lines[-1])
    delta = curr['wei'] - prev['wei']
    print(f'WEI: {prev[\"wei\"]:.1f} -> {curr[\"wei\"]:.1f} ({delta:+.1f}) [{\"REGRESSION\" if delta < -2 else \"OK\"}]')
else:
    print('First run — no baseline to compare')
" 2>/dev/null
elif [ -f "benchmark.py" ]; then
    python3 benchmark.py --profile=all
elif [ -f "package.json" ] && grep -q "benchmark" package.json; then
    npm run benchmark
else
    echo "No benchmarks detected — SKIP"
fi
```

**0f. Falsification:** For every file deleted, renamed, or retired this session — prove it's gone:
```bash
# For each retired/deleted file this session:
find /home/mario/projects -name "{filename}" -not -path "*/_archive/*" -not -path "*/.git/*" 2>/dev/null
# Empty = proven. Any match = not done — fix before committing.
```
For fleet-wide changes: search across ALL spokes (including unregistered), templates, test-bench, demo-wheel, examples. The registry is not the truth — the filesystem is.

Report gate results. Proceed only after user confirms all gates pass or are acknowledged.

### 1. Lug Reconciliation

Scan `WAI-Spoke/lugs/bytype/other/open/` for autosave lugs (`ty="autosave"`, `reconciled=false`). Consolidate into ONE session-summary lug covering: what the session was about, actions taken, files touched, decisions, incomplete work, final state. Mark autosaves `reconciled: true`, `s: "c"`. Write summary to `lugs/bytype/session-summary/{id}.json`.

Session-summary lug fields: `id`, `type: "session-summary"`, `title`, `status: "completed"`, `created_at`, `created_by`, `session_number`, `accomplished[]`, `files_touched[]`, `decisions[]`, `incomplete_work{tasks[], blockers[], next_steps[]}`, `autosaves_reconciled[]`.

### 2. Signal Extraction

Review session for decisions/learnings with **impact >= 8**. Write each as a signal lug to `lugs/bytype/signal/undelivered/{id}.json`. Signal schema: see `wai-lug-schema.md`. Impact scale: 10=direction change, 9=architectural, 8=significant pattern, <8=skip.

### 3. Incomplete Work Capture

Document unfinished work with enough detail to resume: status, what's done, what remains, blockers, files, continuation instructions. Store in session-summary `incomplete_work` AND `_session_state.next_session_recommendation`.

If a session track exists, also read `open` items from the last 3 track points — tracks capture unresolved questions that lug reconciliation may miss.

### 4. Version Increment

Bump `wheel.version` patch: `2.0.7` → `2.0.8`. This versions session state, not a release.

### 5. State Update

Update `WAI-State.json`:
- `_session_state.session_count` += 1
- `_session_state.last_closeout` = now (UTC ISO-8601)
- `_session_state.last_modified_by` = current model
- `_session_state.last_modified_at` = now
- `_session_state.next_session_recommendation` = what to do next
- `_session_state.track_path` = current session track path

If capability adoptions or migrations occurred: update extended state (`WAI-State-extended.json`) migration receipts and adoption markers accordingly.

**Capability check — bytype/ structure:** Before Steps 5b/5c, run:
```bash
test -d WAI-Spoke/lugs/bytype && echo BYTYPE_OK || echo FLAT_LUG
```
If `FLAT_LUG`: skip Steps 5b and 5c entirely. Log: "flat-lug spoke — bytype steps skipped."

### 5b. Adoption Marker Sync

For each implementation lug with `status = "implemented"`: check `_migration_state.adoption_markers` in extended state. If `adopted = false`, update to `true` with timestamp. Log result.

### 5c. Lug Status Sync and Routing-Aware Archival

1. Scan `bytype/*/open/` and `bytype/*/in_progress/` for lugs whose status changed this session
2. For each completed lug, check `routed_to` field:
   - **LOCAL:** Move to `bytype/{type}/completed/` (stays in this spoke)
   - **FRAMEWORK:** Move to `bytype/{type}/completed/` AND copy to hub teachings (Step 9b)
   - **SIGNAL:** Move to `bytype/signal/delivered/` AND copy to hub signal bulletin (Step 9c)
3. Move delivered signals from `undelivered/` to `delivered/` (archive metadata only; actual delivery in Step 9c)
4. Regenerate `WAI-LugIndex.jsonl` — one line per lug: `{id, type, status, title, folder, created_at, routed_to}`
5. Report: "Moved N lugs. Routing: M LOCAL, K FRAMEWORK, J SIGNAL. Index: T entries."

### 6. Finalize Session Track

Write a final track point (phase: `review`). Do NOT delete the track file — it's the permanent session record.

### 7. Documentation Updates

Update `CHANGELOG.md` if applicable. Generate descriptive commit message.

### 7b. Docs Sync (When Protocol Changes)

**Trigger:** After any session that modifies skills, protocol files, architecture, or lug schema.

1. **Update README.md:**
   - Check `wheel.version` in WAI-State.json — update version string if changed
   - If skills were added/removed: update skill list in README
   - If architecture changed: update architecture diagram

2. **Regenerate docs/llm-full.txt:**
   - Concatenate source files: WAI-State.json, wai.md, wai-closeout.md, wai-lug-schema.md, key utilities, CHANGELOG top entries
   - Format: header + `=== FILE: {path} ===` delimiters for each file
   - Target size: under 200KB
   - Purpose: Single-file LLM context loader for external agents

3. **If no protocol changes this session:** Note "Skip 7b: no protocol changes" in session summary.

This step is skippable but must be explicitly noted if skipped.

### 8. Lug Dogfooding

Validate lugs created/modified this session (excluding session-summary and autosave). Check: PEV fields present? `perceive` points to real files? `execute` has concrete steps? `verify` defines done state? Self-contained (no "see above")? Present validation plan to user, wait for approval, fix gaps found. Skip if no actionable lugs were created.

### 9. Outgoing Delivery

Check `WAI-Spoke/lugs/outgoing/` for queued deliveries. If found and hub connected: copy to `{hub_path}/WAI-Spoke/lugs/incoming/`. If hub unreachable: note in next_session_recommendation, don't block.

### 9b. Teaching Generation + Hub Publish

**Conditions:** Teaching-worthy changes exist this session (skill files modified, high-impact signals created since `old_last_closeout`, template/schema changes).

**If no changes:** Skip. Note "No new teachings" in summary.

**If changes exist:**
1. Group changes into teaching families: `{object_type}-{object_name}` (e.g., `skill-wai-closeout`)
2. Determine version bump: major (breaking), minor (new capability), patch (fix/clarification)
3. Generate teaching files to `teachings/{family_key}-v{version}.md.teaching`
4. Each teaching MUST include (hard gate — do not publish without these):
   - What changed and why it matters
   - Migration instructions
   - `safe_to_auto_adopt` flag — **default `true`** for all framework-generated teachings. Only set `false` for schema migrations, file deletions, or config format changes that could break a spoke.
   - `## Prerequisites` block (runnable verify commands, or "None")
   - `## Batch Sequence` block (apply order, depends-on, required-before, parallel-safe)
   Missing either block = teaching is incomplete. Fix before publishing.
5. Enforce single-current rule: archive superseded versions to `teachings/archive/{family_key}/`
6. Signal teachings embed the actual lug JSON verbatim
7. If hub connected: publish to `{hub_path}/teachings_repo/spoke/current/`, archive old versions, rewrite index.json
8. If hub unavailable: keep local, note retry in next_session_recommendation

Teaching format details: see `wai-closeout-reference.md` in this skill's folder.

### 9c. Hub Signal Bulletin (Target-Routed)

Deliver signals to `{hub_path}/WAI-Hub/signals/incoming/` with a `target` field so hub triage can route them.

For each signal lug to deliver, include a `target` field:
- `"hub"` — hub architecture, KB, advisor changes
- `"framework"` — framework skill/template/tool changes
- `"spokes"` — cross-spoke patterns, general learnings
- `"spokes/{id}"` — specific spoke

**What to deliver:**
1. Each lug with `routed_to = "SIGNAL"`: write to `{hub_path}/WAI-Hub/signals/incoming/{id}.json` if not already present
2. Any signal lug with `impact > 7` not already caught by routing
3. **Backlog sweep (always):** All files in `bytype/signal/undelivered/` — drains accumulated backlog

**Signal lifecycle:** Signals delivered here enter the hub triage queue. Hub routes them to `by-target/{target}/`. Target node incorporates and clears to `processed/`. Signals should not accumulate indefinitely — the lifecycle is: arrive → triage → incorporate → teach → clear.

Report: "Delivered N signals to hub (M new, K already present). Targets: X hub, Y framework, Z spokes."

### 10. Autosave Cleanup (Interruption Recovery Hygiene)

Remove autosave checkpoints older than 3 sessions:

```bash
# Get current session count from WAI-State.json
CURRENT_SESSION=$(jq -r '._session_state.session_count' WAI-State.json)
CUTOFF=$((CURRENT_SESSION - 3))

# Remove old autosave files
find WAI-Spoke/.autosave -name "*.json" -exec basename {} \; | while read file; do
    # Extract session metadata from autosave if available
    # If autosave is from session < CUTOFF, delete it
    rm -f "WAI-Spoke/.autosave/$file"
done

echo "✅ Cleaned autosave checkpoints > 3 sessions old"
```

**Why:** Autosaves are crash recovery helpers, not permanent archives. After 3+ sessions, if we haven't resumed from them, they're stale and should be removed. Keeps .autosave/ folder clean.

### 11. Git Commit + Push

Commit and push **immediately** — no user confirmation required. The summary banner displays AFTER, not before.

```bash
git add WAI-Spoke/ [other session files]
git commit -m "WAI Session [N]: [accomplishments] | [version]"
git push origin main
```

If ceremony level is Minimal, include in commit message: `(minimal closeout — full deferred)`

### 12. Verification + Completion Banner

```bash
git status          # Must be clean
git log --oneline -1  # Verify commit
git tag -l | tail -1  # Verify tag (if production release)
```

Then display the visual completion marker:

```
┌─ CLOSEOUT Session-{N} [{track_name}] {timestamp}
│
│  Accomplished: {bullet list}
│  Incomplete: {list or "none"}
│  Version: v{old} → v{new}
│  Context: {X}% at closeout
│  Signals: {N} extracted
│  Ceremony: Full | Standard | Essential | Minimal
│  Commits: {N} files pushed to origin/main
│
└─ Session saved. Next wakeup loads exactly where we left off.
```

If Minimal ceremony:
```
⚠️  Context was critical — full ceremony deferred. Run /wai-closeout next session.
```

### 13. Release Tag (Production Releases Only — skip otherwise)

Skip if not a production release (confirmed in Step 0).

```bash
VERSION=$(jq -r '.wheel.version' WAI-Spoke/WAI-State.json)
git tag "v$VERSION"
git push origin "v$VERSION"
```

If tag already exists: stop and report conflict. Do not force-overwrite.

### 14. Verification

```bash
git status          # Must be clean
git log --oneline -1  # Verify commit
git tag -l | tail -1  # Verify tag (if production release)
```

---

## Success Criteria

- [ ] Quality gates pass (if production release)
- [ ] Autosave lugs reconciled into session-summary
- [ ] Signals extracted (impact >= 8)
- [ ] Incomplete work documented with continuation guidance
- [ ] Version incremented, state updated
- [ ] Lug status synced, index regenerated
- [ ] Session track finalized
- [ ] Lugs dogfooded (if applicable)
- [ ] Teachings generated and published (if applicable)
- [ ] Committed and pushed to origin/main
- [ ] Release tag applied and pushed (if production release)

---

*Closeout = Save game. Next agent continues the adventure.*
