# headless-usage-reading

lugs/tonights-conductor-mechanisms-never-registered-as-real-circles.yaml --
registration of a mechanism landed 260907 with no declaration. Built by
lugs/five-hour-reading-needs-a-headless-poll-not-only-a-session-statusline.yaml.
Full dated investigation: docs/headless-usage-reading-investigation.md.

## Why this exists

Two earlier passes (MAX-112, MAX-115) concluded the five-hour numbers exist
only inside a running session's statusline render. Both conclusions rested on
two checks that are still TRUE -- no documented endpoint exposes subscription
headroom, and `claude` has no `usage` subcommand -- and both missed a third
place. Claude Code's own `.claude.json` carries a `cachedUsageUtilization`
object, and a CACHE IS EVIDENCE OF A FETCH. Probed directly,
`GET https://api.anthropic.com/api/oauth/usage` returns that object's
`utilization` value verbatim.

That closes the hole the persistent heartbeat could not close on its own:
overnight, with no session open, the reading simply stopped changing, aged
past the Envelope's 5h rule, and every heartbeat correctly but uselessly
declined as unmeasured.

## What it does

`src/otto/headlessUsageReading.js`, `pollHeadlessUsage`: resolve credential
-> fetch -> normalize -> write.

1. The OAuth token comes from `$CLAUDE_CONFIG_DIR/.credentials.json` FIRST,
   then `$HOME/.claude/.credentials.json`. Order matters: the default $HOME
   copy on this machine was four days stale and its token was revoked, so a
   poller looking only there would have "proved" no headless source exists.
2. One GET, zero inference tokens, with Claude Code's own credential and
   user-agent. `ANTHROPIC_USAGE_ENDPOINT` is the seam the fixture (and an
   enterprise gateway) uses.
3. `normalizeUsage` renders the payload into the exact document shape
   `scripts/statusline-usage-poll.sh` already writes, and it is written
   atomically to both the instance's `runtime/` and the machine-global
   mirror.

Trustworthy because three independent first-party sources were checked live
against one instant on 2026-09-07T05:57Z -- the statusline's persisted
reading (`resets_at 1788778200`), this endpoint (`2026-09-07T10:50:00Z`), and
the `anthropic-ratelimit-unified-5h-reset` response header (1788778200). They
are the same instant. This is not a parallel estimate of the statusline's
number; it is that number.

## What it does not do

It never refreshes or rotates the credential -- that would race a live
session's own file and risk logging the operator out of his account to save a
poll. An expired token is therefore the one condition under which headless
polling genuinely lapses, and it reports unmeasured rather than guessing.

It never writes a reading it did not receive. Five named failure stages
(`credential`, `fetch`, `normalize`, `write`, and a 200 carrying neither
window) all write nothing.

## Wiring

`runs_on: on_demand` -- `node scripts/headless-usage-poll.mjs`, or
`scripts/conductor-heartbeat.mjs --poll`, which polls BEFORE deciding because
`detectWindowStart` both consumes the boundary and advances the baseline.
