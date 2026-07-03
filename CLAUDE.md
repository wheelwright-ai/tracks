<!-- MANAGED BY BASHER — maintained by `basher tools update`. Do not edit this section directly.
     New entries: (1) document value, (2) declare scope: spoke-local | wheel-wide
     Wheel-wide changes: write a lug to /home/mario/projects/basher/WAI-Spoke/lugs/incoming/ -->

# Claude Code Instructions

**This project uses Wheelwright (WAI) for AI session continuity.**
Read `AGENTS.md` for universal WAI instructions and key paths. This file covers Claude Code specifics.

**Two-way reference:** AGENTS.md is the universal bootstrap; CLAUDE.md layers IDE-specific rules on top.

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
## Wakeup Convergence

- Finish the WAI Point briefing before asking for approval on teachings or side actions.
- During wakeup, summarize teachings from filenames/frontmatter only.
- Do not read full teaching bodies during wakeup unless the user explicitly asks to review them now.

## Anti-Patterns

- **Over-engineering:** Do not propose complex solutions when simpler ones work.
- **Skipping verification:** Never say "probably saved" — run git status, check the file, report what was verified.
- **WAI-State.json direct mutation by hooks:** Session guard state goes in WAI-Spoke/runtime/session-guard.json (gitignored), never in WAI-State.json.
- **settings.local.json junk:** Do not approve one-off session-specific paths into settings.local.json. Keep only reusable entries.
- **Memorizing rules:** Read the skill file. Do not carry rules in conversation context when the file is the source of truth.
- **TaskCreate for persistent state:** Tasks do not survive sessions. Use lugs (P11).
- **Asking permission for safe ops:** Do not ask "want me to X or Y" — use the ROI scorer, pick the best action, do it. P10 says trust is the default. Only pause for genuinely destructive actions.
- **Guessing context %:** Never estimate context usage. Use /context output or state unknown. Estimation was proven 2.4x inaccurate.
- **Placeholder lugs:** Never create a lug without complete PEV, acceptance criteria, effort score, and file targets. Everything will be implemented — make it implementable at creation.
- **Deferring lug quality:** Do not walk away from the creation window without the artifact correctly defined. Test against principles and mission goals. Ozi enforces this.
- **Hook path variables:** Never use $CLAUDE_PROJECT_DIR or other assumed env vars in settings.json hook commands. Always use absolute /home/mario/ paths. Unresolved vars silently break every tool call in the session.
- **Em-dash in bash JSON writes:** Never use em-dash in printf/echo commands that write to .jsonl files. Shell encoding failures produce unparseable JSON. Use Python json.dumps() for any JSON serialization involving free-text strings.
- **Treating SIGNAL routing as skip:** Never skip a lug with routed_to: SIGNAL. SIGNAL means deliver to hub inbox, not skip.
- **Over-escalating to SIGNAL:** SIGNAL requires impact >= 8 AND must apply to every active spoke immediately. Framework improvements, spoke-specific gaps, and process observations are LOCAL or FRAMEWORK impl lugs — never SIGNAL. Default: LOCAL or FRAMEWORK. This has been corrected multiple times.
- **Hub implements hub-side features separately:** Wrong. Framework is the blueprint. Hub is just another spoke. Framework designs, publishes teaching, hub and all spokes adopt.
- **Treating blocked_by as a gate without verification:** Before treating a blocked_by reference as a blocker, verify the blocking lug actually exists and is unresolved. Check the filesystem — if the target file exists or the lug is in completed/, the blocker is clear.
- **Using wheel-tender.sh --dry-run for filter visibility:** --dry-run skips Pass 2 and Pass 3 but still runs Pass 1 (Haiku fleet session, ~$0.50, ~2 min). To inspect filter results without cost, read the last gardener log or parse the filter logic directly.
- **Dropping spoke-directed lugs in hub incoming:** Never deliver a lug meant for a specific spoke to hub/WAI-Spoke/lugs/incoming/. That folder is for hub-scoped work only. For spoke-directed lugs: read hub/hub-registry.json → find the spoke by wheel_id in the wheels[] array → deliver to {path}/WAI-Spoke/lugs/incoming/. Hub incoming is not a relay — spokes will never see lugs left there.
- **Delivering behavior changes without spec review:** Any implementation lug with a spec_id must confirm the spec still matches the behavior after delivery, or open a draft spec update lug. Spec drift is invisible until the next agent reads stale documentation. If you complete an impl lug and the behavior diverged from its spec, open a new lug (type: spec, status: draft) before closing out.

## Behavioral Protocols

| Protocol | Description |
|----------|-------------|
| Man Lug System | Spec lugs live at bytype/spec/. Index at WAI-SpecIndex.jsonl. Query: grep subject_id, load lug. Primary source for spoke behaviors — load before reading code. |
