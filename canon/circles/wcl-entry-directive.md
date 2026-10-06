# wcl-entry-directive

Operator ruling, 2026-09-14 (basher s128, lug
wcl-rows-are-assured-capabilities-and-entry-matched-injection): "on entering
the session the prompt injected that matches either raw or wakeup to make
best use of users time."

## What it does

`wcl` offers two ways in and sets `WCL_ENTRY` on the `claude` it launches.
This hook fires on SessionStart, reads that variable, and injects the
matching opening contract as `additionalContext`:

- `ozi` -- the wakeup contract, one source (`src/basher/wclEntry.js`
  `oziWakeupDirective`): run the spoke's own wakeup protocol, brief
  scannably, then 2-4 options with the recommendation first, then wait for
  the pick. Since the operator decision of 2026-09-29 ("Ozi wakeup needs to
  be a writable session") the operator's Ozi wakeup is ONE interactive,
  writable session under the spoke's pinned `--permission-mode`: the
  directive is its first prompt, nothing narrows its tools, and after the
  pick triage, planning, lug edits (kernel verb) and dispatches are in
  scope. Only `wcl <spoke> --ozi-headless` (CI / cron, no approver) still
  runs the capped read-only `-p` wake turn and then `--resume`s it; that
  variant alone carries the read-only sentence.
- `raw` -- the operator speaks first; answer the ask, no briefing, no options
  menu unless asked; keep the resume contract in mind silently.

## What it is not

Not a briefing. The continuity checkpoint and warmup-goals-review still
inject the wake material; this circle only says how to OPEN with it. A
session not launched by wcl (no `WCL_ENTRY`) gets nothing from this hook,
and the Proofer (`PROOFER_SESSION=1`) never sees an operator-facing contract.
