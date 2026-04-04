# Skills Schema

This file defines the authoritative `Skills/` contract.

## 1. Filesystem Contract

```text
Skills/
  index.jsonl
  <skill-id>/
    SKILL.md
    command.md
```

Advisor children extend that shape:

```text
Skills/
  advisors/
    SKILL.md
    <advisor-id>/
      SKILL.md
      advisor.json
      command.md
```

`index.jsonl` is lowercase by rule. `SKILL.md` is uppercase by rule.

## 2. Router Contract: `Skills/index.jsonl`

One JSON object per line.

Required fields for routed skills:
- `id`
- `kind`
- `skill_path`
- `skill_file`
- `entrypoint`
- `status`
- `summary`

Optional fields:
- `exposure`
- `inherits_from`
- `override_file`
- `legacy_aliases`
- `tags`

Field rules:
- `skill_path` is the folder root, for example `Skills/wakeup`.
- `skill_file` names the canonical definition file and should be `SKILL.md`.
- `entrypoint` names the default executable doc and should be `command.md`.
- `inherits_from` points to the parent `SKILL.md` when inheritance is part of the contract.
- `override_file` is used only for advisor children and should be `advisor.json`.
- `status` may be `active`, `planned`, `prototype`, or `deprecated`.

Example core entry:

```jsonl
{"id":"wakeup","kind":"core","skill_path":"Skills/wakeup","skill_file":"SKILL.md","entrypoint":"command.md","status":"active","exposure":["user","agent"],"legacy_aliases":["WAI-Spoke/commands/wai.md"],"summary":"Session-start orchestration."}
```

Example advisor entry:

```jsonl
{"id":"stewardship-advisor","kind":"advisor","skill_path":"Skills/advisors/stewardship","skill_file":"SKILL.md","entrypoint":"command.md","status":"active","exposure":["agent","subagent"],"inherits_from":"Skills/advisors/SKILL.md","override_file":"advisor.json","legacy_aliases":["WAI-Spoke/commands/wai-stewardship-advisor.md"],"summary":"Detect scope drift before identity or boundary changes."}
```

## 3. `SKILL.md` Frontmatter Contract

Each `SKILL.md` starts with YAML frontmatter followed by markdown body text.

Required frontmatter for routed skills:
- `id`
- `name`
- `kind`
- `entrypoints`
- `description`

Recommended frontmatter for routed skills:
- `exposure`
- `use_cases`
- `objects`
- `summary`
- `inherits_from`
- `authoritative_command_path`
- `legacy_compatibility_paths`
- `composition`
- `notes`

Required frontmatter for inheritance parents such as `Skills/advisors/SKILL.md`:
- `id`
- `name`
- `kind`
- `description`
- `default_entrypoints`
- `default_behavior`

Rules:
- `id` should match the router entry id for routed skills.
- `kind` should match the router entry kind.
- `entrypoints` is an array; today it should contain `command.md`.
- `summary`, when present, should align with the router summary.
- `authoritative_command_path`, when present, should resolve to `<skill_path>/command.md`.
- Advisor children should set `inherits_from: Skills/advisors/SKILL.md`.
- Advisor children may omit `exposure` in frontmatter if exposure is inherited and resolved in `advisor.json` and the router.

Minimal routed skill example:

```yaml
---
id: closeout
name: WAI Closeout
kind: utility
entrypoints:
  - command.md
summary: End-of-session preservation and handoff.
description: >
  Preserve session state, write durable outputs, and leave the spoke ready for
  the next agent.
authoritative_command_path: Skills/closeout/command.md
legacy_compatibility_paths:
  - WAI-Spoke/commands/wai-closeout.md
---
```

Minimal advisor child example:

```yaml
---
id: context-advisor
name: Context Advisor
kind: advisor
entrypoints:
  - command.md
summary: Guard against context loss and overloaded sessions.
description: >
  Detect context-risk conditions and advise on compaction, tracking, or resume
  strategy.
inherits_from: Skills/advisors/SKILL.md
---
```

## 4. Advisor Override Contract: `advisor.json`

`advisor.json` is only for advisor child folders.

Required fields:
- `inherits`
- `overrides`

Allowed override keys:
- `advisory`
- `auto_trigger`
- `exposure`
- `watchers`
- `safety_level`
- `modes`

Rules:
- `inherits` should be `true` for the current single-parent model.
- `overrides` contains only the child-specific differences from `Skills/advisors/SKILL.md`.
- `exposure` here is the resolved runtime exposure for the advisor.
- `watchers` is an array of trigger patterns.
- `modes` is an object keyed by operating mode.

Example:

```json
{
  "inherits": true,
  "overrides": {
    "exposure": ["agent", "subagent"],
    "watchers": ["context.*overflow", "resume.*risk"],
    "safety_level": 9,
    "modes": {
      "execution": "passive",
      "interactive": "active",
      "planning": "active",
      "review": "active",
      "deploy": "passive"
    }
  }
}
```

## 5. Normalization Rules

- `id` and `kind` should agree between the router and `SKILL.md`.
- The router is the discoverability surface; `SKILL.md` is the authoring surface.
- The router should carry resolved advisor metadata needed for routing.
- `advisor.json` should only express inheritance overrides, not duplicate the whole skill definition.
- Legacy command files are not authoritative and should appear only as compatibility paths or aliases.
