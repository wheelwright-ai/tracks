---
id: foundation-advisor
name: Foundation Advisor
kind: advisor
entrypoints:
  - command.md
summary: Protect declared project foundations and surface changes needing explicit confirmation.
description: >
  Detect requests that alter core constraints, operating assumptions, or
  foundational decisions and require them to be handled deliberately.
inherits_from: Skills/advisors/SKILL.md
authoritative_command_path: Skills/advisors/foundation/command.md
legacy_compatibility_paths:
  - WAI-Spoke/commands/wai-foundation-advisor.md
---

# Foundation Advisor

This advisor inherits defaults from `Skills/advisors/SKILL.md`.

Local overrides make foundation-sensitive changes high-scrutiny and explicitly
confirmed.
