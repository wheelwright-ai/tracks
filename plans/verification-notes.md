# Overnight Verification Notes

Date: 2026-03-19
Scope: skills cutover verification for parser integrity, router targets, alias targets, duplicate authority, and legacy command residue.

## Overall Outcome

Status: FAIL with one concrete routing break and no duplicate-authority residue found in the legacy wrappers that still exist.

`Skills/` behaves as the intended authority surface for the migrated skills that were checked. The remaining break is a missing compatibility wrapper referenced by both registries.

## Checks Run

### 1) Parse-check

- PASS: `WAI-Spoke/WAI-State.json` parses with `jq` semantics.
- PASS: every line in `WAI-Spoke/WAI-Skills.jsonl` parses as JSON.
- PASS: every line in `Skills/index.jsonl` parses as JSON.

### 2) Router path existence

- PASS: all `skill_path` directories referenced in `WAI-Spoke/WAI-Skills.jsonl` exist.
- PASS: all `skill_file` targets referenced in `WAI-Spoke/WAI-Skills.jsonl` exist.
- PASS: all `entrypoint` targets referenced in `WAI-Spoke/WAI-Skills.jsonl` exist.
- PASS: all advisor `inherits_from` targets referenced in `WAI-Spoke/WAI-Skills.jsonl` exist.
- PASS: all advisor `override_file` targets referenced in `WAI-Spoke/WAI-Skills.jsonl` exist.
- PASS: all `skill_path` directories referenced in `Skills/index.jsonl` exist.
- PASS: all `skill_file` targets referenced in `Skills/index.jsonl` exist.
- PASS: all `entrypoint` targets referenced in `Skills/index.jsonl` exist.
- PASS: all advisor `inherits_from` targets referenced in `Skills/index.jsonl` exist.
- PASS: all advisor `override_file` targets referenced in `Skills/index.jsonl` exist.

### 3) Alias / command_file existence

- PASS: existing compatibility wrappers resolve correctly for `wakeup`, `closeout`, `track-generate`, `chat-to-track`, `complexity-advisor`, `context-advisor`, `foundation-advisor`, `signal-advisor`, and `lug-advisor`.
- FAIL: `stewardship-advisor` points to `WAI-Spoke/commands/wai-stewardship-advisor.md` in both registries, but that file does not exist.

Affected references:
- `WAI-Spoke/WAI-Skills.jsonl:5`
- `Skills/index.jsonl:5`

Impact:
- router metadata is internally inconsistent for the stewardship compatibility alias
- any caller expecting the legacy wrapper path will fail resolution even though the authoritative skill folder exists

### 4) Duplicate authoritative copies for migrated skills

- PASS: no duplicate authoritative copies were found among the existing legacy command wrappers in `WAI-Spoke/commands/`.
- PASS: the checked wrappers consistently point back to `Skills/` as the authority surface.
- PASS: no existing wrapper inspected contains the migrated full procedure as a second authoritative copy.

Wrappers inspected:
- `WAI-Spoke/commands/wai.md`
- `WAI-Spoke/commands/wai-closeout.md`
- `WAI-Spoke/commands/wai-track-generate.md`
- `WAI-Spoke/commands/wai-chat-to-track.md`
- `WAI-Spoke/commands/wai-complexity-advisor.md`
- `WAI-Spoke/commands/wai-context-advisor.md`
- `WAI-Spoke/commands/wai-foundation-advisor.md`
- `WAI-Spoke/commands/wai-signal-advisor.md`
- `WAI-Spoke/commands/wai-lug-advisor.md`

Open issue:
- the stewardship alias cannot be evaluated as a wrapper-content check because the referenced wrapper file is missing entirely

### 5) Remaining authoritative legacy command content

- PASS: no remaining authoritative legacy command content was found in the existing `WAI-Spoke/commands/*.md` wrappers that were checked.
- PASS: the existing wrappers are compatibility-only surfaces, not procedural sources of truth.
- NOTE: `WAI-Spoke/commands/wai.md` contains slightly more routing and migration prose than the others, but it still delegates authority to `Skills/wakeup/` and does not retain the wakeup protocol itself.

## Overnight Open Issues And Warnings (Historical)

- FAIL: missing file `WAI-Spoke/commands/wai-stewardship-advisor.md` breaks the declared alias path for `stewardship-advisor`.
- WARNING: both registries still carry compatibility-path metadata, so wrapper coverage has to remain complete until alias retirement policy is finalized.
- WARNING: `WAI-Spoke/WAI-Skills.jsonl` remains a mirrored registry beside `Skills/index.jsonl`; even where current entries match, this remains a drift risk until ownership and sync rules are settled.

## Overnight Bottom Line (Superseded)

- Parser integrity is clean.
- Canonical `Skills/` router targets are present.
- Legacy wrappers are generally non-authoritative as intended.
- The overnight verification workstream does not pass cleanly because the stewardship legacy alias target is missing.

## Final Verification Addendum

Date: 2026-03-19
Stage: P7 post-cutover chain, Stage 7 re-check

- PASS: `WAI-Spoke/WAI-State.json` still parses as valid JSON.
- PASS: `Skills/index.jsonl` and `WAI-Spoke/WAI-Skills.jsonl` still parse line-by-line as valid JSONL.
- PASS: all registry-declared `skill_path`, `skill_file`, `entrypoint`, advisor `inherits_from`, and advisor `override_file` targets resolve on disk.
- PASS: registry alias metadata now resolves cleanly for every declared compatibility wrapper, including `WAI-Spoke/commands/wai-stewardship-advisor.md`.
- PASS: `Skills/index.jsonl` and `WAI-Spoke/WAI-Skills.jsonl` carry the same skill IDs and matching alias targets for the ten routed capabilities currently declared.
- PASS: the checked `WAI-Spoke/commands/*.md` files remain compatibility-only wrappers that point back to `Skills/` and do not reintroduce a second authoritative behavior source.
- PASS: no major capability in the current routed surface appears ambiguously authored at this time; authority remains clear that routing lives in `Skills/index.jsonl` and behavior lives in `Skills/`.

Current status: PASS with warnings only.

Remaining warnings:
- WARNING: `WAI-Spoke/WAI-Skills.jsonl` is still a mirror registry beside `Skills/index.jsonl`, so manual drift remains possible until generated or mechanically synchronized upkeep is in place.
- WARNING: compatibility wrappers under `WAI-Spoke/commands/` still need a retirement decision and caller verification, but they do not create a current routing break.
- WARNING: deferred policy questions such as broader advisor inheritance or other blocked teachings remain open, but they do not make the current skill surface ambiguous or broken.
