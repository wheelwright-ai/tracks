# worktree-registry

Every git worktree the harness makes is recorded with **who, for which
prompt, why, and until when**, and is removed on its creator's own exit
path. Lug: `every-harness-worktree-carries-its-session-purpose-and-expiry`.

## Why

2026-09-14: 17 stale worktrees across harness-factory and wheel-hub, none
saying which session made it. One was traced only by grepping transcripts.
A worktree with no owner cannot be folded, judged or cleared safely.

## The store

`<instanceRoot>/runtime/worktrees.jsonl`, `kind: worktree_row`,
append-only, last row per `id` wins. Fields: `repo, path, branch,
head_at_create, session_id, prompt_id, purpose, created_at, ttl_ms,
expires_at, closed_at`. A removal appends the same row with `closed_at`,
`closed_by`, `removal` (what was done) and `forced` (the reason, or null).
`purpose` is required. `session_id` comes from `WHEEL_SESSION_ID` /
`CLAUDE_CODE_SESSION_ID` or is written **null** -- never guessed. The
script refuses `add` without `--ttl`: an expiry nobody declared is not a
default to invent.

## The verbs

`addWorktree` runs `git worktree add` and registers in one call -- the
only sanctioned way in `src/` (the fixture greps). `removeWorktree` is the
only removal: it runs `git cherry <main> <branch-or-HEAD>` and **refuses,
naming the commits**, while any `+` line remains; a dirty tree (tracked or
untracked, a symlinked node_modules excepted) is refused too. `force`
needs a reason; the closed row keeps it. When clear it removes the tree
and deletes the branch with `-D` (cherry-picked commits are on main by
patch id, not as ancestors, so `-d` would wrongly refuse).

`scripts/worktree.js add|list|remove|reap` is the orchestrating session's
verb -- the dispatch recipe uses `add` instead of raw git. `reap` removes
expired rows whose branches are fully on main and lists every other open
row with why it stays.

## Where the harness makes worktrees

- `rollbackCut` (cutUpdate.js): a detached checkout of the pinned commit,
  registered at the spoke, removed in `finally` (forced: read-only).
- `stageFold` (deploy.js): the integrate tree, registered at the hub,
  removed in `finally` (forced: its commits are cherry-pick copies).
- `stageClean` (deploy.js): folded dispatch trees, through `removeWorktree`.

## Readers

`healthSignals.stale_worktree` judges every linked worktree git lists:
named by a live dispatch row -> owned; only terminal rows, expired, or its
session registered here and gone -> stale, with session/purpose/age; no
store knows it -> **unregistered**, with the creating commit's sha, author
and date (the branch's first commit off main, else the checked-out one)
and git's admin-dir mtime. Every row carries the `worktree.js remove`
command. `buildHandoff` lists the ending session's open rows.
