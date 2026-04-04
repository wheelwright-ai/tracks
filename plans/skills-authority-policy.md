# Skills Authority Policy

Date: 2026-03-19
Stage: 3 - Authority Policy

## Purpose

This policy settles long-term ownership for the post-cutover skill system without reopening the architecture decision. `Skills/` remains the authoritative skill system for Tracks. `WAI-Spoke/` keeps only the spoke-local state and compatibility surfaces that still need to exist during the transition.

## Authority Model

- `Skills/` is the authoritative skill namespace for this repo.
- `Skills/index.jsonl` is the routing and discovery authority.
- Each routed skill folder is the behavior authority for that skill.
- `WAI-Spoke/WAI-Skills.jsonl` is a transitional mirror only.
- Legacy `WAI-Spoke/commands/wai-*.md` files are compatibility aliases only.

## Surface Ownership

### Router

- Authoritative file: `Skills/index.jsonl`
- Owns: skill ids, status, kind, exposure, folder path, entrypoint, inheritance metadata, and `legacy_aliases`
- Operational rule: add, remove, rename, activate, retire, or remap skills in `Skills/index.jsonl` first
- Operational rule: if a mirror or alias disagrees with `Skills/index.jsonl`, the router wins

### Skill Folders

- Authoritative location: `Skills/<skill>/` and `Skills/advisors/<skill>/`
- Owns: behavior, instructions, entry documents, and advisor-specific overrides stored in the folder
- Operational rule: edit `SKILL.md`, `command.md`, and allowed local override files in the skill folder when behavior changes
- Operational rule: do not move behavior back into `WAI-Spoke/commands/`

### Guide

- Authoritative guide for spoke startup: `WAI-Spoke/WAI-Guide.md`
- Owns: read order, operator guidance, and how assistants should resolve skill references at runtime
- Operational rule: the guide may describe the system, but it does not override router or skill-folder authority

### Mirrored Registry

- Transitional mirror: `WAI-Spoke/WAI-Skills.jsonl`
- Owns only: spoke-local compatibility fields still needed by consumers that expect a registry under `WAI-Spoke/`
- Does not own: routing policy, canonical aliases, skill status decisions, or behavior
- Operational rule: treat it as derived from `Skills/index.jsonl`
- Operational rule: prefer generated or mechanically synchronized maintenance; do not independently author new skills there
- Operational rule: any manual edit is only acceptable when keeping the mirror in lockstep with a router change made in the same change set

### Alias Wrappers

- Compatibility-only files: `WAI-Spoke/commands/wai.md` and `WAI-Spoke/commands/wai-*.md`
- Own only: legacy entrypoint continuity for users or tooling still calling old command names
- Do not own: behavior, policy, routing, inheritance, or the source text for a skill
- Operational rule: wrappers must resolve back to the routed skill named in `Skills/index.jsonl`
- Operational rule: new behavior must never be added only to an alias wrapper

## Derived And Alias Rules

- Authoritative: `Skills/index.jsonl`, skill folders under `Skills/`, and the behavior documents they point to
- Derived or mirrored: `WAI-Spoke/WAI-Skills.jsonl`
- Alias-only: legacy `WAI-Spoke/commands/wai-*.md` wrappers
- If a consumer needs `command_file`, that field is compatibility data, not authority
- If a wrapper path changes, update `legacy_aliases` in `Skills/index.jsonl` first and then synchronize dependent mirrors

## Alias Transition Policy

- Legacy `wai-*` wrappers remain compatibility aliases for one transition window.
- During that window, wrappers must stay short, non-authoritative, and limited to pointing callers at the routed `Skills/` entry.
- A wrapper may remain even after most callers migrate if it still protects an active consumer or verification path.
- Retire a wrapper only after both conditions hold: verification remains green without depending on it, and known consumers have been updated off the alias.
- Do not restore behavior text, routing logic, or policy ownership to a wrapper while the alias exists.

## Advisor Inheritance Policy

- `Skills/advisors/SKILL.md` defines advisor defaults for behavior, exposure, safety, and mode posture.
- Child advisor folders inherit from that parent by default and should document only advisor-specific behavior in their own folder.
- Child `advisor.json` files are override files, not full advisor definitions.
- Allowed child override fields are limited to `exposure`, `watchers`, `safety_level`, and `modes`.
- If a child does not declare one of those fields, the parent default stays in effect.
- Child `advisor.json` files should not redefine entrypoints, advisory status, auto-trigger posture, or inheritance behavior.

## Change Procedure

1. Change behavior in the relevant `Skills/` folder.
2. Update `Skills/index.jsonl` if routing, exposure, aliases, status, or inheritance changed.
3. Synchronize `WAI-Spoke/WAI-Skills.jsonl` only as a mirror of the router.
4. Keep legacy `wai-*` wrappers aligned only when an existing alias must continue to resolve during the transition window.
5. Update spoke state or planning docs if the operational posture changed.

## Transition Posture

- The transition is still active because spoke-local consumers may read `WAI-Spoke/WAI-Skills.jsonl` and legacy `wai-*` wrappers.
- The intended end state is a generated or mechanically synchronized mirror, not an independently maintained second registry.
- Alias wrappers remain during one transition window for compatibility and retire only after verification stays green and callers are confirmed migrated.

## Out Of Scope For This Stage

- Changing any `Skills/` file contents or schema
- Editing `WAI-Spoke/WAI-Guide.md`
- Deciding the exact retirement date for legacy aliases beyond the transition-window rule
- Choosing the implementation mechanism for mirror generation or synchronization
