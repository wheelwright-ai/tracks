# Skills Teaching Dry-Run Sequence

## Purpose

This is the third chained job after the Skills cutover and post-cutover
reconciliation.

It exists to generate teachings from the new architecture, simulate how they
would be adopted, and improve future migration planning based on the result.

## Start Gate

Do not start until:
- `trk-skills-refactor-overnight-v1` is complete
- `trk-skills-post-cutover-v1` is complete
- post-cutover verification is available
- the authority model is settled enough to know what the teachings should point at

If the architecture is still ambiguous, stop and report that the dry run would
teach the wrong thing.

## Chain

### Stage 1: Teaching Candidate Discovery

Goal:
- identify what the migration actually taught us

Outputs:
- `plans/skills-generated-teachings-review.md`

This stage should separate:
- durable architecture teachings
- project-specific tactics
- temporary transition details that should not become teachings

### Stage 2: Teaching File Generation

Goal:
- materialize candidate `.teaching` files in a reviewable staging area

Outputs:
- staged `.teaching` files under `WAI-Spoke/seed/`
- updated candidate review notes

This stage must target the new `Skills/` authority model, not the retired flat
command model.

### Stage 3: Dry-Run Adoption

Goal:
- simulate what would happen if the generated teachings were adopted

Outputs:
- `plans/skills-dry-run-report.md`

This stage should capture:
- which files would change
- where conflicts would appear
- where generated teachings are too vague or too aggressive

### Stage 4: Migration Feedback

Goal:
- improve the migration system using what the dry run exposed

Outputs:
- `plans/skills-migration-feedback.md`
- targeted improvements to migration planning docs if justified

This stage should answer:
1. What did the migration plan get right?
2. What did it miss?
3. What should future lugs/workstreams require earlier?

### Stage 5: Final Teaching Triage

Goal:
- separate ready teachings from deferred ones

Outputs:
- finalized review/triage notes

This stage should produce three buckets:
- ready for future adoption
- manual review required
- defer until the architecture matures further

## Recommended Model Mix

- Stage 1: `gpt-5.4` high
- Stage 2: `gpt-5.3-codex` high
- Stage 3: `gpt-5.3-codex` high
- Stage 4: `gpt-5.4-mini` medium
- Stage 5: `gpt-5.1-codex-mini` medium

## Queueing Guidance

Queue this after the post-cutover job, not after the overnight job directly.

This run depends on settled authority, otherwise it will generate teachings
against transitional surfaces and contaminate the feedback loop.
