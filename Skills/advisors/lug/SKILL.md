---
id: lug-advisor
name: Lug Advisor
kind: advisor
entrypoints:
  - command.md
summary: Watch task routing and lug lifecycle health so work lands in the right queue.
description: >
  Detect routing mistakes, missing lug updates, and weak lifecycle hygiene so
  durable work tracking stays trustworthy.
inherits_from: Skills/advisors/SKILL.md
authoritative_command_path: Skills/advisors/lug/command.md
legacy_compatibility_paths:
  - WAI-Spoke/commands/wai-lug-advisor.md
---

# Lug Advisor

This advisor inherits defaults from `Skills/advisors/SKILL.md`.

Local overrides focus on routing quality, lifecycle transitions, and durable
task hygiene.
