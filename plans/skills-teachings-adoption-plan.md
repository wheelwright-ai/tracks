# Skills Teachings Adoption Plan

Date: 2026-03-19
Stage: 5 - Teaching Reprioritization

## Purpose

This plan re-ranks the remaining hub teachings after the folder-based `Skills/`
cutover. It does not apply any teaching in this stage. It maps each teaching to
the new architecture, calls out blockers, and updates the recommended adoption
order for later work.

## Ranking Principles

- Favor teachings that strengthen the authoritative runtime path already owned by `Skills/index.jsonl` and routed skill folders.
- Prefer cross-cutting reliability and handoff work before lower-value delivery or release automation.
- Do not let hub teachings reopen the settled authority model from `plans/skills-authority-policy.md`.
- Downgrade or defer teachings that assume a build system, Makefile, or release pipeline this repo does not currently own.
- Treat malformed or underspecified teachings as blockers to adjudicate, not as work to blindly adopt.

## Recommended Adoption Order

### 1. `track-reliability-v1`

- Why now: highest-value reliability pass for the active Skills-era flow across wakeup, track generation, and closeout.
- Primary mapping: `Skills/wakeup/`, `Skills/track-generate/`, `Skills/chat-to-track/`, `Skills/closeout/`, plus state/signal touchpoints.
- Architecture note: should target routed skill behavior and state transitions, not legacy wrappers or the mirror registry.

### 2. `wai-step3a-path-split-v1`

- Why now: it directly affects the teaching ingestion/reconciliation path that became more important after the cutover.
- Primary mapping: `Skills/wakeup/`, teaching reconciliation behavior, `WAI-Spoke/seed/`, and the signal-backed processed-teaching flow.
- Architecture note: must be reconciled with the existing Step 3a signal so it does not duplicate or contradict the current copy-on-reconcile behavior.

### 3. `track-chain-protocol-v1`

- Why now: once reliability and the intake path are clear, chain semantics can be aligned to the new handoff flow.
- Primary mapping: `Skills/wakeup/`, `Skills/track-generate/`, `Skills/closeout/`, and advisor surfaces that watch continuity or routing.
- Architecture note: should express session-to-session chain rules in terms of skill folders and state transitions, not flat command docs.

### 4. `skill-system-v1`

- Why now: it is still important, but it must be translated into the already-settled folder-based architecture instead of reintroducing a parallel skill model.
- Primary mapping: `Skills/index.jsonl`, `Skills/SCHEMA.md`, `Skills/README.md`, and advisor inheritance conventions.
- Architecture note: only adopt the portions that strengthen router, folder, exposure, or inheritance clarity; reject any part that implies flat-command authority or a second registry of truth.

### 5. `test-pipeline-verify-v1`

- Why now: useful after the architecture-facing teachings above, but verification should reflect a docs-and-prompts repo instead of app/build assumptions.
- Primary mapping: verification notes, JSON/Markdown validation, Skills/router coherence checks, and any existing CI definitions.
- Architecture note: translate to repo-appropriate checks; do not invent a heavy build pipeline.

### 6. `shipit-makefile-quality-gate-v1`

- Why later: the quality-gate intent may be useful, but the named mechanism is a mismatch because Tracks has no Makefile and no build-step foundation.
- Primary mapping: only to a lightweight verification entrypoint if one is later justified.
- Architecture note: treat the quality-gate idea as portable, but treat the Makefile assumption as non-authoritative for this repo.

### 7. `wai-shipit-release-tag-v1`

- Why later: release tagging is lower priority than skill routing, teaching reconciliation, and reliability stabilization.
- Primary mapping: only to future release workflow docs or lightweight tagging guidance if the repo starts using formal release cadence.
- Architecture note: do not add release process surface area before the repo defines what a release means for docs, prompts, and samples.

## Blockers And Conflict Bucket

### `wai-closeout-step9b-sender-v1`

- Status: blocked by conflict.
- Conflict: the teaching is explicitly unresolved in state and appears to touch the closeout sender path now owned by `Skills/closeout/` and reflected in current state-update behavior.
- Required before ranking higher: decide whether the hub teaching changes message composition, sender metadata, closeout sequencing, or output ownership; then map that change into the skill-folder model without editing legacy wrappers.

### Metadata-missing teachings

- Status: blocked by malformed or incomplete metadata.
- Conflict: teachings without stable ids, targets, owner fields, or path intent cannot be safely mapped to `Skills/` versus `WAI-Spoke/` compatibility surfaces.
- Required before adoption: normalize metadata so each teaching clearly states target surface, expected files, and whether it is behavioral, schema, verification, or release-oriented.

## Mapping Summary By Surface

- `Skills/wakeup/`: `track-reliability-v1`, `wai-step3a-path-split-v1`, `track-chain-protocol-v1`
- `Skills/track-generate/` and `Skills/chat-to-track/`: `track-reliability-v1`, `track-chain-protocol-v1`
- `Skills/closeout/`: `track-reliability-v1`; potential future target for `wai-closeout-step9b-sender-v1` after conflict resolution
- `Skills/index.jsonl` and Skills docs: `skill-system-v1`
- Verification and CI-facing surfaces: `test-pipeline-verify-v1`; possible partial translation of `shipit-makefile-quality-gate-v1`
- Release/process surfaces: `wai-shipit-release-tag-v1`
- Do not target by default: `WAI-Spoke/WAI-Skills.jsonl` and `WAI-Spoke/commands/*.md` except where compatibility data must stay synchronized with an authoritative `Skills/` change

## Recommended Next Actions

1. Normalize metadata-missing teachings so every remaining hub teaching has enough path and ownership data to map cleanly.
2. Resolve the `wai-closeout-step9b-sender-v1` conflict against `Skills/closeout/` before any closeout-specific adoption work.
3. Review `track-reliability-v1` first as the leading post-cutover teaching.
4. Reconcile `wai-step3a-path-split-v1` with the existing Step 3a teaching-reconciliation signal before changing wakeup behavior.
5. Queue `track-chain-protocol-v1` after the reliability and intake-path decisions are stable.
6. Translate `skill-system-v1` into the settled folder-based model rather than treating it as a fresh architecture proposal.
7. Defer pipeline/release teachings until their assumptions are rewritten for a documentation-and-prompts repo.
