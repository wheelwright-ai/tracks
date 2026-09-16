# closeout-report

Design: `wheel-hub/docs/session-entrance-exit-redesign.md`, section X1
(X2 injects the protocol, X3 carries findings forward -- neither is here).
Code: `src/lugTracking/closeoutReport.js`, `scripts/closeout.js`,
`DIRTY_FILE_CLASSES` in `src/lugTracking/handoff.js`.

## Why

Measured 2026-09-15: every exit finding the wheel produces (dirty tree,
unpushed commits, unreachable remote, lug left in flight, upkeep miss) is
produced at SessionEnd, where no agent is left to act and most of it
prints nothing. A basher session told the operator to run the retired v1
`/wai-closeout` because v2 had no closeout verb. This is the read-only
report an agent runs when the operator asks to end the session, so it can
act (scoped commit, kernel-verb transition, upkeep repair) while it can.

## What it reads

Per repo (home + `registeredRepoRoots`): dirty files through
`DIRTY_FILE_CLASSES` -- telemetry `runtime/ ledger/ messages/
.cut-status.json` | work `lugs/ canon/ src/ docs/` | unknown; untracked
lug files; ahead/behind the upstream; `git ls-remote` (all repos at once,
1 s default); live peers via `liveSessionsAt`.

Per session: lugs touched (track transitions, files-touched record,
active-lug pointer) with the state their file carries now --
`in_progress` is a finding; `evaluateUpkeepManifest` run now, its
`handoff` and `session_registry_row` rows marked `settles_at_session_end`
and not counted; miss rows this session caused; `openDecisions` this
session issued; `buildHandoff` as the preview.

## Output

Table on stdout: one line per finding (`ACTION` / `INFO` / `ERROR`,
stable id, text) plus its `recheck:` line, then the repo strip and the
first handoff lines. `--json` is the whole object. No findings: one line,
exit 0. No session id: usage, exit 2.

Finding ids: `dirty-work:<repo>`, `dirty-unknown:<repo>`,
`dirty-telemetry:<repo>`, `untracked-lugs:<repo>`, `ahead:<repo>`,
`behind:<repo>`, `remote-unreachable:<repo>`, `peer-sessions:<repo>`,
`lug-in-flight:<lug>`, `lug-missing:<lug>`, `upkeep-miss:<asset>`,
`session-misses:<row_kind>`, `vetoable-acts`, `git-status-failed:<repo>`.

## Measured

Real wheel-hub, 2026-09-15, 6 repos, 40k ledger rows, 313 lugs: 1.7-2.0 s
report, 2.2-2.5 s script wall at load 2-4 on 6 cores (was 3.4-5.1 s before
the handoff preview moved to a child process started with the remote
probes and the ledger became one pass); 8-13 s at load 13-20 (sibling
gates), where the fixture prints the number and does not judge the 5 s
claim. GitHub ssh `ls-remote` takes ~1.6 s here; the probe overlaps the
synchronous readings, so at 1 s it still answers on the hub;
`--remote-timeout=3000` when a remote is known slow. Tree hash equal on
every run; the movers seen between attempts were siblings (wheel-clock
catch-up state, the running dispatch's own journal, usage polls).
