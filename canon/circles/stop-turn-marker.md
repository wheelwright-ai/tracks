# stop-turn-marker

Section 7: "The Stop hook writes turn boundaries tagged with the active lug
id into the track; completion sums them. This is the only way per-lug cost
becomes real, because the report showed it cannot be reconstructed
afterwards." v1's baseline was 0 of 20 lugs with a measurable cost -- not
because nobody cared, but because nothing recorded it at the moment it
happened.

## What it records

One marker per turn, appended to `runtime/track.jsonl`, tagged with
whichever lug `lug-lifecycle-tracker` most recently marked active:
`wall_time_seconds` (time since the lug became active, clipped per
260831-FBL-057 ruling 1) and `tokens`, summed for real from the session
transcript (`transcript_path`) and written as `null` -- never 0 -- with a
"cost unmeasured" ledger row when that isn't possible.

## Second, additive duty: the per-turn disclosed-gap scan

wheel-hub `lugs/no-real-mechanism-turns-disclosed-gaps-into-lugs`. The same
firing also reads **this turn's own new content** -- the real git diff
(committed since the last scan's watermark, plus uncommitted and untracked
work), in the session's own repo and in the harness checkout the hook came
from -- for disclosed-gap language, using the ONE canon phrase list
(`canon/disclosed-gap-phrases.yaml`, built by MAX-121 and reused here, not
forked).

Why Stop rather than the commit boundary: a turn that writes a TODO into a
doc and never commits has no commit boundary at all, and that is the exact
shape of the 2026-09-07 miss this closes. Committed work is still covered,
through the per-repo HEAD watermark.

On a match the finding is durable (`runtime/disclosed-gap-findings.jsonl`
plus a real ledger row) and **undismissable**: the first Stop that sees it
blocks the turn from ending silently, naming file, line, phrase and the
line itself, and every later turn restates it until it is resolved. Nothing
is auto-filed and nothing is auto-closed -- `hf gap-findings resolve <id>
--lug <name>` (it was real) or `--dismiss "<why not>"` (it wasn't) are the
only two ways out, and both write a ledger row.

Full build record, including the false-positive layers: `docs/disclosed-gap-turn-scan.md`.
Its own conformance fixture: `conformance/fixtures/disclosed-gap-turn-scan/`.
