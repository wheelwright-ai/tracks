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
later.

## The origin code is real, never defaulted (2026-09-16)

lug footer-identity-is-generated-from-spoke-registration-and-never-
defaulted, long form `docs/footer-identity-gap-260916.md`. footer-audit
used to fall back to a silent `|| "HF"` when a spoke's real origin code
couldn't be resolved -- every spoke registered with no code (basher,
tracks, pathfinder, why-go-bye, all in September) got HF-coded ids until
caught by hand. That default is gone. Two real gaps now write their OWN
honest correction (`gapReason`, never a fabricated `footerText`) through
this same hook: no `origin_code` registered for the spoke names the
spoke and the fix (`add origin_code to canon/<spoke>.spoke.yaml and
compile`); no session-registry row at all (a resumed session whose
SessionStart hook never re-ran) names the session id and the cause.
Surfaced here as `FOOTER CORRECTION UNAVAILABLE (previous turn): <reason>`,
never wrapped in "the correct footer... was" (there is no correct footer
to show). checkFooterPresent itself now also catches a WRONG origin code
(a real coordinate id naming this session but coded for a different
spoke) as a real miss, not a pass.

## The taste loop, same hook (2026-09-16)

lug taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-
footer-does, long form `docs/taste-loop-closes.md`. A taste miss is a
previous-turn correction of the footer's exact shape, so THIS hook (not
tastegraph-injection) also surfaces, from `src/tastegraph/tasteLoop.js`:
the one-shot `TASTE MISSED on the previous turn: <key> -- <rule> -- your
closing lines were: ... -- apply it, or reply \`dispute <key>: <why>\``
block (under 120 tokens, measured); the 10-turn `TASTE REVIEW` line; each
`applies_when` taste whose moment is now (`TASTE NOW (<moment>): ...`,
one line per prompt); and the approach pattern a re-issue just made
timely (`PATTERN at this moment`). A disputed or muted key is never
injected. Proofer sessions see none of it.
