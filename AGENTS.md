<!-- MANAGED BY BASHER — maintained by `basher tools update`. Do not edit this section directly.
     New entries: (1) document value, (2) declare scope: spoke-local | wheel-wide
     Wheel-wide changes: write a lug to /home/mario/projects/basher/WAI-Spoke/lugs/incoming/ -->

# AGENTS.md — Wheelwright AI Integration (WAI) Bootstrap

**This document is mandatory for new contributors and automated scripts.** It describes the universal WAI bootstrap patterns, key paths, agent types, and session lifecycle used by the Wheelwright framework.

**For Claude Code specifics, see `CLAUDE.md`.**

---

## 1. WAI Agent Types

WAI coordinates AI work through several agent patterns. Each pattern routes work differently within the Wheelwright ecosystem.

### Builder Sub-Agents

**Definition:** Specialized agents dispatched by Ozi (the orchestration autopilot) to complete implementation lugs.

- **Role:** Complete lug tasks in isolation with access to the full git repository and MCP tools
- **Dispatch:** Via `dispatch_method: autopilot-subprocess` in the lug's workflow metadata
- **Scope:** Follows the lug's PEV contract (Perceive → Execute → Verify)
- **Session context:** Starts fresh; does not inherit prior conversation state
- **Standing rules:**
  - Use integrated services (gh, vercel, etc.) directly — do not ask the user to run commands
  - Never suggest `git push` unless explicitly required by the lug or user
  - Never prompt for session ceremony (savepoint, closeout) — users have those skills

### Gardener Agents

**Definition:** Fleet of Haiku-tier agents that run autonomously on a schedule to process teachings, intake lugs, and route signals.

- **Role:** Teaching adoption, lug intake/filing, signal routing, spoke state updates
- **Dispatch:** Cron-driven via the framework (not interactive)
- **Autonomy:** High; makes decisions about teaching adoption and signal delivery
- **Session:** Batched; processes multiple spokes in a single multi-lug session

### General-Purpose & Specialized Agents

**Definition:** AI assistants used interactively within a user session for exploration, code review, planning, and research.

- **Types:** claude (default), Explore, Plan, code-reviewer, and domain-specific agents (e.g., gitnexus-*)
- **Context:** Full conversation history; can reference prior work
- **Scope:** User-directed; may continue across multiple turns

---

## 2. Key Paths

All paths are relative to the spoke root (e.g., `/home/mario/projects/wheelwright/tracks/` for Tracks spoke).

### Core Directories

| Path | Purpose | Notes |
|------|---------|-------|
| `WAI-Spoke/` | Spoke state, lugs, sessions, teachings | Main spoke directory |
| `WAI-Spoke/WAI-State.json` | Project metadata, bootstrap instructions, foundation state | Read on every wakeup |
| `WAI-Spoke/commands/` | WAI command/skill definitions (wai.md, wai-closeout.md, etc.) | Authority for `/wai` and related skills |
| `WAI-Spoke/skills/` | Skill routing index and metadata | Supersedes flat command directory |
| `WAI-Spoke/lugs/` | All lug artifacts, organized by lifecycle | Work queue and history |
| `WAI-Spoke/lugs/bytype/` | Lugs grouped by type: spec/, implementation/, task/, bug/, signal/, epic/ | Primary work interface |
| `WAI-Spoke/lugs/incoming/` | Lugs delivered from hub or other spokes | Intake queue |
| `WAI-Spoke/sessions/` | Session records, one folder per session (YYYYMMDD-HHMM) | Track JSONL files for continuity |
| `WAI-Spoke/seed/ingest/` | Teachings inbox: processed/ and manual/ | Teaching adoption queue |
| `WAI-Spoke/runtime/` | Session guard state and runtime artifacts (gitignored) | Transient state, not persisted to git |
| `.claude/` | Claude Code configuration and hooks | IDE-specific integration |
| `.claude/hooks/` | Pre-tool-guard.sh, user-prompt-submit.sh, pre-compact.sh, stop-test-runner.sh | Lifecycle hooks |
| `.claude/commands/` | Legacy command aliases (backward compat) | Skills/ is the source of truth now |

