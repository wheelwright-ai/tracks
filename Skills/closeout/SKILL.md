---
id: closeout
name: WAI Closeout
kind: utility
exposure:
  - user
  - agent
entrypoints:
  - command.md
use_cases:
  - session_end
  - handoff
  - signal_capture
  - state_preservation
objects:
  - WAI-Spoke/WAI-State.json
  - WAI-Spoke/WAI-State.md
  - WAI-Spoke/WAI-Lugs.jsonl
  - WAI-Spoke/WAI-Signals.jsonl
  - WAI-Spoke/WAI-Session-Summary.jsonl
  - WAI-Spoke/WAI-Session-Log.jsonl
  - WAI-Spoke/lugs/outbox/
  - WAI-Spoke/sessions/
description: >
  End-of-session protocol. Consolidates session work, captures signals, updates
  spoke state, and leaves an actionable handoff for the next agent.
composition:
  style: protocol
authoritative_command_path: Skills/closeout/command.md
legacy_compatibility_paths:
  - WAI-Spoke/commands/wai-closeout.md
notes:
  - This folder is the authoritative home of closeout behavior.
  - The legacy command path should remain a compatibility shim only.
---

# WAI Closeout

This skill owns the end-of-session preservation workflow.

## When It Should Trigger

- User asks to close out, wrap up, or prepare handoff
- Agent is ending a session and needs durable continuity

## What It Owns

- durable session summary
- signal extraction and teach generation
- state cleanup and next-session recommendation
- outbox delivery attempt

## Migration Status

- `Skills/closeout/command.md` is the source of truth
- `WAI-Spoke/commands/wai-closeout.md` is compatibility only
