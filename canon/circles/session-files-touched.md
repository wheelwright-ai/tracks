# session-files-touched

Lug `session-exit-commit-sweeps-a-peer-lanes-in-flight-files` (260914):
on the shared harness-factory checkout a peer session's SessionEnd
exit-commit `git add -A`'d basher s128's in-flight, mid-verification
`wclEntry.js` edit and committed it as "Session work: 3 files, no lug
transitions recorded". Two interfaces share one tree; the exit hook did
not know whose files it was taking. This circle is the "whose" half --
the record the `session-exit-commit` circle reads at exit.

## What it does

Bound to `PostToolUse`, matcher `Edit|Write|NotebookEdit|Bash` -- fires
after every tool call that can write has completed. Runs the write-scope
guard's own target extraction (`writeTargetsForTool`,
`src/lugTracking/dispatchScope.js`: `file_path` / `notebook_path` for the
editors; redirects, `tee`, `dd of=`, `sed -i`, `cp`/`mv`/`rm`/`mkdir`/...
for Bash) over `tool_input`, and appends one row per target to
`runtime/files-touched/<session_id>.jsonl` under the session's cwd:

```
{ kind: "file_touched", session_id, agent_id, tool, path, evidence, at }
```

`path` is absolute and alias-free (realpath of the deepest existing
ancestor, so a WSL `/mnt/<drive>` alias and its `$HOME` checkout compare equal).
`agent_id` is set when the call was a dispatched fork's -- a fork's writes
are its parent session's writes for exit purposes, and the id says which
fork.

A read-shaped call (`ls`, `git status`, a `cat`) yields no targets and
records nothing -- no row, no file.

## What it deliberately does not do

Never blocks: PostToolUse runs after the call already landed. Never
prints on allow. Exits 0 even when the record cannot be written -- the
tool call it observed is not this hook's to fail, and the exit commit has
the session transcript as its second source for exactly this case.

Cannot see a write made inside an interpreter (`python3 - <<EOF ...
open(f, "w")`), a heredoc script that writes, or a subprocess a script
spawns. That is the same blindness the write-scope guard has, by the same
construction. The exit commit reports such a file as **left,
unattributed** in its trailer and ledger row rather than taking it -- the
honest outcome is a named file in the operator's view, never a guess.

## Consumers

`session-exit-commit` (reference/circles/session-exit-commit.yaml,
"Whose files"): reads this record for the exiting session (own files),
every OTHER session's record under the committed repos (which lane a left
file belongs to; whether a lane is still live for contention), and unions
the exiting session's transcript. Stages only own + hook-written harness
state, by pathspec.
