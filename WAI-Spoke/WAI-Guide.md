# Tracks - AI Assistant Guide

## Read Order

1. `WAI-Spoke/WAI-State.json`
2. `WAI-Spoke/WAI-State.md`
3. `Skills/index.jsonl`
4. `Skills/SCHEMA.md`
5. `WAI-Spoke/WAI-Skills.jsonl`

## Authority Model

- `Skills/` is the authoritative skill architecture.
- `Skills/index.jsonl` is the canonical router and discovery surface.
- `Skills/SCHEMA.md` defines the current contract for routed skills, advisor inheritance, and legacy aliases.
- `WAI-Spoke/WAI-Skills.jsonl` is a mirror-only compatibility registry for spoke-local consumers; mirror the router and do not evolve it independently.
- `WAI-Spoke/commands/*.md` are compatibility wrappers only; resolve them back to `Skills/` before treating any behavior as real.

## How To Resolve A Skill

1. Find the skill in `Skills/index.jsonl`.
2. Open the folder from `skill_path`.
3. Read `SKILL.md` for the definition.
4. Execute or inspect the default document named by `entrypoint`.
5. Use `legacy_aliases` in `Skills/index.jsonl` as the alias map of record.
6. Consult `WAI-Spoke/WAI-Skills.jsonl` only when a spoke-local consumer still expects `command_file` or other compatibility fields.

## Current Skill Map

- Core and utility skills live under `Skills/wakeup`, `Skills/closeout`, `Skills/track-generate`, and `Skills/chat-to-track`.
- Advisor inheritance is rooted at `Skills/advisors/SKILL.md`.
- Advisor children currently route through `Skills/advisors/stewardship`, `Skills/advisors/complexity`, `Skills/advisors/context`, `Skills/advisors/foundation`, `Skills/advisors/signal`, and `Skills/advisors/lug`.

## Session Procedure

1. Load state from `WAI-Spoke/WAI-State.json` and `WAI-Spoke/WAI-State.md`.
2. Use `Skills/index.jsonl` to determine available skills and advisors.
3. Consult `Skills/SCHEMA.md` before assuming router or inheritance fields.
4. Treat `WAI-Spoke/WAI-Skills.jsonl` as a compatibility mirror, not a source of truth.
5. Update that mirror only to keep pace with `Skills/index.jsonl`, not to define new routing policy.
6. Update spoke state files as work progresses; do not rewrite `Skills/` authority rules locally.

## Legacy Note

- If a user or tool references `/wai-*` command docs, resolve them back to the matching `Skills/` entry before treating the command as authoritative.
- Keep compatibility aliases in place during the transition window; do not expand them into parallel behavior surfaces.
