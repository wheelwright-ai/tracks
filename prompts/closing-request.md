# WAI Track Generator — Closing Request

> Part of [Wheelwright AI Tracks](https://github.com/wheelwright-ai/tracks)
> Generate a portable record of any AI conversation.

## What is this?

A **Track** is a structured JSONL file that captures the meaningful points of a
conversation — decisions made, concepts explored, ideas that evolved or were
abandoned. Track files are portable: feed one to any AI model and it can
reconstruct the session's context without the original conversation.

Your AI conversations produce real intellectual work. Right now that work is
trapped inside the chat. This prompt extracts it and gives it back to you.

This prompt works retroactively on any existing conversation. No prior setup
needed.

## How to use

1. Copy everything below the line into your conversation
2. The agent will analyze the full conversation history
3. It will generate a `.jsonl` Track file you can download and use anywhere

For richer results on future sessions, see the
[prep-and-request](https://github.com/wheelwright-ai/tracks/blob/main/prompts/prep-and-request.md)
variant. For real-time recording on every turn, see
[active-collection](https://github.com/wheelwright-ai/tracks/blob/main/prompts/active-collection.md).

Learn more: [wheelwright.ai](https://wheelwright.ai) |
[wheelwright-ai/framework](https://github.com/wheelwright-ai/framework)

---

You are generating a **WAI Track file** — a portable record of this conversation.

## Your Task

Review the entire conversation history and produce a JSONL file where each line
is one point representing one turn of the conversation.

## Output Format

Name the file: `WAI_Track-{YYYYMMDD}-{HHMM}-{Provider}-{Model}.jsonl`

Use today's date and current time. Identify your own provider and model for the
filename.

### First Line — Session Start

```json
{"event":"session_start","ts":"...","session_id":"descriptive-slug-YYYYMMDD","provider":"...","model":"...","mode":"closing-request"}
```

### Subsequent Lines — One Point Per Turn

Each turn of the conversation becomes exactly one JSONL line.

**Required fields on every point:**

- `turn` — sequential turn number (integer)
- `ts` — ISO-8601 UTC timestamp (estimate based on conversation flow if not available)
- `phase` — current work state: `orientation` | `exploration` | `planning` | `execution` | `review` | `convergence` | `crystallization`
- `focus` — descriptive title of the turn's primary thread
- `action` — summary of what was produced, decided, or changed
- `thinking` — **3–8 sentences.** Why this path was taken, what alternatives were considered, the reasoning behind decisions. This is the most valuable field. Do not produce thin summaries. A future agent must be able to reconstruct the intellectual state of this turn from this field alone.

**Include when applicable:**

- `evolution` — how focus shifted from the prior turn (e.g., `"exploration → planning: user narrowed scope to MVP features"`)
- `decisions` — array of explicit choices made
- `insights` — array of new understandings or realizations
- `fossils` — array of abandoned or superseded concepts: `{"concept":"...","replaced_by":"...","reason":"..."}`
- `open` — array of unresolved threads: `{"item":"...","status":"unknown|deferred|intentional|blocked"}`
- `files_in` — files the user provided: `{"name":"...","type":"...","purpose":"..."}`
- `files_out` — files generated: `{"name":"...","type":"...","summary":"..."}`

### Last Line — Session End

```json
{"event":"session_end","ts":"...","total_turns":N,"summary":"One-sentence session summary.","unresolved_count":N}
```

## Rules

- One JSONL line per turn. No exceptions. Do not skip turns.
- Do not summarize the conversation. Record each turn individually as its own point.
- The `thinking` field must contain genuine reasoning, not restated actions. Capture *why*, not just *what*.
- Produce the Track as a downloadable `.jsonl` file.
- After generating the file, provide a brief summary: point count, major phase transitions, any fossils recorded, count of open items.
