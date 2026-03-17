# Tracks — AI Assistant Guide

**For:** AI assistants working on this Wheelwright spoke
**Version:** 3.1.0
**Spoke ID:** TRK-v0.1.0

---

## READ THIS FIRST

This project is a **Wheelwright wheel** (spoke). It has:

1. **WAI-Spoke/** structure (standard wheel files for context persistence)
2. **Hub connection** at `/home/mario/projects/wheelwright/hub/`
3. **Same update protocol** as all spokes (receives framework updates via seed/ingest/)

**Critical**: Read [WAI-State.json](WAI-State.json) and [WAI-State.md](WAI-State.md) before any work.

---

## Quick Start Protocol

### On First Load
1. Read [WAI-State.json](WAI-State.json) — Project configuration and analytics
2. Read [WAI-State.md](WAI-State.md) — Project identity and current operations
3. Check `_project_foundation.completed` — If false, guide user through `/wai-foundation`
4. Load [WAI-Lugs.jsonl](WAI-Lugs.jsonl) — Active tasks and dependencies
5. Load [WAI-Skills.jsonl](WAI-Skills.jsonl) — Active skills and advisories

### During Session
1. Update `_session_state` in WAI-State.json when making changes
2. Log significant decisions in WAI-State.md evolution log
3. Track session turns and outcomes

### On Closeout
1. Process seed/ingest/ for framework updates
2. Update WAI-State files with session summary
3. Append session summary to WAI-Session-Summary.jsonl
4. Synchronize analytics

---

## Core Files Reference

| File | Purpose | Access |
|------|---------|--------|
| `WAI-State.json` | Technical spec, foundation, session state | UPDATE |
| `WAI-State.md` | Strategic context, vision, evolution log | UPDATE |
| `WAI-Guide.md` | This file — AI assistant instructions | READ |
| `WAI-Skills.jsonl` | Skill registry with metadata | READ |
| `WAI-Lugs.jsonl` | Active task/dependency graph | UPDATE |
| `WAI-Signals.jsonl` | High-impact learnings (≥8/10) | APPEND |
| `WAI-Session-Summary.jsonl` | Session summaries (cleared on closeout) | APPEND |
| `WAI-File-Index.json` | File tracking for the project | UPDATE |

---

## Hub Connection

- **Hub Path:** `/home/mario/projects/wheelwright/hub/`
- **Framework Path:** `/home/mario/projects/wheelwright/framework`
- **Spoke ID:** TRK-v0.1.0

### Lugs (Hub Communication)
- Lugs with `destination_wheel_id="hub"` → Pushed to hub during teach
- Lugs with `source_wheel_id="hub"` → Received from hub during teach
- Self-lugs (`destination_wheel_id=null`) → Local tasks for this spoke

---

## Foundation Enforcement

If `_project_foundation.completed == false`:
- **Do not start project work**
- Guide user through `/wai-foundation` command
- Define identity, boundaries, approach, and philosophy
- Log completion in evolution_log

---

## Decision Logic

### Should this be a Signal?
✅ **YES** if impact ≥ 8, cross-project applicable, architectural insight
❌ **NO** if project-specific detail, minor refactoring, routine fix

### Should this evolve the foundation?
✅ **YES** if scope changes, new constraints, direction shift
❌ **NO** if normal implementation within existing boundaries

---

## Session Protocol

### Session Start
1. Load WAI-State.json (project configuration)
2. Check for pending updates in seed/ingest/
3. Review current operations in WAI-State.md
4. Load session context from _session_state

### During Work
1. Update _session_state on significant changes
2. Log decisions in WAI-State.md
3. Track analytics in real-time

### Session Closeout
1. Update WAI-State files with session summary
2. Process seed/ingest/ (run update)
3. Archive session logs
4. Clear current_session, update last_closeout

---

*Guide for Wheelwright Framework v3.1.0*
