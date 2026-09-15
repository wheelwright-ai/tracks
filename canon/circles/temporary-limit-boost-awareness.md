# temporary-limit-boost-awareness

lugs/navigator-and-conductor-blind-to-temporary-limit-boosts.yaml (260909).

## Why this exists

The operator's client read "Your weekly Claude Code limit is 50% higher
through September 13" while a grep of `src/conductor` and `src/navigator`
for boost/promotional returned zero hits. A temporary ceiling increase was
invisible to every routing and pacing decision this build makes.

## The finding that shaped it

The lug expected the boost in the usage endpoint's `limits[]`, which
`normalizeUsage` was discarding. **It is not there.** A real
`GET /api/oauth/usage` taken 2026-09-09 *while the boost was live* carries
no boost, multiplier or promotional expiry anywhere: `limits[]` is genuine
ceiling metadata (`kind`/`group`/`percent`/`severity`/`resets_at`/`scope`/
`is_active`) that says which ceilings exist and how full each is, never that
one is raised; and the payload's one promotional-shaped slot,
`omelette_promotional`, is `null` on the boosted account. Every percentage
is reported against the current ceiling without saying whether that ceiling
is the base one. See `docs/limit-boost-data-source-investigation.md`.

The boost is real elsewhere: Claude Code's own `.claude.json` carries
`cachedGrowthBookFeatures.tengu_rate_limit_promo_notices` — the exact
sentence the operator quotes — naming the bar (`seven_day`), with
`cachedGrowthBookFeaturesAt` giving it a real age.

## What it does

`src/otto/limitBoost.js`

1. `readPromoNotices` reads the first readable flag cache, `CLAUDE_CONFIG_DIR`
   before `$HOME` (the project-scoped copy is the one kept refreshed).
2. `parsePromoNotice` extracts magnitude and expiry only on a strict match
   against the notice's own words. No match → nulls plus a reason. The year
   and timezone the text omits are resolved by a disclosed rule and reported
   as `expiry_precision: "day"` with the assumptions attached.
3. `detectLimitBoost` returns the fact: `announced`, `lapsed`, `absent` or
   `unknown`, never merged, with the notice text verbatim.
4. `boostExpiryAlert` raises `boost_expiring` on the *earlier* expiry bound,
   and `boost_expiry_unknown` for a live boost whose end cannot be read.

`src/conductor/paceModel.js` — `boostAwareLeftPct` rescales nothing. A boost
adds a second deadline (raised headroom unspent by expiry is lost), so the
runway is measured to `min(window reset, conservative expiry)`. The same
quota over a shorter runway is a higher sustainable speed, straight out of
the unchanged `paceRatioX10`.

`src/conductor/heartbeat.js` reads the fact every tick — recording `absent`
and `unknown` too, so the wave record can show the wheel *looked* — passes it
to `paceFromReading`, and appends an actionable expiry signal to every
outcome, launches and declines alike.

## The two refusals

- **Never `five_hour`.** A notice naming the five-hour bar is refused and the
  refusal disclosed. That window is the wheel's safety floor and this circle
  may not weaken it to buy speed.
- **Never a maybe.** Only `announced` changes pacing; `unknown`, `absent` and
  `lapsed` leave every figure bit-identical to the pre-boost behaviour.

## Known limits

Expiry is day-resolution, from prose. The magnitude (`+50%`) is recorded but
**not** used in any arithmetic — nothing states whether reported utilization
is against the base or the raised ceiling, so applying it would be invention.
Only the first notice is modelled; further ones ride in `other_notices`.

Conformance:
`conformance/fixtures/limit-boost-awareness/limit-boost-awareness.conformance.test.js`
(47 checks, incl. the honest non-effect on the real 2026-09-09 numbers).
