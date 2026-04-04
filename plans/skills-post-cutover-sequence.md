# Skills Post-Cutover Sequence

## Purpose

This is the queued follow-up job that should run after
`trk-skills-refactor-overnight-v1` completes.

It is intentionally sequential. Each stage exists to reduce ambiguity before
the next one starts.

## Start Gate

Do not start this job until the overnight refactor has produced:
- changed file list
- verification notes
- unresolved questions
- known conflicts between router, registry, aliases, and guide

If any of those are missing, Stage 1 reconstructs them first.

## Chain

### Stage 1: Entry and Evidence Collection

Goal:
- collect the overnight evidence and classify the result

Outputs:
- `plans/skills-reconciliation-report.md`
- refreshed `plans/verification-notes.md` if needed

This stage must answer:
1. Was the overnight run a clean cutover, partial cutover, or fragmented output?
2. Which files now claim authority?
3. Which conflicts need reconciliation before policy is written?

### Stage 2: Reconciliation

Goal:
- make router, registry, guide, and aliases agree

Outputs:
- updated `Skills/index.jsonl`
- updated `WAI-Spoke/WAI-Skills.jsonl`
- updated `WAI-Spoke/WAI-Guide.md`
- updated alias files if needed

This stage must remove duplicate-authority where possible.

### Stage 3: Authority Policy

Goal:
- define the long-term ownership model

Outputs:
- `plans/skills-authority-policy.md`
- state updates in `WAI-State.json` and `WAI-State.md`

This stage must explicitly define:
- what is authoritative
- what is derived
- what is mirrored
- what is alias-only

### Stage 4: Alias and Advisor Policy

Goal:
- settle the transitional command surface and normalize advisor behavior

Outputs:
- advisor normalization updates
- alias policy additions to `plans/skills-authority-policy.md`

This stage must answer:
1. How long do aliases live?
2. What minimum fields do advisors inherit?
3. What may child `advisor.json` files override?

### Stage 5: Teaching Reprioritization

Goal:
- remap the remaining hub teaching queue to the new architecture

Outputs:
- `plans/skills-teachings-adoption-plan.md`
- updated backlog references in state files

This stage should not blindly apply teachings. It should rank them against the
new folder-based skill model first.

### Stage 6: Documentation and Cleanup

Goal:
- make the architecture legible and remove stale transitional language

Outputs:
- `plans/skills-post-cutover-report.md`
- refreshed `Skills/README.md`
- refreshed `WAI-Spoke/WAI-Guide.md`

Cleanup must be conservative. Do not remove compatibility surfaces until the
authority model is settled and verification remains green.

### Stage 7: Final Verification

Goal:
- confirm the repo is coherent after the follow-up pass

Outputs:
- final verification addendum in `plans/verification-notes.md`
- closeout summary appended to `plans/skills-post-cutover-report.md`

## Recommended Model Mix

- Stage 1: `gpt-5.4-mini` medium
- Stage 2: `gpt-5.3-codex` high
- Stage 3: `gpt-5.4` high
- Stage 4: `gpt-5.3-codex` high
- Stage 5: `gpt-5.4-mini` medium
- Stage 6: `gpt-5.4-mini` medium
- Stage 7: `gpt-5.1-codex-mini` medium

## Queueing Guidance

If opencode supports queued runs, place this job directly after the overnight
refactor.

If it does not, use this as the next work order in the morning. The same stage
gates still apply.
