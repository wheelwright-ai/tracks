# cross-provider-verification

From wheel-hub's
`lugs/cross-provider-verification-for-high-priority-proof-required-lugs.yaml`
(build record in that spoke's `docs/`, same name). Matcher tiers and the
verdict policy: `docs/fabrication-matcher-tiers.md`.

`callProvider` and the independence check were real and nothing invoked
them: work reached `review` with `proof_required: true` and got no second
opinion. Non-Claude providers exist so we *"don't fall for sweet words"*.

## What fires, and when

| Moment | Who | What |
| --- | --- | --- |
| enters `review` | `lug-kernel-verb` | writes a `required` record + ledger row, sync, no call |
| enters `review` | PostToolUse hook | spawns `scripts/cross-provider-certify.js` detached |
| promoted to `done` | `lug-kernel-verb` | reads this record AND the Proofer's own row -- see `done-gate-two-store-certification` |

## Scope and certifier

`priority: high|critical` **and** `proof_required: true` (operator
ruling). `selectIndependentCandidates` walks the Proofer advisor's
`cross_provider_candidates` in declared order, returning every
independent one; a candidate matching the author's provider is rejected.

## Citations: the matcher's tiers

Every citation is a substring test against real bundle text; a tier only
deletes or re-encodes layout on BOTH sides, so none matches text absent
from the bundle. Weakest last, each named on the record with the bundle
path:line it bound to (`citation_binding.matches[].location`):
verbatim; normalized; structural; ellipsis; quote_normalised;
**prefix** (a runner's `PASS|FAIL|SKIP|ok|INFO|check(` stripped);
**bundler_line** (`=== ... ===` headers, `TEST OUTPUTS: []`, POINTERS NOT
INCLUDED lines -- the bundler wrote them); **yaml_json** (`"k": "v"` <->
`k: v`, `- item`, `k: >-` folded); **multi_line** (joined code =
consecutive CODE lines of one section, comments left out, at most
`MAX_MULTILINE_SPAN_LINES` = 24; a skipped code line is a splice and
refuses); unpinned (a bundle gap, named).

## Verdict policy

A rejected citation carries its nearest bundle window (trigram
similarity). FABRICATED iff any rejected citation has NO near match
(similarity < 0.5) OR the rejected are >= a third of all citations.
Otherwise the PASS stands as PLAUSIBLE -- never CONFIRMED -- with
`unverifiable_citations: [{quote, nearest: {path, line}, similarity}]` on
the record and in the reason line. CONFIRMED needs zero rejected and a
carrying independence axis. FAILED, FABRICATED, REFUSED, BLOCKED block,
reason named; all but FAILED yield to a real Proofer PASS. A near-miss
PASS never flips readiness. Every record and attempt carries
`matcher_version` (hash of tier table + policy constants);
`scripts/certification-replay.js <lug> [--run=<n>] [--summary]` replays
any attempt today and prints `judged by <v> (current <v>)`; the readiness
sweep re-runs stale citation verdicts.

## Exhausting the candidate list

2026-09-09: `dashscope` alone answered 8 FABRICATED; nothing tried the
rest, 0 of 87 certified.

| Outcome | Next |
| --- | --- |
| CONFIRMED/PLAUSIBLE, FAILED | chain stops (a real negative is an answer) |
| FABRICATED, or BLOCKED candidate-attributable | next candidate |
| BLOCKED instance-attributable, REFUSED | chain stops |

Never silent: each attempt gets its `attempts[]` entry, ledger row and
event; on exhaustion FABRICATED outranks BLOCKED as headline.
`--provider=<name>` is one call. Proved by
`conformance/fixtures/cross-provider-fallback/` and
`fabrication-matcher-tiers/`.

## Running it

`node scripts/cross-provider-certify.js <lug> [--provider=<name>]`, or
`--status`. The record is written `running` with `started_at` before the
call (older than 15 minutes: a named block); records land in
`runtime/cross-provider-certifications/`; exit 0 only when the verdict
opens the done gate.
