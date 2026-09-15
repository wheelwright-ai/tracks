# communication-inbox-delta

lug communication-inbox-delta-injected-at-each-prompt (260914), step 2
of the driving initiative wheel-agents-talk-up-down-and-across. The
operator's complaint: a harness-factory session was already running and
did not know about the night's work until asked -- "this shouldn't take
my interaction to ensure it happens quickly." Both sides share disk
(the hub's `messages/messages.jsonl`, routed to ledger rows every 3
ticks by process-signal-inbox) but nothing written mid-session by one
reached the other until its next wakeup.

## What it is

One UserPromptSubmit hook (`src/hooks/communicationInboxDeltaHook.js`),
one module (`src/messaging/inboxDelta.js`):

1. **Delta.** On every prompt the hook reads the hub's message store
   (`resolveHubRoot`, the same lookup tastegraph-injection uses) with
   `messageStore.readMessages` and keeps the rows appended since this
   session's cursor whose `to` is this spoke's name (the announced
   triple's `spoke`, else the root's directory name) or the broadcast
   `spoke`. It also reads the hub's `lugs/` for `type: communication`
   lugs with `target_spoke` equal to this spoke and a status not in
   fulfilled/declined/closed, and keeps the ones the cursor has not
   listed.
2. **Block.** One `COMMUNICATION INBOX DELTA for <spoke> (...)` block,
   one line per row quoting name/from/to/message_kind and a truncated
   attestation (a lug line quotes name/owner/ask/status and its intent),
   cut at 600 chars with the unshown count stated. Rows addressed by
   name come first, then the communication lugs, then broadcasts, a
   `direction` before a `cut`, so the half-hourly navigator/capabilities
   cut rows never push a direction out. Nothing in the block is an
   instruction; it is quoted data.
3. **Cursor.** `runtime/communication-inbox-cursor/<session_id>.json` in
   the spoke's own runtime/ -- `messages_seen` (the store's length at the
   last read), `lugs_shown` (names) and `carried` (by-name rows the cap
   hid, at most 40 -- shown on the next prompts; only what was rendered
   counts as shown, measured on the real hub 2026-09-14 where 32 open
   communication lugs already target harness-factory). Written after
   every read; the only write the circle makes. A missing cursor writes one at the
   current length and injects nothing, so a fresh session is not
   replayed 2,600 rows; it hears from its first prompt on. A compaction
   does not touch runtime/, so the cursor survives it.

## Known, accepted gaps

Fair ranking (priority, escalation, seniority, ask) is lug
communication-inbox-circle-and-fair-ranking; this circle applies a fixed
precedence only. Push notification is out of scope. A message that
predates a session's first prompt is history, not delta: it reaches the
session through the ledger row process-signal-inbox already writes, or
through a hand-seeded cursor -- the real 260914 direction row was
delivered that way, recorded as a ledger row naming the session.
