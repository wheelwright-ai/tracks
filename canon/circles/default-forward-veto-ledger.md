# default-forward-veto-ledger

The half of "proceed without asking" that protects the operator.

## What it is

`src/ledger/defaultForwardDecisions.js` writes one append-only file,
`runtime/decisions.jsonl`, tracked in git. One line per act this harness
took without asking, each carrying:

- **what happened** (`act`)
- **how to undo it** (`rollback`, plus `rollback_source`: `caller` when
  someone declared it, `default` when the call site's standing text
  applied)
- **the smallest real target that could disprove it** (`canary_scope`)
- **until when one word still undoes it** (`veto_window_ends`, 24h by
  default, tunable per instance via `canon/profile.yaml`'s
  `veto_window_hours`)

`recordDefaultForwardAct` **refuses** — throws, writes nothing, leaves a
ledger row naming the refusal — when either is empty. The refusal is the
mechanism, not a guard rail around it: an act with no way back is not a
default-forward decision, it is the class the operator reserves for
themself, and recording it would launder it as covered.

## Prior art, and why a file

Ported from mywheel's `kernel/decisions.py` (operator ruling R2, ratified
2026-08-12), read for the mechanism and rebuilt fresh against this
build's schema and conventions — nothing imported from the archived tree.
A file, not a service, for that module's own reason: it is read by a human
under time pressure to answer one question — what did this do while I was
not looking, and can I take it back. A jsonl file answers that with `tail`
and survives every failure mode the harness has. Tracked in git
deliberately: a veto record a clean checkout erases is not a record.

## Where it fires today

`src/lugTracking/dispatchMechanism.js`. Queueing a dispatch is this
build's most expensive default-forward act: a real, billed builder
session, in a real repo, with nobody at the keyboard.

- `queueDispatch` records the act **before** the registry row. Absent a
  caller-supplied `rollback`/`canaryScope`, the standing default applies
  (kill-switch while queued; `git revert` plus `lug-verb.js` once landed)
  marked `rollback_source: "default"`. An **empty** rollback is refused,
  and no registry row is written.
- `executeDispatch` records one for any row that reached it without going
  through `queueDispatch` — the back door closed.
- A dispatch that never launched settles `void` with the real reason. One
  that ran and failed stays `acted` and vetoable: a half-finished session
  leaves commits behind.

## Where the operator sees it

`buildOpenDefaultForwardSection` is composed into
`buildFullGoalsReviewInjection` (`src/conductor/goalsReview.js`), so open
acts land in the same real SessionStart injection warmup-goals-review
already makes, with the rollback printed verbatim and the decision id
beside it. Silent when nothing is open; capped at the most recent three
(the act line is abbreviated, the rollback never is) with the full count
always stated so a cap never hides how many there are.

## What it does not do

It never runs a rollback. `vetoDecision` marks the entry and hands back
the rollback text; the operator runs it. That boundary is the lug's own
`out_of_scope` and is deliberate — a ledger that undoes things on its own
is a second autonomous actor, which is the problem, not the fix.

## Known gaps, disclosed

**One.** Only the dispatch path is wired. The lug's own acceptance also names
`sessionExitCommit.js`, `arrivalAudit.js`'s auto-commit and `applyCut` as
default-forward acts that should record here; they do not yet. Tracked in
`docs/default-forward-veto-ledger.md`.

**Two.** The read-modify-write in `settleDecision` /
`annotateDecisionOutcome` is guarded by a small claim local to this
module rather than by `src/store/fileLock.js`, which the concurrent
`shared-runtime-files-have-no-cross-process-lock` lug is building. That
file was untracked and vanished mid-build when another session reverted
the shared checkout; a mechanism whose correctness depends on an unlanded
file is not a mechanism. When it really lands, these call sites should
adopt it and the local claim should go.
