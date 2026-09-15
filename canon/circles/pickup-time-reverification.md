# pickup-time-reverification

## Why this exists

Operator principle, verbatim: "as work is picked up it is reverified to
ensure its still needed effort." That is how a dispositioned chain
propagates: **lazily, at pickup**, never by chasing or killing work in
flight (`docs/settled-decisions-lug-redesign-and-spec-vocabulary.md` Part
2, "Deprecation is lazy, not eager"). It also catches what eager
cancellation misses: work still valid but no longer worth doing. The
independent review (gemini, 2026-09-09) found the principle settled and
the mechanism unspecified. This circle is the mechanism.

## Entry point

`src/lugTracking/pickupReverification.js`, wired into the two real pickup
paths and nothing else: `lugVerb.js` on a real transition into
`in_progress` (re-entering is not a pickup), and `dispatchMechanism.js`
`queueDispatchLocked`, after the idempotency collapse and before anything
is queued. `src/conductor/readyWork.js` reads the recorded verdict so a
stopped lug leaves the ready queue visibly.

## The three criteria

Each returns `needed`, `not_needed` or `unknown`; only `not_needed` stops
anything.

1. **Chain disposition.** The lug's `chain_id` against
   `runtime/chain-dispositions/<chain_id>.json`, read through
   `src/advisor/chainDisposition.js`'s own reader, never a parallel store.
   `deprecated` stops the pickup -- Part 2 says of it alone "do not build
   on this". `closed` and `seek_refresh` have no settled effect on a
   specific pickup, so they report `unknown` with the disposition named.
2. **Dependency states.** From the two settled edge kinds only: lineage
   `derived_from`, and `relates_to` with `relation: dependency`. A
   dependency whose chain is deprecated stops the pickup, one hop. One
   that does not resolve is `unknown`, never a stop.
3. **Premise.** Deliberately not an oracle: it asks only whether real
   state *contradicts* the premise. Contradictions: already `done`;
   `superseded_by` / `duplicate_of` names a lug that resolves and is
   `done`. A pointer that no longer resolves is `unknown`.

## Read-only, and why

This circle reads chain dispositions and never writes them; the writer is
`chainDisposition.js`, which refuses anything but a real third-party
witness. This reader enforces what it can: a record with no
`witness.session` -- only a hand-written file can lack one -- is refused
and surfaced as an integrity finding.

## On "no longer needed"

Never silently dropped, never silently proceeding: the verb refuses and
returns the reason; the verdict is written onto the lug as
`pickup_reverification` (with `recordChecksum`, so the integrity backstop
does not revert it); a ledger row records it; on the dispatch path a
`refused` registry row carries it and nothing is queued; `readyWork.js`
drops the lug with the reason attached. On `unknown` the work proceeds,
and both the row and the lug block say it did so on an unanswerable
question. The lug block is compact (under 120 tokens; one capped line per
check, full reasoning on the ledger row it names by id).

## Laziness is structural

The module exports nothing that mutates a dispatch row and never names
the registry. Conformance section D deprecates a chain while a dispatch
for it runs, proves the run finishes untouched, then proves the next
pickup is stopped. One asymmetry (section H): reopening a `done` lug
through the verb is allowed -- someone asked knowingly; a dispatch to a
`done` lug is refused -- nobody decided that.

## Cost

Measured, every verdict carrying its own `cost_ms`: **0.025 ms per
pickup** across all 790 real lugs; ~3 ms on the worst shape (25
dependencies against a 201-chain store), dominated by reading dependency
files, not dispositions. Each chain is read at most once per
re-verification, scoped to that call. Not a tax on dispatch.

## Conformance

`conformance/fixtures/pickup-time-reverification/pickup-time-reverification.conformance.test.js`,
81 checks: both directions at both paths, no-oracle, laziness against a
running dispatch, ready-queue exit, self-certification refusal, cost.
