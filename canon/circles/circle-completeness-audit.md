# circle-completeness-audit

lug `absorb-mywheel-circle-audit-tool`: ports the archived predecessor
project's `circle_audit.py` -- a registry naming each circle's initiator/
deps/return-edge evidence, emitting `CLOSED`/`OPEN`/`PHANTOM` verdicts.
PHANTOM is what a real, by-hand audit found twice: `wheel-clock-catchup`
(fixed, MAX-092) and `reconcile-ledger` (filed separately) -- both
declared and coded, neither ever wired, invisible for days.

## What it is, honestly

A real three-way join per circle, from live inspection only, never a
hand-maintained registry (full detail in `src/factory/circleAudit.js`'s
header comment):

- **hook_event**: `CLOSED` iff declared live AND a real binding exists in
  `.claude/settings.json` (via `checkHookBindingDrift`) AND `hook_script`
  exists on disk.
- **schedule**: `CLOSED` iff the circle corresponds to a real
  `wheel_clock.jobs` entry AND that job has a real `JOB_RUNNERS` runner.
  Correspondence: `depends_on` naming real `JOB_RUNNERS` keys directly is
  authoritative; otherwise a job's camelCase value, kebab-cased, must
  equal/contain the circle's kebab name (verified against all 8 of
  wheel-hub's real schedule circles, no ambiguity today). No canon field
  names this directly -- the one gap this tool works around.
- **on_demand**: `CLOSED` iff a real entry point resolves and exists,
  derived from the fixture's own `path.join(REPO_ROOT, ...)`
  construction (the one place it must already be named).
- **OPEN** (once otherwise wired): the declared `conformance` fixture
  must exist under the framework root, and a bare (non-`external:`)
  `depends_on` naming another PHANTOM circle downgrades this one too.
  Either failing is OPEN, distinct from PHANTOM.

A real PHANTOM opens a real `p0_data_integrity` bug-fix lug via the
existing `p0AutoBugLug.js` gate -- never a second auto-lug-filer.

## Kept vs changed from mywheel

Kept: the three verdicts, the three-way join, "a hand-maintained registry
is itself a liability." Changed: the `CIRCLES` registry is replaced by
this instance's real canon (`loadCanon`). Freshness-bounded evidence
(file/glob + hours bound) is narrowed to existence-only checking of
`conformance` -- no per-circle artifact-path field exists here, and
inventing one unused would be speculative. Staleness isn't ported: a
committed test file's mtime doesn't mean "fired recently."

## Cadence, disclosed

One tier, every `SessionStart` -- not mywheel's cheap/deep split. Its
deep tier did materially more work (subprocess calls, hub checks) gated
behind a rarer trigger; this check is already cheap in-memory joins, no
heavier variant to economize behind. Scoped to the harness-factory
worktree alone this dispatch -- an additional wheel_clock tier needs
wheel-hub's own `otto.advisor.yaml` (a different repo, and the mechanism
the sibling `reconcile-ledger` dispatch lands in parallel) -- left to a
future wheel-level dispatch.

## Known, accepted gaps

- Schedule-job correspondence is a live heuristic, not an explicit canon
  field; a future collision needs a real field (e.g. `schedule_job`).
- The dependency leg skips `external:`-prefixed prose and bare
  identifiers matching neither a circle nor a `JOB_RUNNERS` key (e.g.
  `wheel-clock-catchup`'s own helper functions) rather than guessing --
  flagging every unresolvable entry would false-flag it.
- Evidence-staleness is not checked, only existence.
