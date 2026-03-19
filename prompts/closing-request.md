# WAI Track Generator — Closing Request

> Part of Wheelwright AI Tracks
> Generate a portable, replayable, and continuable record of any AI conversation.

## What is this?

A **WAI Track** is now a rich, multi-dimensional JSONL file that does three things at once:

1. Lets any future agent **continue the conversation exactly** where it left off.
2. Gives a complete intellectual history — including verbatim user voice, trade-offs, rejected paths, fossils with provenance, and half-considered ideas.
3. Preserves **only the final landing artifacts** (never intermediate drafts).

## How to use

1. Copy everything below the line into your conversation.
2. The agent will analyze the full history.
3. It will generate the enriched `.jsonl` Track file.

---

You are generating a **WAI Track file** — a rich, continuable record of this conversation.

## Your Task

Review the entire conversation history and produce a JSONL file where **each line is exactly one turn**.

The track must feel like a living workshop log: a future coding agent should be able to open it and immediately know what to build next, what the user's exact intent was, which ideas were fossils, and where the final reconciled specification lives.

## Output Format

**Filename**: `WAI_Track-{YYYYMMDD}-{HHMM}-{Provider}-{Model}.jsonl`

### First Line — Session Start
```json
{"event":"session_start","ts":"...","session_id":"descriptive-slug-YYYYMMDD","provider":"...","model":"...","mode":"closing-request"}
```

### One Line Per Turn (required fields + new rich fields)

**Always required**
- `turn`: integer
- `ts`: ISO-8601 UTC (estimate if needed)
- `phase`: orientation | exploration | planning | crystallization | convergence | execution | review
- `focus`: short descriptive title of the thread
- `action`: what was produced, decided, or changed this turn
- `thinking`: **5–10 sentences** structured as:
  - Why this path was chosen
  - Alternatives considered and rejected
  - Trade-offs weighed
  - Confidence (high/medium/low) in the direction
  - Any considerations that were only half-explored

**New required-for-richness fields**
- `user_intent`: 1-sentence summary in the **user's own voice/tone** (what the user was actually driving at)
- `pivotal_statements`: array of 1–3 short verbatim quotes (user or assistant) that were true turning points

**Include when applicable (strongly encouraged)**
- `evolution`: "previous-phase → current-phase: one-sentence reason"
- `decisions`: array of `{"choice":"...","rationale":"why this exact choice (1–2 sentences)"}`
- `insights`: array of new understandings
- `fossils`: array of `{"concept":"...","replaced_by":"...","reason":"...","from_turn":N}`
- `open`: array of `{"item":"...","status":"unknown|deferred|intentional|blocked","next_action_suggested":"..."}`
- `files_in`: array of `{"name":"...","type":"...","purpose":"..."}`
- `files_out`: **ONLY the final landing version** of any generated artifact. Format:
  ```json
  {"name":"canonical-wheelwright-spec.md",
   "type":"specification",
   "summary":"First 400 characters of the final reconciled spec + ...",
   "canonical_version":true,
   "excerpt":"[paste first 400 chars here]",
   "note":"This is the only version recorded — all prior drafts were superseded"}
  ```
  Never record intermediate drafts.

### Last Line — Session End
```json
{
  "event":"session_end",
  "ts":"...",
  "total_turns":N,
  "summary":"One-sentence session summary.",
  "key_contributions": ["list of 4–8 most important outputs or agreements"],
  "final_artifacts": ["list of all canonical files_out names with short descriptions"],
  "continuity_note":"What the next coding agent should pick up first (exact next step)",
  "unresolved_count":N,
  "major_phase_transitions":"orientation → exploration → ... → convergence"
}
```

## Rules (strict)

- Exactly one JSONL line per turn. No exceptions.
- **Artifacts rule**: Record **only the final reconciled version** of any spec, schema, folder layout, or charter. Include a short excerpt so the track itself carries value.
- Thinking field must be genuine intellectual history — not a summary.
- Preserve user voice in `user_intent` and `pivotal_statements`.
- After generating the file contents, output a brief human-readable summary:
  - Point count
  - Major phase transitions
  - Fossils recorded
  - Open items count
  - Continuity note for the next agent

After the JSONL contents, always add this exact human-friendly wrapper (do not modify it):

---

**Wheelwright Track Collected ✓**

Conversation successfully exported as a portable WAI Track file.

**Suggested filename:** `WAI_Track-{YYYYMMDD}-{HHMM}-{Provider}-{Model}.jsonl`

**How to save it (takes 10 seconds):**
1. Click anywhere inside the gray code block below
2. Press Ctrl+A (Windows) or Cmd+A (Mac) to select everything
3. Press Ctrl+C / Cmd+C to copy
4. Open a text editor (Notepad, VS Code, TextEdit, etc.)
5. Paste and save the file with the suggested name above (make sure it ends in .jsonl)

You can now:
- Feed this file to another agent to continue exactly where we left off
- Archive it as a structured record of decisions, reasoning, and final artifacts
- Use it later to rebuild context without re-reading the whole chat

Happy building!
