# tracks

Status: proposed, awaiting owner
Date: 2026-11-06

## What it is
Tracks is the wheel's prompt-and-format library for turning an AI conversation into a portable "Track file" (a JSONL record of every turn: decisions, ideas, open items) that can be taken to another model, person or session. It ships three prompt variants (closing-request, prep-and-request, active-collection), a format spec, sample tracks, a small static viewer and a set of skills. Public-facing positioning (MIT license, Wheelwright branding) for anyone who uses LLMs. Stack: markdown, JSONL, an HTML/JS viewer served by serve.py.

## Proposed goals (confidence)
- Free the intellectual product of AI conversations with a portable, model-neutral record — 90%
- Feed the wheel's own continuity (session Tracks; chat-to-track, closeout and wakeup skills) — 65%
- Be a public, adoptable piece of the open-source Wheelwright framework — 45%

## Owner's goals
(to agree)

Source: wheelwright-hub spokes/landing/tracks.md
