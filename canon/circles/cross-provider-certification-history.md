# cross-provider-certification-history

From wheel-hub's
`lugs/cross-provider-certification-runs-have-no-per-run-history.yaml`;
build record in that spoke's `docs/` page of the same name.

## The measured gap (wheel-hub, 2026-09-09 and 2026-09-12)

`writeCertificationRecord` overwrote
`runtime/cross-provider-certifications/<lug>.json` on every write. Run 1
of a real three-run sequence on one lug had to be replayed in a fixture
from reconstructed fragments -- its own citations were gone; every rejected
citation survived only as `checkFabrication`'s 120-char truncated reason.
Then dashscope FABRICATED on a lug and CONFIRMED after the evidence bundle
was repaired, and only the last record survived. The done gate now records
both stores' verdicts when they disagree; the per-run trail is what makes
that record auditable.

## The store

| File | What it is |
| --- | --- |
| `<lug>.runs.jsonl` | append-only, one entry per write, whole record + `seq`, `run`, `recorded_at` |
| `<lug>.json` | the current view: newest entry, latest-wins, plus `history` |

An entry is a **run** when it carries a verdict (`status: complete`);
`required` and `running` markers are trail. Every attempt of a fallback
chain is its own run (`chain_complete: false` until the winner). A
re-write of the same outcome -- the verb's `superseded_by_proofer_pass`
spread -- `annotates_run` instead of counting again.

`history` on the view: `runs_file`, `policy`, `max_entries`, `entries`,
`runs`, `latest_seq`, `latest_run`, `pruned_entries`, `unreadable_lines`,
`trail[]` (run, provider, model, verdict, citations_checked, weakest_tier,
finished_at), `fabrication_followed_by_pass`.

## Migration, never deletion

A pre-existing single record is entry 1 (run 1 if it has a verdict),
`migrated_from_single_record: true` -- lazily on the next write, or by
`scripts/certification-history.js --migrate`. A view hand-written to
`<lug>.json` after history exists is captured the same way before the next
append. Readers see one shape either way: `readCertificationHistory`
returns a not-yet-migrated record as a virtual entry 1.

## Retention, stated

Newest `HISTORY_MAX_ENTRIES` (60) entries per lug; older pruned
oldest-first by atomic rewrite. `seq` and `run` never reset, so
`pruned_entries = first retained seq - 1`. Sized from the live store: a
four-candidate chain writes ~9 entries per invocation at 10-24 KB, so 60 is
~6 invocations, at most ~1.5 MB per lug.

## Reading it

```
node scripts/certification-history.js <lug>            the trail
node scripts/certification-history.js <lug> --run=1    run 1, whole
node scripts/certification-history.js --summary        every lug
```

`summarizeExternalChain` counts attempts from the history (deduplicated by
provider + `started_at` against `attempts[]`) and the session-start section
says, once and with a count, how many lugs had a FABRICATED verdict later
followed by a real PASS.

## Not weakened

`fabricationCheck.js` and the tiered match are untouched. The gate's
current-verdict lookup reads the same keys it always did.
