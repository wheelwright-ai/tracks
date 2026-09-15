# tastegraph-injection

lug tastegraph-is-merged-at-wakeup-and-injected-into-no-session (260912).
Measured: `mergeAtWakeup` ran at every SessionStart and returned the
merged list to a caller that discarded it. Two audits read the merge;
no session ever saw a taste. Rule 12's own comment named "tastegraph"
as aspirational wakeup canon -- it was.

## What it is

Three arms, one module (`src/tastegraph/injection.js`), one audit
(`src/tastegraph/communicationAudit.js`):

1. **Wakeup block.** `buildFullCheckpointInjection` now composes a
   `TASTES (N merged, version ...)` block: one `key: value` line per
   merged taste, values cut at `TASTE_VALUE_CHARS` with the overflow
   stated, the whole block cut at `TASTE_BLOCK_CHARS` with the unshown
   count stated. Because it is composed inside the same function rule
   12 measures, injection and cap measure one text. The cap was not
   raised (worktree total 1160 -> 1720 of 2300).
2. **Next-turn update.** `refreshTasteGraph` hashes master + overlay
   into a version; a new version writes ONE `taste-update` ledger row
   naming the changed keys and appends to a short version history.
   The spoke clock's `tastegraph_refresh` job (`canon/ozi.advisor.yaml`,
   runner `refreshTasteGraph`) and this circle's own hook both call it;
   idempotence per version keeps the ledger at one row. The hook then
   compares the instance version with what THIS session last saw
   (`runtime/taste-update-seen/<session>.json`, written at wakeup) and
   injects `TASTE UPDATED: <keys>` with the new values, once per session.
3. **Taste miss.** `footerAuditHook` (Stop) holds the closed response
   against the merged `communication.*` tastes that have a mechanical
   checker: opening three real lines outcome-shaped, closing three name
   the operator ask (footer line excluded, replies under six real lines
   skipped). A miss is a `taste-miss` row shaped like a footer miss,
   flagged `heuristic: true`; the goals review counts them by key and
   session (`TASTE MISSES:`).

## Known, accepted gaps

The checkers are regexes: a report can open with "Done" and still bury
the ask. The miss row is a stage, not a verdict -- its false-positive
rate is the thing to measure next (taste
`heuristics.measure_their_error_rate`). Tastes outside `communication.*`
are injected, never scored. The hub's own clock (`otto.advisor.yaml`)
does not declare `tastegraph_refresh`; a hub session still learns a
change on its next prompt through the hook, not the clock.
