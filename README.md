# Tracks

> Every AI conversation produces intellectual work. When the session ends, that work is trapped. Track files free it and give it back to you.

[![Wheelwright AI](https://img.shields.io/badge/Wheelwright-AI-orange)](https://wheelwright.ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Framework](https://img.shields.io/badge/framework-wheelwright--ai%2Fframework-blue)](https://github.com/wheelwright-ai/framework)

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

Every productive AI session generates real intellectual work: architectural
decisions, strategy pivots, research synthesis, creative breakthroughs. That work
is yours — but right now it is trapped inside the chat interface of whatever
platform you used. When the session ends, the context evaporates. The next session
starts cold. A different model cannot access it. A colleague cannot pick up where
you left off.

**Track files free your intellectual product and give it back to you.**

Take it to any model, any platform, any person. Use it to seed a new project,
hand off a half-finished idea, or build a library of knowledge that compounds
across months of work. No provider is giving you this. Track files are how you
claim what is already yours.

| Use Case | What It Unlocks |
|----------|----------------|
| **Switch models** | Export a Track from Claude, resume in GPT or Gemini with zero lost context |
| **Merge conversations** | Two separate threads on related topics — feed both Tracks to a new session and work from combined knowledge |
| **Async handoff** | Hand a project to another person or AI instance mid-stream with full fidelity |
| **Knowledge library** | Accumulate Tracks as a personal or team knowledge base — searchable, reusable, composable |
| **Cold start prevention** | Never brief an AI from scratch again — feed a Track and skip the ramp-up entirely |
| **Pattern detection** | Review Tracks across sessions and surface recurring decisions, bottlenecks, insights |

---

## Three Ways to Generate a Track

### Start here — Closing Request

Already had a conversation? Extract a Track from it after the fact. Drop the
prompt into any existing session and get a Track file of what happened. This is
the fastest way to try it — no setup, works retroactively on any chat.

**[prompts/closing-request.md](prompts/closing-request.md)**

Give an LLM the raw URL of that file and say "follow these instructions." It will
understand the assignment.

---

### Next level — Prep and Request

Starting a new session? Give the agent the prompt at the beginning. Work normally.
Say **"collect tracks"** when you want a snapshot. The agent knows the format in
advance and produces higher-fidelity output because it is primed from turn one.

**[prompts/prep-and-request.md](prompts/prep-and-request.md)**

---

### Full integration — Active Collection

The agent records a WAI Point on every single turn, in real time. Nothing to
remember, nothing to request. This is what Wheelwright AI does natively — this
prompt lets you approximate it manually.

**[prompts/active-collection.md](prompts/active-collection.md)**

---

## The Wheelwright Advantage

The prompts in this repo get you the Track. Wheelwright AI gets you the system.

- **Active collection is built in** — every Wheelwright session records automatically, nothing to trigger
- **Cross-spoke continuity** — a strategy session's Track seeds an implementation session in a different project without any manual transfer
- **Historian advisor** — reviews your Track library over time and surfaces patterns you would never think to look for: recurring decision points, bottlenecks, drift from original intent
- **Track files as persistent intelligence** — the foundation of a project context that outlives any individual session or model

The manual technique in this repo is available to anyone, right now, with no
tooling. The Wheelwright framework is what happens when you stop doing it manually.

**[wheelwright.ai](https://wheelwright.ai) | [wheelwright-ai/framework](https://github.com/wheelwright-ai/framework)**

---

## Track Format

Track files are JSONL. One line per turn. The first line is a `session_start`
event, the last is a `session_end` event, and every line between is a WAI Point.

See **[spec/track-format.md](spec/track-format.md)** for the complete format specification.

See **[samples/](samples/)** for real examples you can feed to any LLM today to
demonstrate portability.

---

## Track Viewer

A zero-build web viewer now lives in **[viewer/](viewer/)**.

It supports:
- local Track file upload
- direct loading by relative path or URL
- turn-by-turn timeline navigation
- search and phase filtering
- optional library mode via a JSON or JSONL registry that points at Track files
- optional hub mode that can ingest `hub-registry.json` or `wheel-projects.json`
  and resolve Track files from `WAI-Spoke/sessions/` when your server exposes
  those wheel paths

Quick start:

```bash
cd /home/mario/projects/wheelwright/tracks
python3 -m http.server 8000
```

Then open:
- `http://localhost:8000/viewer/`
- `http://localhost:8000/viewer/?track=../samples/coding-session.jsonl`
- `http://localhost:8000/viewer/?registry=./library.example.json`

For hub registry mode:

- serve a parent directory that includes both `tracks/` and `hub/`
- or serve `/home/mario/projects` and set:
  - server root filesystem path: `/home/mario/projects`
  - server root URL prefix: `/`

Then the viewer can map absolute wheel paths from `hub-registry.json` or
`wheel-projects.json` back into browser-fetchable URLs and auto-discover Track
files under each wheel's `WAI-Spoke/sessions/` directory.

---

## Improve This

These prompts are a starting point. Adapt them to your domain — adjust the schema,
add fields that matter for your work, tune the phase vocabulary. When you find
something that works better, open a PR.

The optimal path is through Wheelwright, where collection is automatic and Tracks
compose across projects. But the technique belongs to everyone.

---

## Coming Soon — MCP Integration

A Tracks MCP server is on the roadmap. Once installed, any MCP-compatible LLM
will understand the Track format, generate Tracks automatically, and surface them
without any user prompting. Star this repo to follow progress.

---

## License

MIT — see [LICENSE](LICENSE)

**Built by [Wheelwright AI](https://wheelwright.ai)**
