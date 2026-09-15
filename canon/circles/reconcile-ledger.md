# reconcile-ledger

Design doc section 9: "The captured -> built loop is a hub circle
(reconcile-ledger) that runs on a schedule and proposes status moves."

## What it does

Reads every ledger row with `row_kind: direction` and `status: captured`,
and for each one asks: does a live canon entity already say this? If a
live Policy's `rule` (or another entity's comparable text) shares enough
vocabulary with the row's text, the row is proposed `resolved`, pointing at
the entity that already formalizes it. If nothing does, the row is proposed
`routed`, pointing at a new `lug:` name to formalize it.

## What it does not do

It never mutates the ledger. It returns proposals; something with the
authority to accept them — Otto, or a human via Wilbur — applies them.
This matches every other propose-then-accept loop in the design (autonomy
table promotions, cut distribution): nothing here silently rewrites what was
said. The similarity check itself is a blunt word-overlap heuristic, not
semantic understanding — good enough to catch "this was already turned into
a policy verbatim," not good enough to catch a direction that says the same
thing in different words. That gap is exactly why a human stays in the loop.

## Counter-metrics (ruling 2026-08-26)

Both `capture-direction`'s regex and this circle's overlap-dedup match are
heuristics accepted as stages, not as ground truth -- so their error rate
has to be visible, not assumed. Every run, `runReconcileLedger` computes and
writes two rates as new `decision` rows (never mutating an existing row --
this is the same additive-only exception `capture-direction` itself uses):

- `direction_regex_false_positive_rate` — of ledger rows the regex marked as
  a direction and that have since been reviewed (resolved, routed, or
  rejected), what fraction were rejected as not actually a standing rule.
- `overlap_dedup_false_positive_rate` — of directions the overlap matcher
  proposed `resolved` against an existing entity, what fraction a human
  rejected as the wrong match.

Rows still sitting at `captured` haven't been judged yet and are excluded
from both denominators — an unreviewed row is neither a true nor a false
positive, it's just not reviewed.
