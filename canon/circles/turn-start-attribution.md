# turn-start-attribution

260831-FBL-057 ruling 2: turn cost used to be attributed by querying the
active-lug/active-advisor pointers live, at `Stop` time. That silently
orphans a turn's own real cost whenever the same turn both opens and
closes a lug (`in_progress` then `done`): `done` clears the pointer via
`clearActiveLug` before `Stop` ever runs, so the live query at `Stop`
time finds nothing to attribute that turn's build cost to -- discovered
live on `bash-destructive-command-guard-widening`'s own build turn.

## What it is, honestly

Captured once, at `UserPromptSubmit` -- the turn's real start, before
anything the turn itself does can have changed it. The snapshot records
the same real, multi-repo-swept lug/advisor resolution
`stop-turn-marker` has always used (`resolveActiveAttributionAcrossRepos`,
`src/lugTracking/activeAttribution.js` -- one authored home for that
resolution, not two copies of it), so a lug active at a turn's start
stays attributed to that turn no matter what the turn itself does to the
pointer before `Stop` fires.

`stop-turn-marker`'s own `Stop` hook consumes (reads, then deletes) this
snapshot instead of re-querying live state. When no snapshot exists --
this hook ran before `turn-start-attribution` existed, or a `Stop` fires
with no matching prior `UserPromptSubmit` -- it falls back to the old
live query, the pre-fix behavior, never a crash and never a guessed
attribution.

## Known, accepted gaps

This only fixes attribution for a lug that was ALREADY active when the
turn began. A lug that is both opened (`in_progress`) and closed
(`done`) entirely within one turn -- never active at that turn's own
start -- is not covered: at `UserPromptSubmit` time there was nothing
yet to snapshot. That narrower case is a real, separate gap (found live
on this exact lug's own build cost, recorded as lost-to-this-bug rather
than reconstructed), left open rather than papered over with a guess.
