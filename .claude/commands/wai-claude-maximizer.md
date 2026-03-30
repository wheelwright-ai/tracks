# WAI Claude Maximizer

Proactive Claude Code optimization audit. Ozi runs this when CC config is underweight for the spoke's maturity.

## What It Does

Reads the current CC configuration across 8 areas, compares against ideal state for the spoke's phase, and surfaces gaps with prioritized fixes. Can also generate patches on request.

## Type

`guard` (advisory) — same pattern as stewardship-guard and complexity-gate.

## When Ozi Triggers

Fire this skill proactively when any of these conditions are detected:

| Condition | Detection |
|-----------|-----------|
| Missing deny rules | `jq '.permissions.deny' .claude/settings.json` returns null |
| Underweight CLAUDE.md | CLAUDE.md under 50 lines or missing stack/anti-patterns blocks |
| No PreToolUse hooks | `.claude/settings.json` has no `PreToolUse` key in hooks |
| No subagent definitions | `.claude/agents/` directory missing or empty |
| Junk accumulation | `.claude/settings.local.json` has >20 session-specific path entries |
| Phase advancement | Spoke phase changed since last audit |
| New spoke onboarding | WAI-State.json exists but CC config is default/minimal |

Also fire when the user invokes `/wai-claude-maximizer` directly.

## Audit Checklist

Read these files and evaluate each area:

### 1. CLAUDE.md (Critical)

**Read:** `CLAUDE.md` at spoke root

**Check for:**
- Project context block (spoke name, stack, phase, modules)
- Development workflow block (ordered build/test/lint commands)
- Plan mode block with phase-appropriate thresholds
- Slash commands block listing available `/commands`
- Standing rules block (security, style, boundaries)
- Anti-patterns block (living document of corrections)
- Hooks reference block (what hooks are configured)

**Ideal:** 100+ lines with all blocks populated. Anti-patterns section grows over time.

### 2. Hooks (Critical)

**Read:** `.claude/settings.json` → `hooks` object

**Check for:**
- `SessionStart` — WAI wakeup / state loading
- `UserPromptSubmit` — session guard / context injection
- `PreToolUse` — destructive operation guard
- `PostToolUse` — formatter / typechecker after file writes
- `Stop` — test suite runner before session ends
- `PreCompact` — state preservation before context compaction

**Ideal:** At minimum SessionStart + UserPromptSubmit + PreToolUse guard. Full setup adds PostToolUse formatter and Stop test runner.

### 3. Permissions (High)

**Read:** `.claude/settings.json` → `permissions`

**Check for:**
- `allow` array with spoke-specific safe commands
- `deny` array guarding destructive operations (`rm -rf`, force-push)
- No `--dangerously-skip-permissions` in global settings

**Ideal:** Targeted allows for the spoke's stack + explicit denies for dangerous ops.

### 4. Statusline (High)

**Read:** `~/.claude/settings.json` → `statusLine` (global)

**Check for:**
- Statusline configured (type: command)
- Script shows model name + context percentage + color-coded bar
- Color thresholds: green <60%, yellow 60-85%, red >85%

**Ideal:** Working statusline with context percentage visible at all times.

### 5. Slash Commands (Medium)

**Read:** `.claude/commands/` directory listing

**Check for:**
- WAI core commands present (wai, wai-closeout, wai-status, wai-time)
- Utility commands (code-simplifier, update-claude-md)
- Commands using inline bash (`!` prefix) for context pre-computation

**Ideal:** All WAI commands + 2-3 spoke-specific workflow commands.

### 6. Subagents (Medium)

**Read:** `.claude/agents/` directory

**Check for:**
- Agent definitions with appropriate memory mode (project/local)
- Isolation settings (worktree for risky operations)
- WAI-native agents (state-sync, lug-reviewer)

**Ideal:** At least 1-2 agents for repetitive workflows. Memory mode set per agent.

### 7. MCP Servers (Low)

**Read:** `.mcp.json` at spoke root

**Check for:**
- GitHub MCP for PR management
- Any spoke-specific integrations

**Ideal:** GitHub MCP at minimum for repos with active PRs.

### 8. Git Worktrees (Low)

**Check:** `git worktree list`

**Check for:**
- Worktrees available for parallel sessions
- WorktreeCreate hook for pre-warming

**Ideal:** Worktree infrastructure ready if parallel sessions are in use.

## Gap Report Format

Present findings as:

```
┌─ CC OPTIMIZATION AUDIT ─────────────────────────┐
│ Spoke: {name}  Phase: {phase}  Score: {N}/8      │
├──────────────────────────────────────────────────┤
│ Area            │ Status │ Priority │ Action      │
│─────────────────│────────│──────────│─────────────│
│ CLAUDE.md       │ [gap]  │ Critical │ [fix]       │
│ Hooks           │ [gap]  │ Critical │ [fix]       │
│ Permissions     │ [gap]  │ High     │ [fix]       │
│ ...             │        │          │             │
└──────────────────────────────────────────────────┘
```

Score = number of areas at or above ideal for the spoke's phase.

## Recommendation Tiers

**Do first** (blocks quality):
- Add deny rules to permissions
- Add PreToolUse guard hook
- Enrich CLAUDE.md with stack + anti-patterns

**High value** (compounds over time):
- Stop hook with test suite verification
- Subagent definitions for repeated workflows
- Clean settings.local.json junk
- PostToolUse formatter hook

**Explore next** (power features):
- MCP servers (GitHub, database)
- `/loop` for async monitoring
- Agent Teams for large refactors (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)
- GitHub Action for CLAUDE.md flywheel (`/install-github-action`)
- `/voice` for dictation input

## Fix Mode

When asked to fix a specific gap:

1. Load `wai-claude-maximizer-reference.md` for the relevant section
2. Read the current file that needs patching
3. Generate a patch that is **additive** — never replace the file, always merge into existing config
4. Present the patch for approval
5. Apply and verify

## Context Budget

- This skill file: load at audit time
- Reference file: load **on-demand only** when generating a specific fix
- Never load reference file at wakeup

## User Reminders

When Ozi detects a CC gap during normal work, surface it as a brief inline suggestion:

> **CC tip:** Your settings.json has no deny rules. Run `/wai-claude-maximizer` to fix, or I can add them now.

Keep suggestions to one line. Don't interrupt flow for low-priority gaps. Only interrupt for Critical items (missing deny rules, no PreToolUse guard).

## Related Skills

- `/wai-ide-setup` — Hook configuration guide
- `/wai-rules` — Project boundaries
- `/wai-status` — Quick health check
