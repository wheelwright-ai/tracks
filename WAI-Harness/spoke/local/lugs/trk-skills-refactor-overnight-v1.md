---
_lug:
  id: "trk-skills-refactor-overnight-v1"
  type: "work-order"
  title: "Tracks — Skills Refactor Overnight Execution"
  status: "ready-to-execute"
  version: "1.1.0"
  created: "2026-03-19"
  authored_by: "gpt-5-codex"
  destination: "opencode multi-agent run"
  safe_to_auto_adopt: false
  behavior_directive:
    what_this_is: >
      A parallel execution brief for fully transforming this spoke from a flat
      command layout into a folder-based Skills system. It defines target
      architecture, workstream ownership, model recommendations, acceptance
      criteria, and merge order.
    what_this_is_not: >
      Not a request to redesign the product. Not a request to revert prompt work.
      Not a request to preserve legacy command files as authoritative artifacts.
    prerequisite: >
      Read plans/skills-refactor-overnight.md and
      plans/skills-refactor-workstreams.jsonl before assigning agents.
---

# Tracks — Skills Refactor Overnight Execution

## Primary Sources

- [plans/skills-refactor-overnight.md](/home/mario/projects/wheelwright/tracks/plans/skills-refactor-overnight.md)
- [plans/skills-refactor-workstreams.jsonl](/home/mario/projects/wheelwright/tracks/plans/skills-refactor-workstreams.jsonl)
- [Skills/SCHEMA.md](/home/mario/projects/wheelwright/tracks/Skills/SCHEMA.md)
- [Skills/index.jsonl](/home/mario/projects/wheelwright/tracks/Skills/index.jsonl)

## Objective

Fully transform this spoke overnight to a folder-based `Skills/` architecture where each capability is an inspectable on-disk unit:

```text
Skills/
  index.jsonl
  <skill-id>/
    SKILL.md
    command.md
```

Legacy command files may remain only as thin aliases or deprecation wrappers. They must not remain authoritative.

## Constraints

- Do not revert existing edits in `prompts/`, `WAI-Spoke/`, or `Skills/`
- `Skills/index.jsonl` is authoritative for routing
- `SKILL.md` remains uppercase
- `index.jsonl` remains lowercase
- This repo remains a documentation/prompt library, not an app
- No migrated capability may remain primarily authored in `WAI-Spoke/commands/`

## Recommended Models

Use these model/task pairings for best cost/quality balance in opencode:

| Agent | Workstream | Recommended Model | Reasoning | Why |
|------|------------|-------------------|-----------|-----|
| A | Schema and router | `gpt-5.4` | `high` | Best for contract design, naming consistency, and migration guardrails |
| B | Core skill migration | `gpt-5.3-codex` | `high` | Best fit for moving command docs into skill folders without losing technical detail |
| C | Advisor migration | `gpt-5.3-codex` | `high` | Similar migration work, many files, careful inheritance consistency needed |
| D | Registry and guide alignment | `gpt-5.4-mini` | `medium` | Strong enough for schema-aligned docs/registry work without paying full frontier cost |
| E | State and narrative | `gpt-5.4-mini` | `medium` | Good for precise but lower-risk metadata and plan updates |
| F | Verification | `gpt-5.1-codex-mini` | `medium` | Cheap and sufficient for file existence, parse checks, and alias validation |

If you want one-model simplicity instead of tuning:
- Use `gpt-5.3-codex` for B/C
- Use `gpt-5.4-mini` for A/D/E
- Use `gpt-5.1-codex-mini` for F

## Workstream Ownership

### Agent A — Schema and Router

**Model:** `gpt-5.4`  
**Reasoning:** `high`  
**Write scope:**
- `Skills/README.md`
- `Skills/SCHEMA.md`
- `Skills/index.jsonl`

**Mission:**
- normalize the skill contract
- settle router field names
- ensure docs and examples match the actual schema

**Must not edit:**
- `WAI-Spoke/WAI-Skills.jsonl`
- `WAI-Spoke/WAI-State.json`
- `WAI-Spoke/WAI-State.md`

