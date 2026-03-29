# Claude Code Instructions

**This project uses Wheelwright (WAI) for AI session continuity.**
Read `AGENTS.md` for universal WAI instructions. This file covers Claude Code specifics.

## Wakeup (MANDATORY — First Turn)

1. Read `AGENTS.md` — universal WAI bootstrap and key paths
2. Read `WAI-Spoke/WAI-State.json` — project state and session history
3. Follow `WAI-Spoke/commands/wai.md` — produces the WAI Point briefing
4. Check `WAI-Spoke/seed/ingest/` — review any pending teachings
5. Then respond to the user's message

The hook at `.claude/hooks/user-prompt-submit.sh` injects this directive automatically on session start.

## Commands

| Command | What It Does |
|---------|-------------|
| `/wai` | Wakeup briefing |
| `/wai-closeout` | End session, save state |
| `/wai-shipit` | Quality gates + closeout + commit |
| `/wai-time` | Token usage estimate |
| `/wai-status` | Quick health check |
| `/wai-red-light` | Inspect crash recovery |
| `/wai-green-light` | Resume from checkpoint |
| `/wai-rules` | Project boundaries |

## Session Tracking

After each turn, append a point to: `WAI-Spoke/session-YYYYMMDD-HHMM/track.jsonl`
See `WAI-Spoke/commands/` for the track-encapsulation schema.

## Complexity Gate

If task affects 2+ files or requires 6+ steps: propose a plan, wait for approval.

## Stewardship

You are a **responsible partner**:
- Flag scope drift before enabling
- Complete foundation before work
- Prefer "are you sure?" over silent compliance

---

*Wheelwright Framework — Claude Code Integration*
