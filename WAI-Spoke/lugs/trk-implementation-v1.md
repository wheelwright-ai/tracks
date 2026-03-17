---
_lug:
  id: "trk-impl-v1"
  type: "work-order"
  title: "Tracks Repo — Full Implementation"
  status: "ready-to-execute"
  version: "1.0.0"
  created: "2026-03-17"
  authored_by: "claude-sonnet-4-6"
  destination: "tracks spoke agent"
  safe_to_auto_adopt: false
  behavior_directive:
    what_this_is: >
      Complete implementation spec for the wheelwright-ai/tracks repository.
      Strip the current Next.js scaffold. Build a pure documentation and prompt
      library repo. Execute in the phases described below, file by file.
    prerequisite: >
      The Next.js scaffold (src/, package.json, node_modules, tsconfig.json,
      next.config.ts, postcss.config.mjs) must be removed before building.
      WAI-Spoke/ stays intact. Bootstrap scripts stay as reference artifacts.
---

# Tracks — Implementation Work Order

## What This Repo Is

`wheelwright-ai/tracks` is a documentation and prompt library. No app, no build
system, no dependencies. It teaches conversation portability via Track files and
serves as a funnel to the Wheelwright AI framework.

**The insight:** AI conversations produce real intellectual work that evaporates
when the session ends. Track files capture it and make it portable. No LLM
provider advertises this freedom. We do.

**The funnel:** The prompts in this repo let anyone generate Track files manually.
Wheelwright AI does it automatically, on every turn, with richer data and
cross-session intelligence.

---

## Phase 0: Strip the Scaffold

Remove all files/dirs that belong to the Next.js app:

```
src/
package.json
package-lock.json
node_modules/
tsconfig.json
next.config.ts
postcss.config.mjs
.next/             (if present)
data/              (if empty)
```

**Keep:**
- `WAI-Spoke/`
- `BOOTSTRAP_TRACKS_BASE.sh`
- `BOOTSTRAP_TRACKS_BEST.sh`
- `.gitignore`

---

## Phase 1: Directory Structure

```
tracks/
├── README.md
├── LICENSE
├── prompts/
│   ├── active-collection.md
│   ├── prep-and-request.md
│   └── closing-request.md
├── samples/
│   ├── coding-session.jsonl
│   ├── strategy-session.jsonl
│   └── learning-session.jsonl
├── spec/
│   └── track-format.md
└── WAI-Spoke/                  (untouched)
```

---

## Phase 2: File Contents

---

### README.md

```markdown
# Tracks

> Your AI conversations produce real knowledge. Track files capture it and make it portable.

[![Wheelwright AI](https://img.shields.io/badge/Wheelwright-AI-orange)](https://wheelwright.ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub](https://img.shields.io/badge/framework-wheelwright--ai%2Fframework-blue)](https://github.com/wheelwright-ai/framework)

---

## What is a Track?

A **Track** is a structured record of an AI conversation — every decision made,
every concept explored, every idea that evolved or was abandoned. It is a JSONL
file where each line is a single **WAI Point** representing one turn of the
conversation.

Track files are not summaries. They are telemetry. A future agent reading a Track
file can reconstruct what happened, why it happened, and what was left unresolved —
without having access to the original conversation.

---

## Why This Matters

Your AI conversations produce real intellectual work: architectural decisions,
strategy pivots, research synthesis, creative breakthroughs. When the session
ends, all of that context evaporates. The next session starts cold. A different
model can't access it. A colleague can't pick up where you left off.

**Track files solve this. They make your conversations portable.**

| Use Case | What It Unlocks |
|----------|----------------|
| **Switch models** | Export a Track from Claude, resume in GPT or Gemini with zero lost context |
| **Merge conversations** | Two separate threads on related topics — feed both Tracks to a new session and work from combined knowledge |
| **Async handoff** | Hand a project to another person or AI instance mid-stream with full fidelity |
| **Knowledge library** | Accumulate Tracks as a personal or team knowledge base — searchable, reusable, composable |
| **Cold start prevention** | Never brief an AI from scratch again — feed a Track and skip the ramp-up entirely |
| **Pattern detection** | Review Tracks across sessions and surface recurring decisions, bottlenecks, insights |

This is not a feature any LLM provider is giving you. The session belongs to you.
Track files are how you claim it.

---

## Three Ways to Generate a Track

### Start here → Closing Request

Already had a conversation? Extract a Track from it after the fact. Drop the
prompt into any existing session and get a Track file of what happened. This is
the fastest way to try it.

**[→ prompts/closing-request.md](prompts/closing-request.md)**

Give an LLM the raw URL of that file and say "follow these instructions." It
will understand the assignment.

### Next level → Prep and Request

Starting a new session? Give the agent the prompt at the beginning. Work
normally. Say **"collect tracks"** when you want a snapshot. The agent knows the
format in advance and produces higher-fidelity output.

**[→ prompts/prep-and-request.md](prompts/prep-and-request.md)**

### Full integration → Active Collection

The agent records a WAI Point on every single turn, in real time. Nothing to
remember, nothing to request. This is what Wheelwright AI does natively — this
prompt lets you approximate it manually.

**[→ prompts/active-collection.md](prompts/active-collection.md)**

---

## The Wheelwright Advantage

The prompts in this repo get you the Track. Wheelwright AI gets you the system.

- **Active collection is built in** — every Wheelwright session records automatically, nothing to trigger
- **Cross-spoke continuity** — a strategy session's Track can seed an implementation session in a different project
- **Historian advisor** — reviews your Track library over time and surfaces patterns you would never think to look for: recurring decision points, bottlenecks, drift from original intent
- **Track files as persistent intelligence** — the foundation of a project context that outlives any individual session or model

This repo is the on-ramp. Wheelwright is the destination.

**[wheelwright.ai](https://wheelwright.ai) | [wheelwright-ai/framework](https://github.com/wheelwright-ai/framework)**

---

## Track Format

Track files are JSONL. One line per turn. The first line is a `session_start`
event, the last is a `session_end` event, and every line between is a WAI Point.

**[→ spec/track-format.md](spec/track-format.md)** — complete format specification.

See **[samples/](samples/)** for real examples you can feed to any LLM to
demonstrate portability.

---

## Improve This

This technique works today, with any LLM, with no tooling. We encourage you to
adapt the prompts to your needs — adjust the point schema, add fields that matter
for your domain, tune the phase vocabulary.

When you find something that works better, open a PR. The prompts improve with
use.

The optimal integration is through the Wheelwright framework, where collection
is automatic, Historian analysis is built in, and Tracks compose across projects.
But the manual technique is available to everyone, right now.

---

## Coming Soon: MCP Integration

A Tracks MCP server is on the roadmap. Once installed, any MCP-compatible LLM
will understand the Track format, generate Tracks automatically, and surface them
without any user prompting.

Star this repo to follow progress.

---

## License

MIT — see [LICENSE](LICENSE)

**Built by [Wheelwright AI](https://wheelwright.ai)**
```

