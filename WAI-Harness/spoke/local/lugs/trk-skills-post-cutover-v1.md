---
_lug:
  id: "trk-skills-post-cutover-v1"
  type: "work-order"
  title: "Tracks — Skills Post-Cutover Reconciliation and Policy"
  status: "ready-to-queue"
  version: "1.0.0"
  created: "2026-03-19"
  authored_by: "gpt-5-codex"
  destination: "opencode queued follow-up run"
  safe_to_auto_adopt: false
  behavior_directive:
    what_this_is: >
      A sequential follow-up work order intended to run after the overnight
      Skills refactor completes. It turns the morning cleanup into a gated
      chain: evidence collection, reconciliation, policy, reprioritization,
      cleanup, and final verification.
    what_this_is_not: >
      Not a second architecture redesign. Not an excuse to reopen the overnight
      migration. Not a request to re-author migrated capabilities in legacy
      command files.
    prerequisite: >
      Queue this only after trk-skills-refactor-overnight-v1 completes or when
      its outputs are available for review.
---

# Tracks — Skills Post-Cutover Reconciliation and Policy

## Primary Sources

- [plans/skills-post-cutover-plan.md](/home/mario/projects/wheelwright/tracks/plans/skills-post-cutover-plan.md)
- [plans/skills-post-cutover-sequence.md](/home/mario/projects/wheelwright/tracks/plans/skills-post-cutover-sequence.md)
- [plans/skills-post-cutover-workstreams.jsonl](/home/mario/projects/wheelwright/tracks/plans/skills-post-cutover-workstreams.jsonl)
- [plans/skills-refactor-overnight.md](/home/mario/projects/wheelwright/tracks/plans/skills-refactor-overnight.md)

## Queue Position

This job is intended to run immediately after:
- [WAI-Spoke/lugs/trk-skills-refactor-overnight-v1.md](/home/mario/projects/wheelwright/tracks/WAI-Spoke/lugs/trk-skills-refactor-overnight-v1.md)

## Start Gate

Do not begin until the overnight refactor has produced:
- changed file list
- verification notes
- unresolved questions
- known conflicts between router, registry, aliases, and guide

If those are incomplete, Stage 1 reconstructs them before proceeding.

## Objective

Move from:
- "the cutover landed"

to:
- "the new Skills architecture is coherent, policy-backed, and ready for
  normal work"

## Stage Order

1. Entry and evidence collection
2. Reconciliation
3. Authority policy
4. Alias and advisor policy
5. Teaching reprioritization
6. Documentation and cleanup
7. Final verification

## Recommended Models

| Stage | Focus | Recommended Model | Reasoning |
|------|-------|-------------------|-----------|
| 1 | Entry and evidence | `gpt-5.4-mini` | `medium` |
| 2 | Reconciliation | `gpt-5.3-codex` | `high` |
| 3 | Authority policy | `gpt-5.4` | `high` |
| 4 | Alias and advisor policy | `gpt-5.3-codex` | `high` |
| 5 | Teaching reprioritization | `gpt-5.4-mini` | `medium` |
| 6 | Documentation and cleanup | `gpt-5.4-mini` | `medium` |
| 7 | Final verification | `gpt-5.1-codex-mini` | `medium` |

## Expected Outputs

- `plans/skills-reconciliation-report.md`
- `plans/skills-authority-policy.md`
- `plans/skills-teachings-adoption-plan.md`
- `plans/skills-post-cutover-report.md`
- refreshed `plans/verification-notes.md`

## Rules

- Do not reopen the architecture decision unless reconciliation proves the
  cutover is fragmented
- Do not make legacy command files authoritative again
- Do not remove transitional aliases until policy and verification agree
- Keep state, guide, router, and registry consistent

## Morning Handoff

When this queued job completes, return:
- outcome classification
- reconciliation report
- authority-policy summary
- teaching adoption order
- final verification status
- remaining open questions
