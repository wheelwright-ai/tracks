# dispatch-run-salvage

Lug: `advisor-autopilot-loses-all-work-when-the-budget-backstop-fires`.
Full build record, with all measurements:
`wheel-hub/docs/advisor-autopilot-loses-all-work-when-the-budget-backstop-fires.md`.

A dispatched session killed by the wall-clock backstop used to lose
everything. This circle changes what survives a kill. It does not change
the kill.

## The failure, measured

2026-09-09T22:20Z, the first autonomous Conductor wake: otto ran 303216ms
against a 300000ms budget and was **still producing** when killed ("123
progress events, last 123ms ago"); kb-curator ran 305599ms. Neither was
wedged. Both kept nothing, and kb-curator's row shows
`child_session_id: null` -- the harness could not name the session whose
work it lost.

The cause is mechanical. The supervisor captures the child's stdout into
an **in-memory** ring, and the only thing read out of it is
`parseStreamJsonResult`'s terminal `{"type":"result"}` event. A child
killed mid-stream never emits one, so that function correctly returns
null and the buffer dies with the supervisor. The work was done; the only
record of it was volatile.

## What it does

1. **Journals in flight** (`src/lugTracking/dispatchJournal.js`), driven
   from the supervisor's own `onProgress`. It must be the supervisor:
   `runWithIdleWatchdogSync` is `spawnSync`, so the caller is blocked and
   cannot observe anything until the child is already dead. Bounded on
   bytes and events, and it says in the file when it hits a bound.
2. **Recovers the session id.** Claude Code emits `session_id` in its
   *first* event (`system`/`init`), not only its last -- so journaling
   names a killed run's session, the field every killed dispatch on
   record had as null.
3. **Records a structured verdict** (`src/lugTracking/dispatchSalvage.js`):
   `work_disposition` on the dispatch row -- what was kept (counted, from
   disk) and what is unfinished (always the literal `"unknown"`). The
   prose `outcome_detail` is left **verbatim**; it was already honest and
   the lug requires that honesty survive.
4. **Derives the budget** (`src/otto/advisorBudgetMeasurement.js`) from
   real completed runs, and refuses below three of them.
5. **Reports once, by cause** (`src/otto/advisorRunLossChannel.js`), on
   the session-start surface. One line per `advisor/watchdog`, with a
   count. No lug is filed.

## The honesty rules

- **The remainder is unknown, always.** Never estimated from how far the
  run got -- interpolating "80% done" would invent the thing the kill
  destroyed.
- **Three verdicts, never merged:** `killed_with_work_kept`,
  `killed_with_nothing_durable_kept`, `killed_extent_unknown`. The third
  exists because a *bounded* ledger scan must not report a zero it did
  not earn: "I found nothing" and "I did not look far enough" differ.
- **Finishing early is not a fault.** `finished_on_its_own`, no
  unfinished section, and no language calling unused budget waste.
- **The budget sample is right-censored, and says so.** Completions all
  fall under budget because longer runs were *killed and never became
  samples*. The observed maximum is a **lower bound**; the censoring rate
  is stated; every recommendation is provisional.

## What it is not

Not a budget increase -- that moves the cliff without removing it, and a
longer run that still records nothing costs strictly more.

It also cannot make a model write incrementally. The advisor prompt has
always *asked* for that, and an instruction cannot carry that guarantee.
What is enforceable from outside the child is: never lose what it did
emit, always know whether incremental landing happened, and never
overstate. This circle does those three.
