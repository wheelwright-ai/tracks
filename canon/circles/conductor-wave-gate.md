# conductor-wave-gate

lugs/tonights-conductor-mechanisms-never-registered-as-real-circles.yaml --
registration of a mechanism landed 260906 with no declaration. Built by
lugs/conductor-autonomous-five-hour-wave-orchestration.yaml (MAX-112/114).
Design: docs/conductor-wave-orchestration.md.

## Why this exists

"Conductor runs at the start of each five-hour usage window, decides whether
to launch a wave, picks the spoke(s), reviews results, decides on another
wave -- fully automatic." That needs one thing first: a real answer to "did a
window just start", from measured evidence rather than a wall-clock guess.

## What it does

Four modules, one chain:

- `windowStart.js` `detectWindowStart` compares the current reading against
  the stored baseline in `runtime/five-hour-window-state.json` and returns
  one of four states -- `unmeasured`, `no_baseline`, `same_window`,
  `started` -- with the driving signal named. Only `started` is ever
  launch-eligible. `windowStillOpen` answers the different question the
  repeat arm asks: still open, with headroom, and not closing.
- `waveDecision.js` `decideWave` gates on that, then on the declared 20%
  headroom reserve, then builds a real candidate pool from `registry/groups/`
  (a Group "applies" only when at least two of its members really resolve on
  this machine AND really have ready work), weights each spoke by
  `ready_weight x outcome_multiplier x allocation prior`, and picks up to the
  declared ceiling of 2.
- `waveReview.js` folds the finished wave's outcome and decides go-again --
  three conditions, all required, each able to stop the loop by name.
- `waveRecord.js` persists every decision, launch or refusal, to
  `runtime/wave-records.jsonl` in one shape shared with Max-origin waves.

## The three boundary signals, in order

`resets_at_crossed` (the stored reading's own declared reset is already past
this reading's `observed_at`), `resets_at_changed` (two different first-party
boundaries, past the declared 60s same-boundary tolerance), and only as a
fallback `used_percentage_dropped` past a declared 15-point floor, used when
a `resets_at` is missing from one side.

Both `resets_at` shapes parse as INSTANTS (epoch seconds as a string from the
statusline, ISO-8601 from the headless source). Before MAX-115 the epoch string
parsed as NaN, so both primary signals were silently unreachable;
`failure_routing` names that lug.

## What it does not do

It never computes a window boundary from elapsed time -- the account's window
is set by Anthropic and drifts with real usage. It never treats an unknown as
a yes: unmeasured and no-baseline decline, separately and by name, because a
yes spends the operator's quota.

## The one gate removed (260909)

An empty ready-work queue is no longer a refusal (lug
`conductor-wakes-the-spoke-rather-than-gating-on-an-empty-ready-queue`, after a
real boundary at 100% headroom was declined and the window spent on nothing).
`decideWave` returns `launch_kind: "maintenance"`, wakes ONE spoke
(`MAINTENANCE_WAKE_MAX_SPOKES`) with guidance "no build work currently clears
the ready bar"; the refusal survives behind `requireReadyWork: true` for the
repeat arm. Proof: `conformance/fixtures/conductor-wake-on-empty-ready-queue/`.

## Wiring

`runs_on: on_demand` -- no hook binding, no wheel_clock job of its own. Two
real callers: `advisorAutopilot.js` in session (on the `advisor_activation`
job) and `scripts/conductor-heartbeat.mjs` out of session.


A spoke's ready count is its execute-only count (lug `a-wave-launches-only-for-work-the-drive-will-accept`): `evaluateSpoke` keeps only the ready lugs the drive's own bar accepts, so the wave reason names, per spoke, "N execute-only (k cross-spoke, ...)". Proof: `conformance/fixtures/wave-counts-execute-only/`.
