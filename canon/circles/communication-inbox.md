# communication-inbox

Step 2 (INBOX) of initiative wheel-agents-talk-up-down-and-across
(wheel-hub docs/wheel-agents-talk-up-down-and-across.md; design
docs/cross-spoke-communication-lugs.md 2.2, 2.3, 2.6). A communication
lug lives in the REQUESTER's lugs/ and names its target in
`target_spoke`; this circle is the target's side.

## Read (`src/conductor/communicationInbox.js`)

`readCommunicationInbox(spokeDir)` resolves this spoke's name
(canon/profile.yaml, else the spoke card whose repo is this directory,
else the only card, else the basename -- the source is on the record),
then walks every sibling it can reach: the hub, the hub's registered
spoke cards with an on-disk repo, and both `.local/known-repos.json`
files. Self is excluded by real path AND by name, so a worktree never
reads its main checkout as a sibling. Each sibling's lugs/ is READ for
`type: communication`, `target_spoke === this spoke`, status not
fulfilled / declined / closed. Nothing is written into a sibling.

## Rank (`rankCommunicationInbox`, `src/conductor/readyWork.js`)

The one ordering: effective priority (stored, or `escalation.bump_to`
once `escalation.after` has elapsed since `requested_at` -- ONE bump,
computed from the stored fields on every read, never compounding), then
escalated-first inside a tier, then the requester's seniority role
(`options.seniority[from_spoke]`: senior > peer > junior > undeclared,
undeclared reads null), then ask (halt > goals_needs > second_opinion >
other), then requested_at, then name. `buildReadyWorkQueue` ranks its own
communication lugs by this effective priority; `buildSeniorInbox` and
`buildAdvisorInbox` are filters over the same rows. Precedence with the
planner's rules is settled in wheel-hub docs/max-as-planning-advisor.md.

## Surface

- Every SessionStart: the goals review (`buildCommunicationInboxSection`,
  composed by `buildGoalsReviewInjectionParts`) reads the inbox live and
  prints the ONE digest line, silent when nothing is addressed here. No
  hook of its own and no settings.json binding: a hook_event circle
  authored on a dispatch branch cannot pass its own commit gate before
  the fold (lug hook-event-circle-authored-on-a-dispatch-branch-cannot-
  pass-its-own-commit-gate), and the line was already the composer's.
- Wheel clock (`JOB_RUNNERS.communicationInbox`): the same read, writing
  `runtime/communication-inbox.json` in THIS spoke for the out-of-session
  loop; the SessionStart catch-up fires it when a tick is owed.
- `node scripts/communication-inbox.js [--view=senior|advisor]` on demand.

## Cadence (disclosed)

harness-factory declares `communication_inbox: { job: communicationInbox,
cadence_ticks: 1 }` in canon/ozi.advisor.yaml (a ~1s read of ~1.5k
files, measured). wheel-hub's canon/otto.advisor.yaml has no rule-11
headroom for another job (997/1000 tokens; lug otto-advisor-yaml-cannot-
take-another-wheel-clock-job), so on the hub this circle audits PHANTOM
and the record is not written until that lug lands; the hub's goals
review still prints the line every session start, and
scripts/communication-inbox.js --record writes the record on demand.

## Not here

Fulfillment records and the outbox (step 3), the group contract that
declares seniority roles (step 5), Max's review record (step 6).
