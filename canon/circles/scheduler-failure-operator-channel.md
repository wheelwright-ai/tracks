# scheduler-failure-operator-channel

Counted live from wheel-hub's own ledger on 2026-09-09: **632 of 2,441
wheel-scheduler rows were failures**, in five classes, over four days.
`wheelScheduler.js` caught every one and wrote a ledger row; nothing read
those rows. The cron log is empty by design. A scheduled job that fails
silently for a week is indistinguishable from one that never ran.

## What it does

`src/otto/schedulerFailureChannel.js`, on two real surfaces that already
existed rather than a new one:

- **The tick.** `tickWheelScheduler` calls `recordSchedulerFailures` after
  the tick's own rows are on disk. When a job's consecutive-failure count
  crosses the threshold (3), one toast goes out through
  `src/basher/notify.js` -- the same WSL2 -> Windows bridge the
  agent-waiting circles ride, gated by the same per-spoke posture -- and a
  durable ledger row is written whether or not the toast lands.
- **Session start.** `buildSchedulerFailureSection` is another section on
  `buildFullGoalsReviewInjection`, beside reference-aging and
  footer-misses. It reports failure classes with counts, first-seen and
  last-seen, and names the open lug (if any) that already covers each.

Both read the same derivation: streaks and classes come from the real
wheel-scheduler ledger rows, not from a counter this module keeps. The
only persisted state is which streak has already been announced
(`runtime/wheel-scheduler-failure-notices.json`), which is a fact about
this channel and cannot be derived from the scheduler's own rows.

## Noise is the same failure in a different costume

632 individual alerts would train the operator to ignore this channel as
thoroughly as 632 unread ledger rows already did. So the toast fires on a
streak, once per streak, per job; the session-start section reports
classes, not rows; and a class an open lug already names says so.

## What it does not do

It does not fix the failures. Two real classes are live as this ships and
both stay lugged elsewhere: the four "no frameworkRoot" jobs
(`wheel-clock-catchup-only-advanced-on-sessionstart` -- the cron
deliberately passes none, because supplying it ran a catch-up call past
120s) and the ENAMETOOLONG that this lug did fix at its cause
(`p0LugName`, bounding auto-opened P0 lug names).

It does not claim a lug match it cannot prove. The known-lug join is a
*mention* join: an open lug qualifies only if its own text contains the
exact job key **and** one of the failure's signature tokens (an error code
like `ENAMETOOLONG`, or a camelCase identifier like `frameworkRoot`) --
two deterministic regexes, no similarity scoring. A failure whose summary
has no such token is reported as NOT LUGGED rather than guessed at, and
every match prints the lug's name so a wrong one is visible instead of
silently suppressing the finding.

## Counter-metric

`silent_scheduled_failure_rate`: of all wheel_clock job failures, the
fraction that never reached the operator through either surface. The
number this circle exists to move off 100%.
