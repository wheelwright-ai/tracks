# WAI Track Format Specification

> Part of [Wheelwright AI Tracks](https://github.com/wheelwright-ai/tracks)

---

## File Naming

```
WAI_Track-{YYYYMMDD}-{HHMM}-{Provider}-{Model}.jsonl
```

**Examples:**
```
WAI_Track-20260317-1304-Claude-claude-opus-4-6.jsonl
WAI_Track-20260318-0921-ChatGPT-gpt5.jsonl
WAI_Track-20260319-1445-Gemini-gemini-2-0-pro.jsonl
```

When multiple collection snapshots occur within the same session, each gets a
new timestamp reflecting the time of collection:
```
WAI_Track-20260317-1304-Claude-claude-opus-4-6.jsonl   (first collection)
WAI_Track-20260317-1502-Claude-claude-opus-4-6.jsonl   (second collection)
```

---

## Session Continuity

Turns within **24 hours** of the session start belong in the same Track file.

If the conversation resumes **more than 24 hours** after the last recorded turn,
treat it as a linked continuation. Create a new Track file with a new timestamp.
Include a `session_start` event that references the prior session:

```json
{"event":"session_start","ts":"2026-03-19T10:00:00Z","session_id":"project-x-20260319","provider":"Claude","model":"claude-opus-4-6","continues":"WAI_Track-20260317-1304-Claude-claude-opus-4-6.jsonl","continuation_gap_hours":45}
```

Any agent reading the new Track knows exactly where the prior context lives and
how much time elapsed.

---

## Structure

Every Track file has three sections:

1. **Session start** — one event line at the top
2. **Points** — one line per turn
3. **Session end** — one event line at the bottom (optional but recommended)

---

## Session Start Event

```json
{
  "event": "session_start",
  "ts": "2026-03-17T13:04:00Z",
  "session_id": "descriptive-slug-YYYYMMDD",
  "provider": "Claude",
  "model": "claude-opus-4-6",
  "mode": "active-collection | prep-and-request | closing-request",
  "continues": null
}
```

---

## WAI Point Schema

Each turn produces exactly one JSONL line.

### Required Fields

Every point, every turn, no exceptions:

| Field | Type | Description |
|-------|------|-------------|
| `turn` | integer | Sequential turn number |
| `ts` | string | ISO-8601 UTC timestamp |
| `phase` | string | Current work state — see phase vocabulary below |
| `focus` | string | Descriptive title of the turn's primary thread |
| `action` | string | Summary of what was produced, decided, or changed |
| `thinking` | string | **3–8 sentences.** Why this path was chosen, what alternatives were rejected, rationale behind decisions, risks identified. Proportional to turn complexity. A future agent must be able to reconstruct the intellectual state of this turn from this field alone. This is the most valuable field in the schema. |

### Phase Vocabulary

| Phase | When to use |
|-------|-------------|
| `orientation` | Establishing context, reading existing state, understanding the problem |
| `exploration` | Generating options, researching, considering approaches |
| `planning` | Selecting approach, defining steps, structuring work |
| `execution` | Implementing, writing, building |
| `review` | Testing, verifying, debugging, quality checking |
| `convergence` | Narrowing from multiple options to a decision |
| `crystallization` | Finalizing, formalizing, committing to an outcome |

### Conditional Fields

Include when applicable, omit when not:

| Field | Type | Description |
|-------|------|-------------|
| `evolution` | string | How focus shifted from the prior turn. E.g., `"planning → execution: user approved approach"` |
| `activity` | array of strings | Concrete tool actions: files read with line ranges, commands executed, tool outputs analyzed. If no tools used: `["conversational response only"]` |
| `decisions` | array of strings | Explicit architectural, strategic, or logic choices made |
| `insights` | array of strings | New understandings or realizations |
| `fossils` | array of objects | Concepts abandoned or superseded: `{"concept":"...","replaced_by":"...","reason":"..."}` |
| `open` | array of objects | Unresolved threads: `{"item":"...","status":"unknown\|deferred\|intentional\|blocked"}` |
| `files_in` | array of objects | Files the user provided: `{"name":"...","type":"...","purpose":"..."}` |
| `files_out` | array of objects | Files the agent generated: `{"name":"...","type":"...","summary":"...","path":"..."}` |
| `context_health` | object | Active-collection mode only, when usage exceeds 70%: `{"usage_estimate":0.72,"warning":"approaching limit"}` |

---

## Session End Event

```json
{
  "event": "session_end",
  "ts": "2026-03-17T15:30:00Z",
  "total_turns": 14,
  "summary": "One-sentence session summary.",
  "unresolved_count": 3
}
```

---

## Full Point Example

```json
{"turn":3,"ts":"2026-03-17T13:12:00Z","phase":"convergence","focus":"Finalizing Track naming convention","action":"Agreed on Tracks as the portable record name; Paths concept retired","thinking":"The user clarified that a Track is a fixed record of the path taken, not a forward-looking route. The railroad metaphor resonates — each turn is a tie laid down, the Track is the permanent record of where the train went. The music metaphor stacks cleanly: a recording you can play back anywhere, on any device. WAI Points as the atomic unit within a Track is cleaner than a compound noun. The key distinction from a summary is per-turn granularity — summaries lose the reasoning thread, Points preserve it.","evolution":"exploration → convergence: naming decision crystallized through metaphor analysis","decisions":["Track replaces Path as the name for portable session records","WAI Points is the term for individual turn records within a Track","Lugs excluded from this repo scope — framework-internal concept"],"fossils":[{"concept":"WAI Paths as the portable artifact name","replaced_by":"WAI Tracks","reason":"Path implies forward direction; Track captures the retrospective, recorded nature of the artifact"}],"open":[{"item":"Does the Path concept retire entirely or shift to mean live session state?","status":"deferred"}]}
```

---

## Design Principles

**One point per turn.** Every turn is recorded regardless of apparent significance.
A turn that seems minor often contains critical context in retrospect.

**Thinking over action.** The `action` field records what happened. The `thinking`
field records why. Future agents can infer actions from context. They cannot infer
reasoning. Invest in `thinking`.

**Fossils are first-class.** Abandoned approaches are as valuable as adopted ones.
A fossil tells a future agent what not to try and why — preventing re-litigation of
already-settled decisions.

**Open items are continuity anchors.** Unresolved threads in one session become
the orientation context for the next. They are the explicit handoff between
sessions.

---

## Wheelwright AI and Active Collection

In the Wheelwright framework, Track recording is not a prompt — it is built into
the session protocol. Every turn is recorded automatically. The Historian advisor
periodically reviews the Track library across all project spokes to surface
patterns, recurring decisions, and context drift that no single-session review
would reveal.

The manual prompts in this repo produce the same format. Tracks generated manually
are fully compatible with Wheelwright's ingestion pipeline.

**[wheelwright.ai](https://wheelwright.ai) | [wheelwright-ai/framework](https://github.com/wheelwright-ai/framework)**
