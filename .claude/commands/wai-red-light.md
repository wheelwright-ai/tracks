# WAI Red Light

Quality gate: pause work, inspect last 10 autosave checkpoints, assess crash recovery readiness.

## Instructions

1. **Read last 10 autosave lugs** from `lugs/active/WAI-Lugs-active.jsonl` where `autosave=true AND reconciled=false`
   If none: report "No autosave lugs found — auto-save protocol may not be active"

2. **Display each** summarized:
   | # | Action | State | Est | Next Step |
   |---|--------|-------|-----|-----------|

3. **Assess adequacy** for crash recovery:
   - **ADEQUATE**: All entries have task_context + current_state + next_step with meaningful content
   - **MARGINAL**: Some missing or vague — could resume with effort
   - **INSUFFICIENT**: Sparse/missing/too vague — high risk of lost context

4. **Show Roadmap** — top 5 open epics from the active lugs file:
   (ty=epic, s=o or s=p, sorted by priority then impact desc)

5. **Show Activity** — last 10 lugs touched (newest created_at/updated_at):
   (any ty, sorted desc)

6. **Output format**:
   ```
   🔴 Red Light — Work Paused

   **Autosave Checkpoint Inspection** ([N] entries)
   | # | Action | State | Est | Next Step |
   |---|--------|-------|-----|-----------|

   **Assessment: ADEQUATE / MARGINAL / INSUFFICIENT**
   [Specific gaps and recommendations if not ADEQUATE]

   ---
   **Roadmap** (Top 5 Open Epics)
   1. [title] — [priority] | impact: [n]

   ---
   **Activity** (Last 10 Lugs)
   - [ts] [title] ([ty], [s])

   ---
   Awaiting Green Light to resume | Discard with Closeout
   ```

7. **Pause** — wait for user response or Green Light.

## Context

### Autosave Protocol

After each significant action, an autosave lug is appended to `lugs/active/WAI-Lugs-active.jsonl`:
- Editing or creating a file
- Making an architectural/design decision
- Completing a sub-task
- Before asking a clarifying question
- Switching context

**Autosave Lug Schema:**
```json
{
  "i": "as-{12-char-hex}",
  "ty": "autosave",
  "s": "o",
  "autosave": true,
  "reconciled": false,
  "session_id": "...",
  "seq": 1,
  "title": "Brief: what was just done",
  "task_context": "Parent task being worked on",
  "action_taken": "What AI did in this turn",
  "current_state": "Where we are in the task",
  "what_remains": "What's left to complete",
  "files_touched": ["list", "of", "files"],
  "completion_estimate": "25%",
  "next_step": "Exactly what to do next"
}
```
