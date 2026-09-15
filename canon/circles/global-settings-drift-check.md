# global-settings-drift-check

lug: global-settings-drift-has-no-recurring-check (wheel-hub). MAX-073
built `src/basher/globalSettingsPreview.js` -- a real, working, on-demand
comparison of the operator's global `~/.claude/settings.json`/
`statusline.sh` against v2 convention. It found 5 real stale v1-era
references the night it was built. Nothing called it except a human who
happened to ask, so drift like that accumulates silently until someone
does. The operator's own lesson, verbatim: "these things were all
forgotten because we called them done before they got a proper wiring
into the verifications." This circle is that wiring.

## What it does

At every real `SessionStart`, it runs `buildGlobalSettingsPreview` (no
overrides in production, so it resolves the real global
`~/.claude/settings.json`/`~/.claude/statusline.sh` via `os.homedir()`)
and turns its structured output into named ledger findings
(`src/basher/globalSettingsDriftCheck.js`): every stale reference, and
every gap whose own severity isn't `"none"` (a confirmed-no-gap is not a
finding). Each finding gets one real ledger row (`row_kind: "decision"`,
attribution `"global-settings-drift-check"`) carrying a stable
`finding_key` (e.g. `stale:_basher.managed_by`,
`gap:permissions.allow`) -- and the same count surfaces in the session's
own `additionalContext` at wakeup, so drift is a loud fact, not a silent
one.

Idempotent by `finding_key`: before writing, it reads the ledger for
rows already attributed to this circle with `status: "captured"` (still
unresolved) and skips any finding whose key is already open. Running the
check twice in a row with nothing changed writes zero new rows. A
finding whose row was later resolved (status moved off `"captured"` --
a human or Otto action, never this circle itself) is free to reopen if
it recurs.

## Why SessionStart, not wheel_clock

`canon/otto.advisor.yaml`'s `wheel_clock` mechanism
(`src/otto/wheelScheduler.js`) looked like the more obvious fit --
several other slow-moving drift checks (`reconcileAdvisorRoster`,
`verifyFleetVersions`) are wired there. Verified live before choosing,
per this lug's own explicit instruction not to assume: grepped every
caller of `tickWheelScheduler`/`runWheelSchedulerFor` outside a
conformance fixture, and found none -- `wheel-scheduler.md`'s own
disclosed gap ("Nothing in this build runs `tickWheelScheduler()` on an
actual timer") is still true today. A wheel_clock job declared now would
sit exactly as dormant as every sibling job until that separate,
larger, already-disclosed piece of infrastructure exists.

`SessionStart`, by contrast, is real and live right now: harness-factory's
own `.claude/settings.json` already fires 5 circles on it (`hook-binding-
drift` among them), confirmed by direct inspection. Every real session
genuinely is the recurring cadence this check needs -- and because it
runs inside the operator's own real process, `os.homedir()` resolves to
the real `$HOME`, not a synthetic one (verified live, read-only, before
writing any code: `~/.claude/settings.json` and `~/.claude/statusline.sh`
both exist and `buildGlobalSettingsPreview()` with no overrides read them
successfully). A wheel-hub-only job calling this from a hub-rooted
`instanceRoot` would have no such guarantee for a path that lives outside
every repo.

## What it does not do

It does not write `~/.claude/settings.json` or `~/.claude/statusline.sh`,
ever, for any reason -- the same hard boundary
`globalSettingsPreview.js` itself carries, unchanged. Applying any of its
findings stays a human-reviewed, human-applied step.

It does not catch drift introduced and reverted between two sessions --
same timing gap every other SessionStart-only circle in this build
already accepts (see `hook-binding-drift.md`'s own equivalent
disclosure).
