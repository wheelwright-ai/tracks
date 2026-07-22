# WAI Wakeup Protocol
> Fast path: load `wai-slim.md` first. Load this file only when deep protocol is needed.

Execute wakeup to initialize the spoke.

---

### -1. Resolve the data-plane base (harness-mode-aware — resolve lazily)

`{BASE}` below is this spoke's active working base. **Steps 0–2 (banner display from
pre-computed session-init context) genuinely cost zero tool calls — do not resolve `{BASE}`
just to reach them.** The first time any step below actually needs to touch the filesystem
(Step 0.5+, the BRIEF PATH, or FULL PROTOCOL), resolve `{BASE}`/`{TOOLS}` ONCE and substitute
the value into every `{BASE}/...` / `{TOOLS}/...` path below (prose, bash, and Python blocks)
— exactly like the other `{placeholder}` fields in this file (`{session_id}`, `{id}`, ...):

```bash
# Shared preamble (P1: ceremony-lib) — single source of truth for harness-mode resolution.
source WAI-Harness/spoke/managed/shared/ceremony-lib.sh && ceremony_init   # exports $BASE + $TOOLS
```

`{BASE}` resolves to `WAI-Harness/spoke/local` on a v4-only spoke and `WAI-Spoke` on
v3/coexist. `{TOOLS}` resolves to `WAI-Harness/spoke/managed/tools` on a v4-only spoke, not a
top-level `tools/`. Never hardcode `WAI-Harness/spoke/`, and **never `os.makedirs` a `WAI-Harness/spoke/...`
path** — on a v4-only spoke that recreates the phantom root that forces v3 coexist mode
(known deployed-hooks issue). If a step below needs to create a directory under the base,
create it under the resolved `{BASE}` only.

---

## Check: Is Session Data Fresh?

Look for `<wai-session-init>` in context and check if it contains `Wakeup brief: FRESH`.

---

## FAST PATH — 0 tool calls (FRESH brief)

Pre-conditions met: hook pre-computed all data, track entry already written by session-start.sh.

**DO NOT make any tool calls.** Display the briefing immediately.

**Steps:**

**0. Intent check.** Scan `<wai-session-init>` CONTEXT HEALTH for an `Intent:` line.
- If found: extract `SESSION_INTENT` and `SESSION_INTENT_LABEL`. After Step 2 banner, jump to **Step 2b** (intent router). Skip Steps 3 and 4.
  - If `SESSION_INTENT = savepoint`: check `{BASE}/runtime/session-intent.json` for `savepoint_resumed = true`. If true, set `SAVEPOINT_ALREADY_CONFIRMED = true` (no prompt needed — wai-enter.sh already captured the choice).
- If absent: proceed normally through Steps 1–4.

**1. Interrupted session check.** If `Prev session: INTERRUPTED` in session-init CONTEXT HEALTH: note it in the banner as `⚠ Prev session interrupted — recovery prompt shown pre-launch`. No action needed — recovery was handled by wai-enter.sh before launch.

**2. Display banner** using session-init sections:

