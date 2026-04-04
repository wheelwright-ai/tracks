# Skills Post-Cutover Report

## Outcome

- Classification: cutover completed; post-cutover documentation and state now align to the settled authority model.
- `Skills/` is the intended authoritative architecture for routed capabilities.
- `WAI-Spoke/commands/*.md` now act as compatibility aliases, not authoring surfaces.
- `WAI-Spoke/WAI-Skills.jsonl` remains a mirror-only compatibility registry for spoke-local consumers.

## What Landed

- Core utility skills now exist in dedicated folders: `wakeup`, `closeout`, `track-generate`, and `chat-to-track`.
- Advisor capabilities now exist under `Skills/advisors/` with a shared parent plus child overrides.
- The router of record is `Skills/index.jsonl`, which names both core/utility skills and advisor entries.
- The authority policy is now written: router authority lives in `Skills/index.jsonl`, behavior authority lives in skill folders, and legacy wrappers stay alias-only during the transition window.
- Spoke-local guide and state docs now describe the settled model instead of the earlier cutover posture.

## Policy Decisions Recorded

- `Skills/index.jsonl` is the canonical routing and alias map.
- Skill folders under `Skills/` own behavior and entry documents.
- `WAI-Spoke/WAI-Guide.md` is the spoke startup guide, but it does not override router or skill-folder authority.
- `WAI-Spoke/WAI-Skills.jsonl` is mirror-only compatibility data and should move toward generated or mechanically synchronized upkeep.
- `WAI-Spoke/commands/*.md` remain compatibility aliases for one transition window and must not regain behavior ownership.

## Documentation Cleanup Completed

- Removed stale cutover wording that implied router, guide, and policy ownership were still undecided.
- Reworded guide and state references so they consistently describe `Skills/` as the settled authority surface.
- Kept compatibility aliases and the mirror registry in place without expanding their authority.

## Remaining Open Issues

- `WAI-Spoke/WAI-Skills.jsonl` is still a drift risk until generated or mechanically synchronized maintenance exists.
- Legacy `wai-*` wrapper retirement still needs final verification against active callers and verification paths.
- Advisor inheritance remains intentionally single-parent for now; broader inheritance questions stay deferred.
- The repo still carries blocked or underspecified hub teachings, including the unresolved `wai-closeout-step9b-sender-v1` conflict.

## Recommended Immediate Follow-Up

1. Final-verify router, mirror, guide, and state coherence.
2. Choose and implement generated or mechanically synchronized upkeep for `WAI-Spoke/WAI-Skills.jsonl`.
3. Keep compatibility aliases until verification confirms callers no longer depend on them.
4. Continue teaching normalization and conflict resolution without reopening the settled authority model.

## Closeout Summary

- Final Stage 7 verification passes for current cutover artifacts.
- `WAI-Spoke/WAI-State.json`, `Skills/index.jsonl`, and `WAI-Spoke/WAI-Skills.jsonl` all parse cleanly.
- Router targets and alias wrappers resolve for all ten declared skills, with the stewardship wrapper now present.
- Current authorship is not materially ambiguous: `Skills/index.jsonl` remains the routing authority, `Skills/` folders remain the behavior authority, and `WAI-Spoke/commands/*.md` remain compatibility-only wrappers.
- Remaining risk is operational rather than blocking: mirror drift in `WAI-Spoke/WAI-Skills.jsonl`, wrapper retirement timing, and deferred policy/teaching questions still need follow-up.
