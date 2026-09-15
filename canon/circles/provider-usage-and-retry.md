# provider-usage-and-retry

Built by the lug `provider-contract-has-no-retry-backoff-or-usage-record`
(260908 design review, R7/E2#7). Full account, including what was left
unresolved:
`wheel-hub/docs/provider-contract-has-no-retry-backoff-or-usage-record.md`.

## Why this exists

On 2026-09-09 a `kimi` call made for a completeness review timed out.
There was no retry, so the review ran with ONE of its two intended
reviewers -- and nothing anywhere recorded that the second one had been
attempted. Afterwards a thin review was indistinguishable from a full one.

**A verification that silently ran with fewer reviewers than intended is
worse than one that failed loudly.**

## What it does

1. `src/advisor/providerUsageRecord.js` -- append-only
   `runtime/provider-usage.jsonl`, one row per attempt, including refusals,
   timeouts and ceiling blocks. `usageFromRaw` reads both real wire shapes
   (OpenAI-compatible, and the claude CLI's `usage`/`modelUsage`) and
   returns `null`, never zero, when the provider reported nothing.
   Deliberately NOT via `eventLog.js`: `appendEvent` refuses to write with
   no session triple, which is exactly the headless-verifier case.
2. `src/advisor/providerContract.js` -- `classifyHttpStatus` (429
   rate_limited, 401/403 auth, >=500 server, else http_error), bounded
   exponential backoff honouring `Retry-After`, same provider only, with
   `attempts` and `retry_history` on the result.
3. `src/navigator/nodeQuota.js` -- `computeProviderQuotaSignal` /
   `checkProviderCeiling`, additive, keeping that module's
   unmeasured-is-not-zero discipline.

## Left open on purpose

Acceptance says retry `rate_limited` and `server`; the incident was a
**timeout**. Acceptance is implemented as written and the disagreement is
one constant, `RETRY_ON_TIMEOUT` (false), with both sides argued beside
it. The record is not left open: every timeout writes a row either way.

## Ceilings

`canon/provider-ceilings.yaml` ships with an empty `providers:` map -- no
provider quota or price has been verified from real config here. An entry
with a number and no `source:` is refused, not enforced; an unmeasured
provider is never blocked.

## Proof

`conformance/fixtures/provider-usage-and-retry/` forces real failures
through the real `callProvider`, then reads the real file on disk: two
429s with `Retry-After` then success; an unrecoverable 500; a 401 that is
not retried; a real timeout from a fetch that hangs until the contract's
own `AbortController` aborts it; a sourced ceiling that blocks before any
request; an unsourced one that is refused. 63 checks.
