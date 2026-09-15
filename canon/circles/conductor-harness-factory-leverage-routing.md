# conductor-harness-factory-leverage-routing

lugs/conductor-harness-factory-leverage-routing.yaml -- a real gap confirmed
live 2026-09-07: this wheel has no concept anywhere in canon of routing real
dispatch effort/budget specifically TOWARD harness-factory work. A fix built
in harness-factory (the mechanism this whole wheel runs on -- e.g. a
mechanism bug circle-audit.js itself catches) benefits every spoke once
cut-distributed, strictly higher leverage than a same-size fix made locally
in one spoke -- but nothing in canon/priority-policy.policy.yaml or in
src/conductor/readyWork.js's ranking ever reflected that. A
harness-factory-targeted lug sorted exactly like any other same-priority
ready-queue item.

## Why this exists

Priority-policy already ranks the ready queue by declared severity class
(canon/priority-policy.policy.yaml's severity_classes, rank 1 through 7),
and within `ready_queue_by_declared_priority` (rank 5) buildReadyWorkQueue
breaks ties by lug name alone. That's silent on leverage: a proven,
ready-to-ship harness-factory fix and an equally-proven spoke-local fix of
the same declared priority are indistinguishable to the ranking, even though
landing the harness-factory one first compounds -- it ships to every spoke
on the next cut, the spoke-local one ships to exactly one.

## What it does

One real rule, read from canon, and one real tie-break that applies it:

- `canon/priority-policy.policy.yaml` carries a new rule,
  `harness_factory_proven_leverage_tiebreak`, in its existing `rules` array
  (the same shape every other rule there already uses -- id + text; no new
  severity class, no change to any existing rank).
- `src/conductor/readyWork.js`'s `isHarnessFactoryTiebreakActive(instanceRoot)`
  loads that real file on every call and checks it is `status: active` and
  that a rule with that id is present -- a real read of canon, not a
  hardcoded assumption of one, so removing the rule from policy silently
  turns the mechanism back off with no code change.
- `isHarnessFactoryTargeted(lug)` is true only for a real
  `external:harness-factory/...` pointer -- never a prose mention.
- `hasProvenHarnessFactoryLeverage(lug, instanceRoot)` is true when the
  lug's own `harness_factory_proof` field names either an explicit,
  live-verified `circle_audit_result: "CLOSED"`, or a `conformance_fixture`
  path that really resolves to a file on disk under the resolved
  harness-factory framework root (`resolveFrameworkRootDefault`, the same
  resolution `circleAudit.js`/`hookBindingDrift.js` already use).
- `buildReadyWorkQueue`'s sort, when the rule is active, breaks a
  same-priority-tier tie in favor of a lug where both are true, before
  falling back to the existing name sort.

## What it does not do

It never reorders across priority tiers -- a critical spoke-local lug still
outranks a high-priority harness-factory-proven one, because `lug.priority`
(via `priorityRank`) is still checked first, unchanged. It never trusts an
unverified claim: a lug that merely mentions harness-factory, or that
carries a `harness_factory_proof` pointing at a fixture that doesn't
actually exist on disk, gets no boost.

## Wiring

`runs_on: on_demand` -- no hook binding, no wheel_clock job. Every real
caller of `buildReadyWorkQueue` (`goalsReview.js`, `warmup.js`,
`conductor.js`'s `planRouting`, `waveDecision.js`'s candidate-pool build,
`factory/positionMap.js`, `lugTracking/handoff.js`) gets the tie-break for
free, gated by the same real policy read.
