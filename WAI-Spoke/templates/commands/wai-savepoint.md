# WAI Savepoint

Save enough state to exit cleanly — safe eject before context runs out.

---

## Purpose

A savepoint is a **safe eject** — commit enough state that the next session starts cleanly without archaeology. Use when approaching context limit, before compression fires, or any time you want to exit without a full `/wai-closeout` ceremony. Does NOT require an in-progress lug.

---

## Steps

All mechanical work runs in a **sub-agent** dispatched from the main session. The main session contributes exactly one reasoning turn: the `next_session_recommendation` string. Everything else is deterministic JSON/git work that runs fresh.

**Step 1 (main session): Compose the savepoint strings**

Compose FOUR plain-English strings — this is the only step requiring session context:

- `work_done`: one line of what was completed this session (e.g. "Implemented autopilot stall gate and per-lug timeout, patched 4 lugs")
- `work_context`: one sentence on what was being worked on — gives the resuming agent a sense of the arc without re-reading the full track (e.g. "Mid-way through scouting expedition; 6 scouts built, Phase E gated on API key")
- `user_next_step`: any action the agent told the user to take before the next session (e.g. "Export ANTHROPIC_API_KEY then run the 3 limited scouts"). Omit if no user action is pending.
- `resume_note`: what the AGENT does first at next `/wai` (max 60 chars). If next step depends on a user action, frame it as: "Ask if [user action] done; if yes, [agent action]". The user action belongs in `user_next_step`, not here.

**resume_note POV rule:** `resume_note` is an agent instruction, not a user instruction. Wrong: "Run migrations 000-003 in Supabase". Correct: "Ask if migrations done; if yes, run basher restore".

Also resolve:
- `session_id` — from `WAI-State.json._session_state.session_id` or derive from current track path
- `lug_id` — the lug currently in progress, or `null`

**Step 2 (main session): Dispatch sub-agent**

Using the Agent tool, dispatch with this exact prompt (substitute `{session_id}`, `{lug_id}`, `{work_done}`, `{work_context}`, `{user_next_step}`, `{resume_note}` before dispatching):

```
You are running a savepoint for session {session_id}.

Read WAI-Spoke/WAI-State.json. Then in order:

1. Write the singular top-level key `_savepoint` (NOT an array):
   {
     "status": "pending",
     "lug_id": {lug_id},
     "session_id": "{session_id}",
     "work_done": "{work_done}",
     "work_context": "{work_context}",
     "user_next_step": "{user_next_step_or_omit}",
     "resume_note": "{resume_note}",
     "saved_at": "<current ISO UTC>"
   }
   Omit `user_next_step` if empty. This replaces any previous `_savepoint` value entirely.

2. Set `_session_state.next_session_recommendation` to: "{resume_note}"

3. Write WAI-Spoke/WAI-State.json with both changes.

4. Append this JSON line to WAI-Spoke/sessions/{session_id}/track.jsonl (create dir/file if needed):
   {"event": "savepoint", "ts": "<ISO UTC>", "session_id": "{session_id}", "lug_id": {lug_id}, "work_done": "{work_done}", "work_context": "{work_context}", "resume_note": "{resume_note}"}

5. Run: python3 tools/generate_wakeup_brief.py

6. Run:
   ```bash
   git add -A && git commit -m "savepoint: {session_id} — {work_done} | next: {resume_note}"
   ```

7. Push to origin (same rebase guard as closeout):
   ```bash
   git fetch origin 2>/dev/null || true
   REMOTE_AHEAD=$(git rev-list HEAD..origin/main --count 2>/dev/null || echo 0)
   if [[ "$REMOTE_AHEAD" -gt 0 ]]; then
       git pull --rebase origin main
   fi
   if ! git push origin main; then
       echo "ERROR: git push failed — savepoint committed locally but NOT pushed to remote"
       echo "Run 'git push origin main' manually before exiting to preserve this savepoint."
       exit 1
   fi
   ```

Output: Savepoint committed and pushed. Report: "Savepoint committed and pushed."
```

**Step 3 (main session, after sub-agent completes): Output exactly**

```
Savepoint saved: "{work_done}". Next: {resume_note}
```

---

## `_savepoint` schema (singular object, not array)

Location: `WAI-Spoke/WAI-State.json`, top-level key `_savepoint`.

- `status` — `"pending"` on creation; `"resumed"` when next session continues; cleared to `{}` on full wakeup or closeout
- `lug_id` — the lug being worked, or `null` if no active lug
- `session_id` — current session ID (fallback identifier when `lug_id` is null)
- `work_done` — what was DONE this session; backward-looking (≤120 chars)
- `work_context` — what was being WORKED ON; gives the resuming agent arc awareness without reading the full track
- `user_next_step` — action the agent told the user to take before next session; omit if none
- `resume_note` — what the AGENT does first at next `/wai` (≤60 chars). Agent instruction, not user instruction. If gated on a user action, write: "Ask if [action] done; if yes, [agent step]"
- `saved_at` — ISO-8601 UTC timestamp

**Lifecycle:**
- `/wai-savepoint` writes `_savepoint = {status: "pending", ...}` and commits WAI-State.json
- Next `/wai` sees `_savepoint.status == "pending"` and offers Resume
- On Resume: set `_savepoint.status = "resumed"`
- On Full wakeup: clear `_savepoint = {}`
- `/wai-closeout` clears `_savepoint` if still pending (closing the arc invalidates mid-arc state)

**There is NO `_savepoints[]` array.** If you see this key in WAI-State.json, it was written by a stale agent — delete it.

---

## Rules

- Savepoint IS a minimal closeout. Full `/wai-closeout` adds session tracking, teaching, and version bump on top of this.
- No in-progress lug required — savepoint works at any point in a session.
- Wakeup detects `_savepoint.status == "pending"` (singular key, not `_session_status`) and shows the resume prompt.
- The `savepoint` track event appended in step 4 lets session-start.sh classify the exit as SAVEPOINT (not INTERRUPTED) when the integrity check is updated to accept `event == "savepoint"`.
- The next `/wai` session will show `work_done` + `resume_note` in CONTEXT HEALTH (both fields displayed when `_savepoint.status == "pending"`).
