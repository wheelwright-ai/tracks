# pattern-language

The operator, 260910: *"a common language to describe patterns and aspects
of its value and lift - every spoke could self describe its own design, then
the hub has a hub level for entire wheel and groups. its a memory of our
variation/mutation and evidence to prove the corrections/refactoring of
code."* Ruling 260911: **reuse, do not invent.**

## Four pieces that already existed

| Piece | Where | Used for |
|---|---|---|
| what/why/where shape | `canon/glossary.md` | the vocabulary is a section of it |
| level enum | `schemas/common.schema.json` | `spoke`, `group`, `wheel` on every record |
| lineage edges | `src/lugTracking/lugEdges.js` | a variant's `derived_from` |
| chain disposition | `src/advisor/chainDisposition.js` | a correction's evidence |

Nothing here is a fifth. The vocabulary is parsed out of the glossary
(`readPatternVocabulary`) and every term's pointer is resolved on disk
(`traceVocabulary`), so the glossary stays the one place a term is defined.

## Value and lift, separately

**Value** is purpose: what a thing is for and why this and not something
else. It is never a number.

**Lift** is measured improvement over a real baseline. Declared, it is a
`success_prediction` with `subject_kind: pattern`, registered through the
same gates every advisor's prediction passes — the mechanism that already
refuses a metric nobody can read, a target nothing could refute, a bar
already met, or a claim with no baseline. Not declared, it is **derived**
from the record: a pattern's distinct-subject success rate against every
other approach at its problem class; a spoke's dispatch completion rate,
later half against earlier half. Where the record supports no figure the
lift reads `unmeasured`. Zero is never substituted.

## Every figure says where it came from

`origin` is one of `declared | derived | asserted | unmeasured`, with a
provenance pointer. A self-description derives each design field from a
named repository file (profile, circles, advisors, policies, lug corpus,
patterns, git head) and marks anything from `local/design-assertions.json`
as asserted. The tally is the first thing printed — v1's failure was that
confirmed and asserted looked the same.

## The hub composes; the enum stays

`composeView` reads each registered spoke's own `generated/self-description.json`
(or describes it on read, and says so) into a `group` view over a group
entity's members or a `wheel` view over every `*.spoke.yaml`. `external:`
members are listed, never described. A level outside the enum is refused.

## Variation is lineage; correction is someone else's verdict

A variant carries `derived_from` and must state `variation` and
`variation_rationale`; without them it is a retry wearing a new name and is
refused — `checkRetry`'s rule at the library's other write. A correction
claim cites a chain whose disposition on disk reads `closed`, written by a
witness independent of the declarer; the declarer's own session as witness
is self-certification and is refused. On refusal nothing is written.

## It files nothing

Descriptions and views land under `generated/`; a ledger row reports them.
A lug is opened only for work someone owes.
