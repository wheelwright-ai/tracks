# WAI Compact Resume — Post-Compaction Recovery Protocol

**Trigger:** Context compaction just occurred (`<wai-post-compact>` block in context, or you notice working context is lost).

**Goal:** Restore full WAI awareness in ≤2 tool calls. Compaction is survivable — not catastrophic.

---

## Recovery Sequence

**Step 1 — Read WAI-State.json (1 tool call):**

```
Read: WAI-Spoke/WAI-State.json
```

Extract:
- `_session_state.track_path` — path to session track (e.g. `WAI-Spoke/sessions/session-XXXX/track.jsonl`)
- `_session_state.next_session_recommendation` — what was planned next
- `_savepoint` — if `status == "pending"`, a savepoint is active; read `lug_id` + `resume_note`
- `_session_state.last_session_id` — current session name

**Step 2 — Read recent track entries (1 tool call):**

```
Read: {track_path from Step 1}  (last 10 lines)
```

Look for: last action, `open` items, in-progress lug IDs, any `completed: true` markers.

**Done.** You are now WAI-aware. Proceed with the work that was in progress.

---

## If Mid-Closeout

Re-invoke `/wai-closeout` — it's idempotent. The track shows the last completed step.

---

## Compaction Survival Matrix

| Artifact | Survives? | Why |
|----------|-----------|-----|
| CLAUDE.md | **YES** | System-level injection — re-loaded every turn |
| MEMORY.md | **YES** | System-level injection — re-loaded every turn |
| Hook reminders (ledger, wakeup) | **YES** | UserPromptSubmit fires every turn |
| WAI-State.json | **YES** | Filesystem — read on resume |
| Lugs (all statuses) | **YES** | Filesystem — read on resume |
| Skill file bodies | **NO** | Context only — re-invoke to restore |
| Track ledger entries | **NO** | Compressed away — read last N lines |
| Tool output context | **NO** | Compressed away |
| In-session reasoning | **NO** | Compressed away |

**Key insight:** The filesystem always survives compaction. Only the conversation context is compressed. Recovery means re-reading the right files — not starting over.

---

## What Each Infrastructure Piece Does

| Component | Purpose | Compaction-specific? |
|-----------|---------|----------------------|
| `pre-compact.sh` | Writes `compacted.flag` + recovery hint to compaction summary | YES |
| `compacted.flag` in `WAI-Spoke/runtime/` | Signals post-compaction to next turn's hook | YES |
| `<wai-post-compact>` block in UserPromptSubmit | Re-orients Claude after compaction | YES |
| CLAUDE.md Critical Rules "survive compaction" | Documents what survives | YES |
| Session guard (`session-guard.json`) | General session hygiene (also helps post-compaction) | NO |
| Ledger turn reminders | General session hygiene (also helps post-compaction) | NO |
