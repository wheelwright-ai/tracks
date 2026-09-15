# definition-complete-gate

Renamed from `readiness-gate` on ruling 2026-08-26: the original name
conflated two different things -- structural completeness and the
fresh-context stranger test -- into one check. They're now two circles.
This one is the structural half, and it gates `defined` and everything
after it (`ready`, `in_progress`, `review`, `done`), because all of those
states presuppose the lug is at least defined.

## What this circle checks

For each field the Lug schema (`schemas/lug.schema.json`) marks required,
definition-complete-gate asks whether it's actually there and non-placeholder:

- `intent` and `outcome` — long enough to say something, not a placeholder.
- `acceptance` — at least one criterion, each one a real, testable sentence.
- `pointers` — at least one, and every pointer that names a file resolves to
  a file that exists.
- `open_questions` — must be empty.
- `executor` — assigned.
- `constraints`, `out_of_scope` — present (may be empty arrays).

## What this circle is not

It is not the stranger test. Passing this check means the lug is
*definition-complete* -- a stranger could read it and know what's being
asked. It does not mean a fresh-context agent has actually tried and
succeeded. That's `ready-gate-stub`'s job, and until increment 7 supplies a
real fresh-context check, `ready-gate-stub` cannot honestly say yes to that
question either -- it only lets a lug enter `ready` as an explicitly logged
stub, never silently.

## On failure

definition-complete-gate never mutates the lug it's checking. On failure it:

1. Blocks the edit that would have set `state: defined` (or later) on a lug
   that isn't actually definition-complete, via a PreToolUse hook.
2. Writes a ledger row of kind `lug` — the failure_routing target,
   `lug:definition-complete-gate-failure` — recording which lug failed and
   why, with `attribution: definition-complete-gate` so it's traceable back
   to this circle.

The lug stays in its current state. The ledger row is what makes the gap
visible to backlog review instead of silently blocking with no trace.
