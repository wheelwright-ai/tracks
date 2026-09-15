# session-start-warmup

Not part of the increment 1-6 loop. Built 2026-08-26 for one purpose: proving
whether a headless (`claude -p`) session binds and fires hooks at all before
investing in the full live-hook-test retest loop. Section 12's baseline
table carries "SessionStart: 31s, fires twice" as a v1 defect -- this
circle's capture is also how a v2 instance would notice if it regressed to
that.

## What it does

Appends one row to `docs/warmup-capture.jsonl` (or `WARMUP_CAPTURE_PATH`)
every time SessionStart fires: hook name, timestamp, and the real stdin
Claude Code sent. Nothing else -- no ledger write, no decision, no
blocking. Reading that file after a session tells you whether hooks fired
at all, and how many times.
