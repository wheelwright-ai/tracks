# session-continuity-checkpoint

Phase 1 Part B, B3 of the reconciled-gate work order: "The first turn
should not be the operator re-explaining." Found live, running Part B's
own "before" TTPT trace (`docs/TTPT.md`): with a lug left `in_progress`
and no checkpoint mechanism, the model reasoned its way to the in-flight
state on its own -- but only by spending real tool calls (`Bash`, `Read`)
discovering `runtime/active-lug.json` and the lug file. Real cost, just
paid by exploration instead of operator restatement.

## What it does

Bound to `SessionStart`. If a lug is active (`runtime/active-lug.json`
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