### Linked Hub Paths

| Reference | Resolved to | Purpose |
|-----------|-------------|---------|
| `framework_path` | `/home/mario/projects/wheelwright/framework` | WAI CLI, teach.py, core framework |
| `hub_path` | `/home/mario/projects/wheelwright/hub/` | Hub inbox, teachings repo, signal relay |

---

## 3. Session Lifecycle

Every user session follows a consistent lifecycle to maintain continuity across AI agents.

### Session Creation

1. User starts Claude Code or invokes an agent
2. Hook `user-prompt-submit.sh` injects the wakeup directive
3. If no session exists, create folder: `WAI-Spoke/sessions/session-YYYYMMDD-HHMM/`

### Wakeup Protocol (MANDATORY — First Turn)

The wakeup sequence ensures all agents have the same context:

1. **Read `AGENTS.md`** — universal WAI bootstrap and key paths (this file)
2. **Read `WAI-Spoke/WAI-State.json`** — project state, wheel metadata, foundation status
3. **Follow `WAI-Spoke/commands/wai.md`** — produces the WAI Point briefing (scope, pending work, constraints)
4. **Check `WAI-Spoke/seed/ingest/`** — review pending teachings from the hub (filenames/frontmatter only)
5. **Then respond** to the user's message

**See `CLAUDE.md` for Claude Code–specific wakeup rules.**

### Session Tracking

After each turn, the agent appends a point to: `WAI-Spoke/sessions/<session-folder>/track.jsonl`

Each point contains:
- `timestamp` — ISO 8601 time
- `user_message` — the user's input (optional)
- `agent_response` — summary of work completed
- `lug_updates` — any lugs opened, closed, or modified
- `token_usage` — estimated or actual token count

### Session Closeout

User runs `/wai-closeout` or `/wai-shipit` skill to:
- Finalize track.jsonl with a closure entry
- Commit any changes to git
- Signal the spoke that this session is complete
- Update WAI-State.json with session metadata

---

## 4. Wakeup Protocol & CLAUDE.md Cross-Reference

The wakeup sequence in CLAUDE.md steps through WAI bootstrap:

```
1. Read AGENTS.md           ← universal WAI + this file
2. Read WAI-Spoke/WAI-State.json
3. Follow WAI-Spoke/commands/wai.md
4. Check WAI-Spoke/seed/ingest/
5. Then respond to user
```

**AGENTS.md is mandatory:** It defines the key paths, agent types, and session structure that all contributors and automated scripts depend on.

**CLAUDE.md is Claude Code–specific:** It overlays additional rules for IDE integration, hooks, and Claude Code commands (e.g., `/wai`, `/wai-closeout`, `/wai-shipit`).

The two files establish a two-way reference:
- CLAUDE.md says "Read AGENTS.md" (step 1 of wakeup)
- AGENTS.md says "For Claude Code specifics, see CLAUDE.md"

This ensures new contributors see the full picture: universal patterns (AGENTS.md) + IDE specifics (CLAUDE.md).

---

## 5. Spoke Architecture Overview

### Lugs: The Work Queue

**Definition:** Lugs are structured, trackable units of work — the primary interface for all AI-driven tasks.

Every lug contains:
- `id` — unique identifier (auto-generated or semantic)
- `type` — spec, implementation, task, bug, feature, signal, epic
- `title` — human-readable name
- `status` — draft, open, in_progress, completed, blocked, on_hold
- `PEV` — Perceive (problem statement), Execute (steps), Verify (acceptance criteria)
- `effort_score` — 1–10 (complexity)
- `quality_score` — 1–10 (quality gate)
- `urgency` — 1–10 (relative priority)
- `routed_to` — LOCAL (this spoke), SIGNAL (hub inbox), or FRAMEWORK (framework spec)

**Lifecycle:** lugs move through `/in_progress/` → `/completed/` and are indexed in `WAI-LugIndex.jsonl` for fast lookup.

### Teachings: Framework Updates

