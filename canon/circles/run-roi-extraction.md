# run-roi-extraction

Operator directive, 2026-09-09: *"Each autopilot run should end with an ROI
extractor that evaluates the reults and appends its kpi's and determines if
remediations are needed... gives it pause to steer things more optimally."*

## Why it was needed

The steering loop had been *declared* since 260906 and did not turn.
Measured on wheel-hub 2026-09-09: **926 waves, one ever launched; 276
opened and never closed** (all from `heartbeat.js`'s `finish()`, which
opened with no close downstream — one cause); **zero** closed waves
carrying a dispatch, so `outcome.measured` was false for the whole history.

## What it does

`src/conductor/roiExtraction.js`, at the one point every run passes through
on its way out (`finishAutopilotRun` — launch, decline and abnormal-end
paths alike):

- **Evaluates the run** into a named KPI set (decision, driving signal,
  duration, dispatch/judged/collapsed/unrecorded counts, granted budget,
  cost tokens, cost coverage, lugs advanced/done, tokens per lug). Each
  names its source.
- **Appends them to the run's own wave record** as `extraction`, a declared
  entry in `WAVE_RECORD_DATA_POINTS`. One stream, one shape.
- **Decides whether a remediation is owed**, always explicitly.
- **Steers the next wave** via a per-spoke `extraction_factor` in
  `decideWave`'s ranking.

## Honesty

No rate card, no imputed denominator, no zero substitution. A KPI is
measured with a real figure, or `measured: false` with `value: null` and a
reason — enforced in `kpi()` itself, so a call site cannot violate it.
`cost_measurement_coverage` keeps the wheel's real measured-cost gap
visible rather than averaged away.

## It cannot self-certify

No parameter accepts a verdict. Every KPI is backed by an artifact written
by a *different* process than the run: the dispatch registry, turn markers
(each child's Stop hook), ledger twins, `lug_transition` events (the kernel
verb, in the child). The run's own `ok` claim is cross-checked against its
ledger twin; a claim with no twin becomes `unrecorded_dispatch_count`.

## It cannot flood the backlog

**A lug is a unit of work someone owes.** This wheel had just found 1,555
auto-filed lugs from a check keyed on a per-event coordinate that could
never dedup. So, following
`schedulerFailureChannel.js`: every cause key names a **cause**; a cause
already lugged is reported, not re-filed; **at most one lug per run**,
strongest first, the rest reported; rules need sustained evidence, never one
occurrence; a fixed cause leaves the channel on its own; the channel is
silent when nothing is owed.

## What it steers, and cannot

A wave that dispatches and yields nothing judgeable scores 0 ok / 0 failed,
so the existing multiplier's total is zero and it stays a neutral 1.00
forever. The extraction sees that and damps the spoke. Two limits: a
spoke's factor is at most 1.00 (no run boosts itself), and it damps *which*
spoke, never *whether* to launch — floored, ranking-weight only.

## Waves never closed

Rule: a wave opened more than one five-hour window ago with no `closed` row
is **unrecoverable** — its results existed only in an exited process. It is
closed explicitly (`outcome.measured: false`, `reconciled: true`, reason
in words), never guessed, never silent, and attributes no provider calls by
time. The sweep runs on the wheel clock (`open_wave_reconciliation`) or by
hand (`scripts/reconcile-open-waves.js`). A real sweep leaves
`runtime/open-wave-reconciliation.json`; the `wave-never-closed` rule adds
its count to the tail's, so a leak older than the tail is counted.

## Cost

Measured on every run and carried on the record: **16–48 ms** live. The
per-run read is bounded to a 2 MB / 400-row tail and says so; only the
sweep reads the whole file. Build record:
`wheel-hub/docs/autopilot-run-ends-with-an-roi-extractor-that-steers-the-next-wave.md`.
