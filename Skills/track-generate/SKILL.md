---
id: track-generate
name: WAI Track Generate
kind: utility
exposure:
  - user
  - agent
entrypoints:
  - command.md
use_cases:
  - portable_export
  - session_snapshot
  - handoff_artifact
objects:
  - spec/track-format.md
  - WAI-Spoke/sessions/
  - WAI-Spoke/WAI-Session-Log.jsonl
  - WAI_Track-*.jsonl
description: >
  Generate a portable WAI Track export from normalized session context using the
  repo's track format contract.
composition:
  style: generator
  calls_subskills:
    - chat-to-track
authoritative_command_path: Skills/track-generate/command.md
legacy_compatibility_paths:
  - WAI-Spoke/commands/wai-track-generate.md
notes:
  - This skill owns portable Track export behavior.
  - The legacy command path should remain a compatibility shim only.
---

# WAI Track Generate

This skill creates the external `WAI_Track-*.jsonl` artifact.

## When It Should Trigger

- User asks to collect, export, save, or generate a Track
- Another skill needs a portable session handoff artifact

## What It Depends On

- `Skills/chat-to-track/command.md` for turn-by-turn normalization
- `spec/track-format.md` for final export shape

## Migration Status

- `Skills/track-generate/command.md` is the source of truth
- `WAI-Spoke/commands/wai-track-generate.md` is compatibility only
