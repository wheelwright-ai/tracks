# lug-type-lifecycles

Every one of the four settled lug types carries its own state lifecycle,
and `state` on a lug is refused outside it. Settled design:
`wheel-hub/docs/settled-decisions-lug-redesign-and-spec-vocabulary.md`
Part 2. Build record:
`wheel-hub/docs/notice-and-remember-lug-types-have-no-lifecycle.md`.

## The four lifecycles

| type | lifecycle | reset target |
|---|---|---|
| `work` | captured → defined → ready → in_progress → review → done, plus `returned` | `defined` |
| `pebble` | captured → discussed → hypothesis → experiment → active; terminals incubated / extracted / composted / superseded | `captured` |
| `notice` | posted → acknowledged → retired | `posted` |
| `remember` | active → superseded | `active` |

`notice` and `remember` were settled by operator ruling on 2026-09-11:
*"indicate its lug-type and give them respective workflows/state to
understand how refined/complete it is."* Before that ruling the schema
held both to the union of every state, so a notice could sit at
`in_progress` and a remembered fact could reach `done` — neither of
which means anything. They are deliberately minimal: a state nobody will
set is the failure mode, not the missing one.

- **notice** — `posted`: issued, the audience has not yet discharged it.
  `acknowledged`: its inheritors have. `retired`: it no longer applies,
  reachable from either (a notice can be withdrawn unacknowledged).
- **remember** — `active`: the fact stands. `superseded`: it was replaced.
  A fact does not progress. Same word pebble uses for the same meaning.

## Where it is enforced

- `src/lugTracking/lugType.js` — `STATES_BY_TYPE`, `statesForType`,
  `statesForLug`, `resetStateForLug`. The single place the lifecycle is
  read from; nothing outside re-derives it.
- `schemas/lug.schema.json` — the `state` union plus one per-type
  narrowing block for **all four** types.
- `applyLugVerb` refuses a transition outside the lug's own lifecycle,
  naming the type, before any other gate runs.
- `lug-integrity-checksum` heals an out-of-band edit to the entry state
  of the lug's own lifecycle.

## What the fixture proves

`conformance/fixtures/lug-type-lifecycles/`: per type, every settled
state valid and every other state refused (schema); the verb moving each
lifecycle and refusing a foreign state, `work → returned` included; the
real hook healing a notice to `posted` and a remember to `active`;
schema block == module list per type, union == set of claimed states;
every real lug on disk still validates; the settled record carries the
ruling. Sibling-repo checks fail loud, never skip.

## Reopen trigger

A real notice or remember lug whose refinement cannot be expressed in
these states. Add a state only with a real instance that needs it.
