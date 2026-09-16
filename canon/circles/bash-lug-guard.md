# bash-lug-guard

Ruling 2026-08-26, first of two changes closing the Bash-tool bypass found
live (`IDEAS.md`, 2026-08-26): a lug edited via `sed`/`python3` never
touched `Edit`/`Write`, so `definition-complete-gate`, `ready-gate-stub`,
and `lug-lifecycle-tracker` never saw it. Lug state changes now go only
through the kernel verb (`scripts/lug-verb.js` /
`src/lugTracking/lugVerb.js`); this hook denies the obvious way around
that -- a `Bash` command that writes into `lugs/` directly.

## What it is, honestly

A command-string heuristic, not a parser. It checks each logical line of
the command independently, and denies a line that references `lugs/` and
also looks like a write on that same line: a real write redirect (`>`,
`>>` -- but not a bare fd redirect like `2>` or a fd duplication like
`2>&1`, both of which are common in ordinary read-only commands), `sed -i`,
`tee`, `cp`, `mv`, `rm`, or a `python`/`node` invocation that actually shows
a write indicator (`open(path, 'w'|'a'|...)`, `.write(`, `writeFileSync`) --
`python`/`node` alone is not enough, since both are used constantly for
read-only inspection. A line invoking the kernel verb script is exempt.

Two false positives were found live and fixed 2026-08-26, pre-flight to the
reconciled-gate work order (`IDEAS.md`): a genuinely read-only command
using `2>&1` (a stranger's first `cat lugs/foo.yaml 2>&1` must not be
blocked), and a multi-line command where an unrelated line's redirect
tripped the guard for a wholly innocuous line elsewhere in the same call.
Both are covered by dedicated conformance test cases.

It can still be fooled by a sufficiently indirect command (a wrapper script
not named `lug-verb.js`, an alias), and it can still over-block a
single line that mixes an unrelated write with a `lugs/` mention (e.g.
`cat lugs/x.yaml; rm other-file` on one line). Both are accepted
tradeoffs, not oversights: this is the proactive half of the fix.
`lug-integrity-checksum` (Stop) is the backstop that doesn't need to guess
intent at all -- it just compares what's on disk against what the verb
actually wrote, so whatever slips past this heuristic still gets caught,
just one turn later instead of immediately.

## Sibling check: another repo's canonical checkout (2026-09-14)

A basher-rooted top-level session edited harness-factory's canonical
`src/` in place through Bash, unseen by every guard. After the `lugs/`
check finds nothing, the same hook classifies the command's real write
targets (dispatchScope's heuristic plus a `node -e`/`python -c` that shows
a write call, and a bare `git mv|rm`) through
`personaBoundary.checkCrossRepoWrite`: a non-dispatched session whose
target resolves into a registered repo (own known-repos.json plus the
hub's spoke cards) other than the one it stands in is refused with the
persona guard's cross-repo sentence -- the two sanctioned paths are a
communication lug with `target_spoke`, or `queueDispatch` with
`externalTargets` -- and the refusal lands on both repos' ledgers
(`src/hooks/lib/crossRepoLedger.js`). A linked worktree, the scratchpad,
declarative content and a dispatched session are outside the rule; a
write in the session's own repo is as unseen here as before.
