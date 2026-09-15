# precompact-checkpoint

Lug `session-continuity-precompact-checkpoint` (wheel-hub/lugs), opened
260901-FBL-068, mid-turn, against a real gap found live: this session's
own context was compacted (2026-09-01) and no hook was bound to
`PreCompact` anywhere in the build -- not the repo default
`.claude/settings.json`, not the live session's own
`CLAUDE_CONFIG_DIR/settings.json` (confirmed by inspection), not
`docs/live-hook-capture.jsonl` (zero rows for the event, because nothing
was there to fire). `canon/hook-liveness-matrix.md`'s own Results table
had no PreCompact row at all -- only a prose note that live-vs-snapshot
testing for the event was deferred as disproportionate (260828-FBL-023).
That deferral was about *testing* liveness; it never meant *no hook
should exist*, and this compaction exposed that the two had drifted into
the same thing.

## What it does

Bound to `PreCompact` (matcher `""` -- every real firing, manual or
auto). On fire, gathers the real state that was in flight the moment
compaction happened: the active lug pointer, the active advisor pointer,
the ledger's most recent decisions and directions, and the current
unsatisfied-reference count -- the same real sources
`buildCheckpointContext` (session-continuity-checkpoint's own module)
already reads at SessionStart, reused here rather than re-derived. Writes
one JSON file per firing to
`runtime/pre-compact-checkpoints/<session_id>-<timestamp>.json` (never
overwrites; a session can compact more than once) and appends a `lug`-kind
ledger row (`attribution: "precompact-checkpoint"`) recording that it
fired, with the checkpoint file's path. Never blocks: exits 0 on a
missing session_id, an unwritable checkpoint dir, or any other failure.

## Build history and scope corrections

The original build's scope correction (why this circle writes a real
side-effecting snapshot rather than a read-side re-injection, and the
still-open PreCompact `additionalContext` question footnoted in
`canon/hook-liveness-matrix.md`), and why the checkpoint is worth having
without the injection half, are recorded in full in
`docs/precompact-checkpoint-build-history.md`. Split out of this file,
not trimmed: rule 11 caps an `instructions_ref` at 1000 tokens, and this
one was already at the ceiling before the second duty below was added.

## Second duty (2026-09-07): track rotation

Added by wheel-hub `lugs/track-files-have-no-retention-and-sessions-never-close.yaml`.
**Additive** -- everything above is unchanged and still runs first, in
its own `try/catch`, so a rotation failure never costs a session the
checkpoint it already wrote. The same firing now also reviews the closing
track for disclosed-gap language, writes a real closing summary, sets
`closed_at`, and reopens a fresh track with the session's identity
carried across (`src/lugTracking/trackRotation.js`).

Full build record, design decisions, traced consumers and proof numbers:
`docs/track-rotation-on-precompact.md`.
