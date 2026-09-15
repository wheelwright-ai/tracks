# lug-kernel-verb

Ruling 2026-08-26: "lug state changes go only through a kernel verb."
`src/lugTracking/lugVerb.js` (`scripts/lug-verb.js` for the CLI) is that
verb: `node scripts/lug-verb.js <lug-relative-path> <new-state> [flags]`,
run with `cwd` at the instance root.

## Why a verb instead of intercepting edits

Every gate this design has built so far (`definition-complete-gate`,
`ready-gate-stub`, `lug-lifecycle-tracker`) works by intercepting an
`Edit`/`Write` and deciding whether to let it through. That only works if
the edit goes through `Edit`/`Write` at all -- and a Bash `sed` proved it
doesn't have to. A kernel verb sidesteps the question of which tool made
an edit entirely: it doesn't intercept a proposed write, it *is* the write.
Run it, it checks the same rules the hooks check (the exact same
`checkDefinitionComplete` function, the exact same stubbed-only rule for
`ready`, the exact same traceability-and-real-cost rule for `done`) and
either applies the change or doesn't. There's nothing to bypass by picking
a different tool, because no tool other than running this script produces
an authorized change.

## What it enforces per target state

- `defined` and beyond: `checkDefinitionComplete`.
- `ready`: requires `--readiness=stubbed` exactly; nothing else is honest
  yet (increment 7).
- `in_progress`: sets the active-lug pointer, same as
  `lug-lifecycle-tracker`.
- `done`: requires traceability evidence (a `// lug:` marker, an existing
  test-shaped `tests:` path naming the lug, or a lug-naming commit that
  touched a test file -- recorded as `traceability_evidence`) and real,
  measured (non-null) turn-marker cost -- computed from the track, not
  supplied by the caller, so a caller can't just claim a cost; with zero
  markers, the dispatch journal's wall clock (`kind: dispatch-measured`)
  or the `pre_attribution_flag` row. Writes an
  explicit `outcome_at_proofer` placeholder (default `"pending"`) since no
  real Proofer exists yet -- never silently marked `"certified"`.

On every authorized write, it records the lug's new checksum as the
baseline `lug-integrity-checksum` compares against at the next `Stop`.

## What it does not do

It is not a hook -- nothing forces an agent to use it over `Edit`/`Write`
or `Bash`. `bash-lug-guard` and `lug-integrity-checksum` are what make
*not* using it (via `Bash`) a dead end; `definition-complete-gate` and
friends still gate the `Edit`/`Write` path too. This verb is the clean,
single, correct way to change a lug's state -- the gates are what make the
alternatives either denied or reverted.
