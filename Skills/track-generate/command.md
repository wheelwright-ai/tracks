# Command: Track Generate

Use this skill to create a portable `WAI_Track-*.jsonl` export.

## Phase 1: Load the Track Contract

Read `spec/track-format.md` before generating output.

Match its rules for:
- filename
- `session_start`
- one line per turn
- optional `session_end`
- required and conditional fields

## Phase 2: Gather Source Context

Collect the best available session source in this order:
1. an existing normalized internal track in `WAI-Spoke/sessions/track_session-*.jsonl`
2. `WAI-Spoke/WAI-Session-Log.jsonl`
3. active chat history prepared through `chat-to-track`

If multiple sources exist, reconcile them into one non-duplicated turn stream.

## Phase 3: Normalize Turns

If the source is not already in track-ready form, invoke `Skills/chat-to-track/command.md` first.

The normalized result must provide one record per turn with:
- `turn`
- `ts`
- `phase`
- `focus`
- `action`
- `thinking`

Add conditional fields only when supported by the source evidence.

## Phase 4: Set Session Metadata

Determine:
- export filename: `WAI_Track-{YYYYMMDD}-{HHMM}-{Provider}-{Model}.jsonl`
- `session_id`
- provider and model labels
- export mode
- continuation metadata when the session resumes a prior track

If the session continues a prior export after a meaningful time gap, include the `continues` field and `continuation_gap_hours` when known.

## Phase 5: Build the Export

Write the export in this order:
1. one `session_start` event
2. one JSONL line per turn
3. one `session_end` event when the snapshot is ending or closeout requests a final export

Rules:
- preserve user voice in `user_intent` and `pivotal_statements` when the richer schema is available
- record only final landing artifacts in `files_out`
- never include superseded intermediate drafts as canonical artifacts
- keep line ordering strictly chronological

## Phase 6: Verify the File

Before returning the export, verify:
- every line is valid JSON
- turn numbers are sequential
- required fields are present
- no turn is duplicated or skipped
- session metadata matches the actual source session

## Outputs

Primary output:
- a portable `WAI_Track-*.jsonl` file or file body suitable for saving

Secondary output:
- a brief human summary with point count, major phase transitions, fossils, open items, and the continuity note when available
