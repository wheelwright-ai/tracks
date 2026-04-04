---
id: wakeup
name: WAI Wakeup
kind: core
exposure:
  - user
  - agent
entrypoints:
  - command.md
use_cases:
  - session_start
  - context_resume
  - teaching_discovery
  - briefing_generation
objects:
  - WAI-Spoke/WAI-Guide.md
  - WAI-Spoke/WAI-State.json
  - WAI-Spoke/WAI-State.md
  - WAI-Spoke/WAI-Lugs.jsonl
  - WAI-Spoke/WAI-Signals.jsonl
  - WAI-Spoke/WAI-Skills.jsonl
  - WAI-Spoke/seed/processed/
  - WAI-Spoke/sessions/
description: >
  Start-of-session protocol. Loads canonical state, reconciles hub teachings,
  checks active work, initializes the current session, and produces a ready-to-work briefing.
composition:
  style: orchestrator
  calls_subskills:
    - teaching-reconciliation
    - chat-to-track
    - track-generate
authoritative_command_path: Skills/wakeup/command.md
legacy_compatibility_paths:
  - WAI-Spoke/commands/wai.md
notes:
  - This is intentionally a protocol skill, not a single atomic action.
  - The folder model lets a multi-step process stay coherent without becoming a monolithic global command file.
  - The legacy command path should remain a shim only.
---

# WAI Wakeup

This skill is the session-start orchestrator and the authoritative home of the wakeup protocol.

It is a good example of why a skill may need multiple files:
- `SKILL.md` describes the capability
- `command.md` contains the operating procedure
- future support files can hold helpers, references, and examples

## Exposure

- `user`: directly invokable as a user-facing capability
- `agent`: selectable internally by the main agent

## When It Should Trigger

- User asks to wake up, resume, start work, or inspect the current spoke state
- Agent detects the start of a new session in a Wheelwright spoke

## What It Should Not Do

- It should not own closeout
- It should not define every advisor inline
- It should not become the dumping ground for unrelated protocol behavior

## Migration Status

- `Skills/wakeup/command.md` is the source of truth
- `WAI-Spoke/commands/wai.md` is compatibility only
