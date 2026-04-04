# Skills Teaching Dry-Run Plan

## Purpose

This plan covers the first learning loop after the Skills architecture cutover
and post-cutover reconciliation are complete.

Its job is to:
- generate candidate teaching files from the migrated architecture
- dry-run a teaching-driven upgrade against the spoke
- capture where the migration plan was strong or weak
- feed those learnings back into future refactor planning

## Queue Position

This job should run after:
1. `trk-skills-refactor-overnight-v1`
2. `trk-skills-post-cutover-v1`

It is not part of the cutover itself. It is the first validation-and-learning
pass after the new architecture is stable enough to test.

## Entry Conditions

Do not begin until all of the following are true:
- `Skills/` is authoritative
- post-cutover reconciliation is complete
- authority policy exists
- alias policy exists
- advisor inheritance is normalized enough to target consistently
- final verification from the post-cutover job is available

If those conditions are not met, stop and report that the architecture is still
too unstable for a useful teaching-generation dry run.

## Objective

Move from:
- "the new architecture exists"

to:
- "we can generate teachings from it, simulate adoption, and learn how to make
  future migrations better"

## Scope

This job should:
- identify migration decisions worth converting into durable teachings
- generate candidate `.teaching` files for those decisions
- perform a dry-run adoption pass
- record conflicts, ambiguities, and weak assumptions
- produce a migration-feedback report

This job should not:
- auto-apply all generated teachings as if they are trusted
- redesign the Skills architecture again
- silently overwrite authoritative docs during dry run
- treat speculative teachings as production-ready without review

## Recommended Dry-Run Method

Use a conservative dry-run posture:
- generate candidate teachings into a reviewable staging area
- simulate adoption without destructive replacement
- compare expected targets against actual authoritative files
- record where generated teachings would cause duplication, drift, or loss

Preferred targets for observation:
- `Skills/index.jsonl`
- `Skills/SCHEMA.md`
- `Skills/<skill-id>/SKILL.md`
- `Skills/<skill-id>/command.md`
- `Skills/advisors/*`
- `WAI-Spoke/WAI-Skills.jsonl`
- `WAI-Spoke/WAI-Guide.md`
- `WAI-Spoke/WAI-State.json`
- `WAI-Spoke/WAI-State.md`

## Output Artifacts

This run should produce:
- `plans/skills-generated-teachings-review.md`
- `plans/skills-dry-run-report.md`
- `plans/skills-migration-feedback.md`

It may also produce:
- staged candidate teaching files for manual review

## Desired Questions To Answer

1. Which parts of the migration naturally become durable teachings?
2. Which generated teachings are clean enough for future auto-adoption?
3. Which generated teachings need manual-review metadata by default?
4. Which parts of the architecture are still too custom or unstable to teach?
5. What did the migration plan miss that the dry run exposed?
6. What should change in the next refactor lug or workstream model?

## Success Criteria

This job is complete when:
- candidate teachings exist for the strongest migration learnings
- the dry run shows how those teachings would land
- risky or ambiguous teachings are clearly flagged
- migration-plan improvements are written down
- the repo has a concrete feedback loop from architecture change to teaching generation
