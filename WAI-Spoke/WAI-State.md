# Wheel State: Tracks

---

**Wheelwright Framework v3.1.0**
**Structure:** v1 (WAI-Spoke/ directory)
**Hub:** /home/mario/projects/wheelwright/hub/

*This wheel uses Wheelwright Framework to maintain perfect context across AI sessions. Wheelwright transforms AI from order-taker to informed, responsible project partner.*

*"We aren't reinventing the wheel - we're evolving it faster than one person ever could."*

---

## Project Foundation

### Identity
- **Type:** Documentation and prompt library
- **Name:** Tracks
- **One-liner:** Portable conversation records for any AI session. Take your context anywhere.
- **Success looks like:** Anyone can generate a WAI Track file from any AI conversation using the prompts in this repo. Samples are realistic enough to demonstrate portability. Wheelwright is the clear next step.

✅ **Foundation Complete** — Defined on 2026-03-17 by claude-sonnet-4-6

### Boundaries

**In Scope:**
- Track format specification (spec/track-format.md)
- Three prompt variants: closing-request, prep-and-request, active-collection
- Three realistic sample Track files demonstrating portability
- README as the manifesto: portability framing, use cases, Wheelwright funnel
- MIT license matching framework

**Out of Scope:**
- Application code, web interface, build system
- Track file viewer or editor (that may be a future spoke)
- Authentication, database, any runtime dependencies

**Constraints:**
- Pure documentation — no package.json, no node_modules, no build step
- All wheelwright.ai and framework repo links must be present
- Prompts must be self-contained (raw URL usable as LLM instruction)
- Samples must be realistic enough to demonstrate portability

### Approach
- **Stack/Tools:** Markdown, JSONL — nothing else
- **Workflow:** GitHub repo, public, discoverable via topics
- **AI Collaboration:** AI takes initiative
- **Review Process:** Mario reviews content quality and messaging

---

## Core Philosophy: AI as Responsible Partner

This wheel follows Wheelwright's stewardship philosophy:

> **AI should enable but remain intentful.** When work strays from the
> established foundation, the AI should flag it and require explicit
> acknowledgment before proceeding.

---

## Purpose

Tracks is the **portable Track format repo** for Wheelwright. It:

1. **Defines the schema** - `spec/track-format.md` describes the canonical WAI Track structure
2. **Ships usable prompts** - the three prompt variants let any LLM generate Tracks without special tooling
3. **Proves portability** - realistic sample Tracks show that context can move across providers and sessions
4. **Funnels to Wheelwright** - the repo is the manual on-ramp; Wheelwright is the native automated system

### Relationship to Wheelwright

Tracks is the manual, provider-agnostic layer:
- **This repo** gives anyone portable prompts and examples
- **Wheelwright** provides native active collection, cross-spoke continuity, and advisor-driven review
- The two should reinforce each other, not describe different products

---

## Current Operating Posture

- `Skills/` is now the authoritative architecture for wakeup, closeout, track generation, chat-to-track, and advisor capabilities.
- `Skills/index.jsonl` is the routing authority; `SKILL.md` and `command.md` inside each skill folder are the behavior and authoring surface.
- `WAI-Spoke/WAI-Guide.md` remains the startup guide for spoke-local operation, but it does not override router or skill-folder authority.
- `WAI-Spoke/WAI-Skills.jsonl` is a mirror-only compatibility registry for spoke-local consumers and should move toward generated or mechanically synchronized maintenance instead of independent authorship.
- `WAI-Spoke/commands/*.md` remain compatibility aliases only and must not regain authoritative behavior.

## Remaining Verification / Follow-Up

- Implement the chosen generated or mechanically synchronized maintenance for `WAI-Spoke/WAI-Skills.jsonl`.
- Final-verify router, mirror, guide, state, and compatibility alias coherence.
- Resolve metadata-missing teachings so each remaining hub teaching has enough target and ownership data to map cleanly into `Skills/` or another clearly non-authoritative surface.
- Resolve the `wai-closeout-step9b-sender-v1` conflict against `Skills/closeout` before any closeout-specific teaching adoption.
- Review the top teaching sequence in this order: `track-reliability-v1`, `wai-step3a-path-split-v1`, then `track-chain-protocol-v1`.
- Translate `skill-system-v1` into the settled folder-based model without reopening the authority policy.
- Triage `test-pipeline-verify-v1`, `shipit-makefile-quality-gate-v1`, and `wai-shipit-release-tag-v1` against the repo's docs-only constraints before adopting delivery or release automation.

## Current Teaching Queue Risks

- `WAI-Spoke/WAI-Skills.jsonl` is still a transitional mirror, so any teaching that touches routing or discovery must continue to treat `Skills/index.jsonl` as the authority.
- Final verification still needs to confirm whether any active consumer depends on specific legacy `wai-*` compatibility aliases before retirement planning advances.
- `wai-step3a-path-split-v1` overlaps the existing Step 3a reconciliation signal and needs adjudication before wakeup behavior changes again.
- `wai-closeout-step9b-sender-v1` remains the clearest unresolved conflict in the queue.
- Metadata-missing teachings cannot be safely adopted until their target surfaces and ownership expectations are explicit.
- Shipit and release-tag teachings assume delivery surfaces this repo may never need because Tracks has no build system or Makefile foundation.

---

## Evolution Log

| Date | Change | Rationale | Acknowledged By |
|------|--------|-----------|--------------------|
| 2026-03-17 | Foundation set to documentation/prompt library | Corrected from Next.js app scaffold — Tracks is a concept explainer and prompt repo, no web app needed | mario |
| 2026-03-17 | Portability framing finalized | "Frees your intellectual product trapped in the LLM chat and gives it back to you" — stronger than generic re-warming framing | mario |
| 2026-03-18 | Reconciled WAI state and command drift | `WAI-State.json` and `wai.md` had fallen back toward stale dashboard/app assumptions; realigned them to the shipped prompt-library repo and current session model | mario |
| 2026-03-18 | Prompt set upgraded to rich v2 track capture | Prompts now preserve user voice, pivotal statements, reconciled artifacts, and next-agent continuity notes instead of only thin per-turn summaries | mario |
| 2026-03-19 | Began folder-based Skills migration | Added `Skills/index.jsonl` and moved wakeup to `Skills/wakeup/` as the first authoritative skill, leaving `WAI-Spoke/commands/wai.md` as a compatibility shim | mario |
| 2026-03-19 | Completed the spoke-level Skills cutover | Core utilities and advisors now live under `Skills/`; legacy command docs are compatibility-only, while registry/guide/policy cleanup moves to post-cutover follow-up | mario |
| 2026-03-19 | Settled the Skills authority policy | Long-term ownership is now explicit: router in `Skills/index.jsonl`, behavior in skill folders, mirror-only spoke registry, and alias-only legacy `wai-*` wrappers | mario |
| 2026-03-19 | Re-ranked the remaining hub teachings for `Skills/` | Reliability and teaching-ingestion work now lead the queue, `skill-system-v1` must translate into the settled folder model, and malformed or conflicting closeout teachings remain blocked pending adjudication | mario |

---

## Session Log

| Session | Date | Focus | Key Outcomes |
|---------|------|-------|--------------|
| 1 | 2026-03-17 | Inception → full build → push to GitHub | Received inception lug, built entire repo (spec, 3 prompts, 3 samples, README, LICENSE), pushed to wheelwright-ai/tracks |

---

*This wheel rolls forward with Wheelwright Framework - wheelwright.ai*
