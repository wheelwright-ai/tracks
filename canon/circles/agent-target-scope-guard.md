# agent-target-scope-guard

260902-FBL-101 item 2, sixth standing lesson: a scope-**declaration**
guard and a target-**path** guard are two different mechanisms, and until
this circle the wheel only had the first.

## Why this exists

During 260902-FBL-100 a fork dispatched via the Agent tool for one
workstream (harness-factory + wheel-hub) ran a cross-spoke migration
against `<home>/projects/minder` -- a third, live repo named by
neither workstream.

`agent-tool-scope-guard` could not have caught it by construction: it
matches restrictive *language* in the dispatching prompt. This fork
declared no restriction, so there was no language to match, and nothing
bounded *where* it wrote. `fbl-065-followup` keys off the same
self-declaration. The re-dispatch that stayed in scope did so because the
coordinating session phrased the retry defensively -- not a structural
guarantee. This circle is the structural guarantee.

## What it does

Fires at PreToolUse on `Edit|Write|Bash`, only for calls made from inside
a dispatched fork -- real hook stdin carries `agent_id`/`agent_type` on a
sub-agent's own tool calls and not on the parent's (verified against 1150
real captured fork tool calls in `docs/live-hook-capture.jsonl`). A parent
session's writes are outside this circle entirely.

It resolves the real path(s) the call would write to and compares them
against the target scope in force, in two layers
(`src/lugTracking/dispatchScope.js`):

1. **dispatch-record** -- live grants in
   `<session root>/runtime/dispatch-scope.jsonl`, written by the
   *dispatcher* (`dispatchMechanism.executeDispatch`, from the dispatch
   row's `granted_paths`) before the session exists. Authoritative and
   narrow. A session cannot author the grant that binds it, and neither
   can its forks.
2. **workstream-default** -- no grant on disk (interactive session, or a
   launch predating this circle): the real repo the session is rooted in,
   plus every repo this instance's own `.local/known-repos.json` really
   registers and that really exists. Both are real on-disk declarations,
   neither is prose. This layer catches FBL-100: `minder` is registered in
   no wheelwright `known-repos.json`.

Multi-path and wheel-wide dispatch are the normal case: a grant carries a
list, and a wheel-wide dispatch names each real root.

A write outside scope is denied with a reason quoting the real target, the
granted paths, the write evidence and the scope's origin, plus a permanent
`row_kind: decision` ledger row. Reads are never bounded. Posture is
profile-configurable (`autonomy_table_defaults.
agent_target_scope_guard_posture: deny | warn`, default `deny`), the
convention `bash-destructive-command-guard` already uses; `warn` never
blocks but still writes the row.

## Relationship to the FBL-065 layers

Additive. Both FBL-065 layers are untouched -- different trigger, input
and concern tag (`agent-target-path-enforcement`). This circle would not
have refused FBL-100's properly-scoped second dispatch, which a blanket
declaration-then-block rule would have.

## Known, accepted gaps

- Bash write detection is a heuristic command-string match, not a parser:
  redirects, `tee`, `cp/mv/rm/mkdir/touch/ln/install/rsync`, `sed -i`,
  `dd of=`, `git -C <dir> <write verb>`. It misses writes inside
  `node -e`, `python -c`, an invoked script, or a runtime-built path.
- Concurrent forks under different grants are bounded by the union of
  those grants: real hook stdin carries no mapping from a fork's
  `agent_id` back to the Agent call that created it. A grant's optional
  `subagent_type` narrows this.
- Paths are `realpath`-resolved before the boundary check, so a symlink
  into a granted directory is judged by its real target.
