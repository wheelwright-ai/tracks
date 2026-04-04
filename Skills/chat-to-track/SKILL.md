---
id: chat-to-track
name: Chat To Track
kind: utility
exposure:
  - agent
  - subagent
entrypoints:
  - command.md
use_cases:
  - normalization
  - session_capture
  - track_preparation
objects:
  - WAI-Spoke/WAI-Session-Log.jsonl
  - WAI-Spoke/sessions/
  - spec/track-format.md
description: >
  Convert raw conversation or session-log context into turn-by-turn track-ready
  records that can be stored internally or handed to track generation.
composition:
  style: transformer
authoritative_command_path: Skills/chat-to-track/command.md
legacy_compatibility_paths:
  - WAI-Spoke/commands/wai-chat-to-track.md
notes:
  - This skill normalizes chat context; it does not own the final portable export wrapper.
  - The legacy command path should remain a compatibility shim only.
---

# Chat To Track

This skill turns raw session context into structured turn records.

## When It Should Trigger

- A session needs turn-by-turn normalization before Track export
- Wakeup or another workflow needs to recover portable continuity from chat state

## What It Does Not Own

- final `WAI_Track-*.jsonl` export packaging
- closeout state updates

## Migration Status

- `Skills/chat-to-track/command.md` is the source of truth
- `WAI-Spoke/commands/wai-chat-to-track.md` is compatibility only
