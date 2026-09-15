# update-discovery

Stage 4 of the wheel feedback loop
(canon/initiatives/docs/wheel-feedback-loop-design.md, wheel-hub).
Operator, t6 (260912): "Otto's oversight should advise spokes to find
updates natively." Before this circle a spoke learned of a new cut once,
at `wcl <spoke>` entry; a running session, a cron-launched dispatch or an
unlaunched spoke never did, and cuts were pushed by hand.

## Publish (hub side, `src/factory/cutPublish.js`)

`hf deploy`'s cut stage (`stageCut`, `src/factory/deploy.js`) calls
`publishLatestCut` before it touches any spoke: `registry/latest-cut.json`
on the hub carries the framework HEAD as `version`, `generated_at`, the
circles and policies added/changed/removed and the lugs closed since the
previously published version (git, never hand-written), and one hub
ledger row (`source_type: cut_published`) per version -- the origin of the
metric. Same version twice: no rewrite, no second row.

## Discover (spoke side, `src/factory/updateDiscovery.js`)

`discoverUpdate` runs from the SessionStart hook
(`src/hooks/updateDiscoveryHook.js`) and from the wheel-clock job
`updateDiscovery`. It compares the spoke's last successfully applied
version (`.cut-status.json`) to the published one and then, in order:
the framework checkout must be at the published version; a rollback at
this very version is not retried; the verdict must be a pending cut
(`pendingCutVerdict`: byte-identical to the recorded cut, or already
clean -- a local edit reports, naming the file and `hf apply-cut`);
`checkSpokeLiveness` must show
no OTHER live session (the caller's own `session_id` is excluded). Only
then `applyCut` runs -- the same path `wcl` trusts, its holds and
refuse-class rollbacks reported as today. Every other outcome prints
`UPDATE AVAILABLE: <version> (<size>) -- <why>` as `additionalContext`
and writes one `update_available` ledger row per version. An apply
writes one `update_applied` row and announces the change to the calling
session.

## Oversight (Otto, `src/otto/cutLaggards.js`)

`runAdvisorAutopilot` records `runtime/cut-laggards.json` on every run,
ahead of every gate: each registered spoke's newest cut attestation
(`messages/`, `from: <spoke>`, `payload.applied_at`) against the published
version, hours behind, and `cut_published_to_spoke_absorbed_hours` for the
spokes that absorbed. The goals review prints the laggards from that
record and files nothing.

## Declaring the job

A spoke with a wheel clock adds, to its clock-owning advisor's
`wheel_clock.jobs`: `update_discovery: { job: updateDiscovery,
cadence_ticks: 3 }`. Spokes without a clock (basher, minder) rely on the
hook alone.
