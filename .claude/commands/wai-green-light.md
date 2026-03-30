# WAI Green Light

Resume execution from last autosave checkpoint.

## Instructions

1. **Read last unreconciled autosave lug** from `lugs/active/WAI-Lugs-active.jsonl`
   (ty=autosave, reconciled=false, latest by created_at)
   If none: "Nothing to resume — starting fresh"

2. **Output**:
   ```
   🟢 Green Light — Resuming

   Task: [task_context]
   Where we left off: [current_state]
   Progress: [completion_estimate]

   **Next step:** [next_step]
   Remaining: [what_remains]
   ```

3. **Continue execution** — proceed with next_step immediately.

## Context

### Wakeup Detection

On session start, if unreconciled autosave lugs exist (ty=autosave, reconciled=false), the briefing shows an "Incomplete Work" section with count, task context, and progress estimate. Options presented: Resume (Green Light) / Inspect (Red Light) / Continue without.

See `wai-red-light.md` for the autosave lug schema.
