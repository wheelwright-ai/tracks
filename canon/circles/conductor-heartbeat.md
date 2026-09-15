# conductor-heartbeat

lugs/tonights-conductor-mechanisms-never-registered-as-real-circles.yaml --
registration of a mechanism landed 260907 with no declaration. Built by
lugs/conductor-persistent-supervisor-loop.yaml. Operating notes:
docs/conductor-heartbeat.md.

## Why this exists

MAX-112/114 built a real wave gate and wired it into `advisorAutopilot.js`.
All of it works -- and none of it can fire unless a Claude Code session is
ALREADY OPEN, because its only trigger is the wheel clock, which only ticks
inside a session. So the one moment the whole design exists to catch -- a
five-hour window opening while nobody is at the machine -- is exactly the
moment nothing is running to notice. This circle is the missing outside
caller.

## What it does

`src/conductor/heartbeat.js` `runHeartbeat`, one tick:

1. **Reconcile first.** `reconcileDispatchRegistry` checks what is already
   running. A row still plausibly in flight declines the tick -- deciding to
   start new work without asking what is in flight is how a concurrency-1
   workstation gets two waves stacked on it. Orphaned rows are surfaced, not
   just repaired quietly.
2. **The reading and the boundary**, via `detectWindowStart` (the
   conductor-wave-gate circle), with `persist: true` -- a heartbeat that did
   not consume the boundary would re-detect the same window start forever.
3. **Pace.** `paceModel.js` asks a question `decideWave` does not: not "is
   there headroom left" (a level) but "are you on track to spend it before it
   resets" (a rate). A window can sit at 35% headroom, well past the reserve,
   and still be EASE OFF on pace.
4. **Operator engagement.** `detectOperatorIdle` throttles the fan-out from
   2 spokes to 1 when the operator is active OR unknown.
5. **`decideWave`, unmodified**, at the throttled width. Its decision is the
   decision.

Every outcome -- launch or refusal -- lands in the same wave-record stream
and the same ledger the in-session gate already writes to. A quiet night is a
decision, and the operator most needs to see the record on the night nothing
happened.

## The additive-conservative rule

Each gate above may only turn a `decideWave` LAUNCH into a no. None can turn
a no into a launch. That is what makes it safe to run unattended: the worst a
bug here can do is decline a wave that should have run -- a lost opportunity,
recorded and visible -- rather than spend the operator's quota on one that
should not have.

## What it does not do

It is not a second decision engine; if the two ever disagreed there would be
no way to tell which was right, so there is only one. It costs nothing on
every default path. `--launch` is opt-in and OFF by default and is not what
the proposed cron entry runs -- wiring auto-dispatch into an unreviewed
trigger would make the first review of this code also its first live, billed
dispatch.

## Wiring

`runs_on: on_demand` -- `node scripts/conductor-heartbeat.mjs --poll`, from
cron, outside any session. Without `--poll` it reads only what a session's
statusline last left on disk, which is why unattended detection needs the
headless-usage-reading circle underneath it.