---

### spec/track-format.md

````markdown
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
WAI_Track-20260317-1304-Claude-claude-opus-4-6.jsonl  (first collection)
WAI_Track-20260317-1502-Claude-claude-opus-4-6.jsonl  (second collection)
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
| `phase` | string | Current work state (see phases below) |
| `focus` | string | Descriptive title of the turn's primary thread |
| `action` | string | Summary of what was produced, decided, or changed |
| `thinking` | string | **3–8 sentences.** Why this path was chosen, what alternatives were rejected, architectural rationale, risks identified. Proportional to turn complexity. A future agent must be able to reconstruct the intellectual state of this turn from this field alone. This is the most valuable field in the schema. |

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
| `evolution` | string | How focus shifted from the prior turn. E.g., `"planning → execution: user approved strategy"` |
| `activity` | array of strings | Concrete tool actions: files read (with line ranges), commands executed, tool outputs analyzed. If no tools used: `["conversational response only"]` |
| `decisions` | array of strings | Explicit architectural, strategic, or logic choices made |
| `insights` | array of strings | New understandings or realizations |
| `fossils` | array of objects | Concepts abandoned or superseded: `{"concept": "...", "replaced_by": "...", "reason": "..."}` |
| `open` | array of objects | Unresolved threads: `{"item": "...", "status": "unknown\|deferred\|intentional\|blocked"}` |
| `files_in` | array of objects | Files the user provided: `{"name": "...", "type": "...", "purpose": "..."}` |
| `files_out` | array of objects | Files the agent generated: `{"name": "...", "type": "...", "summary": "...", "path": "..."}` |
| `context_health` | object | Active-collection mode only, when usage >70%: `{"usage_estimate": 0.72, "warning": "approaching limit"}` |

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
{"turn":3,"ts":"2026-03-17T13:12:00Z","phase":"convergence","focus":"Finalizing Track naming convention","action":"Agreed on Tracks as the portable record name; Paths concept retired","thinking":"The user clarified that a Track is a fixed record of the path taken, not a forward-looking route. The railroad metaphor resonates — each turn is a tie laid down, the Track is the permanent record of where the train went. The music metaphor stacks cleanly too: a recording you can play back anywhere, on any device. WAI Points as the atomic unit within a Track is cleaner than a compound noun. The key distinction from a summary is the per-turn granularity — summaries lose the reasoning thread, Points preserve it.","evolution":"exploration → convergence: naming decision crystallized through metaphor analysis","decisions":["Track replaces Path as the name for portable session records","WAI Points is the term for individual turn records within a Track","Lugs excluded from this repo scope — framework-internal concept"],"fossils":[{"concept":"WAI Paths as the portable artifact name","replaced_by":"WAI Tracks","reason":"Path implies forward direction; Track captures the retrospective, recorded nature of the artifact"}],"open":[{"item":"Does the Path concept retire entirely or shift to mean live session state?","status":"deferred"}]}
```

---

## Design Principles

**One point per turn.** Every turn of the conversation is recorded, regardless
of apparent significance. A turn that seems minor often contains critical context
in retrospect.

**Thinking over action.** The `action` field records what happened. The
`thinking` field records why. Future agents can infer actions from context. They
cannot infer reasoning. Invest in `thinking`.

**Fossils are first-class.** Abandoned approaches are as valuable as adopted
ones. A fossil tells a future agent what not to try and why.

**Open items are continuity anchors.** Unresolved threads in one session become
the orientation context for the next.

---

## Wheelwright AI and Active Collection

In the Wheelwright framework, Track recording is not a prompt — it is built into
the session protocol. Every turn is recorded automatically. The Historian advisor
periodically reviews the Track library across all project spokes to surface
patterns, recurring decisions, and context drift that no single-session review
would reveal.

The manual prompts in this repo produce the same format. Tracks generated
manually are fully compatible with Wheelwright's ingestion pipeline.

**[wheelwright.ai](https://wheelwright.ai) | [wheelwright-ai/framework](https://github.com/wheelwright-ai/framework)**
````

---

### prompts/closing-request.md

Content is exactly as specified in section 1.6 of the plan. Write verbatim.

---

### prompts/prep-and-request.md

Content is exactly as specified in section 1.7 of the plan. Write verbatim.

---

### prompts/active-collection.md

Content is exactly as specified in section 1.8 of the plan. Write verbatim.

---

### samples/coding-session.jsonl

A developer refactoring an authentication module. 10 points. Natural phase
progression: orientation → exploration → planning → execution → review.
Include: activity arrays with file reads and command executions, at least 2
decisions, at least 1 fossil (abandoned approach), 2 open items.
The session should be realistic enough that feeding it to an LLM and saying
"continue this project" immediately works.

**Scenario:** Refactoring JWT auth middleware in a Node/Express API.
The dev discovers the token validation is scattered across 5 files,
decides to centralize it, abandons a Redis session approach in favor of
stateless JWT, and ends the session with the core middleware written but
route integration incomplete.

---

### samples/strategy-session.jsonl

A founder working through go-to-market positioning for a B2B dev tool.
10 points. Phases: exploration → exploration → convergence → crystallization.
Include: fossils for at least 2 abandoned positioning angles, insights about
the market, 3+ open items for follow-up.

**Scenario:** Founder is positioning a database migration tool. Initially
explores "safety" angle (no data loss), then "speed" angle, then realizes
through conversation that the real insight is "developer confidence" —
migrations that devs aren't afraid to run. Session ends with positioning
crystallized but pricing and ICP still open.

---

### samples/learning-session.jsonl

Someone learning distributed consensus algorithms (Raft specifically).
10 points. Phases: orientation → exploration → exploration → convergence.
Include: files_out for generated study materials and a reference sheet,
insights capturing genuine "aha moments" about leader election and log
replication.

**Scenario:** Engineer needs to understand Raft to evaluate whether to use
etcd in their infrastructure. Works through the paper with the AI, gets
confused about log commitment rules, has a breakthrough when the AI uses
a voting analogy, ends with a solid mental model and a generated cheat sheet.

---

## Phase 3: Update WAI-State.json

Update `context.current_phase` to `"implementation"` and `context.next_actions`
to reflect the new build:
- Strip Next.js scaffold
- Build documentation structure
- Write all files per this spec
- Verify: all links resolve, samples are realistic, prompts are self-contained

---

## Phase 4: Update WAI-Lugs.jsonl

Append new lug entry for this work order:
```json
{"id":"trk-impl-v1","type":"work-order","title":"Tracks repo full implementation — doc-only build","status":"published","priority":"high","created_at":"2026-03-17","tags":["implementation","documentation","prompts","samples"]}
```

---

## Verify Checklist

Before declaring done:

- [ ] All Next.js scaffold removed
- [ ] `README.md` present at repo root with all 6 sections
- [ ] `spec/track-format.md` complete with schema table, phase vocabulary, example point
- [ ] `prompts/closing-request.md` — self-contained, works as raw URL instruction
- [ ] `prompts/prep-and-request.md` — self-contained, "collect tracks" trigger explained
- [ ] `prompts/active-collection.md` — self-contained, per-turn recording explained
- [ ] `samples/coding-session.jsonl` — valid JSONL, 10 points, realistic enough to demo portability
- [ ] `samples/strategy-session.jsonl` — valid JSONL, 10 points, fossils present
- [ ] `samples/learning-session.jsonl` — valid JSONL, 10 points, files_out present
- [ ] All internal links in README resolve
- [ ] All wheelwright.ai and framework repo links present
- [ ] `WAI-Spoke/WAI-State.json` updated
- [ ] `WAI-Spoke/WAI-Lugs.jsonl` updated with this work order

---

*Build order: Phase 0 (strip) → Phase 1 (dirs) → Phase 2 (files, README first) → Phase 3 (WAI state) → Phase 4 (lugs) → verify*
