# session-registry

260828-FBL-012 item 1. Registers every session that touches a spoke into
a per-spoke registry (`runtime/session-registry.jsonl`) on SessionStart,
so a session can be found again later and its track consumed. Idempotent
per `session_id` -- a resume or compact re-fires SessionStart for the
same real session (confirmed live, `docs/warmup-capture.jsonl`), and this
circle registers once, not again.

Assigns a callsign from the curated wordlist (`canon/callsign-wordlist.yaml`,
`src/identity/callsigns.js`), unique per spoke within a rolling 30-day
window; pairs two words on exhaustion rather than numbering.

The wordlist is resolved from the **spoke's own canon first**, falling back
to the harness-factory checkout the running hook code itself lives in --
`src/identity/callsigns.js`'s `HARNESS_ROOT`, the same self-referential
resolution `wcl` uses. Before that fallback existed, only harness-factory
had the file and this circle therefore threw on every SessionStart in every
other spoke, so registration had never run outside harness-factory at all
(lug `spoke-callsign-wordlist-missing-kills-session-registration`,
`docs/spoke-callsign-wordlist-resolution.md`). A wordlist is still never
fabricated: with no real file at any candidate, assignment refuses and names
every path it checked.

`mode` (interactive | headless) is read from `WCL_LAUNCH_MODE`, an env var
`src/basher/wcl.js` sets on the processes it spawns headlessly -- not
introspected from anything Claude Code itself exposes to a hook (no such
field exists in the real captured `SessionStart` stdin).

Consumed by: `src/factory/cutUpdate.js`'s `applyCut` (the session liveness
gate, 260828-FBL-024/025), and `wcl sessions <spoke>`.
