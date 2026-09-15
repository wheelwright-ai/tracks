# readiness-certification-sweep

Build record, with the real sweep counts:
`wheel-hub/docs/readiness-certification-sweep-of-review-state-backlog.md`.
Ready+passed enumeration and the shared promote path:
`wheel-hub/docs/readiness-sweep-cannot-see-a-lug-the-proofer-already-passed.md`.
Code: `src/conductor/readinessSweep.js`, `src/conductor/donePromotion.js`,
`scripts/readiness-sweep.js`. Fixtures: both files under
`conformance/fixtures/readiness-certification-sweep/`.

## Why a circle, not another /tmp script

Three sweeps of the review backlog (260908, 260909, 260911) were each
written from scratch under `/tmp` and converged on the same shape: read
the gate with the harness's own functions, re-run the lug's own fixture,
ask the verb, record what happened, stop on budget. None of that survived
its session. This circle is that shape on disk, so the next sweep is a
command, and its record has one schema every reader already knows.

## One lug, one row, always a reason

| step | reads | refuses with |
|---|---|---|
| gate | `checkCrossProviderGateForDone` (both stores) | the gate's own reasons, quoted |
| fixture | `findReferencingTest` marker + `tests:` entries, both repos, **executed** | `fixture red` / `fixture inconclusive` / `no fixture to re-run` |
| verb | `promoteLugToDone` (donePromotion.js -- the SAME body the initiative drive calls) | the verb's reasons, verbatim, and `refused_by` naming the gate |

`outcome_at_proofer` is `certified` only when the gate acted on a real
CONFIRMED/PLAUSIBLE record or a Proofer PASS; otherwise `pending`. The
sweep never claims a certification it did not read.

## Three certification policies, all disclosed on the row

| `--certify` | does | costs |
|---|---|---|
| `none` (default) | records the closed gate, moves on | nothing |
| `request` | spawns the detached certifier the initiative drive uses; gate re-read next sweep | one provider chain, later |
| `run` | runs `scripts/cross-provider-certify.js` synchronously, re-reads the gate now | one provider chain, now, sequential |

`runProofer` without `certifyOnly` is never called: `proofer.js` moves a
PASSing lug review -> ready, which re-queues finished work.

## Who is a candidate, and in what order

Every lug at `review`, and every lug at `ready` with `readiness: passed`
-- the Proofer's own post-PASS shape, which a review-only sweep lost sight
of. `ready` + `stubbed` is unbuilt work, never a candidate. A held ready
lug is `left_at_ready`, never reported as left at review.

Critical before high; within a tier, the lug that unblocks the most other
lugs first (lineage children through the shared normalizer, plus
`pointers:` entries naming it); then by name. Medium/low are out by
default: `--priorities=critical,high,medium` or `all` widens, and the
run summary echoes the list it used.

## The budget is a hard stop

Checked before every lug. On stop: `stopped_reason: time_budget`,
`not_reached` names every lug not reached, none of them counted, CLI exit
3. The tally section is re-rendered after every lug, so a kill mid-sweep
loses at most the lug in flight.

## What it writes

`runtime/readiness-sweep.jsonl` (one row per lug, one run summary),
the `--tally-doc` section between the TALLY markers, one ledger row per
run. Nothing else: lugs move only through the verb, certification records
are written only by the certifier. `--dry-run` writes nothing at all.
