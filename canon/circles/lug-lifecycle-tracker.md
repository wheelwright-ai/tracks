# lug-lifecycle-tracker

Section 7, the other half of the lug lifecycle machinery readiness-gate
doesn't cover:

- entering `in_progress` marks the lug as the active lug, so
  `stop-turn-marker` knows which lug the next turn's cost belongs to.
- entering `done` is denied unless the lug is traceable to a test and its
  own `cost` field is a real measurement. Traceability is any ONE of: a
  `// lug: <name>` marker in a test file; a path in the lug's `tests:`
  field that exists, is test-shaped (`conformance/` or `*.test.js`) and
  names the lug; a commit on a registered repo naming the lug that touched
  a test file. Cost is the sum of the turn markers recorded while the lug
  was active -- or, with zero markers, the journalled wall clock of the
  dispatch that built it (`{ kind: dispatch-measured, wall_time_seconds,
  dispatch_id }`, never a token count), or the `pre_attribution_flag`
  fallback. A lug with none of the evidence is refused, and the refusal
  names what is missing. Baseline: 4.9% of v1 lugs were traceable to a
  test, and 0 of 20 had a measurable cost; measured 260911, 27 fixture-green
  lugs were held by these two checks reading only the marker and the
  markers. The gate makes the numbers real; it never invents them.

Like readiness-gate, this never mutates the lug it's checking -- it only
decides whether the edit that would have marked it done is allowed through.
Getting the cost field right is the editor's job (yours, or an advisor's);
this hook's job is refusing to let a wrong or absent number slip by.
