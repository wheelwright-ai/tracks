# Command: Chat To Track

Use this skill to transform raw conversation history into track-ready turn records.

## Phase 1: Gather Inputs

Use the richest available source material:
- active conversation history
- `WAI-Spoke/WAI-Session-Log.jsonl`
- an in-progress internal track in `WAI-Spoke/sessions/track_session-*.jsonl`
- referenced final artifacts produced during the session

Prefer direct session evidence over reconstructed summaries.

## Phase 2: Establish Session Envelope

Determine or preserve:
- session id
- turn order
- timestamps or best-effort estimates
- provider and model labels when known
- any predecessor track linkage already established by wakeup or prior exports

Do not invent continuity metadata if the source does not support it.

## Phase 3: Map One Record Per Turn

For each turn, produce one structured record with:
- `turn`
- `ts`
- `phase`
- `focus`
- `action`
- `thinking`

`thinking` should preserve why the path was chosen, trade-offs, rejected alternatives, and confidence at a level proportional to the turn complexity.

## Phase 4: Add Rich Context Fields

Include these when supported by the source:
- `user_intent`
- `pivotal_statements`
- `evolution`
- `decisions`
- `insights`
- `fossils`
- `open`
- `files_in`
- `files_out`

Rules:
- preserve the user's own voice where the schema asks for it
- record fossils when an idea was abandoned or replaced
- record only final landing artifacts in `files_out`
- omit fields that cannot be justified from the source

## Phase 5: Reconcile Artifacts and Open Items

Make the normalized record useful for the next agent:
- point `files_out` to canonical outputs when paths are known
- capture unresolved work in `open`
- keep decisions and insights aligned with the actual session sequence

If multiple drafts exist, keep only the final reconciled artifact as canonical.

## Phase 6: Emit Track-Ready Output

Return or write a chronologically ordered turn stream suitable for `Skills/track-generate/command.md`.

When writing an internal session record:
- use `WAI-Spoke/sessions/track_session-YYYYMMDD-HHMM.jsonl`
- treat it as immutable once finalized

Before handing off, verify:
- one record exists for every included turn
- numbering is sequential
- required fields are populated
- unsupported richness fields were omitted rather than guessed
