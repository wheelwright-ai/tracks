---
id: stewardship-advisor
name: Stewardship Advisor
kind: advisor
entrypoints:
  - command.md
summary: Guard against scope drift and identity changes that need explicit acknowledgment.
use_cases:
  - scope_protection
  - drift_detection
  - foundation_evolution
objects:
  - WAI-Spoke/WAI-State.json
  - WAI-Spoke/WAI-State.md
description: >
  Detect scope drift and require explicit acknowledgment before enabling work
  that changes the wheel's identity, boundaries, or operating model.
inherits_from: Skills/advisors/SKILL.md
authoritative_command_path: Skills/advisors/stewardship/command.md
legacy_compatibility_paths:
  - WAI-Spoke/commands/wai-stewardship-advisor.md
---

# Stewardship Advisor

This advisor inherits defaults from `Skills/advisors/SKILL.md`.

Local overrides focus activation on scope drift, boundary changes, and identity
level shifts.
