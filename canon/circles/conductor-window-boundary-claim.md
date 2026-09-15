# conductor-window-boundary-claim

lugs/conductor-two-cron-drivers-race-the-same-window-boundary.yaml (filed
260908 from a real design review, report R1, verified against the live
crontab). Implementation: `harness-factory/src/conductor/boundaryClaim.js`.
Full design notes: `docs/conductor-window-boundary-claim.md`.

## Why this exists

The installed crontab has two `*/10 * * * *` entries firing the same
minute: `conductor-heartbeat.mjs --poll --launch` and
`runWheelClockCatchup(...)`. Both are wanted, separate processes doing
separate jobs -- but `wheelClockCatchup`'s `advisor_activation` job calls
`detectWindowStart`/`decideWave` on its own too. On the tick a five-hour
window really turns over, both processes can read
`runtime/five-hour-window-state.json` before either rewrites it, both see
`resets_at_crossed`, and both can launch real, billed `claude -p` children
for the *same* boundary. Nothing had double-launched only because the
ready-work queue was empty; since 260909 an empty queue wakes a spoke
anyway, so the race is armed now.

## What it does

One thing: an atomic, durable claim on one boundary-crossing event.
Whichever process gets there first creates
`runtime/window-boundary-claims/<key>.claim.json` with `O_CREAT|O_EXCL` --
kernel-atomic on a local filesystem, so exactly one of any number of
concurrent creators succeeds and every other gets `EEXIST`. The winner
proceeds; every loser is told who holds the boundary and no-ops. Two call
sites only: `src/conductor/heartbeat.js` `runHeartbeat` (Gate F, after
`decideWave` returns LAUNCH, when `options.claimBoundary` is set) and
`src/otto/advisorAutopilot.js` `runAdvisorAutopilot` (between `decideWave`
and `openWaveRecord`).

## A claim, not a mutex

No release, no lease, no expiry -- a window boundary is an event acted on
once, ever, so there is no stale-lock recovery to get wrong and nothing
here retries or spins. Cost, disclosed: if the claim-winner dies before
launching, that boundary is spent and no wave runs for it -- a lost
opportunity, but recorded (holder, pid, instant) and consistent with
`heartbeat.js`'s own additive-conservative rule: decline a wave that
should have run, never spend quota on one that shouldn't.

## Why the key comes from the baseline, not the reading

The claim key names the window that *ended* -- the stored baseline's own
`resets_at`. Two racers agree on this because they raced by reading the
same baseline before either rewrote it; their live *readings* may
legitimately differ (`--poll` refreshes mid-race), and a key derived from
the reading would let two processes compute two different keys for one
boundary and both "win" -- the same race, one layer down (fixture check
A3). When a baseline has no readable `resets_at`, the key falls back to
`observed_at`, still shared by both racers.

## What did NOT change

Neither cron entry is removed or merged -- only the one shared action
("act on THIS boundary") is excluded. The stored baseline is still the
primary defence (a later reader sees `same_window` and never reaches the
claim); the claim is the backstop for the read window between the two
processes, not a replacement (fixture section G). No new daemon, no third
driver -- a hard constraint from the lug.

## Where it can drift

A `runtime/` moved off a filesystem with working `O_EXCL` would weaken the
atomicity guarantee. A third `decideWave` caller added later without a
claim would reopen the gap; `failure_routing` names this lug.

## Proof

`conformance/fixtures/conductor-boundary-claim/` -- 38 checks. Section C
spawns real, separate OS processes racing one shared start instant: eight
racers on the bare claim (exactly one wins), then the real pair of cron
drivers launched together against one hub (exactly one launches; the other
reports `window_boundary_already_claimed`). Zero cost -- synthetic roots
under `os.tmpdir()`, and the one path that could spawn a real `claude`
child uses an injected stub that counts and spawns nothing.
