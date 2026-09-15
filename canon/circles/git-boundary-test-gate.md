# git-boundary-test-gate

A tiered test gate at the real git boundary, in both repos. Absorbed from
mywheel's `.githooks/pre-commit`, `.githooks/pre-push` and
`WAI-Harness/kernel/proof.py`.

## Why it exists

The installed `pre-commit` hook ran a lug-schema check and a secret scan;
neither runs a test. There was no `pre-push` hook at all. The only thing in
the build that consulted a test result was `sessionExitCommit.js`, and it
reads a *cached* `runtime/last-test-run.json` at SessionEnd — so a
mid-session or headless `git push` shipped a red tree with nothing
mechanical anywhere in the path.

## The three tiers

**Commit — changed scope.** The covering suites for the staged set only.
The full sweep is 1107s measured; paying that per commit teaches
`--no-verify`, and a gate people routinely bypass protects nothing. Scope
is computed from the real import graph (reverse-reachability from a changed
file to the suites that reach it), plus a text match for non-JS inputs such
as canon YAML and lug files. Suites run most-specific-first inside a 90s
wall budget; suites the budget does not reach are named and **deferred to
the push gate**, never reported as passed.

**Push — the full suite plus a failure ratchet.** Every suite, no
fail-fast: the ratchet needs the whole failure set, because a single-failure
view lets a new failure hide behind a baselined one. A failure already in
`runtime/test-ratchet.json` is printed and does not block; one that is not
is NEW and blocks. The baseline may only shrink. This is what makes a gate
possible on a tree that is honestly red — and this one is.

**Receipt — an unchanged suite does not run again.**
`runtime/test-proofs.json` holds, per suite set, the content hash of the
paths it covers. The push gate keys on HEAD; the commit gate keys on the
index, because staged files are dirty relative to HEAD by definition and a
HEAD-keyed commit receipt could never fire. Either way the tests run on the
working tree, so a receipt is neither read nor written while the covered
scope is dirty. **Absence is not a pass**: no receipt, an unreadable store
or an unobtainable hash all run the suite. A skip is noisy on purpose — it
names the suite set, the tree and when the proof was taken.

## Bypass

`WHEEL_SKIP_TEST_GATE=<reason> git commit|push`. It prints loudly and
writes a ledger row naming the gate and the reason. There is no other way
past it short of `--no-verify`.

## Bounds

Per-suite 600s (~4.6x the measured 130.8s slowest suite), commit budget
90s, push budget 3600s (~3.3x the measured 1107s sweep of 178 suites).
Measured on 2026-09-08, not guessed — an undersized bound is the specific
bug mywheel's own hook records twice, and the first draft of this gate
reintroduced it by guessing 33.1s for a suite that really takes 130.8s.
