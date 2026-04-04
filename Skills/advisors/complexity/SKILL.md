---
id: complexity-advisor
name: Complexity Advisor
kind: advisor
entrypoints:
  - command.md
summary: Flag unnecessary complexity and steer work toward simpler viable solutions.
description: >
  Detect overbuilt plans, premature abstraction, and avoidable process overhead
  before they harden into the work.
inherits_from: Skills/advisors/SKILL.md
authoritative_command_path: Skills/advisors/complexity/command.md
legacy_compatibility_paths:
  - WAI-Spoke/commands/wai-complexity-advisor.md
---

# Complexity Advisor

This advisor inherits defaults from `Skills/advisors/SKILL.md`.

Local overrides focus activation on over-design, excess abstraction, and
disproportionate process.
