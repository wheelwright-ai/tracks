# liveness-lease

Lug: `long-running-work-declares-a-liveness-lease-instead-of-a-flat-silence-kill`.
Build record, with every measurement:
`wheel-hub/docs/long-running-work-declares-a-liveness-lease-instead-of-a-flat-silence-kill.md`.

Operator mandate (260911), verbatim: "Long running processes should have
mandate to have a reset timer value in the lug so instead of flat off
killing it the agent can simply respect the saved countdown value and
note when it stops updating. This ensures hangs get cleaned up respective
of the time needed."

## The failure, measured

The launch supervisor killed a child after `DEFAULT_DISPATCH_IDLE_MS =
300000` of stdout silence, flat. Dispatch registry, 24h to 260912: three
legitimate runs `timed_out` with `killed_by: idle` at 300000 -- a
certification pass, a 48-lug batch, a sweep's second leg -- each in one
long quiet step (a Proofer call, a suite run). A hang and a nine-minute
provider call are identical to a silence timer. They are not identical to
a lease: a live process refreshes its lease before the countdown expires;
a hung one cannot.

## The lease

Verb-owned bookkeeping on the lug, in rule 11's `VERB_OWNED_LUG_FIELDS`:

```yaml
liveness_lease:
  countdown_ms: 600000
  refreshed_at: '2026-09-12T04:57:14.997Z'
  refreshed_by: <session id | dispatch id | pid:N>
  step: Proofer call for lug "X"      # required; no step = refused
  expires_at: '...'                    # derived
  refreshes: 1
  clamped_to_budget: true              # only when the wall clock cut it
```

One writer: `refreshLivenessLease(instanceRoot, lugRel, { step,
countdownMs, budgetDeadline })`. `leaseForStep({ step, countdownMs })`
is the same call resolved from the environment the launcher sets
(`WCL_LIVENESS_LEASE_PATH`, `WCL_LIVENESS_BUDGET_DEADLINE`,
`WCL_DISPATCH_ID`); outside a supervised launch it is a recorded no-op.
From a shell: `node scripts/liveness-lease.js refresh --step=...
--countdown-ms=...`. The write re-records the integrity checksum.

## The supervisor's rule

On its ticker, `idleWatchdog.js` reads the lug (re-parsed only when its
mtime moves) and evaluates: `deadline = min(refreshed_at + countdown_ms,
startedAt + timeoutMs)`; a lease whose expiry precedes `startedAt` is a
prior run's and is ignored. Then, in order: the operator's stop flag; the
wall clock (`now - startedAt >= timeoutMs` -> `wallclock`, whatever the
lease says); silence (`now - lastOutput >= idleMs`) **unless the lease is
live** -> `lease-expired` when a lease was declared, `idle` otherwise.

A `lease-expired` envelope carries `lease.last` (refreshed_at,
countdown_ms, step, refreshed_by, expires_at), `expired_at`, `killed_at`,
`last_output_at`; the journal gets `lease_refresh` rows for every refresh
seen and a `lease_expired` row; the dispatch row's `outcome_detail` says
"stopped updating at T during step S". A run with no lease reads
`lease.declared: false` and dies on the flat window exactly as before.

## Wired long steps

`proofer.js` before `callProvider` (sized to every attempt plus backoff);
`readinessSweep.js` before each fixture `spawnSync` and before the
certification chain; `advisorAutopilot.js` before each nested
`executeDispatch`. `executeDispatch` names the lease file from `lug_ref`
when a lug file exists; a role dispatch has none and is recorded
`liveness_lease.eligible: false`.

## The fallback census

`buildLivenessFallbackSection` (goals review, session start): once per
distinct count -- leased / had a lug and declared none / role dispatches /
lease-expired kills / idle kills, with lug refs. `node
scripts/liveness-lease.js report` prints the same counts on demand.
