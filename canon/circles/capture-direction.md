# capture-direction

Admission rule no-ledger (design doc section 3, ten admission rules table):
"Every direction becomes a ledger row with an owner when said." v1 lost 22
directions this way — said once in conversation, never written down anywhere
a later session could find.

## What counts as a direction

A standing rule, not a one-off question or task: "from now on...", "always
...", "never...", "whenever...", "each time...", "as a rule...", "by
default...". The same phrase family the `update-config` skill itself
triggers on. This is a deterministic, mechanical marker match — not a
judgment call about whether the user *meant* it as a standing rule — so it
can run as a plain command hook on every `UserPromptSubmit`, inside the same
turn, before Claude ever responds.

It will have false positives (a question that happens to contain "always")
and false negatives (a direction phrased without any marker). Both are
acceptable at this layer: capture-direction's job is to make sure a marked
direction is never lost to a transcript nobody re-reads, not to be the only
line of defense. `reconcile-ledger` is what turns a captured row into
something formalized in canon, and a human (or Wilbur) can always add a
missed direction to the ledger by hand.

## What this circle does not do

It never blocks the prompt — direction or not, the user's turn proceeds
exactly as it would have. It never decides whether the direction is *good*;
it only makes sure it's recorded, with attribution, in the turn it was said.

## What it stores (fixed 2026-08-27)

Only the directive sentence(s) — extracted via `extractDirective()` — not
the whole prompt. Before this fix, any prompt containing a marker phrase
became a single ledger row holding the *entire* prompt verbatim; a 40KB
work order that happened to contain "each phase" became a 40KB row, which
is what first tripped admission rule 12 (`no-oversized-session-start`).
`source_ref` carries a character-offset locator (`session:<id>#chars:N-M`)
back into the original prompt, so the full context is still recoverable
from the transcript without storing it in the ledger. Sentence splitting is
a heuristic, not a parser (same accepted tradeoff as `bash-lug-guard`'s
command-string matching); a hard safety-net truncation covers the
pathological case of no sentence punctuation at all.

Any row captured before this fix that turned out to be oversized (over 200
tokens) is marked `status: oversized-capture` by
`scripts/rescan-oversized-captures.js` — never deleted, so the original
content stays recoverable if it's ever needed, but flagged so it isn't
mistaken for a normal, terse direction row.