```
┌─ WAI WAKEUP Session-{N} [{session_name}] {today_date}
│  Project: {name} v{version}               ← STATIC DATA
│  Active: {epics_open} open, {epics_ip} ip | {other_open} other | {signals} signals
│  Queue: {ready} ready | {refinement} refinement     ← Expediter line
│  {If _savepoint.status == "pending": ⚑ Savepoint: [lug_id] | Silo: [silo_label] ({initiative_id}) | Done: [work_done] | Next: [resume_note]}
│  {If savepoint.focus_directive: Focus lock: [focus_directive]}
│  Intent: {intent} — {intent_label}   ← If intent set; otherwise: Vibe: none  |  Context: unknown — run /context
│  {If TEACHINGS New > 0: ⚑ Teachings: N pending (Path A/B) — adopt before work queue}
│  {If incoming_lugs_pending > 0: ⚑ Incoming: N lugs unprocessed — triage before work queue}
│  {If HUB SIGNALS > 0: Hub signals: N framework}
│  {If recommendations valid: Navigator: N profiles current | If stale or null: ⚠ Navigator: recommendations stale}
│  {If TOOL ADVISOR audit due: ⚠ Tool audit due}
│  {If Hook drift in CONTEXT HEALTH: ⚠ Hook drift: N hooks stale (oldest: Xd) — sync recommended}
│  {If context feeds stale: Context feeds: N stale}
│  {If assurance_health: Assurance: trail {trail.checkable_ratio:.0%} checkable{If trail.drifted>0: | ⚠ {trail.drifted} DRIFTED}{If trail.unevidenced_claims>0: | {trail.unevidenced_claims} unevidenced} | canon {If canon.ok: clean|⚠ {canon.drift_count} drift}{If open_assurance_lugs>0: | {open_assurance_lugs} assurance lug(s)}}
│  {If HISTORIAN ADVICE present: Historian: {first bullet}}
│  {Active feedback: top-3 from MEMORY.md feedback entries — see Step 3b}
│  Next: {first item from NEXT ACTIONS}
└─ Ready to work.
```

**2a. Loose-end surface (no-dead-ends).** Surface any work the LAST session stranded so it is not silently lost (initiative-no-dead-ends-v1):

```bash
python3 WAI-Harness/spoke/managed/tools/dead_end_scan.py --root . --json
```

If `clean: false`, add a banner line: `⚠ Carryover: {N} uncommitted, {N} untracked-source, {N} unpushed, {N} stash(es)` and offer to reconcile them (commit / lug / discard-with-reason) before new work. `branches_ahead` → note `↪ {N} session branch(es) unmerged to main — reunify (initiative-fleet-branch-reunification-v1)`. Cheap, read-only; never auto-commits.

**0.5 — Priority Gate (mandatory, runs before intent router and savepoint intercept):**

If a hub base is reachable, OR `TEACH_NEW > 0`, OR `Incoming: N lug(s) pending triage` — execute A → B → C silently, **in that order**, before any other step. Do not present a savepoint prompt or work queue until all complete.

**Order is load-bearing: base adoption (A) is a HARD PREREQUISITE for teaching/patch adoption (B).** A spoke that is behind on its base MUST level up first; patches and teachings are deltas *against the current base* and do not apply to an old base. "Absorb teachings" therefore always forces base adoption first.

**A — Harness base adoption (FIRST — hard gate):**

Compare this spoke's `WAI-State.json._harness.base_version` to the hub's `teachings_repo/spoke/base/index.json` `base_version`.

- **Behind (spoke `base_version` < hub, or `_harness` absent):** run the Base Harness Adoption Kit **once** — read `{hub}/teachings_repo/spoke/base/01-orient.md` → `06-verify.md` in order (the base folder is flat — only the current version lives there; the version is `base/index.json` `base_version`). Greenfield/brownfield branch is idempotent re-assert; emit an `adoption` bolt, set `_harness.base_version` + `base_bolt_id`. A behind spoke levels up by running the kit, **not** by adopting N stale teachings. **Do not proceed to B until base is current** — stale teachings against an old base are skipped, not applied.
- **Current:** continue to B.

One-line report: `Step 0.5A: base {version} current` (or `kit run → base {version}` if leveled up).

**B — Teaching + patch adoption** (when base is current AND TEACH_NEW > 0 or patches pending):

First apply any unadopted entries in the hub `base/teachings/index.json` in order, appending each id to `_harness.patches_adopted` (cap ≤10). **Base cutting is AUTOMATIC** — when the patch set reaches the cap, `base_cut_draft.py auto` cuts a new base version (absorbs the patches, resets the set, bumps `base_version`), so a behind spoke just levels up to the new base via Section A. No manual base-cut reminder. **Teaching lug:** Before processing any teachings, auto-create a tracking lug so closeout can associate modified files with this adoption session:

