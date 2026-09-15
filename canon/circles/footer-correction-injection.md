# footer-correction-injection

260831-FBL-057 ruling 4: the practice row from the prior session already
found the real shape of this failure -- the turn-status-footer
instruction survives composing a long, tool-call-heavy response, but
dies at closing; the footer is the very last thing composed, and it's
the thing that gets dropped. Repeating the instruction earlier in
context has not moved 32 recorded misses. Until a mechanical, structural
closer exists, this is the cheapest late-stage check actually available.

## What it is, honestly

`footer-audit` (Stop) already knows a miss happened the moment it
happens, and already has every real field a footer needs (the session's
real callsign, its real turn ordinal, the real model, the real framework
version, the real turn cost, the real open-reference count). Rather than
only recording the miss, it now also computes the CORRECT footer for the
turn that just closed and hands it to this circle
(`writePendingFooterCorrection`, `src/lugTracking/footerCorrection.js`).

This circle is the other half: at the very next `UserPromptSubmit`, it
consumes (reads, then deletes) that pending correction and surfaces it
as `additionalContext` -- so the next response opens already
acknowledging the miss and carrying the real coordinates that should
have closed the previous one. A missed footer becomes self-correcting
on the following turn instead of silent until someone happens to check
the ledger.

One-shot by construction: consuming deletes the pending file, so this
never repeats past the one turn immediately following a miss, and never
accumulates a growing backlog of stale corrections.

## Known, accepted gaps

This does not make the model actually emit its OWN footer any more
reliably -- it only guarantees the miss is surfaced, loudly, one turn
later. If footer-audit itself cannot compute a real correction (no
callsign registered yet, an unreadable track), it silently skips writing
one rather than fabricate a placeholder -- that turn's miss is still
recorded in the ledger, just without a follow-up injection.
