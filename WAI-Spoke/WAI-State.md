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
- **Type:** Hub Dashboard
- **Name:** Tracks
- **One-liner:** Centralized session track viewer and pattern analyzer for all Wheelwright wheels
- **Success looks like:** View session history across all wheels, see Historian pattern detection results, navigate to specific sessions, and surface recurring patterns — all in one dashboard

✅ **Foundation Complete** — Defined on 2026-03-17 by code-puppy-2bfd03 (Sparky)

### Boundaries

**In Scope:**
- Aggregate track_*.jsonl files from all wheels' WAI-Spoke/sessions/
- Display session history across all Wheelwright projects
- Show Historian pattern detection results (open_recurrence, workaround_churn, reopened_decision)
- Visualize session track points (open[], activity[], decisions[])
- Navigate to specific sessions and wheels
- Display Historian review files from advisors/historian/reviews/
- Show pattern vectors from advisors/historian/vectors.jsonl
- Timeline view of sessions across wheels
- Search/filter by wheel, date, agent, or content
- Web-based dashboard (Next.js)
- Read-only viewer (no editing of tracks)

**Out of Scope:**
- Editing or modifying session track files (tracks are immutable)
- Running Historian analysis (that's a framework skill)
- Creating new tracks (that's done during sessions)
- Multi-user auth (single user, local dashboard)
- Real-time updates (refresh to see new sessions)
- Mobile app
- Cloud deployment (local-first)

**Constraints:**
- Read-only access to all track files
- Must respect WAI-Spoke structure across all wheels
- Never modify track_*.jsonl or WAI_Track-*.jsonl files
- Hub registry as source of truth for wheel locations
- Match PathFinder/Wheelwright stack: Next.js 16, TypeScript, Tailwind v4

### Approach
- **Stack/Tools:**
  - Next.js 16 (App Router)
  - React 19
  - TypeScript
  - Tailwind CSS v4
  - File-based data (read hub-registry.json, track_*.jsonl files)
  - No database needed (read-only viewer)
- **Workflow:** Read hub registry to find all wheels → scan each wheel's WAI-Spoke/sessions/ → aggregate and display tracks → show Historian results if available
- **AI Collaboration:** AI takes initiative
- **Review Process:** Mario reviews dashboard functionality and UX

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
| 2026-03-17 | Foundation defined | Corrected mission from generic progress tracker to Wheelwright session track viewer | code-puppy-2bfd03 (Sparky) |

---

## Session Log

| Session | Date | Focus | Key Outcomes |
|---------|------|-------|--------------||
| _None yet_ | | | |

---

*This wheel rolls forward with Wheelwright Framework - wheelwright.ai*
