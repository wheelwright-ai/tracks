# chain-disposition

Summary. From wheel-hub's
`lugs/chain-scope-disposition-from-node-certifications.yaml`; **every
rule's *why* is in that spoke's `docs/` page of the same name.**

The cross-provider path certifies one lug. The redesign says a **chain**
carries a `disposition` written only by third-party verification, and an
independent review (gemini, 2026-09-09) found nothing said how node
verdicts become a chain verdict. This is that rule, over records that
already exist. **No provider is called, on any path** -- re-certifying
concatenated node content would be one fresh verdict in a chain's name.

## Per-node standing

`confirmed`/`plausible`; `negative` (FAILED); `inconclusive`
(REFUSED/BLOCKED/FABRICATED); `stale` (satisfying verdict, different
`pointer_digest`); and three uncertified kinds -- `uncertified_required`
(qualifies, at review/done, silent), `uncertified_pending` (pre-review),
`uncertified_exempt` (never obliged).

## Aggregation, in precedence order

- **`deprecated`** -- any unsuperseded `negative`. A FAILED node is
  superseded only by a CONFIRMED (never PLAUSIBLE) certification on a node
  deriving from it: the rule must not punish correction.
- **`seek_refresh`** -- no negative, but an obstruction
  (`required`/`pending`/`stale`/`inconclusive`) or no satisfying verdict.
- **`closed`** -- every obliged node satisfied, nothing stale or
  inconclusive, at least one real certification.

An **exempt** node contributes nothing: its silence as failure would make
a chain holding one pebble unclosable, and as evidence it would close a
chain with zero third-party verdicts -- hence the extra "one real
certification". An all-PLAUSIBLE chain closes at
`certification_strength: plausible`, never rounded up.

## Different providers across the chain

**Strengthens the evidence** -- independence is distance, not volume:
gemini + kimi + deepseek are three distinct witnesses, so no one
provider's blind spot carries the chain (2026-09-09: dashscope returned 8
FABRICATED verdicts in a row). **Complicates the verdict** -- they are not
commensurable; nothing calibrates a gemini PASS against a deepseek one. So
diversity is recorded, never an input: it never upgrades PLAUSIBLE,
rescues an uncertified node, or offsets a FAILED. `single_witness_chain`
flags the converse; it records, it does not gate.

## "Is it well tested" -- four axes, weakest link

Per axis, the **minimum over nodes obliged on that axis**, naming the node
that set it; obligation is state-scoped. Ladders weakest-first,
**threshold bold**:

- `tests`: untested, claimed, **tested**, traced -- a named-but-missing
  file is a claim, not a test.
- `readiness`: failed, not_run, stubbed, **passed** -- `stubbed` means the
  fresh-context check never ran.
- `proofer_outcome`: **none rejected; every `done` node certified**.
- `citation_binding`: unverified, structural, **normalized**, verbatim.

Four ladders, not one score -- four kinds of weak are not one number.
`well_tested: null` when nothing is obliged yet. **Never an input to the
disposition:** it is a repo fact an author can change.

## Third party only

Sharper failure first: (1) a witness session that authored or executed any
node -- authors from `author.session`, executors from the real
`lug_transition` events -- is `self_attestation`; (2) `independence.js`'s
four-axis check against every node's author record. A refusal writes
**nothing**.

## Retention, membership, running it

Never deletes: own store `runtime/chain-dispositions/<chain_id>.json`, no
lug file touched on any path, prior verdicts kept in `history[]`. A
deprecated chain stays readable and can be re-dispositioned. Membership:
`chain_id` when declared, else the `derived_from` closure around a lug of
that name, recorded as the weaker basis it is. Run `node
scripts/chain-disposition.js <chain-id>`; add `--write --session-id=<id>`
to gate and write.
