# cross-store-finding-coalescing

A systemic finding costs ONE record per cause in every store, not one per
occurrence in any of them. Full build record and measured before/after
sizes: wheel-hub `docs/cross-store-check-floods-every-store-not-just-lugs.md`.

## Why this exists (measured, 2026-09-10, wheel-hub)

One mis-keyed writer wrote ~180 MB across all three durable stores:

| store | before | share |
|---|---|---|
| `ledger/ledger.jsonl` | 105.3 MB | 79,050 of 92,869 rows (85.1%) |
| live session track | 82.1 MB | `decisions` 74.1 MB, 75,968 of 76,673 (99.1%) |
| `lugs/` | 1,555 generated files | 83% of the backlog |

All of it for **57 real causes**. 3,262 distinct coordinates, each
re-written 24.2x on average. The cause key was
`session|lug|from|to|timestamp|check` -- a timestamp in a key makes every
occurrence unique by construction.

## The rule

1. **Key on a cause.** `causeKeyOf` → `check:<check>|session:<id>`. No
   timestamp, no lug name, no state. Occurrence detail belongs in the
   record's count and sample, never in the key.
2. **Carry the evidence forward.** Count, distinct-subject count, time
   span, a bounded sample of real coordinates, and what is still
   undiagnosed. Coalescing that loses the cause has failed.
3. **Bound each store independently** (`src/store/storeBounds.js`):
   `LEDGER_ROWS_PER_SOURCE_REF_PER_DAY`, `TRACK_DECISIONS_MAX_ENTRIES` /
   `_MAX_BYTES`, `AUTO_FILED_LUGS_PER_CAUSE_FAMILY`. Per writer, never
   global.
4. **Refuse, never trim.** The ledger declines a new append. The track
   bounds a projection it rebuilds from the ledger every Stop and discloses
   the omission in `decisions_bound`, naming where the full record lives.
5. **Disclose once, then count.** First refusal per scope writes a ledger
   row and a stderr line; the rest are counted in
   `runtime/store-bound-state.json`.
6. **Report, don't file.** `buildCrossStoreFindingSection` in the goals
   review. A lug is work owed; a finding is information.

## Adding a new P0 writer

Set `p0_cause_key` on the row -- a structured field, which `deriveP0Cause`
prefers over any regex. If you cannot state a cause key without a
coordinate in it, you do not yet know what your cause is.

## Reading a bound's output

- `decisions_bound` absent → the section is complete.
- `decisions_bound` present → it names cap, available, retained, omitted,
  both windows, and that every row is still in `ledger/ledger.jsonl`.
- `runtime/cross-store-cause-state.json` → per cause, the last recorded
  count. A cause at an unchanged count is deliberately not re-stated.

## What this circle does NOT do

It does not diagnose why track and event log disagree at all. That is the
real bug under the noise, still owed, and named in every coalesced report
so it cannot be mistaken for fixed. Coalescing made it legible; it did not
solve it.
