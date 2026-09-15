# cartographer

Spoke-understanding prompt, Part A: "what does the user gain from Ozi
being in the spoke at all, and how does Ozi get the spoke rolling?...
Ozi understands the spoke."

## What it does

Produces the spoke's map (`src/cartographer/builtinScan.js`,
`src/cartographer/index.js`): areas, entry points, the mapping from every
circle/policy/advisor to its real implementing file(s) (read from fields
those entities already declare -- `hook_script`, `conformance`,
`instructions_ref` -- or parsed from the conformance test's own imports,
never guessed), the test-to-lug index (the existing `// lug: <name>`
convention), a content hash per mapped file, and what changed since the
last map. Written to `runtime/cartographer-map.json`, read only through
`readCartographerMap()`.

Renders two index tiers, not one, because rule 12's existing token cap
had almost no headroom left once real content already filled it: a terse
`buildWakeupIndex()` (areas + counts + what changed, under 100 tokens)
injected at wakeup, and a fuller `buildLocationIndex()` (every circle and
policy's real path) handed to the Proofer and the stranger test, both of
which read it directly rather than through the SessionStart hook budget.

## Engine

Chosen by real, live comparison against `gitnexus` (v1's tool), not
assumed -- see `docs/DESIGN_INPUTS_REGISTER.md`. The built-in scan won on
time-to-produce (sub-50ms vs. 14-33s), size (KB vs. 405MB combined), and
determinism (reads declared fields vs. ranked search), while tying on
completeness. GitNexus stays available as an on-demand MCP tool for
call-graph questions the map doesn't answer; it is not the map's
producer.

## What it does not do

It does not guess at "why" a file exists -- only where. Area purposes
(`AREA_PURPOSES` in `builtinScan.js`) are authored, disclosed as such, not
extracted from file contents; there is no reliable existing convention to
extract them from. It does not hash every file in the repo -- only files
the map itself references, matching the "small, diffable" requirement.
