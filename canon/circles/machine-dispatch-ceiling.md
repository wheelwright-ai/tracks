# machine-dispatch-ceiling

Lug `machine-dispatch-ceiling-is-enforced-memory-aware-and-covers-agent-forks`.
On 2026-10-02 seven parallel Agent-tool builders on a 6-cpu / 8 GB WSL VM
fragmented kernel memory (487 `page allocation failure: order:7` lines)
until WSL's DNS tunnel could not open its channel and the session died with
`EAI_AGAIN`. The per-machine ceiling in
`canon/policies/parallel-dispatch-by-default.policy.yaml` was prose only,
and Agent-tool forks never pass through `dispatchMechanism.js`.

## One measurement, three places

`src/factory/machineCapacity.js` `measureDispatchCapacity({ hubRoot, now, readers })`
reads the machine entity for this hostname (`registry/<name>.machine.yaml`:
`max_concurrent_dispatches`, `dispatch_pause_when`) and four values:

| value | source |
|---|---|
| load per cpu | `/proc/loadavg` over the cpu count |
| MemAvailable (MB) | `/proc/meminfo` |
| large free blocks | `/proc/buddyinfo`, Normal zone, order 7 and above |
| kernel allocation failures | `journalctl -k -b -o short-unix`, 1500 ms timeout: the count since boot, and the count in the last `kernel_alloc_failures_window_minutes` (default 15) |

A value it cannot read is `null`, listed in `unmeasured`, and trips nothing.

It is enforced at:

1. `executeDispatch` -- a real launch at the ceiling or while paused stays
   `queued` with a `capacity_hold` carrying the numbers; `queueDispatch`
   hands the same row back on the next request for its lug.
2. `runAdvisorAutopilot` (Gate 0c) and `runHeartbeat` with `--launch` --
   the tick is declined before the window boundary is consumed.
3. This hook, on the Agent tool.

## What the hook does

- **Refuses** only on a hard signal, on a machine whose entity declares
  `dispatch_pause_when`: kernel allocation failures in the recent window
  above `kernel_alloc_failures_recent_above` (default 0), or MemAvailable
  below `mem_available_mb_below`. The message carries the measured numbers
  and every way out.
- **Ways out of the kernel refusal:** wait -- it clears by itself N minutes
  after the last failure; or `touch runtime/dispatch-ceiling.ack` in the
  main checkout, no session restart -- an ack newer than the newest counted
  failure turns the refusal into an advisory, and a failure after it counts
  again. Also the relief line `sudo sysctl vm.compact_memory=1`.
- **Advises and allows** on a soft signal (load per cpu, few large blocks),
  on the since-boot count (`kernel_alloc_failures_since_boot_above` is read
  for the advisory only), and on any hard signal when no machine entity
  declares thresholds.
- **Off switch:** `WHEEL_DISPATCH_CEILING=off` in the session's environment.
- **Fails open:** any error inside allows the call and exits 0.

The kernel-log reading is cached for 60 s in the user's runtime dir
(`$XDG_RUNTIME_DIR/wheel-machine-capacity/kernel-log.json`, else the temp
dir): a machine fact, kept out of every checkout's tracked `runtime/`.

## Honest limits

The same recent-window rule and ack pause and release the harness launch
holds. Agent forks are not counted against `max_concurrent_dispatches` --
no registry records them -- so the hook judges the machine's state, not a
fork count. A kernel log line with no timestamp leaves the recent count
unmeasured, which refuses nothing.
