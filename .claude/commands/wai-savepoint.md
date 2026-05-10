# WAI Savepoint

Save a mid-arc savepoint so you can reset context without losing work state.

---

## Purpose

A savepoint is a **planned mid-arc context reset**. It is NOT a session closeout. The active lug stays `in_progress`, and work resumes in the next session via `/wai` → `[C]ontinue`.

**Use when:** approaching ~80% context with an `in_progress` lug that isn't finished.

---

## Steps

**Step 1: Identify active lug**

Read `WAI-Spoke/lugs/bytype/*/in_progress/*.json`. If multiple in-progress lugs exist, ask the user: "Which lug are you savepointing?"

**Step 2: Capture progress**

Ask (or infer from the conversation):
- What's done so far in this lug?
- What's the exact next step?

**Step 3: Write `savepoint_note` to the lug file**

Add or update this field in the lug JSON:

```json
"savepoint_note": {
  "done": "<what's been completed>",
  "next_step": "<exact next step>",
  "saved_at": "<ISO timestamp>"
}
```

**Step 4: Write `_savepoint` to `WAI-State.json`**

```json
"_savepoint": {
  "lug_id": "<lug_id>",
  "resume_note": "<one-line next step — plain English, no lug IDs, max 60 chars>",
  "saved_at": "<ISO timestamp>",
  "session_id": "<current session_id>",
  "status": "pending"
}
```

`resume_note` is displayed in CONTEXT HEALTH at wakeup. Write it for a human skimming a status line — what to do next, not which lug to open.

**Step 5: Commit**

```bash
git add WAI-Spoke/lugs/bytype/<type>/in_progress/<lug-id>.json
git add WAI-Spoke/WAI-State.json
git commit -m "savepoint: <lug-id> — <resume_note>"
```

**Step 6: Output exactly**

```
Savepoint saved: "<lug title>" (<lug-id>). Next: <resume_note>. Safe to exit — choose [C]ontinue at next /wai.
```

---

## Rules

- Do NOT run `/wai-closeout`
- Do NOT change lug status (stays `in_progress`)
- Do NOT write a session track closeout entry
- The next `/wai` session will detect the pending savepoint in CONTEXT HEALTH and offer `[C]ontinue`
