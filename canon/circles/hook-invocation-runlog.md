# hook-invocation-runlog

This harness runs 33 hooks on every session start, prompt submit, tool
call and turn end. Until this circle, not one invocation left a record of
how long it took or whether it succeeded. The motivating case (full
account in `docs/hooks-have-no-per-invocation-timing-and-outcome-log.md`):
hooks bound in `readdirSync` order ran the session-triple announcer last,
so every ledger write on a spoke's first session was refused, 30 of 30,
while the injection reported "15 new finding(s)" that were all refusals.
A per-invocation outcome log would have shown that on day one.

## What it does

`src/hooks/lib/hookRunlog.js` (write) and `hookRunlogReport.js` (read), on
the one dispatch point every hook already passes through:

- **Write.** `makeCapture` (`src/hooks/lib/hookIO.js`) appends one compact
  row to `runtime/hook-runlog.jsonl` on the way out: hook name, event,
  duration, exit code, outcome, session id, pid. Two clocks: `duration_ms`
  is wall time since the process's `timeOrigin` (what the hook's `timeout`
  bounds); `work_ms` is from `makeCapture` to exit.
- **Read.** `buildHookRunlogSection` aggregates rows per hook and reports
  only what crosses a threshold: p95 at or past half the hook's own
  declared timeout, or any invocation that did not exit clean. Rides on
  `runWarmup`; null, byte-for-byte unchanged, when nothing is over.

## The failing hook is the whole point

A hook that throws never reaches `capture.exit`, so `makeCapture` also
registers `process.on("exit")`: a throw, an unhandled rejection and a bare
`process.exit` all still produce a row, tagged
`recorded_via: "process_exit_fallback"`, with the real exit code. The
message comes from `uncaughtExceptionMonitor`, not `uncaughtException`, so
the hook still dies exactly as it would have and its exit code is
unchanged. Proven in the fixture.

## Same shape as the scheduler failure channel

Three properties copied from `src/otto/schedulerFailureChannel.js`, which
surfaced 544 silent failures readably: derived from rows on disk, never
accumulated (the only persisted state is what was already announced);
aggregated, at most six hook lines; live only, so a hook that stops
failing disappears on its own.

## Bounded by canon

`canon/policies/hook-runlog-retention.policy.yaml`: 4 MiB, one retained
generation, rotation disclosed with real dropped-row and dropped-byte
counts. Measured: 257-byte rows x 10,020 real invocations across 58
sessions and both repos, plus 20% -- the same `cap_history` formula every
admission rule uses.

## Cost, measured

True A/B against `HEAD`'s `hookIO.js`, three replicates of n=120: +2 to
+6 ms per invocation, 2-4% of a ~160 ms hook process; the write itself is
0.109 ms p50 / 0.243 ms p95 (n=3000). The rest is ESM module load, which
is where the one real regression lurked: an import of `findLiveHookCircles`
cost 22 ms per hook process. Found by this circle's own instrument before
it shipped, and removed.

## What it does not do

It does not repair and does not notify: a hook fails inside a live session
whose agent already reads the session-start surface, so a second channel
would be noise. It does not record a binding that points at a missing file
-- no process, no row; that gap is `hook-binding-drift`'s.

## Counter-metric

`silent_hook_failure_rate`: of hook invocations that did not exit clean,
the fraction that left no record anywhere. The number this circle exists
to move off 100%.
