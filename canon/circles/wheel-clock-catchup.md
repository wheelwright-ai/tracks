# wheel-clock-catchup

lug: wheel-clock-sessionstart-catchup-tick (MAX-085) built the real
mechanism -- `src/otto/wheelClockCatchup.js` (owed-ticks-from-elapsed-
wall-clock-time, ceiling 5, carry-forward debt) wired into a real
SessionStart hook, `src/hooks/wheelClockCatchupHook.js`. That lug's own
outcome record shipped the mechanism and bound it directly into
harness-factory's own `.claude/settings.json` (correct for this
self-hosting instance's own compile) but never declared a real,
distributable circle for it. No circle meant no binding ever reached an
adopted spoke's own generated `.claude/settings.json` -- confirmed live
on wheel-hub, the highest-value spoke for this mechanism (owns
`advisor_activation`, cadence 1): the hook had never once run there,
`runtime/wheel-clock-catchup-state.json` didn't exist, and
`wheel-scheduler-state.json` sat frozen at tick 6 for 9 days.
(lug: wheel-clock-catchup-hook-undeclared-and-undistributed). This
circle is that missing declaration.

## What it does

At every real `SessionStart`, it runs `runWheelClockCatchup`
(`src/otto/wheelClockCatchup.js`): computes ticks really owed from
elapsed wall-clock time against this instance's own persisted
`runtime/wheel-clock-catchup-state.json`, fires them through the
unmodified `runWheelSchedulerFor`, and reports what ran (or didn't) as
`additionalContext`, the same "loud fact at wakeup" convention
`global-settings-drift-check` already established. A ceiling (5
ticks/call) bounds a single catch-up; any excess owed time carries
forward as disclosed debt rather than being dropped. A thrown error
inside the mechanism never blocks the real session start.

## Why this is a circle now, and not before

`checkHookBindingDrift` (`src/factory/hookBindingDrift.js`) only ever
flags a binding as missing when a DECLARED live circle names it and the
real `settings.json` doesn't have a matching binding -- it walks
canon's own circles, not the hook scripts on disk. A hook file that
exists, is wired into one instance's `settings.json` by hand, but names
no circle anywhere is invisible to that check by construction: there is
nothing in canon to compare against. That's exactly what happened here,
and it's also the CLASS defect this lug's own acceptance bar closes
separately (`hookBindingDrift.js`'s own `findUndeclaredHooks`) -- this
circle closes the one real instance already found; that function closes
the class so the next one doesn't need an advisor to notice its own
clock stopped.

## What it does not do

It does not touch the tick-vs-wall-clock tradeoff, the owed-ticks
formula, or the ceiling/overflow design -- all already shipped and
accepted by wheel-clock-sessionstart-catchup-tick's own outcome record,
out of scope here. It does not run real advisor dispatches as a side
effect of THIS circle's own declaration landing -- whether a catch-up
fires anything on a given session start depends entirely on whatever
owed ticks and due jobs `runWheelClockCatchup`/`runWheelSchedulerFor`
already compute, unchanged by this circle existing.

## Hook mode (lug wheel-clock-tick-exceeds-sessionstart-hook-timeout-and-replays)

From the SessionStart hook, runWheelClockCatchup runs with hookBudgetMs
(the binding's own timeout in .claude/settings.json, compiler default
30s): the baseline is written BEFORE the ticks run, each firing is
recorded as it completes, and jobs a hook cannot afford are DEFERRED to
the cron driver (scripts/wheel-clock-cron.mjs, which runs everything).
HOOK_DEFERRED_JOBS in src/otto/wheelScheduler.js is the documented
default (a provider call, a dispatch, a detached child, or a measured
cost near the budget); a job may override it with hook_safe: true|false;
past half the budget whatever is still due waits. Each deferral is one
ledger row (attribution wheel-clock-catchup, deferred_job_key,
deferred_reason), named in the wakeup context. The lease's staleness cap
is the budget, a dead holder's sidecar is reclaimed on the way in, and
SIGTERM releases held locks (SIGKILL cannot be caught -- state-before-work
is what makes a killed tick owe nothing already done).
