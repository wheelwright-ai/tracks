# warmup-goals-review

Part C's C4 (ruling 2026-08-27), built on the authoritative injection
pattern the controlled B4 re-run validated (`docs/B4_CONTROLLED.md`): a
real signal, not a clean win, but a directional one -- stating a source's
authority (path, hash, mtime, an explicit no-re-read-unless-changed
instruction) measurably reduced re-reads across four controlled cycles.
This circle applies the same underlying idea to a different problem: B4's
own conclusion was that passive context injection (session-continuity-checkpoint)
did not, by itself, stop the model choosing to re-verify. "A structured,
directive goals review is a stronger lever than passive context
injection" -- this circle is that lever.

## What it does

Bound to `SessionStart`, alongside `session-continuity-checkpoint` and
`session-start-warmup` on the same event. Builds the ready-work queue
(`src/conductor/readyWork.js`: definition-complete, `readiness: "passed"`,
inside the autonomy line -- all three, not a subset), runs it through
Conductor's routing plan (`src/conductor/conductor.js`), and injects a
**directive** summary: name the top few ready lugs and where Conductor
would route them, and say to proceed with the highest-priority one unless
there's a specific reason not to.

**The honest common case:** `readiness: "passed"` cannot happen without a
real fresh-context check (increment 7, not built), so the ready-work queue
is empty in every real instance today. Rather than going silent, the
review names the single lug closest to ready-work and states exactly what
blocks it -- still directive, still a real next action, not a placeholder.

Target: under 300 tokens (earlier default). Silent only when there are no
lugs in `lugs/` at all.

## What it is not

Not `session-continuity-checkpoint` (B3) -- that's passive in-flight-state
recall, already loaded before this circle runs. Not a real Proofer
certification -- every routed decision's `outcome_at_proofer` stays an
explicit `"pending"`. Not a real multi-node routing choice -- wheel-hub's
registry has exactly one real node today, so "cheapest capable node" and
the 10% exploration fraction are both honest about having nothing to
choose between yet; the mechanism is real and tested, the choice isn't
interesting until a second node exists.

## The autonomy line, honestly

`isInsideAutonomyLine` (`src/conductor/readyWork.js`) uses
`profile.autonomy_table_defaults.lug_execution` -- real data every profile
already carries (`src/factory/interview.js`'s `buildAutonomyDefaults`,
derived deterministically from `autonomy_comfort`: low/medium/high ->
propose/auto_with_notify/auto), not invented here. `auto` and
`auto_with_notify` are inside the line; `propose` is not. This is the
simple, three-cell profile-default table, not the fuller "every cell
stated," per-task-class table with overlays and outcome-driven
promotion/demotion design doc section 7 describes as increment 9's
deliverable -- that richer table is genuinely not built, and Conductor
only ever reads the simpler one that already exists.
