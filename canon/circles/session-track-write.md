# session-track-write

Part A (work order "After Intake Protocols"): "Track: an Artifact
contract. One file per session, written by the Stop hook and closed by
the session-end circle, required sections asserted by conformance
(identity triple, active lugs and transitions, directions captured, cost
markers, decisions, handoff)."

## What it does

Runs on every Stop event, unconditionally (unlike `stop-turn-marker`,
which only fires when a lug or advisor is active). Recomputes
`runtime/tracks/<session_id>.track.json` from real underlying sources:
the session triple, lug-transition events since the track's own
`started_at`, direction/decision ledger rows in that window, and turn
markers summed the same way `track.js`'s own cost functions already do.

## Real, disclosed limitation

Neither ledger rows nor turn markers carry a `session_id` field today.
This circle scopes "this session's" content by real timestamp window
(`started_at` .. now) rather than an exact session_id filter --
overlapping sessions in the same narrow window could double-count. A
fresh track's `started_at` defaults to 30 minutes before its first write
(the first Stop of a session fires after one turn's worth of activity
already happened) rather than the exact session start.

## Retention

`src/lugTracking/trackArtifact.js`'s `archiveOldTracks()` moves tracks
older than 90 days from `runtime/tracks/` to
`runtime/tracks-archive/<YYYY-MM>/` -- never deletes. The ledger rows a
track's own session produced survive independently in `ledger.jsonl`,
unaffected by the track file's own archival state.
