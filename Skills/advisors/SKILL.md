---
id: advisors
name: Advisor Defaults
kind: advisor-group
exposure:
  - agent
default_entrypoints:
  - command.md
default_behavior:
  advisory: true
  auto_trigger: true
  inherit_to_children: true
  default_exposure:
    - agent
  default_safety_level: 10
  default_modes:
    execution: passive
    interactive: active
    planning: active
    review: active
    deploy: active
description: >
  Parent defaults for advisor skills. Child advisor folders inherit these
  defaults unless they override them with advisor.json.
---

# Advisor Defaults

This folder defines the default advisor posture for all child advisors.

- Default behavior: advisory, auto-triggered, inherited by child advisor folders.
- Default exposure: `agent`.
- Default safety level: `10`.
- Default modes: execution passive; interactive, planning, review, and deploy active.

Child folders inherit these defaults from `Skills/advisors/SKILL.md`.

Use `advisor.json` only for narrow child overrides.

- Required shape: `{"inherits": true, "overrides": {...}}`
- Allowed override keys: `exposure`, `watchers`, `safety_level`, `modes`
- Do not redefine entrypoints, advisory status, auto-trigger posture, or inheritance rules in child `advisor.json` files.
- If an allowed key is omitted, the parent default remains in effect.
