# cross-provider-verification

From wheel-hub's
`lugs/cross-provider-verification-for-high-priority-proof-required-lugs.yaml`;
long-form build record in that spoke's `docs/` page of the same name.

`callProvider` and the four-axis independence check were real and
working, and nothing invoked them: work could reach `review` carrying
`proof_required: true` and never get a second opinion. Why non-Claude
providers exist at all, operator's words: a low-trust harness -- *"ensure
we don't fall for sweet words"*.

## What fires, and when

| Moment | Who | What |
| --- | --- | --- |
| enters `review` | `lug-kernel-verb` | writes a `required` record + ledger row, sync, no call |
| enters `review` | PostToolUse hook | spawns `scripts/cross-provider-certify.js` detached |
| promoted to `done` | `lug-kernel-verb` | reads this record AND the Proofer's own row -- see `done-gate-two-store-certification` |

Transitions, not states: `review -> review` raises nothing; anything
already `done` before this gate existed stays hand-editable.

## Scope

`priority: high|critical` **and** `proof_required: true`. Operator ruling,
~65% confidence, real per-call cost named. Low-priority/haiku-tier work
stays on the Claude subscription path.

## Choosing the certifier

`selectIndependentCandidates` walks the Proofer advisor's
`cross_provider_candidates` (gemini, dashscope, kimi, deepseek), returning
every independent one in declared order. A candidate matching the
author's own recorded provider is rejected first.

## Verdicts

CONFIRMED (independent PASS, verbatim citations) and PLAUSIBLE (same PASS,
author stated no provider) open the gate. FAILED, FABRICATED
(`fabricationCheck.js`, citations not verbatim), REFUSED
(self-attestation/no candidate passed), BLOCKED (network/401/timeout/
incomplete evidence) all block, reason named; all but FAILED yield to a
real Proofer PASS (`done-gate-two-store-certification`).

## Exhausting the candidate list

Used to refuse fallback outright ("one selection, one call"). Real
counter-example, 2026-09-09: the first readiness-certification sweep saw
`dashscope` (first in declared order) return 8 FABRICATED verdicts in a
row and BLOCK a 9th -- nothing tried the rest, 0 of 87 qualifying lugs got
certified, not because the work was bad but because the head of the list
was.

| Outcome | Next |
| --- | --- |
| CONFIRMED/PLAUSIBLE | chain stops -- certified |
| FAILED | chain stops -- a real negative is an answer, not something to shop past |
| FABRICATED | next candidate (still rejected, always) |
| BLOCKED, candidate-attributable | next candidate |
| BLOCKED, instance-attributable (no call made) | chain stops -- identical for every candidate |
| REFUSED | chain stops -- independence pre-check already settled it |

Not a coin flip: never silent (each attempt gets its own `attempts[]`
entry/ledger row/event); fabrication check untouched (fabricated PASSes
never add to one real one); on exhaustion the headline is chosen not
inherited (FABRICATED outranks BLOCKED, else first candidate stands).
`callProvider` never silently falls back on its own -- the retry decision
is one layer up, recorded. `--provider=<name>` is still one call.

Proved by `conformance/fixtures/cross-provider-fallback/`. Re-ordering
`cross_provider_candidates` is deliberately out of scope.

## Detached, with a timestamp

A real call runs to the Proofer's 120s timeout, too long to hold a tool
call open on a review transition. The record is written `running`
with `started_at` before the call; a `running` record older than 15
minutes reads as a named block, never an absence.

## What it does not touch

`callProvider`'s contract, adapter shapes, axis-checking logic. A
cross-provider PASS never flips `readiness`, which stays claude
fresh-context per standing ledger rule 260829-FBL-026.

## Running it

`node scripts/cross-provider-certify.js <lug> [--provider=<name>]`, or
`--status` for a no-call report. Records land in
`runtime/cross-provider-certifications/<name>.json`; exit 0 only when the
verdict really opens the done gate.
