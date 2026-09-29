# raw-worktree-add-redirect

Lug `worktrees-clean-themselves-at-fold-and-exit` (audit 2026-09-28 F04):
harness-factory had 25 worktrees in five location styles (sibling
`harness-factory-wt-*`, `hf-wt-*`, `.claude/worktrees`, `.local/worktrees`,
`/tmp/push-gate-*`), and most were made by a raw `git worktree add` the
registry (`runtime/worktrees.jsonl`) never saw -- no owner, no purpose, no
expiry, so nothing could tell a live tree from an abandoned one.

This PreToolUse hook refuses a raw `git worktree add` from a session and
names the registrar verb that does the same thing with the record attached:

    node scripts/worktree.js add [<path>] --branch=<name> [--ref=<start>] --purpose="<why>" --ttl=24h

With the path omitted the tree lands in the one canonical root,
`<repo>/.local/worktrees/<branch>` -- gitignored, and never scanned by the
compiler.

## What it is, honestly

A command-string heuristic, not a parser (`src/hooks/lib/rawWorktreeAdd.js`).
It matches `git [-C dir] [-c k=v] worktree add` at a command position -- the
start of a line or after `;`, `&&`, `||`, `|`, `(`, `$(` or a backtick --
so a quoted mention (`echo "git worktree add"`) or a grep for the phrase
passes. A wrapper script or an alias can still get around it; the backstop
is the worktree gc (`node scripts/worktree.js gc`, run at every session exit
and at the end of `hf deploy`'s fold), which judges every tree git knows,
registered or not, and never removes one holding work that is not on main.
