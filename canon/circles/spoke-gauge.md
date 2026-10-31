# spoke-gauge

One line per spoke, so nobody has to ask: **GAS** (account capacity against the
window still ahead, and the work tank), **SPEED** (dones per day this week vs the
week before, dispatches landed vs dispatched), **POSITION** (RIGHT PLACE or the
first gap), **IMPROVE** (the top unstick action and who acts).

Shown three ways: first line of `node scripts/spoke-status.js`, first line of the
SessionStart goals review, one row per registered spoke in
`node scripts/fleet-gauge.js` (hub). Each Ozi run's close rewrites
`runtime/spoke-gauge.json`; the session-start line and Ozi's next brief read that
snapshot first and print its age once it is older than one cadence.

Everything is measured or says `unmeasured`. The data is `readPaceReading` and
`buildSpokeStatus`; the done counts come from `runtime/event-log.jsonl`
`lug_transition` rows. Fixture:
`conformance/fixtures/spoke-gauge/spoke-gauge.conformance.test.js`.
