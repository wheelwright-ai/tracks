# lug-write-schema-gate

Lug `push-gate-judges-a-snapshot-of-live-state-not-whatever-a-sibling-
session-is-writing` (260915), half B. Measured that day: 6 of 17
harness-factory pushes were refused by NEW REDs whose cause was a lug
ANOTHER session had written invalid and not yet fixed -- a hub lug missing
`out_of_scope` / `open_questions` / `author`, a re-filed pathfinder lug
with a string `derived_from` and an unquoted `type: communication` that
YAML read as a mapping. Each was fixed by hand in minutes once seen; each
was seen a 10-minute gate later, by somebody else. The session writing a
lug is the one that can fix it in seconds. This gate puts the check there.

## What it does

A PreToolUse hook on `Edit|Write|NotebookEdit`, on the same path the
other three lug-write guards (`definition-complete-gate`,
`ready-gate-stub`, `lug-lifecycle-tracker`) intercept. Those gate a lug's
STATE transitions; this one gates its SHAPE, at every state. It
reconstructs the content the tool would produce (`resolveProposedContent`,
hookIO.js) and validates it with `checkLugWrite`
(`src/compiler/lugWriteSchemaCheck.js`), which imports `buildAjv().lug`
from `src/compiler/schemaRegistry.js` -- rule 00's own validator over
`schemas/lug.schema.json`. There is no second schema to drift.

Scope is by PATH: a `.yaml`/`.yml` directly inside a `lugs/` directory
(never `lugs/docs/...`), wherever the session is rooted -- a hub lug
written from a harness-factory-rooted dispatch is checked exactly like one
written at home. A lug at `captured` is still a lug: the schema's required
set for its type applies (a pebble needs the core seven, a work lug the
full contract, a communication lug its payload and target).

The refusal is the fix: missing fields by name (`missing: out_of_scope,
open_questions`), mistyped ones by path and rule (`/derived_from must be
array`). Ajv's if/then bookkeeping lines are folded away. Unparseable
YAML and a non-mapping document are refused with the parser's own words.
Every refusal writes a `decision` ledger row, the sibling guards' shape.

## What it does not do

Bash writes (heredocs, `tee`, the kernel verb's own writes) are not
checked -- their content is not knowable before they run. Compile (rule
00) and the push gate's committed corpus snapshot (half A of the same lug,
`src/lugTracking/lugCorpus.js`) remain the backstop for those. It never
edits or truncates content, and it is silent on every path that is not a
deny -- an explicit allow would skip Claude Code's own permission flow.

## Return edge

`conformance/fixtures/gate-corpus-snapshot/gate-corpus-snapshot.conformance.test.js`
drives the hook as a real subprocess: a Write of a work lug missing
`out_of_scope` is refused with the field named; a valid pebble at
`captured` and a non-lug path pass through silent.