```python
import json, os, datetime, shutil
from datetime import timezone

guard_path = '{BASE}/runtime/session-guard.json'
try:
    session_id = json.load(open(guard_path)).get('session_id', 'unknown')
except Exception:
    session_id = 'unknown'

today = datetime.datetime.now(timezone.utc).strftime('%Y%m%d')
lug_id = f'teaching-adoption-{today}-{session_id}'

lug = {
    'id': lug_id,
    'type': 'task',
    'title': f'Teaching adoption: apply teachings from hub (session {session_id})',
    'status': 'in_progress',
    'va': 'grind',
    'routed_to': 'LOCAL',
    'model_fit': 'haiku',
    'created_at': datetime.datetime.now(timezone.utc).isoformat(),
    'file_targets': [],
    'done_list': [],
    'perceive': f'Hub delivered teachings to session {session_id}.',
    'execute': 'Apply each teaching per its adoption steps.',
    'verify': 'All teachings moved to processed/. file_targets lists every file modified.',
}

os.makedirs('{BASE}/lugs/bytype/task/in_progress', exist_ok=True)
TEACHING_LUG_PATH = f'{BASE}/lugs/bytype/task/in_progress/{lug_id}.json'
# Idempotent: skip if already created (re-run scenario)
if not os.path.exists(TEACHING_LUG_PATH):
    with open(TEACHING_LUG_PATH, 'w') as f:
        json.dump(lug, f, indent=2)
    print(f'[teaching-lug] Created tracking lug: {lug_id}')
else:
    lug = json.load(open(TEACHING_LUG_PATH))
    print(f'[teaching-lug] Resuming existing tracking lug: {lug_id}')
```

Store `TEACHING_LUG_PATH` and `lug_id` for use in subsequent steps.

