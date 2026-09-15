# success-prediction

Operator directive, 2026-09-09: *"Each initiative and advisor should have a
prediction about what success looks like - that can be reviewed at the end
and if not achieved triggers deepr reviewal and remediation."*

Full build record, with the measured before-state and the worked examples'
derivations: `wheel-hub/docs/initiatives-and-advisors-carry-a-falsifiable-success-prediction.md`.

## Why

Every live advisor declared a `counter_metric` — which names *what* to
watch, never *what value* counts as success, and which was **never
measured**: its only consumer was interpolation into the advisor's own
prompt (`advisorAutopilot.js:83`). Initiatives had no entity at all, so
nowhere to put a prediction. Meanwhile the ROI extractor evaluates what
each run *did*, against no pre-registered claim — and an evaluation with
no prior bar can narrate any outcome as success afterward.

## The four properties

**1. Pre-registered and immutable.** `runtime/success-predictions.jsonl` is
append-only; the module has no update path. A change is
`supersedePrediction`, which appends a row pointing back at the original.
Superseding is refused once any verdict exists, and once `check_by` has
passed (the outcome exists whether or not anyone looked). Canon declares
the prediction but **is not the bar**: registration copies it into a
digested row, and verdicts are judged against that row — so editing canon
later cannot move the target, and `verifyRegistryIntegrity` reports the
divergence.

**2. Falsifiable.** Borrowed from `falsifiability-gate.yaml`: *"a check is
only certified falsifiable when its real exit code moved on a real mutated
mirror."* `certifyFalsifiable` runs the real `judgePrediction` over probes
swept across the metric's declared domain and requires the verdict to
actually move. Refusal classes: `unfalsifiable` (nothing yields `missed`),
`unsatisfiable` (nothing yields `achieved`), `no_reader`, and
`falsifiability_unproven` — the gate's own third verdict, refused rather
than passed.

**3. Third-party review.** The registrant's session and every recorded
executor session are refused, then the real `checkIndependence` runs. A
different session on an identical witness vector is still refused: one
instrument read twice. **A refusal writes nothing.**

**4. Three verdicts.** `achieved` / `missed` / `unevaluable`. A metric that
could not be read yields `unevaluable`, never a substituted zero, and is
never scored as either: `achieved_rate` divides by `achieved + missed`
alone and states the exclusion in its own output.

## Trivially-safe predictions, refused

`already_true_at_registration` (the baseline already satisfies it);
`near_vacuous_bound` (≥90% of the reachable domain satisfies it — a
declared judgement, and every refusal says so); and no measured baseline
without an explicit `first_baseline: true` admission.

## Reporting: a lug is a unit of work someone owes

After this wheel found 1,555 auto-filed lugs — 83% of its backlog — from a
check whose cause key carried a timestamp:

- N verdicts produce **one** section with counts. **No lug is ever filed to
  report a verdict.**
- Cause keys are `prediction-missed:<kind>:<subject>:<metric>` — no session
  id, run id, date or timestamp. Six cycles of the same miss is **one** lug.
- At most one lug per sweep, strongest first; the rest are reported.

## The miss branch

`missed` → `deeperReview` (the gap; whether the metric **moved at all**
from its baseline — a metric that did not move means the work and the
metric may not be connected, a different failure from falling short; prior
misses) → one lug through the real kernel verb, carrying that evidence.

Three consecutive `unevaluable` verdicts instead surface the subject's own
**definition** as the defect.

## Where it runs

`scripts/success-prediction.js` (report / status / verify / register /
register-from-canon / supersede / review / review-due), and
`buildSuccessPredictionSection` in `goalsReview.js` at session start.
