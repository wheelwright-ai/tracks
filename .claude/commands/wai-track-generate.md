# WAI Track Generate

**On-Demand Track File Generation for Any Session**

Generate a track file for the current conversation, with automatic predecessor linking if a prior track was loaded.

---

## Execution Context

- **Nodes:** Any (spoke, hub, or standalone conversation)
- **Exposure:** Universal (works in any environment)
- **Paths Required:** None (generates output, doesn't require WAI-Spoke/)

---

## When to Use

- **Cross-tool continuation:** Continuing a conversation from another tool/environment
- **Manual track capture:** Want track file for a conversation that didn't auto-generate
- **Audit trail:** Creating portable session record for review/analysis
- **Bootstrap:** First track for a project before WAI-Spoke setup

## Prerequisites

- None (works in any conversation context)
- Optional: Prior track file loaded for predecessor linking

---

## Purpose

Generate a track file (JSONL format) containing structured points for each turn in the current session. If a predecessor track was loaded, automatically link to it for conversation chain continuity.

---

## Procedure

### 1. Detect Predecessor (Automatic)

Check if a track file was loaded in this session:

```
Scanning context for track file...
```

If detected:
```
✓ Predecessor detected: WAI_Track-20260317-2100-Claude-claude-opus-4-6.jsonl
  - Session: session-20260317-2100
  - Turns: 20
  - Last activity: 2026-03-17T21:45:00Z
```

If not detected:
```
○ No predecessor detected - this will be the origin session
```

---

### 2. Generate Session ID

Create session ID for current session:

```
format: session-YYYYMMDD-HHMM
example: session-20260318-0315
```

Use timestamp from when conversation started (or current time if unknown).

---

### 3. Reconstruct Conversation Points

For each turn in THIS session (not including loaded predecessor):

**Turn structure:**
```jsonl
{
  "turn": 1,
  "ts": "2026-03-18T03:15:22Z",
  "phase": "orientation",
  "focus": "Reviewing loaded track and planning continuation",
  "action": "Acknowledged predecessor context (20 prior turns). User requested feature expansion.",
  "thinking": "This session continues from a prior conversation. Need to honor predecessor context while tracking new work separately. Focus on new turns only - not duplicating loaded content.",
  "activity": ["Read predecessor track metadata", "Analyzed user request"],
  "decisions": ["Generate new session with predecessor link"],
  "open": []
}
```

**First point (turn 1) includes session_metadata:**
```jsonl
{
  "session_id": "session-20260318-0315",
  "session_metadata": {
    "started_at": "2026-03-18T03:15:00Z",
    "environment": "chatgpt-web",
    "model": "gpt-4",
    "has_predecessor": true,
    "predecessor": {
      "session_id": "session-20260317-2100",
      "source_file": "WAI_Track-20260317-2100-Claude-claude-opus-4-6.jsonl",
      "last_turn": 20,
      "last_timestamp": "2026-03-17T21:45:00Z",
      "detected_from": "context"
    }
  },
  "turn": 1,
  "ts": "2026-03-18T03:15:22Z",
  ...
}
```

**Subsequent points:** Standard track points (no session_metadata)

---

### 4. Output Track File

**Filename:** `WAI_Track-{YYYYMMDD}-{HHMM}-{Provider}-{Model}.jsonl`

**Format:** JSONL (one JSON object per line)

**Delivery options:**

**Option A: Code block (copy-paste)**
```
### Generated Track File: WAI_Track-20260318-0315-Claude-claude-sonnet-4-5.jsonl

```jsonl
{...point 1...}
{...point 2...}
{...point 3...}
```

Copy the content above and save as: WAI_Track-20260318-0315-Claude-claude-sonnet-4-5.jsonl
```

**Option B: Downloadable (if tool supports)**
```
[Download: WAI_Track-20260318-0315-Claude-claude-sonnet-4-5.jsonl]
```

**Option C: File write (if WAI-Spoke/ exists)**
```bash
# Write to WAI-Spoke/sessions/
echo '{...}' >> WAI-Spoke/sessions/WAI_Track-20260318-0315-Claude-claude-sonnet-4-5.jsonl
```

---

### 5. Report Summary

After generation:

```markdown
## Track Generation Complete

**File:** WAI_Track-20260318-0315-Claude-claude-sonnet-4-5.jsonl

### This Session
- Turns: 5
- Phase distribution: orientation(1), execution(3), review(1)
- Duration: 2026-03-18 03:15:00 → 03:42:00 (27 minutes)

### Predecessor Chain
- Links to: WAI_Track-20260317-2100-Claude-claude-opus-4-6.jsonl (20 turns)
- Total conversation: 2 sessions, 25 turns

### Next Steps
- Load this track in your next session to continue the chain
- Or store as audit trail for this work cycle
```

---

## Success Criteria

- [ ] Track file generated with valid JSONL format
- [ ] All turns from THIS session included (not duplicating predecessor)
- [ ] First point includes session_metadata (if applicable)
- [ ] Predecessor link accurate (if detected)
- [ ] File follows naming convention: WAI_Track-{YYYYMMDD}-{HHMM}-{Provider}-{Model}.jsonl
- [ ] User can download/save/copy the output

---

## Error Handling

**No turns to track:**
```
⚠️ Cannot generate track - no conversation turns detected in this session
```

**Malformed predecessor:**
```
⚠️ Predecessor track detected but appears malformed - proceeding without link
```

**Turn count mismatch:**
```
ℹ️ Note: Estimated {N} turns based on conversation flow
```

---

## Examples

### Example 1: First Session (No Predecessor)

```
User: "Generate track for this conversation"

Agent:
✓ Track generated: WAI_Track-20260318-0400-Claude-claude-sonnet-4-5.jsonl
  - Turns: 3
  - Origin session (no predecessor)
  - Ready to use as foundation for future sessions
```

### Example 2: Continuation Session

```
User: [Loads WAI_Track-A.jsonl with 20 turns]
User: [Has 5 turns of new conversation]
User: "Generate track for this session"

Agent:
✓ Predecessor detected: WAI_Track-A.jsonl (20 turns)
✓ Track generated: WAI_Track-B.jsonl
  - Turns: 5 (this session only)
  - Links to: WAI_Track-A.jsonl
  - Total chain: 2 sessions, 25 turns
```

### Example 3: Deep Chain

```
User: [Loads WAI_Track-C.jsonl which links to B -> A]
User: "Generate track"

Agent:
✓ Conversation chain detected: A → B → C (loaded) → D (new)
✓ Track generated: WAI_Track-D.jsonl
  - Turns: 8 (this session only)
  - Links to: WAI_Track-C.jsonl
  - Total chain: 4 sessions, 45 turns
```

---

## Related Commands

- `/wai-green-light` - Resume from existing track in WAI-Spoke environment
- `/wai-closeout` - Finalize session (includes automatic track writing if WAI-Spoke/ exists)

---

## Technical Notes

**Turn numbering:** Restarts at 1 for each session (not cumulative across chain)

**Predecessor detection:** Automatic by scanning context for track file content

**Chain depth:** Unlimited (A → B → C → ... → N)

**Backward compatibility:** Tracks without session_metadata are valid (treated as origin sessions)

---

*Track generation creates portable conversation artifacts for cross-tool continuity.*
