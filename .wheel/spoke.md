# tracks

Status: goals agreed with the owner
Date: 2026-11-06

## What it is
Tracks is the wheel's prompt-and-format library for turning an AI conversation into a portable "Track file" (a JSONL record of every turn: decisions, ideas, open items) that can be taken to another model, person or session. It ships three prompt variants (closing-request, prep-and-request, active-collection), a format spec, sample tracks, a small static viewer and a set of skills. Public-facing positioning (MIT license, Wheelwright branding) for anyone who uses LLMs. Stack: markdown, JSONL, an HTML/JS viewer served by serve.py.

## Proposed goals (confidence)
- Free the intellectual product of AI conversations with a portable, model-neutral record — 90%
- Feed the wheel's own continuity (session Tracks; chat-to-track, closeout and wakeup skills) — 65%
- Be a public, adoptable piece of the open-source Wheelwright framework — 45%

## Owner's goals
Ordered along the path to market: works for you, proven with real users, earns, grows.
1. **The product:** a portable, model-neutral record of an AI conversation that anyone can use.
2. **Use it ourselves:** the wheel's own sessions and wake-ups run on Tracks.
3. **Make it the best:** measure prompt variants across models and keep the winner.
4. **Distribute:** define and prove the claude.ai connector.

Agreed with the owner, 2026-11-07 (hub ledger r-003060; plans/spoke-goals.md in the hub).
