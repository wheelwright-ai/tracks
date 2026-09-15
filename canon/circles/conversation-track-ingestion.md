# conversation-track-ingestion

`lugs/conversation-track-ingestion-tool-for-goals-and-stranded-ideas.yaml`
(filed 260909 from a verbatim operator directive). Implementation:
`scripts/ingest-conversations.js` and `scripts/ingest/`. Design notes and the
real run report: `docs/conversation-track-ingestion.md`.

## Why this exists

Operator directive, verbatim: *"a tool that can process conversations/track
exports from any source and build a unified and valuable perspective on my
goals and needs in order to extract the very most value from previously
stranded ideas."* Two kinds of value sit in records this build already writes
and never reads back: **goals and preferences** (what `tastegraph/` exists to
hold) and **stranded ideas** (raised, never built or declined -- by
definition untracked, or they would not be stranded).

## What it does

Reads conversation-shaped records from any registered source adapter,
normalizes them, and runs two extractors over the normalized form:

- `recurring_stated_rule` → a tastegraph **proposal** (never a direct write).
- `unclaimed_proposal` and `stalled_work_item` → a **lug**, or a report line
  when filing one would duplicate an existing lug.

One source is registered today: `tracks`, this repo's own
`runtime/tracks/*.track.json` and `*.canary.json`. It was chosen first
because it needs nothing to arrive — every real session this build has ever
run already wrote one — so the mechanism could be proven before any export
exists.

## The contract is the load-bearing part

`scripts/ingest/sourceAdapter.js` declares the normalized shapes and validates
every record at the adapter's own boundary, not three layers downstream.
`extractors.js` may not read a native format, name a source, or branch on
`conversation.source`. Not self-certified:
`lug:claude-ai-export-adapter-for-conversation-ingestion` is the second
adapter, and its acceptance requires the extractors run over claude.ai
conversations with no source-specific branching -- and that a genuinely
needed branch be recorded as a finding about this contract, not patched
around.

## Honesty properties, enforced rather than described

- **Citations are openable** -- file plus pointer
  (`runtime/tracks/<id>.track.json#decisions[18].text`); an adapter omitting
  one is rejected.
- **Quotes are real quotes** -- every segment declares `text_is_verbatim`;
  synthesized prose can be cited as evidence, never presented as speech.
- **A missing reason stays missing** -- the reason for not proceeding is
  quoted only when the source states one, else "reason not recoverable".
- **Thin is reported as thin** -- every filter prints its count, so a
  zero-finding run explains itself.

## Two heuristics, both calibrated against real data

Both extractors are heuristics, per this build's own
`heuristics.measure_their_error_rate` taste (a stage, never ground truth,
error rate measured and written down). Two real false-positive classes found
on the first run, named in code beside the checks that catch them:

- **Dispatch fan-out.** Counting recurrence in distinct sessions produced 9
  findings, 8 of which had every capture within one day — one prompt
  dispatched to several sub-sessions. Recurrence is now distinct UTC days.
- **A marker inside a name.** `proposal` matched 384 rows only because a lug
  they mention is *called* `…-proposal-mechanism`. The marker must now
  survive having quoted spans and `lug:<name>` tokens stripped.

## Where it can drift

- `capture-direction` feeds the goal extractor; its window size and marker
  list set that extractor's input quality. If it changes, re-measure the
  truncated-capture figure in the design notes.
- A second adapter is the real test of the contract. A branch appearing in
  `extractors.js` is the drift signal; `failure_routing` names the parent lug.
- The staleness threshold, not the mechanism, currently binds
  `stalled_work_item`: only 4 of 421 work items cleared 7 days in a
  two-week-old repo. Expect that to change as the corpus ages.

## Proof

`conformance/fixtures/conversation-track-ingestion/` -- contract rejection
paths against malformed adapters, the real tracks adapter against this
repo's real `runtime/tracks/`, source-agnosticism against a synthetic second
adapter, the operator-stated-key collision refusal, and a real assertion
that a dry run writes nothing.
