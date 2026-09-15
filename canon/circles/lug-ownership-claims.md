# lug-ownership-claims

Who had a lug first, and what a second session should do about it.
Design record and the operator's verbatim direction:
`wheel-hub/docs/lug-ownership-claims-design-260913.md`. Build record:
`wheel-hub/docs/lug-ownership-claims-build-260914.md`.

## The table

`runtime/lug-claims.jsonl`, append-only under `withFileLock`. The kernel
verb appends `lug_claim` at `in_progress` (`--step` names the work) and
`lug_release` at `review`/`done`; the session-end handoff releases what
the ending session still held; `scripts/lug-claim.js release` is the
explicit hand-off. A lug's live claim is its last row when that row is a
claim. **First claim wins** — nothing here rewrites a row.

## Precedence — three signals, no fourth

| rank | who | signal |
|---|---|---|
| 3 | operator | `--as=<id>` naming a canon counterparty of type `operator`; or the session's registry row is **interactive** on a registry machine the operator owns, with no dispatch record |
| 2 | top-level | no dispatch record for this session (`personaBoundary.sessionDispatchContext`) |
| 1 | dispatched | `WCL_DISPATCH_ID` in the process (the launch supervisor's env), or a live scope grant for this session's root |

Then the lug's own priority (as it stands now vs. what the owner claimed
it at), then first claim. The claiming process computes its own rank and
writes it on the row with `rank_basis`, so a contender never guesses
another process's environment.

## Collaborate vs drive — a reading, not a judgment

`contend(lug, session)` → `{owner, owner_step, owner_live, precedence,
recommendation, reason}`. **Drive** only when the owner is stale (absent
from `runtime/session-registry.jsonl`, or no turn marker / registration
inside 30 min) or the contender outranks it. Otherwise **collaborate**.
The verb refuses `in_progress` on another live session's claim quoting
the reading, unless `--drive=<reason>` (takeover: the owner's release row
reads "taken over", a ledger decision row records the deviation) or
`--collaborate=<sub-scope>` (no claim, no transition; a `lug` Message to
the owner's session in the hub's `messages/messages.jsonl`).

## Guards

`src/hooks/lib/claimGuard.js` is the one check the four lug-write guards
share. A write to a lug another **live** session claims is refused with
the reading quoted. Posture: `canon/profile.yaml`
`autonomy_table_defaults.lug_claim_guard_posture` — `deny` (default) or
`warn` (never blocks, still writes the row). The guards never rewrite the
other session's version.

## Divergence

`runtime/divergences/<id>.json`: both versions verbatim, a unified diff,
each side's session and reason, and an impact reading — priority, state
per side, which done-gate inputs differ (`state`, `readiness`, `tests`,
`acceptance`), dependants from `lugEdges`. Written by the integrity
backstop when a lifecycle mismatch has two sessions in evidence, by a
`--drive` takeover that finds the lug file dirty, or by any fold with two
versions in hand. One open record per lug. `applyLugVerb` refuses every
transition on the lug until `scripts/lug-divergence.js resolve <id>
--keep=a|b|merge --session-id=<id>` lands a choice — content first, then
the state through the verb. `merge` is the file as it stands, declared
merged; no automatic three-way merge exists. Open divergences lead the
goals review.

## Out of scope

Cross-machine claims (one machine's session registry only); automatic
merge of lug prose.
