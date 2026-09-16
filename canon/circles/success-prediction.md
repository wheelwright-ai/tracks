# success-prediction

Operator directive, 2026-09-09: *"Each initiative and advisor should have a
prediction about what success looks like - that can be reviewed at the end
and if not achieved triggers deepr reviewal and remediation."*

Build record, measured before-state, worked examples:
`wheel-hub/docs/initiatives-and-advisors-carry-a-falsifiable-success-prediction.md`.

## Why

Every live advisor declared a `counter_metric` — *what* to watch, never
*what value* counts as success, and **never measured** (its only consumer
was prompt interpolation, `advisorAutopilot.js:83`). Initiatives had no
entity at all. The ROI extractor evaluated what each run *did* against no
pre-registered claim — and with no prior bar, any outcome can be narrated
as success afterward.

## The four properties

**1. Pre-registered and immutable.** `runtime/success-predictions.jsonl` is
append-only; there is no update path. A change is `supersedePrediction`,
a row pointing back at the original — refused once any verdict exists or
`check_by` has passed (the outcome exists whether or not anyone looked).
Canon declares the prediction but **is not the bar**: registration copies
it into a digested row and verdicts are judged against that, so a later
canon edit cannot move the target; `verifyRegistryIntegrity` reports it.

**2. Falsifiable.** `falsifiability-gate.yaml`'s standard: *"certified
only when its real exit code moved on a real mutated mirror."*
`certifyFalsifiable` runs the real `judgePrediction` over probes swept
across the metric's declared domain and requires the verdict to move.
Refusals: `unfalsifiable` (nothing yields `missed`), `unsatisfiable`
(nothing yields `achieved`), `no_reader`, `falsifiability_unproven` — the
gate's own third verdict, refused rather than passed.

**3. Third-party review.** The registrant's and every recorded executor
session are refused, then the real `checkIndependence` runs; a different
session on an identical witness vector is one instrument read twice, and
refused. **A refusal writes nothing.**

**4. Three verdicts.** `achieved` / `missed` / `unevaluable`. An unreadable
metric yields `unevaluable`, never a substituted zero, and is never scored:
`achieved_rate` divides by `achieved + missed` alone and says so.

## Trivially-safe predictions, refused

`already_true_at_registration` (the baseline already satisfies it);
`near_vacuous_bound` (≥90% of the reachable domain satisfies it — a
declared judgement, and every refusal says so); and no measured baseline
without an explicit `first_baseline: true` admission.

## Reporting: a lug is a unit of work someone owes

After 1,555 auto-filed lugs — 83% of the backlog — from a cause key that
carried a timestamp:

- N verdicts produce **one** section with counts. **No lug is ever filed to
  report a verdict.**
- Cause keys are `prediction-missed:<kind>:<subject>:<metric>` — no session
  id, run id, date or timestamp. Six cycles of the same miss is **one** lug.
- At most one lug per sweep, strongest first; the rest are reported.

## The miss branch

`missed` → `deeperReview` (the gap; whether the metric **moved at all** —
a metric that did not move means the work and the metric may not be
connected, a different failure from falling short; prior misses) → one
lug through the real kernel verb, carrying that evidence.

Three consecutive `unevaluable` verdicts instead surface the subject's own
**definition** as the defect.

## Where it runs

`scripts/success-prediction.js` (report / status / verify / register /
register-from-canon / supersede / review / review-due);
`buildSuccessPredictionSection` at session start; the wheel-clock job
`success_prediction_review`, grading what is due with the **calling
session** as reviewer (no session: nothing graded, left due; the
registrant's own session: refused — a clock removes the registrant's
discretion over *when* to grade, the distance the rule buys); and every
autopilot run's ROI extraction, whose `prediction-missed` rule owes a
miss into the same single-lug queue, on the same cause key.
