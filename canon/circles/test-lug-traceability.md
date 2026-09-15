# test-lug-traceability

Section 7: "A hook on test-file writes requires a lug id in test metadata."
The other direction from `lug-lifecycle-tracker`'s completion check: this
one runs when a test file is written, not when a lug is completed, so the
marker exists from the moment the test is created rather than being
retrofitted later.

## The convention

A test file must contain a `// lug: <name>` comment somewhere in it. No
particular position or format beyond that -- the marker just has to be
findable by `src/lugTracking/traceability.js`, which both this hook and
`lug-lifecycle-tracker`'s completion check use.
