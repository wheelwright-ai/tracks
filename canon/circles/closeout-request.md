# closeout-request

Design: `wheel-hub/docs/session-entrance-exit-redesign.md`, section X2
(X1 is the report this injects a call to; X3 carries deferred findings
to the handoff; X4 is the exit verdict -- none of those are here).
Code: `src/hooks/closeoutRequestHook.js`,
`src/hooks/lib/closeoutRequestPhrases.js`,
`canon/closeout-request-phrases.yaml`.

## Why

Operator, 2026-09-15: end a session by saying so ("ty lets end here")
and have the agent audit and act, instead of the retired v1
`/wai-closeout`. X1 (83bec49) built the read-only report; nothing made
the agent run it. This circle is the trigger: on the prompt that asks
to close out, the protocol arrives as `additionalContext`, so the agent
runs the report, acts on or defers every finding, and answers with a
verdict -- in the same turn, while it can still act.

## Matching rules (the phrase list itself is canon, not here)

The prompt is cut into clauses on `. ! ? ; ,` and newlines, fenced code
removed first. A clause matches when a `closeout_phrases` regex hits it
(case-insensitive, any position) and

- no `negation_guards` regex ends before the hit in that clause --
  "don't end here", "do not end here", "not yet time to wrap up",
  "before we wrap up, commit" do not match; "lets end here, but don't
  push" does (the guard is in the next clause);
- the clause carries no code: no backticked span, no token of word chars
  joined by `/ . _ -` (`scripts/closeout.js`, `closeout-request`) --
  "the closeout in scripts/closeout.js" and "`closeout`" do not match.

No usable canon file in the instance or in the framework checkout the
hook lives in: no match. There is no built-in list.

## The block

Measured 2026-09-16 with `countTokens` (src/compiler/tokenCount.js) on
the text the hook injects for a real 36-char session id: **188 tokens,
674 chars**; the fixture re-measures it and refuses above 260 tokens. It
says: ignore if not a closeout; run `node scripts/closeout.js
--session-id=<id>`; ACT (scoped `git commit -- <paths>`, never `add -A`;
kernel-verb lug transitions; `scripts/acknowledge-live-state.js` for the
session's own misses; repair upkeep) or DEFER (finding + recheck command
in the reply) each finding; NEVER push in-session; reply with the verdict
(done / deferred / operator must do) and end with "safe to /exit" or
"NOT safe to /exit: <why>".

## What it does not do

It never blocks a prompt, never runs the report itself, never writes a
store (the per-hook capture row aside). A prompt that is not a closeout
produces empty stdout; the fixture composes the other UserPromptSubmit
hooks with and without this one bound and proves byte equality.
