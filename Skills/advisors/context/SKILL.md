---
id: context-advisor
name: Context Advisor
kind: advisor
entrypoints:
  - command.md
summary: Guard against context loss, overflow, and weak handoff conditions.
description: >
  Detect when active work is at risk of losing important context and advise on
  compaction, checkpoints, or handoff structure.
inherits_from: Skills/advisors/SKILL.md
authoritative_command_path: Skills/advisors/context/command.md
legacy_compatibility_paths:
  - WAI-Spoke/commands/wai-context-advisor.md
---

# Context Advisor

This advisor inherits defaults from `Skills/advisors/SKILL.md`.

Local overrides emphasize context pressure, missing checkpoints, and weak resume
state.
