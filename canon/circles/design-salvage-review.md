# design-salvage-review

## Why this exists

The wheelwright handoff spec asks for a periodic pass that keeps work
from falling onto the cutting floor. The reconciliation
(`docs/wheelwright-handoff-vocabulary-reconciliation.md`, Part 2) cleared
the **record type** as genuinely new while stating plainly that the
detectors are not: *"The record type is new; the detectors largely are
not."* Seven of the eight salvage signals already had a real detector.

So this circle's job is to **drive** them and record one honest verdict —
not to grow a second copy of machinery that already works.

## Entry point

`src/otto/designSalvageReview.js`. Typed by
`schemas/design-salvage-review.schema.json`; reviews land in
`runtime/design-salvage-reviews.jsonl`. `buildDesignSalvageReview()`
reads only, so a pass can be inspected before it is committed;
`runDesignSalvageReview()` appends.

## The signals and their real detectors

| Signal | Real detector |
|---|---|
| repeated unresolved items | `src/ledger/references.js#agedUnsatisfiedReferences` |
| implementation missing design linkage | `src/cartographer/index.js` (`test_to_lug`) |
| designs lacking verification | `runtime/coverage-ledger.jsonl` |
| dormant work, dependencies arrived | coverage ledger joined against declared state |
| unresolved contradictions / silent deferrals | `src/lugTracking/turnGapScan.js#readOpenFindings` |
| structural drift | `src/cartographer/builtinScan.js#scanCircleMap` |
| high-value relationships with no topic or owner | `src/ideaGraph/ideaGraphStore.js` |

## The three that do not run, and why

- **stale evidence in the capability record** — the real detector is
  kb-curator's standing lens, a judgment a live model run makes against
  `kb/capabilities-graph.md`. Naming it beats writing a weaker string
  check here.
- **active unlinked ideas** — blocked on **D2**. The real store is a flat
  append-only table with no edges; "unlinked" cannot be computed without
  first deciding where an idea graph lives.
- **rejected paths worth extracting** — blocked on **D6**. Two real homes
  for a design record already exist and there is no single place to read
  rejected paths from.

Each is recorded with `available: false`, a real reason, a null count and
(where it applies) the decision id. **A skipped signal must never read as
a clean signal** — the schema refuses an unavailable detector that
reports zero findings.

## The revival guard

The spec's own rule: *"Do not revive items only because they are old or
connected. Require changed evidence, dependency, context, or priority."*
`change_kind` is a closed enum of exactly those four. There is no `age`
member, so an age-only proposal cannot be expressed, let alone accepted.
Every candidate must cite evidence.

## Conformance

`conformance/fixtures/design-salvage-review/design-salvage-review.conformance.test.js`
— runs the pass over the real wheel-hub, checks each detector ref exists
on disk, and proves the refusals.
