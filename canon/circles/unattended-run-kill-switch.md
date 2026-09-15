# unattended-run-kill-switch

Built by wheel-hub's lug `unattended-run-has-no-kill-switch-or-whole-run-
cost-total` (260909). Build record, including what was left open, at
`wheel-hub/docs/` under that same name.

## Why this exists

Cron ticks `conductor-heartbeat.mjs --launch` every ten minutes and launches
billed waves with nobody at the machine. On 2026-09-09 a guard defect froze
five concurrent dispatches for 24 hours and **nothing outside those sessions
could stop them**. `killPendingDispatches` only flipped `queued` rows and had
no CLI caller. A running child detaches from its orchestrator by design — the
property that makes dispatch useful, and the one that made it unstoppable.

mywheel's `autopilot_loop.sh` had the first half (a `stop.flag` checked each
round) and totalled tokens. This restores both, plus what it lacked: it
reaches **running** children, and it **fails safe**.

## The fail-safe rule

**If the stop file cannot be read, that is a STOP, not a go.** A clean
`ENOENT` on a readable instance root is the only reading that permits spend.

The asymmetry is the argument: a wrong *stop* costs a declined wave, while a
wrong *go* keeps spending through the exact fault that made the switch
unreadable. A kill switch whose failure mode is "keep going" is not one.

## Both halves, proven separately

Halting new launches while running children keep spending is not a kill
switch, so the fixture proves the two halves in separate blocks.

**New launches** — three gates: `executeDispatch` (the last point before a
billed session spawns, so a *future* caller cannot escape it),
`runHeartbeat` Gate 0, `runAdvisorAutopilot` Gate 0. Both Gate 0s precede
`detectWindowStart`, which *consumes* the five-hour boundary — a halted night
that ate its boundary would leave nothing to launch from. Halted rows are
written `killed`, non-collapsible, so a retry really relaunches.

**Running children** — two independent mechanisms:

1. **The supervisor polls.** `runWithIdleWatchdog`'s ticker reads the flag
   every tick and kills its child through the same signal path a timeout
   uses, reporting `killedBy: "stop-flag"` and **not** `timedOut`.
2. **By recorded pid.** The supervisor self-registers its own pid and its
   child's into `runtime/dispatch-children.jsonl` — it must, since the
   `spawnSync` caller learns the pid only after it has exited.
   `terminateLiveChildren` folds that file, checks liveness with signal 0
   (never inferred from a missing `ended` row), and signals both — the path
   for when the supervisor is itself gone.

## The cost total

The child's stream-json result event carries its own `session_id`; its Stop
hook filed measured turn markers under that id in the spoke's
`runtime/track.jsonl`. Nothing joined the two, which is why `waveRecord.js`
writes `cost: null`. `executeDispatch` now joins it at finalize, on **every**
terminal outcome (a halted dispatch still really spent), and `runWarmup` sums
the rows.

No estimation, no pricing, and a missing measurement is never zero: a
dispatch reports `unmeasured` with a reason, and one with *some* null-token
markers is measured **with a stated shortfall**. Every total is three
numbers — the sum, what it covers, what it does not.

## Wiring

`hf stop [--root <dir>] [--by <id>] [--reason <text>] [--force]`, plus
`--status` and `--clear`.

Order is load-bearing: raise the flag **first** (a tick firing between
"killed the children" and "raised the flag" would launch onto a machine just
cleared), then terminate children, then `killPendingDispatches` — its first
caller. Each step is independently fault-tolerant; step 3 can legitimately
throw and never blocks the halt.

**The file is the primary interface.** `touch <root>/runtime/stop.flag` halts
the wheel just as completely from any shell, with no node and no working
harness. That reachability is the feature.

Out of scope: dollar pricing. `--clear` cannot resume a terminated child and
says so rather than implying a restart.
