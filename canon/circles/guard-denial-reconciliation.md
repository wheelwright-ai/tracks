# guard-denial-reconciliation

lugs/guard-circles-denials-untracked-and-never-reconciled.yaml, half 2.

## Why this exists

The wheel has 4 real guard-class hook circles (bash-lug-guard,
bash-destructive-command-guard, agent-target-scope-guard,
agent-tool-scope-guard). Each one, on a real denial, writes a real ledger
row (`row_kind: decision`, `attribution` naming the guard, `source_type:
hook`, text starting `REFUSED --`). Found live 2026-09-05: nothing ever
read those rows back. No false-positive-shaped computation, no proposal --
unlike `reconcile-ledger` (canon/circles/reconcile-ledger.yaml), whose
counter-metric pattern this circle reuses rather than reinventing.

## What it does

Every run (src/ledger/reconcileGuardDenials.js, `runReconcileGuardDenials`):

1. Reads every real ledger row.
2. For each of the 4 guards, computes a **repeat-denial rate**: of that
   guard's own real denial rows that carry a `session_id`, what fraction
   belong to a session the same guard had already denied at least once
   before. Rows with no `session_id` can't be attributed to a repeat and
   are excluded from both numerator and denominator -- the same
   "unreviewed rows don't belong in the denominator" discipline
   `reconcile-ledger`'s own counter-metrics already use.
3. Writes one additive counter-metric row per guard, every run
   (`source_type: counter_metric`, `source_ref` names the metric).
4. When a guard's repeat-denial rate is >= 0.5 across >= 3 real denials,
   writes one additive proposal row for that guard
   (`source_type: proposal`) recommending a human/Otto review whether its
   pattern is over-triggering a real workflow, or its sanctioned path
   isn't discoverable.

## What it does not do

It never mutates an existing ledger row -- counter-metric and proposal
rows are additive only, same invariant `reconcile-ledger` carries. It
never changes any guard's own denial logic or patterns: this circle is
entirely about giving each guard's real denial a durable trace and a real
feedback loop, never about loosening what it blocks. A proposal is a
recommendation for a human/Otto to act on, not a silent auto-relaxation.

## Why repeat-denial rate, not a "succeeded via the sanctioned path after"
## heuristic

The lug that opened this circle floated a richer heuristic: "denials
later followed by the same operator/session succeeding at an equivalent
action through the sanctioned path." That needs a second, correlated
signal -- what command actually ran next and whether it was the
guard-approved equivalent -- that isn't captured anywhere queryable today
(the denial row records the refusal, not what followed it). Repeat-denial
rate is a real computation over real, already-captured rows: simpler,
defensible, and disclosed as a proxy rather than ground truth. A future
lug that wants the richer signal has a real row shape to correlate
against once one exists.

## Wiring

Fires on the `guard_denial_reconciliation` wheel_clock job
(canon/otto.advisor.yaml), cadence 6 ticks -- a repeat-denial pattern
accumulates across sessions, not within one, so it's as slow-forming as
roster drift and cross-store reconciliation.
