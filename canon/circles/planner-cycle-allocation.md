# planner-cycle-allocation

Planner: the advisor kind `canon/initiatives/planner-conductor-impact-design.md`
settled 2026-09-03, which shipped code depended on before it existed.
Built by lug `build-planner-advisor-kind` (260909).

## What it does

`src/planner/planner.js`, fired by the `planner_cycle` wheel_clock job,
computes this cycle's real budget allocation across the spoke's advisor
roster and writes `runtime/planner-cycle.json`. Real arithmetic over real
history, checkable by hand:

1. Read every `canon/*.advisor.yaml`. A file that will not parse is a
   refusal -- no shares at all.
2. Allocatable = `status: live` and a real positive `autopilot_budget_ms`
   -- the rule `advisorAutopilot.js` already enforces at dispatch, so an
   advisor that could not spend a share is never handed one. Every
   exclusion is named.
3. Every declared `guaranteed_runtime_share.fraction_of_wheel_runtime` is
   reserved off the top, before weighting.
4. `even = total_at_bats / allocatable_count`; `deficit_i = max(0, even -
   at_bat_i)`. At-bats come from `readAdvisorDispatchRows` (MAX-072's
   `recordOutcome` stream, the only real per-advisor history), deduplicated
   by row id.
5. The remainder splits by deficit share; with no deficits it splits
   evenly, since a deficit weighting with no deficits has nothing to say.
6. `share_i = floor_i + weighted_i`, then floors are asserted again.

It emits one queue of **maintain** rows (one per allocatable advisor,
priced) and **build** rows (real `buildReadyWorkQueue` output, ordered,
`share: null`). A spoke with zero ready build work still gets a non-empty
queue -- that is the point.

## Why counts, and only counts

The design record leaves four questions open for the operator: P0-P4
definitions, the comparable impact unit, demand-factor inputs, and
pacing/earmarks. "Who has been to bat, how often" is a count and needs
none of them. Anything richer is exactly what those questions are about
and is not invented here.

## What it deliberately does not do

**Price a build row.** Ranking a lug against an advisor finding is open
question 2, so the queue declares `cross_segment_ranking: "not_ranked"`
and its order is a stated convention (build rows first, having cleared
`readyWork.js`'s bar), not a computed comparison.

**Make the LLM judgment call.** No model call anywhere in `planner.js`.

**Gate activation.** `dueForActivation` still decides who is due and
`advisorAutopilot.js` who is dispatched. A zero share is reported by name
in `zero_share_advisors`, never used to drop an advisor.

**Enforce a minimum participation share.** Pure deficit weighting can
leave an advisor at its floor; that self-corrects across cycles and is
reported. A declared minimum would be an operator number, adjacent to
open question 4.

## Ordering: real, and honestly fragile

`tickWheelScheduler` iterates `Object.entries(wheelClock.jobs)` in the
canon file's YAML key order, so declaring `planner_cycle` first suffices
today. The design record disclosed this as an accident of parsing, not a
contract, and named a real `order:` field as worth having once more than
one job depends on sequencing. That is now the case; the field is not
added here (a scheduler change with every job to re-verify) and is named
in the build record rather than assumed solved.

## Circle of value and ownership

Every data point: gatherer, consumer, age past which it is not trusted.
Gatherer: this circle, every tick. Consumer: `waveDecision.js`
`buildWakeGuidance`, read-only, never triggering a cycle by looking. Age:
`PLANNER_MAX_AGE_MS`, the five-hour window (`FIVE_HOUR_SECS` from
`paceModel.js`, not a second number); past it a reader reports
`state: "stale"`.

## Counter-metric

`advisor_at_bat_evenness`: the spread of real at-bat counts across the
allocatable roster. Planner's job is to shrink it; a spread that does not
shrink across cycles means the allocation is not reaching dispatch.
