---
_lug:
  id: "trk-skills-teaching-dry-run-v1"
  type: "work-order"
  title: "Tracks — Skills Teaching Generation and Dry-Run Upgrade"
  status: "ready-to-queue"
  version: "1.0.0"
  created: "2026-03-19"
  authored_by: "gpt-5-codex"
  destination: "opencode queued follow-up run"
  safe_to_auto_adopt: false
  behavior_directive:
    what_this_is: >
      A post-cutover learning loop. Generate candidate teachings from the new
      Skills architecture, dry-run their adoption, and use the results to
      improve future migration plans and work orders.
    what_this_is_not: >
      Not a second migration. Not a request to auto-apply all generated
      teachings. Not permission to teach transitional or ambiguous authority.
    prerequisite: >
      Queue this only after trk-skills-refactor-overnight-v1 and
      trk-skills-post-cutover-v1 complete and their verification outputs are
      available.
---

# Tracks — Skills Teaching Generation and Dry-Run Upgrade

## Primary Sources

- [plans/skills-teaching-dry-run-plan.md](/home/mario/projects/wheelwright/tracks/plans/skills-teaching-dry-run-plan.md)
- [plans/skills-teaching-dry-run-sequence.md](/home/mario/projects/wheelwright/tracks/plans/skills-teaching-dry-run-sequence.md)
- [plans/skills-teaching-dry-run-workstreams.jsonl](/home/mario/projects/wheelwright/tracks/plans/skills-teaching-dry-run-workstreams.jsonl)
- [plans/skills-post-cutover-plan.md](/home/mario/projects/wheelwright/tracks/plans/skills-post-cutover-plan.md)

## Queue Position

This job is intended to run after:
1. [WAI-Spoke/lugs/trk-skills-refactor-overnight-v1.md](/home/mario/projects/wheelwright/tracks/WAI-Spoke/lugs/trk-skills-refactor-overnight-v1.md)
2. [WAI-Spoke/lugs/trk-skills-post-cutover-v1.md](/home/mario/projects/wheelwright/tracks/WAI-Spoke/lugs/trk-skills-post-cutover-v1.md)

## Start Gate

Do not begin until:
- the Skills cutover is complete
- post-cutover reconciliation is complete
- final verification from the post-cutover job is available
- authority is settled enough to target the correct files

If authority is still ambiguous, stop and report that generated teachings would
be unreliable.

## Objective

Move from:
- "the new Skills architecture is in place"

to:
- "we can generate teachings from it, dry-run an upgrade, and improve our
  migration system from what that run reveals"

## Stage Order

1. Teaching candidate discovery
2. Teaching file generation
3. Dry-run adoption
4. Migration feedback
5. Final teaching triage

## Recommended Models

| Stage | Focus | Recommended Model | Reasoning |
|------|-------|-------------------|-----------|
| 1 | Candidate discovery | `gpt-5.4` | `high` |
| 2 | Teaching generation | `gpt-5.3-codex` | `high` |
| 3 | Dry-run adoption | `gpt-5.3-codex` | `high` |
| 4 | Migration feedback | `gpt-5.4-mini` | `medium` |
| 5 | Final triage | `gpt-5.1-codex-mini` | `medium` |

## Expected Outputs

- `plans/skills-generated-teachings-review.md`
- `plans/skills-dry-run-report.md`
- `plans/skills-migration-feedback.md`
- staged candidate `.teaching` files under `WAI-Spoke/seed/`

## Rules

- Do not auto-promote generated teachings to trusted production teachings
- Do not target retired flat command authority unless the purpose is explicit compatibility analysis
- Do not overwrite authoritative files during the dry run
- Mark uncertain teachings as manual-review rather than pretending they are safe
- Use the dry run to improve future migration planning, not just to produce files

## Final Handoff

When this queued job completes, return:
- candidate teaching inventory
- dry-run findings
- migration-plan improvements
- ready/manual/defer teaching triage
- remaining risks before any real adoption run
