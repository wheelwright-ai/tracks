# Skills Post-Cutover Plan

## Purpose

This plan covers the work **after** the overnight Skills refactor completes.

It assumes the spoke has been transformed to a folder-based `Skills/` architecture, but that morning follow-through is still required to:
- reconcile agent output
- remove ambiguity
- finish adoption decisions
- harden the new architecture

## Queueing Guidance

Yes: this plan is intended to be queued behind the overnight refactor as the
next job in sequence.

The queued follow-up job should not start until the overnight run has produced:
- changed file list
- verification notes
- unresolved questions
- any conflicts between router, registry, aliases, and guide

This is a chained handoff, not an independent fresh start.

## Primary Objective

Move from:
- "the refactor landed"

to:
- "the new Skills architecture is trusted, coherent, documented, and ready to evolve"

## Morning Entry Conditions

Before doing any follow-up work, collect:
- changed file list
- verification notes
- unresolved questions from the overnight run
- any conflicts between `Skills/`, `WAI-Spoke/WAI-Skills.jsonl`, `WAI-Guide.md`, and legacy command aliases

If those artifacts are missing, the first task is to reconstruct them before
making any cleanup or policy decisions.

## Morning Review Sequence

### Step 1: Reconcile the Overnight Result

Review:
- `Skills/index.jsonl`
- `WAI-Spoke/WAI-Skills.jsonl`
- `WAI-Spoke/WAI-Guide.md`
- `WAI-Spoke/WAI-State.json`
- `WAI-Spoke/WAI-State.md`
- all migrated `Skills/<skill-id>/` folders
- all legacy `WAI-Spoke/commands/*.md` files

Answer:
1. Is `Skills/` actually authoritative?
2. Are legacy command files truly non-authoritative?
3. Did any agents leave duplicated procedural content in two places?
4. Did the registry and guide drift from the router?

### Step 2: Classify the Outcome

Put the overnight result in one of these states:

#### State A: Clean Cutover

- router coherent
- migrated skills present
- aliases thin
- registry aligned
- guide aligned
- verification mostly green

Action:
- proceed to simplification and cleanup

#### State B: Partial Cutover

- some skills migrated cleanly
- some still duplicated or half-transitioned
- guide/registry not fully aligned

Action:
- run a reconciliation pass first
- do not begin cleanup until authority is clear

#### State C: Fragmented Output

- overlapping ownership damage
- schema drift
- aliases that still contain real behavior
- registry/router contradictions

Action:
- stop
- restore a single source of truth per capability
- reconcile before doing any further feature work

## Sequenced Execution Model

The post-cutover queue should run as a staged chain:

1. Entry and evidence collection
2. Reconciliation and outcome classification
3. Authority-policy decision
4. Alias-policy decision
5. Advisor normalization
6. Teaching reprioritization against the new architecture
7. Documentation and cleanup
8. Final handoff report

Each stage should write its outputs in a way the next stage can consume without
re-discovering the repo.

## Immediate Next Work After Successful Cutover

### 1. Reconciliation Pass

Goal:
- remove duplicate-authority problems

Tasks:
- compare every migrated skill folder against its legacy alias
- strip any real procedural content from aliases
- ensure `WAI-Spoke/WAI-Skills.jsonl` and `Skills/index.jsonl` say the same thing
- ensure `WAI-Guide.md` points to the same authority model

### 2. Registry Decision

Goal:
- stop maintaining two separate sources of truth without a plan

Decision:
- either generate `WAI-Spoke/WAI-Skills.jsonl` from `Skills/index.jsonl`
- or explicitly keep a mirrored transitional registry with clear ownership rules

Recommendation:
- move toward generated or mechanically synchronized registry as soon as practical

### 3. Alias Policy

Goal:
- settle what legacy command files are for

Decide:
- permanent aliases
- temporary compatibility shims
- explicit deprecation stubs

Recommendation:
- keep them as compatibility aliases for one transition window
- mark them clearly as non-authoritative
- add a planned retirement policy

### 4. Complete Advisor Surface

Goal:
- ensure the advisor model is internally consistent

Tasks:
- review parent defaults under `Skills/advisors/SKILL.md`
- normalize child `advisor.json` overrides
- verify mode behavior is coherent across advisors
- decide whether all advisors need the same fields or if some are optional

### 5. Finish the Remaining Hub Teachings

The skill architecture refactor and the pending hub teaching queue are now separate concerns.

After cutover stabilizes, handle:
- `track-reliability-v1`
- `track-chain-protocol-v1`
- `wai-step3a-path-split-v1`
- `shipit-makefile-quality-gate-v1`
- `test-pipeline-verify-v1`
- `wai-shipit-release-tag-v1`
- `wai-closeout-step9b-sender-v1` conflict
- `skill-system-v1`
- metadata-missing teachings

Recommendation:
- apply architecture-stabilizing teachings first:
  1. `track-reliability-v1`
  2. `wai-closeout-step9b-sender-v1` after conflict resolution
  3. `track-chain-protocol-v1`
  4. `skill-system-v1` only after deciding how it maps to folder-based skills

### 6. Documentation Pass

Goal:
- make the new architecture understandable without tribal knowledge

Tasks:
- add a `Skills/` section to the repo README if appropriate
- document the authority model:
  - router
  - skill folder
  - alias
  - registry
- explain advisor inheritance and overrides

### 7. Cleanup Pass

Goal:
- reduce transitional clutter after confidence is high

Candidates:
- stale flat command docs that are now only placeholders
- outdated plan files
- redundant compatibility notes
- old references to `INDEX.jsonl`

Do not do this until:
- verification is green
- authority is unambiguous
- morning review signs off

## Day-2 Deliverables

If the overnight cutover succeeds, the next concrete deliverables should be:

1. `plans/skills-reconciliation-report.md`
   Summarize what landed, what conflicted, and what was fixed.

2. `plans/skills-authority-policy.md`
   Define:
   - what is authoritative
   - what is derived
   - what is alias-only
   - who owns each surface

3. `plans/skills-teachings-adoption-plan.md`
   Re-rank the remaining hub teachings against the new architecture.

4. `plans/skills-post-cutover-report.md`
   Summarize:
   - which outcome state was reached
   - what was reconciled
   - which policy decisions were made
   - what remains open

## Questions To Answer After Cutover

1. Is `WAI-Spoke/WAI-Skills.jsonl` still needed as a first-class authored artifact?
2. Should `Skills/` eventually replace `WAI-Spoke/commands/` entirely?
3. Should skills support more than one entrypoint beyond `command.md`?
4. Should advisor inheritance support multiple parent layers?
5. Should hub teachings begin targeting `Skills/` paths directly?

## Recommended Follow-On Workstreams

If you want to parallelize the next day as well:

### Workstream 1: Reconciliation

Scope:
- compare router, registry, guide, aliases, and skill folders

Output:
- reconciliation report

### Workstream 2: Authority Policy

Scope:
- define long-term ownership model for:
  - `Skills/index.jsonl`
  - `WAI-Spoke/WAI-Skills.jsonl`
  - `WAI-Guide.md`
  - legacy aliases

Output:
- authority policy doc

### Workstream 3: Teaching Integration

Scope:
- remap pending hub teachings to the new folder-based architecture

Output:
- teaching adoption plan

## Success Criteria

This phase is complete when:
- post-cutover authority is unambiguous
- duplicate-authority problems are removed
- the registry strategy is decided
- aliases have a policy
- pending teachings are re-prioritized against the new architecture
- the repo is ready for normal work again
