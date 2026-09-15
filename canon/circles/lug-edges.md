# lug-edges

Two edge kinds on a lug, **deliberately not merged**. Settled design:
`wheel-hub/docs/settled-decisions-lug-redesign-and-spec-vocabulary.md`
Part 2. Full build record, with the worked merge example:
`wheel-hub/docs/lug-lineage-and-association-edges.md`.

## Lineage — one stored direction

`derived_from`, on the **child**, naming its parent(s). That is the only
lineage field. `refines_into` is **derived by index, never stored**: two
stored directions can disagree, and after that neither is trustworthy.

Mechanical, not documentary. Eleven downstream field names
(`refines_into`, `children`, `verified_by`, …) are refused by the
schema's own `not: { required: [...] }` block *and* by `checkLugEdges`
at the kernel verb; the fixture asserts the two lists match. It has to be
mechanical because the failure is silent — nothing breaks the day a
second direction is added, only the day the two disagree.

Two authored forms, normalized in one place (`lineageEdgesOf`): a bare
name means `refinement`; `{ parent, relation }` says otherwise.
`verification` is a **lineage** relation, so "every verification of this"
is a plain downstream traversal, not a second index. The relation sits on
the **edge**, so one node can be a refinement of one parent and a
verification of another. No `merge` relation — a merge *is* >1 parent.

Both pre-existing consumers (`chainDisposition.resolveChain`,
`pickupReverification.dependencyRefs`) were written against bare strings
and now **import** the normalizer; a stale local `String(x)` yields
`"[object Object]"` and silently drops a whole lineage.

## Association — evidence or nothing

`relates_to: [{ target, relation, evidence }]`, `relation` one of eight
settled words. **Evidence is required**, as a provenance pointer
(`{source_type, source_ref}`) and never prose — prose is how "they feel
related" passes an evidence check. A pointer addressing nothing (`n/a`,
`TBD`) is refused.

Non-directional: edges read from **both** sides, always carrying
`asserted_by`. When both sides assert and *disagree*, that is
**reported** — refusing the second claim would discard real,
separately-evidenced work.

## Chain identity

`chain_id` is stored, minted at first refinement, inherited after —
chosen over deriving from a root because a merged chain (an Aggregate
Topic) **has no single root**.

A merge resolves by **union, never rewriting**. Lineage-connected nodes
form one component; its alias set is every `chain_id` its nodes declare;
the canonical id is the smallest alias — deterministic so two readers
agree, not a claim the smaller id matters more, and always reported with
the full alias set. Nothing on disk is rewritten, so **every pre-merge id
stays a live address for the whole merged chain**. That is "keep one
coherent chain_id rather than lose one lineage".

An invented `chain_id` is refused, checked against **ancestors** — a
component already contains the invented id, so a component-wide check
would pass everything.

## consumers and duplicate_of — stated, not ambiguous

`consumers` is **unchanged** and is not an edge: a canon-entity concept,
declared-but-unenforced for lugs (rules 07/09 gate on
`circle|artifact`), and neither the derived downstream direction nor
`relates_to: dependency`.

`duplicate_of` is **unchanged** and outranks the new edges. It is a
**fact**; `supersession_candidate` is a **hypothesis**. A candidate
restating an existing `duplicate_of` is refused, nothing promotes a
candidate automatically, and `duplicate_of` is never migrated into
`derived_from` — a duplicate does not *derive* from its original, it *is*
the original filed twice, and putting it in the DAG would inflate every
chain by the number of duplicates.

## Scope

The verb's check is single-lug plus a targeted read of the parents it
names — **not** a corpus walk, which at 2,714 files per transition would
be slow enough to route around. Corpus-scope checks live in
`node scripts/lug-edges.js audit`, which exits non-zero so it can gate.

Zero migration, measured: 0 of 2,714 real lugs carry any edge field.