### Agent B — Core Skill Migration

**Model:** `gpt-5.3-codex`  
**Reasoning:** `high`  
**Write scope:**
- `Skills/closeout/`
- `Skills/track-generate/`
- `Skills/chat-to-track/`
- `WAI-Spoke/commands/wai-closeout.md`
- `WAI-Spoke/commands/wai-track-generate.md`
- `WAI-Spoke/commands/wai-chat-to-track.md`

**Mission:**
- migrate legacy command docs into authoritative skill folders
- leave legacy paths as aliases or deprecation wrappers only

**Must not edit:**
- `Skills/index.jsonl` unless coordinated with Agent A

### Agent C — Advisor Migration

**Model:** `gpt-5.3-codex`  
**Reasoning:** `high`  
**Write scope:**
- `Skills/advisors/`
- `WAI-Spoke/commands/wai-complexity-advisor.md`
- `WAI-Spoke/commands/wai-context-advisor.md`
- `WAI-Spoke/commands/wai-foundation-advisor.md`
- `WAI-Spoke/commands/wai-signal-advisor.md`
- `WAI-Spoke/commands/wai-lug-advisor.md`

**Mission:**
- flesh out advisor folders under the inheritance model
- create meaningful `advisor.json` overrides
- keep parent defaults centralized

### Agent D — Registry and Guide Alignment

**Model:** `gpt-5.4-mini`  
**Reasoning:** `medium`  
**Write scope:**
- `WAI-Spoke/WAI-Skills.jsonl`
- `WAI-Spoke/WAI-Guide.md`

**Mission:**
- align the registry fully to the folder-based model
- rewrite the guide as a pointer to the router and skills

**Depends on:**
- Agent A
- core naming from Agent B

### Agent E — State and Narrative

**Model:** `gpt-5.4-mini`  
**Reasoning:** `medium`  
**Write scope:**
- `WAI-Spoke/WAI-State.json`
- `WAI-Spoke/WAI-State.md`
- `plans/`

**Mission:**
- keep the state honest about the migration
- update evolution logs, blockers, and next actions
- capture unresolved questions for morning review

### Agent F — Verification

**Model:** `gpt-5.1-codex-mini`  
**Reasoning:** `medium`  
**Write scope:**
- `plans/verification-notes.md`

**Mission:**
- parse-check JSON and JSONL
- verify router paths exist
- verify alias targets exist
- report duplicate-authority risks
- report any remaining authoritative legacy command content

**This agent is read-only except for its own note file.**

## Execution Order

Run in this order:

1. Agent A starts immediately
2. Agent B starts immediately
3. Agent C starts immediately
4. Agent D starts after A and B stabilize naming
5. Agent E starts after A stabilizes the schema
6. Agent F runs last

## Merge Order

1. A
2. B
3. C
4. D
5. E
6. F

## Acceptance Criteria

Morning success means:

1. `Skills/index.jsonl` is the real router
2. `closeout`, `track-generate`, and `chat-to-track` exist as skill folders
3. legacy command files are aliases or deprecation wrappers only
4. advisor folders exist with inheritance plus local overrides
5. `WAI-Spoke/WAI-Skills.jsonl` parses and references `skill_path`
6. `WAI-Guide.md` points to `Skills/` as authority
7. `WAI-State.json` and `WAI-State.md` describe the migration accurately
8. verification notes call out any remaining duplicate-authority or routing issues
9. no major capability remains authored primarily in the flat command directory

## Explicit Warnings For Agents

- Do not create overlapping write ownership
- Do not make `WAI-Spoke/commands/*.md` authoritative again
- Do not invent a runtime or build system
- Do not remove old files unless they are explicitly being replaced by aliases or deprecation wrappers
- Do not rewrite prompt content unless a task explicitly says so

## Morning Handoff

When the overnight run is complete, hand back:
- changed file list
- verification notes
- unresolved questions
- any conflicts between schema, registry, aliases, and guide
