# cartographer-commit-trigger

Lug `wire-cartographer-map-to-commit-trigger` (wheel-hub/lugs), closed
260901-FBL-066 item 5: "the operator's original Cartographer request said
the map regenerates on commit and on the scheduler; only the scheduler
half was ever wired." This circle is the commit half.

## What it does

Bound to `PostToolUse`, matcher `"Bash"` -- fires after every real Bash
call completes. Matches `tool_input.command` against a real `git commit`
pattern; anything else is silent. On a match, reads the just-made
commit's real changed files (`git diff-tree --no-commit-id --name-only -r
HEAD`, run in the commit's own repo) and checks whether any of them fall
under `reference/circles/`, `canon/policies/`, `canon/*.advisor.yaml`, or
`src/compiler/rules/` -- the Cartographer's own real inputs
(reference/circles/cartographer.yaml). Only then does it call the same
producer the scheduler already uses (`regenerateCartographerMap`,
`src/cartographer/index.js`), targeting wheel-hub's own map with
harness-factory as the framework root -- the resolved lug's own scope
("this only needs to fire for commits IN harness-factory... a
wheel-hub-only commit doesn't change the map's own inputs").

Logs the same way the scheduler's own regeneration already does (a
`lug`-kind ledger row, `attribution: cartographer-commit-trigger`) --
written into **wheel-hub's own ledger**, since the regenerated artifact
is wheel-hub's, per 260901-FBL-066 ruling 1's destinations-by-ownership
principle.

## What it deliberately skips

A commit that fails, or one whose diff doesn't touch a Cartographer
input path, never regenerates -- the lug's own acceptance criterion 3.
Never blocks the commit itself: this is PostToolUse, after the tool
already ran, and any failure inside this hook is swallowed the same
non-blocking way every other hook in this build handles its own errors.
