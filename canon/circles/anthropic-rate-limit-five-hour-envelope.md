# anthropic-rate-limit-five-hour-envelope

lugs/tonights-conductor-mechanisms-never-registered-as-real-circles.yaml --
registration of a mechanism landed 260906 with no declaration. Built by
lugs/statusline-usage-poller-dead-envelope-current-null.yaml.

## Why this exists

No Anthropic API exposes subscription headroom, and a hand-typed capacity
file on this machine once reached 583 HOURS stale while still being read as
current. Claude Code itself, though, hands the statusline
`.rate_limits.five_hour.used_percentage` and `.resets_at` on every refresh,
and `scripts/statusline-usage-poll.sh` persists them. This circle is the
reader half: it turns that real file into a real Envelope's `current`,
following budgetEnforcement.js's own established shape (measure from a real
source -> enforce -> optionally write back), never a fabricated number.

It targets a NEW Envelope, `anthropic-rate-limit-five-hour`, rather than
borrowing `otto-runtime-share` or `session-start-token-budget`: neither of
those is the same capacity, and writing this reading into either would put a
number in a field whose `capacity_kind` says something else.

## What it does

`src/otto/statuslineUsageEnvelope.js`:

1. `measureAnthropicRateLimitUsage` reads the instance's own
   `runtime/anthropic-usage-observed.json`, falling back to the
   machine-global `$HOME/.claude/runtime/` mirror -- the windows are
   per-ACCOUNT, so a reading taken in any spoke on this machine is a true
   reading here. First readable file wins; the two are never merged.
2. It returns `measured: false` with a named reason in four distinct cases:
   no file at either path, no parseable `observed_at`, an age past the
   declared `MAX_READING_AGE_HOURS` (5.0), or a payload with no `five_hour`
   window. A stale reading trusted as current is worse than an absent one.
3. `enforceAnthropicRateLimitEnvelope` loads the real Envelope row and, only
   when the caller passes `writeBack`, sets `current` on an Envelope file
   that already exists.

## What it does not do

It never polls. Both real pollers -- the in-session statusline one and the
headless one (the headless-usage-reading circle) -- are separate mechanisms; this
circle only reads what one of them left on disk. It never invents a zero: an
absent reading stays `null`, because a fabricated "0% used" would open a
budget gate on the absence of evidence.

The write-back is still a manual call rather than a scheduled job -- a real,
known gap, which is exactly why `failure_routing` points at
`five-hour-envelope-writeback-is-a-manual-call-not-a-job` rather than at a
generic escalation.

## Wiring

`runs_on: on_demand` -- there is no hook binding and no wheel_clock job of
its own; it is a library called by whoever needs the reading, chiefly
`detectWindowStart` (conductor-wave-gate) on every wave decision and every
heartbeat tick.
