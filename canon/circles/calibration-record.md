# calibration-record

## Why this exists

`tastegraph/master.yaml` already states the rule this circle serves:
*"A heuristic is acceptable as a stage, not as ground truth, and its
false-positive rate must be measured and written down, not assumed."*
Until now nothing wrote one down. This circle produces the record.

It is Phase 1 of the wheelwright implementation handoff spec, cleared as
genuinely new and unblocked by
`docs/wheelwright-handoff-vocabulary-reconciliation.md` Part 6.

## Entry point

`src/observability/calibrationRecord.js`. Typed by
`schemas/calibration-record.schema.json`; records land in
`runtime/calibration-records.jsonl`.

## What it reads

Only the real evidence streams the reconciliation's Part 2 names, listed
in code as `REAL_EVIDENCE_STREAMS`:

- `runtime/autonomy-outcomes.jsonl`
- `runtime/coverage-ledger.jsonl`
- `runtime/vitals.jsonl`
- `runtime/roi-rollup-history.jsonl`
- `runtime/wave-records.jsonl`
- `runtime/disclosed-gap-findings.jsonl`

Citing anything else throws. A record holds counts, a window, a selector
and a pointer at the stream — never a copy of a row. The schema enforces
that with a top-level `not` on `rows`/`source_rows`/`records`.

## Adapters that exist today

- `calibrateDisclosedGapHeuristic(instanceRoot)` — the disclosed-gap
  phrase heuristic (`src/lugTracking/turnGapScan.js`) against its own
  findings stream. The operator's own adjudication is already on each
  row: `filed` = true positive (a real lug came of it), `dismissed` =
  false positive, `open` = undetermined and excluded.
- `calibrateAutonomyCell(instanceRoot, cell)` — one autonomy cell against
  `runtime/autonomy-outcomes.jsonl`, where `requiredRework` is the miss.

## The honest-unmeasured path

No adjudicated observations means `measured: false`, a null rate and a
stated `unmeasured_reason`. This is not an error path; it is the point.
The same posture `navigator-cut.json` takes with
`quota_signal.disclosure` ("explicitly unmeasured, NOT zero
consumption").

Confidence tracks the sample, not the author's mood: a handful of rows
reports a low number and names the weakness in `unknowns`.

## What it is not

It is **not** the TasteGraph. Whether `tastegraph/master.yaml` may hold
inferred, confidence-scored entries is open operator decision **D8**, and
ruling 6 plus the master file's own admission rule currently forbid them.
Measurement gets its own home here so that measuring a heuristic does not
require answering D8 first. Do not merge the two stores before it is.

## Conformance

`conformance/fixtures/calibration-record/calibration-record.conformance.test.js`
— computes real readings from the real wheel-hub streams, and proves the
refusals (duplicated rows, invented stream, unmeasured-with-a-rate).
