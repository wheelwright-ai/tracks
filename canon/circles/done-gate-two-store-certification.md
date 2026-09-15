# done-gate-two-store-certification

From wheel-hub's
`lugs/done-gate-ignores-a-proofer-pass-and-reads-only-the-external-chain.yaml`;
build record in that spoke's `docs/` page of the same name.

## The measured gap (wheel-hub, 2026-09-11)

56 lugs reached `review` in 7 days, 0 reached `done`. A non-author session
ran the Proofer on `cross-provider-gate-has-no-fallback-on-fabrication-or-
block`: VERDICT PASS, four verbatim citations, independent on every axis;
the verb moved it `review -> ready`, `readiness: passed`. Then `lug-verb
done` refused, reading ONLY the external record -- dashscope FABRICATED,
deepseek BLOCKED (no VERDICT line), kimi BLOCKED (timeout), gemini
FABRICATED. Two stores, one gate reading one of them. The drive's
`promote_to_done` then skipped the lug, because it looked only at `review`.

## The two stores

| Store | Written by | Read as |
| --- | --- | --- |
| `runtime/cross-provider-certifications/<lug>.json` | the external chain (`crossProviderCertify.js`) | `classifyExternalRecord`: satisfying / failed / stale / fabricated / blocked / refused / running / running_stale / required / absent |
| `ldg-verb-ready-proofer-<lug>-*` ledger row | the kernel verb, on a real Proofer PASS only | `readProoferPassRecord`: valid, or refused by name |

`usable` is true for exactly two external classes: satisfying and failed.
Everything else is "the outside voice said nothing that can be acted on",
which is a different fact from "the outside voice said no".

## The rule

| External | Proofer PASS | Result |
| --- | --- | --- |
| satisfying | any | done, `acted_on: external` |
| failed | valid | refused, BOTH named |
| running (fresh) | any | wait -- preferred second opinion is coming |
| absent / required | valid | held, not waived; the drive requests the chain |
| fabricated / blocked / refused / stale / running_stale | valid | done, `acted_on: proofer`, both verdicts recorded |
| any non-satisfying | none | refused, as before |

## Both verdicts, never one waived

On `acted_on: proofer` the verb writes one row naming the Proofer row and
every external attempt, and adds `superseded_by_proofer_pass` to the
external record. Its `verdict` stays `FABRICATED`. A reader sees both.

## What is NOT weakened

`independence.js` is untouched. The Proofer row now carries
`certifier_session` (the requester -- the identity self-attestation is
measured against) and `pointer_digest`; the gate re-checks both, plus
`enforceable` and carrying axes. Rows written before 260911 lack the two
fields and say so as a caveat. An author's own session is refused
`self_attestation` before any call is spent (fixture section D).

## Drive and metric

`nextInitiativeLug` ranks `ready` + `readiness: passed` first;
`driveInitiativeLug` promotes it through the same `promoteToDone` as
`review`. `review_to_done_lug_transitions_last_7d` counts the
`review -> ready(passed) -> done` exit; a plain `ready -> done` is not.

## Operator channel

`buildExternalChainSection` (src/advisor/externalChainChannel.js), on the
scheduler-failure-channel pattern: derived from the records, classes with
counts, announced once when the counts move (signature file), files
nothing. Terse by design: it rides the rule-12-capped wakeup.
