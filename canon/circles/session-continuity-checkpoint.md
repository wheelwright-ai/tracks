# session-continuity-checkpoint

Phase 1 Part B, B3 of the reconciled-gate work order: "The first turn
should not be the operator re-explaining." Found live, running Part B's
own "before" TTPT trace (`docs/TTPT.md`): with a lug left `in_progress`
and no checkpoint mechanism, the model reasoned its way to the in-flight
state on its own -- but only by spending real tool calls (`Bash`, `Read`)
discovering `runtime/active-lug.json` and the lug file. Real cost, just
paid by exploration instead of operator restatement.

## What it does

Bound to `SessionStart`. Opens with the operator BOARD (lug
session-start-injection-action-block-then-delta-digest, E2: net-net,
CURRENT / IN FLIGHT / NEXT / YOURS, handoff, active lug, closeout
findings, vetoable acts -- `src/conductor/statusBoard.js`, the same board
`hf status` prints, under 1,200 chars, every row naming its store). Then,
if a lug is active (`runtime/active-lug.json`
exists), injects its **full** YAML content as `additionalContext` -- per
ruling 2026-08-27 (task 3), the active lug loads in full, since it's the
one thing actually being worked on and a stranger picking it back up needs
everything. The rest of the backlog loads as **one-line summaries**
(`- name [state, priority, ~estimate] outcome`), the exact format measured
in `docs/CONTEXT_LOAD.md` (231 tokens for wheel-hub's 8-lug backlog,
against 2,125 for full content).

Silent (no `additionalContext` emitted at all) when nothing is in flight
and the backlog is empty -- there's nothing to say, so it says nothing,
rather than injecting an empty checkpoint block into every session.

## What it is not

It is not Part C's Conductor or goals review -- it doesn't propose
routing, doesn't compute cost, doesn't know about the autonomy table. It
is the narrower thing B3 asks for: making sure in-flight state is *already
loaded* by the time the first turn starts, so Part C's fuller wakeup has
something to build on rather than starting from the same "the model has to
go discover this" gap this circle closes.

## Carried findings rechecked (X3, 260916)

Lug closeout-findings-carried-forward-and-rechecked-at-wakeup. Before the
board is composed, `recheckCarriedFindings` (`src/lugTracking/
sessionCheckpoint.js`) runs every finding the last handoff carried
(`findings[]`, plus the pending set) through its own X1 recheck line, each
under `RECHECK_TIMEOUT_MS` (3000 ms), the set under `RECHECK_BUDGET_MS`
(10 000 ms) -- a start is never held past that. Condition gone (per the
finding's `gone` rule) -> RESOLVED: one ledger row (`row_kind: decision`,
naming the finding and the session that deferred it), never printed.
Still true -> printed in the ACTION block (after the board, or after the
active-lug block when one is in flight; before the backlog) as
`carried from <session8>: <text> -- recheck: <cmd>`, and carried again
with `deferred_by` unchanged and `carried` +1 (one per session start that
saw it open). Could not run (timed out, no shell) -> printed as `unknown`,
carried unchanged, never dropped. Seen open `CARRY_ESCALATION_COUNT` = 3
times -> escalated: first in the block as `ESCALATED carried Nx`, one
ledger row at the crossing; never dropped. The open set is written back
to `runtime/last-handoff.json` (`findings_recheck` records the pass) and
to the pending set, so a sibling waking on the same checkout does not
retire the same finding twice. A composition with no session id (rule
12's measurement) runs nothing and writes nothing.
