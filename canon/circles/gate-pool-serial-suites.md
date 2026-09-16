# gate-pool-serial-suites

Lug: `three-suites-flake-only-inside-the-gate-pool-and-block-every-push`.
Full account, with the measurements: `docs/gate-pool-serial-suites.md`.

## What it closes

Seven gate runs on 260912: three suites green alone every time, red
inside the pool -- liveness-lease (C1, C3, C4, C5, C6), launch-idle-watchdog
("a progressing child ... killedBy idle"), cross-provider-verification
("the provider it selected is on the record too", 3 push refusals at
236/237). The gate's verdict depended on the pool, not the code.

## The mechanism

- **Serial-first.** The three suites carry `// serial -- <measured
  reason>` at their head; `suitePool.js` reads the marker from the file
  and runs them alone before the pool opens. `runSuites` prints
  `test-boundary-gate: pool N worker(s) (source); serial-first: ...` as
  its first line, before any verdict.
- **Measured windows.** `src/factory/boxTiming.js` spawns a node child
  on a 250 ms timer three times and reports spawn latency, timer lateness
  and clock step; `derivedWindowMs(floor, box)` is `max(floor, 4 x slack)`
  rounded up to 100 ms. liveness-lease derives its unit (floor 2000 ms),
  launch-idle-watchdog its idle window (floor 800 ms); both print the
  measurement.
- **Budget-end deferral.** `idleWatchdog.js` `leaseExpiredAtBudgetEnd`:
  a lease clamped to the launcher's budget deadline that ran out is the
  budget ending, so the tick defers to the wall-clock arm (due within one
  spawn latency; the deferral is granted only while that arm is due
  inside one idle window) and the run ends as `wallclock` at
  `>= timeoutMs` -- the C4 race (a tick landing in the spawn-latency gap
  between the launcher's deadline and the supervisor's own) no window
  could widen away, and a relabel alone did not (drive #1, run 13).
- **Fixture-owned state.** The cross-provider fixture's hook launch pins
  `CLAUDE_CONFIG_DIR`, `WAI_PROVIDER_USAGE_ROOT` and
  `WAI_PROVIDER_FRAMEWORK_ROOT_OVERRIDE` to its temp roots and waits for
  the chain's final record (`chain_complete: true`) -- the old predicate
  accepted intermediate attempts (`status: complete, chain_complete:
  false`, dashscope/kimi for 2-8 ms each idle, longer under load).

## Under load (lug two-timing-suites-flake-under-box-load-and-refuse-real-pushes)

Slack is three probes at suite start and says nothing about the next
minute's contention: 260915 the two suites were green alone at load
0.35/cpu and red at 0.63/cpu and 1.6/cpu with the window at its floor.
So `boxTiming.js` reads the 1-minute load per cpu too: above 0.35/cpu (the
highest green; a fourth red landed at 0.40) the derived window widens in
proportion (x1.8 at 0.63, x4.57 at 1.6), above
2.0/cpu no window is honest and every load-sensitive check is a
`loadCheck` that SKIPs with the number printed. And `runSuites` re-runs a
red serial-first timing suite (one that imports boxTiming.js) once,
alone, after the pool closes: NEW RED only if both runs fail, the report
and both refusals quoting both outcomes with the load at each. Proof:
`conformance/fixtures/timing-suites-under-load/`.

## Proof

`conformance/fixtures/gate-pool-serial-suites/` -- A marker + report
line, B pins by grep and a live chain under a throwaway HOME, C the
measurement, the derivation and the forced C4 race, D the recorded
20-run full-pool drive (`GATE_POOL_SERIAL_SUITES_RUNS=20` regenerates it).
