# Skills Reconciliation Report

Date: 2026-03-19
Stage: 2 - Reconciliation

## Classification

- Result: partial cutover
- Why: the folder-based `Skills/` architecture landed and is repeatedly named as authoritative, but the overnight output did not finish as a clean cutover because one declared legacy alias is broken and the repo still carries unresolved duplicate-routing surfaces.

## Overnight Evidence Snapshot

- `Skills/` was added as the new architecture surface, including `Skills/index.jsonl`, schema/docs, core utility folders, and advisor folders with `advisor.json` overrides.
- `WAI-Spoke/WAI-Skills.jsonl` was expanded into a spoke-local mirror of the skill map.
- `WAI-Spoke/WAI-Guide.md`, `WAI-Spoke/WAI-State.json`, and `WAI-Spoke/WAI-State.md` now say `Skills/` is authoritative and that legacy command files are compatibility-only.
- Compatibility wrappers exist for `wakeup`, `closeout`, `track-generate`, `chat-to-track`, `complexity-advisor`, `context-advisor`, `foundation-advisor`, `signal-advisor`, and `lug-advisor`.
- `plans/verification-notes.md` is complete enough for Stage 1 and already records the concrete break: `WAI-Spoke/commands/wai-stewardship-advisor.md` is referenced in both registries but missing on disk.

## Changed Files Relevant To The Overnight Cutover

- Added `Skills/README.md`, `Skills/SCHEMA.md`, `Skills/index.jsonl`, `Skills/wakeup/`, `Skills/closeout/`, `Skills/track-generate/`, `Skills/chat-to-track/`, and `Skills/advisors/`.
- Added compatibility wrappers in `WAI-Spoke/commands/` for `wai-closeout.md`, `wai-track-generate.md`, `wai-chat-to-track.md`, `wai-complexity-advisor.md`, `wai-context-advisor.md`, `wai-foundation-advisor.md`, `wai-signal-advisor.md`, and `wai-lug-advisor.md`.
- Modified `WAI-Spoke/WAI-Guide.md`, `WAI-Spoke/WAI-Skills.jsonl`, `WAI-Spoke/WAI-State.json`, `WAI-Spoke/WAI-State.md`, and `WAI-Spoke/commands/wai.md` to reflect the cutover.
- Added planning and handoff artifacts under `plans/`, including `plans/verification-notes.md` and this reconciliation report.

## Current Authority Claims

- `Skills/` is claimed as the authoritative skill architecture by `WAI-Spoke/WAI-Guide.md`, `WAI-Spoke/WAI-State.json`, `WAI-Spoke/WAI-State.md`, `Skills/README.md`, and `Skills/SCHEMA.md`.
- `Skills/index.jsonl` is claimed as the canonical router/discovery surface by `WAI-Spoke/WAI-Guide.md`, `Skills/README.md`, and `Skills/SCHEMA.md`.
- Skill folders own `SKILL.md` and `command.md` as the authoring surface per `Skills/README.md` and `Skills/SCHEMA.md`.
- `WAI-Spoke/WAI-Skills.jsonl` claims to be a transitional mirror/compatibility registry, not a source of truth.
- `WAI-Spoke/commands/*.md` claim compatibility-wrapper status, not authoritative behavior.

## Stage 2 Reconciliations Completed

- Fixed the broken compatibility alias by adding `WAI-Spoke/commands/wai-stewardship-advisor.md` to match both registries.
- Promoted every routed skill with an existing folder on disk from `planned` to `active` in both `Skills/index.jsonl` and `WAI-Spoke/WAI-Skills.jsonl`.
- Re-aligned the guide so authority is singular: `Skills/index.jsonl` owns routing and alias mapping, `WAI-Spoke/WAI-Skills.jsonl` is mirror-only, and legacy command docs resolve back to `Skills/`.
- Kept legacy command wrappers non-authoritative and added the missing advisor shim without restoring any legacy file as a behavior source.

## Remaining Duplicate-Authority Risk

- `WAI-Spoke/WAI-Skills.jsonl` still exists as a transitional mirror with a spoke-local `command_file` field, so drift remains possible until Stage 3 decides whether it becomes generated or otherwise mechanically synchronized.
- The router/mirror field-shape split remains intentional for now: `legacy_aliases` stays canonical in `Skills/index.jsonl`, while `command_file` remains a compatibility field for spoke-local consumers.
- `plans/skills-post-cutover-report.md` still contains stronger "full cutover" language than the current reconciliation posture; that narrative cleanup is deferred to the later documentation stage.

## Unresolved Questions For Downstream Stages

- Should `WAI-Spoke/WAI-Skills.jsonl` become generated, mechanically synchronized, or manually mirrored for a short transition window?
- How long do legacy `wai-*` command wrappers live, and what retires them?
- Should `command.md` remain the single entry document, or may skills expose additional entry docs later?
- Does advisor inheritance stay single-parent only, or will nested/multi-layer inheritance be allowed later?
- Should remaining hub teachings be remapped directly to `Skills/` now, including the still-open `wai-closeout-step9b-sender` conflict referenced in state?

## Stage 2 Call

- The cutover is more coherent after reconciliation: router, guide, mirror, and alias wrappers now agree on `Skills/` authority and the declared alias set exists on disk.
- The repo is still in a transitional state, not a final policy state: the mirror registry remains manually representable and long-term ownership rules are not yet written.
- Stage 3 should formalize the authority policy without revisiting `WAI-State` files yet touched by later policy work.
