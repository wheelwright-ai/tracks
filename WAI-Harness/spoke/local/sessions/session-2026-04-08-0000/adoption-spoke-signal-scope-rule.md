# Teaching Applied: Spoke Signal Scope Rule

**Teaching:** signal-20260407-1904-from-minder.md.teaching
**Applied:** 2026-04-08
**Rule:** Spokes must only emit hub signals for cross-spoke-generalizable patterns. Local patterns should be kept local.

## Summary
Applied behavioral rule to prevent spoke-local signals from polluting the hub signal queue. Before emitting a signal, ask: "Does this pattern apply to >=1 other spoke?" If no, keep it local. If yes, emit signal as a cross-spoke generalization.

**Status:** APPLIED