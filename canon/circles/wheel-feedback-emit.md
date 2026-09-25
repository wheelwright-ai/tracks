# wheel-feedback-emit

Stage 1 of the wheel feedback loop
(canon/initiatives/docs/wheel-feedback-loop-design.md, wheel-hub).
Measured before this circle: wheel-hub/messages/messages.jsonl held 2040
messages, every one `message_kind: cut` -- no guard denial, P0 row, gap
finding, exit-commit refusal, footer/upkeep miss, red suite or handoff
process note had ever travelled spoke -> hub. Each spoke's own findings
lived only in its own `ledger/` and `runtime/`, read by nobody but its
next session.

## Emit (spoke side, `src/lugTracking/wheelFeedbackEmit.js`)

`emitFeedback` runs from the SessionEnd hook
(`src/hooks/wheelFeedbackEmitHook.js`) and from the wheel-clock job
`wheelFeedbackEmit`. It reads, since `runtime/feedback-emit-cursor.json`'s
own cursor: guard denials (the four real guard hooks' own `REFUSED --`
ledger rows), P0 data-integrity rows (`p0AutoBugLug.js`'s own
`isP0DataIntegrityRow`/`deriveP0Cause`, reused), still-open disclosed-gap
findings (`turnGapScan.js`), session-exit-commit refusals (`REFUSED`/
`BLOCKED` `session-exit-commit` ledger rows), footer and upkeep misses
(`footer-miss` / `session-upkeep-miss` ledger rows), red suites named in
`runtime/push-logs/*.log` (the gate's own `NEW RED` / `FAILED` verdict
lines), and the last handoff's own `process_notes`.

Every source is coalesced by `cause_key` (never one message per
occurrence): count, first/last-seen span, one truncated representative
sample. Each cause becomes one `message_kind: feedback` message
(`schemas/message.schema.json`'s `feedbackPayload`: `cause_key`, `count`,
`cut_version`, `first_seen`, `last_seen`, `sample`), posted to the hub's
`messages/messages.jsonl` via `appendMessage` (schema-validated at
write). The cursor (ledger rows scanned, gap-finding ids seen, push-log
files seen, the last handoff timestamp forwarded) means a re-run with
nothing new emits nothing.

## Bound

Reuses `storeBounds.js`'s own `chargeBound` discipline
(`p0AutoBugLug.js`'s proven rules): one cap per session
(`FEEDBACK_MESSAGES_PER_SESSION_CAP`, 20) and one per day
(`FEEDBACK_MESSAGES_PER_DAY_CAP`, 50), each keyed under this spoke's own
`runtime/store-bound-state.json`. The first trip of either cap writes a
real ledger row and a stderr line naming the store, the cap and the
cause; detection is untouched -- the coalesced finding is still recorded
in `runtime/feedback-emit-result.json` even when its message is refused.

## Constraint (design doc 3.5)

A feedback message is data, never an instruction: `process-signal-inbox`
already stringifies every message's fields into a ledger row's text,
`feedback` included, and never executes or branches on one. No secrets
or credentials travel in any payload; samples are truncated
(`FEEDBACK_MESSAGE_SAMPLE_MAX_CHARS`, 400 chars).

## Declaring the job

A spoke with a wheel clock adds, to its clock-owning advisor's
`wheel_clock.jobs`: `wheel_feedback_emit: { job: wheelFeedbackEmit,
cadence_ticks: <declared> }`. Spokes without a clock rely on the
SessionEnd hook alone, same posture `update-discovery` takes for
SessionStart.
