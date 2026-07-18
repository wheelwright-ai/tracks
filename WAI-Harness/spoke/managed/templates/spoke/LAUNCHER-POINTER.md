# The launcher is NOT distributed as a per-spoke copy

`wai-enter.sh` used to live here as a 405-line template and was MANIFEST-registered for
fan-out to every new spoke. It had **zero worktree isolation and no duplicate-session
guard** — so every spoke onboarded from it received a launcher weaker than the one `wcl`
actually runs. That divergence is what produced the three-way fork (1790 / 660 / 405
lines) that seat A exists to end.

**Canonical launcher:** `WAI-Harness/spoke/managed/tools/wai-enter.sh` (authored here;
mywheel is `is_master`). Basher distributes it.

**How a spoke reaches it:** the PATH shim — `wai-enter` on PATH resolves to the single
deployed launcher. `basher/bin/wai-enter`'s own comment states the shim exists so
`wai-enter` works "from any folder **without a per-spoke copy**". Basher already reached
that conclusion; the per-spoke copies were v3 vestiges, and because the `basher` TUI read
them, they became the fork.

A spoke needs NO local `wai-enter.sh`. If you are adding one back, you are re-creating the
fork. Route the change to the canon instead.

See: epic-launcher-reconciliation-v1 (seat A, ratified 2026-07-15)
Precedent: `templates/spoke/.claude/hooks/POINTER.md` retired the hook templates the same way.