Then, for each unadopted teaching listed in session-init TEACHINGS:
1. Read the teaching file from the hub at `{hub_path}/teachings_repo/spoke/current/` or `cross_spoke/current/` (or `framework/current/` if not found in the typed dirs — **deprecated legacy fallback**, pre-typed-dirs; keep reading it for old unmigrated hubs, but do not write NEW teachings there).
2. Check `safe_to_auto_adopt`:
   - **`true` → silent apply:** Read `## Adoption Steps`. Apply changes inline (Write/Edit). Run `## Verification`. If PASS: `\cp` file to `{BASE}/seed/ingest/processed/{filename}`. Write track event `{"event":"teaching_adopted","teaching":"{name}","ts":"..."}`. Update tracking lug: append `{name}` to `done_list`, append all files modified during adoption to `file_targets` (read from the teaching's `## Files Modified` section or detect via `git diff --name-only`). If FAIL: write notation lug `notation-teaching-failed-{slug}` with error; still move to processed/ (won't re-fire next session).
   - **`false` → silent defer:** Write notation lug `{BASE}/lugs/bytype/notation/deferred/notation-teaching-review-{slug}-v1.json` (title + "requires manual review"). `\cp` teaching file to `{BASE}/seed/ingest/processed/{filename}` (won't re-fire). Write track event `{"event":"teaching_deferred","teaching":"{name}","ts":"..."}`. The notation lug surfaces in the work queue — no session-start interruption.

Both paths move the file to `processed/` immediately so the next session doesn't re-detect.
One-line report: `Step 0.5B: N patch(es) applied, N adopted, M deferred to work queue.`

**Complete teaching lug:** After all teachings are processed, move the tracking lug to completed:

```python
import json, os, shutil, datetime
from datetime import timezone

if os.path.exists(TEACHING_LUG_PATH):
    lug = json.load(open(TEACHING_LUG_PATH))
    lug['status'] = 'completed'
    lug['completed_at'] = datetime.datetime.now(timezone.utc).isoformat()
    # Deduplicate file_targets
    lug['file_targets'] = sorted(set(lug.get('file_targets', [])))
    with open(TEACHING_LUG_PATH, 'w') as f:
        json.dump(lug, f, indent=2)
    os.makedirs('{BASE}/lugs/bytype/task/completed', exist_ok=True)
    dest = TEACHING_LUG_PATH.replace('/in_progress/', '/completed/')
    shutil.move(TEACHING_LUG_PATH, dest)
    print(f'[teaching-lug] Completed: {lug_id} → {dest}')
    print(f'[teaching-lug] file_targets: {lug["file_targets"]}')
    print(f'[teaching-lug] done_list: {lug["done_list"]}')
```

**C — Incoming lug triage** (when `Incoming: N lug(s)` shown):

For each `.json` file in `{BASE}/lugs/incoming/` (skip `processed/` and `completed/` subdirs):
1. Read the lug. Validate: `type`, `routed_to`, non-empty `perceive`/`execute`/`verify`.
2. Valid → `\cp` to `{BASE}/lugs/bytype/{type}/open/{id}.json`. Invalid/incomplete → write notation lug describing the gap instead.
3. Move original to `{BASE}/lugs/incoming/processed/{filename}`.

One-line report: `Step 0.5C: N lugs triaged to bytype/.`

**Proceed to Step 2b/2c only after 0.5 completes (A → B → C).**

**2.5 — Upgrade Report Intake (runs after 0.5C, before intent router):**

Check `{BASE}/lugs/bytype/upgrade-report/open/` for any unprocessed reports:

```python
import glob
reports = glob.glob('{BASE}/lugs/bytype/upgrade-report/open/*.json')
```

If any found, invoke `wai-upgrade-report-intake` for each — read Steps 1–5 of that skill inline for each report file, passing its path as `report_path`. Collect `improvement_count` and `bug_count` across all reports processed. After all reports are done, surface the count in the briefing:

```
Step 2.5: N upgrade report(s) processed → M improvement lug(s) opened
```

If `outcome=fail` on any report, also surface: `⚠ N adoption failure(s) — bug lug(s) opened`.

If no upgrade-report lugs exist in open/, skip this step silently.

---

**2b. Intent router** (skip entirely if SESSION_INTENT absent — proceed to Step 3):

| Intent | Max tools | Action |
|--------|-----------|--------|
| `savepoint` | 3 | **If `SAVEPOINT_ALREADY_CONFIRMED = true`:** skip prompt — display `⚑ Savepoint confirmed at session start — continuing {lug_id}`, then read WAI-State.json `_savepoint` object (check `status=pending`) + lug file + append track, set `_savepoint.status = "resumed"`, display `Done: {work_done} | Next: {resume_note}`. If savepoint has `focus_directive`, display it and set active initiative to `initiative_id`. **If false:** show `[C]ontinue savepoint / [F]ull wakeup?` — on C: same auto-proceed; on F: clear `_savepoint = {}`, fall through to FULL PROTOCOL. **Initiative focus lock:** if the claimed savepoint has `initiative_id` set, the resuming agent MUST stay on that initiative for the session. Any item discovered outside the active silo should be recorded as a notation lug (`type: notation, status: deferred, deferred_from_initiative: {initiative_id}`) and set aside — do not act on it. |
| `implement` | 1 | Read WAI-State.json. Display top-3 ready lugs by ROI. |
| `refinement` | 1 | Read WAI-State.json. Display needs_refinement items. |
| `teachings` | 1 | List `{BASE}/seed/ingest/` teaching dir. Display pending count. |
| `explore` | — | Skip router. Proceed to Steps 3+4 normally. |
| `closeout` | 0 | Display closeout reminder. Invoke `/wai-closeout`. |
| `full` | — | If `_savepoint.status == "pending"`: clear `_savepoint = {}`. Fall through to FULL PROTOCOL. |

After routing, **do not ask for vibe**. Proceed directly to work.

**2c. Savepoint intercept** (only when `SESSION_INTENT` is absent — skip if already handled by Step 2b):

If `CONTEXT HEALTH` in session-init contains a line beginning with `Savepoint: PENDING`:
- Extract `lug_id` and `resume_note` from `Savepoint: PENDING [lug_id] — resume_note`.
- Display:

```
⚑ Savepoint detected: [lug-id]
  Done: [work_done]
  Next: [resume_note]
  [C]ontinue (load lug only ~5k tokens) / [F]ull wakeup
```

If user chooses **C**:
1. Read the savepoint lug JSON only (1 tool call) — use `lug_id` from `_savepoint` (if non-null)
2. Read last 2 track entries from current `track_path` (1 tool call)
3. Write `WAI-State.json`: set `_savepoint.status = "resumed"` (1 write)
4. Display: `Continuing [lug-id]. Context: ~5k tokens. Done: [work_done] | Next: [resume_note]`
5. Begin work — skip Steps 3 and 4 entirely

If user chooses **F**:
1. Write `WAI-State.json`: clear `_savepoint = {}`
2. Continue normally to Step 3

**3. Ask:** `Vibe? (build / fix / think / grind / ship / refine) [skip]`
**After user responds:** Write chosen vibe (or `null` if skipped) to `WAI-State.json._session_state.current_vibe`. Example: `{"event": "vibe_set", "vibe": "build", "ts": "..."}`

**3a. Session start event (activity instrumentation):** After vibe is set, emit a `session_start` activity event:

```python
import subprocess, json

try:
    session_id = json.load(open('{BASE}/runtime/session-guard.json')).get('session_id', 'unknown')
except Exception:
    session_id = 'unknown'

event = {
    "event_type": "session_start",
    "session_kind": "user",          # or "autonomous" for cron/gardener sessions
    "session_id": session_id,
    "metadata": {"vibe": vibe}       # vibe from step 3
}
# wheel_id is auto-resolved by emit_activity_event.py from WAI-State.json / $WHEEL_ID — do not pass it.
subprocess.run(["python3", "{TOOLS}/emit_activity_event.py", json.dumps(event)], check=False)
# Gracefully skipped if {TOOLS}/emit_activity_event.py absent or SUPABASE_REST unset.
```

**3b. Active Feedback Surface:** Scan the `MEMORY.md` already loaded in context. Find all entries of type `feedback`. Pick the top 3 by most-recently-updated or most frequently-triggered. Output one compact line:

```
Active feedback (N): [rule-1 short label] | [rule-2 short label] | [rule-3 short label]
```

This line closes the apply gap — feedback entries are loaded at wakeup AND explicitly surfaced so the agent acknowledges them before starting work. If fewer than 3 feedback entries exist, show all of them. If MEMORY.md has no feedback entries, skip this line silently.

**3c. Initiative Prompt (soft, skippable):** After vibe prompt, ask once: _"Which initiative are you advancing this session? (or skip for freeform)"_ Present up to 3 options drawn from `{BASE}/initiatives/bytype/initiative/{approved,active,measuring}/*.json` — priority ordered by `focus_lock=true` first, then `impact_rank` ascending. If the user picks one, write `WAI-State.json._session_state.active_initiative_id = <slug>`. If skipped or no initiatives exist, set `active_initiative_id: null`. This choice is used at closeout (Step 5b) to group completed lugs into a bolt. If `{BASE}/wakeup-brief.json` contains a `continuation_menu` field, surface those open initiatives + pending savepoints as ranked options **before** any new-initiative path — finish-before-start is the default.

**3c.1 — Continuation Menu (BASHER command surface — finish-before-start, surfaced FIRST):** Before the soft prompt above, if the wakeup brief carries a `continuation_menu` (computed by `generate_wakeup_brief.py` → `build_continuation_menu`: `{initiatives:[…top 3, sorted focus_lock then impact_rank…], pending_savepoints:[…]}`), DISPLAY it as the first option set so resumable work is claimed before anything new is started:

```
▸ Continue where you left off  (finish-before-start)
  {each pending_savepoint}  ⚑ Resume savepoint: {lug_id} — {resume_note}
  {each initiative, top 3}   ◴ {label}  [{state}{· focus-locked if focus_lock}]  impact {impact_rank}
  [N] new / freeform
```

On the user's pick:
- **Savepoint** → resume via the `savepoint` intent path (read the lug, set `_savepoint.status = "resumed"`, adopt its `initiative_id` as the focus lock).
- **Initiative** → claim it: run `/wai-initiative pin <id>` (→ the resolved `initiative_nav.py pin <id>`, which sets the focus lock) and write `WAI-State.json._session_state.active_initiative_id = <id>`. The agent MUST then stay on that initiative for the session — out-of-silo items become `notation`/`deferred` lugs (same focus-lock rule as a resumed savepoint).
- **[N] new / freeform** → fall through to the soft prompt (3c).

Engine note: the durable focus-lock write is performed by `initiative_nav.py pin` (`implement-initiative-nav-lifecycle-v1`, Phase 1). The pin shellout is guarded — `/wai-initiative` resolves the engine path (`managed/tools/` then `hub/local/scripts/`) and skips silently if absent.

**4. Work Queue Interactive Mode:** After vibe prompt, if `_work_queue.items` has `>=1` ready item, display top-3 by weighted ROI (initiative impact × lug ROI).

Extracted to a tested tool (impl-wakeup-v4-modernization-v1, per the `classify_delta_ceremony.py`
precedent) — the inline block used to hardcode `WAI-Harness/spoke/...`, which silently no-op'd on
v4-only spokes. Run and print its output verbatim (empty output = stay silent, same as before):

```bash
python3 {TOOLS}/wakeup_lib.py work-queue --base {BASE}
```

**[W] Lug gate:** Before starting work on the selected item, confirm the lug has `perceive`, `execute`, and `verify` (or `acceptance_criteria`) sections. If `verify` is absent: surface `⚠ Lug {id} has no verify steps — [A]dd now / [S]kip gate`. Do not silently start work on an unverifiable lug.

**[P] Parallel dispatch:** Call `python3 {TOOLS}/batch_planner.py --json`, present the batch plan, invoke `/wai-apply-all`. See `wai-apply-all.md` for the full dispatch orchestration.

**4b. Model Intelligence (conditional — suppressed entirely if no data):**

If `{BASE}/assessor-matrix.json` exists, load it and display after the Work Queue. Render only when the top queue item has a matching recommendation. Extracted to the same tested tool as Step 4 above:

```bash
python3 {TOOLS}/wakeup_lib.py model-intelligence --base {BASE}
```

Suppression rules: each line renders independently. If a field is null/unavailable, that
line is omitted. If `assessor-matrix.json` does not exist, or carries no recommendations,
the tool prints nothing. Never prints `null`, `[]`, or `{}`. Full behavior (and the ported
logic) lives in `wakeup_lib.py`'s `model_intelligence_lines()` docstring/tests — this doc no
longer inlines a shadow copy that could drift from the executable tool.

Done. Zero tool calls when nothing above triggered a tool call (nothing pending, no queue,
no matrix data); each conditional step above costs exactly the one call it documents.

---

## BRIEF PATH — 1 tool call (no session-init, brief exists)

Pre-conditions: No `<wai-session-init>` in context AND `{BASE}/wakeup-brief.json` exists (resolve `{BASE}`/`{TOOLS}` per Step -1 before this path runs any file I/O).

**Steps:**

1. Read `{BASE}/wakeup-brief.json` (1 tool call). Also read `{BASE}/advisors/navigator/recommendations-current.json` and `{BASE}/advisors/navigator/catalog-cache.json` if present (local files, silent skip if absent). For profile selection in brief-path, default to `coding_high` (no lug-type breakdown available at this step).
2. Display banner:

```
┌─ WAI WAKEUP [brief-path] {today_date}
│  Project: v{spoke_version}
│  Open lugs: {open_lug_count} | Queue: {ready_count} ready | {needs_refinement_count} refinement
│  Context: unknown — run /context  |  Vibe: none
│  {If teachings_pending > 0: ⚑ Teachings: N pending — adopt before work queue}
│  {If incoming_lugs_pending > 0: ⚑ Incoming: N lugs unprocessed — triage before work queue}
│  {If hub_signals_pending > 0: Hub signals: N pending}
│  {If lug_staleness.violations_count > 0: ⚠ Lug staleness: N SLO violation(s), oldest {oldest_violation.id} at {oldest_violation.age_hours}h (SLO {oldest_violation.slo_hours}h){If lug_staleness.stale_report:  — report itself is {report_age_hours}h old, may be stale}}
│  {If recommendations exist: Navigator: matrix {generated_at_date} ✓  (or ⚠ stale {age}h if valid_through <= now)}
│  {default_mode: Available: {best_model_id} ({profile_id}, score={score}) [{provider}] [+ N others — configure API keys to unlock]}
│  {embedded_ai_mode (top ready lug tagged ai-integration/embedding-ai/llm-feature/ai-tool): Full landscape: {provider_count} providers, {model_count} models | Best: {model_id} ({provider}) | Cost: {cost_model_id} | See recommendations-current.json}
│  Next: {next_actions[0] — first 120 chars}
└─ Ready to work. (brief-path)
```

3. Ask: `Vibe? (build / fix / think / grind / ship / refine) [skip]`

**4. Work Queue Interactive Mode:** (Same as FAST PATH Step 4, same extracted tool)

```bash
python3 {TOOLS}/wakeup_lib.py work-queue --base {BASE}
```

Done. 1 tool call for the brief read + 1 for the work-queue tool (2 total).

**If brief does not exist:** fall through to FULL PROTOCOL.
**If brief is clearly stale** (git_sha_at_generation far behind HEAD): note staleness,
proceed anyway or fall through to FULL PROTOCOL.

---

## FULL PROTOCOL (STALE brief or no session-init)

Resolve `{BASE}`/`{TOOLS}` now (Step -1) if not already resolved this turn — every step below touches the filesystem.

### Step 1: Load Spoke Taste

Load `{BASE}/taste.spoke.yaml`. If any `entries` have `status: proposed`, surface them in the briefing and prompt for action.

```python
import yaml, os
try:
    with open('{BASE}/taste.spoke.yaml', 'r') as f:
        taste_data = yaml.safe_load(f)
    proposed_nudges = [e for e in taste_data.get('entries', []) if e.get('status') == 'proposed']
    if proposed_nudges:
        print(f"Taste nudges: {len(proposed_nudges)} proposed -- [a]ccept / [r]eject / [s]kip")
    # Historian nudge output format comment
    # {id, category, statement, evidence: [session_ids where correction occurred]}
except FileNotFoundError:
    pass # No taste.spoke.yaml yet, or it's empty/malformed.
```

### Step 1b: Qualifiers Check (silent if set)

```python
import json, os
state = json.load(open('{BASE}/WAI-State.json'))
q = state.get('wheel', {}).get('qualifiers', {})
if not q or all(len(v) == 0 for v in q.values()):
    print("⚠ Qualifiers not set — add wheel.qualifiers to help the hub KB match relevant learnings to this project.")
    print("  Fields: project_types, languages, frameworks, domains, themes")
```

### Step 1c: Navigator Startup (silent if hub absent)

Sync Navigator recommendations from hub and check catalog TTL. Extracted to the same tested
tool as Steps 4/4b (`{TOOLS}/wakeup_lib.py`) — the inline version hardcoded `WAI-Harness/spoke/...`
(silent no-op on v4-only spokes) and never consulted the operator's Navigator budget guard,
so a deliberate pause (`navigator_allowed: false` in `budget-guard.json`) rendered as a
misleading "recommendations stale" warning instead of the paused state it actually was
(impl-wakeup-v4-modernization-v1, feeds the exitclarity-4 paused-automation ATTENTION line):

```bash
python3 {TOOLS}/wakeup_lib.py navigator-startup --base {BASE}
```

### Step 1d: Hub Signals Inbox (skip if HUB SIGNALS = 0)

When `hub_signals_pending > 0` in session-init (or wakeup-brief), process each signal in `{hub_path}/WAI-Hub/signals/incoming/framework/` with two suppression checks before incorporating:

```python
import json, os, glob

state = json.load(open('{BASE}/WAI-State.json'))
wheel_name = state.get('wheel', {}).get('name', '')
hub_path = state.get('_hub', {}).get('path') or state.get('hub_path', '')
inbox = os.path.join(hub_path, 'WAI-Hub/signals/incoming/framework') if hub_path else ''

# Build local signal ID index (all subdirs under bytype/signal/)
local_ids = set()
for f in glob.glob('{BASE}/lugs/bytype/signal/**/*.json', recursive=True):
    try:
        d = json.load(open(f))
        local_ids.add(d.get('id', ''))
    except Exception:
        pass

if inbox and os.path.isdir(inbox):
    for sig_file in glob.glob(os.path.join(inbox, '*.json')):
        try:
            sig = json.load(open(sig_file))
            sig_id = sig.get('id', os.path.basename(sig_file))
            source_spoke = sig.get('source_spoke', '')

            # Dedup: skip if ID already incorporated locally
            if sig_id in local_ids:
                print(f'  [skip-dedup] {sig_id}')
                continue

            # Boomerang: skip if this spoke originated the signal
            if source_spoke and source_spoke == wheel_name:
                print(f'  [skip-boomerang] {sig_id} (originated here)')
                continue

            print(f'  [new] {sig_id} — {sig.get("title", sig.get("subject", "?"))[:80]}')
        except Exception as e:
            print(f'  [error] {sig_file}: {e}')
```

**Note:** `source_spoke` is a required field on all signal lugs. Without it, boomerang suppression cannot fire — the signal will be re-incorporated by the originating spoke on every wakeup.

### Step 2: Execute Full Protocol

Use `Read` to load `templates/commands/wai-full.md`, then execute all steps in that document.

---

*Fast path: 0 tool calls, ~15s. Brief path: 1 tool call. Full protocol in wai-full.md (loaded on demand).*


Convergence rules for all tools:
- Finish the WAI Point briefing before pausing for teaching approval or any other side action.
- During wakeup, inspect teachings using filenames and lightweight header/frontmatter fields only. Do NOT read full teaching bodies unless the user explicitly asks to review them now.
- If pending teachings exist, include them in the briefing under a compact "Pending Teachings" section, then ask what to do next.
- **Teachings and incoming lugs are first-class priority.** If either is non-zero at wakeup, address them before entering work queue mode. Do not skip or defer to the next session.
- **Post-adoption basher doctor check.** After the user confirms adoption of any teaching: check if `WAI-Harness/spoke/basher.json` exists (v4; `WAI-Harness/spoke/basher.json` on v3/coexist) in this spoke. If it does, emit immediately after adoption completes: `Recommended: run \`basher doctor\` to apply latest basher configuration to this spoke. Restart session if prompted.`

## Initiatives & Theme Health

**Initiatives** group related epics for completion tracking. **Themes** are the 7 health dimensions scored over time.

To surface the full scorecard: `/wai-initiative`

Quick summary at wakeup:
- Show count of epics per initiative (open / in_progress / completed)
- Flag any theme with zero active epic coverage as "neglected"
- Flag any epic with no `themes[]` field as "untagged"

Data source: `{BASE}/initiatives/index.json`

---

Output contract for all tools:
- Output the completed WAI Point briefing directly; do not narrate shell probes or bootstrap steps before it.
- Keep the post-brief closeout to one short readiness line such as `Wake complete. Ready to work.`
- Do not replace the briefing with a numbered next-steps plan unless the user explicitly asks for planning.
- If teachings or stale-task decisions need approval, list them compactly under `Pending Items` inside the briefing rather than stopping early.
