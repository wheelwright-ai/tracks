# initiative-focus

Operator mandate, 2026-09-11, verbatim: *"arc's must get recorded as
initiatives that get focus to drive them to implementation to done. Work
with the user prioritizes clearing design needs but the agnet should then
be ready to implement in an AP. ... This behavior is harness wide mandate
for any spoke agent."*

Full build record: `wheel-hub/docs/initiatives-get-focus-and-drive-their-lugs-to-done-in-autopilot-build.md`.

## Why

Measured over the seven days to 2026-09-11: 56 lugs reached `review`,
**0 reached `done`**. Six initiatives existed in `canon/initiatives/`, each
valid, each naming its lugs and its open questions — and nothing read
them. All six success predictions were refused at registration for want
of a metric reader. Focus was the missing mechanism.

## The two states

`open_questions` is the whole of what the operator is asked.

- **IN-DESIGN** — non-empty. The goals review lists those questions
  verbatim and asks nothing else.
- **AP-READY** — empty. The autopilot picks the initiative's next lug and
  drives it one step per pass: `defined → ready` through the kernel verb;
  `ready →` a real dispatched build session (at most one per pass);
  `review →` certification requested out of process, or `done` through
  the verb once a CONFIRMED/PLAUSIBLE record exists.

## What is recorded

Every step lands in `runtime/initiative-focus.jsonl` (append-only) with
the initiative, the lug, from/to state, the action, the outcome
(`advanced | dispatched | requested | in_flight | blocked | refused |
missing`) and the reason — a gate's own words, a certification verdict —
plus a ledger twin. The session-start section reports counts. **No lug is
ever filed to report progress.**

## Sequencing, said plainly

`sequenced_after: [<initiative>]` on an initiative means it is not driven
until the named one has landed (every lug done). It is reported
**WAITING on <name>** with the prerequisite's own done count. `land-to-done`
is first on wheel-hub because until the backstop stops erasing review and
certification confirms more than 1 in 38, nothing can reach done — and a
report saying the others were driving would be the overstatement this
mandate exists to end.

## Planner

`rankByInitiativePrecedence`: inside one priority tier, a lug an AP-ready
initiative names sorts ahead of an unaffiliated one, and the build row
carries `initiative`. Priority is operator-declared and is never re-ranked
across tiers.

## Readers

Six readers in `METRIC_READERS`, one per initiative metric, each reading
the real store it names (event log, wave records joined to the dispatch
registry's work disposition, certification store, lug corpus, prediction
registry). Each returns `measured:false` with the reason when its store
cannot answer. Domains are measured operating ranges, stated in
`domain_basis`.

## Entry points

`src/conductor/initiativeFocus.js`; `buildInitiativeFocusSection` on
`goalsReview.js`; `driveApReadyInitiatives` from `runAdvisorAutopilot`.
