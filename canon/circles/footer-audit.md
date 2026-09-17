# footer-audit

260829-FBL-027. Ports v1's `AI1_footer_mandatory` (Design Inputs
Register: "every assistant response MUST end with the turn footer...
omitting it is a values violation, not a formatting choice") with real
enforcement v1 never had. v1's only mechanism was `AI2_self_correction`
-- the model noticing its own miss -- which is precisely the failure mode
that motivated this circle (a real miss, this session, caught by the
operator, not by self-correction).

Reads the transcript for the response that just completed, checks
whether it contains a real coordinate id (`isCoordinateId`,
`src/ledger/promptId.js`) naming this session's own real `session8` or
registered callsign, and writes a `footer-miss` ledger row when it
doesn't. Positioned BEFORE `trackWriteHook.js` in `.claude/settings.json`'s
Stop array so it reads `turn_ordinal` as it stood before this Stop's own
increment -- the value that was actually knowable when the audited
response was composed.

Misses accumulate visibly: `src/conductor/goalsReview.js`'s
`buildFooterMissSection` surfaces them in the warmup goals review once 3
or more unacknowledged misses exist. Prompt instructs
(`trackGovernancePrompt.js`'s compiled text, injected at SessionStart),
hook verifies (this circle), ledger remembers (`footer-miss` rows) --
same pattern as every other real-evidence mechanism in this codebase.

Lug max-plans-planner-schedules-ozi-dispatches-and-reports-validated
(260914): the same Stop also audits the turn's TOOL CALLS against
`canon/policies/max-plans-planner-schedules.policy.yaml`
(`src/lugTracking/roleSplitAudit.js`). A top-level session that edited
`src/`, `conformance/` or `scripts/` in a canonical checkout (its own root
or a registered repo) with no dispatch row issued that turn gets one
existing-shape `decision` row, attribution `max-plans-planner-schedules`.
A dispatched session is exempt by a real signal only: `WCL_DISPATCH_ID`,
a registry row naming its `child_session_id`, or a live dispatch-children
row naming its pid. Bash edits are read heuristically (`writeTargetsForTool`);
the row names the evidence so the error rate can be measured.

## Origin code is real, never defaulted (2026-09-16)

lug footer-identity-is-generated-from-spoke-registration-and-never-
defaulted, long form `docs/footer-identity-gap-260916.md`. `checkFooterPresent`
now takes a real `originCode` (`resolveOriginCodeForSpoke`, read from the
GENERATED `canon/origin-codes.registry.yaml` -- compiler rule 21 refuses
BUILD when a spoke.yaml carries no real `origin_code` or two share one)
and returns `present: false` with `"origin code X, registered Y"` when a
coordinate id names this session but was minted with the WRONG spoke's
code -- basher's own real bug (`0916-HF-otter`, HF-coded by the removed
`|| "HF"` default in this hook). Callsign comparison is case-insensitive
(`formatCoordinateIdV3` renders callsigns capitalised -- Otter, not
otter -- the wordlist itself stays lowercase). No real origin code
resolved at all, or no session-registry row -- never silently skipped;
see `footer-correction-injection`'s own note on the two honest corrections.

## The taste loop's Stop half (2026-09-16)

lug taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-
footer-does: the taste audit here goes through `runStopTasteLoop`
(`src/tastegraph/tasteLoop.js`) -- it records a `dispute <key>: <why>` the
response carries (taste-dispute row + calibration record + per-session
stop), skips muted heuristics, writes the miss with its judged lines for
the next prompt, and at every 10th response turn prints one
`TASTE REVIEW turns N-M: <key>=<misses> (<disputes> disputed)` line to
this hook's stdout and writes `runtime/tastegraph-proposals/<key>.md` for
a key missed 3+ times undisputed. Never edits master or overlay.
