# WAI Rules

Display project identity, scope boundaries, and AI behavior guidelines.

## What It Does

Shows the project foundation and behavioral guardrails:

1. Project Identity - What is this, why exists
2. Scope - What is in scope, what is out
3. Constraints - Technical/organizational limits
4. Collaboration style - How AI and human work together
5. AI Guidelines - Behavioral rules from skills system

## When to Use

- Scope drift detected: Confirm boundaries
- New contributor: Understand constraints
- Decision point: Check if work aligns
- Uncertainty: What are the rules?

## How It Works

1. Read project foundation from WAI-State.json
2. Display identity, boundaries, constraints
3. Show collaboration model (ADAPTIVE, YOLO, etc.)
4. Reference skill files for behavioral details

## Example

User: /wai-rules

AI Output shows:

Identity:
- Type: Framework
- One-liner: Build AI wheels that roll forward forever
- Success: Any AI assistant can pick up any project with full context

Scope:

In Scope:
- Core framework code (Python modules, skills, templates)
- Wheel templates and schemas
- Hub creation and management
- Spoke loader architecture
- Documentation and learning protocols

Out of Scope:
- Hub storage (users manage separately)
- IDE extensions (separate repo)
- Browser extensions (separate repo)
- Website (separate repo)
- Project-specific implementations

Constraints:
- AI-agnostic (work with Claude, GPT, etc.)
- Lightweight (minimal dependencies)
- Non-coding support (research, writing, design)

Collaboration: ADAPTIVE Mode
- Small tasks: AI autonomous
- Significant features: Plan, Approval, Implement
- When in doubt: Propose plan

Autonomy (P10): Trust is the default
- Run standard commands without asking (git, python3, bash, file ops)
- Do NOT chain confirmation pauses for safe sequential operations
- Pause ONLY for: destructive irreversible actions, actions affecting shared systems
- Proceed and report — don't interrupt flow

Behavioral Rules: See skill files, not inline
- Complexity: wai-complexity-gate.md
- Scope drift: wai-stewardship-guard.md
- Foundation: wai-foundation-gate.md

## Tool Ownership (Basher)

**Basher owns all distributed tool files, local-only excepted.**

Two tiers:

1. **Templates + distribution tooling (Basher exclusive):** Basher owns the canonical source templates and everything distributed from `WAI-Harness/spoke/managed/` (tools, schemas, templates, `.claude/` hooks/commands/agents/workflows/settings), plus `MANIFEST.json`, `.mcp.json`, and provider file templates (`CLAUDE.md`/`GEMINI.md`/`QWEN.md`). Route all improvements to these via a complete change-lug to Basher's `incoming/`; Basher edits the canonical source, re-cuts the MANIFEST, and distributes.

2. **Placed local instances (Spoke):** The spoke's own deployed copies are the spoke's to maintain locally. The spoke MAY edit its local copy directly. If the edit is a template improvement worth propagating fleet-wide, emit a complete change-lug to Basher's `incoming/` so Basher can fold it into the canonical template.

Apply changes directly **only for purely local state** — files under `WAI-Harness/spoke/local/` (lugs, sessions, savepoints, runtime). When in doubt, route to Basher.

## Related Skills

- /wai — Full briefing
- /wai-stewardship-guard — Scope drift detection
- /wai-foundation-gate — Foundation enforcement
