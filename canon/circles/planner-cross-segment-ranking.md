# planner-cross-segment-ranking

Built by lug `planner-ranks-initiative-work-first-then-allocates-remaining-
capacity` (260911). Closes `planner-conductor-impact-design.md` open
question 2 the way the operator decided it, verbatim: **"it should rank
against the initiative above the work first then allocate capacity to
complete non initiative work."** The comparable unit is not a price -- it
is initiative membership.

## What it does

`rankCrossSegment` (`src/planner/planner.js`), inside every `planner_cycle`
job, sorts build and maintain rows into ONE queue by these keys, in order:

1. **tier** -- `initiative` before `non_initiative`. A build row is in the
   initiative tier when a live AP-ready initiative's `lugs` names it
   (`initiativeLugIndex`); a maintain row when a live AP-ready initiative's
   `consumers` names its advisor (`initiativeAdvisorIndex`, e.g.
   `external:otto`). Roles that are not roster advisors (`external:planner`)
   affiliate nothing. IN-DESIGN initiatives affiliate nothing.
2. **initiative_rank** -- `initiativeSequenceRank`: 0 = free to drive; n =
   waits on an initiative of rank n-1. Waiting work is still initiative
   work; it ranks below what it waits on and above the non-initiative tier.
3. **kind** -- build before maintain. A declared convention inside a tier:
   there is still no unit that prices a lug against a runtime share.
4. inside build: operator-declared priority, then readyWork's own order;
   inside maintain: share, then the allocation's order.

Every row carries `rank`, `tier`, `initiative`, `initiative_rank`,
`waiting_on`, `sequencing_reason`, `ranking_basis`. The cycle carries
`cross_segment_ranking: ranked`, `cross_segment_ranking_rule:
initiative_membership_first`, and a `capacity` block: floors reserved off
the top, initiative-held maintain share, remaining maintain share, and
build slots as counts.

## What it deliberately does not do

- Price a build row. `share: null`, reason stated.
- Touch a share. Otto's floor is reserved in `computeAdvisorAllocation`
  before this runs; ranking reorders rows, never numbers.
- Re-rank across priority INSIDE a tier. Priority governs there.
- Guess who carries an initiative. The link is `initiative.consumers`; a
  dedicated `drives:` field would be a schema addition, not made here.
- Edit the prediction. `planner_cross_segment_ranking_ranked` was registered
  at a real baseline of 0; the live `runtime/planner-cycle.json` is what
  a third party reads.

## Consequence to know

Membership is first-order, so a medium initiative lug outranks a critical
orphan. That is the operator's rule, applied as stated. The within-tier
ranker `rankByInitiativePrecedence` still exists for callers that must not
cross a tier; Planner no longer calls it.
