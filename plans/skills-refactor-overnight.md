# Skills Refactor Overnight Plan

## Goal

Fully transform the spoke overnight from a flat, command-file-oriented layout into a folder-based skill system where each capability lives in `Skills/<skill-id>/`.

This is a design cutover at the spoke level, not a tentative pilot.

## Current State

- `Skills/` exists as the first migration slice
- `wakeup` is already migrated as the first authoritative skill
- `WAI-Spoke/commands/wai.md` is already a compatibility shim
- `WAI-Spoke/WAI-Skills.jsonl` is transitional and incomplete
- `closeout` still exists only in the legacy command path
- advisor migration is only mocked via `stewardship`

## Target State

### Authoritative Layout

```text
Skills/
  index.jsonl
  SCHEMA.md
  README.md
  wakeup/
    SKILL.md
    command.md
  closeout/
    SKILL.md
    command.md
  track-generate/
    SKILL.md
    command.md
  chat-to-track/
    SKILL.md
    command.md
  advisors/
    SKILL.md
    stewardship/
      SKILL.md
      advisor.json
      command.md
    complexity/
      SKILL.md
      advisor.json
      command.md
    context/
      SKILL.md
      advisor.json
      command.md
    foundation/
      SKILL.md
      advisor.json
      command.md
    signal/
      SKILL.md
      advisor.json
      command.md
    lug/
      SKILL.md
      advisor.json
      command.md
```

### Legacy Layer

```text
WAI-Spoke/commands/
  wai.md
  wai-closeout.md
  wai-track-generate.md
  wai-chat-to-track.md
  wai-stewardship-advisor.md
  wai-complexity-advisor.md
  wai-context-advisor.md
  wai-foundation-advisor.md
  wai-signal-advisor.md
  wai-lug-advisor.md
```

Legacy command files may remain only as:
- thin aliases
- deprecation wrappers
- compatibility entrypoints

No legacy command file may remain authoritative.

## Transformation Standard

By morning:
- `Skills/` should read as the real architecture
- the registry and guide should align to `Skills/`
- no major capability should still be authored primarily in `WAI-Spoke/commands/`
- any remaining legacy files should be thin wrappers, aliases, or deprecation stubs only

## Invariants

- Do not revert or rewrite the prompt work already landed in `prompts/`
- `Skills/index.jsonl` is the router of record
- `SKILL.md` stays uppercase; `index.jsonl` stays lowercase
- This repo remains a documentation/prompt library, not an application
- Avoid adding runtime-heavy code or a build system
- Do not keep two authoritative copies of a migrated capability

## Non-Goals For Overnight Pass

- Full framework-wide migration
- Replacing hub/framework skill YAMLs
- Adding a generator script unless absolutely necessary
- Solving every pending hub teaching

## Critical Path

1. Lock the Skills schema and router conventions
2. Migrate `closeout`
3. Migrate `track-generate`
4. Migrate `chat-to-track`
5. Expand advisor folders and aliases
6. Rewrite `WAI-Spoke/WAI-Skills.jsonl` to fully mirror the new skill map
7. Rewrite `WAI-Guide.md` around the router and skill folders
8. Demote legacy command files to aliases/deprecation wrappers only

## Parallel Workstreams

### Workstream A: Schema and Router

**Owner:** Agent A  
**Write scope:** `Skills/README.md`, `Skills/SCHEMA.md`, `Skills/index.jsonl`

#### Tasks

1. Review current schema docs
2. Normalize field names across:
   - router entries
   - `SKILL.md` frontmatter
   - advisor override files
3. Decide whether extra router fields are required:
   - `status`
   - `inherits`
   - `tags`
   - `aliases`
4. Ensure examples in docs match the actual files on disk

#### Deliverable

- Stable schema docs
- Stable `Skills/index.jsonl`

#### Acceptance Criteria

- Every router entry points to a real skill folder
- Every example in docs reflects the actual schema
- No uppercase router filename remains

---

### Workstream B: Core Skill Migration

**Owner:** Agent B  
**Write scope:** `Skills/closeout/`, `Skills/track-generate/`, `Skills/chat-to-track/`, matching legacy aliases in `WAI-Spoke/commands/`

#### Tasks

1. Create:
   - `Skills/closeout/SKILL.md`
   - `Skills/closeout/command.md`
   - `Skills/track-generate/SKILL.md`
   - `Skills/track-generate/command.md`
   - `Skills/chat-to-track/SKILL.md`
   - `Skills/chat-to-track/command.md`
2. Convert legacy command docs into aliases or deprecation wrappers:
   - `WAI-Spoke/commands/wai-closeout.md`
   - `WAI-Spoke/commands/wai-track-generate.md`
   - `WAI-Spoke/commands/wai-chat-to-track.md`
3. Coordinate with Agent A for router entries

#### Deliverable

- Three migrated core/utility skills plus non-authoritative legacy entrypoints

#### Acceptance Criteria

