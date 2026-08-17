# Codex Instructions for {{PROJECT_NAME}}

{{PROJECT_DESCRIPTION}}

Quick start:
- Read this `AGENTS.md`
- Read `WAI-Harness/spoke/local/WAI-State.json` (v3 coexist spokes: `WAI-Harness/spoke/WAI-State.json`)
- Do not read `CLAUDE.md` by default.
- If the user explicitly asks for `/wai` or wakeup behavior, load the first file that exists:
  - `.claude/commands/wai.md` (v4 — invoke `/wai`)
  - `WAI-Harness/spoke/commands/wai.md` (v3 coexist fallback)
  - `WAI-Harness/spoke/skills/wai/wai.md` (v3 coexist fallback)
- During wakeup, finish the WAI Point briefing before asking for teaching approval.
- Do not read full teaching bodies during wakeup unless the user explicitly asks to review them now.
- During `/wai`, output the briefing directly instead of narrating the bootstrap steps you ran.
- After the briefing, use a single readiness line. Do not append a numbered action menu unless the user asked for planning.
- Keep any manual teaching review or stale-task decisions inside a compact `Pending Items` section in the briefing.

If any of those files are missing, ask the user to initialize Wheelwright for this project.

Default optimization rules:
- Do not read `CLAUDE.md` unless the task touches Claude-specific hooks or config.
- Do not preload large WAI history/runtime files.
- Prefer targeted file reads over scanning entire `WAI-Harness/spoke/` trees.

## Tool Ownership (Basher)

**Basher owns all distributed tool files, local-only excepted.**

Two tiers:

1. **Templates + distribution tooling (Basher exclusive):** Basher owns the canonical source templates and everything distributed from `WAI-Harness/spoke/managed/` (tools, schemas, templates, `.claude/` hooks/commands/agents/workflows/settings), plus `MANIFEST.json`, `.mcp.json`, and provider file templates (`CLAUDE.md`/`GEMINI.md`/`QWEN.md`). Route all improvements to these via a complete change-lug to Basher's `incoming/`; Basher edits the canonical source, re-cuts the MANIFEST, and distributes — **this is how we maintain the wheel.**

2. **Placed local instances (Spoke, with receipt-back):** The spoke's own deployed copies (its `CLAUDE.md`, `.env.template`, local `tools/`) are the spoke's to maintain locally. The spoke MAY edit its local copy directly. If the edit is a template improvement worth propagating fleet-wide, emit a complete change-lug (change-receipt) to Basher's `incoming/` so Basher can fold it into the canonical template.

Apply changes directly **only for purely local state** — files under `WAI-Harness/spoke/local/` (lugs, sessions, savepoints, runtime). When in doubt, route to Basher.

## Codex Wakeup Output

- During `/wai`, return the completed WAI Point briefing itself, not a transcript of the checks you ran.
- Do not narrate shell probes, file reads, or step-by-step bootstrap work in the wakeup reply.
- After the briefing, use one short readiness line such as `Wake complete. Ready to work.`
- Do not append a numbered next-steps plan unless the user explicitly asks for planning.
- If review or approval items are pending, keep them inside the briefing under `Pending Items` rather than stopping early.
