# oversized-canon-write-guard

Lug `wcl-strands-the-operator-on-a-hygiene-rule-and-reports-one-violation-
at-a-time` (260911), defect 3. Rule 11 (no-oversized-file, 1000 o200k_base
tokens per canon file) was enforced only at compile. Four reference circle
docs were written over the cap by dispatched build sessions on 260909/10
and landed without a word; the operator met them a day later as a launch
refusal that named one of the four. The session that writes a file is the
one that can still trim it for meaning. This guard puts the check there.

## What it does

A PreToolUse hook on `Edit|Write`, on the same path `bash-lug-guard` and
`agent-target-scope-guard` already intercept writes. It reconstructs the
content the tool would produce (`resolveProposedContent`, hookIO.js),
decides whether the target is in rule 11's scope, counts it with the
compiler's own tokenizer, and refuses an over-cap write with the measured
count, the cap, the file, and the fix path in one line. Scope and measure
live in `src/compiler/oversizedWriteCheck.js`, which imports
`PER_FILE_TOKEN_CAP` from rule 11 and `countTokens` from
`src/compiler/tokenCount.js` -- one cap, one counter, never restated.

Scope follows the rule: a yaml file whose proposed content carries a
`kind:` document is an entity file (the same test `isNonCanonEntity`
applies), and each such document's `instructions_ref` target on disk is
measured too, so writing the yaml that first points at an oversized doc is
refused as well. Any other file is in scope only when a kind-bearing yaml
in the same directory names it as `instructions_ref`. A path under a
loader skip dir, or outside the session's cwd, is never checked.

The measure is rule 11's `measureCanonContent`. On a `kind: lug` document
it excludes the kernel verb's own bookkeeping -- `VERB_OWNED_LUG_FIELDS`
(`cost`, `outcome_at_proofer`, `pickup_reverification`,
`traceability_evidence`), declared once in the rule and read by this
guard, the compile rule and the verb, so the three cannot disagree. The
cap bounds what an author writes; the verb's appends at done (~114
tokens) had made 55 of 92 hub review lugs unable to reach done (lug
`done-transition-appends-push-near-cap-lugs-over-rule-11`). The list is
closed: a field joins it only when the verb is its sole writer, by grep.

A write that is over the cap but strictly smaller than what is on disk is
progress on an existing violation: it passes, with a `systemMessage`
saying it is still over. Refusing it would strand a trim the way the
launch refusal stranded the operator.

Every refusal is a ledger row (`source_ref: oversized-canon-write-guard`),
the shape the sibling guards write.

## Known, accepted gaps

Bash writes (heredocs, `tee`, `sed -i`) are not measured -- their content
is not knowable before they run; compile and the launcher's report remain
the backstop. A doc referenced by a yaml in another directory is not
caught at write time (no real instructions_ref does that today). The
instance root is the target's nearest repo root, not the session's cwd --
the four docs were written into harness-factory from wheel-hub-rooted
dispatches, so a cwd-rooted check would have missed the defect it exists
for; a target with no repo-root ancestor falls back to cwd.
