# Change Log -- tracks (operator view)

<!-- (generated -- never hand-edit) by hf changelog, from the record layer -->

Range: earliest framework commit (2026-08-26T09:39:03.000Z) .. latest record. Repos: tracks. Dates are UTC.
Records read: git log (main); lugs/*.yaml (state done, certified_by, tests, cost, intent's operator quote); runtime/event-log.jsonl (done transitions); runtime/deploy-runs.jsonl + registry/latest-cut.json (cuts published); .cut-status.json and its git history (cuts applied / received); canon/circles + .claude/settings.json between two landings (what a cut changed for the spoke); reference/circles/*.yaml + .claude/settings.json (circles added, hooks bound); runtime/dispatch-registry.jsonl (dispatches completed, measured tokens).

# Part 1 -- tracks's own history

## 2026-09-18

### cuts

- Cut 87971bbe received (from 5c79e2c6), posture absorb_and_report: 3 changed (dispatch-run-salvage, git-boundary-test-gate, hf-deploy).

### harness bookkeeping

- 1 harness bookkeeping commit(s) in tracks (harness-arrival-audit 1).

## 2026-09-17

### cuts

- Cut 5c79e2c6 received (from b81e2bc1), posture absorb_and_report: no circle or hook changed for this spoke.
- Cut b81e2bc1 received (from 4a839956), posture absorb_and_report: no circle or hook changed for this spoke.
- Cut 4a839956 received (from ca0e4076), posture absorb_and_report: no circle or hook changed for this spoke.
- Cut ca0e4076 received (from 89051371), posture absorb_and_report: no circle or hook changed for this spoke.
- Cut 89051371 received (from 6e237e8f), posture absorb_and_report: no circle or hook changed for this spoke.
- Cut 6e237e8f received (from 8e61551f), posture absorb_and_report: no circle or hook changed for this spoke.
- Cut 8e61551f received (from c8ec1341), posture absorb_and_report: 3 circle(s) gained (zellij-tab-identity-session-end, zellij-tab-identity-tool-reset, zellij-tab-identity-turn-start); 14 changed (calibration-record, cross-provider-verification, dispatch-run-salvage, footer-audit, footer-correction-injection, hf-deploy, notification-agent-waiting-notify, readiness-certification-sweep, session-continuity-checkpoint, session-registry, stop-agent-waiting-notify, tastegraph-injection, warmup-goals-review, wcl-verify-then-launch); hooks bound: PreToolUse preToolTabResetHook.js, SessionEnd sessionEndTabClearHook.js, UserPromptSubmit userPromptSubmitTabHook.js.
- Cut c8ec1341 received (from 21926af8), posture absorb_and_report: 1 changed (cross-provider-verification).

### harness bookkeeping

- 22 harness bookkeeping commit(s) in tracks (harness-arrival-audit 15, hf deploy: cut 7).

## 2026-09-16

### cuts

- Cut 21926af8 received (from 79c1648d), posture absorb_and_report: 4 circle(s) gained (closeout-report, closeout-request, lug-write-schema-gate, session-files-touched); 12 changed (agent-tool-scope-guard, bash-lug-guard, communication-inbox-delta, gate-pool-serial-suites, hf-deploy, max-persona-boundary-guard, session-continuity-checkpoint, session-end-handoff, session-exit-commit, success-prediction, warmup-goals-review, wcl-verify-then-launch); hooks bound: PostToolUse filesTouchedRecorderHook.js, PreToolUse lugSchemaGateHook.js, UserPromptSubmit closeoutRequestHook.js.

### harness bookkeeping

- 3 harness bookkeeping commit(s) in tracks (harness-arrival-audit 2, hf deploy: cut 1).

## 2026-09-15

### p0-bugfix-circle-audit-conversation-track-ingestion  (at review -- certification pending)

Challenge: P0 (p0_data_integrity): circle-completeness audit found a real PHANTOM circle -- conversation-track-ingestion: could not resolve a real entry point from conformance fixture conformance/fixtures/conversation-track-ingestion/conversation-track-ingestion.test.js under the instance root ~/projects/wheelwright/tracks (expected a path.join(REPO_ROOT, ...) construction)
Solution: The real data-integrity failure recorded in ledger row ldg-p0-circle-audit-conversation-track-ingestion-1789431314084-9u86 (source_ref: circle-audit, 2026-09-15) is fixed at its real cause -- the same check that produced this P0 row no longer reports it on a clean re-run, and no other code path can reproduce it silently.
Record: certification pending

### cuts

- Cut 79c1648d received (from f40bc3fe), posture absorb_and_report: 1 circle(s) gained (wcl-entry-directive); 1 removed (conversation-track-ingestion); hooks bound: SessionStart wclEntryDirectiveHook.js.
- Cut f40bc3fe received (from 66e48e3a), posture absorb_and_report: no circle or hook changed for this spoke.
- Cut 66e48e3a received (first cut), posture absorb_and_report: no circle or hook changed for this spoke; policies changed planner-class-floors.

### runtime

- tracks: v2 onboarding tail -- cut status 66e48e3a, ledger rows, first session's runtime and capture files (the arrival audit committed the 200-file cut itself at 96ffc65/9a6d6cb)

### WAI-Harness

- tracks: retire the v1 WAI-Harness machinery to ~/projects/.archived/tracks-v1-260914 (WAI-Harness/, .claude/hooks, wai-enter/exit, the v1 settings and CLAUDE.md, basher's v1 session-cost advisor and its test) -- fully on the v2 harness (cut 66e48e3a); WAI-Spoke/sessions stays (Track files, product data)

### harness bookkeeping

- 5 harness bookkeeping commit(s) in tracks (Session work 2, harness-arrival-audit 3).

# Part 2 -- the wheel's history that reached tracks

## Cut 87971bbe -- received 2026-09-18 01:44Z (from 5c79e2c6)

Cut 87971bbe received (from 5c79e2c6), posture absorb_and_report: 3 changed (dispatch-run-salvage, git-boundary-test-gate, hf-deploy).

### 2026-09-18

#### docs

- git-boundary-test-gate circle doc under the rule-11 cap after two builders extended it (186 lease skip, 187 incremental gate + sweep yield): one lease section, tiers trimmed for meaning

#### wheel-agents-talk-up-down-and-across

- The push gate judges the pushed tree by the suites that cover the files changed since the last PROVEN tree (the proof record it already writes) plus the serial-first timing suites and the circles runner, and reuses the prior proof for everything else -- one push, ~4 min at today's sizes. [fixtures 40/40, 31/31, 66/66, 15/15; landed 9cafbd1c]

### 2026-09-17

#### commits

- P0 round trip fulfilled by basher's reply (reply_to linked)
- P0 round-trip request to basher (real run for MAX-184): no live basher session, rung C refused on the missing spoke envelope -- follow-up lug filed on the hub

#### taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-footer-does

- The tap's headroom check resolves the envelope from the hub (the wheel's account) and only then the target spoke's own, naming which it used in the ledger row; with headroom and the kill switch clear a Sonnet dispatch is queued on the target spoke for the request and the request lug reads dispatch_queued. [landed b5f24c4f]

#### wheel-agents-talk-up-down-and-across

- launchSpoke's headless envOverrides set CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0 so a builder's background task is bounded by the dispatch's own idle/timeout watchdog only; the dispatch prompt's standing rules tell builders to run gates in the foreground; and dispatch-run-salvage reads the child's stderr for the print-mode termination line and records verdict killed_by: print_mode_bg_ceiling with the uncommitted files named, never finished_on_its_own. [landed 89a22492]

## Cut 5c79e2c6 -- received 2026-09-17 22:42Z (from b81e2bc1)

Cut 5c79e2c6 received (from b81e2bc1), posture absorb_and_report: no circle or hook changed for this spoke.

### 2026-09-17

#### conformance

- spokes-talk-directly fixture: the unfixed-code proof skips by name once HEAD carries the fix

#### taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-footer-does

- AMBASSADOR_BRIEF carries a generated "Talking to another spoke" section (send, ask for a confirm-back, resolve the path from the hub registry with `hf spoke-path <name>`, reply with reply_to, close both with one verb call). [fixtures 51/51; landed b877b91f]

## Cut b81e2bc1 -- received 2026-09-17 21:18Z (from 4a839956)

Cut b81e2bc1 received (from 4a839956), posture absorb_and_report: no circle or hook changed for this spoke.

### 2026-09-17

#### circle-schema-hook-event-name-lacks-stopfailure-and-worktreecreate  (at review -- certification pending)

Challenge: MEASURED 2026-09-17 (basher session 238db105) while declaring basher's pre-cut bash hooks as spoke-local hook circles (docs/spoke-local-hook- circles.md): schemas/circle.schema.json enumerates hook_event_name as PreToolUse, PostToolUse, UserPromptSubmit, Stop, SessionStart, SessionEnd, Notification, PreCompact.
Solution: The enum gains StopFailure and WorktreeCreate (and any other event the current Claude Code hooks reference lists); generateHookBinding emits them like the rest; the hook-binding-drift resolver and arrival audit treat them as ordinary events. basher can then declare canon/hooks/basher-hook-notify-stopfailure.circle.yaml (StopFailure, .*) and basher-hook-worktree-create.circle.yaml (WorktreeCreate, *) and both land in the generated settings.json.
Record: certification pending

#### taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-footer-does

- AMBASSADOR_BRIEF carries a generated "Talking to another spoke" section (send, ask for a confirm-back, resolve the path from the hub registry with `hf spoke-path <name>`, reply with reply_to, close both with one verb call). [landed b81e2bc1]

## Cut 4a839956 -- received 2026-09-17 20:33Z (from ca0e4076)

Cut 4a839956 received (from ca0e4076), posture absorb_and_report: no circle or hook changed for this spoke.

### 2026-09-17

#### wheel-agents-talk-up-down-and-across

- The no-lane branch accepts a recorded lane_override exactly as the planner-lane branch does; `node scripts/lane-override.js <dispatch-id> --reason=<why> --session-id=<id>` stamps a completed dispatch row with lane_override + who/when and writes the default-forward veto row the MAX-173 design names; the done verb prints "lane gate: overridden -- <reason>" on the receipt. [landed 4a839956]
- One command a stranger can run from the public repo's README (curl the bootstrap script, or `npx`/`git clone && node src/cli.js bootstrap`) that installs dependencies, runs the scaffold interview (user, machine, hub path, first spoke, model lanes, permission mode, origin code), builds the hub and the first spoke, binds hooks with the paths of THAT machine, installs wcl on PATH and launches `wcl <first-spoke>` into the Ozi wakeup. [fixtures 5/150; landed 9988ca02]

#### commits

- confirm-back to basher: circle schema StopFailure/WorktreeCreate landed in cut c50fb9c876a3

#### conformance

- The enum gains StopFailure and WorktreeCreate (and any other event the current Claude Code hooks reference lists); generateHookBinding emits them like the rest; the hook-binding-drift resolver and arrival audit treat them as ordinary events. basher can then declare canon/hooks/basher-hook-notify-stopfailure.circle.yaml (StopFailure, .*) and basher-hook-worktree-create.circle.yaml (WorktreeCreate, *) and both land in the generated settings.json. [fixtures 9/9; landed c50fb9c8]

#### wilbur-d-custodian-timeline-otto-steering

- Every lug that reached review or done in the range gets ONE entry, headed by its name, with three short lines rendered from its own fields: Challenge (the intent, condensed to its first sentence plus the operator quote when present), Solution (the outcome, first two sentences), and the record line (state, certified_by verdict/provider, fixture counts, dispatch minutes + measured cost, commit shas -- every commit whose subject starts with the lug name is grouped under it, never listed loose). [landed e0cfe93b]

## Cut ca0e4076 -- received 2026-09-17 17:39Z (from 89051371)

Cut ca0e4076 received (from 89051371), posture absorb_and_report: no circle or hook changed for this spoke.

### 2026-09-17

#### conformance

- circles-runner-final-verdict fixture: the unfixed-code proof skips by name once HEAD carries the fix

#### wheel-agents-talk-up-down-and-across

- The pool results record carries a verdict's finality: a serial/timing suite's first failure is written provisional and the re-run's result replaces it as final; the circles runner in consumer mode waits for the final verdict of every covered fixture and judges on that alone; a runner that consumed a provisional verdict is impossible by construction. [fixtures 17/17, 66/66, 44/44; landed 0f90f8d5]

## Cut 89051371 -- received 2026-09-17 16:17Z (from 6e237e8f)

Cut 89051371 received (from 6e237e8f), posture absorb_and_report: no circle or hook changed for this spoke.

### 2026-09-17

#### taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-footer-does

- Drive: a Stop whose NEXT is dispatchable with no YOURS blocker and nothing started that turn is a drive-miss injected on the next prompt; unattended 30 min, the session self-continues with the NEXT as its prompt (kill switch clear, envelope headroom, every resume a ledger row). [landed 89051371]

#### wheel-agents-talk-up-down-and-across

- A cut landing on a spoke makes the live session's next prompt a closeout: the UserPromptSubmit hook sees .cut-status.json newer than the session's registered cut, injects one block ("cut <sha> applied at <t>; this session is on <old>; finish the turn, then exit -- wcl <spoke> relaunches on the new rules") and the session-end handoff records cut_relaunch_required; wcl <spoke> after that runs the full sequential warmup (compile, drift, arrival audit, secrets, freshness, persona handoff) and refuses to launch a session on a stale cut. [landed 2cfce55a]

## Cut 6e237e8f -- received 2026-09-17 09:49Z (from 8e61551f)

Cut 6e237e8f received (from 8e61551f), posture absorb_and_report: no circle or hook changed for this spoke.

### 2026-09-17

#### conformance

- wcl-entry-welcome fixture accepts the keystroke remedy on the Rules row

#### src/factory

- When a cut adds a required profile key that has a hub-declared value, the arrival audit SEEDS that key into the spoke's canon/profile.yaml with the hub's value and a dated comment (reported in the absorb commit), so the next launch is ready. [fixtures 42/42; landed 06de36c5, 2942ed72]

#### wheel-agents-talk-up-down-and-across

- scaffoldInstance and every fixture scratch instance declare builder_model_lane / planner_model_lane and origin_code the way the real wheel does -- through the scaffold (one helper, no per-fixture hand copies) -- so the refusals fire only where a real instance is missing them; the governance line fixture asserts the current compiled text; push gate green on main with no baseline change. [landed 02aaefbb]

## Cut 8e61551f -- received 2026-09-17 06:59Z (from c8ec1341)

Cut 8e61551f received (from c8ec1341), posture absorb_and_report: 3 circle(s) gained (zellij-tab-identity-session-end, zellij-tab-identity-tool-reset, zellij-tab-identity-turn-start); 14 changed (calibration-record, cross-provider-verification, dispatch-run-salvage, footer-audit, footer-correction-injection, hf-deploy, notification-agent-waiting-notify, readiness-certification-sweep, session-continuity-checkpoint, session-registry, stop-agent-waiting-notify, tastegraph-injection, warmup-goals-review, wcl-verify-then-launch); hooks bound: PreToolUse preToolTabResetHook.js, SessionEnd sessionEndTabClearHook.js, UserPromptSubmit userPromptSubmitTabHook.js.

### 2026-09-17

#### toast-is-one-short-line-per-turn  (at review -- certification pending)

Challenge: Operator, 2026-09-16, after the fleet toast landed: "the toast notifications still seem off -- make sure they are clear and simple." MEASURED on basher (session otter, hook-runlog 02:36-03:47Z): every turn produces TWO toasts -- the Stop toast, then ~60 s later Claude Code's idle_prompt Notification fires notificationNotifyHook, which toasts again with sound Alarm2 (ms-winsoundevent Looping.Alarm2, loops until dismissed) for a turn that merely finished.
Solution: One toast per turn at most, one short line. idle_prompt never toasts on its own (Stop already said "done"; the tab glyph still updates) -- it toasts only when a pending question or permission prompt exists. Body by reason: stop -> "Done -- waiting for you"; permission_prompt -> "Needs permission: <Claude Code's message, 120 chars>"; pending_question -> "Question: <text, 120 chars>"; failure -> "Turn failed -- check the session".
Record: certification pending · fixtures 47/47 · shas 95198938

#### wcl-freshness-refusal-offers-the-remedy-and-scaffold-rule-drift-is-not-local-drift  (at review -- certification pending)

Challenge: Operator, 2026-09-16, at `wcl` in minder: "this is not a helpful end -- dont fail and exit, give options or take action to remediate." The row read `Rules canon edited since its cut -> revert the local edits` and wcl exited 1.
Solution: (1) pendingCutVerdict classifies an edited/added/deleted file as LOCAL only when it differs from the recorded cut's own source for that circle: a yaml that loads structurally equal (ignoring duplicate_of) to the recorded source, or an .md byte-equal to it, is cut-produced and the verdict is pending -- step 3 applies it. (2) In compact TTY mode a freshness refusal renders the rows, then a chip menu: `a` revert canon/circles to the recorded cut and apply the current cut (behind confirmChip naming every file that will be discarded), `d` show the per-file diff, `q` exit 1.
Record: certification pending · fixtures 48/48 · shas cc8ef71c

#### zellij-tab-identity-and-gated-toast-are-a-fleet-circle  (at review -- certification pending)

Challenge: MEASURED 2026-09-16: every wcl session runs with CLAUDE_CONFIG_DIR at the spoke's .local/provider-claude-config, a cut-generated mirror of .claude/settings.json (41 harness-factory hooks, zero spoke hooks). basher's v1 zellij tab writer (glyph + spoke name + folder ordinal on the tab, pane title, pane<->transcript map, toast gating, sound by reason) is registered only in ~/.claude/settings.json, which a wcl session never reads (globalSettingsPreview.js:163).
Solution: Tab identity and the gated toast are one fleet mechanism every spoke gets with the cut. zellijTabIdentity.js (node only) sets `<glyph> <name><-n>` on the tab and the pane title: working on UserPromptSubmit and on the first tool call after a permission prompt, done on Stop / idle, blocked on permission_prompt, failed on StopFailure, idle on SessionEnd (never over an unacknowledged attention glyph); keeps the v1 sidecar paths under /tmp/claude-sessions so basher lens still reads them; skips lens-sentinel tabs; no-ops outside zellij. agentWaitingNotify gains the v1 gate (300 s quick-turn, 60 s presence; permission / failure / pending question always fire), reason -> sound, a tab-matching title, and a static toast.ps1 launched -File and detached so Stop never waits on PowerShell.
Record: certification pending · fixtures 75/75, 34/34, 9/9, 31/31, 22/22, 28/28, 11/11, 48/48, 155/158 · shas 64bbef64

#### circles

- Circle wheel-change-log declared: the wheel's Change Log is rendered -- `hf changelog [--since=<date|sha>] [--until=<date|sha>] [--spoke=<name>|--wheel] [--view=operator|technical] [--write]` (src/cli.js -> src/factory/changeLog.js runChangelogCommand, or scripts/changelog.js on a spoke) on demand, and the hub wheel-clock job wheel_change_log (JOB_RUNNERS.regenerateChangeLog, runChangeLogJob) on the deploy_fleet cadence, so a fresh cut is followed by a fresh docs/CHANGELOG.md
- Hook bound on PreToolUse: zellij-tab-identity-tool-reset.
- Hook bound on SessionEnd: zellij-tab-identity-session-end.
- Hook bound on UserPromptSubmit: zellij-tab-identity-turn-start.
- Circle zellij-tab-identity-session-end declared: the session ends -- the tab goes back to idle unless it still needs a look
- Circle zellij-tab-identity-tool-reset declared: the first tool call after a permission prompt the operator answered
- Circle zellij-tab-identity-turn-start declared: the operator submits a prompt -- the session is working again

#### wheel-agents-talk-up-down-and-across

- One cut-owned persona definition, reference/personas/max.md, on every spoke: Max maximizes sub-agent issuance (every independent ready lug dispatched in parallel on the builder lane up to the lane ceiling, walk one before fanning out), optimizes delivery (fold pipeline, gate load, cost per lug measured and reported) and improves (one improvement lug per session from its own misses, disputes and refusals). [fixtures 32/32; landed 9c297e7f]
- The hub profile declares builder_model_lane (wheel-wide, every spoke must match, like permission_mode) beside the interactive model_lane. executeDispatch resolves option -> row -> profile and REFUSES a dispatch with no resolvable lane or one equal to the planner's lane, unless --lane-override=<reason> is given and written as a default-forward veto row. [landed 051c2f0f]
- canon/profile.yaml gains permission_mode (validated against the modes the installed claude accepts; default auto, the mode the operator runs the hub in); wclCli.js passes --permission-mode <mode> beside --model <lane> on every interactive launch, resolved through the same resolveModelLane-style reader; the hub profile and every spoke profile declare the same value; a launch whose profile omits it refuses with the field named, never silently defaults. [landed b7fbb429]

#### commits

- statusline fixture: the custodian's copy without the v2 path is basher's port, not this tree's red
- zellij tab identity: the three hook circles bound on the canonical checkout (compile-self --standing after the fold of 64bbef6); basher's two lugs (zellij tab identity, wcl freshness remedy) committed here at review

#### wilbur-d-custodian-timeline-otto-steering

- Every registered spoke carries docs/CHANGELOG.md as a cut-owned generated artifact (the cut regenerates it, the arrival audit absorbs it, hand edits are refused like CLAUDE.md), with two parts: the spoke's own history (its lugs done, its cuts received with version and what each cut changed for it -- circles gained/bound, policies, hooks -- its dispatches, its own commits) and the wheel's history that reached it (framework functionality landed per cut, in operator words). [fixtures 39/39, 34/34, 48/48, 33/33, 20/20, 11/11, 13/13, 51/51, 32/32, 25/25; landed 40a4f53d]
- `hf changelog [--since=<date|sha>] [--spoke=<name>|--wheel] [--view= operator|technical]` renders a Change Log from the record layer only -- git log of main (commit subjects, the lug each names), lugs that reached done with their certified_by receipt, cuts published (registry/latest- cut.json history, .cut-status.json per spoke), circles added or bound (circle audit deltas), dispatches completed (dispatch registry) -- one dated section per day, operator view in plain words (what a session can now do that it could not), technical view with shas, lugs, fixtures and counts. [fixtures 12/12, 34/34, 31/31, 28/28, 57/57, 3 passed; landed 4c791cce]

#### session-entrance-exit-ux

- Per-section goals-review/checkpoint results cached in the spoke's runtime/goals-review-cache.json, keyed on each section's DECLARED input files (mtime+size) and the ledger's row count; a hit reads no section input; any key move recomputes that section only; runlog rows for warmup-goals-review under 2,000ms on wheel-hub across three consecutive real sessions. [landed cc0ee90e]

#### src/advisor

- Every certification record and attempt carries matcher_version (a hash of fabricationCheck.js's tier table + the policy constants, exported from the module) and the replay can say "judged by <version>". [landed 280fbb6f, 66156307]

#### src/conductor

- success-prediction registry path leaves the roiExtraction<->successPrediction import cycle

#### src/factory

- push 30's two reds: closeout-report E2 judges live-peer telemetry movement as live state (the hub is a live instance; 8 of 8 attempts moved only telemetry beside an Otto session); a `// timing` head marker makes session-exit-path a timing suite for the gate's alone re-run (fixed-second budgets race the box; red at load 6.6, 102/102 alone)

#### src/lugTracking

- disclosed-gap scan excludes the generated change log: docs/CHANGELOG.md quotes historical commit subjects and lug outcomes verbatim; its first regeneration raised 9 findings, all the past's own words

#### src/tastegraph

- A taste miss on turn N is shown on turn N+1 with the offending lines, exactly as the footer correction is, with one reply that applies it or disputes it (a calibration row). [fixtures 999/1000, 54/54, 20/27; landed 5d25a542]

#### taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-footer-does

- The origin-code registry is generated: every canon/<name>.spoke.yaml carries a unique origin_code minted at registration, the compiler writes the registry from them and refuses a spoke without a code or a shared code. [fixtures 41/41; landed 2293f20c]

## Cut c8ec1341 -- received 2026-09-17 00:02Z (from 21926af8)

Cut c8ec1341 received (from 21926af8), posture absorb_and_report: 1 changed (cross-provider-verification).

### 2026-09-16

#### conformance

- session-exit-path runs serial-first: its H.3-H.5 checks race a 12s commit-gate budget against a 15s covering suite and went red on push 28 at load 4 (13s measured) while 102/102 alone at load 1.3 -- the `// serial` marker gives it the alone run and the alone re-run before NEW RED

#### low-trust-multi-provider-verification

- A citation whose every fragment is real bundle text matches (joined multi-line code across consecutive lines, runner prefix, yaml-as-json, bundler-written lines). [fixtures 1/3; landed c8ec1341]

#### wcl-launches-on-the-global-sign-in-spokes-hold-only-local-settings

- A provider call from an interactive session (or the operator's shell) resolves the fleet's secrets from the one canonical store, <frameworkRoot>/.local/secrets.json, when no CLAUDE_CONFIG_DIR is set and no bag is passed -- stated on the record as source: framework-store -- while a fixture or a headless launch with a scratch config dir still never reaches the operator's real secrets (B2 stays as it is). [fixtures 4/17, 21/21; landed 78877646]

## Cut 21926af8 -- received 2026-09-16 19:29Z (from 79c1648d)

Cut 21926af8 received (from 79c1648d), posture absorb_and_report: 4 circle(s) gained (closeout-report, closeout-request, lug-write-schema-gate, session-files-touched); 12 changed (agent-tool-scope-guard, bash-lug-guard, communication-inbox-delta, gate-pool-serial-suites, hf-deploy, max-persona-boundary-guard, session-continuity-checkpoint, session-end-handoff, session-exit-commit, success-prediction, warmup-goals-review, wcl-verify-then-launch); hooks bound: PostToolUse filesTouchedRecorderHook.js, PreToolUse lugSchemaGateHook.js, UserPromptSubmit closeoutRequestHook.js.

### 2026-09-16

#### circles

- Circle closeout-request declared: a real prompt is submitted (UserPromptSubmit) and, read clause by clause, it asks to end the session -- a phrase from canon/closeout-request-phrases.yaml (end here, wrap up, close out, closeout, lets end) with no negation guard earlier in its clause and no code path, identifier or backticked span in that clause
- Hook bound on UserPromptSubmit: closeout-request.
- Circle closeout-report declared: the operator asks to end a session and the agent audits the closeout before /exit -- `node scripts/closeout.js --session-id=<id> [--json] [--cwd=<dir>] [--transcript=<path>] [--remote-timeout=<ms>]` in any spoke that received the cut; buildCloseoutReport (src/lugTracking/closeoutReport.js) is the one composer, and X2's closeout-request injection (out of scope here) is its intended in-session caller
- Circle lug-write-schema-gate declared: a Write, Edit or NotebookEdit call is about to land on lugs/*.yaml, in any session -- top-level or dispatched, at any lug state
- Hook bound on PreToolUse: lug-write-schema-gate.

#### session-entrance-exit-ux

- One terminal line per exit, always, naming what landed and what did not, with a fixture for the clean, refused and unpushed cases. [fixtures 42 passed; landed 9d06435e]
- Handoff schema and writer accept findings[]; the checkpoint hook rechecks and retires; a fixture proves a deferred unpushed-commit finding is retired after the push lands and an unresolved one is printed. [landed f90947f7]
- A canon circle + hook in harness-factory, cut to spokes; a fixture proving the phrase match, the negation miss, and that the injected block names the closeout script and the act-or-defer rule. [fixtures 48/48; landed ede4ebd9]
- scripts/closeout.js --session-id=<id> [--json] in harness-factory, cut to spokes. [landed 83bec491]

#### src/basher

- wcl launches interactive sessions on the operator's global config (~/.claude, basher-managed: credentials, global settings, model default) and applies spoke-local settings through the repo's own .claude/settings.json (hooks, permissions, statusline) -- no per-spoke CLAUDE_CONFIG_DIR, no credential copy, no per-spoke sign-in. [fixtures 213/0; landed 203de44c]
- wcl-entry-directive never reaches a dispatched builder -- MAX-161 inherited WCL_ENTRY=ozi from its orchestrator, took the read-only wakeup directive as its own, briefed and exited in 3 minutes with 0 commits
- A timing suite never turns a real push red on load alone: the two suites derive their windows from measured load as well as slack (or state the load they refuse to judge under and SKIP with the number, never FAIL), and the gate re-runs a red timing suite once, alone, before calling it NEW RED -- reporting both runs and the load at each, so a real regression still refuses and a flake is named as one. [fixtures 3/3, 57/57, 43/43; landed b4e6af7f]

#### reference

- closeout-request: circle declared and bound on the canonical checkout (MAX-158's binding.patch, applied after the fold of ede4ebd)
- lug-write-schema-gate: circle declared and bound on the canonical checkout (MAX-155's binding.patch, applied after the fold of dfb0f6b)

#### src/conductor

- success-prediction: the assayer reader reads the coverage ledger the assayer really writes
- success-prediction: the miss routes through the ROI extractor, the clock grades what is due, every canon subject has a readable prediction

#### src/factory

- A circle can bind a hook that is not a node script. [fixtures 35/35; landed 7e029800]
- session-exit-commit returns the shared checkout to the branch it found after a red exit -- fox-skunk's refused red exit left this checkout on wip/2026-09-16-fox-skunk and the next session (porcupine) committed 8995713 there believing it was main

#### src/hooks

- A restriction whose object is a verb/action (commit, push, merge, deploy, delete, run, launch) rather than a path binds to THAT action, not to the fork's write surface: the guard records it, and the Bash guard refuses the matching git verb, while file writes stay allowed. [fixtures 64/43, 19/26; landed 2ef974c6]
- lug-write-schema-gate also refuses an unresolved lineage parent at the keystroke -- push 20 was refused on pathfinder's COMMITTED audit-cron-fit-value (derived_from a bare archive path), which the schema alone let through

#### conformance

- two fixtures moved to the global-sign-in contract (model-lane-durable-declaration, secrets-template-migration -- push 26's 3 NEW REDs); lug filed for the gap MAX-163 disclosed: provider secrets for an interactive session with no config dir

#### src/compiler

- A push is refused only for what the pushed tree changed or what the wheel has already committed: the gate snapshots the corpus it will judge (every known repo's COMMITTED lugs/, the hub registry rows) once at gate start, the corpus fixtures read that snapshot, an uncommitted sibling file can never turn this repo's push red, and a corpus red names the repo and commit it came from so the owner is obvious. [landed dfb0f6b0]

### 2026-09-15

#### push-main-blocked-on-taste-injection-digest-contract  (done)

Challenge: From basher session 12d1aba4 (2026-09-15 00:30-01:15). main is 34 commits ahead of origin (through b484121); two pre-push gate runs went 17 NEW REDs -> 4 (wheel-hub 23be24ad certified_by migration, the cut on wheel-hub's disk, porcupine's b484121 cleared the rest).
Solution: Decide, then land one of: (a) the digest is the contract -> the taste-injection check asserts the digest line and states what a first injection says; (b) a first injection carries the full block -> the digest falls back to the block when no prior refresh is recorded. Default if nobody rules: (b), because "unchanged" is false on a first injection.
Record: CONFIRMED via claude (reviewer c2e8739d) · fixtures 1 fixture(s) · shas b2fae708, 5c99d268

#### session-exit-commit-sweeps-a-peer-lanes-in-flight-files  (at review -- certification pending)

Challenge: 2026-09-14 20:15-20:18 on the shared harness-factory main checkout: a peer session's SessionEnd exit-commit (src/hooks/sessionExitCommitHook.js) committed ANOTHER lane's uncommitted work -- basher s128's in-flight src/basher/wclEntry.js and the wcl-entry-welcome fixture (the chip-menu /dev/tty fix, mid-verification) -- as "Session work: 3 files, no lug transitions recorded" (5bd3432, and 385a6cb before it).
Solution: The exit-commit hook commits only files this session touched: it reads the session's own runlog / turn markers (files_touched) and stages that set; files modified on disk but never touched by this session are left in the working tree and named in the commit trailer as "left for lane <other>". When a file is contended (touched by two live sessions) it is left uncommitted and ledgered, never guessed.
Record: certification pending · fixtures 102/102, 64/64, 40/40 · shas 9a2b46e7, f7155a6a

#### wcl-enters-any-spoke-old-harness-or-unregistered-with-a-real-entry-and-warmup  (at review -- certification pending)

Challenge: Operator, 2026-09-15: "how can I enter a spoke (or new spoke) like pathfinder which is running an old version of the harness -- wcl should give me the proper entry and warmup.." Measured: pathfinder is v1 (wai-enter.sh, inline-bash hooks, no canon/) and registered nowhere (known-repos.json, hub spoke entities, wheel.group.yaml).
Solution: `wcl` in a folder not in the wheel classifies it (v2 | v1 | unscaffolded | not-a-repo) and offers one keypress to INITIATE: git-level consolidation first (clear the noise), then upgrade ALL THE WAY to v2 (scaffold, register, apply the current cut, retire the v1 hooks), then the normal entry -- never a silent exit 1. Operator ruling 2026-09-15.
Record: certification pending · fixtures 44/44 · shas 6f6504bc, 5f0aad13

#### wcl-signs-in-with-a-long-lived-fleet-token  (at review -- certification pending)

Challenge: Operator, 2026-09-14 (basher s128): "I cant successfully exit or reenter ... if you can automate the action i prefer that over directions.." Every spoke's isolated store (.local/provider-claude-config) needs its own OAuth sign-in, and copying ~/.claude's tokens diverges on refresh (FBL-046).
Solution: One sign-in for the fleet. `claude setup-token` yields a long-lived subscription token; wcl stores it once (1Password op://Dev/Basher/ claude_code_oauth_token when `op` is available, else <frameworkRoot>/.local/secrets.json, mode 0600, value never printed) and injects it as CLAUDE_CODE_OAUTH_TOKEN into every launch (raw, ozi -p and -c).
Record: certification pending · shas 2ef4a2a9

#### src/basher

- wcl: one global sign-in -- the fleet token resolves from and is stored in the framework checkout's .local/secrets.json (WCL_FLEET_ROOT overrides; spoke-level store kept as fallback), new verb wcl signin runs claude setup-token from any folder; operator 2026-09-15: login was per spoke
- wcl upgrade: gitignore .local/ before the first cut -- found live on pathfinder, where the launch's arrival audit committed 455 files of the composed provider config dir; fixture asserts check-ignore on a composed .claude.json
- wcl upgrade: retire-v1 lug carries out_of_scope (lug schema work-type clause) -- found live on pathfinder's first launch, where the cut re-apply rolled back on the schema-invalid lug; fixture now compiles the upgraded spoke refuse-free and re-applies the cut
- wcl: a linked worktree's git identity outranks its basename -- the push-gate worktree <tmp>/push-gate-harness-factory-<sha>/harness-factory served the main checkout in its own place
- wcl: sign in BEFORE launch when the store is unsigned; fleet-token capture survives Ink line-wrap and is verified before it is stored
- wcl: one sign-in for the fleet -- a long-lived token, stored once, injected into every launch; `s` sets it up from the menu

#### src/factory

- A timing suite never turns a real push red on load alone: the two suites derive their windows from measured load as well as slack (or state the load they refuse to judge under and SKIP with the number, never FAIL), and the gate re-runs a red timing suite once, alone, before calling it NEW RED -- reporting both runs and the load at each, so a real regression still refuses and a flake is named as one. [fixtures 39/39, 66/66; landed 93e4c1a7, 6af0f848]
- A gate and an oracle sweep never run the corpus together: whichever starts second sees the other's lease and either waits (gate: bounded, with the holder named) or yields (oracle: skips this tick with a ledger row naming the gate it deferred to). [fixtures 272/272, 44/44, 31/31, 66/66, 50/50; landed 0117742b, ab87b73f]
- A wip/ branch is a foldable branch: hf deploy --stage fold (and the by-hand recipe) classifies wip/* beside dispatch/*, the same cherry-pick-onto-integrate path folds it, clean removes it once every commit is on main by patch id, and the session-exit-commit ledger row names the fold command that will consume the branch instead of leaving it as an orphan the operator has to discover with `git branch --list 'wip/*'`. [fixtures 26/0, 67/0, 71/0, 102/0, 8 passed; landed e1f9b302, 565cfe4f]
- push gate: the ratchet baseline and suite timings (gitignored runtime/) are copied into the clean push-gate worktree -- the first real ref-gate run (dbfff96) judged 18 baselined reds as 'failing and this repo has no ratchet baseline'; integrator fix on main by session 4f1a0301, fixture 70/70
- The real data-integrity failure recorded in ledger row ldg-p0-circle-audit-conversation-track-ingestion-1789111866697-5no2 (source_ref: circle-audit, 2026-09-11) is fixed at its real cause -- the same check that produced this P0 row no longer reports it on a clean re-run, and no other code path can reproduce it silently. [landed 04737711]

#### commits

- communication lug to basher: wcl-enters-any-spoke-old-harness-or-unregistered-with-a-real-entry-and-warmup -- 13 v1 spokes and 3 unregistered v2 spokes under the project roots that wcl cannot enter today (pathfinder measured)
- retire the origin copy: promoted to wheel-hub and done there (506433a5)
- basher's blocker lug overtaken (defined -> ready -> review: f2477c8 landed its option b, pushed 271/271); peer lug's review edit committed; lug filed: harness-factory has no Proofer, so a non-proof_required lug can never reach done

#### .claude

- session-exit-commit: bounded to Claude Code's real ~60s window -- 12s commit-gate budget, never push at exit, 45s wall cap; the prior "Session work: 10 files" commit (5d6266c) carries the code
- compile-self --standing after the wcl-entry-directive fold: SessionStart binding for src/hooks/wclEntryDirectiveHook.js (UserPromptSubmit order is the compiler's canonical order)

#### advisor-pattern-hub-managed-spoke-leveraged

- A push is judged on the tree being pushed, never on whoever's dirt is in the working directory; a second live session on a checkout works in its own registered worktree from the moment it starts; main is written only by the fold (integrator), so two sessions cannot race a commit; and every refusal or lock wait names the other session instead of the operator. [landed 79bbcc1e, 5bdcc37f, 84b79fb6]
- A top-level session's write whose target resolves inside a registered repo other than the session's own (canonical checkout, not a worktree or scratchpad) is refused at PreToolUse regardless of posture -- Write, Edit, NotebookEdit and write-shaped Bash alike -- with the refusal naming the two sanctioned paths: file a communication lug targeting that repo, or dispatch a worktree-isolated build from this session; the refusal is a ledger row on BOTH repos. [fixtures 25 passed; landed a57be628]

#### circles

- Circle session-files-touched declared: a tool call that can write completes (PostToolUse on Edit, Write, NotebookEdit, Bash)
- Hook bound on PostToolUse: session-files-touched.

#### lugs

- A push is refused only for what the pushed tree changed or what the wheel has already committed: the gate snapshots the corpus it will judge (every known repo's COMMITTED lugs/, the hub registry rows) once at gate start, the corpus fixtures read that snapshot, an uncommitted sibling file can never turn this repo's push red, and a corpus red names the repo and commit it came from so the owner is obvious. [landed 9633b378]
- wcl launches interactive sessions on the operator's global config (~/.claude, basher-managed: credentials, global settings, model default) and applies spoke-local settings through the repo's own .claude/settings.json (hooks, permissions, statusline) -- no per-spoke CLAUDE_CONFIG_DIR, no credential copy, no per-spoke sign-in. [landed 862d5c33]

#### review-transition-certifies-before-the-session-commits-so-the-bundle-never-sees-the-work

- A harness-factory lug without proof_required reaches a real Proofer: the Proofer entity resolves through the registered wheel-hub when the instance declares none (the same cross-repo fallback resolveGovernancePrompt in src/lugTracking/sessionCheckpoint.js already uses for the track-governance prompt), the record names which canon the Proofer came from, and a spoke with no hub reachable gets an explicit BLOCKED naming both places it looked -- never a silent skip and never a copied advisor entity in this spoke's canon. [fixtures 38/38, 9/29, 25/25, 92/92, 65/65; landed 7d34a7ef]
- Every done carries certified_by {reviewer_session, provider, model, verdict, record, at} independent of the author on the session axis and model-or-provider; the done gate refuses otherwise for every priority; certification launches and verdicts are messages to the spoke that the inbox delta prints at the next prompt; the goals review counts the window's done lugs by receipt; certification for dispatched work runs at the fold, requested by the fold, never by the author session. [fixtures 143/150, 88 passed, 95 passed, 152 passed; landed dbfff960, df2e4aa4, ab29eb02]

#### src/advisor

- provider-contract: the Proofer prompt rides argv under 100 KB and stdin above it -- the all-stdin form (e87e93c) broke five stub-claude fixtures with EPIPE
- Proofer prompt goes over stdin (E2BIG on the first hub-resolved call); taste-injection's first-sight check names the contract it asserts; basher's lug carries its pointers and verification

#### conductor-autonomous-loop

- classBalance.js reads shortfall from the policy; when a class's rows run out mid-cycle its remaining floor is redistributed to the classes that still have rows in proportion to their declared floors; the cycle artifact records the redistribution per class. [fixtures 69/69, 33/33, 5/0, 2/0, 15/0, 4/0, 3/0, 4/3; landed d1db3553]

#### conformance

- two source-shape checks on stageFold updated for the wip/* fold (e1f9b30): worktree-registry B5 reads the whole function, not a 6000-char window; receipt F8 accepts folded.filter(has lug).map

#### scaffolded-spoke-ships-schedule-circles-with-no-wheel-clock

- applyCut on a spoke with no clock of its own writes the canon default clock as canon/spoke.wheel-clock.yaml (never overwriting an existing clock, never adding a second), the excluded schedule circles arrive with it, and the arrival audit names the clock as an absorbed file. [fixtures 15 passed; landed 979153cd]

#### session-entrance-exit-ux

- Operator 2026-09-14: define E2 as the board. [landed 26aef712]

#### src/lugTracking

- push gate's third run: first-sight TASTES collapsed to its own refresh stamp (26aef71); check-ignore refused through the gate worktree's symlinked .local

#### three-suites-flake-only-inside-the-gate-pool-and-block-every-push

- A fixture that reads a real spoke's checkout asserts consistency with that spoke's own recorded state (cut-status, registry), never a literal; a lint in the commit gate names any fixture that pins a path under the real spoke roots with a literal expectation; the generated-docs drift check runs in the commit gate's always-run set so stale CLAUDE.md never reaches the push gate. [landed 759ff3ea]

#### harness bookkeeping

- 6 harness bookkeeping commit(s) in harness-factory (Session work 6).

## Cut 79c1648d -- received 2026-09-15 03:42Z (from f40bc3fe)

Cut 79c1648d received (from f40bc3fe), posture absorb_and_report: 1 circle(s) gained (wcl-entry-directive); 1 removed (conversation-track-ingestion); hooks bound: SessionStart wclEntryDirectiveHook.js.

### 2026-09-15

#### wcl-entry-is-a-welcome-raw-or-ozi-wakeup  (at review -- certification pending)

Challenge: Operator, 2026-09-14 (basher s128): "improve the entry via wcl so it is more delightful and user can choose a raw session or to allow Ozi to wakeup and advise options. This is too rough - i want joy and delight." wcl printed an eleven-line status dump and launched Claude Code cold: nothing speaks until the operator types, even though SessionStart already injects the continuity checkpoint and goals review -- Ozi's wake material is loaded and silent.
Solution: On a TTY, wcl greets (time of day, spoke, cut, dir), folds every ok step into one ready line (re-folding between attention lines) and prints only non-ok steps in full with their fix; then a single-keystroke chip menu -- 1/r Raw session or 2/o Ozi wakeup (recommended, Enter). Ozi runs one headless `claude -p` wakeup turn (briefing + options stream to the terminal), then `claude -c` opens the session with it already inside.
Record: certification pending · shas 67676f94

#### wcl-rows-are-assured-capabilities-and-entry-matched-injection  (at review -- certification pending)

Challenge: Operator, 2026-09-14 (basher s128), on the first welcome cut (9c2007a): "each row should be a feature/capability that is assured. Codebase is ready or not ready (remediating action). I dont care if hooks are 37 but id like to know that the workspace is ready to be used (if not remediating action).... and on entering the session the prompt injected that matches either raw or wakeup to make best use of users time.." The compact view still folded MECHANISM names (git · rules · hooks (37) · custody) and the launched session had no idea which entry the operator chose.
Solution: Compact rows are capabilities, one each, in this order -- Codebase (git sync), Rules (canon freshness + cut + generated docs), Workspace (hook resolution + config custody + secrets), Sign-in (credential preflight) -- rendered `✓ <Capability> <assurance>` when ready or `▲ <Capability> <what is not ready> → <remediating action>` when not; a wcl-applied cut reads as ready ("current, cut <sha>"), a held cut and stale docs read as ▲ with the action. Full step text stays under --verbose / --dry-run (unchanged strings).
Record: certification pending · shas bbc6c01c

#### circles

- Hook bound on SessionStart: wcl-entry-directive.
- Circle wcl-entry-directive declared: a session starts

#### src/basher

- wcl: rows are assured capabilities; a SessionStart circle injects the entry-matched opening contract
- wcl: the entry is a welcome -- raw session or Ozi wakeup, one keystroke

#### .claude

- compile-self --standing after the wcl-entry-directive fold: SessionStart binding for src/hooks/wclEntryDirectiveHook.js (UserPromptSubmit order is the compiler's canonical order)

#### lugs

- The exit-commit hook commits only files this session touched: it reads the session's own runlog / turn markers (files_touched) and stages that set; files modified on disk but never touched by this session are left in the working tree and named in the commit trailer as "left for lane <other>". [landed 79c1648d]

#### repo root

- regenerate-docs: live circles 92 -> 94 (worktree-registry from 41896a7, wcl-entry-directive from 6f531ab)

#### review-transition-certifies-before-the-session-commits-so-the-bundle-never-sees-the-work

- Every done carries certified_by {reviewer_session, provider, model, verdict, record, at} independent of the author on the session axis and model-or-provider; the done gate refuses otherwise for every priority; certification launches and verdicts are messages to the spoke that the inbox delta prints at the next prompt; the goals review counts the window's done lugs by receipt; certification for dispatched work runs at the fold, requested by the fold, never by the author session. [landed db69e054]

#### harness bookkeeping

- 4 harness bookkeeping commit(s) in harness-factory (Session work 4).

## Cut f40bc3fe -- received 2026-09-15 00:14Z (from 66e48e3a)

Cut f40bc3fe received (from 66e48e3a), posture absorb_and_report: no circle or hook changed for this spoke.

### 2026-09-15

#### lugs

- A circle can bind a hook that is not a node script. [landed f40bc3fe]

## Cut 66e48e3a -- received 2026-09-15 00:11Z (first cut)

Cut 66e48e3a received (first cut), posture absorb_and_report: no circle or hook changed for this spoke; policies changed planner-class-floors.

### 2026-09-14

#### wcl-cold-start-store-is-a-condition-not-a-lockout  (at review -- certification pending)

Challenge: wcl refused every launch of basher for nine days (5 preflight_refusal rows, 2026-09-05..14) with "no real claudeAiOauth accessToken/refreshToken".
Solution: An interactive wcl launch on a missing/unauthenticated/refresh-expired store says NEEDS LOGIN, states the condition (sign in when prompted; the login lands in this spoke's own store once, never copied from ~/.claude again) and launches. REFUSED is reserved for what a sign-in cannot fix (corrupt file) and for headless dispatch (nobody there to answer).
Record: certification pending · shas 8e4f1ff4

#### circles

- Circle secrets-template-migration declared: a spoke's .env.template meets the secrets manifest -- `wcl <spoke>` step 5 on a spoke with a template and no canon/secrets.manifest.yaml (runSecretsMigrationStep, src/basher/wclCli.js); `node scripts/secrets.js migrate|fallbacks|retirement|show [<spoke>]` on demand; getSecret's cache miss (src/basher/secrets.js, the dual-read); and every applyCut (src/factory/cutUpdate.js), where the measured retirement runs
- Circle worktree-registry declared: a git worktree is created, removed, judged or handed off by the harness -- addWorktree/removeWorktree (src/factory/worktreeRegistry.js) at every `git worktree add` in src/ (rollbackCut's pinned checkout, hf deploy's fold integrate tree, stageClean's removals); `node scripts/worktree.js add|list|remove|reap` by the orchestrating session in place of raw git; healthSignals.js's stale_worktree signal on every Planner cycle; and buildHandoff at every session end
- Circle farming declared: a solution recurring across spokes is detected, abstracted, promoted or demoted -- detectRecurrence / proposePromotion / proposeDemotion / certifyHarvest / applyHarvest / auditPromotions (src/otto/farming.js), run by `node scripts/farming.js detect|propose|demote|certify|apply|audit`; and every session start, where buildFarmSection reports through goalsReview.js
- Circle communication-inbox-delta declared: a real prompt is submitted (UserPromptSubmit), and the hub's messages/messages.jsonl or lugs/ holds a row addressed to this spoke that this session's cursor has not shown
- Hook bound on UserPromptSubmit: communication-inbox-delta.
- Circle communication-inbox declared: a session starts -- every SessionStart composes the goals review (buildGoalsReviewInjectionParts, src/conductor/goalsReview.js), which reads the inbox live and prints the one digest line, and the SessionStart wheel-clock catch-up fires the job when a tick is owed -- and the spoke's wheel_clock job communication_inbox (JOB_RUNNERS.communicationInbox) on its declared cadence, for the out-of-session loop: the spoke reads every sibling spoke's lugs/ for type: communication lugs whose target_spoke names it and whose status is still open (not fulfilled / declined / closed), ranks them through rankCommunicationInbox (src/conductor/readyWork.js, the ONE ordering the ready-work queue, the senior inbox and the advisor inbox all call), and writes only its own runtime/communication-inbox.json
- Circle lug-ownership-claims declared: a lug's ownership is claimed, contested or diverged -- applyLugVerb (src/lugTracking/lugVerb.js) appends a claim at in_progress and a release at review/done, refusing a lug another LIVE session holds unless --drive=<reason> or --collaborate=<sub-scope>; `node scripts/lug-claim.js list|contend|release` reads the table on demand; the four lug-write guards (bash-lug-guard, definition-complete-gate, ready-gate-stub, lug-lifecycle-tracker) refuse a write to another live session's claimed lug through src/hooks/lib/claimGuard.js; the session-end handoff releases what the ending session held; lugIntegrity.classifyViolation, a dirty-file takeover or `node scripts/lug-divergence.js resolve` write or settle runtime/divergences/<id>.json

#### conformance

- secrets-template-migration fixture names its root REPO_ROOT: circle-completeness-audit resolves an on_demand circle's entry point from that construction, so the FRAMEWORK_ROOT spelling read as PHANTOM on the hub (92/93) and refused the push; hub audit now 93/93 with 0 phantom
- pending-cut-verdict fixture: the real-spoke section asserts consistency with each spoke's own .cut-status.json instead of a pinned snapshot -- it pinned "minder: no recorded cut" and went red the same afternoon minder took its first cut (48746ea); basher will move on every hf deploy the same way
- The wheel clock's declaration can grow again without breaking rule 11, and canon/otto.advisor.yaml is back under the cap. [fixtures 117/1, 84/2, 67/0, 12/17; landed 85216107]
- position-map runs serial-first: it composes the map twice against the real wheel-hub and asserts the two agree; inside the gate pool another suite can write into the hub between the calls (NEW RED on two consecutive 260914 push gates, 36/36 alone) -- the gate-pool-serial-suites marker, not a retry
- A hook_event circle declared on a dispatch branch can prove its own binding from that branch: the scaffold-and-launch fixture (or the commit gate's scaffold step) compiles bindings from the branch's own canon when run inside that worktree, so the declaring commit passes its gate before the fold, and hook-binding-drift stops reporting a circle as unbound when the only reason is an unfolded branch. [landed 64ad1620]

#### src/lugTracking

- Done (MAX-093, harness-factory 85fa322 + c176901, hub cut e0921527). [landed c1769015, 85fa3221]
- A claim table records who had a lug first; a second session reaching for it is told the owner, the owner's step and a collaborate-or-drive recommendation with its reason before it writes; a divergence between two sessions' versions of one lug is a record with both sides and a value/impact reading, surfaced at session start and resolved through a verb -- never silently overwritten. [landed d55a2986, 5ebda53d]
- honestNullMarker: drop the operator's name from a code comment -- rule 13 (no-personal-leak) flagged the shipping artifact and refused every wheel-hub push through the cross-repo conformance check
- The done gate accepts a tokens: null marker when a stop-turn-marker cost-unmeasured ledger row names the same lug within 5 s of the marker's timestamp; the lug's cost carries the measured subtotal and an explicit count of such markers with their recorded causes; the ruling amendment is on the ledger; the blocked lug reaches done through the verb. [landed 547e5270]

#### conductor-autonomous-loop

- classBalance.js reads shortfall from the policy; when a class's rows run out mid-cycle its remaining floor is redistributed to the classes that still have rows in proportion to their declared floors; the cycle artifact records the redistribution per class. [fixtures 5/0, 2/0, 15/0; landed dc0ee4f0]
- Every cycle emits one interleaved AP queue over the classes initiative_build, build, maintain (advisor runs) and health, by deficit against floors declared in canon; dependency-aware inside a class with dependency-free siblings marked as a parallel wave; a gate-closed build row is moved to the operator queue with the sweep's reason; health rows come from real signals and carry the command that clears them; Planner runs on every spoke's clock. [landed d1772266]
- Every planner cycle writes operator_queue beside the AP queue -- one row per lug the machine cannot advance, with blocker class, evidence, the one action that unblocks it and what it unblocks, ranked by unblocked weight then priority; printed at session start and by scripts/planner-cycle.js --operator-queue; a row leaves only when its source condition clears. [fixtures 997/1000; landed c3b01a62]

#### src/factory

- Every worktree the harness creates (dispatch worktrees, rollbackCut's temp, cut-apply scratch, any proof checkout) is registered in runtime/worktrees.jsonl with session id, prompt id, purpose, created_at and expiry; the creator removes it on its own exit path; the Planner's health signal reads the registry, names an unregistered worktree as such, and gives the clearing command per row; a session-end handoff lists the worktrees the ending session still holds. [landed 41896a70]
- An operator can bring a stale spoke current with a real, named command, without weakening the launch-time refusal that protects against genuine tampering. [fixtures 0/0, 4/5, 47/47, 58/58, 23/23, 20/20, 7/7, 11/11, 48/48, 27/27, 0/1; landed 96df6d22]
- A spoke scaffolded from the current cut either gets the advisor canon its own scheduled circles need, or does not receive circles it cannot run. [fixtures 33/33; landed 06bdf9c4]

#### wheel-agents-talk-up-down-and-across

- The inbox circle in canon, cut to spokes; rankCommunicationInbox exported from readyWork.js; a fixture with two fixture spokes proving surfacing, fair ranking, one escalation bump, and the three orderings. [fixtures 46/46, 44/46; landed f911fc58]
- A UserPromptSubmit hook (canon circle, cut to spokes) reading messages/messages.jsonl and the hub's ledger for rows addressed to this spoke newer than a per-session cursor in runtime/, injecting one block under 600 chars or nothing, advancing the cursor, never re-injecting; the direction message written tonight (direction-driving-initiative-keystone-1789371600000, to harness-factory) is the first real row it must deliver. [fixtures 46/46; landed 098115c1]
- communication in LUG_TYPES and STATES_BY_TYPE (pending -> acknowledged -> in_progress -> fulfilled | declined, closed terminal) with the schema's per-type allOf requiring target_spoke, status, requested_at, escalation and one of payload/payload_doc, optional ask (enum incl. second_opinion, goals_needs, halt) and target_advisor; a migration script converting every wheel-hub lug carrying intended_type communication; the kernel verb transitioning status through the same sanctioned path as state. [fixtures 36/86; landed 5b6b48e2]

#### repo root

- planner-class-balance fixture asserts the floors_basis the canon file declares (it pinned "unmeasured_default" and went red the moment the operator confirmed the floors); generated docs regenerated for the policy edit -- the causes of the refused floors pushes; generated docs regenerated for the secrets-template-migration and worktree-registry circles (146 entities)
- generated docs regenerated after the wave-2 folds (planner-class-floors policy, 12 policies) -- run-spoke-drift and the two self-hosting doc fixtures refused the push on the stale CLAUDE.md/AMBASSADOR_BRIEF.md; the four hub lugs that carried an explicit default `type: work` are corrected on the hub side (lug-type-conditional-requirements proves the corpus carries the default, not a migration)

#### src/compiler

- Not started. [fixtures 29/29, 662/662, 26/26, 17/17; landed 48746ea7, c0a5ba9e, 964bbf4e]
- Partial. 2026-09-07: hand-fixed basher's 3 instance files, ported verbatim from minder's own already-fixed copies (minder hit this exact class first, 260902-MAX-014; basher never got synced). [fixtures 16/16; landed 1978fa7b]

#### src/conductor

- farming: detect independent recurrence across spokes, abstract preserving what differed, promote/demote through the cut with third-party certification
- The sweep enumerates lugs at ready with readiness passed as well as lugs at review, and promotes a ready+passed lug through the same done gate the drive uses -- or records, per lug, exactly which gate still refuses it (traceability, tests, cost). [landed e65fbf67]

#### advisor-pattern-hub-managed-spoke-leveraged

- Every spoke's Ozi instructions and wakeup injection carry the split; a top-level session's own implementation edits outside a dispatch are a recorded miss; a sub-agent's work is reported with its validation lines or not at all; a defined lug is in the Planner's queue or names why not. [fixtures 62/62; landed 6b6bde9a, 822deb2f]

#### basher-secrets-remediation

- The template is the manifest's input, never discarded -- a migrate tool derives canon/secrets.manifest.yaml from it (as a proposal when one exists), wcl step 5 runs it when a spoke has a template and no manifest, getSecret dual-reads (cache first, template fallback with one ledger row per fallback), retirement is per spoke and measured (zero fallbacks for max_age x 7 -> template renamed, sha recorded), and all of it ships in the cut so spokes learn it through update-discovery. [fixtures 75/75; landed 7992c253, 0d8a69ba]

#### low-trust-multi-provider-verification

- checkFabrication binds a citation through a quote-normalised tier (backtick, single and double quotes equal), reports a truncated pointer as a citation boundary to the certifier and never scores text past it as fabricated, and classes a citation found in the repo but outside the pinned pointers as unpinned (a bundle gap, not a fabrication); the 6 records re-run through the replay tool bind clean and the 14 real ones stay FABRICATED. [landed b855319b]

#### reference

- communication-inbox meets the declared wheel-clock join (MAX-126 x MAX-127 seam): the circle declares requires_wheel_clock_job: communicationInbox, the canon default spoke clock schedules communication_inbox so every scaffolded spoke gains an inbox (the lug's own intent), and the fixture reads this instance's clock through resolveWheelClock instead of a hardcoded advisor file -- the three suites the push gate refused (communication-inbox 46/46, scaffolded-spoke-wheel-clock 33/33, run-reference-circles 90/90)

#### roi-steered-waves

- An orphaned dispatch is reconciled against real disk evidence -- completed, partial, or unknown -- evidence cited. "Orphaned" describes how the SUPERVISOR ended, never the work's verdict; both stay separately readable. [landed f2e00eb1]

#### src/advisor

- A provider whose verdicts a live ledger ruling marks advisory-only can never reach a blocking gate implicitly. [landed b92fe9e5]

#### src/basher

- wcl: an unauthenticated isolated store is a cold-start condition, not a lockout

#### src/otto

- A SessionStart tick never does work it cannot finish inside the hook budget, and a killed tick cannot cause a repeat spend. [landed 15715745]

#### harness bookkeeping

- 8 harness bookkeeping commit(s) in harness-factory (Session work 8).

### 2026-09-13

#### circles

- Circle gate-pool-serial-suites declared: the commit or push gate runs its suites through the pool (src/factory/testBoundaryGate.js runSuites -> src/factory/suitePool.js runSuitePool): every suite whose head carries `// serial` runs alone before the pool opens and the gate's first report line names them and the pool size; and when the two timing suites (liveness-lease, launch-idle-watchdog) start, they measure the box (src/factory/boxTiming.js) and derive their windows from it before the first supervised child
- Circle tastegraph-injection declared: a real prompt is submitted (UserPromptSubmit), after the wakeup block handed the session the merged tastegraph and a master or overlay change has landed since
- Hook bound on UserPromptSubmit: tastegraph-injection.
- Hook bound on SessionStart: update-discovery.
- Circle rule-12-live-state-report declared: a compile runs against a spoke with lugs (run + warn in src/compiler/rules/12-no-oversized-session-start.js, measured once per compile via ctx.sessionStartMeasurement) -- `hf compile`, `wcl compile`, the commit and push gates, wcl's stale-instance step, applyCut's scratch and real recompiles; and on demand when an operator or session runs `node scripts/acknowledge-live-state.js` to shrink the live-state backlog the warning names

#### low-trust-multi-provider-verification

- Every attempt's citations and per-citation match tier are kept on the record; a replay command rebuilds the pinned bundle and re-runs checkFabrication on any recorded attempt; the replay over today's 14 FABRICATED records names the cause per citation with counts, and the matcher or bundle is fixed for the causes that are not real fabrication. [fixtures 3/3, 34/34; landed 6109154d, 63568466, ec539699]
- A candidate that cannot answer the wave's bundle size stops being tried in that wave: the chain reads a per-provider timeout from the machine record where one is declared, and after a declared number of consecutive timeouts or empty answers in one wave it skips that provider for the rest of the wave, disclosed in every record it skips on. [landed 27dc43aa]

#### repo root

- regenerate-docs after the gate-pool fold
- compile-self --standing after the fold: update-discovery SessionStart binding, regenerated docs

#### conformance

- gate-pool-serial-suites (2/2): the fixture, its twenty-run full-pool record, and the circle declaration

#### conformance-suite-runs-218-suites-serially-22-minutes-on-every-push

- Every circle fixture runs once per gate. run-reference-circles keeps its own verdicts (declaration -> fixture mapping, self-hosting compile) and consumes the outer run's per-suite results when it is a pool child instead of re-executing them; standalone it still runs them itself. [landed e8ad374c]

#### docs

- Rule 11 measures the authored contract (intent, outcome, acceptance, constraints, out_of_scope, pointers, open_questions) and not verb-owned bookkeeping (cost, traceability_evidence, outcome_at_proofer, pickup_reverification, harness_factory_proof, build_record). [landed 93c450dd]

#### done-transition-appends-push-near-cap-lugs-over-rule-11

- `author` is measured as verb-owned everywhere rule 11 is applied -- the compiler rule, the oversized-canon-write-guard and the kernel verb -- and the 8 lugs the verb refused only for the author append reach done through the sweep with no trim. [fixtures 41/0, 105/0; landed 7486c88c]

#### land-to-done

- A declared pointer to an oversized file reaches the provider as a bounded, disclosed excerpt (head, byte count, sha256 of the whole), never as the whole file; the bundle's own report names every truncation; both lugs above get a real verdict on the next re-certification. [fixtures 60/60; landed df7c31fa, 096880ce]

#### roi-steered-waves

- Every run ends with an extractor reading what it did, appending KPIs to its wave record, stating if remediation is owed. [landed a1ca15c9]

#### src/advisor

- fabricationCheck: literal \n/\r/\t markers inside a backtick citation fold to whitespace in normalizeForMatch (recovered from index blob ded1306 -- staged in the main checkout by a finished session at 19:41, lost to a cherry-pick --abort, restored verbatim; cross-provider-verification 92/92)

#### src/compiler

- The hub's compile verdict depends only on canon; the live-state growth of the session-start injection is bounded by count caps in each section that grows with backlog, and the sections that are pure backlog (upkeep misses, vetoable acts, exit-commit rows) are acknowledged by a real mechanism instead of accumulating forever. [fixtures 64/64; landed ac436238]

#### src/factory

- gate-pool-serial-suites (1/2): the three suites that flaked only in the pool run serial-first with measured reasons; timing windows derived from the box; a lease that ran out at the budget's end defers to the wall-clock arm

#### src/hooks

- Every session on the wheel receives the merged tastegraph at wakeup and learns a master change within the session, and the goals review names the tastes a session's own turns violated, so the hub advisor's taste analysis reaches behaviour, not only the ledger. [fixtures 36/36, 64/64; landed 01df7bc9]

### 2026-09-12

#### circles

- Circle update-discovery declared: a real session starts (SessionStart event) in any spoke that receives cuts, and the spoke's wheel_clock job update_discovery (JOB_RUNNERS.updateDiscovery) on its declared cadence -- the spoke compares its .cut-status.json to the hub's registry/latest-cut.json, published by hf deploy's cut stage (src/factory/cutPublish.js, from stageCut); Otto's autopilot records who is behind (src/otto/cutLaggards.js) and the hub goals review prints it
- Circle hf-deploy declared: the orchestrating (non-authoring) session runs `hf deploy [--spokes a,b] [--stage fold,push,cut,relaunch,clean]` (src/factory/deploy.js runDeployCommand) to take the fleet's finished work to every registered spoke; or the hub wheel clock's deploy_fleet job (runScheduledDeploy) finds main proven green with foldable branches or commits ahead of origin and launches fold+push+cut detached
- Circle liveness-lease declared: a supervised dispatched session runs -- the running session calls the one sanctioned refresh (refreshLivenessLease / leaseForStep, src/lugTracking/livenessLease.js, or `node scripts/liveness-lease.js refresh`) before any step longer than its remaining countdown, and the launch supervisor (src/basher/idleWatchdog.js) reads the lease off the lug on every tick of the child's life
- Circle cross-provider-certification-history declared: a cross-provider certification record is written or read -- every writeCertificationRecord (src/advisor/crossProviderVerification.js) from the chain (crossProviderCertify.js, every attempt), the requirement note, the verb's supersession block; readCertificationHistory on demand (node scripts/certification-history.js <lug> [--run=<n>] | --migrate | --summary); and summarizeExternalChain at session start
- Circle readiness-certification-sweep declared: the review-state backlog is swept for real check results -- `node scripts/readiness-sweep.js [instanceRoot] --session-id=<id> [--certify=none|request|run]` walks every state:review lug in scope (critical first, then the lugs that unblock the most others), re-runs each lug's own conformance fixture, reads the done gate through the harness's own functions, and asks the kernel verb for done
- Circle done-gate-two-store-certification declared: a qualifying lug (high/critical AND proof_required) transitions into done -- checkCrossProviderGateForDone (src/advisor/crossProviderVerification.js) at the kernel verb, and the drive's promote_to_done (src/conductor/initiativeFocus.js) for a lug at review OR at ready with readiness passed; and at session start, where buildExternalChainSection reports the external chain's failure modes with counts

#### src/lugTracking

- The cost gate honours the ruling, and every lug the sweep left at review on a process refusal has been re-run through the real verb from a non-author session, with the ones that reached done listed and the rest named with the exact evidence still missing. [landed add6c753]
- Long-running work declares its liveness lease on the lug -- a countdown the running agent refreshes as it works, sized to what the next step really needs (a provider call, a suite). [fixtures 57/0, 58/0; landed 5ed3f66b]
- A lug whose fixture is green and whose work is tied to a real dispatch record or a real commit reaches done without a hand-written flag row or a cosmetic marker line -- and a lug with none of that evidence is still refused, naming exactly which evidence is missing. [landed 69adebeb]
- lug-integrity-checksum tells a state forgery from a content edit: baseline records lifecycle fields; content edits adopted, state/readiness forgeries still healed; one-shot state-vs-evidence reconciliation
- Kernel verb measures its own write against rule 11's cap; pickup_reverification block compacted to <120 tokens
- A lug whose real proof lives in a pointers: external:<repo>/... path can reach state: done when that repo's own tagged fixture passes, without weakening today's same-repo check for a same-repo lug. [fixtures 42/42; landed c73763d8]

#### docs

- update-discovery: build record -- commits as landed, the fold-order hazard, the measured wall-clock step on this box
- hf-deploy: build record (docs/hf-deploy.md) -- measurements, the hub canon declaration and its ordering hazard, verification, what is left open

#### reference

- update-discovery: the circle declaration and its fixture
- pickup-time-reverification circle doc: the lug block is compact; fixture is 81 checks

#### src/conductor

- The sweep enumerates lugs at ready with readiness passed as well as lugs at review, and promotes a ready+passed lug through the same done gate the drive uses -- or records, per lug, exactly which gate still refuses it (traceability, tests, cost). [landed 1b31755e]
- readiness-certification-sweep: the review-backlog sweep as a real mechanism (module, CLI, on_demand circle, 29-check fixture naming its lug)

#### src/otto

- harness-factory's own `ozi` advisor runs on a real, live cadence -- either a real tick caller local to harness-factory, or loadWheelClock generalized to read any advisor's own wheel_clock block, not just otto.advisor.yaml's hardcoded one (design doc section 7: "Ozi runs on the spoke's clock, distinct from Otto's wheel-level one"). [fixtures 56/0; landed dc008d97]
- Max installed a real crontab entry (operator-approved live) calling runWheelClockCatchup directly every 10 minutes, matching TARGET_INTERVAL_MS -- confirmed idempotent and safe against a concurrent SessionStart caller (state-persisted, whichever caller runs first claims the owed ticks). [landed 5edae357]

#### wheel-feedback-loop

- A spoke discovers the current cut in its own sessions and on its own schedule and pulls it when the delta is pending-cut-shaped; otherwise it reports "UPDATE AVAILABLE" with the version and size. [landed 636f9060]
- One verb, `hf deploy`, run by Max, takes the fleet's finished work to every registered spoke: fold, push, cut, relaunch, clean -- each step its own recorded, resumable stage with a real refusal reason when a gate says no, never a bypass. [landed a44db163]

#### conductor-autonomous-loop

- A run killed mid-work keeps what it finished -- incremental recording means the backstop costs only the remainder, not the whole run. [fixtures 59/9, 68/0; landed 544fdf89]

#### conformance

- definition-complete-gate and ready-gate-stub fixtures run their hooks against a per-run scratch root; tracked lug-checksums.json reduced to the real seed

#### repo root

- regenerate-docs: CLAUDE.md and AMBASSADOR_BRIEF.md follow the liveness-lease cut

#### src/advisor

- Done gate reads both certification stores; a Proofer PASS is sufficient when the external chain produced nothing usable

#### src/basher

- A cut lands when only report-class rules are violated, with every violation named in the cut status and a lug owed; it rolls back only on refuse-class violations. [landed 1606f325]

#### src/cartographer

- The full suite is green in a git worktree of the repo exactly as it is in the canonical checkout, and a fixture that genuinely needs the canonical path says so by name and is skipped-with-reason in a worktree, never silently red. [landed 8c721a45]

#### src/compiler

- Rule 11 measures the authored contract (intent, outcome, acceptance, constraints, out_of_scope, pointers, open_questions) and not verb-owned bookkeeping (cost, traceability_evidence, outcome_at_proofer, pickup_reverification, harness_factory_proof, build_record). [fixtures 43/43; landed d4c8439f]

#### src/factory

- The full suite completes in about five minutes on this machine with the same per-suite verdicts and the same fail-fast/no-fail-fast contracts the gates rely on, and a suite that cannot run concurrently says so and is run alone. [fixtures 43/0; landed 89ceb779, 297fb7be]

#### src/hooks

- A real v2 mechanism captures a one-line "what this turn is doing/just achieved" string per turn (no such field exists anywhere in v2's real track.json schema today -- confirmed live, its real keys are kind, session_id, started_at, closed_at, turn_ordinal, last_stop_at, identity_triple, active_lugs_and_transitions, directions_captured, cost_markers, decisions, handoff -- none of them a per-turn narration field), and `resolve_focus()`/`save_color()` in the deployed ~/.claude/statusline.sh gain a v2 read path for it, additive to the untouched v1 path, the same pattern `resolve_turns()` already established this session. [landed 43815c10, 8f475e52]

#### harness bookkeeping

- 2 harness bookkeeping commit(s) in harness-factory (Session work 2).

### 2026-09-11

#### conformance

- track-rotation fixture: traceability marker for harness-factory-aggregator-red-since-260909-blocks-every-push (cause 6)
- wcl fixtures: init-cli usage check from a non-spoke cwd; hygiene fixture follows wcl's reworded step labels
- wcl-global-settings-cli: assert the usage string from a non-spoke cwd (wcl now infers the spoke from a spoke-root cwd and would launch)
- rule-12 broken fixture: grow the injection by initiative COUNT, not one verbose lug
- Finish the aggregator dispatch's last increment: hosted_by:instance circles delegated in run-reference-circles; notify fixture clears inherited launch-mode env; lug-edges adoption measured not pinned; exit hook timeout 480s from a two-repo measurement
- track-rotation: synthesize the 5-day-open track instead of copying the live one (harness-factory-aggregator-red-since-260909-blocks-every-push, cause 6)
- Isolate HOME in the heartbeat fixture; date D3/D4 readings relative to now (harness-factory-aggregator-red-since-260909-blocks-every-push, cause 5)
- Regenerate stale docs; correct wcl no-arg tests to the cwd-inference contract (harness-factory-aggregator-red-since-260909-blocks-every-push, causes 1+4)

#### circles

- Circle pattern-language declared: a pattern, spoke, group or the wheel is described in the common language -- declarePattern (src/otto/approachPatterns.js) running the value/lift/variant/correction gates at the library's write; describeSpoke/composeView (src/otto/patternLanguage.js) run by `node scripts/pattern-language.js describe|describe-all|view`; and `pattern-language.js vocabulary` tracing every glossary term to disk
- Circle planner-cross-segment-ranking declared: every wheel_clock planner_cycle job -- runPlannerCycle -> buildPlannerCycle -> rankCrossSegment (src/planner/planner.js), reading canon/initiatives/ live on each cycle
- Circle lug-type-lifecycles declared: a lug's type-specific lifecycle is consulted -- every applyLugVerb transition reads statesForLug (src/lugTracking/lugType.js) at the one sanctioned mutation path; every schema validation of a lug applies the per-type state enum in schemas/lug.schema.json; and the lug-integrity-checksum heal reads resetStateForLug to pick the entry state of the lug's OWN lifecycle
- Hook bound on PreToolUse: oversized-canon-write-guard.
- Circle initiative-focus declared: an initiative is read, ranked or driven -- every session start (buildInitiativeFocusSection through goalsReview.js), every Planner cycle (initiativeLugIndex + rankByInitiativePrecedence in src/planner/planner.js), and every autopilot launch (driveApReadyInitiatives from runAdvisorAutopilot, src/otto/advisorAutopilot.js) -- src/conductor/initiativeFocus.js
- Circle oversized-canon-write-guard declared: a Write or Edit call is about to run against a canon entity file or a circle/advisor instructions doc, in any session -- top-level or dispatched

#### src/conductor

- Planner ranks initiative work first across build and maintain, then allocates remaining capacity
- Session-start: verify the active-lug pointer against the lug file; retrim injected sections; citation rows must cite (harness-factory-aggregator-red-since-260909-blocks-every-push, cause 2 / rule 12)
- Initiatives get focus: readers, states, Planner precedence, autopilot drive, operator channel
- Retrim rule-12 session-start injection constants (real backlog growth)

#### src/advisor

- Evidence bundle carries every file changed by a commit naming the lug, pinned, deduplicated, capped in canon
- Kernel verb launches the cross-provider certification on a real transition into review
- Evidence bundle: a LOCAL directory pointer is disclosed and skipped, never an EISDIR crash

#### repo root

- Regenerate generated docs after today's canon changes (proofer evidence_bundle_commit_files, lug-type lifecycles circle)

#### src/basher

- Reword wcl's startup health-check report for readers with no framework vocabulary

#### src/cartographer

- Cartographer: resolve instance-hosted circles under the instance root; never map phantom paths (harness-factory-aggregator-red-since-260909-blocks-every-push, cause 3)

#### src/compiler

- Land two dispatched lugs: wcl hygiene launch classes + write-time cap guard; session-exit path fixes

#### src/hooks

- notice and remember lug types get minimal lifecycles, enforced per type at schema and verb

#### src/ledger

- Ledger byte cap declared in canon + the flood fold, with a fixture proving the fold idempotent and the cap refusing

#### src/lugTracking

- Fix done-gate traceability check to search the adopting spoke's framework repo

#### src/otto

- Pattern language: value, lift and self-description on the existing level enum

#### harness bookkeeping

- 12 harness bookkeeping commit(s) in harness-factory (Session work 12).

### 2026-09-10

#### circles

- Circle approach-pattern-library declared: the hub's approach-pattern library is written or read -- recordAttempt/declarePattern (src/otto/approachPatterns.js), the wheel-clock approach_pattern_library job running runApproachReview, scripts/approach-review.js run by an operator, and publish_kb_cut cutting the library to a spoke
- Circle calibration-record declared: an operator or agent asks what a named heuristic's real error rate is
- Circle chain-disposition declared: an operator or third-party session asks for a chain's verdict -- `node scripts/chain-disposition.js <chain-id> [--write --session-id=<id>]`
- Circle design-salvage-review declared: an operator or agent runs a salvage pass over work at risk of falling onto the cutting floor
- Circle dispatch-run-salvage declared: a real dispatched session runs -- the launch supervisor journals its child's stream to disk for the child's whole life (src/basher/idleWatchdog.js main(), from the first chunk, before any kill can happen), and executeDispatch (src/lugTracking/dispatchMechanism.js) builds the run's work disposition when the launcher returns, on every terminal outcome and not only on completions
- Circle hook-invocation-runlog declared: every hook invocation in this build -- makeCapture (src/hooks/lib/hookIO.js) records the invocation's duration and outcome on its way out, whether the hook exited cleanly, exited non-zero, threw, or never reached its own exit path at all; and again when a session start or warmup composes the operator surface from the recorded rows
- Circle orphan-dispatch-disposition declared: an orphaned dispatch row is re-reconciled against the real evidence its child left on disk -- `node scripts/orphan-disposition.js <instanceRoot>` runs the sweep on demand, and every session start reports the standing result once through goalsReview.js's buildOrphanDispositionSection
- Circle pickup-time-reverification declared: work is picked up -- a lug transitions into in_progress, or a dispatch is queued for it
- Circle planner-cycle-allocation declared: wheel_clock job planner_cycle (canon/otto.advisor.yaml), declared FIRST so it fires before every other scheduled job
- Circle provider-usage-and-retry declared: any provider call is made through src/advisor/providerContract.js's callProvider -- every caller: proofer.js (the cross-provider certification path), machineProbe.js, and any script or fixture that calls it directly
- Circle run-roi-extraction declared: every autopilot run ENDS here -- finishAutopilotRun (src/conductor/roiExtraction.js) is reached from runAdvisorAutopilot's close path (launch, decline, and its abnormal-end guard alike), from src/conductor/heartbeat.js finish() on an out-of-session no-launch, and from scripts/conductor-heartbeat.mjs's launch arm in its own `finally`; and again on demand as the reconciliation sweep (scripts/reconcile-open-waves.js) over waves that were opened and never closed
- Circle scheduler-failure-operator-channel declared: a wheel_clock job fails on consecutive ticks (evaluated at the end of every real tickWheelScheduler run), and again when a session start composes the goals review
- Circle success-prediction declared: a success prediction is registered, superseded or reviewed -- registerPrediction / supersedePrediction / reviewPrediction / reviewDuePredictions (src/conductor/successPrediction.js), via scripts/success-prediction.js on demand; and every session start, where buildSuccessPredictionSection reports verdict counts through goalsReview.js
- Circle temporary-limit-boost-awareness declared: a caller asks whether a temporary rate-limit boost is currently active on this account -- every conductor heartbeat tick (detectLimitBoost + boostExpiryAlert), every paceFromReading given a boost fact, and every headless usage poll's own operator-facing output
- Circle unattended-run-kill-switch declared: any caller is about to spend, or is already spending, the operator's subscription with nobody at the machine -- checked at every launch gate (executeDispatch, runHeartbeat Gate 0, runAdvisorAutopilot Gate 0) and POLLED by every launch supervisor for the whole life of its child.
- Circle cross-store-finding-coalescing declared: a systemic finding is recorded into any of the wheel's three durable stores -- the wheel-clock cross_store_reconciliation job coalescing its disagreements by cause (runCrossStoreReconciliation), every ledger append passing through appendRow, every Stop rebuilding a track's decisions projection (writeOrUpdateTrack), and every automatic P0 lug filing (openP0BugFixLug)
- Circle lug-edges declared: a lug's edges are written or read -- every applyLugVerb transition runs checkLugEdges (src/lugTracking/lugEdges.js) at the one sanctioned mutation path; `node scripts/lug-edges.js up|down|verifications|chain|relates|audit` reads them on demand; and the two pre-existing consumers of the fields, chainDisposition.resolveChain and pickupReverification.dependencyRefs, now import the shared normalizer instead of re-reading derived_from

#### reference

- Commit mechanical/generated updates from prior sessions' uncommitted work
- Sync reference/circles trim with the already-distributed wheel-hub cut

#### src/advisor

- Fix wheelClockCatchup cron invocations never exiting (real leak, real fix)
- Commit proofer/cross-provider verification updates (broad existing coverage)

#### conformance

- Regenerate lug-checksums.json fixture snapshot

#### src/conductor

- Commit the real, disciplined backlog of prior-session work (143 files)

#### src/otto

- Fix compile-blocking violations: kb SKIP_DIRS and session-start context cap

### 2026-09-09

#### circles

- Circle conductor-window-boundary-claim declared: a cron-driven process is about to act on a detected five-hour window boundary -- scripts/conductor-heartbeat.mjs --launch, or the wheel clock's advisor_activation job (runAdvisorAutopilot) reaching a decideWave LAUNCH.
- Circle conversation-track-ingestion declared: an operator or agent runs `node scripts/ingest-conversations.js` at an instance root, to mine conversation/track exports from any declared source for operator goals and preferences and for stranded ideas.
- Circle default-forward-veto-ledger declared: a default-forward act is about to happen -- today, a dispatch queued or executed with no human at the keyboard
- Circle falsifiability-gate declared: an operator or agent asks whether a verify command CAN fail, before trusting that it passed
- Circle git-boundary-test-gate declared: a real `git commit` or `git push` runs in harness-factory or wheel-hub
- Circle node-probe-scheduler declared: wheel_clock job node_probe_scheduler (canon/otto.advisor.yaml)
- Hook bound on PostToolUse: cross-provider-verification.
- Circle cross-provider-verification declared: a lug transitions into review with priority high or critical AND proof_required: true

#### src/lugTracking

- Lug type field and conditional requirements (D1/D2, Part 2)

#### harness bookkeeping

- 4 harness bookkeeping commit(s) in harness-factory (Session work 4).

### 2026-09-08

#### circles

- Circle conductor-harness-factory-leverage-routing declared: buildReadyWorkQueue (src/conductor/readyWork.js) is called to rank the ready-work queue -- every real caller: goalsReview.js, warmup.js, conductor.js's planRouting, waveDecision.js's candidate-pool build, factory/positionMap.js, lugTracking/handoff.js

#### harness bookkeeping

- 1 harness bookkeeping commit(s) in harness-factory (Session work 1).

### 2026-09-07

#### circles

- Circle max-persona-boundary-guard declared: a Write, Edit or NotebookEdit call is about to run from the top-level (non-dispatched) session
- Hook bound on PreToolUse: max-persona-boundary-guard.
- Circle anthropic-rate-limit-five-hour-envelope declared: a caller asks for the account's real five-hour rate-limit headroom -- detectWindowStart on every wave decision and every heartbeat tick (measureAnthropicRateLimitUsage), or a caller running enforceAnthropicRateLimitEnvelope to write the measured value back onto the Envelope row
- Circle conductor-heartbeat declared: scripts/conductor-heartbeat.mjs is run from outside any Claude Code session -- the out-of-session supervisor tick (the proposed cron entry, docs/conductor-heartbeat.md), which is the one caller awake when a five-hour window opens with nobody at the machine
- Circle conductor-wave-gate declared: a real caller asks whether a five-hour window just started and whether to spend it -- src/otto/advisorAutopilot.js runAdvisorAutopilot in session (on the advisor_activation wheel-clock job), or scripts/conductor-heartbeat.mjs out of session; the repeat arm is reviewWaveAndDecideRepeat after a wave closes
- Circle headless-usage-reading declared: scripts/headless-usage-poll.mjs is run (no session, no statusline, no TTY), or scripts/conductor-heartbeat.mjs is run with --poll, which calls pollHeadlessUsage before deciding

#### src/conductor

- Fix rule-13 personal-leak refusing the build (paceModel.js provenance comment)
- Headless five-hour reading: a real source EXISTS -- found, wired, proven
- windowStart: parse the real epoch-seconds resets_at, so the primary signal fires
- Conductor heartbeat: the wave gate, callable from outside a session
- Conductor: autonomous five-hour wave orchestration, and the poller fix behind it

#### src/lugTracking

- MAX-124: catch a disclosed gap on the turn that writes it, not never
- PreCompact track rotation: close the segment, review it, reopen the session
- Register tonight's four Conductor mechanisms as real circles (MAX-119)
- Dispatch into an external repo gets its scope grant automatically

#### docs

- Fix stale windowStart.js description (MAX-118 superseded MAX-116's fix)
- MAX-123: close statusline poller lug -- confirm the real Envelope chain, correct a false v1-guard claim

#### src/hooks

- max-persona-boundary-guard: refuse top-level authorship of application code
- Fix the real reason 31 dispatch-registry rows stayed stranded

#### src/basher

- Fix: prefer the operator's real, rich statusline.sh over the bare poller

#### src/identity

- MAX-122: resolve the callsign wordlist from the harness checkout, not the spoke

### 2026-09-06

#### src/factory

- Absorb mywheel's bench.py: real harness-change effectiveness benchmark
- Done (merged via MAX-110). mywheel's own 5 sources don't exist here, ported the design instead: 4 real, already-owned signals fused -- circleAudit.auditCircles (CLOSED/OPEN/PHANTOM), cartographer's readCartographerMap, conductor's buildReadyWorkQueue, and a new read-only roiRollup.loadPreviousRollup export (deliberately not buildRoiRollup, which has a designed side effect of appending a history row -- would violate read-only for a run-every-session map). [fixtures 36/36; landed 708297b5]
- Done (merged via MAX-107). [fixtures 34/34, 0/42, 29/68; landed 90f2ae99]
- Add additive verify_mode/verify lug schema fields + a commit-boundary lug gate
- Absorb mywheel's bridge.py: real propose/apply generation-intent-harvest tool

#### circles

- Circle regression-oracle declared: wheel_clock job regression_oracle (canon/otto.advisor.yaml)

#### reference

- Trim regression-oracle.md for rule 11 (self-hosting compile clean)

#### src/hooks

- bash-destructive-command-guard: write a real ledger row on real deny-posture denials

#### src/otto

- Absorb mywheel's wai_assurance.py: real regression-detecting oracle runner

### 2026-09-05

#### src/factory

- Fix findScheduleJobMatch to also check wheel_clock job-key correspondence
- MAX-102: absorb mywheel's circle-completeness auditor into the harness
- Extend frameworkroot-fallback fix to scaffold.js's own same-pattern bug
- Fix frameworkroot-fallback-resolves-to-worktree-not-canonical-repo
- Declare wheel-clock-catchup circle + hook-binding-drift catches undeclared hooks
- Never silently clobber real, non-v2 .claude/settings.json or generated docs
- Done (merged to harness-factory main via MAX-089). buildAllowBlock replaces v1's blanket grant with a real mapping: baseline read-only access unconditional (so "propose" isn't crippled), Write/Edit/Skill/ Agent/narrow in-repo Bash gated on lug_execution (auto_with_notify/auto), dependency-change and external-contact grants gated separately on their own cells (both hardcode "review" today, so empty in practice until a real promotion lands), git push excluded unconditionally. [fixtures 23/23; landed 6b9a8a4c]

#### circles

- Circle circle-completeness-audit declared: a real session starts (SessionStart event)
- Hook bound on SessionStart: circle-completeness-audit.
- Circle guard-denial-reconciliation declared: wheel_clock job guard_denial_reconciliation (canon/otto.advisor.yaml)
- Circle wheel-clock-catchup declared: a real session starts (SessionStart event)
- Hook bound on SessionStart: wheel-clock-catchup.

#### src/basher

- MAX-099: bring launchSpoke to pending-cut parity with wclCli.js
- Stale-instance check no longer refuses a launch for a pending cut it would fix
- Session-start lane consolidation + routine-file merge strategy (half 1)

#### src/compiler

- compile() ok no longer counts informational non-canon-yaml as a failure
- Fix real defect: compile() rules 04/11/13 scanned a spoke's non-canon legacy tree as if it were canon
- Done (merged to harness-factory main via MAX-086). loadCanon() never throws on a per-file parse failure or non-mapping document -- both become a synthetic, kind-less entity carrying _loadError, which compile() turns into a real, itemized rule-00 violation naming the file and the real error. [fixtures 27/27; landed 2fe7b6c1]

#### src/hooks

- Fix real defect: lug-lifecycle-tracker and ready-gate-stub denials vanish with no ledger trace
- MAX-101: bash-lug-guard denial trace + guard-denial-reconciliation job
- Wire a SessionStart catch-up driver for the wheel clock (lug: wheel-clock-sessionstart-catchup-tick)

#### src/otto

- Wire reconcile-ledger into the wheel-clock scheduler (JOB_RUNNERS)
- Fix roi-rollup crash on non-rollup-shaped history row, isolate tick job failures
- Add advisors bucket to buildRoiRollup, distinct from the building bucket

#### reference

- Add missing canonical source for guard-denial-reconciliation circle
- Fix stale trigger text at its canonical source, not just the derived copy

#### src/lugTracking

- Fix dispatch-raw-error-misclassified-as-completed: raw launcher errors no longer land as completed

#### harness bookkeeping

- 1 harness bookkeeping commit(s) in harness-factory (Session work 1).

### 2026-09-04

#### src/basher

- Wire global-settings-drift-check onto real SessionStart cadence
- config-custody: disclose why the two zero-caller probes stay uncalled
- Detach the launch supervisor so a dispatch survives its orchestrator dying
- MAX-073: real, preview-only reconciliation of the operator's global Claude Code config

#### circles

- Circle global-settings-drift-check declared: a real session starts
- Hook bound on SessionStart: global-settings-drift-check.

#### src/lugTracking

- Self-heal orphaned dispatch-registry rows stuck at "running"
- Fix scope-guard cross-dispatch leakage via subagent_type fallback

#### canon

- MAX-075: declare harness-factory's own Ozi advisor identity

#### repo root

- Regenerate harness-factory's own stale generated docs

#### src/advisor

- Fix resolveExternalPointer EISDIR crash on directory-shaped pointers

#### src/hooks

- Give scope-guard declaration phrases per-file granularity

#### src/otto

- MAX-072: real advisor autopilot -- activation-to-dispatch link for otto/kb-curator

### 2026-09-03

#### circles

- Hook bound on Notification: notification-agent-waiting-notify.
- Hook bound on PostToolUse: cartographer-commit-trigger.
- Hook bound on PreCompact: precompact-checkpoint.
- Hook bound on PreToolUse: agent-target-scope-guard.
- Hook bound on PreToolUse: agent-tool-scope-guard.
- Hook bound on PreToolUse: bash-destructive-command-guard.
- Hook bound on PreToolUse: bash-lug-guard.
- Hook bound on PreToolUse: definition-complete-gate.
- Hook bound on PreToolUse: lug-lifecycle-tracker.
- Hook bound on PreToolUse: ready-gate-stub.
- Hook bound on PreToolUse: test-lug-traceability.
- Hook bound on SessionEnd: session-end-handoff.
- Hook bound on SessionEnd: session-end-notify.
- Hook bound on SessionEnd: session-exit-commit.
- Hook bound on SessionStart: hook-binding-drift.
- Hook bound on SessionStart: session-continuity-checkpoint.
- Hook bound on SessionStart: session-registry.
- Hook bound on SessionStart: session-start-warmup.
- Hook bound on SessionStart: warmup-goals-review.
- Hook bound on Stop: footer-audit.
- Hook bound on Stop: lug-integrity-checksum.
- Hook bound on Stop: stop-agent-waiting-notify.
- Hook bound on Stop: stop-turn-marker.
- Hook bound on Stop: session-track-write.
- Hook bound on UserPromptSubmit: capture-direction.
- Hook bound on UserPromptSubmit: footer-correction-injection.
- Hook bound on UserPromptSubmit: live-apply-announce.
- Hook bound on UserPromptSubmit: turn-start-attribution.
- Circle verify-fleet-versions declared: hub reconciliation schedule
- Circle canonical-spec-lug-index declared: hub wheel-clock schedule (every 6 ticks)
- Circle process-signal-inbox declared: hub wheel-clock schedule (every 3 ticks)
- Circle publish-kb-cut declared: hub wheel-clock schedule (every 6 ticks) or a real change to kb/capabilities-graph.md
- Circle agent-target-scope-guard declared: a Write, Edit, NotebookEdit or Bash call is about to run from inside a dispatched Agent-tool fork

#### conformance

- MAX-069: fix stale scoped-compile workaround causing rule-20 false positives
- MAX-060: replace hand-maintained test:suites with auto-discovery
- MAX-059: complete rule 20's fixture (root cause: Max's manual test, not the rule)
- MAX-052: verify wclCli.js's v1 delegation branch is real, not dead code
- Recalibrate rule-12's own broken fixture for the raised cap (MAX-019)
- Use static imports in hub-governance circle tests so cartographer resolves implementing_files
- Add local conformance tests for the hub-governance circles (rule 01)
- Add nonzero_exit coverage to provider-contract conformance test

#### src/compiler

- MAX-063: real 1Password service counterparty row + generic service-card convention
- MAX-056: rule 20, no-dead-orchestrator-knowledge-source
- MAX-045: compile-self now writes the same permissions.deny block scaffold.js does
- MAX-035: skip .github/ as canon, and tell pre-v2 legacy YAML apart from real malformed canon
- MAX-036: rule 13's binary-file guard never actually fired -- fix at root cause
- Remove personal-path leak from v1PathScan.js comment; trim rule-12 policy file
- Root-cause the v1-path scan mywheel false positive (was patched, not fixed)
- Generalize loader SKIP_DIRS and close compile-self teardown exposure window

#### src/hooks

- MAX-066: real session attribution fixes track-artifact contamination under concurrency
- MAX-067: trim scope-declaration-phrases.yaml to fix harness-factory's broken self-compile
- MAX-061: narrow agent-tool-scope-guard's false positive on content-preservation prose
- MAX-034 Job 1: restore denyJSON's systemMessage param, lost in the MAX-030 merge
- MAX-030: bound live-hook-capture growth and stop reparsing it per launch
- MAX-028: FBL-065 followup -- catch a fork's write after dispatch-time matching misses it
- MAX-025: real second-provider liveness proof plus a personal-path-leak fix
- Remove remaining personal-path leaks from shipping artifact (rule 13)

#### src/factory

- MAX-051: wire real regeneration for self-hosting spoke's own generated docs
- MAX-050: resolve the Ambassador Brief's glossary pointer to where it really lives, restoring a MAX-048 fix I accidentally reverted merging MAX-047
- MAX-049: generated docs enumerate a spoke's real live circles, not a hardcoded path
- MAX-047: adopted spokes get a real compiler command, not an ENOENT
- MAX-048: fix stale ROI-rollup claim in the generated Ambassador Brief
- MAX-042: resolve tool_disposition's replaced_by to its real tool field, not the raw entity name
- Build fleet-version wiring, spoke arrival-audit, and restore-manifest

#### src/basher

- MAX-068: wire the documented `wcl init` verb into the real CLI dispatch table
- MAX-057: basher counterparties CLI verb
- MAX-044: model-tier selection on the programmatic dispatch path
- MAX-021/026: replace the blind wall-clock launch kill with a silence watchdog
- Fix worktree spokeDir treated as its own frameworkRoot (real credential-copy regression)

#### src/otto

- MAX-064: real wheel-wide cross-store reconciliation job
- MAX-054: wire the statusline poller's real output into a real Envelope
- MAX-023: report malformed per-file advisor YAML instead of silently dropping it
- Add publish-kb-cut, spec-lug-index, and signal-inbox Otto mechanisms

#### repo root

- Regenerate harness-factory's own live docs (MAX-050 fix live)
- Regenerate harness-factory's own live CLAUDE.md and AMBASSADOR_BRIEF.md (MAX-049 fix live)
- Resolve unresolved merge conflict markers in package.json

#### .claude

- Regenerate harness-factory's own live .claude/settings.json (MAX-045 fix applied)
- Fix: restore .claude/settings.json deleted by the prior commit

#### src/advisor

- MAX-053: real active-advisor attribution, session-scoped, wired into max+otto
- MAX-040/041: durable model-lane declaration + a second real FBL-046 recurrence, closed

#### src/lugTracking

- MAX-058: real P0 ledger row auto-opens a bug-fix-protocol lug
- Add path-based cross-workstream scope guard (MAX-020, FBL-101)

#### canon

- Add harness-factory.spoke.yaml identity entity (MAX/wilbur-a2-followup)

#### src/conductor

- MAX-039: Conductor weighs a real quota signal; [redacted] gated on real operator-idle

#### src/messaging

- MAX-029: Wilbur-E cross-machine transport (queue-and-drain) plus Group Message payload shape

#### src/minder

- MAX-022: fix minder-shadow-check latency measurement to per-turn grouping

#### harness bookkeeping

- 2 harness bookkeeping commit(s) in harness-factory (Session work 2).

### 2026-09-02

#### conformance

- Add current-layout statusline usage poller (MAX-015)
- Generalize orchestrator.schema.json beyond Wilbur (MAX-010)
- Add row_kind: conversation to ledger schema (MAX-005)

#### src/advisor

- Add proofer independence axes: model, provider, method, input (MAX-012)

#### src/basher

- Fix dispatch timeout forwarding and outcome statuses (MAX-007)

#### src/hooks

- Fix lug-integrity heal false-positive on legitimate git merges (MAX-011)

#### harness bookkeeping

- 2 harness bookkeeping commit(s) in harness-factory (Session work 2).

### 2026-09-01

#### circles

- Circle agent-tool-scope-guard declared: an Agent-tool call is about to run
- Circle cartographer-commit-trigger declared: a real git commit lands in harness-factory (PostToolUse, Bash matching git commit)
- Circle precompact-checkpoint declared: a real context compaction is about to happen (PreCompact event, manual or auto)
- Circle notification-agent-waiting-notify declared: Claude Code sends a real permission_prompt or idle_prompt notification
- Circle stop-agent-waiting-notify declared: a real turn completes -- Claude stopped and is waiting
- Circle session-end-notify declared: a real session ends
- Circle wcl-verify-then-launch declared: the operator runs `wcl <spoke>`
- Circle footer-correction-injection declared: a real prompt is submitted, following a turn footer-audit flagged as missed
- Circle turn-start-attribution declared: a real prompt is submitted
- Circle hook-binding-drift declared: a real session starts

#### src/hooks

- Fix cartographer-commit-trigger correctness bug found by Proofer certification
- FBL-066/068: destination-by-ownership fixes, precompact checkpoint, cartographer commit trigger

#### src/tastegraph

- Build tastegraph proposal mechanism (FBL-066 ruling 4)

#### harness bookkeeping

- 11 harness bookkeeping commit(s) in harness-factory (Session work 11).

### 2026-08-31

#### circles

- Circle bash-destructive-command-guard declared: a Bash command is about to run
- Circle session-exit-commit declared: a real session ends (SessionEnd event), after the handoff is written and the track closed
- Circle live-apply-announce declared: a prompt is submitted (UserPromptSubmit event)
- Circle session-registry declared: a session starts (SessionStart event)
- Circle footer-audit declared: a turn ends (Stop event)

#### src/advisor

- Assayer plan drafting, the fabrication check, and external evidence resolution
- One persistent provider config dir, a credential preflight, and an authoritative secrets bag

#### src/basher

- The config-custody manifest and real version-drift detection
- wcl, cut-update, and the live-apply announce circle

#### src/compiler

- Generated CLAUDE.md, compile-self, the aggregator, and the live hook bindings
- Admission rule 12: cap history and the cap-growth review lug

#### src/hooks

- Lug kernel verbs, lifecycle tracking, the gates, and the continuity checkpoint
- Cross-repo instance-root resolution: a lug worked from another repo now costs

#### src/conductor

- Warmup goals review and the bash lug guard

#### src/identity

- id-v3 identity: callsigns, the session registry, and spoke liveness

#### src/influence

- The session-upkeep manifest, influence contracts, and the minder-tracks clarification

#### src/ledger

- The prompt-id protocol, origin codes, references, and the track artifact

#### src/lugTracking

- The merged turn footer and its audit circle

#### harness bookkeeping

- 3 harness bookkeeping commit(s) in harness-factory (Session work 3).

### 2026-08-29

#### circles

- Circle reconcile-advisor-roster declared: hub reconciliation schedule
- Circle session-end-handoff declared: a real session ends (SessionEnd event)
- Circle session-track-write declared: a turn ends (Stop event)

#### src/advisor

- Fix gemini Proofer verdict truncation: raise max_tokens 1024 -> 8192 (260828-FBL-011)
- Give the Proofer a real evidence bundle and citation-fabrication check

#### src/ledger

- Add teaching writeback and the ledger row_kind enum for it (+ directive)
- Fix direction-capture truncating on ordinary word-wrap

#### src/lugTracking

- Amend the done gate: pre-instance markers are exempted narrowly, nothing else is (260828-FBL-011)
- Add the real Track/Handoff artifact system (session-track-write, session-end-handoff circles)

#### .claude

- Commit the standing self-instance .claude/settings.json (260828-FBL-009)

#### canon

- Register harness-factory's own identity (FBL-005 self-instance)

#### conformance

- Wire all new conformance suites into the npm test aggregator

#### scripts

- Add minder shadow-window tooling (identity, baseline, dry-run, --latest check, bounded AP loop)

#### src/basher

- Add 1Password-backed secrets loading (docs/SECRETS_V2.md, src/basher/onePassword.js)

#### src/compiler

- Adopt the PROMPT-ID protocol (FBL-001..260828-FBL-010) and compile-self --standing

#### src/conductor

- Add owned-vs-rented routing and Diakon integration (Part C)

#### src/navigator

- Surface ownership/control/lane fields on Navigator cut nodes

#### src/otto

- Implement the reconcile-advisor-roster circle (lugs/advisor-roster-reconciliation, real Otto backlog work)

### 2026-08-27

#### src/compiler

- Two rulings before increments 7-11: rule 12 measures the wrong set, cut rollback pins previous SHA
- Phase 2 report: all six exit tests PASS, with a live counter-metric firing mid-report
- Phase 2, Part A: sharable bootstrap (wcl init), shipping-artifact scan
- Phase 1 stop: rule 11 extension coverage, rule 12 counter-metric, JUDGMENT resolutions
- Part C exit test: rules 11/12 re-derived from a real measured wakeup
- Pre-Part-C items 3+4: ledger slice policy in canon, close the ready-skip bug
- Fix rule 12: sum the ledger SLICE (design doc section 7), not the whole file forever -- caught live when it refused wheel-hub's own compile
- Phase 1 Part A: context load audit (docs/CONTEXT_LOAD.md)

#### circles

- Circle cartographer declared: the wheel-scheduler's cartographer_map job, on its declared cadence
- Circle wheel-scheduler declared: the wheel clock -- canon/otto.advisor.yaml's wheel_clock block
- Circle warmup-goals-review declared: a session starts
- Circle session-continuity-checkpoint declared: a session starts
- Circle bash-lug-guard declared: a Bash command is about to run
- Circle lug-integrity-checksum declared: a turn ends (Stop event)
- Circle lug-kernel-verb declared: an operator or agent runs the verb to change a lug's state

#### src/advisor

- Increment 8: Conductor cloud-only disclosure + real wheel-scheduler circle
- Ruling 1: gate advisor improvement cycles on real measured consumption
- Second-provider credentials: secrets layer, OpenAI-compatible adapters, Proofer suppression
- Increment 7: real Proofer, provider contract, advisor rotation, improvement cycle

#### src/hooks

- Increment 9: TasteGraph overlay merge, autonomy table with real proposals
- Phase 1 Part B: time to productive turn (docs/TTPT.md)
- Pre-flight (reconciled-gate work order): fix bash-lug-guard false positives
- Close increments 2 and 6 live; kernel verb + Bash-bypass fix; two real bugs

#### docs

- Increment 8 stop report
- Third live second-provider Proofer run, now that credentials exist
- Increment 7 stop report

#### src/conductor

- Part D: warmup that earns its tokens
- Part C: Navigator, Conductor, ready-work automation, C4 goals review

#### src/factory

- Phase 2, Part C: contribution back (Message shape + evidence requirements only)
- Phase 2, Part B: self-update (distribution, safe apply, migration, fleet truth)

#### src/identity

- Ruling: the triple is stamped by writers, not callers
- Identity and Environment Registry, deployment as a contract

#### .claude

- IDEAS.md: bash-lug-guard weaknesses confirmed against this session itself

#### canon

- Task 1: mark admission rules 11 and 12 provisional in canon

#### conformance

- Task 4: recompile-and-diff check for both repos, wired into npm test

#### fixtures

- Freeze the B4 controlled re-run fixture

#### src

- Task 6: compile-self cannot leave the builder's own session hooked

#### src/assayer

- Part B + the Assayer: QA advisor that makes test coverage predictable

#### src/basher

- C0: wcl, basher v2's first verb

#### src/cartographer

- Part A: Cartographer -- Ozi understands the spoke

#### src/intake

- Intake Protocol taxonomy: the protocol's output is the lug

#### src/ledger

- Task 2 (scope exception, done first): capture-direction stores the directive sentence, not the whole prompt

#### src/lugTracking

- Controlled B4 re-run: authoritative checkpoint framing, four cycles

#### src/navigator

- Diakon onboarding: real probe, real DNS failure, a real registry gate fix

#### src/observability

- Part C: base observability, then a real paths-worth-tracking analysis

### 2026-08-26

#### circles

- Circle session-start-warmup declared: a session starts
- Circle definition-complete-gate declared: a lug's state field is edited to defined (or beyond)
- Circle ready-gate-stub declared: a lug's state field is edited to ready
- Circle lug-lifecycle-tracker declared: a lug's state field is edited to in_progress or done
- Circle stop-turn-marker declared: a turn ends (Stop event)
- Circle test-lug-traceability declared: a new test file is written
- Circle capture-direction declared: user submits a prompt containing a standing-rule marker phrase
- Circle reconcile-ledger declared: hub reconciliation schedule
- Circle readiness-gate declared: a lug's state field is edited to ready (or beyond)

#### src/hooks

- Live-hook-test infrastructure: capture wrapper, SessionStart warmup canary, self-compile, and a real hook_script resolution fix
- Rulings 2026-08-26: split definition-complete from a stubbed ready gate, honest cost measurement, counter-metrics, hook_script resolution
- Increment 6: lug lifecycle traceability and cost

#### docs

- Live hook test: real evidence for increments 2, 3, 6 via real headless sessions
- Update exit-test evidence table for the readiness-gate split and wheel-hub scaffold

#### src/compiler

- Increment 2: one circle end to end (readiness-gate)
- Increment 1: schemas, compiler, conformance runner

#### src/factory

- Increment 5: factory greenfield (interview, scaffold, bootstrap)

#### src/ledger

- Increment 3: the ledger (capture-direction, reconcile-ledger)

---

# Change Log -- tracks (technical view)

<!-- (generated -- never hand-edit) by hf changelog, from the record layer -->

Range: earliest framework commit (2026-08-26T09:39:03.000Z) .. latest record. Repos: tracks. Dates are UTC.
Records read: git log (main); lugs/*.yaml (state done, certified_by, tests, cost, intent's operator quote); runtime/event-log.jsonl (done transitions); runtime/deploy-runs.jsonl + registry/latest-cut.json (cuts published); .cut-status.json and its git history (cuts applied / received); canon/circles + .claude/settings.json between two landings (what a cut changed for the spoke); reference/circles/*.yaml + .claude/settings.json (circles added, hooks bound); runtime/dispatch-registry.jsonl (dispatches completed, measured tokens).

# Part 1 -- tracks's own history

Entries: 47 (commit 33, cut_received 13, lug_review 1).

## 2026-09-18

### cuts

- 01:44Z cut 87971bbe received by tracks (previous 5c79e2c6) (working tree), posture absorb_and_report: +0/~3/-0 circles for tracks -- changed dispatch-run-salvage, git-boundary-test-gate, hf-deploy (git fbb4ff64..working tree -- canon/circles, .claude/settings.json) -- published +0/~3/-0 circles, 0 lug(s) closed at 2026-09-18T01:40:52.511Z -- source: tracks: .cut-status.json (working tree, not yet committed)

### runtime

- 01:44Z commit f4ebdc34 [tracks] harness-arrival-audit: absorbed 5 file(s) on cut arrival -- 5 file(s), area runtime -- source: tracks: git log main f4ebdc34

## 2026-09-17

### runtime

- 22:42Z commit 15491b7b [tracks] harness-arrival-audit: absorbed 3 file(s) on cut arrival -- 3 file(s), area runtime -- source: tracks: git log main 15491b7b
- 22:42Z commit 2f007057 [tracks] harness-arrival-audit: absorbed 5 file(s) on cut arrival -- 5 file(s), area runtime -- source: tracks: git log main 2f007057
- 21:18Z commit 7a618cda [tracks] harness-arrival-audit: absorbed 3 file(s) on cut arrival -- 3 file(s), area runtime -- source: tracks: git log main 7a618cda
- 21:18Z commit 581cd582 [tracks] harness-arrival-audit: absorbed 5 file(s) on cut arrival -- 5 file(s), area runtime -- source: tracks: git log main 581cd582
- 20:33Z commit 26b718d2 [tracks] harness-arrival-audit: absorbed 3 file(s) on cut arrival -- 3 file(s), area runtime -- source: tracks: git log main 26b718d2
- 20:33Z commit 500d0bb6 [tracks] harness-arrival-audit: absorbed 5 file(s) on cut arrival -- 5 file(s), area runtime -- source: tracks: git log main 500d0bb6
- 17:39Z commit e6779214 [tracks] harness-arrival-audit: absorbed 3 file(s) on cut arrival -- 3 file(s), area runtime -- source: tracks: git log main e6779214
- 17:39Z commit 3abd1e51 [tracks] harness-arrival-audit: absorbed 5 file(s) on cut arrival -- 5 file(s), area runtime -- source: tracks: git log main 3abd1e51
- 16:17Z commit 549b2592 [tracks] harness-arrival-audit: absorbed 3 file(s) on cut arrival -- 3 file(s), area runtime -- source: tracks: git log main 549b2592

### cuts

- 22:42Z cut 5c79e2c6 received by tracks (previous b81e2bc1) landed fbb4ff64, posture absorb_and_report: +0/~0/-0 circles for tracks (git c065e2ee..fbb4ff64 -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-17T22:38:25.849Z -- source: tracks: git show fbb4ff64:.cut-status.json
- 21:18Z cut b81e2bc1 received by tracks (previous 4a839956) landed c065e2ee, posture absorb_and_report: +0/~0/-0 circles for tracks (git 7c2adcaa..c065e2ee -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-17T21:14:46.508Z -- source: tracks: git show c065e2ee:.cut-status.json
- 20:33Z cut 4a839956 received by tracks (previous ca0e4076) landed 7c2adcaa, posture absorb_and_report: +0/~0/-0 circles for tracks (git 14fd1be8..7c2adcaa -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-17T20:29:51.348Z -- source: tracks: git show 7c2adcaa:.cut-status.json
- 17:39Z cut ca0e4076 received by tracks (previous 89051371) landed 14fd1be8, posture absorb_and_report: +0/~0/-0 circles for tracks (git 3e684e52..14fd1be8 -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-17T17:36:55.978Z -- source: tracks: git show 14fd1be8:.cut-status.json
- 16:17Z cut 89051371 received by tracks (previous 6e237e8f) landed 3e684e52, posture absorb_and_report: +0/~0/-0 circles for tracks (git 1df4cd62..3e684e52 -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-17T16:13:44.078Z -- source: tracks: git show 3e684e52:.cut-status.json
- 09:49Z cut 6e237e8f received by tracks (previous 8e61551f) landed 1df4cd62, posture absorb_and_report: +0/~0/-0 circles for tracks (git 1f8a6d8c..1df4cd62 -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-17T09:47:08.708Z -- source: tracks: git show 1df4cd62:.cut-status.json
- 06:59Z cut 8e61551f received by tracks (previous c8ec1341) landed 1f8a6d8c, posture absorb_and_report: +3/~14/-0 circles for tracks -- gained zellij-tab-identity-session-end, zellij-tab-identity-tool-reset, zellij-tab-identity-turn-start -- changed calibration-record, cross-provider-verification, dispatch-run-salvage, footer-audit, footer-correction-injection, hf-deploy, notification-agent-waiting-notify, readiness-certification-sweep, session-continuity-checkpoint, session-registry, stop-agent-waiting-notify, tastegraph-injection, warmup-goals-review, wcl-verify-then-launch -- hooks bound PreToolUse preToolTabResetHook.js, SessionEnd sessionEndTabClearHook.js, UserPromptSubmit userPromptSubmitTabHook.js (git 7b156f5f..1f8a6d8c -- canon/circles, .claude/settings.json) -- source: tracks: git show 1f8a6d8c:.cut-status.json
- 00:02Z cut c8ec1341 received by tracks (previous 21926af8) landed 7b156f5f, posture absorb_and_report: +0/~1/-0 circles for tracks -- changed cross-provider-verification (git 56d36285..7b156f5f -- canon/circles, .claude/settings.json) -- published +0/~1/-0 circles, 0 lug(s) closed at 2026-09-16T23:49:56.148Z -- source: tracks: git show 7b156f5f:.cut-status.json

### docs

- 20:33Z commit 7c2adcaa [tracks] hf deploy: cut 4a839956b726 applied (canon/circles, .claude/settings.json, generated docs, .cut-status.json) -- 2 file(s), area docs -- source: tracks: git log main 7c2adcaa
- 17:39Z commit 14fd1be8 [tracks] hf deploy: cut ca0e40768449 applied (canon/circles, .claude/settings.json, generated docs, .cut-status.json) -- 2 file(s), area docs -- source: tracks: git log main 14fd1be8
- 16:17Z commit 3e684e52 [tracks] hf deploy: cut 8905137109da applied (canon/circles, .claude/settings.json, generated docs, .cut-status.json) -- 2 file(s), area docs -- source: tracks: git log main 3e684e52
- 16:17Z commit 107f3c9e [tracks] harness-arrival-audit: absorbed 4 file(s) on cut arrival -- 4 file(s), area docs -- source: tracks: git log main 107f3c9e
- 09:49Z commit 1df4cd62 [tracks] hf deploy: cut 6e237e8f934a applied (canon/circles, .claude/settings.json, generated docs, .cut-status.json) -- 2 file(s), area docs -- source: tracks: git log main 1df4cd62

### canon

- 09:49Z commit 1f8a6d8c [tracks] harness-arrival-audit: absorbed 28 file(s) on cut arrival -- 28 file(s), area canon -- source: tracks: git log main 1f8a6d8c
- 06:59Z commit 2706435e [tracks] harness-arrival-audit: absorbed 4 file(s) on cut arrival -- 4 file(s), area canon -- source: tracks: git log main 2706435e
- 00:02Z commit 7b156f5f [tracks] hf deploy: cut c8ec1341cbd4 applied (canon/circles, .claude/settings.json, generated docs, .cut-status.json) -- 2 file(s), area canon -- source: tracks: git log main 7b156f5f

### ledger

- 09:50Z commit bb150bb4 [tracks] harness-arrival-audit: absorbed 2 file(s) on cut arrival -- 2 file(s), area ledger -- source: tracks: git log main bb150bb4
- 00:02Z commit 72e10cc9 [tracks] harness-arrival-audit: absorbed 2 file(s) on cut arrival -- 2 file(s), area ledger -- source: tracks: git log main 72e10cc9
- 00:02Z commit ad5064f9 [tracks] harness-arrival-audit: absorbed 3 file(s) on cut arrival -- 3 file(s), area ledger -- source: tracks: git log main ad5064f9

### repo root

- 22:42Z commit fbb4ff64 [tracks] hf deploy: cut 5c79e2c68aff applied (canon/circles, .claude/settings.json, generated docs, .cut-status.json) -- 3 file(s), area repo root -- source: tracks: git log main fbb4ff64
- 21:18Z commit c065e2ee [tracks] hf deploy: cut b81e2bc1c9a6 applied (canon/circles, .claude/settings.json, generated docs, .cut-status.json) -- 3 file(s), area repo root -- source: tracks: git log main c065e2ee

## 2026-09-16

### runtime

- 19:29Z commit 7de5dafe [tracks] harness-arrival-audit: absorbed 3 file(s) on cut arrival -- 3 file(s), area runtime -- source: tracks: git log main 7de5dafe
- 19:29Z commit 29f14768 [tracks] harness-arrival-audit: absorbed 8 file(s) on cut arrival -- 8 file(s), area runtime -- source: tracks: git log main 29f14768

### canon

- 19:29Z commit 56d36285 [tracks] hf deploy: cut 21926af88442 applied (canon/circles, .claude/settings.json, generated docs, .cut-status.json) -- 29 file(s), area canon -- source: tracks: git log main 56d36285

### cuts

- 19:29Z cut 21926af8 received by tracks (previous 79c1648d) landed 56d36285, posture absorb_and_report: +4/~12/-0 circles for tracks -- gained closeout-report, closeout-request, lug-write-schema-gate, session-files-touched -- changed agent-tool-scope-guard, bash-lug-guard, communication-inbox-delta, gate-pool-serial-suites, hf-deploy, max-persona-boundary-guard, session-continuity-checkpoint, session-end-handoff, session-exit-commit, success-prediction, warmup-goals-review, wcl-verify-then-launch -- hooks bound PostToolUse filesTouchedRecorderHook.js, PreToolUse lugSchemaGateHook.js, UserPromptSubmit closeoutRequestHook.js (git 7e85f546..56d36285 -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-16T19:27:59.865Z -- source: tracks: git show 56d36285:.cut-status.json

## 2026-09-15

### runtime

- 06:05Z commit 23f79d7b [tracks] Session work: p0-bugfix-circle-audit-conversation-track-ingestion -- 23 file(s), area runtime -- source: tracks: git log main 23f79d7b
- 03:42Z commit 7e85f546 [tracks] Session work: 22 files, no lug transitions recorded -- 22 file(s), area runtime -- source: tracks: git log main 7e85f546
- 03:42Z commit f0026029 [tracks] harness-arrival-audit: absorbed 11 file(s) on cut arrival -- 13 file(s), area runtime -- source: tracks: git log main f0026029
- 00:17Z commit d306639d [tracks] tracks: v2 onboarding tail -- cut status 66e48e3a, ledger rows, first session's runtime and capture files (the arrival audit committed the 200-file cut itself at 96ffc65/9a6d6cb) -- 22 file(s), area runtime -- source: tracks: git log main d306639d

### cuts

- 03:42Z cut 79c1648d received by tracks (previous f40bc3fe) landed 7e85f546, posture absorb_and_report: +1/~0/-1 circles for tracks -- gained wcl-entry-directive -- removed conversation-track-ingestion -- hooks bound SessionStart wclEntryDirectiveHook.js (git d306639d..7e85f546 -- canon/circles, .claude/settings.json) -- source: tracks: git show 7e85f546:.cut-status.json
- 00:14Z cut f40bc3fe received by tracks (previous 66e48e3a) landed d306639d, posture absorb_and_report: +0/~0/-0 circles for tracks (git 9a6d6cb2..d306639d -- canon/circles, .claude/settings.json) -- source: tracks: git show d306639d:.cut-status.json
- 00:11Z cut 66e48e3a received by tracks (first cut) landed 9a6d6cb2, posture absorb_and_report: +0/~0/-0 circles for tracks (git 9a6d6cb2..9a6d6cb2 -- canon/circles, .claude/settings.json) -- published +3/~0/-0 circles, 0 lug(s) closed at 2026-09-14T23:27:44.981Z -- source: tracks: git show 9a6d6cb2:.cut-status.json

### canon

- 00:11Z commit 96ffc65b [tracks] harness-arrival-audit: absorbed 195 file(s) on cut arrival -- 195 file(s), area canon -- source: tracks: git log main 96ffc65b

### repo root

- 00:14Z commit 9a6d6cb2 [tracks] harness-arrival-audit: absorbed 5 file(s) on cut arrival -- 5 file(s), area repo root -- source: tracks: git log main 9a6d6cb2

### unaffiliated lugs

- 03:44Z lug at review p0-bugfix-circle-audit-conversation-track-ingestion [tracks] priority critical -- no certification receipt -- date from runtime/event-log.jsonl review transition -- readiness stubbed -- source: tracks: lugs/p0-bugfix-circle-audit-conversation-track-ingestion.yaml (runtime/event-log.jsonl review transition)

### WAI-Harness

- 00:18Z commit 1339bab0 [tracks] tracks: retire the v1 WAI-Harness machinery to /home/mario/projects/.archived/tracks-v1-260914 (WAI-Harness/, .claude/hooks, wai-enter/exit, the v1 settings and CLAUDE.md, basher's v1 session-cost advisor and its test) -- fully on the v2 harness (cut 66e48e3a); WAI-Spoke/sessions stays (Track files, product data) -- 1711 file(s), area WAI-Harness -- source: tracks: git log main 1339bab0

# Part 2 -- the wheel's history that reached tracks

## Cut 87971bbe -- received 2026-09-18 01:44Z (from 5c79e2c6)

01:44Z cut 87971bbe received by tracks (previous 5c79e2c6) (working tree), posture absorb_and_report: +0/~3/-0 circles for tracks -- changed dispatch-run-salvage, git-boundary-test-gate, hf-deploy (git fbb4ff64..working tree -- canon/circles, .claude/settings.json) -- published +0/~3/-0 circles, 0 lug(s) closed at 2026-09-18T01:40:52.511Z -- source: tracks: .cut-status.json (working tree, not yet committed)

Entries: 6 (commit 6).

### 2026-09-18

#### docs

- 01:19Z commit 87971bbe [harness-factory] git-boundary-test-gate circle doc under the rule-11 cap after two builders extended it (186 lease skip, 187 incremental gate + sweep yield): one lease section, tiers trimmed for meaning -- 2 file(s), area docs -- source: harness-factory: git log main 87971bbe

#### wheel-agents-talk-up-down-and-across

- 00:07Z commit 9cafbd1c [harness-factory] push-gate-runs-what-changed-since-the-last-proven-tree-and-the-sweep-yields-to-gates: the push gate runs the suites covering what changed since the last proven tree, reuses the proof for the rest; the full functional review runs once per cut; the sweep yields the corpus lease to a waiting gate -- lug push-gate-runs-what-changed-since-the-last-proven-tree-and-the-sweep-yields-to-gates -- fixtures 40/40, 31/31, 66/66, 15/15 -- 11 file(s), area src/factory -- source: harness-factory: git log main 9cafbd1c

### 2026-09-17

#### commits

- 23:22Z commit acfb6c13 [harness-factory] P0 round trip fulfilled by basher's reply (reply_to linked) -- 1 file(s), area lugs -- source: harness-factory: git log main acfb6c13
- 22:45Z commit 81fa1bbf [harness-factory] P0 round-trip request to basher (real run for MAX-184): no live basher session, rung C refused on the missing spoke envelope -- follow-up lug filed on the hub -- 1 file(s), area lugs -- source: harness-factory: git log main 81fa1bbf

#### taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-footer-does

- 23:18Z commit b5f24c4f [harness-factory] p0-tap-reads-the-wheel-envelope-from-the-hub-when-the-spoke-declares-none: rung C's headroom check resolves the hub's envelope first, the spoke's own second -- lug p0-tap-reads-the-wheel-envelope-from-the-hub-when-the-spoke-declares-none -- 3 file(s), area src/lugTracking -- source: harness-factory: git log main b5f24c4f

#### wheel-agents-talk-up-down-and-across

- 23:30Z commit 89a22492 [harness-factory] dispatch-launch-lifts-the-print-mode-background-ceiling-and-salvage-names-the-kill: lift Claude Code's 600s print-mode background ceiling on headless launches, name a print-mode kill and an uncommitted worktree in the work disposition, and let a registered dispatch worktree's commit gate skip the shared suite-corpus lease -- lug dispatch-launch-lifts-the-print-mode-background-ceiling-and-salvage-names-the-kill -- 10 file(s), area src/lugTracking -- source: harness-factory: git log main 89a22492

## Cut 5c79e2c6 -- received 2026-09-17 22:42Z (from b81e2bc1)

22:42Z cut 5c79e2c6 received by tracks (previous b81e2bc1) landed fbb4ff64, posture absorb_and_report: +0/~0/-0 circles for tracks (git c065e2ee..fbb4ff64 -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-17T22:38:25.849Z -- source: tracks: git show fbb4ff64:.cut-status.json

Entries: 2 (commit 2).

### 2026-09-17

#### conformance

- 22:22Z commit 5c79e2c6 [harness-factory] spokes-talk-directly fixture: the unfixed-code proof skips by name once HEAD carries the fix -- 1 file(s), area conformance -- source: harness-factory: git log main 5c79e2c6

#### taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-footer-does

- 21:45Z commit b877b91f [harness-factory] spokes-talk-directly-via-lugs-with-a-confirm-back-and-a-p0-taps-the-live-session: the P0 tap -- a critical request taps the target's live session mid-turn, queues a dispatch when nobody is there, and fulfilment lands back on the requester -- lug spokes-talk-directly-via-lugs-with-a-confirm-back-and-a-p0-taps-the-live-session -- fixtures 51/51 -- 10 file(s), area src/lugTracking -- source: harness-factory: git log main b877b91f

## Cut b81e2bc1 -- received 2026-09-17 21:18Z (from 4a839956)

21:18Z cut b81e2bc1 received by tracks (previous 4a839956) landed c065e2ee, posture absorb_and_report: +0/~0/-0 circles for tracks (git 7c2adcaa..c065e2ee -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-17T21:14:46.508Z -- source: tracks: git show c065e2ee:.cut-status.json

Entries: 2 (commit 1, lug_review 1).

### 2026-09-17

#### taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-footer-does

- 20:50Z commit b81e2bc1 [harness-factory] spokes-talk-directly-via-lugs-with-a-confirm-back-and-a-p0-taps-the-live-session: reply_to wires a reply back to its request, hf spoke-path resolves a sibling from the hub registry -- lug spokes-talk-directly-via-lugs-with-a-confirm-back-and-a-p0-taps-the-live-session -- 10 file(s), area src/conductor -- source: harness-factory: git log main b81e2bc1

#### unaffiliated lugs

- 19:33Z lug at review circle-schema-hook-event-name-lacks-stopfailure-and-worktreecreate [harness-factory] priority critical -- no certification receipt -- date from runtime/event-log.jsonl review transition -- readiness stubbed -- source: harness-factory: lugs/circle-schema-hook-event-name-lacks-stopfailure-and-worktreecreate.yaml (runtime/event-log.jsonl review transition)

## Cut 4a839956 -- received 2026-09-17 20:33Z (from ca0e4076)

20:33Z cut 4a839956 received by tracks (previous ca0e4076) landed 7c2adcaa, posture absorb_and_report: +0/~0/-0 circles for tracks (git 14fd1be8..7c2adcaa -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-17T20:29:51.348Z -- source: tracks: git show 7c2adcaa:.cut-status.json

Entries: 5 (commit 5).

### 2026-09-17

#### wheel-agents-talk-up-down-and-across

- 19:28Z commit 4a839956 [harness-factory] builder-lane-gate-takes-a-recorded-override-for-dispatches-that-predate-the-lane: the no-lane branch honours a recorded override; scripts/lane-override.js stamps a completed row with the reason and the veto row -- lug builder-lane-gate-takes-a-recorded-override-for-dispatches-that-predate-the-lane -- 7 file(s), area src/lugTracking -- source: harness-factory: git log main 4a839956
- 17:44Z commit 9988ca02 [harness-factory] wcl-bootstrap-pulls-a-sanitized-wheel-from-the-public-repo: repo-wide personal-leak scanner + first two identity files moved to .local/ -- lug wcl-bootstrap-pulls-a-sanitized-wheel-from-the-public-repo -- fixtures 5/150 -- 5 file(s), area src/compiler -- source: harness-factory: git log main 9988ca02

#### commits

- 20:05Z commit 0a5d51dd [harness-factory] confirm-back to basher: circle schema StopFailure/WorktreeCreate landed in cut c50fb9c876a3 -- 1 file(s), area lugs -- source: harness-factory: git log main 0a5d51dd

#### conformance

- 19:22Z commit c50fb9c8 [harness-factory] circle-schema-hook-event-name-lacks-stopfailure-and-worktreecreate: the enum carries StopFailure and WorktreeCreate; both bind into the generated settings.json -- lug circle-schema-hook-event-name-lacks-stopfailure-and-worktreecreate -- fixtures 9/9 -- 4 file(s), area conformance -- source: harness-factory: git log main c50fb9c8

#### wilbur-d-custodian-timeline-otto-steering

- 19:00Z commit e0cfe93b [harness-factory] change-log-entries-name-the-lug-and-tell-the-challenge-and-the-solution: per-lug ### blocks with Challenge/Solution/Record -- lug change-log-entries-name-the-lug-and-tell-the-challenge-and-the-solution -- 6 file(s), area src/factory -- source: harness-factory: git log main e0cfe93b

## Cut ca0e4076 -- received 2026-09-17 17:39Z (from 89051371)

17:39Z cut ca0e4076 received by tracks (previous 89051371) landed 14fd1be8, posture absorb_and_report: +0/~0/-0 circles for tracks (git 3e684e52..14fd1be8 -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-17T17:36:55.978Z -- source: tracks: git show 14fd1be8:.cut-status.json

Entries: 2 (commit 2).

### 2026-09-17

#### conformance

- 17:20Z commit ca0e4076 [harness-factory] circles-runner-final-verdict fixture: the unfixed-code proof skips by name once HEAD carries the fix -- fixtures 15 passed -- 1 file(s), area conformance -- source: harness-factory: git log main ca0e4076

#### wheel-agents-talk-up-down-and-across

- 16:58Z commit 0f90f8d5 [harness-factory] circles-runner-consumes-the-final-pool-verdict-not-the-first-timing-run: a timing suite's first pool verdict is provisional; the runner judges on the re-run's final verdict -- lug circles-runner-consumes-the-final-pool-verdict-not-the-first-timing-run -- fixtures 17/17, 66/66, 44/44 -- 6 file(s), area src/factory -- source: harness-factory: git log main 0f90f8d5

## Cut 89051371 -- received 2026-09-17 16:17Z (from 6e237e8f)

16:17Z cut 89051371 received by tracks (previous 6e237e8f) landed 3e684e52, posture absorb_and_report: +0/~0/-0 circles for tracks (git 1df4cd62..3e684e52 -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-17T16:13:44.078Z -- source: tracks: git show 3e684e52:.cut-status.json

Entries: 2 (commit 2).

### 2026-09-17

#### taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-footer-does

- 15:23Z commit 89051371 [harness-factory] advisor-drives-to-the-natural-end-point-and-landings-reach-the-operator-out-of-band: land notifications and drive-miss self-continue -- lug advisor-drives-to-the-natural-end-point-and-landings-reach-the-operator-out-of-band -- 19 file(s), area src/hooks -- source: harness-factory: git log main 89051371

#### wheel-agents-talk-up-down-and-across

- 14:58Z commit 2cfce55a [harness-factory] a-cut-ends-the-live-session-and-wcl-relaunches-it-on-the-new-rules: a cut landing on a spoke ends the live session's next prompt as a closeout, instead of it running for hours on hooks and canon a cut already replaced -- lug a-cut-ends-the-live-session-and-wcl-relaunches-it-on-the-new-rules -- 12 file(s), area src/hooks -- source: harness-factory: git log main 2cfce55a

## Cut 6e237e8f -- received 2026-09-17 09:49Z (from 8e61551f)

09:49Z cut 6e237e8f received by tracks (previous 8e61551f) landed 1df4cd62, posture absorb_and_report: +0/~0/-0 circles for tracks (git 1f8a6d8c..1df4cd62 -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-17T09:47:08.708Z -- source: tracks: git show 1df4cd62:.cut-status.json

Entries: 4 (commit 4).

### 2026-09-17

#### commits

- 07:01Z commit 2942ed72 [harness-factory] lug cut-requirements-on-profile-are-seeded-on-arrival-never-refused-at-launch: cut 8e61551f locked the operator out of every spoke over a key the cut could have seeded (permission_mode) -- lug cut-requirements-on-profile-are-seeded-on-arrival-never-refused-at-launch -- 1 file(s), area lugs -- source: harness-factory: git log main 2942ed72

#### conformance

- 09:10Z commit 6e237e8f [harness-factory] wcl-entry-welcome fixture accepts the keystroke remedy on the Rules row -- 1 file(s), area conformance -- source: harness-factory: git log main 6e237e8f

#### src/factory

- 08:44Z commit 06de36c5 [harness-factory] cut-requirements-on-profile-are-seeded-on-arrival-never-refused-at-launch: the arrival audit seeds required, hub-declared profile keys into the spoke profile; a key with no hub value offers the keystroke fix -- lug cut-requirements-on-profile-are-seeded-on-arrival-never-refused-at-launch -- fixtures 42/42 -- 8 file(s), area src/factory -- source: harness-factory: git log main 06de36c5

#### wheel-agents-talk-up-down-and-across

- 07:59Z commit 02aaefbb [harness-factory] lane-and-origin-refusals-reach-every-scratch-instance-the-fixtures-build: done-gate-evidence-paths' synthetic dispatch rows now carry model_lane/builder_model_observed via the writeDispatch helper (defaulting to SCRATCH_BUILDER_MODEL_LANE), so a completed row reaching the kernel verb's builder-lane gate is no longer refused for predating the field. -- lug lane-and-origin-refusals-reach-every-scratch-instance-the-fixtures-build -- 8 file(s), area conformance -- source: harness-factory: git log main 02aaefbb

## Cut 8e61551f -- received 2026-09-17 06:59Z (from c8ec1341)

06:59Z cut 8e61551f received by tracks (previous c8ec1341) landed 1f8a6d8c, posture absorb_and_report: +3/~14/-0 circles for tracks -- gained zellij-tab-identity-session-end, zellij-tab-identity-tool-reset, zellij-tab-identity-turn-start -- changed calibration-record, cross-provider-verification, dispatch-run-salvage, footer-audit, footer-correction-injection, hf-deploy, notification-agent-waiting-notify, readiness-certification-sweep, session-continuity-checkpoint, session-registry, stop-agent-waiting-notify, tastegraph-injection, warmup-goals-review, wcl-verify-then-launch -- hooks bound PreToolUse preToolTabResetHook.js, SessionEnd sessionEndTabClearHook.js, UserPromptSubmit userPromptSubmitTabHook.js (git 7b156f5f..1f8a6d8c -- canon/circles, .claude/settings.json) -- source: tracks: git show 1f8a6d8c:.cut-status.json

Entries: 28 (circle_added 4, commit 18, hook_bound 3, lug_review 3).

### 2026-09-17

#### circles

- 03:10Z circle wheel-change-log added at 4c791cce -- source: harness-factory: git log --diff-filter=A 4c791cce -- reference/circles/wheel-change-log.yaml
- 01:07Z hook PreToolUse -> node src/hooks/preToolTabResetHook.js (circle zellij-tab-identity-tool-reset) at ee6ff1a8 -- source: harness-factory: .claude/settings.json at 8e61551f vs c8ec1341
- 01:07Z hook SessionEnd -> node src/hooks/sessionEndTabClearHook.js (circle zellij-tab-identity-session-end) at ee6ff1a8 -- source: harness-factory: .claude/settings.json at 8e61551f vs c8ec1341
- 01:07Z hook UserPromptSubmit -> node src/hooks/userPromptSubmitTabHook.js (circle zellij-tab-identity-turn-start) at ee6ff1a8 -- source: harness-factory: .claude/settings.json at 8e61551f vs c8ec1341
- 00:20Z circle zellij-tab-identity-session-end added at 64bbef64 -- source: harness-factory: git log --diff-filter=A 64bbef64 -- reference/circles/zellij-tab-identity-session-end.yaml
- 00:20Z circle zellij-tab-identity-tool-reset added at 64bbef64 -- source: harness-factory: git log --diff-filter=A 64bbef64 -- reference/circles/zellij-tab-identity-tool-reset.yaml
- 00:20Z circle zellij-tab-identity-turn-start added at 64bbef64 -- source: harness-factory: git log --diff-filter=A 64bbef64 -- reference/circles/zellij-tab-identity-turn-start.yaml

#### commits

- 04:30Z commit 9e12bc6f [harness-factory] statusline fixture: the custodian's copy without the v2 path is basher's port, not this tree's red -- 3 file(s), area lugs -- source: harness-factory: git log main 9e12bc6f
- 01:07Z commit ee6ff1a8 [harness-factory] zellij tab identity: the three hook circles bound on the canonical checkout (compile-self --standing after the fold of 64bbef6); basher's two lugs (zellij tab identity, wcl freshness remedy) committed here at review -- fixtures 48/48, 33/33, 49/49 -- 3 file(s), area lugs -- source: harness-factory: git log main ee6ff1a8
- 01:05Z commit 66156307 [harness-factory] lug certification-verdicts-record-the-matcher-version-and-the-sweep-recertifies-when-it-changes: sweep 2 after the matcher change made 0 provider calls and moved 1 lug; the by-hand re-certification of 16 FABRICATED records flipped 11 -- lug certification-verdicts-record-the-matcher-version-and-the-sweep-recertifies-when-it-changes -- 1 file(s), area lugs -- source: harness-factory: git log main 66156307

#### unaffiliated lugs

- 04:02Z lug at review toast-is-one-short-line-per-turn [harness-factory] priority high -- no certification receipt -- date from runtime/event-log.jsonl review transition -- readiness stubbed -- Operator, 2026-09-16, after the fleet toast landed: "the toast notifications still seem off -- make sure they are clear and simple" -- source: harness-factory: lugs/toast-is-one-short-line-per-turn.yaml (runtime/event-log.jsonl review transition)
- 00:52Z lug at review wcl-freshness-refusal-offers-the-remedy-and-scaffold-rule-drift-is-not-local-drift [harness-factory] priority high -- no certification receipt -- date from runtime/event-log.jsonl review transition -- readiness stubbed -- Operator, 2026-09-16, at `wcl` in minder: "this is not a helpful end -- dont fail and exit, give options or take action to remediate" -- source: harness-factory: lugs/wcl-freshness-refusal-offers-the-remedy-and-scaffold-rule-drift-is-not-local-drift.yaml (runtime/event-log.jsonl review transition)
- 00:21Z lug at review zellij-tab-identity-and-gated-toast-are-a-fleet-circle [harness-factory] priority high -- no certification receipt -- date from runtime/event-log.jsonl review transition -- readiness stubbed -- source: harness-factory: lugs/zellij-tab-identity-and-gated-toast-are-a-fleet-circle.yaml (runtime/event-log.jsonl review transition)

#### wheel-agents-talk-up-down-and-across

- 06:06Z commit 9c297e7f [harness-factory] ozi-wakes-the-spoke-then-max-runs-it-and-the-footer-names-the-agent: Max persona as a cut-owned card and a record, footer agent segment -- lug ozi-wakes-the-spoke-then-max-runs-it-and-the-footer-names-the-agent -- fixtures 32/32 -- 27 file(s), area src/lugTracking -- source: harness-factory: git log main 9c297e7f
- 05:48Z commit 051c2f0f [harness-factory] builders-run-on-the-profile-builder-lane-never-the-planner-model: canon/profile.yaml gains builder_model_lane/planner_model_lane (wheel-wide, never defaulted, same shape as permission_mode); executeDispatch resolves option -> row -> profile and refuses a dispatch with no resolvable lane or one equal to the planner's, unless a laneOverride reason is given and recorded as a default-forward veto row; the dispatch row and lug receipt record the builder model actually observed via the journal's init event; the kernel verb's builderLaneGate.js refuses done on an un-overridden planner-lane build; the readiness sweep and Planner queue print the resolved lane per row. -- lug builders-run-on-the-profile-builder-lane-never-the-planner-model -- 18 file(s), area src/lugTracking -- source: harness-factory: git log main 051c2f0f
- 03:21Z commit b7fbb429 [harness-factory] wcl-pins-one-permission-mode-wheel-wide-from-the-profile: canon/profile.yaml gains permission_mode (schema enum = the installed claude --help's list); wclCli.js resolvePermissionMode reads it beside resolveModelLane -- the hub's profile is the wheel-wide value, a spoke must declare the same (mismatch refuses naming both, omission refuses naming the field, never a default), self-hosting takes the hub's -- and every interactive launch spawns `--model <lane> --permission-mode <mode>` (raw, ozi wake + resume, resume); headless launchSpoke argv byte-identical (proven with the fake claude); the scaffold interview declares it (auto unless answered); WCL_HUB_ROOT lets fixtures use a synthetic hub; compact view shows it as a Rules row -- lug wcl-pins-one-permission-mode-wheel-wide-from-the-profile -- 8 file(s), area src/basher -- source: harness-factory: git log main b7fbb429

#### src/basher

- 04:01Z commit 95198938 [harness-factory] toast-is-one-short-line-per-turn: at most one toast per turn, one short line -- idle_prompt never toasts alone, no answer excerpts, Default/Reminder only (no looping alarm), title `<glyph> <spoke> · <callsign>`, duplicate guard via last-toast-<pane> -- lug toast-is-one-short-line-per-turn -- fixtures 47/47 -- 8 file(s), area src/basher -- source: harness-factory: git log main 95198938
- 00:50Z commit cc8ef71c [harness-factory] wcl-freshness-refusal-offers-the-remedy-and-scaffold-rule-drift-is-not-local-drift: pendingCutVerdict compares each candidate to the recorded cut's own source (cutProducedFiles never refuse); at a real terminal the refusal is a chip menu -- a reverts canon/circles to the recorded cut behind a confirm naming every file, d diffs, q exits 1 -- and the remedy row keeps `then hf apply-cut <spoke>` -- lug wcl-freshness-refusal-offers-the-remedy-and-scaffold-rule-drift-is-not-local-drift -- fixtures 48/48 -- 7 file(s), area src/basher -- source: harness-factory: git log main cc8ef71c

#### wilbur-d-custodian-timeline-otto-steering

- 03:54Z commit 40a4f53d [harness-factory] change-log-is-an-artifact-in-every-spoke-and-carries-the-full-record: docs/CHANGELOG.md is a cut-owned generated doc on every spoke -- two parts from records (the spoke's own history: done lugs with the whole receipt, tests, cost and the quoted operator ruling; every cut received from its .cut-status.json git history with the circles gained/changed/removed and hooks bound between two landings; dispatches with measured tokens; its commits -- and per cut the framework entries in the git range previous..version), written by applyCut/rollbackCut after .cut-status.json through generatedDocs.js (third GENERATED_DOCS entry, stage after-status), by the hub clock job and by scaffoldInstance({ changeLog }); .cut-status.json lists cut_owned_files and generated_docs; the arrival audit absorbs it; the custody manifest names it; the file ends in an integrity seal that checkGeneratedDocsDrift, the commit gate and run-spoke-drift judge (a hand edit is refused, a pending regeneration is not drift); sha endpoints are git ranges for framework commits, circles and hooks -- lug change-log-is-an-artifact-in-every-spoke-and-carries-the-full-record -- fixtures 39/39, 34/34, 48/48, 33/33, 20/20, 11/11, 13/13, 51/51, 32/32, 25/25 -- 20 file(s), area src/factory -- source: harness-factory: git log main 40a4f53d
- 03:10Z commit 4c791cce [harness-factory] wheel-change-log-renders-from-the-record-layer: hf changelog renders the wheel's Change Log from the record layer only -- git log, done lugs with their certified_by receipt, cuts, circles added and hooks bound, dispatches completed -- two views, docs/CHANGELOG.md by the same verb (idempotent by hash), regenerated on the hub clock beside deploy_fleet -- lug wheel-change-log-renders-from-the-record-layer -- fixtures 12/12, 34/34, 31/31, 28/28, 57/57, 3 passed -- 13 file(s), area src -- source: harness-factory: git log main 4c791cce

#### session-entrance-exit-ux

- 03:34Z commit cc0ee90e [harness-factory] session-start-composer-under-two-seconds: per-section cache for the goals review and the checkpoint (runtime/goals-review-cache.json, keyed on declared inputs' mtime+size, the ledger's size/mtime/row count, the day and the composer's own code); one ledger read memo per start; kind-indexed ledger reads -- lug session-start-composer-under-two-seconds -- 16 file(s), area src/conductor -- source: harness-factory: git log main cc0ee90e

#### src/advisor

- 03:02Z commit 280fbb6f [harness-factory] certification-verdicts-record-the-matcher-version-and-the-sweep-recertifies-when-it-changes: MATCHER_VERSION on every record and attempt; readiness-sweep --recertify=stale (implied by --certify=run) re-runs citation-driven verdicts an older matcher produced -- lug certification-verdicts-record-the-matcher-version-and-the-sweep-recertifies-when-it-changes -- 9 file(s), area src/advisor -- source: harness-factory: git log main 280fbb6f

#### src/conductor

- 06:20Z commit 8e61551f [harness-factory] success-prediction registry path leaves the roiExtraction<->successPrediction import cycle -- fixtures 20/20, 191/191 -- 4 file(s), area src/conductor -- source: harness-factory: git log main 8e61551f

#### src/factory

- 00:06Z commit 35f211ec [harness-factory] push 30's two reds: closeout-report E2 judges live-peer telemetry movement as live state (the hub is a live instance; 8 of 8 attempts moved only telemetry beside an Otto session); a `// timing` head marker makes session-exit-path a timing suite for the gate's alone re-run (fixed-second budgets race the box; red at load 6.6, 102/102 alone) -- fixtures 102/102, 42/42, 44/44, 66/66 -- 4 file(s), area src/factory -- source: harness-factory: git log main 35f211ec

#### src/hooks

- 00:20Z commit 64bbef64 [harness-factory] zellij-tab-identity-and-gated-toast-are-a-fleet-circle: the zellij tab writer and basher v1's toast gate are one fleet mechanism every spoke gets with the cut -- lug zellij-tab-identity-and-gated-toast-are-a-fleet-circle -- fixtures 75/75, 34/34, 9/9, 31/31, 22/22, 28/28, 11/11, 48/48, 155/158 -- 24 file(s), area src/hooks -- source: harness-factory: git log main 64bbef64

#### src/lugTracking

- 03:17Z commit 40f63600 [harness-factory] disclosed-gap scan excludes the generated change log: docs/CHANGELOG.md quotes historical commit subjects and lug outcomes verbatim; its first regeneration raised 9 findings, all the past's own words -- 2 file(s), area src/lugTracking -- source: harness-factory: git log main 40f63600

#### src/tastegraph

- 04:15Z commit 5d25a542 [harness-factory] taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-footer-does: a taste miss closes its loop on the NEXT TURN the way the footer's does -- the Stop audit's miss row carries the judged lines and the footer-correction-injection hook (the one hook) injects one TASTE MISSED block under 120 tokens with the quoted lines and the dispute form; `dispute <key>: <why>` at the next Stop writes a taste-dispute row, a calibration record against the heuristic (ledger/ledger.jsonl joins REAL_EVIDENCE_STREAMS) and a per-session stop on re-injection; tastegraph schema gains applies_when (response_end | report_shaped | dispatch_reissue | late_night), fired as one line at its moment and listed by key only at wakeup (hub master: late_night_stays_high_level -> late_night, 999/1000 tokens; HF overlay: net_net_then_board -> report_shaped, the master has no headroom for it); recordAttempt on a re-issue writes runtime/pending-pattern-injection/<session>.json and the same hook prints vary-a-dispatch-before-reissuing-it with the prior attempt's failure line; every 10th response turn the footer audit prints TASTE REVIEW turns N-M and writes runtime/tastegraph-proposals/<key>.md for a key missed 3+ times undisputed, never editing master or overlay; a heuristic over 30% false positives on >= 3 shown misses is muted (no rows, no injection) and named at wakeup as a LIVE part; solutions_not_problems reads the content above a trailing fenced footer (stripTrailingFencedFooter, checkFooterPresent's own ID regex), not the fence. Real run on porcupine's transcript: 46 -> 34 misses over 109 responses (97 fenced), the last three audited responses still miss 4 on their real closing lines. Fixture taste-loop-closes 54/54; 20/27 fail on cc0ee90. -- lug taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-footer-does -- fixtures 999/1000, 54/54, 20/27 -- 18 file(s), area src/tastegraph -- source: harness-factory: git log main 5d25a542

#### taste-and-pattern-misses-close-the-loop-on-the-next-turn-like-the-footer-does

- 05:53Z commit 2293f20c [harness-factory] footer-identity-is-generated-from-spoke-registration-and-never-defaulted: the origin registry is compiled, never hand-typed -- lug footer-identity-is-generated-from-spoke-registration-and-never-defaulted -- fixtures 41/41 -- 24 file(s), area src/factory -- source: harness-factory: git log main 2293f20c

## Cut c8ec1341 -- received 2026-09-17 00:02Z (from 21926af8)

00:02Z cut c8ec1341 received by tracks (previous 21926af8) landed 7b156f5f, posture absorb_and_report: +0/~1/-0 circles for tracks -- changed cross-provider-verification (git 56d36285..7b156f5f -- canon/circles, .claude/settings.json) -- published +0/~1/-0 circles, 0 lug(s) closed at 2026-09-16T23:49:56.148Z -- source: tracks: git show 7b156f5f:.cut-status.json

Entries: 3 (commit 3).

### 2026-09-16

#### conformance

- 20:01Z commit c5aec643 [harness-factory] session-exit-path runs serial-first: its H.3-H.5 checks race a 12s commit-gate budget against a 15s covering suite and went red on push 28 at load 4 (13s measured) while 102/102 alone at load 1.3 -- the `// serial` marker gives it the alone run and the alone re-run before NEW RED -- fixtures 102/102 -- 1 file(s), area conformance -- source: harness-factory: git log main c5aec643

#### low-trust-multi-provider-verification

- 23:45Z commit c8ec1341 [harness-factory] fabrication-matcher-rejects-real-joined-and-restated-citations-and-one-rejection-fabricates-the-verdict: four line-locating tiers (prefix, bundler_line, yaml_json, multi_line) and a verdict policy that names a near miss instead of calling it a fabrication -- 20 replayed records: 7 bind, 9 PLAUSIBLE, 4 stay FABRICATED -- lug fabrication-matcher-rejects-real-joined-and-restated-citations-and-one-rejection-fabricates-the-verdict -- fixtures 1/3 -- 10 file(s), area src/advisor -- source: harness-factory: git log main c8ec1341

#### wcl-launches-on-the-global-sign-in-spokes-hold-only-local-settings

- 19:39Z commit 78877646 [harness-factory] provider-secrets-resolve-for-an-interactive-session-that-has-no-config-dir: resolveSecret reads bag -> set config dir -> canonical <frameworkRoot>/.local/secrets.json (only when CLAUDE_CONFIG_DIR is unset); the source rides on the result, the certification record (secrets_source) and certify --status's secrets: line; the two disclosed-gap passages carry the resolved rule -- lug provider-secrets-resolve-for-an-interactive-session-that-has-no-config-dir -- fixtures 4/17, 21/21 -- 8 file(s), area src/advisor -- source: harness-factory: git log main 78877646

## Cut 21926af8 -- received 2026-09-16 19:29Z (from 79c1648d)

19:29Z cut 21926af8 received by tracks (previous 79c1648d) landed 56d36285, posture absorb_and_report: +4/~12/-0 circles for tracks -- gained closeout-report, closeout-request, lug-write-schema-gate, session-files-touched -- changed agent-tool-scope-guard, bash-lug-guard, communication-inbox-delta, gate-pool-serial-suites, hf-deploy, max-persona-boundary-guard, session-continuity-checkpoint, session-end-handoff, session-exit-commit, success-prediction, warmup-goals-review, wcl-verify-then-launch -- hooks bound PostToolUse filesTouchedRecorderHook.js, PreToolUse lugSchemaGateHook.js, UserPromptSubmit closeoutRequestHook.js (git 7e85f546..56d36285 -- canon/circles, .claude/settings.json) -- published +0/~0/-0 circles, 0 lug(s) closed at 2026-09-16T19:27:59.865Z -- source: tracks: git show 56d36285:.cut-status.json

Entries: 78 (circle_added 4, commit 67, hook_bound 3, lug_done 1, lug_review 3).

### 2026-09-16

#### circles

- 04:28Z circle closeout-request added at 4af1942e -- source: harness-factory: git log --diff-filter=A 4af1942e -- reference/circles/closeout-request.yaml
- 04:28Z hook UserPromptSubmit -> node src/hooks/closeoutRequestHook.js (circle closeout-request) at 4af1942e -- source: harness-factory: .claude/settings.json at 21926af8 vs 79c1648d
- 00:48Z circle closeout-report added at 83bec491 -- source: harness-factory: git log --diff-filter=A 83bec491 -- reference/circles/closeout-report.yaml
- 00:12Z circle lug-write-schema-gate added at 3f30b7ba -- source: harness-factory: git log --diff-filter=A 3f30b7ba -- reference/circles/lug-write-schema-gate.yaml
- 00:12Z hook PreToolUse -> node src/hooks/lugSchemaGateHook.js (circle lug-write-schema-gate) at 3f30b7ba -- source: harness-factory: .claude/settings.json at 21926af8 vs 79c1648d

#### session-entrance-exit-ux

- 17:46Z commit 9d06435e [harness-factory] exit-prints-one-verdict-line: the exit hook prints one verdict line last and writes runtime/exit-verdict.json; wcl prints closed: after the session returns -- lug exit-prints-one-verdict-line -- fixtures 42 passed -- 10 file(s), area src/basher -- source: harness-factory: git log main 9d06435e
- 17:43Z commit f90947f7 [harness-factory] closeout-findings-carried-forward-and-rechecked-at-wakeup: the handoff carries findings[], the wakeup rechecks, retires, carries and escalates them -- lug closeout-findings-carried-forward-and-rechecked-at-wakeup -- 8 file(s), area src/lugTracking -- source: harness-factory: git log main f90947f7
- 04:23Z commit ede4ebd9 [harness-factory] closeout-request-injects-the-protocol: the closeout phrase injects the protocol on UserPromptSubmit (X2) -- lug closeout-request-injects-the-protocol -- fixtures 48/48 -- 6 file(s), area src/hooks -- source: harness-factory: git log main ede4ebd9
- 00:48Z commit 83bec491 [harness-factory] closeout-report-script: scripts/closeout.js, the read-only in-session closeout report (X1) -- lug closeout-report-script -- 8 file(s), area src/lugTracking -- source: harness-factory: git log main 83bec491

#### src/basher

- 19:00Z commit 203de44c [harness-factory] wcl-launches-on-the-global-sign-in-spokes-hold-only-local-settings: interactive wcl runs on the operator's ~/.claude (no CLAUDE_CONFIG_DIR, no per-spoke store, no credential copy, no fleet token); the Sign-in row reads the global store and its fix is `claude auth login`; custody is enforced on the spoke's own .claude/settings.json (+ settings.local.json); headless launchSpoke keeps the isolated store -- lug wcl-launches-on-the-global-sign-in-spokes-hold-only-local-settings -- fixtures 213/0 -- 11 file(s), area src/basher -- source: harness-factory: git log main 203de44c
- 17:39Z commit 8995713f [harness-factory] wcl-entry-directive never reaches a dispatched builder -- MAX-161 inherited WCL_ENTRY=ozi from its orchestrator, took the read-only wakeup directive as its own, briefed and exited in 3 minutes with 0 commits -- fixtures 24/24, 34/34 -- 3 file(s), area src/basher -- source: harness-factory: git log main 8995713f
- 00:14Z commit b4e6af7f [harness-factory] two-timing-suites-flake-under-box-load-and-refuse-real-pushes: the idle arm measures silence on the monotonic clock; the lease suite's run budget scales with its unit -- lug two-timing-suites-flake-under-box-load-and-refuse-real-pushes -- fixtures 3/3, 57/57, 43/43 -- 3 file(s), area src/basher -- source: harness-factory: git log main b4e6af7f

#### reference

- 04:28Z commit 4af1942e [harness-factory] closeout-request: circle declared and bound on the canonical checkout (MAX-158's binding.patch, applied after the fold of ede4ebd) -- fixtures 48/48, 18/18, 36/36 -- 5 file(s), area reference -- source: harness-factory: git log main 4af1942e
- 00:12Z commit 3f30b7ba [harness-factory] lug-write-schema-gate: circle declared and bound on the canonical checkout (MAX-155's binding.patch, applied after the fold of dfb0f6b) -- fixtures 49/49 -- 5 file(s), area reference -- source: harness-factory: git log main 3f30b7ba

#### src/conductor

- 09:43Z commit bc4c2afc [harness-factory] success-prediction: the assayer reader reads the coverage ledger the assayer really writes -- fixtures 191/191 -- 2 file(s), area src/conductor -- source: harness-factory: git log main bc4c2afc
- 09:39Z commit 272af7c0 [harness-factory] success-prediction: the miss routes through the ROI extractor, the clock grades what is due, every canon subject has a readable prediction -- fixtures 190/190, 119/119, 69/69 -- 10 file(s), area src/conductor -- source: harness-factory: git log main 272af7c0

#### src/factory

- 18:16Z commit 7e029800 [harness-factory] compiler-hook-script-node-only-drops-spoke-bash-hooks: the interpreter derives from hook_script's extension (.sh bash, .py python3, else node), hook_command is emitted verbatim, a spoke's own hook circles ride the cut, and every prior hook a cut does not carry forward is named as an arrival-audit finding -- lug compiler-hook-script-node-only-drops-spoke-bash-hooks -- fixtures 35/35 -- 11 file(s), area src/factory -- source: harness-factory: git log main 7e029800
- 17:54Z commit 1c0d927b [harness-factory] session-exit-commit returns the shared checkout to the branch it found after a red exit -- fox-skunk's refused red exit left this checkout on wip/2026-09-16-fox-skunk and the next session (porcupine) committed 8995713 there believing it was main -- fixtures 68/68, 26/26, 102/102 -- 2 file(s), area src/factory -- source: harness-factory: git log main 1c0d927b

#### src/hooks

- 18:30Z commit 2ef974c6 [harness-factory] scope-guard-action-restriction-is-not-a-write-restriction: a "Do NOT commit" restriction binds the git verb, never the write surface -- lug scope-guard-action-restriction-is-not-a-write-restriction -- fixtures 64/43, 19/26 -- 9 file(s), area src/hooks -- source: harness-factory: git log main 2ef974c6
- 01:11Z commit 4592d2c2 [harness-factory] lug-write-schema-gate also refuses an unresolved lineage parent at the keystroke -- push 20 was refused on pathfinder's COMMITTED audit-cron-fit-value (derived_from a bare archive path), which the schema alone let through -- fixtures 51/51, 149/149 -- 2 file(s), area src/hooks -- source: harness-factory: git log main 4592d2c2

#### conformance

- 19:18Z commit 21926af8 [harness-factory] two fixtures moved to the global-sign-in contract (model-lane-durable-declaration, secrets-template-migration -- push 26's 3 NEW REDs); lug filed for the gap MAX-163 disclosed: provider secrets for an interactive session with no config dir -- 3 file(s), area conformance -- source: harness-factory: git log main 21926af8

#### src/compiler

- 00:08Z commit dfb0f6b0 [harness-factory] push-gate-judges-a-snapshot-of-live-state-not-whatever-a-sibling-session-is-writing: the gate judges a committed corpus snapshot and lug writes are schema-checked at the keystroke -- lug push-gate-judges-a-snapshot-of-live-state-not-whatever-a-sibling-session-is-writing -- 10 file(s), area src/compiler -- source: harness-factory: git log main dfb0f6b0

### 2026-09-15

#### commits

- 23:13Z commit 9633b378 [harness-factory] lug push-gate-judges-a-snapshot-of-live-state-not-whatever-a-sibling-session-is-writing: 5 of 16 pushes today refused by other sessions' uncommitted or malformed live state -- lug push-gate-judges-a-snapshot-of-live-state-not-whatever-a-sibling-session-is-writing -- 1 file(s), area lugs -- source: harness-factory: git log main 9633b378
- 22:03Z commit 6f6504bc [harness-factory] lug wcl-enters-any-spoke-old-harness-or-unregistered-with-a-real-entry-and-warmup: scope folded from operator rulings 2026-09-15 (git-level consolidation, upgrade all the way, inferred interview); defined -> ready -> in_progress -> review with fixture wcl-enter-any-spoke (44/44) -- lug wcl-enters-any-spoke-old-harness-or-unregistered-with-a-real-entry-and-warmup -- fixtures 44/44 -- 1 file(s), area lugs -- source: harness-factory: git log main 6f6504bc
- 21:37Z commit 163050b4 [harness-factory] communication lug to basher: wcl-enters-any-spoke-old-harness-or-unregistered-with-a-real-entry-and-warmup -- 13 v1 spokes and 3 unregistered v2 spokes under the project roots that wcl cannot enter today (pathfinder measured) -- 1 file(s), area lugs -- source: harness-factory: git log main 163050b4
- 21:16Z commit 571d3609 [harness-factory] retire the origin copy: promoted to wheel-hub and done there (506433a5) -- 1 file(s), area lugs -- source: harness-factory: git log main 571d3609
- 21:02Z commit 6af0f848 [harness-factory] lug two-timing-suites-flake-under-box-load-and-refuse-real-pushes: launch-idle-watchdog and liveness-lease read red on pushes 9 and 10 (lug-only commit, green on push 8), green alone at load 2.1 -- lug two-timing-suites-flake-under-box-load-and-refuse-real-pushes -- 1 file(s), area lugs -- source: harness-factory: git log main 6af0f848
- 18:31Z commit b2fae708 [harness-factory] lug push-main-blocked-on-taste-injection-digest-contract: review -> done, CONFIRMED via claude-sonnet-5 (author opus, 3 verbatim citations), cost unmeasured-pre-attribution with its ledger row -- lug push-main-blocked-on-taste-injection-digest-contract -- 1 file(s), area lugs -- source: harness-factory: git log main b2fae708
- 17:49Z commit ab87b73f [harness-factory] lug push-gate-and-regression-oracle-sweep-collide-on-the-box-and-the-harness-kills-the-push: two pushes killed by the memory watchdog on 2026-09-15 while the hub's regression_oracle sweep ran the same corpus -- lug push-gate-and-regression-oracle-sweep-collide-on-the-box-and-the-harness-kills-the-push -- 1 file(s), area lugs -- source: harness-factory: git log main ab87b73f
- 16:05Z commit 62750a75 [harness-factory] basher's blocker lug overtaken (defined -> ready -> review: f2477c8 landed its option b, pushed 271/271); peer lug's review edit committed; lug filed: harness-factory has no Proofer, so a non-proof_required lug can never reach done -- fixtures 271/271 -- 3 file(s), area lugs -- source: harness-factory: git log main 62750a75
- 15:51Z commit 5c99d268 [harness-factory] lug push-main-blocked-on-taste-injection-digest-contract: from the basher lane -- main (34 ahead) is gated on 26aef71's TASTES digest vs the taste-injection fixture; decide, land, push; retire beaver + the basher session branch -- lug push-main-blocked-on-taste-injection-digest-contract -- 1 file(s), area lugs -- source: harness-factory: git log main 5c99d268
- 07:37Z commit 565cfe4f [harness-factory] p0 circle-audit batch of 2026-09-11T07:31Z returned as one cause; lug wip-branches-from-session-exit-commit-are-never-folded-or-cleaned filed -- lug wip-branches-from-session-exit-commit-are-never-folded-or-cleaned -- 26 file(s), area lugs -- source: harness-factory: git log main 565cfe4f
- 05:20Z commit 862d5c33 [harness-factory] lug wcl-launches-on-the-global-sign-in-spokes-hold-only-local-settings: operator ruling -- basher manages the global config, spokes hold local settings; wcl stops isolating credentials per spoke -- lug wcl-launches-on-the-global-sign-in-spokes-hold-only-local-settings -- 1 file(s), area lugs -- source: harness-factory: git log main 862d5c33
- 04:46Z commit 2ef4a2a9 [harness-factory] lug wcl-signs-in-with-a-long-lived-fleet-token: defined -> ready(stubbed) -> review (1623f30) -- lug wcl-signs-in-with-a-long-lived-fleet-token -- 1 file(s), area lugs -- source: harness-factory: git log main 2ef4a2a9
- 04:12Z commit 9cc8815c [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area lugs -- source: harness-factory: git log main 9cc8815c
- 03:39Z commit f7155a6a [harness-factory] lug session-exit-commit-sweeps-a-peer-lanes-in-flight-files: the exit hook committed basher s128's in-flight wcl menu fix as 'Session work' (385a6cb, 5bd3432) -- provenance lost, could have been broken -- lug session-exit-commit-sweeps-a-peer-lanes-in-flight-files -- 1 file(s), area lugs -- source: harness-factory: git log main f7155a6a

#### src/basher

- 22:59Z commit eb29be57 [harness-factory] wcl: one global sign-in -- the fleet token resolves from and is stored in the framework checkout's .local/secrets.json (WCL_FLEET_ROOT overrides; spoke-level store kept as fallback), new verb wcl signin runs claude setup-token from any folder; operator 2026-09-15: login was per spoke -- 3 file(s), area src/basher -- source: harness-factory: git log main eb29be57
- 22:52Z commit f283e0d2 [harness-factory] wcl upgrade: gitignore .local/ before the first cut -- found live on pathfinder, where the launch's arrival audit committed 455 files of the composed provider config dir; fixture asserts check-ignore on a composed .claude.json -- 2 file(s), area src/basher -- source: harness-factory: git log main f283e0d2
- 22:45Z commit f57dc063 [harness-factory] wcl upgrade: retire-v1 lug carries out_of_scope (lug schema work-type clause) -- found live on pathfinder's first launch, where the cut re-apply rolled back on the schema-invalid lug; fixture now compiles the upgraded spoke refuse-free and re-applies the cut -- 2 file(s), area src/basher -- source: harness-factory: git log main f57dc063
- 22:00Z commit 5f0aad13 [harness-factory] wcl enters any folder: classify (v2|v1|unscaffolded|not-a-repo), offer initiate/register, consolidate (git-level, confirm per action, never -A/reset/clean), upgrade all the way (backup v1 settings, scaffold, promote v2 hooks, register known-repos + hub entity + wheel group, apply cut, retire-v1 lug, scoped commit); inferred-defaults interview for wcl init -- lug wcl-enters-any-spoke-old-harness-or-unregistered-with-a-real-entry-and-warmup -- lug wcl-enters-any-spoke-old-harness-or-unregistered-with-a-real-entry-and-warmup -- 9 file(s), area src/basher -- source: harness-factory: git log main 5f0aad13
- 08:08Z commit b484121f [harness-factory] wcl: a linked worktree's git identity outranks its basename -- the push-gate worktree <tmp>/push-gate-harness-factory-<sha>/harness-factory served the main checkout in its own place -- fixtures 19/19 -- 1 file(s), area src/basher -- source: harness-factory: git log main b484121f
- 06:26Z commit a9ffd90c [harness-factory] Session work: 10 files, no lug transitions recorded -- 10 file(s), area src/basher -- source: harness-factory: git log main a9ffd90c
- 05:10Z commit 54ca4d45 [harness-factory] wcl: sign in BEFORE launch when the store is unsigned; fleet-token capture survives Ink line-wrap and is verified before it is stored -- fixtures 177/177, 18/18 -- 3 file(s), area src/basher -- source: harness-factory: git log main 54ca4d45
- 04:45Z commit 552037ad [harness-factory] wcl: one sign-in for the fleet -- a long-lived token, stored once, injected into every launch; `s` sets it up from the menu -- fixtures 157/157 -- 3 file(s), area src/basher -- source: harness-factory: git log main 552037ad
- 03:18Z commit 96c98b9d [harness-factory] Session work: 3 files, no lug transitions recorded -- 3 file(s), area src/basher -- source: harness-factory: git log main 96c98b9d
- 03:10Z commit f8b169a9 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area src/basher -- source: harness-factory: git log main f8b169a9

#### src/factory

- 23:41Z commit 93e4c1a7 [harness-factory] two-timing-suites-flake-under-box-load-and-refuse-real-pushes: windows scale with measured load, a red serial-first timing suite is re-run once alone -- lug two-timing-suites-flake-under-box-load-and-refuse-real-pushes -- fixtures 39/39, 66/66 -- 7 file(s), area src/factory -- source: harness-factory: git log main 93e4c1a7
- 21:37Z commit 0117742b [harness-factory] push-gate-and-regression-oracle-sweep-collide-on-the-box-and-the-harness-kills-the-push: one corpus lease for gate and sweep, memory-aware pool -- lug push-gate-and-regression-oracle-sweep-collide-on-the-box-and-the-harness-kills-the-push -- fixtures 272/272, 44/44, 31/31, 66/66, 50/50 -- 6 file(s), area src/factory -- source: harness-factory: git log main 0117742b
- 21:33Z commit e1f9b302 [harness-factory] wip-branches-from-session-exit-commit-are-never-folded-or-cleaned: hf deploy fold and clean read wip/* beside dispatch/* -- lug wip-branches-from-session-exit-commit-are-never-folded-or-cleaned -- fixtures 26/0, 67/0, 71/0, 102/0, 8 passed -- 7 file(s), area src/factory -- source: harness-factory: git log main e1f9b302
- 07:07Z commit 9a2b46e7 [harness-factory] session-exit-commit stages only the session's own files -- never `git add -A` again (lug session-exit-commit-sweeps-a-peer-lanes-in-flight-files) -- lug session-exit-commit-sweeps-a-peer-lanes-in-flight-files -- fixtures 102/102, 64/64, 40/40 -- 15 file(s), area src/factory -- source: harness-factory: git log main 9a2b46e7
- 04:41Z commit 290b1f72 [harness-factory] push gate: the ratchet baseline and suite timings (gitignored runtime/) are copied into the clean push-gate worktree -- the first real ref-gate run (dbfff96) judged 18 baselined reds as 'failing and this repo has no ratchet baseline'; integrator fix on main by session 4f1a0301, fixture 70/70 -- fixtures 70/70 -- 1 file(s), area src/factory -- source: harness-factory: git log main 290b1f72
- 03:45Z commit 04737711 [harness-factory] lug p0-bugfix-circle-audit-conversation-track-ingestion: a cut ships a hosted_by: instance circle only to the instance that hosts it -- lug p0-bugfix-circle-audit-conversation-track-ingestion -- 2 file(s), area src/factory -- source: harness-factory: git log main 04737711

#### advisor-pattern-hub-managed-spoke-leveraged

- 02:58Z commit 79bbcc1e [harness-factory] concurrent-sessions-on-one-checkout-never-collide: the push gate hands every suite the main checkout its temp tree stands for (WHEEL_GATE_MAIN_CHECKOUT) -- measured on the real hub: one identity-by-path suite cannot find itself in a temp worktree -- lug concurrent-sessions-on-one-checkout-never-collide -- 2 file(s), area src/factory -- source: harness-factory: git log main 79bbcc1e
- 02:33Z commit a57be628 [harness-factory] a-spoke-session-never-edits-another-repos-canonical-checkout: a top-level write into another registered repo's canonical checkout is refused regardless of posture, Edit/Write/NotebookEdit and write-shaped Bash alike -- lug a-spoke-session-never-edits-another-repos-canonical-checkout -- fixtures 25 passed -- 9 file(s), area src/hooks -- source: harness-factory: git log main a57be628
- 02:19Z commit 5bdcc37f [harness-factory] concurrent-sessions-on-one-checkout-never-collide: a symlinked node_modules/.local in a worktree is machine state, never dirt -- found on the real run (the .local link read as '?? .local' and would have refused the fold's clean removal); fixture proves a placed worktree's commit folds and removes clean -- lug concurrent-sessions-on-one-checkout-never-collide -- 2 file(s), area src/factory -- source: harness-factory: git log main 5bdcc37f
- 02:15Z commit 84b79fb6 [harness-factory] concurrent-sessions-on-one-checkout-never-collide: the push gate judges the pushed ref in a clean registered worktree; a second live session gets a session/<callsign> worktree at wcl entry; one locked commit helper names the holder; main is written by the fold only -- lug concurrent-sessions-on-one-checkout-never-collide -- 15 file(s), area src/factory -- source: harness-factory: git log main 84b79fb6

#### review-transition-certifies-before-the-session-commits-so-the-bundle-never-sees-the-work

- 17:13Z commit 7d34a7ef [harness-factory] harness-factory-has-no-proofer-so-a-non-proof-required-lug-can-never-reach-done: ONE loadProoferAdvisor resolves instance -> registered hub -> none, and the record says which -- lug harness-factory-has-no-proofer-so-a-non-proof-required-lug-can-never-reach-done -- fixtures 38/38, 9/29, 25/25, 92/92, 65/65 -- 8 file(s), area src/advisor -- source: harness-factory: git log main 7d34a7ef
- 04:09Z commit dbfff960 [harness-factory] independent-review-receipt-and-notice-on-every-done: legacy done lugs carry a DISCLOSED legacy receipt, the verb refuses it on a fresh done, the debt stays counted (MAX-151, third leg after MAX-143/150) -- lug independent-review-receipt-and-notice-on-every-done -- fixtures 143/150, 88 passed, 95 passed, 152 passed -- 6 file(s), area src/advisor -- source: harness-factory: git log main dbfff960
- 03:45Z commit df2e4aa4 [harness-factory] independent-review-receipt-and-notice-on-every-done: the readiness sweep through the REAL verb -- a low-priority lug with a non-author record reaches done stamped, one with no verdict is left at review naming the policy (MAX-150, continuation of MAX-143's 43938e8) -- lug independent-review-receipt-and-notice-on-every-done -- 1 file(s), area conformance -- source: harness-factory: git log main df2e4aa4
- 03:18Z commit ab29eb02 [harness-factory] independent-review-receipt-and-notice-on-every-done: every done carries certified_by, every lug gets an independent reviewer, the operator is told -- lug independent-review-receipt-and-notice-on-every-done -- 46 file(s), area src/advisor -- source: harness-factory: git log main ab29eb02

#### unaffiliated lugs

- 22:02Z lug at review wcl-enters-any-spoke-old-harness-or-unregistered-with-a-real-entry-and-warmup [harness-factory] priority high -- no certification receipt -- date from runtime/event-log.jsonl review transition -- readiness stubbed -- Operator, 2026-09-15: "how can I enter a spoke (or new spoke) like pathfinder which is running an old version of the harness -- wcl should give me the proper entry and warmup." -- source: harness-factory: lugs/wcl-enters-any-spoke-old-harness-or-unregistered-with-a-real-entry-and-warmup.yaml (runtime/event-log.jsonl review transition)
- 18:30Z lug done push-main-blocked-on-taste-injection-digest-contract [harness-factory] priority high -- verdict CONFIRMED via claude/claude-sonnet-5 -- date from certified_by.at -- reviewer session c2e8739d-ca64-4fbd-b8ab-5fb7f686c52b -- record runtime/cross-provider-certifications/push-main-blocked-on-taste-injection-digest-contract.json (external) -- tests conformance/fixtures/proofer-hub-fallback/proofer-hub-fallback.conformance.test.js -- readiness stubbed -- source: harness-factory: lugs/push-main-blocked-on-taste-injection-digest-contract.yaml (certified_by.at)
- 07:17Z lug at review session-exit-commit-sweeps-a-peer-lanes-in-flight-files [harness-factory] priority high -- no certification receipt -- date from runtime/event-log.jsonl review transition -- readiness stubbed -- source: harness-factory: lugs/session-exit-commit-sweeps-a-peer-lanes-in-flight-files.yaml (runtime/event-log.jsonl review transition)
- 04:46Z lug at review wcl-signs-in-with-a-long-lived-fleet-token [harness-factory] priority critical -- no certification receipt -- date from runtime/event-log.jsonl review transition -- readiness stubbed -- Operator, 2026-09-14 (basher s128): "I cant successfully exit or reenter ... if you can automate the action i prefer that over directions." -- source: harness-factory: lugs/wcl-signs-in-with-a-long-lived-fleet-token.yaml (runtime/event-log.jsonl review transition)

#### .claude

- 06:30Z commit 16b0a91e [harness-factory] session-exit-commit: bounded to Claude Code's real ~60s window -- 12s commit-gate budget, never push at exit, 45s wall cap; the prior "Session work: 10 files" commit (5d6266c) carries the code -- fixtures 87/87, 64/64, 18/18, 21/21, 210/210 -- 2 file(s), area .claude -- source: harness-factory: git log main 16b0a91e
- 02:46Z commit a097d661 [harness-factory] compile-self --standing after the wcl-entry-directive fold: SessionStart binding for src/hooks/wclEntryDirectiveHook.js (UserPromptSubmit order is the compiler's canonical order) -- 1 file(s), area .claude -- source: harness-factory: git log main a097d661

#### circles

- 07:07Z circle session-files-touched added at 9a2b46e7 -- source: harness-factory: git log --diff-filter=A 9a2b46e7 -- reference/circles/session-files-touched.yaml
- 07:07Z hook PostToolUse -> node src/hooks/filesTouchedRecorderHook.js (circle session-files-touched) at 9a2b46e7 -- source: harness-factory: .claude/settings.json at 21926af8 vs 79c1648d

#### conformance

- 21:54Z commit 58d88c73 [harness-factory] two source-shape checks on stageFold updated for the wip/* fold (e1f9b30): worktree-registry B5 reads the whole function, not a 6000-char window; receipt F8 accepts folded.filter(has lug).map -- fixtures 55/55, 39/39, 95/95 -- 2 file(s), area conformance -- source: harness-factory: git log main 58d88c73
- 02:16Z commit e7fb61bb [harness-factory] Session work: 0 files, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main e7fb61bb

#### src/advisor

- 17:34Z commit 55d663df [harness-factory] provider-contract: the Proofer prompt rides argv under 100 KB and stdin above it -- the all-stdin form (e87e93c) broke five stub-claude fixtures with EPIPE -- fixtures 43/43, 42/42, 43/95, 63/38 -- 2 file(s), area src/advisor -- source: harness-factory: git log main 55d663df
- 17:21Z commit e87e93cd [harness-factory] Proofer prompt goes over stdin (E2BIG on the first hub-resolved call); taste-injection's first-sight check names the contract it asserts; basher's lug carries its pointers and verification -- fixtures 38/38, 25/25, 92/92, 36/36, 271/271 -- 3 file(s), area src/advisor -- source: harness-factory: git log main e87e93cd

#### conductor-autonomous-loop

- 03:16Z commit d1db3553 [harness-factory] planner-shortfall-waterfalls-proportionally: classBalance.js reads the policy's shortfall rule -- a spent class's floor waterfalls to the live classes in proportion to theirs, per-class released/received on the artifact -- lug planner-shortfall-waterfalls-proportionally -- fixtures 69/69, 33/33, 5/0, 2/0, 15/0, 4/0, 3/0, 4/3 -- 5 file(s), area src/planner -- source: harness-factory: git log main d1db3553

#### scaffolded-spoke-ships-schedule-circles-with-no-wheel-clock

- 02:06Z commit 979153cd [harness-factory] cut-gives-a-clockless-spoke-the-default-wheel-clock: applyCut writes the canon default clock to a spoke that declares none -- lug cut-gives-a-clockless-spoke-the-default-wheel-clock -- fixtures 15 passed -- 4 file(s), area src/factory -- source: harness-factory: git log main 979153cd

#### session-entrance-exit-ux

- 03:49Z commit 26aef712 [harness-factory] session-start-injection-action-block-then-delta-digest: the SessionStart injection opens with the operator BOARD and every standing section follows as a one-line digest with its delta -- measured on the real wheel-hub 4170 -> 1747 tokens (canon 959 -> 444, live 3211 -> 1303), two real hooks 1162, cap unchanged at 2300 -- lug session-start-injection-action-block-then-delta-digest -- 15 file(s), area src/conductor -- source: harness-factory: git log main 26aef712

#### src/lugTracking

- 08:26Z commit f2477c8e [harness-factory] push gate's third run: first-sight TASTES collapsed to its own refresh stamp (26aef71); check-ignore refused through the gate worktree's symlinked .local -- fixtures 35/36, 36/36, 67/67, 65/65, 40/40, 82/82 -- 3 file(s), area src/lugTracking -- source: harness-factory: git log main f2477c8e

#### tastegraph

- 03:29Z commit 8f6b7239 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area tastegraph -- source: harness-factory: git log main 8f6b7239

#### three-suites-flake-only-inside-the-gate-pool-and-block-every-push

- 03:26Z commit 759ff3ea [harness-factory] fixtures-never-pin-a-real-spokes-state: fixture lint in the commit gate (a real spoke root + a literal expectation is refused with the line quoted; consistency with the spoke's own recorded state is the named alternative) and the generated-docs drift check runs on every commit regardless of the staged set -- measured 19% false positives over 263 fixtures at first cut; the gate's first live run refused THIS commit on main's own stale CLAUDE.md/AMBASSADOR_BRIEF.md (79bbcc1 never regenerated after wcl-entry-directive), regenerated here byte-identical to 0ccc12f -- lug fixtures-never-pin-a-real-spokes-state -- 5 file(s), area src/factory -- source: harness-factory: git log main 759ff3ea

## Cut 79c1648d -- received 2026-09-15 03:42Z (from f40bc3fe)

03:42Z cut 79c1648d received by tracks (previous f40bc3fe) landed 7e85f546, posture absorb_and_report: +1/~0/-1 circles for tracks -- gained wcl-entry-directive -- removed conversation-track-ingestion -- hooks bound SessionStart wclEntryDirectiveHook.js (git d306639d..7e85f546 -- canon/circles, .claude/settings.json) -- source: tracks: git show 7e85f546:.cut-status.json

Entries: 16 (circle_added 1, commit 12, hook_bound 1, lug_review 2).

### 2026-09-15

#### src/basher

- 03:18Z commit 5bd34323 [harness-factory] Session work: 3 files, no lug transitions recorded -- 3 file(s), area src/basher -- source: harness-factory: git log main 5bd34323
- 03:10Z commit 385a6cb9 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area src/basher -- source: harness-factory: git log main 385a6cb9
- 01:44Z commit 6f531ab7 [harness-factory] wcl: rows are assured capabilities; a SessionStart circle injects the entry-matched opening contract -- fixtures 111/111, 19/19, 18/18, 6/6, 152/152 -- 9 file(s), area src/basher -- source: harness-factory: git log main 6f531ab7
- 00:35Z commit 9c2007a8 [harness-factory] wcl: the entry is a welcome -- raw session or Ozi wakeup, one keystroke -- fixtures 85/85, 18/18, 17/17, 39/39, 152/152 -- 5 file(s), area src/basher -- source: harness-factory: git log main 9c2007a8

#### commits

- 03:39Z commit 79c1648d [harness-factory] lug session-exit-commit-sweeps-a-peer-lanes-in-flight-files: the exit hook committed basher s128's in-flight wcl menu fix as 'Session work' (385a6cb, 5bd3432) -- provenance lost, could have been broken -- lug session-exit-commit-sweeps-a-peer-lanes-in-flight-files -- 1 file(s), area lugs -- source: harness-factory: git log main 79c1648d
- 01:44Z commit bbc6c01c [harness-factory] lug wcl-rows-are-assured-capabilities-and-entry-matched-injection: defined -> ready(stubbed) -> review -- lug wcl-rows-are-assured-capabilities-and-entry-matched-injection -- 1 file(s), area lugs -- source: harness-factory: git log main bbc6c01c
- 00:36Z commit 67676f94 [harness-factory] lug wcl-entry-is-a-welcome-raw-or-ozi-wakeup: defined -> ready(stubbed) -> review -- lug wcl-entry-is-a-welcome-raw-or-ozi-wakeup -- 1 file(s), area lugs -- source: harness-factory: git log main 67676f94

#### circles

- 02:46Z hook SessionStart -> node src/hooks/wclEntryDirectiveHook.js (circle wcl-entry-directive) at 86af6d29 -- source: harness-factory: .claude/settings.json at 79c1648d vs f40bc3fe
- 01:44Z circle wcl-entry-directive added at 6f531ab7 -- source: harness-factory: git log --diff-filter=A 6f531ab7 -- reference/circles/wcl-entry-directive.yaml

#### unaffiliated lugs

- 01:44Z lug at review wcl-rows-are-assured-capabilities-and-entry-matched-injection [harness-factory] priority high -- no certification receipt -- date from runtime/event-log.jsonl review transition -- readiness stubbed -- Operator, 2026-09-14 (basher s128), on the first welcome cut (9c2007a): "each row should be a feature/capability that is assured. Codebase is ready or not ready (remediating action). I dont care if hooks are 37 but id like to know that the workspace is ready to be used (if not remediating action).... and on entering the session the prompt injected that matches either raw or wakeup to make best use of users time." -- source: harness-factory: lugs/wcl-rows-are-assured-capabilities-and-entry-matched-injection.yaml (runtime/event-log.jsonl review transition)
- 00:36Z lug at review wcl-entry-is-a-welcome-raw-or-ozi-wakeup [harness-factory] priority high -- no certification receipt -- date from runtime/event-log.jsonl review transition -- readiness stubbed -- Operator, 2026-09-14 (basher s128): "improve the entry via wcl so it is more delightful and user can choose a raw session or to allow Ozi to wakeup and advise options. This is too rough - i want joy and delight" -- source: harness-factory: lugs/wcl-entry-is-a-welcome-raw-or-ozi-wakeup.yaml (runtime/event-log.jsonl review transition)

#### .claude

- 02:46Z commit 86af6d29 [harness-factory] compile-self --standing after the wcl-entry-directive fold: SessionStart binding for src/hooks/wclEntryDirectiveHook.js (UserPromptSubmit order is the compiler's canonical order) -- 1 file(s), area .claude -- source: harness-factory: git log main 86af6d29

#### conformance

- 02:16Z commit 8294fd6c [harness-factory] Session work: 0 files, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main 8294fd6c

#### repo root

- 02:17Z commit 0ccc12fd [harness-factory] regenerate-docs: live circles 92 -> 94 (worktree-registry from 41896a7, wcl-entry-directive from 6f531ab) -- 2 file(s), area repo root -- source: harness-factory: git log main 0ccc12fd

#### review-transition-certifies-before-the-session-commits-so-the-bundle-never-sees-the-work

- 01:30Z commit db69e054 [harness-factory] independent-review-is-required-and-visible: policy from the 2026-09-14 operator direction -- the agent that did the work never verifies it as done; every lug at every priority reaches done only on a reviewer independent of the author (session axis plus model-or-provider); the operator is told when a third-party reviewer is enjoined and what it returned (spoke message printed by the inbox delta, goals-review tally, certified_by receipt on the lug); mechanics in lug independent-review-receipt-and-notice-on-every-done; generated docs regenerated (13 policies) -- lug independent-review-receipt-and-notice-on-every-done -- 3 file(s), area repo root -- source: harness-factory: git log main db69e054

#### tastegraph

- 03:29Z commit a3aefc94 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area tastegraph -- source: harness-factory: git log main a3aefc94

## Cut f40bc3fe -- received 2026-09-15 00:14Z (from 66e48e3a)

00:14Z cut f40bc3fe received by tracks (previous 66e48e3a) landed d306639d, posture absorb_and_report: +0/~0/-0 circles for tracks (git 9a6d6cb2..d306639d -- canon/circles, .claude/settings.json) -- source: tracks: git show d306639d:.cut-status.json

Entries: 1 (commit 1).

### 2026-09-15

#### commits

- 00:12Z commit f40bc3fe [harness-factory] lug compiler-hook-script-node-only-drops-spoke-bash-hooks: generate.js emits node-only bindings, so the v2 cut silently dropped every basher-local bash hook (change-lug from basher s127) -- lug compiler-hook-script-node-only-drops-spoke-bash-hooks -- 1 file(s), area lugs -- source: harness-factory: git log main f40bc3fe

## Cut 66e48e3a -- received 2026-09-15 00:11Z (first cut)

00:11Z cut 66e48e3a received by tracks (first cut) landed 9a6d6cb2, posture absorb_and_report: +0/~0/-0 circles for tracks (git 9a6d6cb2..9a6d6cb2 -- canon/circles, .claude/settings.json) -- published +3/~0/-0 circles, 0 lug(s) closed at 2026-09-14T23:27:44.981Z -- source: tracks: git show 9a6d6cb2:.cut-status.json

Entries: 485 (circle_added 94, commit 353, hook_bound 37, lug_review 1).

### 2026-09-14

#### conformance

- 23:19Z commit 66e48e3a [harness-factory] secrets-template-migration fixture names its root REPO_ROOT: circle-completeness-audit resolves an on_demand circle's entry point from that construction, so the FRAMEWORK_ROOT spelling read as PHANTOM on the hub (92/93) and refused the push; hub audit now 93/93 with 0 phantom -- fixtures 92/93, 93/93 -- 1 file(s), area conformance -- source: harness-factory: git log main 66e48e3a
- 21:58Z commit a2df577b [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main a2df577b
- 21:12Z commit 75f4abfc [harness-factory] pending-cut-verdict fixture: the real-spoke section asserts consistency with each spoke's own .cut-status.json instead of a pinned snapshot -- it pinned "minder: no recorded cut" and went red the same afternoon minder took its first cut (48746ea); basher will move on every hf deploy the same way -- 1 file(s), area conformance -- source: harness-factory: git log main 75f4abfc
- 20:47Z commit 2d771e9b [harness-factory] Session work: 0 files, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main 2d771e9b
- 20:40Z commit 0482abf5 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main 0482abf5
- 20:16Z commit 3039de93 [harness-factory] Session work: 0 files, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main 3039de93
- 20:11Z commit 85216107 [harness-factory] otto-advisor-yaml-cannot-take-another-wheel-clock-job: the hub's wheel clock moves to canon/otto.wheel-clock.yaml (MAX-134) -- lug otto-advisor-yaml-cannot-take-another-wheel-clock-job -- fixtures 117/1, 84/2, 67/0, 12/17 -- 3 file(s), area conformance -- source: harness-factory: git log main 85216107
- 20:05Z commit 2eb7e861 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main 2eb7e861
- 18:26Z commit 3930190d [harness-factory] position-map runs serial-first: it composes the map twice against the real wheel-hub and asserts the two agree; inside the gate pool another suite can write into the hub between the calls (NEW RED on two consecutive 260914 push gates, 36/36 alone) -- the gate-pool-serial-suites marker, not a retry -- fixtures 36/36 -- 1 file(s), area conformance -- source: harness-factory: git log main 3930190d
- 17:58Z commit 64ad1620 [harness-factory] fold 260914 (session rat): communication-inbox-delta's UserPromptSubmit binding and circle declaration applied on the canonical checkout (a hook binding cannot pass the custody gate from a worktree -- lug hook-event-circle-authored-on-a-dispatch-branch-cannot-pass-its-own-commit-gate; built by MAX-125); wheel-clock-catchup.md trimmed back under rule 11 after MAX-128's hook-mode section pushed it to 1020 tokens (main was BUILD REFUSED); circle-completeness-audit fixture asserts the four Conductor circles CLOSED and two fixtures name the lugs they already proved (generated-claude-md, fbl-065-followup-scope-guard-write-detection) so the done gate reads real evidence; generated docs regenerated for 90 circles and the ozi wheel clock -- lug hook-event-circle-authored-on-a-dispatch-branch-cannot-pass-its-own-commit-gate -- 9 file(s), area conformance -- source: harness-factory: git log main 64ad1620
- 05:18Z commit bd1dce11 [harness-factory] Session work: 0 files, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main bd1dce11
- 05:03Z commit a16283fd [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main a16283fd

#### circles

- 22:53Z circle secrets-template-migration added at 0d8a69ba -- source: harness-factory: git log --diff-filter=A 0d8a69ba -- reference/circles/secrets-template-migration.yaml
- 22:43Z circle worktree-registry added at 41896a70 -- source: harness-factory: git log --diff-filter=A 41896a70 -- reference/circles/worktree-registry.yaml
- 22:18Z circle farming added at c5c7f88a -- source: harness-factory: git log --diff-filter=A c5c7f88a -- reference/circles/farming.yaml
- 17:58Z circle communication-inbox-delta added at 64ad1620 -- source: harness-factory: git log --diff-filter=A 64ad1620 -- reference/circles/communication-inbox-delta.yaml
- 17:58Z hook UserPromptSubmit -> node src/hooks/communicationInboxDeltaHook.js (circle communication-inbox-delta) at 64ad1620 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 17:44Z circle communication-inbox added at f911fc58 -- source: harness-factory: git log --diff-filter=A f911fc58 -- reference/circles/communication-inbox.yaml
- 05:31Z circle lug-ownership-claims added at 5ebda53d -- source: harness-factory: git log --diff-filter=A 5ebda53d -- reference/circles/lug-ownership-claims.yaml

#### src/lugTracking

- 05:52Z commit c1769015 [harness-factory] max-persona-boundary-blocks-planning-from-max-outside-the-spoke: the ruling attribution in the comment and the circle outcome named the operator personally -- rule 13 (no-personal-leak) refused the push; "the operator" carries the same fact -- lug max-persona-boundary-blocks-planning-from-max-outside-the-spoke -- 2 file(s), area src/lugTracking -- source: harness-factory: git log main c1769015
- 05:39Z commit d55a2986 [harness-factory] lug-ownership-claims-and-divergence-review-across-live-sessions: liveness reads the hook runlog tail (a turn marker lands only at Stop, so a session 30 min into one turn read STALE live on the hub); generated docs regenerated for the 88th circle -- lug lug-ownership-claims-and-divergence-review-across-live-sessions -- 4 file(s), area src/lugTracking -- source: harness-factory: git log main d55a2986
- 05:14Z commit 85fa3221 [harness-factory] max-persona-boundary-blocks-planning-from-max-outside-the-spoke: allow and disclose Max's planning scaffold outside every repo; framework checkout warns by default -- lug max-persona-boundary-blocks-planning-from-max-outside-the-spoke -- 6 file(s), area src/lugTracking -- source: harness-factory: git log main 85fa3221
- 05:14Z commit 608a5046 [harness-factory] honestNullMarker: drop the operator's name from a code comment -- rule 13 (no-personal-leak) flagged the shipping artifact and refused every wheel-hub push through the cross-repo conformance check -- 1 file(s), area src/lugTracking -- source: harness-factory: git log main 608a5046
- 05:01Z commit 547e5270 [harness-factory] honest-null-turn-marker-with-recorded-cause-blocks-done-forever: operator ruling 2026-09-13 "2.a" (session 2776bea2) amending 260828-FBL-011 ruling 2 -- a tokens: null turn marker whose cause the Stop hook itself recorded (ldg-cost-unmeasured row naming the lug, within 5 s of the marker) counts as measured-zero for the done gate; cost.tokens stays the measured subtotal and cost.unmeasured_markers lists each such marker with its recorded cause; every other null marker is refused with the unchanged text; fixture reproduces the hub's real 2 ms marker/row pair and proves 10 FAIL on the unfixed gate -- lug honest-null-turn-marker-with-recorded-cause-blocks-done-forever -- 5 file(s), area src/lugTracking -- source: harness-factory: git log main 547e5270

#### src/compiler

- 21:00Z commit 48746ea7 [harness-factory] minder-v1-lug-migration-debt-blocks-cut-promotion: authored-path-retire -- a migrated lug whose authored fields name a v1 path moves whole (MAX-139) -- lug minder-v1-lug-migration-debt-blocks-cut-promotion -- fixtures 29/29 -- 3 file(s), area src/compiler -- source: harness-factory: git log main 48746ea7
- 20:46Z commit c0a5ba9e [harness-factory] minder-v1-lug-migration-debt-blocks-cut-promotion: duplicate-retire, v1_source sidecar with reconstruction proof, whole-retire (MAX-138) -- lug minder-v1-lug-migration-debt-blocks-cut-promotion -- fixtures 662/662, 26/26 -- 3 file(s), area src/compiler -- source: harness-factory: git log main c0a5ba9e
- 20:22Z commit 964bbf4e [harness-factory] minder-v1-lug-migration-debt-blocks-cut-promotion: v1-canon disposition tool -- the measured, mechanical half; judgement rows left to the operator -- lug minder-v1-lug-migration-debt-blocks-cut-promotion -- fixtures 17/17 -- 3 file(s), area src/compiler -- source: harness-factory: git log main 964bbf4e
- 20:03Z commit 1978fa7b [harness-factory] compile-ok-yaml-load-error-subtype-still-blocks-legacy-tree-cut-promotion: rule 00's yaml-load-error subtype is informational (blocking: false) for a file that fails to parse AND declares no top-level `kind:` -- the same key-presence test isNonCanonEntity() already applies (declaresKind, one exported helper; loadCanon reads it off the raw text via rawDeclaresKind and records `kind: null` on the synthetic _loadError entity), still blocking for a real canon file that declares kind:; isNonCanonEntity unchanged for rules 11/v1PathScan. Measured: basher today compiles BUILD OK 126 entities / 0 blocking / 38 informational (all non-canon-yaml; its 3 unparseable files were hand-fixed 2026-09-07 in c295bbe7); a disposable copy with those 3 pre-fix files restored compiles BUILD REFUSED (38 violations, the 3 yaml-load-error the only blocking ones) on the unfixed code and BUILD OK 0 blocking / 38 informational with the 3 findings visible after; the real cut path (applyCut, what launchSpoke --dry-run runs) rolls that copy back on exactly those 3 refuse-class violations before and lands (ok:true, canon/circles gains 4 files) after. Fixture compile-ok-yaml-load-error-legacy-informational 16/16, 6 FAIL on the unfixed code; loader-canon-skip-dirs' vacuous "malformed file is a real build failure" line (passed only because its stub circle fails schema) now asserts the informational contract. -- lug compile-ok-yaml-load-error-subtype-still-blocks-legacy-tree-cut-promotion -- fixtures 16/16 -- 4 file(s), area src/compiler -- source: harness-factory: git log main 1978fa7b

#### conductor-autonomous-loop

- 22:20Z commit dc0ee4f0 [harness-factory] planner-class-floors: operator confirmed the 0.5/0.2/0.15/0.15 blend (floors_basis operator_confirmed_260914) and directed shortfall: proportional_to_remaining_floors -- a class that runs out of rows waterfalls its capacity to the remaining classes in proportion to their floors; reader lands with lug planner-shortfall-waterfalls-proportionally -- lug planner-shortfall-waterfalls-proportionally -- fixtures 5/0, 2/0, 15/0 -- 1 file(s), area canon -- source: harness-factory: git log main dc0ee4f0
- 20:38Z commit d1772266 [harness-factory] planner-balances-build-maintain-health-with-declared-floors: one interleaved AP queue over initiative_build / build / maintain / health by deficit against floors declared in canon (MAX-137) -- lug planner-balances-build-maintain-health-with-declared-floors -- 13 file(s), area src/planner -- source: harness-factory: git log main d1772266
- 19:48Z commit c3b01a62 [harness-factory] planner-builds-the-operator-queue-of-blocked-work: buildPlannerCycle emits operator_queue beside the AP queue -- one row per lug no autopilot run can advance, six classes each read from its own real source (open_questions; readiness-sweep.jsonl last row FABRICATED/FAILED; guard-refused cleanup ledger rows; spoke .cut-status.json ok:false; captured + initiative sequence rank; canon pointer at rule 11's cap measured by measureCanonContent), weight from lugEdges.js descendants + dependency edges, ties by priority; runtime/planner-cycle.json carries it, goalsReview prints top 5 (+N more, 329 tokens on the hub) under the AP queue, scripts/planner-cycle.js --operator-queue prints all; a class with no source stream is not emitted and operator_queue_rule says so; real hub run: 95 rows, 18 FABRICATED + 15 FAILED gates, canon/otto.advisor.yaml 997/1000, minder cut ok:false 1216 violations, both 2026-09-14 ruled lugs absent, stale worktrees NOT named (the classifier writes no ledger row -- stated in the rule) -- lug planner-builds-the-operator-queue-of-blocked-work -- fixtures 997/1000 -- 5 file(s), area src/planner -- source: harness-factory: git log main c3b01a62

#### src/factory

- 22:43Z commit 41896a70 [harness-factory] every-harness-worktree-carries-its-session-purpose-and-expiry: one registrar for every harness worktree (runtime/worktrees.jsonl), patch-id-gated removal, health signal + handoff read it -- lug every-harness-worktree-carries-its-session-purpose-and-expiry -- 9 file(s), area src/factory -- source: harness-factory: git log main 41896a70
- 19:49Z commit 96df6d22 [harness-factory] no-operator-verb-applies-a-pending-cut-outside-the-launch-path: a pending cut is equality against the recorded cut, and hf apply-cut reaches applyCut outside the launch path (MAX-129) -- lug no-operator-verb-applies-a-pending-cut-outside-the-launch-path -- fixtures 0/0, 4/5, 47/47, 58/58, 23/23, 20/20, 7/7, 11/11, 48/48, 27/27, 0/1 -- 13 file(s), area src/factory -- source: harness-factory: git log main 96df6d22
- 17:49Z commit 06bdf9c4 [harness-factory] scaffolded-spoke-ships-schedule-circles-with-no-wheel-clock: an instance's wheel clock is its own canon file (kind: wheel_clock), a fresh scaffold is born with the canon default clock, and a schedule circle declares the job it runs as -- excluded from any cut whose target clock does not declare it, audited EXCLUDED there, never PHANTOM -- lug scaffolded-spoke-ships-schedule-circles-with-no-wheel-clock -- fixtures 33/33 -- 33 file(s), area src/factory -- source: harness-factory: git log main 06bdf9c4

#### wheel-agents-talk-up-down-and-across

- 17:44Z commit f911fc58 [harness-factory] communication-inbox-circle-and-fair-ranking: the inbox circle and the one ranking -- rankCommunicationInbox (priority, escalation as one non-compounding bump, requester seniority, ask) exported from readyWork.js and called by buildReadyWorkQueue, the senior inbox and the Max second-opinion inbox; readCommunicationInbox walks sibling spokes' lugs/ read-only for open requests addressed to this spoke; ONE digest line through the goals review composer; a schedule circle: every SessionStart prints the line through the goals review composer and wheel_clock job communication_inbox (declared on ozi's clock, cadence 1; otto.advisor.yaml has no rule-11 headroom, so the hub audits PHANTOM until its clock moves -- disclosed in the circle .md); no hook binding, so the branch passes its own gate; fixture 46/46, planted unfixed comparator 44/46 -- lug communication-inbox-circle-and-fair-ranking -- fixtures 46/46, 44/46 -- 9 file(s), area src/conductor -- source: harness-factory: git log main f911fc58
- 17:30Z commit 098115c1 [harness-factory] communication-inbox-delta-injected-at-each-prompt: a UserPromptSubmit hook injects the delta of hub messages and communication lugs addressed to this spoke since the session's cursor -- one block under 600 chars or nothing, cursor in the spoke's runtime/ the only write, by-name rows and lugs the cap hid carry to the next prompt (measured on the real hub: 32 open communication lugs already target harness-factory), the 260914 direction row delivered to session 4f1a0301 by hand-run and ledgered as such (fixture 46/46; planted failure without the hook: exit 1; hub BUILD OK from the worktree) -- lug communication-inbox-delta-injected-at-each-prompt -- fixtures 46/46 -- 3 file(s), area src/hooks -- source: harness-factory: git log main 098115c1
- 07:24Z commit 5b6b48e2 [harness-factory] communication-lug-type-and-schema: the fifth lug type -- communication -- with its six statuses as a sibling of state, the schema block, the status arm of the kernel verb, and the migration of the hub's 31 intended_type stand-ins -- lug communication-lug-type-and-schema -- fixtures 36/86 -- 9 file(s), area src/lugTracking -- source: harness-factory: git log main 5b6b48e2

#### advisor-pattern-hub-managed-spoke-leveraged

- 19:46Z commit 6b6bde9a [harness-factory] max-plans-planner-schedules-ozi-dispatches-and-reports-validated: the policy's mechanics on every spoke -- canon/ozi.md gains "How Ozi manages work" (855 -> 995 of rule 11's 1000, clock disclosure condensed not dropped); the wakeup injection carries a 297-char CANON role-split block compiled from the policy entity (69 tokens by rule 12's own measure, resolved through the registry so a spoke never carries a copy); footer-audit at Stop records one existing-shape decision row (attribution max-plans-planner-schedules) when a top-level session's turn edited src/, conformance/ or scripts/ in a canonical checkout with no dispatch row that turn, a dispatched session exempt by WCL_DISPATCH_ID, a child_session_id registry row or a live dispatch-children pid; the session-end handoff lists every defined lug the Planner's last cycle did not queue with readyWork's own reason (180 on the hub today); fixture 62/62 on a scratch instance plus a real run, 15 FAIL on the unfixed code -- lug max-plans-planner-schedules-ozi-dispatches-and-reports-validated -- fixtures 62/62 -- 9 file(s), area src/lugTracking -- source: harness-factory: git log main 6b6bde9a
- 19:25Z commit 822deb2f [harness-factory] max-plans-planner-schedules: policy from the 2026-09-14 operator direction -- a spoke's Max plans and records lugs, the Planner places them and awaits budget, in-session work goes to a worktree-isolated sub-agent and is reported only once validated, Ozi owns the split on every spoke; enforcement mechanics in lug max-plans-planner-schedules-ozi-dispatches-and-reports-validated; generated docs regenerated (12 policies) -- lug max-plans-planner-schedules-ozi-dispatches-and-reports-validated -- 3 file(s), area repo root -- source: harness-factory: git log main 822deb2f

#### basher-secrets-remediation

- 22:58Z commit 7992c253 [harness-factory] secrets-manifest-migrates-from-env-template-and-spreads-by-cut: compact manifest render -- minder's real manifest measured 1132 tokens against rule 11's 1000 cap; nulls/empties omitted, 2-line header, banner head as vendor; now 806 (886 with retirement fields), fixture asserts the cap on both real templates -- lug secrets-manifest-migrates-from-env-template-and-spreads-by-cut -- 2 file(s), area src/basher -- source: harness-factory: git log main 7992c253
- 22:53Z commit 0d8a69ba [harness-factory] secrets-manifest-migrates-from-env-template-and-spreads-by-cut: .env.template -> secrets manifest migration path (design section 8) -- lug secrets-manifest-migrates-from-env-template-and-spreads-by-cut -- fixtures 75/75 -- 10 file(s), area src/basher -- source: harness-factory: git log main 0d8a69ba

#### repo root

- 23:06Z commit b8bcd9e9 [harness-factory] planner-class-balance fixture asserts the floors_basis the canon file declares (it pinned "unmeasured_default" and went red the moment the operator confirmed the floors); generated docs regenerated for the policy edit -- the causes of the refused floors pushes; generated docs regenerated for the secrets-template-migration and worktree-registry circles (146 entities) -- 3 file(s), area repo root -- source: harness-factory: git log main b8bcd9e9
- 21:02Z commit 8eb63ac5 [harness-factory] generated docs regenerated after the wave-2 folds (planner-class-floors policy, 12 policies) -- run-spoke-drift and the two self-hosting doc fixtures refused the push on the stale CLAUDE.md/AMBASSADOR_BRIEF.md; the four hub lugs that carried an explicit default `type: work` are corrected on the hub side (lug-type-conditional-requirements proves the corpus carries the default, not a migration) -- 2 file(s), area repo root -- source: harness-factory: git log main 8eb63ac5

#### src/conductor

- 22:18Z commit c5c7f88a [harness-factory] farming: detect independent recurrence across spokes, abstract preserving what differed, promote/demote through the cut with third-party certification -- fixtures 759/620 -- 6 file(s), area src/conductor -- source: harness-factory: git log main c5c7f88a
- 04:10Z commit e65fbf67 [harness-factory] readiness-sweep-cannot-see-a-lug-the-proofer-already-passed: three sweep-side false readings found on the 2026-09-13 review-pile sweep -- a nested `node --test` inherited NODE_TEST_CONTEXT and reported a red fixture GREEN; both marker walkers descended .claude/worktrees and resolved a stale worktree copy first (261 copies vs 63 real in wheel-hub); the verb wrote traceability_evidence.repo: null on an instance-repo commit and the whole hub corpus failed rule 00 -- the verb now validates the file it is about to write against the lug schema and refuses instead -- lug readiness-sweep-cannot-see-a-lug-the-proofer-already-passed -- 6 file(s), area src/conductor -- source: harness-factory: git log main e65fbf67

#### commits

- 23:03Z commit 8e4f1ff4 [harness-factory] lug wcl-cold-start-store-is-a-condition-not-a-lockout: defined -> ready(stubbed) -> review; cross-provider certification launched -- lug wcl-cold-start-store-is-a-condition-not-a-lockout -- 1 file(s), area lugs -- source: harness-factory: git log main 8e4f1ff4

#### docs

- 04:51Z commit 5ddbe412 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area docs -- source: harness-factory: git log main 5ddbe412

#### low-trust-multi-provider-verification

- 19:58Z commit b855319b [harness-factory] fabrication-binder-quote-truncation-and-unpinned-false-positives: the binder gains tiers quote_normalised (` ' " deleted on both sides of the structural form) and unpinned (reason beyond_bundle: past a truncated pointer's byte boundary the bundle builder now hands the certifier with a lazy reader to the full text; reason unpinned_file: a registered-repo file no pointer or lug-naming commit pinned, found by src/advisor/unpinnedSearch.js -- git-grep shortlist then the real tiers, runtime/ and the bundle's own files never searched); the literal \n marker is read as the newline it denotes BEFORE the comment-decoration strip and a citation that opens as a comment gets its reflowed `//`/`*`/`#` line leads back (citation side only) -- 9+5 real rejections on the 2026-09-14 records were exactly those two shapes; certification-replay runs the binder first with the boundaries and the search, and tolerates the 1-based attempt_index three gemini records carry; tier_counts, reason_counts, truncation_boundaries and fabricated_detail carry it all onto the record; chain-disposition's binding ladder ranks the two new tiers weakest. Replayed over the 20 FABRICATED records: 8 bind now (communication-lug-type-and-schema quote_normalised; three-suites-flake... beyond_bundle; generated-docs... comment reflow; tastegraph... and done-gate-process-checks... the \n fold; conductor-two-cron... unpinned_file in AMBASSADOR_BRIEF.md; headless-launchspoke... and ledger-conversation... quote_normalised), 12 stay FABRICATED -- stale-instance-check... is a paraphrase ("same name", "exactly as today") found in no file at any commit of either repo, not the unpinned case the ledger row called it. Fixture conformance/fixtures/fabrication-binder (43 checks: one planted citation per class, the real 2026-08-28 fabrication, the two layout shapes, end to end through runProofer with the record's ledger row); the quote case is ok:false on the unfixed matcher (stash, run, pop). Readiness sweep over the 6 with --certify=none: 0 moved -- the gate reads the RECORDED verdict, 5 held by it and 1 by the cost gate; re-binding a record in place is the named follow-up, not done here. -- lug fabrication-binder-quote-truncation-and-unpinned-false-positives -- 9 file(s), area src/advisor -- source: harness-factory: git log main b855319b

#### reference

- 18:10Z commit 78dcd580 [harness-factory] communication-inbox meets the declared wheel-clock join (MAX-126 x MAX-127 seam): the circle declares requires_wheel_clock_job: communicationInbox, the canon default spoke clock schedules communication_inbox so every scaffolded spoke gains an inbox (the lug's own intent), and the fixture reads this instance's clock through resolveWheelClock instead of a hardcoded advisor file -- the three suites the push gate refused (communication-inbox 46/46, scaffolded-spoke-wheel-clock 33/33, run-reference-circles 90/90) -- fixtures 46/46, 33/33, 90/90 -- 3 file(s), area reference -- source: harness-factory: git log main 78dcd580

#### roi-steered-waves

- 07:49Z commit f2e00eb1 [harness-factory] orphaned-dispatch-rows-are-never-reconciled-against-disk-evidence: the reconciler now resolves the repo-qualified `<repo>:<path>` tests form the verb writes at done -- the worked COMPLETED example (implement-lug-lineage) read PARTIAL after its own done rewrote external:harness-factory/... to harness-factory:..., and the fixture's real-data case is the regression proof -- lug orphaned-dispatch-rows-are-never-reconciled-against-disk-evidence -- 1 file(s), area src/lugTracking -- source: harness-factory: git log main f2e00eb1

#### src/advisor

- 20:13Z commit b92fe9e5 [harness-factory] fallback-chain-reaches-advisory-only-gemini-without-an-explicit-flag: the implicit chain skips an advisory-only provider unless --provider names it (MAX-136) -- lug fallback-chain-reaches-advisory-only-gemini-without-an-explicit-flag -- 6 file(s), area src/advisor -- source: harness-factory: git log main b92fe9e5

#### src/basher

- 23:00Z commit d753a67d [harness-factory] wcl: an unauthenticated isolated store is a cold-start condition, not a lockout -- fixtures 39/39, 152/152, 49/49 -- 5 file(s), area src/basher -- source: harness-factory: git log main d753a67d

#### src/hooks

- 05:31Z commit 5ebda53d [harness-factory] lug-ownership-claims-and-divergence-review-across-live-sessions: a claim table (runtime/lug-claims.jsonl) records who had a lug first; the verb claims at in_progress, releases at review/done, refuses another live session's claim unless --drive/--collaborate; four guards quote contend; divergences are records resolved through the verb -- lug lug-ownership-claims-and-divergence-review-across-live-sessions -- 18 file(s), area src/hooks -- source: harness-factory: git log main 5ebda53d

#### src/otto

- 17:40Z commit 15715745 [harness-factory] wheel-clock-tick-exceeds-sessionstart-hook-timeout-and-replays: the SessionStart hook runs the catch-up in hook mode -- state before work, the jobs a hook cannot afford deferred to the cron driver with a ledger row each, and the lease reclaimed on the next start instead of stranded for the push gate -- lug wheel-clock-tick-exceeds-sessionstart-hook-timeout-and-replays -- 8 file(s), area src/otto -- source: harness-factory: git log main 15715745

#### unaffiliated lugs

- 23:03Z lug at review wcl-cold-start-store-is-a-condition-not-a-lockout [harness-factory] priority critical -- no certification receipt -- date from runtime/event-log.jsonl review transition -- readiness stubbed -- source: harness-factory: lugs/wcl-cold-start-store-is-a-condition-not-a-lockout.yaml (runtime/event-log.jsonl review transition)

### 2026-09-13

#### circles

- 08:13Z circle gate-pool-serial-suites added at b7ac2036 -- source: harness-factory: git log --diff-filter=A b7ac2036 -- reference/circles/gate-pool-serial-suites.yaml
- 06:27Z circle tastegraph-injection added at 01df7bc9 -- source: harness-factory: git log --diff-filter=A 01df7bc9 -- reference/circles/tastegraph-injection.yaml
- 06:27Z hook UserPromptSubmit -> node src/hooks/tasteUpdateInjectionHook.js (circle tastegraph-injection) at 01df7bc9 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 05:09Z hook SessionStart -> node src/hooks/updateDiscoveryHook.js (circle update-discovery) at f90dd791 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 04:47Z circle rule-12-live-state-report added at ac436238 -- source: harness-factory: git log --diff-filter=A ac436238 -- reference/circles/rule-12-live-state-report.yaml

#### low-trust-multi-provider-verification

- 22:38Z commit 6109154d [harness-factory] fabrication-check-still-rejects-most-verdicts-and-the-record-cannot-replay-why: re-certification of the 13 affected lugs (CONFIRMED 4, PLAUSIBLE 3, FAILED 1, FABRICATED 5) in the build record; the escape fold collapses a doubled backslash and a citation prefixed with a bundle FILE it really carries is judged on its remainder -- both from the first post-fix rejections, each with a fixture case; quote-style swaps stay rejected -- lug fabrication-check-still-rejects-most-verdicts-and-the-record-cannot-replay-why -- fixtures 3/3 -- 4 file(s), area src/advisor -- source: harness-factory: git log main 6109154d
- 22:12Z commit 63568466 [harness-factory] fabrication-check-still-rejects-most-verdicts-and-the-record-cannot-replay-why: certification-replay rebuilds the pinned bundle and names one cause per rejected citation; the 2026-09-13 table (16 records, 110 rejections: 15 escaped, 13 ellipsis, 5 other, 1 past the cut, 22 real, 54 excerpt-only); matcher folds escapes on both sides, strips the prompt's own list marker and paired emphasis, and adds a named ellipsis tier -- substitutions and inventions stay rejected -- lug fabrication-check-still-rejects-most-verdicts-and-the-record-cannot-replay-why -- fixtures 34/34 -- 6 file(s), area src/advisor -- source: harness-factory: git log main 63568466
- 21:29Z commit ec539699 [harness-factory] fabrication-check-still-rejects-most-verdicts-and-the-record-cannot-replay-why: every attempt keeps its own citations, citation_binding, evidence_pins and truncated_pointers -- the last attempt of an exhausted chain was recoverable only as a 300-char reason excerpt -- lug fabrication-check-still-rejects-most-verdicts-and-the-record-cannot-replay-why -- 3 file(s), area src/advisor -- source: harness-factory: git log main ec539699
- 20:50Z commit 27dc43aa [harness-factory] certification-chain-spends-two-thirds-of-its-time-on-providers-that-never-answer: wave circuit breaker -- per-candidate timeouts and a consecutive-unanswered threshold from canon, one runtime wave file shared by every lane, skips disclosed with the count -- lug certification-chain-spends-two-thirds-of-its-time-on-providers-that-never-answer -- 7 file(s), area src/advisor -- source: harness-factory: git log main 27dc43aa

#### land-to-done

- 19:43Z commit df7c31fa [harness-factory] declared-pointer-to-a-multi-megabyte-runtime-file-blocks-certification-forever: build record -- both re-certifications reached real verdicts (FAILED, PLAUSIBLE), truncation lines quoted -- lug declared-pointer-to-a-multi-megabyte-runtime-file-blocks-certification-forever -- 1 file(s), area docs -- source: harness-factory: git log main df7c31fa
- 19:36Z commit 096880ce [harness-factory] declared-pointer-to-a-multi-megabyte-runtime-file-blocks-certification-forever: both declared-pointer read paths honour the canon byte cap, head shown verbatim, whole file hashed, every truncation disclosed -- lug declared-pointer-to-a-multi-megabyte-runtime-file-blocks-certification-forever -- fixtures 60/60 -- 3 file(s), area src/advisor -- source: harness-factory: git log main 096880ce

#### repo root

- 08:24Z commit 9b3ac235 [harness-factory] regenerate-docs after the gate-pool fold -- 2 file(s), area repo root -- source: harness-factory: git log main 9b3ac235
- 05:09Z commit f90dd791 [harness-factory] compile-self --standing after the fold: update-discovery SessionStart binding, regenerated docs -- 3 file(s), area repo root -- source: harness-factory: git log main f90dd791

#### conformance

- 08:13Z commit b7ac2036 [harness-factory] gate-pool-serial-suites (2/2): the fixture, its twenty-run full-pool record, and the circle declaration -- fixtures 2/2, 20/20, 13/13, 19/20, 1/2 -- 7 file(s), area conformance -- source: harness-factory: git log main b7ac2036

#### conformance-suite-runs-218-suites-serially-22-minutes-on-every-push

- 20:37Z commit e8ad374c [harness-factory] push-gate-runs-87-circle-fixtures-twice-reference-circles-is-the-critical-path: every circle fixture runs once per gate -- run-reference-circles consumes the pool's own per-suite record as a pool child -- lug push-gate-runs-87-circle-fixtures-twice-reference-circles-is-the-critical-path -- 6 file(s), area src/factory -- source: harness-factory: git log main e8ad374c

#### docs

- 19:26Z commit 93c450dd [harness-factory] done-transition-appends-push-near-cap-lugs-over-rule-11: acceptance 4 evidence -- near-cap review lugs re-measured on the authored contract (0 over the cap on disk; 11 refused only by the done-time author/tests appends, named) -- lug done-transition-appends-push-near-cap-lugs-over-rule-11 -- 1 file(s), area docs -- source: harness-factory: git log main 93c450dd

#### done-transition-appends-push-near-cap-lugs-over-rule-11

- 22:05Z commit 7486c88c [harness-factory] author-record-is-verb-owned-and-counts-against-no-lugs-authored-contract: author joins VERB_OWNED_LUG_FIELDS -- the verb's attribution record no longer counts against the authored contract -- lug author-record-is-verb-owned-and-counts-against-no-lugs-authored-contract -- fixtures 41/0, 105/0 -- 3 file(s), area src/compiler -- source: harness-factory: git log main 7486c88c

#### roi-steered-waves

- 01:32Z commit a1ca15c9 [harness-factory] autopilot-run-ends-with-an-roi-extractor-that-steers-the-next-wave: the open-wave sweep is a wheel-clock job and the wave-never-closed rule reads its whole-stream count; a reconciled close attributes no provider calls -- lug autopilot-run-ends-with-an-roi-extractor-that-steers-the-next-wave -- 6 file(s), area src/conductor -- source: harness-factory: git log main a1ca15c9

#### src/advisor

- 04:50Z commit 1ebdef98 [harness-factory] fabricationCheck: literal \n/\r/\t markers inside a backtick citation fold to whitespace in normalizeForMatch (recovered from index blob ded1306 -- staged in the main checkout by a finished session at 19:41, lost to a cherry-pick --abort, restored verbatim; cross-provider-verification 92/92) -- fixtures 92/92 -- 1 file(s), area src/advisor -- source: harness-factory: git log main 1ebdef98

#### src/compiler

- 04:47Z commit ac436238 [harness-factory] rule-12-measures-live-runtime-state-so-the-hub-compile-verdict-flips-hourly: rule 12 refuses only on the canon-derived injection; the live part is a warning with the number; live sections carry count caps and an acknowledge path (fixture 64/64; staged by dispatch 47840625 whose run was cut by wallclock after the machine slept, committed by the orchestrator after re-running its fixture; gate run at WHEEL_SUITE_WORKERS=2 because the liveness-lease timing checks fail under the full pool's load, not because of this change) -- lug rule-12-measures-live-runtime-state-so-the-hub-compile-verdict-flips-hourly -- fixtures 64/64 -- 306 file(s), area src/compiler -- source: harness-factory: git log main ac436238

#### src/factory

- 07:39Z commit e3b4ce57 [harness-factory] gate-pool-serial-suites (1/2): the three suites that flaked only in the pool run serial-first with measured reasons; timing windows derived from the box; a lease that ran out at the budget's end defers to the wall-clock arm -- fixtures 1/2, 57/57, 34/34, 94/94, 43/43, 14/15, 19/20, 2/2 -- 8 file(s), area src/factory -- source: harness-factory: git log main e3b4ce57

#### src/hooks

- 06:27Z commit 01df7bc9 [harness-factory] tastegraph-is-merged-at-wakeup-and-injected-into-no-session: merged tastes reach every session at wakeup, refresh mid-session, footer audit measures communication tastes -- rebased onto the rule-12 fold (taste-injection 36/36, rule-12 64/64, hub BUILD OK; built by dispatch 73e6d000, rebased by dispatch f53463c3, applied to main by the orchestrator because the new hook binds to the canonical checkout and cannot pass the custody gate from a worktree -- the fold-gate lug; gate at WHEEL_SUITE_WORKERS=2) -- lug tastegraph-is-merged-at-wakeup-and-injected-into-no-session -- fixtures 36/36, 64/64 -- 19 file(s), area src/hooks -- source: harness-factory: git log main 01df7bc9

### 2026-09-12

#### src/lugTracking

- 08:15Z commit add6c753 [harness-factory] done-gate-registry-span-cost-and-rerun-of-53-refused-rows: a completed dispatch row's observed span is a measured wall clock where no journal exists -- lug done-gate-registry-span-cost-and-rerun-of-53-refused-rows -- 5 file(s), area src/lugTracking -- source: harness-factory: git log main add6c753
- 05:11Z commit 5ed3f66b [harness-factory] long-running-work-declares-a-liveness-lease-instead-of-a-flat-silence-kill: a live lease on the lug lets silence pass; a hung one is killed with the step named -- lug long-running-work-declares-a-liveness-lease-instead-of-a-flat-silence-kill -- fixtures 57/0, 58/0 -- 17 file(s), area src/lugTracking -- source: harness-factory: git log main 5ed3f66b
- 03:06Z commit 69adebeb [harness-factory] done-gate-process-checks-hold-38-verified-lugs: the done gate reads dispatch and commit evidence it already had -- lug done-gate-process-checks-hold-38-verified-lugs -- 10 file(s), area src/lugTracking -- source: harness-factory: git log main 69adebeb
- 01:01Z commit b53d52bb [harness-factory] lug-integrity-checksum tells a state forgery from a content edit: baseline records lifecycle fields; content edits adopted, state/readiness forgeries still healed; one-shot state-vs-evidence reconciliation -- 10 file(s), area src/lugTracking -- source: harness-factory: git log main b53d52bb
- 00:46Z commit ca618d9b [harness-factory] Kernel verb measures its own write against rule 11's cap; pickup_reverification block compacted to <120 tokens -- 5 file(s), area src/lugTracking -- source: harness-factory: git log main ca618d9b
- 00:30Z commit 8f475e52 [harness-factory] statusline-resolve-focus-has-no-v2-source: track.json carries a per-turn turn_focus the statusline can read -- lug statusline-resolve-focus-has-no-v2-source -- 2 file(s), area src/lugTracking -- source: harness-factory: git log main 8f475e52
- 00:20Z commit c73763d8 [harness-factory] lug-lifecycle-tracker-blind-to-cross-repo-proof: done gate scans the repos a lug's external: pointers name -- lug lug-lifecycle-tracker-blind-to-cross-repo-proof -- fixtures 42/42 -- 4 file(s), area src/lugTracking -- source: harness-factory: git log main c73763d8

#### circles

- 09:11Z circle update-discovery added at 46fe1cd1 -- source: harness-factory: git log --diff-filter=A 46fe1cd1 -- reference/circles/update-discovery.yaml
- 08:03Z circle hf-deploy added at a44db163 -- source: harness-factory: git log --diff-filter=A a44db163 -- reference/circles/hf-deploy.yaml
- 05:11Z circle liveness-lease added at 5ed3f66b -- source: harness-factory: git log --diff-filter=A 5ed3f66b -- reference/circles/liveness-lease.yaml
- 02:52Z circle cross-provider-certification-history added at 0498d24d -- source: harness-factory: git log --diff-filter=A 0498d24d -- reference/circles/cross-provider-certification-history.yaml
- 00:37Z circle readiness-certification-sweep added at 827542c8 -- source: harness-factory: git log --diff-filter=A 827542c8 -- reference/circles/readiness-certification-sweep.yaml
- 00:10Z circle done-gate-two-store-certification added at fa696cd0 -- source: harness-factory: git log --diff-filter=A fa696cd0 -- reference/circles/done-gate-two-store-certification.yaml

#### conformance

- 00:49Z commit ec05df32 [harness-factory] definition-complete-gate and ready-gate-stub fixtures run their hooks against a per-run scratch root; tracked lug-checksums.json reduced to the real seed -- 4 file(s), area conformance -- source: harness-factory: git log main ec05df32
- 00:13Z commit 84550905 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main 84550905

#### docs

- 09:12Z commit cb7175ef [harness-factory] update-discovery: build record -- commits as landed, the fold-order hazard, the measured wall-clock step on this box -- 1 file(s), area docs -- source: harness-factory: git log main cb7175ef
- 08:12Z commit a3f3b42f [harness-factory] hf-deploy: build record (docs/hf-deploy.md) -- measurements, the hub canon declaration and its ordering hazard, verification, what is left open -- 1 file(s), area docs -- source: harness-factory: git log main a3f3b42f

#### reference

- 09:11Z commit 46fe1cd1 [harness-factory] update-discovery: the circle declaration and its fixture -- 3 file(s), area reference -- source: harness-factory: git log main 46fe1cd1
- 00:54Z commit 103534f8 [harness-factory] pickup-time-reverification circle doc: the lug block is compact; fixture is 81 checks -- 1 file(s), area reference -- source: harness-factory: git log main 103534f8

#### src/advisor

- 02:52Z commit 0498d24d [harness-factory] Session work: 10 files, no lug transitions recorded -- 10 file(s), area src/advisor -- source: harness-factory: git log main 0498d24d
- 00:10Z commit fa696cd0 [harness-factory] Done gate reads both certification stores; a Proofer PASS is sufficient when the external chain produced nothing usable -- fixtures 65/65 -- 13 file(s), area src/advisor -- source: harness-factory: git log main fa696cd0

#### src/conductor

- 03:49Z commit 1b31755e [harness-factory] readiness-sweep-cannot-see-a-lug-the-proofer-already-passed: sweep enumerates ready+passed; one promote path shared with the drive -- lug readiness-sweep-cannot-see-a-lug-the-proofer-already-passed -- 8 file(s), area src/conductor -- source: harness-factory: git log main 1b31755e
- 00:37Z commit 827542c8 [harness-factory] readiness-certification-sweep: the review-backlog sweep as a real mechanism (module, CLI, on_demand circle, 29-check fixture naming its lug) -- 5 file(s), area src/conductor -- source: harness-factory: git log main 827542c8

#### src/factory

- 02:29Z commit 89ceb779 [harness-factory] conformance-suite-runs-218-suites-serially-22-minutes-on-every-push: pool refinements from the parallel run; arrivalAudit window compares whole milliseconds -- lug conformance-suite-runs-218-suites-serially-22-minutes-on-every-push -- fixtures 43/0 -- 5 file(s), area src/factory -- source: harness-factory: git log main 89ceb779
- 01:26Z commit 297fb7be [harness-factory] conformance-suite-runs-218-suites-serially-22-minutes-on-every-push: run suites on one worker pool for npm test and both gates -- lug conformance-suite-runs-218-suites-serially-22-minutes-on-every-push -- 7 file(s), area src/factory -- source: harness-factory: git log main 297fb7be

#### src/otto

- 01:20Z commit dc008d97 [harness-factory] harness-factory-ozi-has-no-live-wheel-clock-cadence: ozi declares a real wheel_clock; scheduler runs it; autopilot halts honestly when no advisor declares a clock -- lug harness-factory-ozi-has-no-live-wheel-clock-cadence -- fixtures 56/0 -- 5 file(s), area src/otto -- source: harness-factory: git log main dc008d97
- 00:27Z commit 5edae357 [harness-factory] wheel-clock-catchup-only-advanced-on-sessionstart: record every job's real wall-clock; no second cron entry -- lug wheel-clock-catchup-only-advanced-on-sessionstart -- 4 file(s), area src/otto -- source: harness-factory: git log main 5edae357

#### wheel-feedback-loop

- 09:07Z commit 636f9060 [harness-factory] spokes-discover-and-pull-the-current-cut-natively-instead-of-max-pushing-it: the cut is published by hf deploy's cut stage and discovered by every spoke natively; Otto names the laggards -- lug spokes-discover-and-pull-the-current-cut-natively-instead-of-max-pushing-it -- 12 file(s), area src/factory -- source: harness-factory: git log main 636f9060
- 08:03Z commit a44db163 [harness-factory] max-deploys-updates-through-its-fleet-fold-push-cut-relaunch-as-one-verb: hf deploy -- fold, push, cut, relaunch, clean as one recorded, resumable verb -- lug max-deploys-updates-through-its-fleet-fold-push-cut-relaunch-as-one-verb -- 8 file(s), area src -- source: harness-factory: git log main a44db163

#### conductor-autonomous-loop

- 12:12Z commit 544fdf89 [harness-factory] advisor-autopilot-loses-all-work-when-the-budget-backstop-fires: the kept-row count reads the real ledger stamp and credits only the run's own rows -- lug advisor-autopilot-loses-all-work-when-the-budget-backstop-fires -- fixtures 59/9, 68/0 -- 3 file(s), area src/lugTracking -- source: harness-factory: git log main 544fdf89

#### repo root

- 07:11Z commit 8b8a7b49 [harness-factory] regenerate-docs: CLAUDE.md and AMBASSADOR_BRIEF.md follow the liveness-lease cut -- 2 file(s), area repo root -- source: harness-factory: git log main 8b8a7b49

#### src/basher

- 08:17Z commit 1606f325 [harness-factory] cut-promotion-rolls-back-on-hygiene-rules-the-launcher-already-classifies-as-report: applyCut classifies the scratch and real recompile's violations through canon's launch classes -- report-class (11, 12) lets the cut land with every violation named in .cut-status.json and the cut message, a lug owed; refuse-class (00, 13, 15, 18, 19, 20) still rolls back -- lug cut-promotion-rolls-back-on-hygiene-rules-the-launcher-already-classifies-as-report -- 3 file(s), area src/basher -- source: harness-factory: git log main 1606f325

#### src/cartographer

- 03:27Z commit 8c721a45 [harness-factory] six-fixtures-assume-the-canonical-checkout-path-and-fail-in-every-git-worktree: the suite is green from a linked git worktree -- lug six-fixtures-assume-the-canonical-checkout-path-and-fail-in-every-git-worktree -- 10 file(s), area src/cartographer -- source: harness-factory: git log main 8c721a45

#### src/compiler

- 04:30Z commit d4c8439f [harness-factory] done-transition-appends-push-near-cap-lugs-over-rule-11: rule 11 measures the authored contract, not the verb's bookkeeping -- lug done-transition-appends-push-near-cap-lugs-over-rule-11 -- fixtures 43/43 -- 8 file(s), area src/compiler -- source: harness-factory: git log main d4c8439f

#### src/hooks

- 00:31Z commit 43815c10 [harness-factory] statusline-resolve-focus-has-no-v2-source: wire turn_focus into writeOrUpdateTrack, the Stop hook, and the track schema -- lug statusline-resolve-focus-has-no-v2-source -- 3 file(s), area src/hooks -- source: harness-factory: git log main 43815c10

### 2026-09-11

#### conformance

- 20:55Z commit 0403a74e [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main 0403a74e
- 20:52Z commit d750ebc7 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main d750ebc7
- 19:02Z commit 52570914 [harness-factory] track-rotation fixture: traceability marker for harness-factory-aggregator-red-since-260909-blocks-every-push (cause 6) -- 2 file(s), area conformance -- source: harness-factory: git log main 52570914
- 17:17Z commit e766c875 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main e766c875
- 15:56Z commit 5052533d [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main 5052533d
- 15:53Z commit d0d83751 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main d0d83751
- 10:56Z commit 745a5270 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main 745a5270
- 10:53Z commit 13970139 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main 13970139
- 09:49Z commit a3d78af0 [harness-factory] wcl fixtures: init-cli usage check from a non-spoke cwd; hygiene fixture follows wcl's reworded step labels -- 2 file(s), area conformance -- source: harness-factory: git log main a3d78af0
- 09:44Z commit b8343cbe [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main b8343cbe
- 09:43Z commit 817074b9 [harness-factory] wcl-global-settings-cli: assert the usage string from a non-spoke cwd (wcl now infers the spoke from a spoke-root cwd and would launch) -- fixtures 6604 passed -- 1 file(s), area conformance -- source: harness-factory: git log main 817074b9
- 09:41Z commit ea09ad79 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main ea09ad79
- 09:23Z commit 53c0e544 [harness-factory] rule-12 broken fixture: grow the injection by initiative COUNT, not one verbose lug -- fixtures 260910/260911 -- 51 file(s), area conformance -- source: harness-factory: git log main 53c0e544
- 09:16Z commit eb88d839 [harness-factory] Finish the aggregator dispatch's last increment: hosted_by:instance circles delegated in run-reference-circles; notify fixture clears inherited launch-mode env; lug-edges adoption measured not pinned; exit hook timeout 480s from a two-repo measurement -- 6 file(s), area conformance -- source: harness-factory: git log main eb88d839
- 09:15Z commit 875dacd4 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main 875dacd4
- 08:35Z commit 3eb44b09 [harness-factory] track-rotation: synthesize the 5-day-open track instead of copying the live one (harness-factory-aggregator-red-since-260909-blocks-every-push, cause 6) -- fixtures 102/0 -- 1 file(s), area conformance -- source: harness-factory: git log main 3eb44b09
- 08:33Z commit a59a2add [harness-factory] Isolate HOME in the heartbeat fixture; date D3/D4 readings relative to now (harness-factory-aggregator-red-since-260909-blocks-every-push, cause 5) -- fixtures 54/0, 75/0 -- 2 file(s), area conformance -- source: harness-factory: git log main a59a2add
- 08:21Z commit 00d198b6 [harness-factory] Regenerate stale docs; correct wcl no-arg tests to the cwd-inference contract (harness-factory-aggregator-red-since-260909-blocks-every-push, causes 1+4) -- 4 file(s), area conformance -- source: harness-factory: git log main 00d198b6
- 07:04Z commit b3b38a0e [harness-factory] Session work: 3 files, no lug transitions recorded -- 3 file(s), area conformance -- source: harness-factory: git log main b3b38a0e

#### circles

- 19:00Z circle pattern-language added at f575f800 -- source: harness-factory: git log --diff-filter=A f575f800 -- reference/circles/pattern-language.yaml
- 18:54Z circle planner-cross-segment-ranking added at 4e655299 -- source: harness-factory: git log --diff-filter=A 4e655299 -- reference/circles/planner-cross-segment-ranking.yaml
- 18:44Z circle lug-type-lifecycles added at 9b332054 -- source: harness-factory: git log --diff-filter=A 9b332054 -- reference/circles/lug-type-lifecycles.yaml
- 09:16Z hook PreToolUse -> node src/hooks/oversizedCanonWriteGuardHook.js (circle oversized-canon-write-guard) at eb88d839 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 08:31Z circle initiative-focus added at db8412ae -- source: harness-factory: git log --diff-filter=A db8412ae -- reference/circles/initiative-focus.yaml
- 08:09Z circle oversized-canon-write-guard added at 641ff5a3 -- source: harness-factory: git log --diff-filter=A 641ff5a3 -- reference/circles/oversized-canon-write-guard.yaml

#### src/conductor

- 18:54Z commit 4e655299 [harness-factory] Planner ranks initiative work first across build and maintain, then allocates remaining capacity -- 12 file(s), area src/conductor -- source: harness-factory: git log main 4e655299
- 08:58Z commit 6d40f566 [harness-factory] Session-start: verify the active-lug pointer against the lug file; retrim injected sections; citation rows must cite (harness-factory-aggregator-red-since-260909-blocks-every-push, cause 2 / rule 12) -- fixtures 40/0, 42/0, 59/0 -- 9 file(s), area src/conductor -- source: harness-factory: git log main 6d40f566
- 08:31Z commit db8412ae [harness-factory] Initiatives get focus: readers, states, Planner precedence, autopilot drive, operator channel -- 6 file(s), area src/conductor -- source: harness-factory: git log main db8412ae
- 05:05Z commit b31eabfa [harness-factory] Retrim rule-12 session-start injection constants (real backlog growth) -- fixtures 375 passed -- 2 file(s), area src/conductor -- source: harness-factory: git log main b31eabfa

#### src/advisor

- 18:38Z commit f5469aca [harness-factory] Evidence bundle carries every file changed by a commit naming the lug, pinned, deduplicated, capped in canon -- fixtures 39/39 -- 6 file(s), area src/advisor -- source: harness-factory: git log main f5469aca
- 18:29Z commit 61dee67a [harness-factory] Kernel verb launches the cross-provider certification on a real transition into review -- fixtures 44/44 -- 6 file(s), area src/advisor -- source: harness-factory: git log main 61dee67a
- 18:23Z commit 01503a3d [harness-factory] Evidence bundle: a LOCAL directory pointer is disclosed and skipped, never an EISDIR crash -- fixtures 11/13, 13/13 -- 5 file(s), area src/advisor -- source: harness-factory: git log main 01503a3d

#### src/compiler

- 08:09Z commit 641ff5a3 [harness-factory] Land two dispatched lugs: wcl hygiene launch classes + write-time cap guard; session-exit path fixes -- 61 file(s), area src/compiler -- source: harness-factory: git log main 641ff5a3
- 06:55Z commit f600ce77 [harness-factory] Session work: 7 files, no lug transitions recorded -- 7 file(s), area src/compiler -- source: harness-factory: git log main f600ce77

#### repo root

- 19:27Z commit 072ca177 [harness-factory] Regenerate generated docs after today's canon changes (proofer evidence_bundle_commit_files, lug-type lifecycles circle) -- 2 file(s), area repo root -- source: harness-factory: git log main 072ca177

#### src/basher

- 05:55Z commit 1e7b1574 [harness-factory] Reword wcl's startup health-check report for readers with no framework vocabulary -- 4 file(s), area src/basher -- source: harness-factory: git log main 1e7b1574

#### src/cartographer

- 08:29Z commit dab6eaa7 [harness-factory] Cartographer: resolve instance-hosted circles under the instance root; never map phantom paths (harness-factory-aggregator-red-since-260909-blocks-every-push, cause 3) -- fixtures 677/0, 20/0 -- 3 file(s), area src/cartographer -- source: harness-factory: git log main dab6eaa7

#### src/hooks

- 18:44Z commit 9b332054 [harness-factory] notice and remember lug types get minimal lifecycles, enforced per type at schema and verb -- fixtures 98/98 -- 8 file(s), area src/hooks -- source: harness-factory: git log main 9b332054

#### src/ledger

- 17:15Z commit 0ae4f352 [harness-factory] Ledger byte cap declared in canon + the flood fold, with a fixture proving the fold idempotent and the cap refusing -- 5 file(s), area src/ledger -- source: harness-factory: git log main 0ae4f352

#### src/lugTracking

- 06:13Z commit 8b6164b5 [harness-factory] Fix done-gate traceability check to search the adopting spoke's framework repo -- 3 file(s), area src/lugTracking -- source: harness-factory: git log main 8b6164b5

#### src/otto

- 19:00Z commit f575f800 [harness-factory] Pattern language: value, lift and self-description on the existing level enum -- 8 file(s), area src/otto -- source: harness-factory: git log main f575f800

### 2026-09-10

#### circles

- 23:17Z circle approach-pattern-library added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/approach-pattern-library.yaml
- 23:17Z circle calibration-record added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/calibration-record.yaml
- 23:17Z circle chain-disposition added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/chain-disposition.yaml
- 23:17Z circle design-salvage-review added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/design-salvage-review.yaml
- 23:17Z circle dispatch-run-salvage added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/dispatch-run-salvage.yaml
- 23:17Z circle hook-invocation-runlog added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/hook-invocation-runlog.yaml
- 23:17Z circle orphan-dispatch-disposition added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/orphan-dispatch-disposition.yaml
- 23:17Z circle pickup-time-reverification added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/pickup-time-reverification.yaml
- 23:17Z circle planner-cycle-allocation added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/planner-cycle-allocation.yaml
- 23:17Z circle provider-usage-and-retry added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/provider-usage-and-retry.yaml
- 23:17Z circle run-roi-extraction added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/run-roi-extraction.yaml
- 23:17Z circle scheduler-failure-operator-channel added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/scheduler-failure-operator-channel.yaml
- 23:17Z circle success-prediction added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/success-prediction.yaml
- 23:17Z circle temporary-limit-boost-awareness added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/temporary-limit-boost-awareness.yaml
- 23:17Z circle unattended-run-kill-switch added at 7a9c1442 -- source: harness-factory: git log --diff-filter=A 7a9c1442 -- reference/circles/unattended-run-kill-switch.yaml
- 22:18Z circle cross-store-finding-coalescing added at 034b976c -- source: harness-factory: git log --diff-filter=A 034b976c -- reference/circles/cross-store-finding-coalescing.yaml
- 22:18Z circle lug-edges added at 034b976c -- source: harness-factory: git log --diff-filter=A 034b976c -- reference/circles/lug-edges.yaml

#### reference

- 23:02Z commit 50fb8451 [harness-factory] Commit mechanical/generated updates from prior sessions' uncommitted work -- 8 file(s), area reference -- source: harness-factory: git log main 50fb8451
- 22:18Z commit 034b976c [harness-factory] Sync reference/circles trim with the already-distributed wheel-hub cut -- 2 file(s), area reference -- source: harness-factory: git log main 034b976c

#### src/advisor

- 23:52Z commit 62a4a0cd [harness-factory] Fix wheelClockCatchup cron invocations never exiting (real leak, real fix) -- fixtures 14/14, 57/57, 48/48 -- 5 file(s), area src/advisor -- source: harness-factory: git log main 62a4a0cd
- 23:05Z commit 02a1987a [harness-factory] Commit proofer/cross-provider verification updates (broad existing coverage) -- 7 file(s), area src/advisor -- source: harness-factory: git log main 02a1987a

#### conformance

- 23:17Z commit 17121d23 [harness-factory] Regenerate lug-checksums.json fixture snapshot -- 1 file(s), area conformance -- source: harness-factory: git log main 17121d23

#### src/conductor

- 23:17Z commit 7a9c1442 [harness-factory] Commit the real, disciplined backlog of prior-session work (143 files) -- 143 file(s), area src/conductor -- source: harness-factory: git log main 7a9c1442

#### src/otto

- 21:37Z commit a9d06e9b [harness-factory] Fix compile-blocking violations: kb SKIP_DIRS and session-start context cap -- 6 file(s), area src/otto -- source: harness-factory: git log main a9d06e9b

### 2026-09-09

#### circles

- 08:41Z circle conductor-window-boundary-claim added at cb4305fa -- source: harness-factory: git log --diff-filter=A cb4305fa -- reference/circles/conductor-window-boundary-claim.yaml
- 08:41Z circle conversation-track-ingestion added at cb4305fa -- source: harness-factory: git log --diff-filter=A cb4305fa -- reference/circles/conversation-track-ingestion.yaml
- 08:41Z circle default-forward-veto-ledger added at cb4305fa -- source: harness-factory: git log --diff-filter=A cb4305fa -- reference/circles/default-forward-veto-ledger.yaml
- 08:41Z circle falsifiability-gate added at cb4305fa -- source: harness-factory: git log --diff-filter=A cb4305fa -- reference/circles/falsifiability-gate.yaml
- 08:41Z circle git-boundary-test-gate added at cb4305fa -- source: harness-factory: git log --diff-filter=A cb4305fa -- reference/circles/git-boundary-test-gate.yaml
- 04:13Z circle node-probe-scheduler added at fcd71d31 -- source: harness-factory: git log --diff-filter=A fcd71d31 -- reference/circles/node-probe-scheduler.yaml
- 04:13Z hook PostToolUse -> node src/hooks/crossProviderVerificationHook.js (circle cross-provider-verification) at fcd71d31 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 03:28Z circle cross-provider-verification added at 2956fdec -- source: harness-factory: git log --diff-filter=A 2956fdec -- reference/circles/cross-provider-verification.yaml

#### src/advisor

- 03:28Z commit 2956fdec [harness-factory] Session work: 8 files, no lug transitions recorded -- 8 file(s), area src/advisor -- source: harness-factory: git log main 2956fdec
- 03:25Z commit 50159c65 [harness-factory] Session work: 2 files, no lug transitions recorded -- 2 file(s), area src/advisor -- source: harness-factory: git log main 50159c65

#### src/conductor

- 08:41Z commit cb4305fa [harness-factory] Session work: harness-factory fixes and features tonight -- 59 file(s), area src/conductor -- source: harness-factory: git log main cb4305fa

#### src/lugTracking

- 11:12Z commit 10ab1cfe [harness-factory] Lug type field and conditional requirements (D1/D2, Part 2) -- 9 file(s), area src/lugTracking -- source: harness-factory: git log main 10ab1cfe

#### src/navigator

- 04:13Z commit fcd71d31 [harness-factory] Session work: 23 files, no lug transitions recorded -- 23 file(s), area src/navigator -- source: harness-factory: git log main fcd71d31

### 2026-09-08

#### circles

- 17:22Z circle conductor-harness-factory-leverage-routing added at 70cbf799 -- source: harness-factory: git log --diff-filter=A 70cbf799 -- reference/circles/conductor-harness-factory-leverage-routing.yaml

#### src/conductor

- 17:22Z commit 70cbf799 [harness-factory] Session work: 6 files, no lug transitions recorded -- 6 file(s), area src/conductor -- source: harness-factory: git log main 70cbf799

### 2026-09-07

#### circles

- 06:50Z circle max-persona-boundary-guard added at 305b4b5f -- source: harness-factory: git log --diff-filter=A 305b4b5f -- reference/circles/max-persona-boundary-guard.yaml
- 06:50Z hook PreToolUse -> node src/hooks/maxPersonaBoundaryGuardHook.js (circle max-persona-boundary-guard) at 305b4b5f -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 06:43Z circle anthropic-rate-limit-five-hour-envelope added at fa391c93 -- source: harness-factory: git log --diff-filter=A fa391c93 -- reference/circles/anthropic-rate-limit-five-hour-envelope.yaml
- 06:43Z circle conductor-heartbeat added at fa391c93 -- source: harness-factory: git log --diff-filter=A fa391c93 -- reference/circles/conductor-heartbeat.yaml
- 06:43Z circle conductor-wave-gate added at fa391c93 -- source: harness-factory: git log --diff-filter=A fa391c93 -- reference/circles/conductor-wave-gate.yaml
- 06:43Z circle headless-usage-reading added at fa391c93 -- source: harness-factory: git log --diff-filter=A fa391c93 -- reference/circles/headless-usage-reading.yaml

#### src/conductor

- 06:43Z commit 858931ee [harness-factory] Fix rule-13 personal-leak refusing the build (paceModel.js provenance comment) -- 1 file(s), area src/conductor -- source: harness-factory: git log main 858931ee
- 06:16Z commit ea89341d [harness-factory] Headless five-hour reading: a real source EXISTS -- found, wired, proven -- fixtures 75/75, 54/54, 80/80, 30/30, 32/32, 43/43, 18/18, 21/21 -- 9 file(s), area src/conductor -- source: harness-factory: git log main ea89341d
- 06:01Z commit 80001300 [harness-factory] windowStart: parse the real epoch-seconds resets_at, so the primary signal fires -- fixtures 19/19, 80/80, 54/54, 40 passed -- 3 file(s), area src/conductor -- source: harness-factory: git log main 80001300
- 05:33Z commit 0db0dcc3 [harness-factory] Conductor heartbeat: the wave gate, callable from outside a session -- fixtures 54/54, 112/114 -- 6 file(s), area src/conductor -- source: harness-factory: git log main 0db0dcc3
- 01:09Z commit bce14b58 [harness-factory] Conductor: autonomous five-hour wave orchestration, and the poller fix behind it -- fixtures 32/32, 79/79 -- 13 file(s), area src/conductor -- source: harness-factory: git log main bce14b58

#### src/lugTracking

- 08:36Z commit 30a7d08a [harness-factory] MAX-124: catch a disclosed gap on the turn that writes it, not never -- fixtures 100/0, 30/0, 58 passed -- 13 file(s), area src/lugTracking -- source: harness-factory: git log main 30a7d08a
- 07:11Z commit feef7b10 [harness-factory] PreCompact track rotation: close the segment, review it, reopen the session -- fixtures 100/100 -- 20 file(s), area src/lugTracking -- source: harness-factory: git log main feef7b10
- 06:43Z commit fa391c93 [harness-factory] Register tonight's four Conductor mechanisms as real circles (MAX-119) -- fixtures 43/43 -- 10 file(s), area src/lugTracking -- source: harness-factory: git log main fa391c93
- 04:42Z commit 77f78b91 [harness-factory] Dispatch into an external repo gets its scope grant automatically -- 6 file(s), area src/lugTracking -- source: harness-factory: git log main 77f78b91

#### docs

- 18:20Z commit 38a09c19 [harness-factory] Fix stale windowStart.js description (MAX-118 superseded MAX-116's fix) -- 1 file(s), area docs -- source: harness-factory: git log main 38a09c19
- 08:11Z commit 9e231609 [harness-factory] MAX-123: close statusline poller lug -- confirm the real Envelope chain, correct a false v1-guard claim -- fixtures 32/32, 30/30 -- 1 file(s), area docs -- source: harness-factory: git log main 9e231609

#### src/hooks

- 06:50Z commit 305b4b5f [harness-factory] max-persona-boundary-guard: refuse top-level authorship of application code -- fixtures 56/56, 63/63, 43/43, 22/22, 19/19 -- 7 file(s), area src/hooks -- source: harness-factory: git log main 305b4b5f
- 06:00Z commit 82999c05 [harness-factory] Fix the real reason 31 dispatch-registry rows stayed stranded -- fixtures 21/21, 19/19, 16/16, 14/14, 34/34, 54/54 -- 6 file(s), area src/hooks -- source: harness-factory: git log main 82999c05

#### src/basher

- 04:37Z commit af624959 [harness-factory] Fix: prefer the operator's real, rich statusline.sh over the bare poller -- fixtures 80/80 -- 2 file(s), area src/basher -- source: harness-factory: git log main af624959

#### src/identity

- 08:17Z commit dac6671c [harness-factory] MAX-122: resolve the callsign wordlist from the harness checkout, not the spoke -- fixtures 28/28, 19/21, 22/22, 16/16, 14/14, 19/19, 20/20, 11/11, 26/26, 63/63, 34/34, 21/21, 53/54 -- 6 file(s), area src/identity -- source: harness-factory: git log main dac6671c

### 2026-09-06

#### src/factory

- 20:36Z commit 26654033 [harness-factory] Absorb mywheel's bench.py: real harness-change effectiveness benchmark -- fixtures 14/14 -- 7 file(s), area src/factory -- source: harness-factory: git log main 26654033
- 20:14Z commit 708297b5 [harness-factory] absorb-mywheel-spoke-position-map: fuse this harness's own real signals into one legible position map -- lug absorb-mywheel-spoke-position-map -- fixtures 36/36 -- 3 file(s), area src/factory -- source: harness-factory: git log main 708297b5
- 20:14Z commit 90f2ae99 [harness-factory] lug absorb-mywheel-vitals-dead-mechanism-tracker: real vitals/dead-mechanism tracker -- lug absorb-mywheel-vitals-dead-mechanism-tracker -- fixtures 34/34, 0/42, 29/68 -- 4 file(s), area src/factory -- source: harness-factory: git log main 90f2ae99
- 20:10Z commit 7227d158 [harness-factory] Add additive verify_mode/verify lug schema fields + a commit-boundary lug gate -- fixtures 10/10 -- 4 file(s), area src/factory -- source: harness-factory: git log main 7227d158
- 20:07Z commit 172a4a25 [harness-factory] Absorb mywheel's bridge.py: real propose/apply generation-intent-harvest tool -- 4 file(s), area src/factory -- source: harness-factory: git log main 172a4a25

#### circles

- 20:16Z circle regression-oracle added at 7786ffe9 -- source: harness-factory: git log --diff-filter=A 7786ffe9 -- reference/circles/regression-oracle.yaml

#### reference

- 20:20Z commit 6e26a4ea [harness-factory] Trim regression-oracle.md for rule 11 (self-hosting compile clean) -- 1 file(s), area reference -- source: harness-factory: git log main 6e26a4ea

#### src/hooks

- 02:01Z commit 5422bdc7 [harness-factory] bash-destructive-command-guard: write a real ledger row on real deny-posture denials -- 3 file(s), area src/hooks -- source: harness-factory: git log main 5422bdc7

#### src/otto

- 20:16Z commit 7786ffe9 [harness-factory] Absorb mywheel's wai_assurance.py: real regression-detecting oracle runner -- fixtures 15/15 -- 5 file(s), area src/otto -- source: harness-factory: git log main 7786ffe9

### 2026-09-05

#### src/factory

- 21:14Z commit 0fcc2e84 [harness-factory] Fix findScheduleJobMatch to also check wheel_clock job-key correspondence -- 2 file(s), area src/factory -- source: harness-factory: git log main 0fcc2e84
- 20:45Z commit 8bce9b8c [harness-factory] MAX-102: absorb mywheel's circle-completeness auditor into the harness -- fixtures 18/18, 85/86 -- 11 file(s), area src/factory -- source: harness-factory: git log main 8bce9b8c
- 06:53Z commit 865d497c [harness-factory] Extend frameworkroot-fallback fix to scaffold.js's own same-pattern bug -- 3 file(s), area src/factory -- source: harness-factory: git log main 865d497c
- 06:48Z commit 38e0ccb5 [harness-factory] Fix frameworkroot-fallback-resolves-to-worktree-not-canonical-repo -- 2 file(s), area src/factory -- source: harness-factory: git log main 38e0ccb5
- 05:46Z commit ea6bc324 [harness-factory] Declare wheel-clock-catchup circle + hook-binding-drift catches undeclared hooks -- fixtures 22/22 -- 5 file(s), area src/factory -- source: harness-factory: git log main ea6bc324
- 04:14Z commit 1cdfc8db [harness-factory] Never silently clobber real, non-v2 .claude/settings.json or generated docs -- 7 file(s), area src/factory -- source: harness-factory: git log main 1cdfc8db
- 04:12Z commit 6b9a8a4c [harness-factory] Generate permissions.allow from autonomy_table_defaults (lug permissions-allow-still-reproduces-v1-blanket-grants) -- lug permissions-allow-still-reproduces-v1-blanket-grants -- fixtures 23/23 -- 5 file(s), area src/factory -- source: harness-factory: git log main 6b9a8a4c

#### circles

- 20:45Z circle circle-completeness-audit added at 8bce9b8c -- source: harness-factory: git log --diff-filter=A 8bce9b8c -- reference/circles/circle-completeness-audit.yaml
- 20:45Z hook SessionStart -> node src/hooks/circleAuditHook.js (circle circle-completeness-audit) at 8bce9b8c -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 20:34Z circle guard-denial-reconciliation added at cb3cb245 -- source: harness-factory: git log --diff-filter=A cb3cb245 -- reference/circles/guard-denial-reconciliation.yaml
- 05:46Z circle wheel-clock-catchup added at ea6bc324 -- source: harness-factory: git log --diff-filter=A ea6bc324 -- reference/circles/wheel-clock-catchup.yaml
- 00:18Z hook SessionStart -> node src/hooks/wheelClockCatchupHook.js (circle wheel-clock-catchup) at 84b436ab -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e

#### src/basher

- 18:43Z commit 7120206f [harness-factory] MAX-099: bring launchSpoke to pending-cut parity with wclCli.js -- fixtures 19/19, 7/7 -- 3 file(s), area src/basher -- source: harness-factory: git log main 7120206f
- 07:01Z commit 27301e85 [harness-factory] Stale-instance check no longer refuses a launch for a pending cut it would fix -- 3 file(s), area src/basher -- source: harness-factory: git log main 27301e85
- 05:37Z commit e466a2e7 [harness-factory] Session-start lane consolidation + routine-file merge strategy (half 1) -- fixtures 13/13 -- 4 file(s), area src/basher -- source: harness-factory: git log main e466a2e7

#### src/compiler

- 18:26Z commit d7609278 [harness-factory] compile() ok no longer counts informational non-canon-yaml as a failure -- fixtures 5/5 -- 5 file(s), area src/compiler -- source: harness-factory: git log main d7609278
- 08:23Z commit eece55b4 [harness-factory] Fix real defect: compile() rules 04/11/13 scanned a spoke's non-canon legacy tree as if it were canon -- fixtures 04/11 -- 9 file(s), area src/compiler -- source: harness-factory: git log main eece55b4
- 00:37Z commit 2fe7b6c1 [harness-factory] Fix loadCanon crash on genuinely malformed YAML (lug loadcanon-crashes-on-malformed-non-canon-yaml) -- lug loadcanon-crashes-on-malformed-non-canon-yaml -- fixtures 27/27 -- 3 file(s), area src/compiler -- source: harness-factory: git log main 2fe7b6c1

#### src/hooks

- 20:10Z commit 9d5528a1 [harness-factory] Fix real defect: lug-lifecycle-tracker and ready-gate-stub denials vanish with no ledger trace -- 6 file(s), area src/hooks -- source: harness-factory: git log main 9d5528a1
- 20:07Z commit bb1a8c5f [harness-factory] MAX-101: bash-lug-guard denial trace + guard-denial-reconciliation job -- fixtures 23/23, 30/30 -- 5 file(s), area src/hooks -- source: harness-factory: git log main bb1a8c5f
- 00:18Z commit 84b436ab [harness-factory] Wire a SessionStart catch-up driver for the wheel clock (lug: wheel-clock-sessionstart-catchup-tick) -- fixtures 63/63, 31/31, 21/21 -- 5 file(s), area src/hooks -- source: harness-factory: git log main 84b436ab

#### src/otto

- 19:58Z commit 68c66cac [harness-factory] Wire reconcile-ledger into the wheel-clock scheduler (JOB_RUNNERS) -- 2 file(s), area src/otto -- source: harness-factory: git log main 68c66cac
- 05:21Z commit 4c9a4722 [harness-factory] Fix roi-rollup crash on non-rollup-shaped history row, isolate tick job failures -- 4 file(s), area src/otto -- source: harness-factory: git log main 4c9a4722
- 04:11Z commit ef657f33 [harness-factory] Add advisors bucket to buildRoiRollup, distinct from the building bucket -- 2 file(s), area src/otto -- source: harness-factory: git log main ef657f33

#### reference

- 20:34Z commit cb3cb245 [harness-factory] Add missing canonical source for guard-denial-reconciliation circle -- 2 file(s), area reference -- source: harness-factory: git log main cb3cb245
- 20:28Z commit 8a0e5181 [harness-factory] Fix stale trigger text at its canonical source, not just the derived copy -- 3 file(s), area reference -- source: harness-factory: git log main 8a0e5181

#### conformance

- 05:04Z commit 624c8896 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main 624c8896

#### src/lugTracking

- 04:03Z commit c5068893 [harness-factory] Fix dispatch-raw-error-misclassified-as-completed: raw launcher errors no longer land as completed -- 2 file(s), area src/lugTracking -- source: harness-factory: git log main c5068893

### 2026-09-04

#### src/basher

- 07:48Z commit f619fcd4 [harness-factory] Wire global-settings-drift-check onto real SessionStart cadence -- 7 file(s), area src/basher -- source: harness-factory: git log main f619fcd4
- 07:39Z commit e3e55e96 [harness-factory] config-custody: disclose why the two zero-caller probes stay uncalled -- fixtures 103 passed -- 1 file(s), area src/basher -- source: harness-factory: git log main e3e55e96
- 06:18Z commit 7591c286 [harness-factory] Detach the launch supervisor so a dispatch survives its orchestrator dying -- fixtures 34/34, 29/29, 21/21, 28/28 -- 7 file(s), area src/basher -- source: harness-factory: git log main 7591c286
- 04:19Z commit 1450bd50 [harness-factory] MAX-073: real, preview-only reconciliation of the operator's global Claude Code config -- fixtures 17/17, 11/11, 10/10, 12/12 -- 3 file(s), area src/basher -- source: harness-factory: git log main 1450bd50

#### circles

- 07:48Z circle global-settings-drift-check added at f619fcd4 -- source: harness-factory: git log --diff-filter=A f619fcd4 -- reference/circles/global-settings-drift-check.yaml
- 07:48Z hook SessionStart -> node src/hooks/globalSettingsDriftHook.js (circle global-settings-drift-check) at f619fcd4 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e

#### src/lugTracking

- 06:08Z commit f125399b [harness-factory] Self-heal orphaned dispatch-registry rows stuck at "running" -- 6 file(s), area src/lugTracking -- source: harness-factory: git log main f125399b
- 05:50Z commit 7d461f75 [harness-factory] Fix scope-guard cross-dispatch leakage via subagent_type fallback -- 2 file(s), area src/lugTracking -- source: harness-factory: git log main 7d461f75

#### canon

- 05:36Z commit cb1fbc21 [harness-factory] MAX-075: declare harness-factory's own Ozi advisor identity -- 2 file(s), area canon -- source: harness-factory: git log main cb1fbc21

#### repo root

- 17:03Z commit b143e210 [harness-factory] Regenerate harness-factory's own stale generated docs -- 2 file(s), area repo root -- source: harness-factory: git log main b143e210

#### src/advisor

- 08:27Z commit 0807b895 [harness-factory] Fix resolveExternalPointer EISDIR crash on directory-shaped pointers -- fixtures 6/6 -- 3 file(s), area src/advisor -- source: harness-factory: git log main 0807b895

#### src/hooks

- 07:37Z commit d172a822 [harness-factory] Give scope-guard declaration phrases per-file granularity -- fixtures 63/63 -- 4 file(s), area src/hooks -- source: harness-factory: git log main d172a822

#### src/otto

- 00:10Z commit 86bce45f [harness-factory] MAX-072: real advisor autopilot -- activation-to-dispatch link for otto/kb-curator -- fixtures 21/21, 31/31, 29/29, 25/25 -- 5 file(s), area src/otto -- source: harness-factory: git log main 86bce45f

### 2026-09-03

#### circles

- 02:30Z hook Notification -> node src/hooks/notificationNotifyHook.js (circle notification-agent-waiting-notify) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook PostToolUse -> node src/hooks/cartographerCommitTriggerHook.js (circle cartographer-commit-trigger) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook PreCompact -> node src/hooks/preCompactCheckpointHook.js (circle precompact-checkpoint) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook PreToolUse -> node src/hooks/agentTargetScopeGuardHook.js (circle agent-target-scope-guard) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook PreToolUse -> node src/hooks/agentToolScopeGuardHook.js (circle agent-tool-scope-guard) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook PreToolUse -> node src/hooks/bashDestructiveGuardHook.js (circle bash-destructive-command-guard) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook PreToolUse -> node src/hooks/bashLugGuardHook.js (circle bash-lug-guard) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook PreToolUse -> node src/hooks/definitionCompleteGateHook.js (circle definition-complete-gate) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook PreToolUse -> node src/hooks/lugLifecycleHook.js (circle lug-lifecycle-tracker) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook PreToolUse -> node src/hooks/readyGateStubHook.js (circle ready-gate-stub) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook PreToolUse -> node src/hooks/testFileLugMarkerHook.js (circle test-lug-traceability) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook SessionEnd -> node src/hooks/sessionEndHandoffHook.js (circle session-end-handoff) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook SessionEnd -> node src/hooks/sessionEndNotifyHook.js (circle session-end-notify) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook SessionEnd -> node src/hooks/sessionExitCommitHook.js (circle session-exit-commit) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook SessionStart -> node src/hooks/hookBindingDriftHook.js (circle hook-binding-drift) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook SessionStart -> node src/hooks/sessionCheckpointHook.js (circle session-continuity-checkpoint) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook SessionStart -> node src/hooks/sessionRegistryHook.js (circle session-registry) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook SessionStart -> node src/hooks/sessionStartWarmupHook.js (circle session-start-warmup) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook SessionStart -> node src/hooks/warmupGoalsReviewHook.js (circle warmup-goals-review) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook Stop -> node src/hooks/footerAuditHook.js (circle footer-audit) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook Stop -> node src/hooks/lugIntegrityHook.js (circle lug-integrity-checksum) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook Stop -> node src/hooks/stopNotifyHook.js (circle stop-agent-waiting-notify) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook Stop -> node src/hooks/stopTurnMarkerHook.js (circle stop-turn-marker) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook Stop -> node src/hooks/trackWriteHook.js (circle session-track-write) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook UserPromptSubmit -> node src/hooks/captureDirectionHook.js (circle capture-direction) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook UserPromptSubmit -> node src/hooks/footerCorrectionInjectionHook.js (circle footer-correction-injection) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook UserPromptSubmit -> node src/hooks/liveApplyAnnounceHook.js (circle live-apply-announce) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 02:30Z hook UserPromptSubmit -> node src/hooks/turnStartAttributionHook.js (circle turn-start-attribution) at 78402cb2 -- source: harness-factory: .claude/settings.json at 66e48e3a vs 23dc5f6e
- 01:10Z circle verify-fleet-versions added at 50b12400 -- source: harness-factory: git log --diff-filter=A 50b12400 -- reference/circles/verify-fleet-versions.yaml
- 01:00Z circle canonical-spec-lug-index added at 60ed7f11 -- source: harness-factory: git log --diff-filter=A 60ed7f11 -- reference/circles/canonical-spec-lug-index.yaml
- 01:00Z circle process-signal-inbox added at 60ed7f11 -- source: harness-factory: git log --diff-filter=A 60ed7f11 -- reference/circles/process-signal-inbox.yaml
- 01:00Z circle publish-kb-cut added at 60ed7f11 -- source: harness-factory: git log --diff-filter=A 60ed7f11 -- reference/circles/publish-kb-cut.yaml
- 00:50Z circle agent-target-scope-guard added at 8ddd97ec -- source: harness-factory: git log --diff-filter=A 8ddd97ec -- reference/circles/agent-target-scope-guard.yaml

#### conformance

- 20:18Z commit c48c9037 [harness-factory] MAX-069: fix stale scoped-compile workaround causing rule-20 false positives -- fixtures 10/10 -- 1 file(s), area conformance -- source: harness-factory: git log main c48c9037
- 18:53Z commit a4d3ce48 [harness-factory] MAX-060: replace hand-maintained test:suites with auto-discovery -- 3 file(s), area conformance -- source: harness-factory: git log main a4d3ce48
- 18:19Z commit 7b9d322d [harness-factory] MAX-059: complete rule 20's fixture (root cause: Max's manual test, not the rule) -- fixtures 7/7 -- 2 file(s), area conformance -- source: harness-factory: git log main 7b9d322d
- 17:53Z commit ee1970f0 [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main ee1970f0
- 17:16Z commit 22580c5e [harness-factory] MAX-052: verify wclCli.js's v1 delegation branch is real, not dead code -- fixtures 9/9 -- 2 file(s), area conformance -- source: harness-factory: git log main 22580c5e
- 01:36Z commit 77cba3c9 [harness-factory] Recalibrate rule-12's own broken fixture for the raised cap (MAX-019) -- fixtures 36/36 -- 4 file(s), area conformance -- source: harness-factory: git log main 77cba3c9
- 01:32Z commit 48b6f295 [harness-factory] Use static imports in hub-governance circle tests so cartographer resolves implementing_files -- fixtures 15/15 -- 3 file(s), area conformance -- source: harness-factory: git log main 48b6f295
- 01:18Z commit 7dbf5fcd [harness-factory] Add local conformance tests for the hub-governance circles (rule 01) -- fixtures 15/15 -- 4 file(s), area conformance -- source: harness-factory: git log main 7dbf5fcd
- 00:38Z commit d8a61b9b [harness-factory] Add nonzero_exit coverage to provider-contract conformance test -- fixtures 38/38 -- 1 file(s), area conformance -- source: harness-factory: git log main d8a61b9b

#### src/compiler

- 18:39Z commit ee423dba [harness-factory] MAX-063: real 1Password service counterparty row + generic service-card convention -- fixtures 11/12, 12/12 -- 4 file(s), area src/compiler -- source: harness-factory: git log main ee423dba
- 18:11Z commit e11e0bd2 [harness-factory] MAX-056: rule 20, no-dead-orchestrator-knowledge-source -- fixtures 15/19 -- 5 file(s), area src/compiler -- source: harness-factory: git log main e11e0bd2
- 05:48Z commit 80199c78 [harness-factory] MAX-045: compile-self now writes the same permissions.deny block scaffold.js does -- fixtures 23/23 -- 5 file(s), area src/compiler -- source: harness-factory: git log main 80199c78
- 03:20Z commit 9367bccc [harness-factory] MAX-035: skip .github/ as canon, and tell pre-v2 legacy YAML apart from real malformed canon -- fixtures 18/18 -- 4 file(s), area src/compiler -- source: harness-factory: git log main 9367bccc
- 03:18Z commit d6d73b94 [harness-factory] MAX-036: rule 13's binary-file guard never actually fired -- fix at root cause -- fixtures 12/12, 36/36, 76/76 -- 3 file(s), area src/compiler -- source: harness-factory: git log main d6d73b94
- 01:33Z commit 0c26c5f9 [harness-factory] Session work: 15 lugs (provider-contract-second-provider-path, wilbur-a2-followup-harness-factory-spoke-identity-missing, orchestrator-schema-hardcoded-to-wilbur-blocks-max, ...) -- 3 file(s), area src/compiler -- source: harness-factory: git log main 0c26c5f9
- 01:24Z commit b8206e3f [harness-factory] Remove personal-path leak from v1PathScan.js comment; trim rule-12 policy file -- 2 file(s), area src/compiler -- source: harness-factory: git log main b8206e3f
- 01:19Z commit f093f6c5 [harness-factory] Root-cause the v1-path scan mywheel false positive (was patched, not fixed) -- fixtures 4/4 -- 2 file(s), area src/compiler -- source: harness-factory: git log main f093f6c5
- 00:51Z commit ec332fa7 [harness-factory] Generalize loader SKIP_DIRS and close compile-self teardown exposure window -- 7 file(s), area src/compiler -- source: harness-factory: git log main ec332fa7

#### src/hooks

- 19:58Z commit 764e44f8 [harness-factory] MAX-066: real session attribution fixes track-artifact contamination under concurrency -- fixtures 18/18, 7/7, 23/23 -- 11 file(s), area src/hooks -- source: harness-factory: git log main 764e44f8
- 19:48Z commit 38b3841b [harness-factory] MAX-067: trim scope-declaration-phrases.yaml to fix harness-factory's broken self-compile -- fixtures 48/48 -- 2 file(s), area src/hooks -- source: harness-factory: git log main 38b3841b
- 18:35Z commit 9224b943 [harness-factory] MAX-061: narrow agent-tool-scope-guard's false positive on content-preservation prose -- fixtures 48/48 -- 3 file(s), area src/hooks -- source: harness-factory: git log main 9224b943
- 03:07Z commit 9bce8dc2 [harness-factory] MAX-034 Job 1: restore denyJSON's systemMessage param, lost in the MAX-030 merge -- fixtures 42/42, 41/42, 30/30 -- 1 file(s), area src/hooks -- source: harness-factory: git log main 9bce8dc2
- 02:32Z commit 72f561f4 [harness-factory] MAX-030: bound live-hook-capture growth and stop reparsing it per launch -- fixtures 30/30 -- 9 file(s), area src/hooks -- source: harness-factory: git log main 72f561f4
- 02:29Z commit 2ae5e862 [harness-factory] MAX-028: FBL-065 followup -- catch a fork's write after dispatch-time matching misses it -- fixtures 42/42 -- 14 file(s), area src/hooks -- source: harness-factory: git log main 2ae5e862
- 02:07Z commit eeba05b7 [harness-factory] MAX-025: real second-provider liveness proof plus a personal-path-leak fix -- 8 file(s), area src/hooks -- source: harness-factory: git log main eeba05b7
- 01:28Z commit ef315617 [harness-factory] Remove remaining personal-path leaks from shipping artifact (rule 13) -- 4 file(s), area src/hooks -- source: harness-factory: git log main ef315617

#### src/factory

- 17:25Z commit ecdc36a1 [harness-factory] MAX-051: wire real regeneration for self-hosting spoke's own generated docs -- fixtures 045/047, 048/049, 49/49 -- 15 file(s), area src/factory -- source: harness-factory: git log main ecdc36a1
- 06:22Z commit 6689b1a4 [harness-factory] MAX-050: resolve the Ambassador Brief's glossary pointer to where it really lives, restoring a MAX-048 fix I accidentally reverted merging MAX-047 -- fixtures 19/19, 25/25, 31/31, 13/13 -- 3 file(s), area src/factory -- source: harness-factory: git log main 6689b1a4
- 06:18Z commit bfea1f1d [harness-factory] MAX-049: generated docs enumerate a spoke's real live circles, not a hardcoded path -- fixtures 31/31, 25/25 -- 6 file(s), area src/factory -- source: harness-factory: git log main bfea1f1d
- 06:09Z commit f5ff6b78 [harness-factory] MAX-047: adopted spokes get a real compiler command, not an ENOENT -- fixtures 25/25, 14/14, 23/23 -- 8 file(s), area src/factory -- source: harness-factory: git log main f5ff6b78
- 05:57Z commit cd6dd189 [harness-factory] MAX-048: fix stale ROI-rollup claim in the generated Ambassador Brief -- fixtures 13/13, 14/14 -- 1 file(s), area src/factory -- source: harness-factory: git log main cd6dd189
- 05:07Z commit e61b185c [harness-factory] MAX-042: resolve tool_disposition's replaced_by to its real tool field, not the raw entity name -- fixtures 14 passed -- 8 file(s), area src/factory -- source: harness-factory: git log main e61b185c
- 01:10Z commit 50b12400 [harness-factory] Build fleet-version wiring, spoke arrival-audit, and restore-manifest -- 15 file(s), area src/factory -- source: harness-factory: git log main 50b12400

#### src/basher

- 20:03Z commit 8683332a [harness-factory] MAX-068: wire the documented `wcl init` verb into the real CLI dispatch table -- fixtures 9/9, 11/11, 10/10, 7/7 -- 2 file(s), area src/basher -- source: harness-factory: git log main 8683332a
- 18:15Z commit e210d040 [harness-factory] MAX-057: basher counterparties CLI verb -- fixtures 13/13, 10/10, 7/7 -- 4 file(s), area src/basher -- source: harness-factory: git log main e210d040
- 05:43Z commit 503614ea [harness-factory] MAX-044: model-tier selection on the programmatic dispatch path -- fixtures 28/28, 29/29, 7/7 -- 6 file(s), area src/basher -- source: harness-factory: git log main 503614ea
- 02:07Z commit 509b2e9f [harness-factory] MAX-021/026: replace the blind wall-clock launch kill with a silence watchdog -- fixtures 021/026, 34/34 -- 7 file(s), area src/basher -- source: harness-factory: git log main 509b2e9f
- 01:14Z commit b12b2267 [harness-factory] Fix worktree spokeDir treated as its own frameworkRoot (real credential-copy regression) -- 4 file(s), area src/basher -- source: harness-factory: git log main b12b2267

#### src/otto

- 18:45Z commit c565ae15 [harness-factory] MAX-064: real wheel-wide cross-store reconciliation job -- fixtures 26/26, 28/28, 31/31 -- 5 file(s), area src/otto -- source: harness-factory: git log main c565ae15
- 18:04Z commit fec18148 [harness-factory] MAX-054: wire the statusline poller's real output into a real Envelope -- fixtures 30/30 -- 3 file(s), area src/otto -- source: harness-factory: git log main fec18148
- 01:41Z commit d560ad97 [harness-factory] MAX-023: report malformed per-file advisor YAML instead of silently dropping it -- fixtures 34/34 -- 4 file(s), area src/otto -- source: harness-factory: git log main d560ad97
- 01:00Z commit 60ed7f11 [harness-factory] Add publish-kb-cut, spec-lug-index, and signal-inbox Otto mechanisms -- 12 file(s), area src/otto -- source: harness-factory: git log main 60ed7f11

#### repo root

- 06:23Z commit 3cc05451 [harness-factory] Regenerate harness-factory's own live docs (MAX-050 fix live) -- 1 file(s), area repo root -- source: harness-factory: git log main 3cc05451
- 06:19Z commit 86301cdf [harness-factory] Regenerate harness-factory's own live CLAUDE.md and AMBASSADOR_BRIEF.md (MAX-049 fix live) -- 2 file(s), area repo root -- source: harness-factory: git log main 86301cdf
- 01:17Z commit 4fa609fd [harness-factory] Resolve unresolved merge conflict markers in package.json -- 1 file(s), area repo root -- source: harness-factory: git log main 4fa609fd

#### .claude

- 05:49Z commit cd32c7c9 [harness-factory] Regenerate harness-factory's own live .claude/settings.json (MAX-045 fix applied) -- 1 file(s), area .claude -- source: harness-factory: git log main cd32c7c9
- 02:30Z commit 78402cb2 [harness-factory] Fix: restore .claude/settings.json deleted by the prior commit -- 1 file(s), area .claude -- source: harness-factory: git log main 78402cb2

#### src/advisor

- 18:02Z commit 6864f064 [harness-factory] MAX-053: real active-advisor attribution, session-scoped, wired into max+otto -- fixtures 23/23, 25/25, 29/29 -- 12 file(s), area src/advisor -- source: harness-factory: git log main 6864f064
- 04:40Z commit a4adfd63 [harness-factory] MAX-040/041: durable model-lane declaration + a second real FBL-046 recurrence, closed -- fixtures 040/041, 24/24, 12/12, 7/7 -- 7 file(s), area src/advisor -- source: harness-factory: git log main a4adfd63

#### src/lugTracking

- 18:17Z commit 2cf1b7bc [harness-factory] MAX-058: real P0 ledger row auto-opens a bug-fix-protocol lug -- fixtures 28/28 -- 6 file(s), area src/lugTracking -- source: harness-factory: git log main 2cf1b7bc
- 00:50Z commit 8ddd97ec [harness-factory] Add path-based cross-workstream scope guard (MAX-020, FBL-101) -- 10 file(s), area src/lugTracking -- source: harness-factory: git log main 8ddd97ec

#### canon

- 00:39Z commit bdb37292 [harness-factory] Add harness-factory.spoke.yaml identity entity (MAX/wilbur-a2-followup) -- 2 file(s), area canon -- source: harness-factory: git log main bdb37292

#### src/conductor

- 04:24Z commit 1106697d [harness-factory] MAX-039: Conductor weighs a real quota signal; Sparky gated on real operator-idle -- fixtures 43/43, 18/18 -- 8 file(s), area src/conductor -- source: harness-factory: git log main 1106697d

#### src/messaging

- 02:26Z commit 04e5b0bd [harness-factory] MAX-029: Wilbur-E cross-machine transport (queue-and-drain) plus Group Message payload shape -- fixtures 58/58 -- 7 file(s), area src/messaging -- source: harness-factory: git log main 04e5b0bd

#### src/minder

- 01:41Z commit e9ba7ecb [harness-factory] MAX-022: fix minder-shadow-check latency measurement to per-turn grouping -- fixtures 31/31 -- 7 file(s), area src/minder -- source: harness-factory: git log main e9ba7ecb

### 2026-09-02

#### conformance

- 21:18Z commit 7d0e871b [harness-factory] Add current-layout statusline usage poller (MAX-015) -- 2 file(s), area conformance -- source: harness-factory: git log main 7d0e871b
- 21:07Z commit 7960c759 [harness-factory] Generalize orchestrator.schema.json beyond Wilbur (MAX-010) -- 3 file(s), area conformance -- source: harness-factory: git log main 7960c759
- 20:07Z commit 75451fd2 [harness-factory] Add row_kind: conversation to ledger schema (MAX-005) -- 3 file(s), area conformance -- source: harness-factory: git log main 75451fd2

#### src/compiler

- 17:01Z commit b70130e3 [harness-factory] Session work: 11 files, no lug transitions recorded -- fixtures 100/101 -- 11 file(s), area src/compiler -- source: harness-factory: git log main b70130e3
- 03:18Z commit ff31ab10 [harness-factory] Session work: 24 lugs (session-registry-callsigns-id-v3-references, applycut-liveness-and-version-drift, references-ephemeral-todos, ...) -- 24 file(s), area src/compiler -- source: harness-factory: git log main ff31ab10

#### src/advisor

- 21:09Z commit fe695a11 [harness-factory] Add proofer independence axes: model, provider, method, input (MAX-012) -- fixtures 21/21, 25/25 -- 11 file(s), area src/advisor -- source: harness-factory: git log main fe695a11

#### src/basher

- 20:24Z commit b7e8b2db [harness-factory] Fix dispatch timeout forwarding and outcome statuses (MAX-007) -- fixtures 29/29 -- 3 file(s), area src/basher -- source: harness-factory: git log main b7e8b2db

#### src/hooks

- 21:03Z commit c51e01c1 [harness-factory] Fix lug-integrity heal false-positive on legitimate git merges (MAX-011) -- fixtures 31/31 -- 5 file(s), area src/hooks -- source: harness-factory: git log main c51e01c1

### 2026-09-01

#### circles

- 22:50Z circle agent-tool-scope-guard added at 072f2280 -- source: harness-factory: git log --diff-filter=A 072f2280 -- reference/circles/agent-tool-scope-guard.yaml
- 09:21Z circle cartographer-commit-trigger added at a1721243 -- source: harness-factory: git log --diff-filter=A a1721243 -- reference/circles/cartographer-commit-trigger.yaml
- 09:21Z circle precompact-checkpoint added at a1721243 -- source: harness-factory: git log --diff-filter=A a1721243 -- reference/circles/precompact-checkpoint.yaml
- 08:18Z circle notification-agent-waiting-notify added at a93e22cf -- source: harness-factory: git log --diff-filter=A a93e22cf -- reference/circles/notification-agent-waiting-notify.yaml
- 08:18Z circle stop-agent-waiting-notify added at a93e22cf -- source: harness-factory: git log --diff-filter=A a93e22cf -- reference/circles/stop-agent-waiting-notify.yaml
- 07:35Z circle session-end-notify added at 108eac3c -- source: harness-factory: git log --diff-filter=A 108eac3c -- reference/circles/session-end-notify.yaml
- 07:35Z circle wcl-verify-then-launch added at 108eac3c -- source: harness-factory: git log --diff-filter=A 108eac3c -- reference/circles/wcl-verify-then-launch.yaml
- 06:51Z circle footer-correction-injection added at ce1358d2 -- source: harness-factory: git log --diff-filter=A ce1358d2 -- reference/circles/footer-correction-injection.yaml
- 06:51Z circle turn-start-attribution added at ce1358d2 -- source: harness-factory: git log --diff-filter=A ce1358d2 -- reference/circles/turn-start-attribution.yaml
- 05:13Z circle hook-binding-drift added at 0f5decb4 -- source: harness-factory: git log --diff-filter=A 0f5decb4 -- reference/circles/hook-binding-drift.yaml

#### conformance

- 10:13Z commit 95f72d4a [harness-factory] Session work: 9 lugs (bash-destructive-command-guard-widening, harness-factory-config-drift-self-heal, advisor-roster-reconciliation, ...) -- 2 file(s), area conformance -- source: harness-factory: git log main 95f72d4a
- 08:20Z commit 44ea693a [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main 44ea693a
- 05:04Z commit b46b19cb [harness-factory] Session work: 1 file, no lug transitions recorded -- 1 file(s), area conformance -- source: harness-factory: git log main b46b19cb

#### src/basher

- 08:18Z commit a93e22cf [harness-factory] Session work: 19 files, no lug transitions recorded -- 19 file(s), area src/basher -- source: harness-factory: git log main a93e22cf
- 07:56Z commit 037733be [harness-factory] Session work: 4 files, no lug transitions recorded -- 4 file(s), area src/basher -- source: harness-factory: git log main 037733be
- 07:35Z commit 108eac3c [harness-factory] Session work: 14 files, no lug transitions recorded -- 14 file(s), area src/basher -- source: harness-factory: git log main 108eac3c

#### src/hooks

- 09:29Z commit 406bc463 [harness-factory] Fix cartographer-commit-trigger correctness bug found by Proofer certification -- 3 file(s), area src/hooks -- source: harness-factory: git log main 406bc463
- 09:21Z commit a1721243 [harness-factory] FBL-066/068: destination-by-ownership fixes, precompact checkpoint, cartographer commit trigger -- fixtures 066/068, 2/3 -- 23 file(s), area src/hooks -- source: harness-factory: git log main a1721243
- 06:51Z commit ce1358d2 [harness-factory] Session work: 24 files, no lug transitions recorded -- 24 file(s), area src/hooks -- source: harness-factory: git log main ce1358d2

#### src/lugTracking

- 22:50Z commit 072f2280 [harness-factory] Session work: 11 lugs (fbl072-remainder-rule14-and-goals-backlog-fix, fbl077-session-scoped-active-lug, fbl067-p0-class-and-canaries, ...) -- 65 file(s), area src/lugTracking -- source: harness-factory: git log main 072f2280
- 14:48Z commit 61c99c22 [harness-factory] Session work: 7 files, no lug transitions recorded -- 7 file(s), area src/lugTracking -- source: harness-factory: git log main 61c99c22

#### src/factory

- 05:13Z commit 0f5decb4 [harness-factory] Session work: 8 files, no lug transitions recorded -- 8 file(s), area src/factory -- source: harness-factory: git log main 0f5decb4

#### src/otto

- 07:06Z commit bc364c8e [harness-factory] Session work: 5 files, no lug transitions recorded -- 5 file(s), area src/otto -- source: harness-factory: git log main bc364c8e

#### src/tastegraph

- 09:36Z commit 5a8d6c5c [harness-factory] Build tastegraph proposal mechanism (FBL-066 ruling 4) -- 2 file(s), area src/tastegraph -- source: harness-factory: git log main 5a8d6c5c

### 2026-08-31

#### circles

- 21:35Z circle bash-destructive-command-guard added at 6a93b4f6 -- source: harness-factory: git log --diff-filter=A 6a93b4f6 -- reference/circles/bash-destructive-command-guard.yaml
- 05:50Z circle session-exit-commit added at 4a86be54 -- source: harness-factory: git log --diff-filter=A 4a86be54 -- reference/circles/session-exit-commit.yaml
- 05:18Z circle live-apply-announce added at 2e6ce6a6 -- source: harness-factory: git log --diff-filter=A 2e6ce6a6 -- reference/circles/live-apply-announce.yaml
- 05:18Z circle session-registry added at 9cef7c67 -- source: harness-factory: git log --diff-filter=A 9cef7c67 -- reference/circles/session-registry.yaml
- 05:18Z circle footer-audit added at a3c7df81 -- source: harness-factory: git log --diff-filter=A a3c7df81 -- reference/circles/footer-audit.yaml

#### src/basher

- 21:35Z commit 6a93b4f6 [harness-factory] Session work: 9 files, no lug transitions recorded -- 9 file(s), area src/basher -- source: harness-factory: git log main 6a93b4f6
- 05:18Z commit 21b0ef2f [harness-factory] The config-custody manifest and real version-drift detection -- 6 file(s), area src/basher -- source: harness-factory: git log main 21b0ef2f
- 05:18Z commit 2e6ce6a6 [harness-factory] wcl, cut-update, and the live-apply announce circle -- 8 file(s), area src/basher -- source: harness-factory: git log main 2e6ce6a6

#### src/hooks

- 05:50Z commit 4a86be54 [harness-factory] Session work: 18 files, no lug transitions recorded -- 18 file(s), area src/hooks -- source: harness-factory: git log main 4a86be54
- 05:18Z commit 38460306 [harness-factory] Lug kernel verbs, lifecycle tracking, the gates, and the continuity checkpoint -- 18 file(s), area src/hooks -- source: harness-factory: git log main 38460306
- 05:18Z commit 5016a740 [harness-factory] Cross-repo instance-root resolution: a lug worked from another repo now costs -- 9 file(s), area src/hooks -- source: harness-factory: git log main 5016a740

#### src/advisor

- 05:18Z commit 3d67d6dd [harness-factory] Assayer plan drafting, the fabrication check, and external evidence resolution -- 10 file(s), area src/advisor -- source: harness-factory: git log main 3d67d6dd
- 05:18Z commit 72f9f296 [harness-factory] One persistent provider config dir, a credential preflight, and an authoritative secrets bag -- 4 file(s), area src/advisor -- source: harness-factory: git log main 72f9f296

#### src/compiler

- 05:18Z commit 09906283 [harness-factory] Generated CLAUDE.md, compile-self, the aggregator, and the live hook bindings -- 9 file(s), area src/compiler -- source: harness-factory: git log main 09906283
- 05:18Z commit cb2bad5d [harness-factory] Admission rule 12: cap history and the cap-growth review lug -- 6 file(s), area src/compiler -- source: harness-factory: git log main cb2bad5d

#### src/conductor

- 05:18Z commit 8726e966 [harness-factory] Warmup goals review and the bash lug guard -- 6 file(s), area src/conductor -- source: harness-factory: git log main 8726e966

#### src/factory

- 05:56Z commit f4cf5596 [harness-factory] Session work: 4 files, no lug transitions recorded -- 4 file(s), area src/factory -- source: harness-factory: git log main f4cf5596

#### src/identity

- 05:18Z commit 9cef7c67 [harness-factory] id-v3 identity: callsigns, the session registry, and spoke liveness -- 12 file(s), area src/identity -- source: harness-factory: git log main 9cef7c67

#### src/influence

- 05:18Z commit c56c309c [harness-factory] The session-upkeep manifest, influence contracts, and the minder-tracks clarification -- 6 file(s), area src/influence -- source: harness-factory: git log main c56c309c

#### src/ledger

- 05:18Z commit 47dda5c8 [harness-factory] The prompt-id protocol, origin codes, references, and the track artifact -- 11 file(s), area src/ledger -- source: harness-factory: git log main 47dda5c8

#### src/lugTracking

- 05:18Z commit a3c7df81 [harness-factory] The merged turn footer and its audit circle -- 8 file(s), area src/lugTracking -- source: harness-factory: git log main a3c7df81

### 2026-08-29

#### circles

- 01:13Z circle reconcile-advisor-roster added at ff462c91 -- source: harness-factory: git log --diff-filter=A ff462c91 -- reference/circles/reconcile-advisor-roster.yaml
- 00:48Z circle session-end-handoff added at d667a113 -- source: harness-factory: git log --diff-filter=A d667a113 -- reference/circles/session-end-handoff.yaml
- 00:48Z circle session-track-write added at d667a113 -- source: harness-factory: git log --diff-filter=A d667a113 -- reference/circles/session-track-write.yaml

#### src/advisor

- 02:22Z commit d9f78aee [harness-factory] Fix gemini Proofer verdict truncation: raise max_tokens 1024 -> 8192 (260828-FBL-011) -- 3 file(s), area src/advisor -- source: harness-factory: git log main d9f78aee
- 00:48Z commit 87b23243 [harness-factory] Give the Proofer a real evidence bundle and citation-fabrication check -- 6 file(s), area src/advisor -- source: harness-factory: git log main 87b23243

#### src/ledger

- 00:48Z commit b1f7d2d3 [harness-factory] Add teaching writeback and the ledger row_kind enum for it (+ directive) -- 3 file(s), area src/ledger -- source: harness-factory: git log main b1f7d2d3
- 00:48Z commit f32092ab [harness-factory] Fix direction-capture truncating on ordinary word-wrap -- 2 file(s), area src/ledger -- source: harness-factory: git log main f32092ab

#### src/lugTracking

- 02:22Z commit 86721a30 [harness-factory] Amend the done gate: pre-instance markers are exempted narrowly, nothing else is (260828-FBL-011) -- fixtures 31/31 -- 5 file(s), area src/lugTracking -- source: harness-factory: git log main 86721a30
- 00:48Z commit d667a113 [harness-factory] Add the real Track/Handoff artifact system (session-track-write, session-end-handoff circles) -- 15 file(s), area src/lugTracking -- source: harness-factory: git log main d667a113

#### .claude

- 00:49Z commit e1e84cc7 [harness-factory] Commit the standing self-instance .claude/settings.json (260828-FBL-009) -- 2 file(s), area .claude -- source: harness-factory: git log main e1e84cc7

#### canon

- 00:48Z commit 40d3f282 [harness-factory] Register harness-factory's own identity (FBL-005 self-instance) -- 3 file(s), area canon -- source: harness-factory: git log main 40d3f282

#### conformance

- 00:49Z commit 3f671fb4 [harness-factory] Wire all new conformance suites into the npm test aggregator -- 3 file(s), area conformance -- source: harness-factory: git log main 3f671fb4

#### scripts

- 00:48Z commit f9b70483 [harness-factory] Add minder shadow-window tooling (identity, baseline, dry-run, --latest check, bounded AP loop) -- 6 file(s), area scripts -- source: harness-factory: git log main f9b70483

#### src/basher

- 00:48Z commit a29de1f5 [harness-factory] Add 1Password-backed secrets loading (docs/SECRETS_V2.md, src/basher/onePassword.js) -- 4 file(s), area src/basher -- source: harness-factory: git log main a29de1f5

#### src/compiler

- 00:48Z commit a0543569 [harness-factory] Adopt the PROMPT-ID protocol (FBL-001..260828-FBL-010) and compile-self --standing -- 10 file(s), area src/compiler -- source: harness-factory: git log main a0543569

#### src/conductor

- 00:48Z commit 7b3cafc5 [harness-factory] Add owned-vs-rented routing and Diakon integration (Part C) -- 16 file(s), area src/conductor -- source: harness-factory: git log main 7b3cafc5

#### src/navigator

- 00:49Z commit 11ddf9dd [harness-factory] Surface ownership/control/lane fields on Navigator cut nodes -- 1 file(s), area src/navigator -- source: harness-factory: git log main 11ddf9dd

#### src/otto

- 01:13Z commit ff462c91 [harness-factory] Implement the reconcile-advisor-roster circle (lugs/advisor-roster-reconciliation, real Otto backlog work) -- fixtures 17/17, 16/16, 2/2 -- 5 file(s), area src/otto -- source: harness-factory: git log main ff462c91

### 2026-08-27

#### src/compiler

- 09:08Z commit 8704485b [harness-factory] Two rulings before increments 7-11: rule 12 measures the wrong set, cut rollback pins previous SHA -- fixtures 26/26, 37/37 -- 17 file(s), area src/compiler -- source: harness-factory: git log main 8704485b
- 08:16Z commit 7f9e5206 [harness-factory] Phase 2 report: all six exit tests PASS, with a live counter-metric firing mid-report -- 9 file(s), area src/compiler -- source: harness-factory: git log main 7f9e5206
- 08:03Z commit 41ec8d3b [harness-factory] Phase 2, Part A: sharable bootstrap (wcl init), shipping-artifact scan -- fixtures 28/28, 11/11 -- 16 file(s), area src/compiler -- source: harness-factory: git log main 41ec8d3b
- 07:51Z commit cd550562 [harness-factory] Phase 1 stop: rule 11 extension coverage, rule 12 counter-metric, JUDGMENT resolutions -- fixtures 26/26, 18/18, 12/12 -- 24 file(s), area src/compiler -- source: harness-factory: git log main cd550562
- 07:25Z commit 2feeb92c [harness-factory] Part C exit test: rules 11/12 re-derived from a real measured wakeup -- fixtures 11/12 -- 7 file(s), area src/compiler -- source: harness-factory: git log main 2feeb92c
- 06:25Z commit 3dce507b [harness-factory] Pre-Part-C items 3+4: ledger slice policy in canon, close the ready-skip bug -- 40 file(s), area src/compiler -- source: harness-factory: git log main 3dce507b
- 05:20Z commit 83f0c6d0 [harness-factory] Fix rule 12: sum the ledger SLICE (design doc section 7), not the whole file forever -- caught live when it refused wheel-hub's own compile -- 3 file(s), area src/compiler -- source: harness-factory: git log main 83f0c6d0
- 04:31Z commit 7a1aabd5 [harness-factory] Phase 1 Part A: context load audit (docs/CONTEXT_LOAD.md) -- fixtures 24/24, 51/51 -- 39 file(s), area src/compiler -- source: harness-factory: git log main 7a1aabd5

#### circles

- 17:26Z circle cartographer added at 2945106d -- source: harness-factory: git log --diff-filter=A 2945106d -- reference/circles/cartographer.yaml
- 10:29Z circle wheel-scheduler added at 87f364b7 -- source: harness-factory: git log --diff-filter=A 87f364b7 -- reference/circles/wheel-scheduler.yaml
- 07:17Z circle warmup-goals-review added at 5937062f -- source: harness-factory: git log --diff-filter=A 5937062f -- reference/circles/warmup-goals-review.yaml
- 05:14Z circle session-continuity-checkpoint added at 786df11d -- source: harness-factory: git log --diff-filter=A 786df11d -- reference/circles/session-continuity-checkpoint.yaml
- 04:00Z circle bash-lug-guard added at f927b4ae -- source: harness-factory: git log --diff-filter=A f927b4ae -- reference/circles/bash-lug-guard.yaml
- 04:00Z circle lug-integrity-checksum added at f927b4ae -- source: harness-factory: git log --diff-filter=A f927b4ae -- reference/circles/lug-integrity-checksum.yaml
- 04:00Z circle lug-kernel-verb added at f927b4ae -- source: harness-factory: git log --diff-filter=A f927b4ae -- reference/circles/lug-kernel-verb.yaml

#### src/advisor

- 10:29Z commit 87f364b7 [harness-factory] Increment 8: Conductor cloud-only disclosure + real wheel-scheduler circle -- 10 file(s), area src/advisor -- source: harness-factory: git log main 87f364b7
- 10:13Z commit 55b7872c [harness-factory] Ruling 1: gate advisor improvement cycles on real measured consumption -- 7 file(s), area src/advisor -- source: harness-factory: git log main 55b7872c
- 10:03Z commit 9cc09f01 [harness-factory] Second-provider credentials: secrets layer, OpenAI-compatible adapters, Proofer suppression -- fixtures 30/30, 9/9 -- 17 file(s), area src/advisor -- source: harness-factory: git log main 9cc09f01
- 09:27Z commit e65b7b3f [harness-factory] Increment 7: real Proofer, provider contract, advisor rotation, improvement cycle -- fixtures 21/21, 25/25, 17/17, 19/19 -- 12 file(s), area src/advisor -- source: harness-factory: git log main e65b7b3f

#### src/hooks

- 19:49Z commit c4753a43 [harness-factory] Increment 9: TasteGraph overlay merge, autonomy table with real proposals -- 5 file(s), area src/hooks -- source: harness-factory: git log main c4753a43
- 05:14Z commit 786df11d [harness-factory] Phase 1 Part B: time to productive turn (docs/TTPT.md) -- fixtures 16/16, 23/23, 1/2, 4/6 -- 11 file(s), area src/hooks -- source: harness-factory: git log main 786df11d
- 04:18Z commit e34c322e [harness-factory] Pre-flight (reconciled-gate work order): fix bash-lug-guard false positives -- fixtures 17/17 -- 3 file(s), area src/hooks -- source: harness-factory: git log main e34c322e
- 04:00Z commit f927b4ae [harness-factory] Close increments 2 and 6 live; kernel verb + Bash-bypass fix; two real bugs -- fixtures 23/23, 25/25 -- 38 file(s), area src/hooks -- source: harness-factory: git log main f927b4ae

#### docs

- 10:31Z commit 62dfb9fc [harness-factory] Increment 8 stop report -- 1 file(s), area docs -- source: harness-factory: git log main 62dfb9fc
- 10:16Z commit 3c2209a5 [harness-factory] Third live second-provider Proofer run, now that credentials exist -- 2 file(s), area docs -- source: harness-factory: git log main 3c2209a5
- 09:29Z commit 587bfbb0 [harness-factory] Increment 7 stop report -- 1 file(s), area docs -- source: harness-factory: git log main 587bfbb0

#### src/conductor

- 17:54Z commit ef629b8d [harness-factory] Part D: warmup that earns its tokens -- fixtures 1/5, 3/5 -- 5 file(s), area src/conductor -- source: harness-factory: git log main ef629b8d
- 07:17Z commit 5937062f [harness-factory] Part C: Navigator, Conductor, ready-work automation, C4 goals review -- fixtures 18/18 -- 8 file(s), area src/conductor -- source: harness-factory: git log main 5937062f

#### src/factory

- 08:11Z commit 01267fa1 [harness-factory] Phase 2, Part C: contribution back (Message shape + evidence requirements only) -- fixtures 13/13 -- 3 file(s), area src/factory -- source: harness-factory: git log main 01267fa1
- 08:09Z commit 9b8407ba [harness-factory] Phase 2, Part B: self-update (distribution, safe apply, migration, fleet truth) -- fixtures 31/31 -- 6 file(s), area src/factory -- source: harness-factory: git log main 9b8407ba

#### src/identity

- 19:40Z commit 86ec6a52 [harness-factory] Ruling: the triple is stamped by writers, not callers -- 30 file(s), area src/identity -- source: harness-factory: git log main 86ec6a52
- 19:16Z commit 14d93fc7 [harness-factory] Identity and Environment Registry, deployment as a contract -- 18 file(s), area src/identity -- source: harness-factory: git log main 14d93fc7

#### .claude

- 04:02Z commit 69213b0a [harness-factory] IDEAS.md: bash-lug-guard weaknesses confirmed against this session itself -- 2 file(s), area .claude -- source: harness-factory: git log main 69213b0a

#### canon

- 04:55Z commit f670aee2 [harness-factory] Task 1: mark admission rules 11 and 12 provisional in canon -- 3 file(s), area canon -- source: harness-factory: git log main f670aee2

#### conformance

- 04:59Z commit 3ac82227 [harness-factory] Task 4: recompile-and-diff check for both repos, wired into npm test -- 4 file(s), area conformance -- source: harness-factory: git log main 3ac82227

#### fixtures

- 06:40Z commit 1ae5140a [harness-factory] Freeze the B4 controlled re-run fixture -- 36 file(s), area fixtures -- source: harness-factory: git log main 1ae5140a

#### src

- 04:54Z commit 5c9739ab [harness-factory] Task 6: compile-self cannot leave the builder's own session hooked -- fixtures 16/16 -- 5 file(s), area src -- source: harness-factory: git log main 5c9739ab

#### src/assayer

- 17:37Z commit b14cf494 [harness-factory] Part B + the Assayer: QA advisor that makes test coverage predictable -- 9 file(s), area src/assayer -- source: harness-factory: git log main b14cf494

#### src/basher

- 06:34Z commit 3ff981be [harness-factory] C0: wcl, basher v2's first verb -- fixtures 7/7 -- 7 file(s), area src/basher -- source: harness-factory: git log main 3ff981be

#### src/cartographer

- 17:26Z commit 2945106d [harness-factory] Part A: Cartographer -- Ozi understands the spoke -- fixtures 14/14, 13/13, 10/10 -- 9 file(s), area src/cartographer -- source: harness-factory: git log main 2945106d

#### src/intake

- 21:37Z commit 97dd44ac [harness-factory] Intake Protocol taxonomy: the protocol's output is the lug -- 8 file(s), area src/intake -- source: harness-factory: git log main 97dd44ac

#### src/ledger

- 04:48Z commit 638217f5 [harness-factory] Task 2 (scope exception, done first): capture-direction stores the directive sentence, not the whole prompt -- fixtures 18/18, 7/7 -- 9 file(s), area src/ledger -- source: harness-factory: git log main 638217f5

#### src/lugTracking

- 07:08Z commit 9dc29e24 [harness-factory] Controlled B4 re-run: authoritative checkpoint framing, four cycles -- 45 file(s), area src/lugTracking -- source: harness-factory: git log main 9dc29e24

#### src/navigator

- 17:59Z commit 7227b968 [harness-factory] Diakon onboarding: real probe, real DNS failure, a real registry gate fix -- 3 file(s), area src/navigator -- source: harness-factory: git log main 7227b968

#### src/observability

- 17:43Z commit 4683e1c7 [harness-factory] Part C: base observability, then a real paths-worth-tracking analysis -- 7 file(s), area src/observability -- source: harness-factory: git log main 4683e1c7

### 2026-08-26

#### circles

- 20:54Z circle session-start-warmup added at 00f46bbe -- source: harness-factory: git log --diff-filter=A 00f46bbe -- reference/circles/session-start-warmup.yaml
- 19:38Z circle definition-complete-gate added at 1082d7c7 -- source: harness-factory: git log --diff-filter=A 1082d7c7 -- reference/circles/definition-complete-gate.yaml
- 19:38Z circle ready-gate-stub added at 1082d7c7 -- source: harness-factory: git log --diff-filter=A 1082d7c7 -- reference/circles/ready-gate-stub.yaml
- 09:56Z circle lug-lifecycle-tracker added at 4927112b -- source: harness-factory: git log --diff-filter=A 4927112b -- reference/circles/lug-lifecycle-tracker.yaml
- 09:56Z circle stop-turn-marker added at 4927112b -- source: harness-factory: git log --diff-filter=A 4927112b -- reference/circles/stop-turn-marker.yaml
- 09:56Z circle test-lug-traceability added at 4927112b -- source: harness-factory: git log --diff-filter=A 4927112b -- reference/circles/test-lug-traceability.yaml
- 09:49Z circle capture-direction added at bd2ddd3d -- source: harness-factory: git log --diff-filter=A bd2ddd3d -- reference/circles/capture-direction.yaml
- 09:49Z circle reconcile-ledger added at bd2ddd3d -- source: harness-factory: git log --diff-filter=A bd2ddd3d -- reference/circles/reconcile-ledger.yaml
- 09:45Z circle readiness-gate added at 03e7212a -- source: harness-factory: git log --diff-filter=A 03e7212a -- reference/circles/readiness-gate.yaml

#### src/hooks

- 20:54Z commit 00f46bbe [harness-factory] Live-hook-test infrastructure: capture wrapper, SessionStart warmup canary, self-compile, and a real hook_script resolution fix -- 15 file(s), area src/hooks -- source: harness-factory: git log main 00f46bbe
- 19:38Z commit 1082d7c7 [harness-factory] Rulings 2026-08-26: split definition-complete from a stubbed ready gate, honest cost measurement, counter-metrics, hook_script resolution -- 39 file(s), area src/hooks -- source: harness-factory: git log main 1082d7c7
- 09:56Z commit 4927112b [harness-factory] Increment 6: lug lifecycle traceability and cost -- 17 file(s), area src/hooks -- source: harness-factory: git log main 4927112b

#### docs

- 21:13Z commit 019a15dc [harness-factory] Live hook test: real evidence for increments 2, 3, 6 via real headless sessions -- fixtures 12/12, 14/14 -- 15 file(s), area docs -- source: harness-factory: git log main 019a15dc
- 19:41Z commit 0897c368 [harness-factory] Update exit-test evidence table for the readiness-gate split and wheel-hub scaffold -- 1 file(s), area docs -- source: harness-factory: git log main 0897c368

#### src/compiler

- 09:45Z commit 03e7212a [harness-factory] Increment 2: one circle end to end (readiness-gate) -- 21 file(s), area src/compiler -- source: harness-factory: git log main 03e7212a
- 09:39Z commit 23dc5f6e [harness-factory] Increment 1: schemas, compiler, conformance runner -- 65 file(s), area src/compiler -- source: harness-factory: git log main 23dc5f6e

#### src/factory

- 09:51Z commit e64e4971 [harness-factory] Increment 5: factory greenfield (interview, scaffold, bootstrap) -- 7 file(s), area src/factory -- source: harness-factory: git log main e64e4971

#### src/ledger

- 09:49Z commit bd2ddd3d [harness-factory] Increment 3: the ledger (capture-direction, reconcile-ledger) -- 10 file(s), area src/ledger -- source: harness-factory: git log main bd2ddd3d

<!-- integrity sha256:1fd6078e1d834ec4569059a78fd12a9a428109e03a63a89abbb2fdf1edd984f1 -->
