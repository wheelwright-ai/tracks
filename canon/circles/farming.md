# farming

The harvest step atop the pattern language. Operator, 260910: *"The
ability to see these patterns will allow an abstraction of shared
solutions that can be farmed."* Lug
`farm-recurring-spoke-solutions-into-promoted-shared-abstractions`
(wheel-hub); build record in that hub's `docs/`.

## The asymmetry, and why every step refuses

Duplication is local and cheap. A wrong shared abstraction is fleet-wide
via the cut, so every spoke inherits the mistake. Farming is therefore
harder than skipping at every step:

1. **Detect** (`detectRecurrence`) -- over independent spoke roots (same
   real path or git remote = one root), every spoke-authored canon entity
   by exact `kind:name`. Cut copies, promoted copies and reference circles
   are excluded. A key in >= 3 roots recurs; fewer is reported below the
   bar. Report: `runtime/farm-recurrence.json`.
2. **Propose** (`proposePromotion`) -- re-detects live; refuses below the
   bar, a non-cut-carried kind, an open harvest, or an incomplete
   abstraction. The variation surface is computed; the proposer only
   resolves each differing path to an observed value or `{absent: true}`.
3. **Certify** (`certifyHarvest`) -- a witness `checkIndependence` finds
   independent of the proposer; `rejected` is recorded too.
4. **Apply** (`applyHarvest`) -- writes `reference/circles/<name>.yaml`
   (schema-validated) carrying `visibility: promoted`, `promoted_from`,
   `derived_from` per origin, and `harvest`. Never overwrites a
   framework-authored circle. Spokes receive it on their next cut.
5. **Demote** (`proposeDemotion` -> certify -> apply) -- same door, on
   evidence pointers that resolve; apply removes the file unless it
   drifted. The next cut takes it out of every spoke.

Every step is a row in `kb/farm-harvest.jsonl` (`entity_kind`, `action`,
`direction`, `harvest_id`) and a hub ledger row. `auditPromotions` checks
the store against disk. `buildFarmSection` prints only what needs acting
on; a measured "none yet" is CLI output, not session-start injection.

## Disclosed limits

- Only `circle` is cut-carried today; a recurring policy or advisor is
  reported and cannot be promoted through this path.
- The variation surface is PRESERVED on the record; the compiler has no
  per-spoke substitution, so the promoted circle carries the chosen
  observed value and each spoke's own is recorded, not applied.
- Independence of ROOT is enforced (path, remote); independence of
  AUTHORSHIP is not knowable from disk and hashes are printed instead.
