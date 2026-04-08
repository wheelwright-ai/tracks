# KnowMe — Tracks (TRK)

_Generated: 2026-04-08 | Gardener pass | v0.1.1_

---

## 1. Who I am

**Tracks** is a documentation and prompt library spoke in the Wheelwright fleet. It is not an application — it has no build system, no runtime, and no web server.

**Core deliverable:** Three portable conversation-record prompt variants that let users extract and continue work from LLM sessions:

- `prompts/closing-request.md` — session wrap + handoff request
- `prompts/prep-and-request.md` — preparation + scoped continuation
- `prompts/active-collection.md` — live session capture for AI-assisted continuity

**Hub relationship:** Connected to hub at `/home/mario/projects/wheelwright/hub`. Teachings arrive from `hub/teachings_repo/spoke/current/`. Signals delivered to `hub/WAI-Hub/signals/incoming/framework/`.

**Problem solved:** Intellectual product trapped in LLM chat sessions gets lost. Tracks provides portable, reusable prompts to capture and continue that work.

---

## 2. Current stage

Skills-cutover stabilization: the authority model has settled (Skills/ owns routing, legacy commands are compatibility aliases), but the WAI-Skills.jsonl mirror and a handful of conflicted teachings remain unresolved before the next version increment.

**Single most important truth:** This is a docs repo — no delivery automation, no release pipeline, no app code.

---

## 3. Priorities

1. **Resolve blocked teachings** — wai-closeout-step9b-sender-v1 conflict, wai-step3a-path-split-v1 overlap, metadata-missing teachings (need normalization before safe adoption)
2. **Station Master epic** — lug-station-schema-v1 and lug-station-orchestrator-v1 are open tasks under epic-station-master-lines-v1; quality scores are not yet high enough for autonomous execution
3. **WAI-Skills.jsonl mechanical sync** — transitional mirror needs generation or sync script to remove drift risk

---

## 4. Architecture

| Component | Path | Notes |
|-----------|------|-------|
| Prompt variants | `prompts/` | Core deliverable — closing-request, prep-and-request, active-collection (v0.24) |
| Skills system | `Skills/` | Routing authority; `index.jsonl` is canonical |
| Legacy commands | `.claude/commands/` | Compatibility aliases for wai skills |
| Spoke state | `WAI-Spoke/WAI-State.json` | Version, wheel metadata, context |
| Lugs | `WAI-Spoke/lugs/bytype/` | task/bug/feature/signal/epic by type |
| Sessions | `WAI-Spoke/sessions/` | Track JSONL session records |
| Hooks | `.claude/hooks/` | pre-tool-guard.sh, user-prompt-submit.sh, pre-compact.sh, stop-test-runner.sh |
| Teachings inbox | `WAI-Spoke/seed/ingest/` | processed/ (102), manual/ (31+) |

**Non-obvious facts:**
- No `tools/`, no `web/`, no package.json, no Makefile
- Shipit/release teachings assume surfaces this repo doesn't own — do not adopt
- WAI-Skills.jsonl is mirror-only; do not manually edit it

---

## 5. Brand and voice

Tracks is a quiet reference spoke — it holds prompts and docs, not execution logic. Sessions are focused on authoring, teaching adoption, and signal routing. Autonomy is limited to teaching ingestion and signal routing; substantive prompt changes require human review.

---

## 6. Open epics and lugs

| ID | Type | Title | Status | Priority |
|----|------|-------|--------|----------|
| epic-station-master-lines-v1 | epic | Station Master + Lines: Track Assembly & Continuity Layer | open | session_focus |
| lug-station-schema-v1 | task | Station Schema — lines, lineEvents, extend sessions + trackArtifacts | open | quality below threshold |
| lug-station-orchestrator-v1 | task | Station Master Orchestrator — ingest() entry point wiring all station modules | open | quality below threshold |

**Signals undelivered:** 12 (in `WAI-Spoke/lugs/bytype/signal/undelivered/`)

---

## 7. Current constraints

- **Frozen:** wai-closeout-step9b-sender-v1 teaching — unresolved conflict against current Skills/closeout model
- **Blocked:** wai-step3a-path-split-v1 — overlaps existing Step 3a reconciliation signal; needs adjudication
- **Off-limits:** Delivery/release automation teachings (shipit, release tags, Makefile quality gates) — repo has no delivery surface
- **Hold:** Station Master epic tasks — quality_score below execution threshold; need refinement first
- **Caution:** Metadata-missing/malformed teachings — normalize before adopting

---

## 8. Implementation style

- Lug-first: all work tracked in `lugs/bytype/` before execution
- No build/test pipeline — verification is file-existence check
- Commits: `chore: gardener lifecycle YYYY-MM-DD — teachings + work`
- Teaching adoption is the primary autonomous activity
- Hooks use absolute paths (no `$CLAUDE_PROJECT_DIR`)
- PreToolUse hook: exit 0 to allow silently (no stdout JSON), exit 2 + stderr to block

---

## 9. Known risks

| Risk | Source | Severity |
|------|--------|----------|
| WAI-Skills.jsonl drift from Skills/index.jsonl | No sync mechanism | Medium |
| Conflicted closeout teaching blocks closeout skill iteration | wai-closeout-step9b-sender-v1 | Medium |
| Station epic tasks stuck below quality threshold | No expediter refinement yet | Low |
| Legacy command alias retirement undefined | No cleanup plan | Low |

---

## 10. Context health

- **Last session:** 2026-04-07 (gardener pass, 0 work executed)
- **Previous session:** 2026-04-06 (4 teachings applied, prompts updated to v0.24, version 0.1.0→0.1.1)
- **Teachings processed:** 102
- **Teachings in manual review:** 31+
- **Signals undelivered:** 12
- **Pending teachings today:** 9 new (6 auto-adopted, 3 to manual) + 1 reinstall verified
