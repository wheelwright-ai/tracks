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

Tracks is the **centralized observation deck** for all Wheelwright activity. It:

1. **Shows where you've been** - View session history across all your wheels
2. **Surfaces what matters** - Display Historian-detected patterns (recurring opens, workarounds, reopened decisions)
3. **Connects the dots** - Navigate between related sessions across different projects
4. **Respects immutability** - Tracks are read-only records; this dashboard observes but never modifies

### Integration with Historian

Tracks works hand-in-hand with the Historian advisor skill:
- **Historian** analyzes track data and creates vectors/reviews
- **Tracks** displays those results in a visual, navigable interface
- Together they form the "memory and interpretation" layer of Wheelwright

---

## Evolution Log

| Date | Change | Rationale | Acknowledged By |
|------|--------|-----------|--------------------|
| 2026-03-17 | Foundation set to documentation/prompt library | Corrected from Next.js app scaffold — Tracks is a concept explainer and prompt repo, no web app needed | mario |
| 2026-03-17 | Portability framing finalized | "Frees your intellectual product trapped in the LLM chat and gives it back to you" — stronger than generic re-warming framing | mario |

---

## Session Log

| Session | Date | Focus | Key Outcomes |
|---------|------|-------|--------------|
| 1 | 2026-03-17 | Inception → full build → push to GitHub | Received inception lug, built entire repo (spec, 3 prompts, 3 samples, README, LICENSE), pushed to wheelwright-ai/tracks |

---

*This wheel rolls forward with Wheelwright Framework - wheelwright.ai*
