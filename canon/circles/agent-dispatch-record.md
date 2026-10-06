# agent-dispatch-record

Lug `interrupted-agent-builds-are-recorded-surfaced-and-resumable`. On
2026-10-02 a session died with six Agent-tool builders in flight. The next
session start said "nothing is in_progress", the briefs had to be dug out
of a 21MB transcript, and the builders' write grants had expired.

## What it writes

At PreToolUse on every Agent call, one row in
`runtime/agent-dispatches.jsonl` (at the repo's MAIN checkout, so a session
in its own worktree writes where the next session start looks):

- `id`, `session_id`, `prompt_id`, `tool_use_id`, `description`,
  `subagent_type`, `at`
- `worktrees` -- the open rows of `runtime/worktrees.jsonl` whose path the
  prompt names (path, branch, repo, base commit)
- `lugs` -- the lug files and lug names the prompt names
- `grant_ids` / `grants` -- the live scope grants for those worktrees
- `brief_path` -- `runtime/agent-briefs/<id>.md`, the prompt after
  credential redaction

It never denies and never adds context. Any failure inside it exits 0.

## Who reads it

- Session start, section `INTERRUPTED BUILDS`
  (`src/conductor/interruptedBuilds.js`): every record with no completion
  mark whose worktree is dirty or holds commits not on the main checkout's
  current branch, with the resume command.
- `node scripts/dispatch-resume.js <id>`: re-issues grants for exactly the
  record's worktree paths with a fresh expiry and prints the brief path and
  a resume preface. `--list` prints the open records. `--done <id>` writes
  the completion mark. A record whose commits have all landed is marked
  done automatically.

A redispatch whose prompt carries the resume preface (it names the record
id) is linked to that record and replaces it in the section. Any other
later dispatch into the same worktree -- a reviewer -- replaces nothing.
A subagent type that cannot write (Explore, Plan, pattern-gate) is
recorded but never listed.

## What it is not

It does not know whether a fork is still running. A build dispatched by a
session that is still live is listed as "STILL LIVE -- may be in flight".
Briefs are not pruned yet.