- Skill folders are authoritative
- Legacy command files are aliases or deprecation wrappers only
- Each alias points to a real `Skills/<id>/command.md`
- No authoritative procedural content remains duplicated in the legacy command path

---

### Workstream C: Advisor Migration

**Owner:** Agent C  
**Write scope:** `Skills/advisors/`, legacy advisor aliases in `WAI-Spoke/commands/`

#### Tasks

1. Keep `Skills/advisors/SKILL.md` as the inheritance parent
2. Add advisor folders for:
   - `complexity`
   - `context`
   - `foundation`
   - `signal`
   - `lug`
3. Each child gets:
   - `SKILL.md`
   - `advisor.json`
   - `command.md`
4. Create aliases/deprecation wrappers:
   - `wai-complexity-advisor.md`
   - `wai-context-advisor.md`
   - `wai-foundation-advisor.md`
   - `wai-signal-advisor.md`
   - `wai-lug-advisor.md`

#### Deliverable

- Complete advisor folder model with inheritance + local overrides

#### Acceptance Criteria

- All advisor folders inherit from `Skills/advisors/SKILL.md`
- Each child has at least one meaningful override in `advisor.json`
- Legacy advisor command names resolve cleanly to the new folders
- Legacy advisor files do not remain authoritative

---

### Workstream D: Registry and Guide Alignment

**Owner:** Agent D  
**Write scope:** `WAI-Spoke/WAI-Skills.jsonl`, `WAI-Spoke/WAI-Guide.md`

#### Tasks

1. Replace the placeholder wakeup-only registry with a full transitional mirror of the new skill map
2. Make each registry entry reference:
   - `skill_path`
   - `entrypoint`
   - legacy `command_file` when present
3. Rewrite `WAI-Guide.md` as a lightweight pointer to:
   - `Skills/index.jsonl`
   - `Skills/SCHEMA.md`
   - major skill folders

#### Deliverable

- Registry fully aligned to the folder model
- Guide rewritten around the router instead of legacy commands

#### Acceptance Criteria

- `WAI-Spoke/WAI-Skills.jsonl` parses as JSONL
- `WAI-Guide.md` explicitly states that `Skills/` is authoritative
- `WAI-Guide.md` does not present `WAI-Spoke/commands/` as the primary capability surface

---

### Workstream E: State, Narrative, and Cleanup

**Owner:** Agent E  
**Write scope:** `WAI-Spoke/WAI-State.json`, `WAI-Spoke/WAI-State.md`, `plans/`

#### Tasks

1. Update `WAI-State.json`:
   - next actions
   - blockers
   - insights
   - evolution log
2. Update `WAI-State.md` evolution log
3. Add or revise plan docs as migration advances
4. Capture unresolved questions discovered by other agents

#### Deliverable

- WAI state files reflect a full design migration honestly

#### Acceptance Criteria

- No stale references claiming a legacy command file is authoritative
- Evolution log documents the cutover clearly
- Next actions reflect the actual remaining work

---

### Workstream F: Verification

**Owner:** Agent F  
**Write scope:** `plans/verification-notes.md` only

#### Tasks

1. Validate:
   - `WAI-State.json` with `jq`
   - `WAI-Skills.jsonl` line-by-line with `jq`
   - `Skills/index.jsonl` line-by-line with `jq`
2. Check every router path exists
3. Check every alias points at a real skill path
4. Check there are no duplicate authoritative copies for migrated skills
5. Report any remaining authoritative legacy command content

#### Deliverable

- Verification note with pass/fail and findings

#### Acceptance Criteria

- Machine-readable files parse
- Router entries resolve
- Alias targets resolve
- No duplicate authoritative copies exist for migrated skills
- Remaining legacy command files are non-authoritative only

## Recommended Execution Order

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

## File Ownership Rules

- No two agents should write the same file
- `Skills/index.jsonl` belongs only to Agent A unless explicitly reassigned
- `WAI-Spoke/WAI-Skills.jsonl` belongs only to Agent D
- `WAI-State.json` and `WAI-State.md` belong only to Agent E
- Verification agent is read-only except for its own note file

## Open Questions To Resolve During Refactor

1. Should `WAI-Spoke/WAI-Skills.jsonl` become generated from `Skills/index.jsonl` immediately, or remain mirrored manually for one transition window?
2. Should user-facing `wai-*` command files remain as aliases indefinitely, or should the repo explicitly deprecate them after this migration?
3. Should `command.md` always be singular, or can a skill expose multiple entry docs?
4. Should advisor inheritance support nested parents beyond `Skills/advisors/`?

## Morning Review Checklist

- Does `Skills/index.jsonl` look like the true router?
- Are `closeout`, `track-generate`, and `chat-to-track` migrated?
- Are advisor folders present and internally consistent?
- Does `WAI-Guide.md` point to `Skills/` as the authority?
- Are legacy command files non-authoritative only?
- Are state files honest about what changed?