**Definition:** Portable knowledge packages distributed from hub to all wheels. Each teaching is a `.md.teaching` file with:
- Framework pattern discovery or refinement
- `safe_to_auto_adopt` flag (true = auto-adopt after summary, false = require approval)
- `weight` — complexity contribution (1/5/10/25 points)
- `fingerprint` — 3-char derivation from MD5, appended to spoke version on adoption
- Optional `Context Doc Patch` sections to update local docs

**Lifecycle:** Pattern → Signal → Hub Package → Gardener Distribution → Spoke Adoption → wai-context.md Updated

Adopted teachings are tracked in `wai-context.md` header with fingerprints and accumulated weight.

### Signals: Cross-Spoke Coordination

**Definition:** High-priority routing messages for problems that affect multiple spokes or the framework itself.

- Originated as signal lugs in a spoke
- Delivered to hub inbox (`hub/WAI-Hub/signals/incoming/framework/`)
- Processed by hub gardener and re-routed to affected spokes
- Indexed in `WAI-LugIndex.jsonl` for tracking

**Scoping rule:** SIGNAL routing requires:
- `impact >= 8` (affects 8+ team members or multiple spokes)
- Must apply to **every active spoke immediately**

Local or framework improvements are LOCAL or FRAMEWORK type, not SIGNAL.

### Sessions: Conversation Records

**Definition:** JSONL-based conversation ledgers that track AI work continuity within a session.

- Created on first turn: `WAI-Spoke/sessions/session-YYYYMMDD-HHMM/`
- Each entry in track.jsonl is a point: timestamp, message, response, lug updates, token usage
- Enables continuation across agent invocations (same session ≠ same agent instance)

Session records persist even after closeout, forming a historical audit trail of all AI work on the spoke.

### Skills: Routing Authority

**Definition:** Folder-based command/skill definitions that route user actions to the appropriate implementation.

- Root: `WAI-Spoke/skills/index.jsonl` — canonical routing index
- Each skill has: name, description, implementation file, required permissions, inheritance chain
- Legacy `.claude/commands/` are compatibility aliases; skills/ is the source of truth
- Users invoke skills via `/command` syntax (e.g., `/wai`, `/wai-closeout`)

---

## 6. Bootstrap Checklist for New Contributors

When you join a Wheelwright-enabled project:

- [ ] Read this file (AGENTS.md)
- [ ] Read `CLAUDE.md` (if using Claude Code)
- [ ] Read `WAI-Spoke/WAI-State.json` to understand the project's identity and constraints
- [ ] Run `/wai` command (or read `WAI-Spoke/commands/wai.md`) to see the current briefing
- [ ] Check `WAI-Spoke/seed/ingest/` for pending teachings
- [ ] Review `WAI-Spoke/lugs/bytype/` to see what's in scope
- [ ] Familiarize yourself with lug syntax by reading a few existing lugs
- [ ] When you have a new task: create a lug (type: task or implementation), follow the PEV template, and wait for assignment

---

## 7. Common Operations

### Creating a Lug

Use the lug schema in `WAI-Spoke/commands/wai-lug-schema.md` to author a well-formed lug. All fields must be complete before filing:
- PEV (Perceive, Execute, Verify) fully specified
- Acceptance criteria clearly stated
- effort_score, quality_score, urgency estimated
- routed_to set correctly (LOCAL by default)

### Reviewing a Lug

Before implementation, verify:
- PEV is actionable (Execute steps are concrete, not vague)
- Acceptance criteria are checkable (not subjective)
- routed_to is appropriate (SIGNAL only for impact >= 8 AND multi-spoke)
- blocked_by references exist and are unresolved (verify filesystem before treating as blocker)

### Session Continuity

To continue a prior session:
1. If in same conversation window: agents maintain context automatically
2. If in new conversation: follow the wakeup protocol to restore context from `WAI-Spoke/sessions/<session-folder>/`

---

## 8. Anti-Patterns (Enforcement Rules)

The following practices have been corrected multiple times across the fleet. Do not do them:

