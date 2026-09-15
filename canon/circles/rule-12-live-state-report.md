# rule-12-live-state-report

Lug: `rule-12-measures-live-runtime-state-so-the-hub-compile-verdict-flips-hourly`.

## The failure, measured

Rule 12 measured the real SessionStart injection -- right -- but half of
that injection is built from live runtime and ledger state: unacknowledged
upkeep misses, footer misses, vetoable default-forward acts, unannounced
exit-commit rows, the dispatch's active-lug pointer, every initiative's
drive state. One unchanged hub canon compiled at 3517, OK, 2409 and OK
tokens on 260911; 2740, 2963, 2392 against the 2300 cap on 260912, minutes
apart. Every gate that asserts "the hub compiles clean" (commit, push,
wilbur-a1/a2/a3, onepassword-secrets, lug-lifecycle-companion, the
launcher) inherited the coin flip. The cap was right; calling a moving
measurement a canon verdict was the defect.

## The split

`src/lugTracking/injectionDerivation.js` gives every injected block a
declared derivation, at its composer:

- CANON -- a pure function of the compiled tree: the backlog summary,
  the governance prompt (compiled from policy), the routing plan /
  closest-blocked lug (lugs + the profile's own `goals_review_top_n`),
  and the merged tastegraph block once it lands.
- LIVE -- read from `runtime/` or `ledger/`: the handoff, the active-lug
  block, the precompact notice, and every goals-review section after the
  routing plan.

`buildCheckpointInjectionParts` and `buildGoalsReviewInjectionParts` are
the parts views of the same two composers the hooks call; the hooks get
`joinParts(...)`, so injected text and measured text are one string.

Rule 12 (`run`) refuses on the canon sum only. Its `warn` half (in
`WARN_RULES`) reports the whole injection when it is over the cap: total,
canon/live split, each live section's number, and how to shrink it.
`printCompileResult` now prints warnings after the verdict line; applyCut
carries them into `.cut-status.json` as `warnings`. Rule 12 stays
report-class for wcl and the cut path.

## Count caps

Every live-growing section has a declared cap with a `+N more, see
<store>` tail. New on 260912: initiatives (AP-READY 3, driving first;
IN-DESIGN questions 3). Already declared: reference aging 2, upkeep
misses 1, footer misses 1 (count stated), exit commits 2, vetoable acts
1, advisor-run-loss causes 1, scheduler classes 5, cut laggards 5.

## The acknowledge path

`node scripts/acknowledge-live-state.js status` prints the three open
counts. `upkeep-miss | footer-miss | vetoable-act (<id>... | --all |
--before=<ISO>) --reason=<why> [--by=<who>]` acknowledges: a ledger row
moves captured -> acknowledged with `acknowledged_at/by` and
`acknowledge_reason` (one locked rewrite for the batch,
`updateRowsStatus`); an open act settles KEPT through `settleDecisions`
with the reason in `outcome`. One `decision` ledger row records each
call. Nothing is deleted; no reason, no acknowledgement (exit 1).

## Proof

`conformance/fixtures/rule-12-live-state-reported-not-refused/`: fixed/
is wheel-hub's 260912 backlog (553 / 78 / 43 rows, through the real
writers) against a small canon -- BUILD OK, under the cap with the caps;
a wider day is over the cap, still OK, warning names every section;
broken/ overflows on canon alone (top-N 100 x 100 ready lugs) and refuses.
The canon number is byte-identical across live-state changes.
