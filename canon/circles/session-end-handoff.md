# session-end-handoff

Part A: "Handoff: a session-end circle that writes the next session's
starting state into the continuity checkpoint and the track, so wakeup
reads the handoff, never the transcript."

## What it does

Fires on SessionEnd. Builds a real handoff object (`src/lugTracking/
handoff.js`'s `buildHandoff`) from the active lug pointer, the top of the
real ready-work queue, and this session's own track's last decisions/
directions/cost. Writes it to `runtime/last-handoff.json` (what the next
session's `session-continuity-checkpoint` circle reads) and closes this
session's track (`closed_at` + the same `handoff` object) via
`closeTrack()`.

## Real, disclosed limitation

Neither v1 nor v2 (before this pass) ever built a distinct, purpose-built
handoff artifact -- the v1 behavior harvest (fork a6e4874c9bdc300ad)
found v1 had "wakeup reads the prior track directly," a lighter
mechanism, not a real handoff object. This circle is the first real
handoff artifact either version has had.

## Failure mode

A handoff-write failure never blocks the real session from ending --
worst case, the next session's wakeup finds no handoff and falls back to
the existing continuity-checkpoint mechanism (active-lug.json + backlog
summary), which predates this circle and is unaffected by it.

## Unqueued defined lugs (260914)

Lug max-plans-planner-schedules-ozi-dispatches-and-reports-validated: the
handoff also lists every `defined` lug of this spoke absent from the
Planner's last cycle queue (`runtime/planner-cycle.json`), each with the
Planner's own reason (`isReadyForRouting`, `src/conductor/readyWork.js` --
the build queue's own order), or `readPlannerCycle`'s verbatim reason when
no usable cycle exists. Full list on disk in
`defined_outside_planner_queue`; the injected text carries one bounded line.