- **Direct WAI-State.json mutation by hooks:** Use `WAI-Spoke/runtime/session-guard.json` (gitignored) for session guard state
- **Unresolved env vars in hook commands:** Always use absolute `/home/mario/` paths, never `$CLAUDE_PROJECT_DIR` or similar
- **Em-dash in JSON writes:** Never use em-dash in bash `printf`/`echo` writing to `.jsonl` files; use Python `json.dumps()` instead
- **Silent SIGNAL scope violations:** Do not escalate LOCAL problems to SIGNAL without impact >= 8 AND multi-spoke applicability
- **Placeholder lugs:** Never create a lug without complete PEV, acceptance criteria, effort score, and file targets
- **Treating blocked_by as gate without verification:** Check filesystem first; if blocking lug is in completed/ or target file exists, blocker is clear
- **Spec drift on delivery:** If an implementation lug diverges from its spec_id, open a spec update lug (type: spec, status: draft) before closing out

---

## 9. Framework Integration

Wheelwright consists of:

- **Framework** (`/home/mario/projects/wheelwright/framework/`) — WAI CLI, teach.py, gardener, core coordination
- **Hub** (`/home/mario/projects/wheelwright/hub/`) — teaching distribution, signal relay, cross-spoke insights
- **Spokes** (this project + others) — individual wheels, each with their own WAI-Spoke directory and commands

The `WAI-State.json` in this spoke contains pointers to framework and hub so agents can locate shared services.

---

## 10. References

- **`CLAUDE.md`** — Claude Code integration specifics
- **`WAI-Spoke/WAI-State.json`** — Project metadata and bootstrap instructions
- **`WAI-Spoke/commands/wai.md`** — Daily briefing (in-progress work, pending lugs, constraints)
- **`WAI-Spoke/commands/wai-lug-schema.md`** — Complete lug template and field reference
- **`WAI-Spoke/KnowMe.md`** — This spoke's identity, priorities, and architecture
- **`WAI-Spoke/wai-context.md`** — Teaching adoption fingerprints and framework version

---

**Document Status:** Active — Established 2026-06-14  
**Last Updated:** 2026-06-14  
**Framework Version:** 1.0.0
## Wakeup Convergence

- Finish the WAI Point briefing before asking for approval on teachings or side actions.
- During wakeup, summarize teachings from filenames/frontmatter only.
- Do not read full teaching bodies during wakeup unless the user explicitly asks to review them now.
## Codex Wakeup Output

- During `/wai`, return the completed WAI Point briefing itself, not a transcript of the checks you ran.
- Do not narrate shell probes, file reads, or step-by-step bootstrap work in the wakeup reply.
- After the briefing, use one short readiness line such as `Wake complete. Ready to work.`
- Do not append a numbered next-steps plan unless the user explicitly asks for planning.
- If review or approval items are pending, keep them inside the briefing under `Pending Items` rather than stopping early.
## TasteGraph (Operator Preference Model)

If `WAI-Spoke/tastegraph.json` exists, load it at session start.
This file encodes operator preferences (work style, risk posture, communication register)
and overrides generic defaults for tracking, response style, and decision-making.
- Do not generate or modify `tastegraph.json` during normal sessions.
- For cross-interface portability, use `/wai-tastegraph export --format prompt`.
## Codex Startup Duties (No Hook Equivalents)

Codex has no lifecycle hook surface equivalent to Claude Code. The following behaviors are automatic in Claude Code but **manual in Codex**:

| Claude Code Hook | Codex Manual Equivalent |
|------------------|-------------------------|
| SessionStart | Run /wai manually at session start; wakeup brief is not pre-computed |
| UserPromptSubmit | Check wakeup brief freshness; session guard state is not auto-injected |
| PreToolUse | Apply manual caution before rm, git reset --hard, force-push, and similar |
| Stop | Run verification steps manually before ending session; no auto track flush |
| PreCompact | Save important context manually before running /compact |
| PostToolUse | Verify Python file syntax after edits: python -m py_compile <file> |
| PermissionRequest | Not applicable — Codex has no permission request hook surface |

**Session closeout:** Run `./wai-exit.sh` (or `/wai-closeout`) at session end to commit state, update session history, and save track data.
