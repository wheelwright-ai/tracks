# Command: Closeout

Run this skill at session end.

## Phase 0: Snapshot Prior Closeout

Before changing state, capture `_session_state.last_closeout` as `old_last_closeout`.

You need it later to detect which signals were created during this session.

## Phase 1: Reconcile Session Work

Read `WAI-Spoke/WAI-Lugs.jsonl` and consolidate unreconciled autosave or session lugs into one durable session summary.

The summary should capture:
- session goal
- files touched
- decisions made
- incomplete work
- exact next steps

If no autosave or session lugs exist, state that explicitly and continue.

## Phase 2: Extract Signals

Review the session for decisions or learnings with impact `>= 8`.

Append each qualifying signal to `WAI-Spoke/WAI-Signals.jsonl` as a JSON object with:
- `timestamp`
- `session_id`
- `signal`
- `impact`
- `rationale`
- `by`

Before appending, check for an existing entry with the same `timestamp` to avoid duplicates.

## Phase 3: Capture Forward Continuity

Write the handoff in two places:
- the session summary entry
- `_session_state.next_session_recommendation`

Include:
- current status
- what is done
- what remains
- blockers
- files involved
- the exact first next step

If `_session_state.track_path` exists, review the latest open items in that track before finalizing the recommendation.

## Phase 4: Update WAI State

Update `WAI-Spoke/WAI-State.json`:
- increment `_session_state.session_count`
- set `_session_state.last_closeout`
- set `_session_state.last_modified_by`
- set `_session_state.last_modified_at`
- set `_session_state.next_session_recommendation`
- clear `_session_state.current_session`
- preserve the latest `_session_state.track_path` if it exists

If the session changed product identity, scope, or approach, also update `_project_foundation.evolution_log`.

## Phase 5: Finalize Session Logs

If the live session used `WAI-Spoke/WAI-Session-Log.jsonl`:
- extract anything still needed for summary or signals
- then clear the file

If the session used an internal track file:
- keep `WAI-Spoke/sessions/track_session-*.jsonl` as an immutable session record
- never rewrite old session tracks

Portable exports remain separate:
- `WAI_Track-*.jsonl` files are external-facing artifacts
- they do not replace the internal live session log

## Phase 6: Deliver Outbox

Check `WAI-Spoke/lugs/outbox/` for pending `.jsonl` files.

If the hub path exists:
- copy each pending lug to `{hub_path}/WAI-Spoke/lugs/inbox/`
- report how many were delivered

If the hub is unavailable:
- note that in `_session_state.next_session_recommendation`
- do not block closeout

## Phase 7: Teach New Signals

If `WAI-Spoke/WAI-Signals.jsonl` contains entries newer than `old_last_closeout`, generate one teaching file per new signal using:

`signal-YYYYMMDD-HHMM-from-{spoke_id}.md.teaching`

Rules:
- include the actual signal payload
- include the sender spoke id in the filename
- skip signals already taught for the same timestamp

Outbox delivery happens during closeout; do not require a separate wakeup command for signal sync.

## Phase 8: Refresh Durable Docs

Update `WAI-Spoke/WAI-State.md` when the session materially changed:
- identity
- scope
- workflow
- major repo direction

Append to `WAI-Spoke/WAI-Session-Summary.jsonl` with the session date, model, outcomes, fossils, and open items.

## Phase 9: Ready-To-Leave Check

Before ending the session, confirm:
- session summary is written
- new signals are recorded or intentionally skipped
- `WAI-Spoke/WAI-State.json` has no active current session
- outbox delivery was attempted or explicitly deferred
- the next-session recommendation is actionable

Final line:

`Closeout complete. State preserved for the next session.`
