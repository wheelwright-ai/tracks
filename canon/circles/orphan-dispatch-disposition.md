# orphan-dispatch-disposition

Full build record, with the real sweep counts:
`wheel-hub/docs/orphaned-dispatch-rows-are-never-reconciled-against-disk-evidence.md`.
Code: `src/lugTracking/orphanDisposition.js`, `scripts/orphan-disposition.js`.

## Two claims, never one

`status: "orphaned"` is a fact about the **supervisor**: the row still
claimed `running` past the launcher's watchdog ceiling, so the process
that would have written a terminal status is presumed dead. Nothing ever
went back and asked about the **work**. Measured 2026-09-09: 33 of 226
rows (15%) orphaned, all with `outcome_detail: null`, at least one
provably finished (only its wrapper was killed). The record understated
what the wheel did, which misleads as much as overstating it.

This circle writes a second field, `work_verdict`, and never touches
`status`, so "the supervisor died" and "the work failed" stay separable.

## Three verdicts, and the third is mandatory

| verdict | means |
|---|---|
| `completed` | supervisor died, work proven finished |
| `partial` | supervisor died, real artifacts exist, completion bar unmet |
| `unknown` | supervisor died, nothing determinable |

`unknown` is never upgraded to make a count look better; it records why.
On the real wheel it is the majority verdict (31 of 33).

## The hard rule: no self-certification

"The lug reached `review`, so it's done" is exactly wrong: that field was
written by the session whose work is in question, the problem already
settled for chain disposition and prediction review. The lug's state is
read and recorded at `EVIDENCE_WEIGHT.self_asserted === 0`, so the claim
is visible and visibly not counted. What counts is evidence the reconciler
obtains itself:

| kind | weight | obtained by |
|---|---|---|
| `fixture_run` | 2 | the reconciler **runs** the declared test and reads its exit code |
| `circle_audit` | 1 | `auditCircles`' own verdict for the pointed circle |
| `artifact_present` | 1 | a pointed file really exists on disk |
| `self_asserted` | **0** | the lug's `state` |

`completed` needs a **passing** `fixture_run` plus one independent
corroborator. A fixture is the only evidence here that could have come
back negative; a bar nothing can fail is not a bar. A fixture that cannot
run to a verdict is `inconclusive`, and any non-passing fixture blocks
`completed`.

## Append-only

Original rows are never rewritten. A disposition is a new forward record
in `runtime/orphan-dispositions.jsonl` citing `resolves_dispatch_id`;
re-running appends again (a fixture may now pass), readers take
latest-wins. Kept out of `dispatch-registry.jsonl` so every existing
registry reader keeps reading exactly the rows it reads today.

## A work verdict is not a cost measurement

`completed` says the work finished, not what it cost -- the child may have
emitted no result event, which is often *why* it was orphaned.
`summarizeRunCost` takes dispositions as display only: they add
`work_verdict` and cannot reach `measured`, `tokens` or the total.

## Reported once, by cause, and files nothing

`buildOrphanDispositionSection` is the operator channel (pattern:
`schedulerFailureChannel.js`): once, with counts, keyed on a signature of
the numbers so it goes quiet until they move. Unsettled orphans group by
**cause**, never one line per row, and a cause key never carries a
dispatch id, lug name or timestamp -- a coordinate in the key makes every
occurrence its own cause. It files no lug: a verdict is information; a lug
is opened only for a real remediation owed.
