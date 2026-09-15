# max-persona-boundary-guard

Full build record and reasoning: `docs/max-persona-boundary.md`.

## Why this exists

260907, asked live: *"How can I ensure Max is the persona I'm engaging?"*
The orchestrating session's standing rule -- **plans and dispatches,
never codes** -- was in a loaded memory file and violated twice anyway:
`src/basher/providerConfigDir.js` and a deployed `~/.claude/statusline.sh`,
each self-justified as narrow and urgent, with no lug, dispatch record,
fixture or reviewer. Both existing guards (`agent-tool-scope-guard`,
`agent-target-scope-guard`) open with `if (!agent_id) return allow`.
That exemption is the gap.

## What it does

PreToolUse on `Edit|Write|NotebookEdit`. Refuses when both hold: this is
the top-level session, **and** the target is real application code.

**"Dispatched" reuses two existing signals, no third mechanism:** `agent_id`
on the hook stdin (an Agent-tool fork), or a live scope grant in
`<session root>/runtime/dispatch-scope.jsonl` naming this session's own
root, written by `executeDispatch` before the session existed. The second
is load-bearing: a headless dispatched session (`claude -p` under
`launchSpoke`) carries no `agent_id`. So is the `isWithin(cwd, grant.root)`
filter: wheel-hub's own `dispatch-scope.jsonl` carries live grants whose
`root` is a dispatch *worktree*.

**"Application code"** (`src/lugTracking/personaBoundary.js`), on the
first path segment relative to the real repo root: the declarative trees
(`lugs, canon, docs, registry, runtime, ledger, reference, kb, schemas`)
are allowed outright; then a real code **extension** is code; then a
spoke's own **code directory** (`src, scripts, bin, lib, ...`) with a
non-content extension is code (catches `bin/wcl`); anything else is
allowed -- an authorship boundary, not a lockdown.

## Review and merge are never blocked

Structurally: the matcher excludes Bash, so `git merge`, `git commit`,
`git cherry-pick`, `git checkout --ours/--theirs` are unreachable.

## The merge-conflict edge case

**Resolved: hand-reconciling a conflicted application-code file is
original authorship, and is refused.** The refusal names two mechanical
ways through: `git checkout --ours` (a derivation) then dispatch the
reconciliation, or `git merge --abort` and dispatch one session with both SHAs.

## The 260913 ruling: planning outside the spoke

Measured 260913: a write outside every repo classified on extension alone,
so scratchpad launchers were refused and written through bash heredocs
(skirted, not honoured), and the framework's own checkout (no
`canon/profile.yaml`) was always deny.
Operator ruling, session 2776bea2: *"Remediate the max-persona boundary
issue to facilitate planning coming from Max outside the spoke as being
allowed."* Reading taken: Max = the top-level orchestrating session;
outside the spoke = paths outside every repo (its scratchpad) and the
framework's self-hosting checkout, which is not a spoke. Two outcomes:

- **ALLOWED, orchestration scaffold**: no `.git` above the target and not
  provider config (`$HOME/.claude`, `$CLAUDE_CONFIG_DIR`, any
  `provider-claude-config` segment) -> `kind: orchestration-scaffold`,
  allowed, ledger row `ALLOWED -- orchestration scaffold outside every
  repo: <path>`. `~/.claude/statusline.sh` is still refused, same text.
- **WARN in the framework checkout**: no `canon/profile.yaml` and cwd
  `isSelfHostingFramework` (`traceability.js`) -> posture `warn`, every
  write its WARN row. A scaffolded spoke stays `deny`; explicit canon wins.

## Posture

`canon/profile.yaml` ->
`autonomy_table_defaults.max_persona_boundary_guard_posture: deny | warn`;
`resolvePosture` applies the precedence above. `warn` never blocks but
still writes the ledger row.

## Known, accepted gaps

Enumerated in `docs/max-persona-boundary.md`. The largest, deliberate:
this guard never matches Bash, so `cat > src/foo.js <<EOF` gets through;
closing that puts it one heuristic away from refusing `git merge`.
