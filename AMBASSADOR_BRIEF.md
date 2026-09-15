# Ambassador Brief (generated -- never hand-edit; regenerated on every real cut)

This is what any agent needs to become a competent partner to this spoke
from one wakeup, with no hand-fed context (the Ambassador property,
260901-FBL-063; see canon/glossary.md -- not on this spoke, and no registered hub has it either; see .local/known-repos.json). Never hand-written -- compiled
from canon only. A pointer to this file is what's actually injected at
wakeup, per the generated CLAUDE.md; the full brief is one read away.

## 1. What this spoke is

tracks -- Tracks -- structured records of AI conversations (WAI Points in JSONL); an existing v1 WAI-Harness spoke (cut 4.14.58) onboarded to the v2 harness on 2026-09-14

## 2. Its toolbox

83 live circle(s):
- **agent-target-scope-guard** (hook_event): a Write, Edit, NotebookEdit or Bash call is about to run from inside a dispatched Agent-tool fork
- **agent-tool-scope-guard** (hook_event): an Agent-tool call is about to run, or a dispatched fork reaches for a write
- **anthropic-rate-limit-five-hour-envelope** (on_demand): a caller asks for the account's real five-hour rate-limit headroom -- detectWindowStart on every wave decision and every heartbeat tick (measureAnthropicRateLimitUsage), or a caller running enforceAnthropicRateLimitEnvelope to write the measured value back onto the Envelope row
- **bash-destructive-command-guard** (hook_event): a Bash command is about to run
- **bash-lug-guard** (hook_event): a Bash command is about to run
- **calibration-record** (on_demand): an operator or agent asks what a named heuristic's real error rate is
- **capture-direction** (hook_event): user submits a prompt containing a standing-rule marker phrase
- **cartographer** (schedule): the wheel-scheduler's cartographer_map job, on its declared cadence
- **cartographer-commit-trigger** (hook_event): a real git commit lands in harness-factory (PostToolUse, Bash matching git commit)
- **chain-disposition** (on_demand): an operator or third-party session asks for a chain's verdict -- `node scripts/chain-disposition.js <chain-id> [--write --session-id=<id>]`
- **circle-completeness-audit** (hook_event): a real session starts (SessionStart event)
- **communication-inbox** (schedule): a session starts -- every SessionStart composes the goals review (buildGoalsReviewInjectionParts, src/conductor/goalsReview.js), which reads the inbox live and prints the one digest line, and the SessionStart wheel-clock catch-up fires the job when a tick is owed -- and the spoke's wheel_clock job communication_inbox (JOB_RUNNERS.communicationInbox) on its declared cadence, for the out-of-session loop: the spoke reads every sibling spoke's lugs/ for type: communication lugs whose target_spoke names it and whose status is still open (not fulfilled / declined / closed), ranks them through rankCommunicationInbox (src/conductor/readyWork.js, the ONE ordering the ready-work queue, the senior inbox and the advisor inbox all call), and writes only its own runtime/communication-inbox.json
- **communication-inbox-delta** (hook_event): a real prompt is submitted (UserPromptSubmit), and the hub's messages/messages.jsonl or lugs/ holds a row addressed to this spoke that this session's cursor has not shown
- **conductor-harness-factory-leverage-routing** (on_demand): buildReadyWorkQueue (src/conductor/readyWork.js) is called to rank the ready-work queue -- every real caller: goalsReview.js, warmup.js, conductor.js's planRouting, waveDecision.js's candidate-pool build, factory/positionMap.js, lugTracking/handoff.js
- **conductor-heartbeat** (on_demand): scripts/conductor-heartbeat.mjs is run from outside any Claude Code session -- the out-of-session supervisor tick, which is the one caller awake when a five-hour window opens with nobody at the machine. As of 260908 this is no longer a proposal: it is really installed in the operator's crontab as `*/10 * * * * ... node scripts/conductor-heartbeat.mjs --hub-root .../wheel-hub --poll --launch`, i.e. WITH the launch arm engaged, in the same minute as a second `*/10` entry running a bare runWheelClockCatchup(wheel-hub) -- see the conductor-window-boundary-claim circle for how those two are kept from acting on one boundary together
- **conductor-wave-gate** (on_demand): a real caller asks whether a five-hour window just started and whether to spend it -- src/otto/advisorAutopilot.js runAdvisorAutopilot in session (on the advisor_activation wheel-clock job), or scripts/conductor-heartbeat.mjs out of session; the repeat arm is reviewWaveAndDecideRepeat after a wave closes
- **conductor-window-boundary-claim** (on_demand): a cron-driven process is about to act on a detected five-hour window boundary -- scripts/conductor-heartbeat.mjs --launch, or the wheel clock's advisor_activation job (runAdvisorAutopilot) reaching a decideWave LAUNCH. Both are installed as separate */10 crontab entries that fire in the same minute, so both really can reach the same boundary together.
- **cross-provider-certification-history** (on_demand): a cross-provider certification record is written or read -- every writeCertificationRecord (src/advisor/crossProviderVerification.js) from the chain (crossProviderCertify.js, every attempt), the requirement note, the verb's supersession block; readCertificationHistory on demand (node scripts/certification-history.js <lug> [--run=<n>] | --migrate | --summary); and summarizeExternalChain at session start
- **cross-provider-verification** (hook_event): a lug transitions into review with priority high or critical AND proof_required: true
- **cross-store-finding-coalescing** (on_demand): a systemic finding is recorded into any of the wheel's three durable stores -- the wheel-clock cross_store_reconciliation job coalescing its disagreements by cause (runCrossStoreReconciliation), every ledger append passing through appendRow, every Stop rebuilding a track's decisions projection (writeOrUpdateTrack), and every automatic P0 lug filing (openP0BugFixLug)
- **default-forward-veto-ledger** (on_demand): a default-forward act is about to happen -- today, a dispatch queued or executed with no human at the keyboard
- **definition-complete-gate** (hook_event): a lug's state field is edited to defined (or beyond)
- **design-salvage-review** (on_demand): an operator or agent runs a salvage pass over work at risk of falling onto the cutting floor
- **dispatch-run-salvage** (on_demand): a real dispatched session runs -- the launch supervisor journals its child's stream to disk for the child's whole life (src/basher/idleWatchdog.js main(), from the first chunk, before any kill can happen), and executeDispatch (src/lugTracking/dispatchMechanism.js) builds the run's work disposition when the launcher returns, on every terminal outcome and not only on completions
- **done-gate-two-store-certification** (on_demand): a qualifying lug (high/critical AND proof_required) transitions into done -- checkCrossProviderGateForDone (src/advisor/crossProviderVerification.js) at the kernel verb, and the drive's promote_to_done (src/conductor/initiativeFocus.js) for a lug at review OR at ready with readiness passed; and at session start, where buildExternalChainSection reports the external chain's failure modes with counts
- **falsifiability-gate** (on_demand): an operator or agent asks whether a verify command CAN fail, before trusting that it passed
- **farming** (on_demand): a solution recurring across spokes is detected, abstracted, promoted or demoted -- detectRecurrence / proposePromotion / proposeDemotion / certifyHarvest / applyHarvest / auditPromotions (src/otto/farming.js), run by `node scripts/farming.js detect|propose|demote|certify|apply|audit`; and every session start, where buildFarmSection reports through goalsReview.js
- **footer-audit** (hook_event): a turn ends (Stop event)
- **footer-correction-injection** (hook_event): a real prompt is submitted, following a turn footer-audit flagged as missed
- **gate-pool-serial-suites** (on_demand): the commit or push gate runs its suites through the pool (src/factory/testBoundaryGate.js runSuites -> src/factory/suitePool.js runSuitePool): every suite whose head carries `// serial` runs alone before the pool opens and the gate's first report line names them and the pool size; and when the two timing suites (liveness-lease, launch-idle-watchdog) start, they measure the box (src/factory/boxTiming.js) and derive their windows from it before the first supervised child
- **git-boundary-test-gate** (on_demand): a real `git commit` or `git push` runs in harness-factory or wheel-hub
- **global-settings-drift-check** (hook_event): a real session starts
- **guard-denial-reconciliation** (schedule): wheel_clock job guard_denial_reconciliation (canon/otto.advisor.yaml)
- **headless-usage-reading** (on_demand): scripts/headless-usage-poll.mjs is run (no session, no statusline, no TTY), or scripts/conductor-heartbeat.mjs is run with --poll, which calls pollHeadlessUsage before deciding
- **hf-deploy** (on_demand): the orchestrating (non-authoring) session runs `hf deploy [--spokes a,b] [--stage fold,push,cut,relaunch,clean]` (src/factory/deploy.js runDeployCommand) to take the fleet's finished work to every registered spoke; or the hub wheel clock's deploy_fleet job (runScheduledDeploy) finds main proven green with foldable branches or commits ahead of origin and launches fold+push+cut detached
- **hook-binding-drift** (hook_event): a real session starts
- **hook-invocation-runlog** (on_demand): every hook invocation in this build -- makeCapture (src/hooks/lib/hookIO.js) records the invocation's duration and outcome on its way out, whether the hook exited cleanly, exited non-zero, threw, or never reached its own exit path at all; and again when a session start or warmup composes the operator surface from the recorded rows
- **initiative-focus** (on_demand): an initiative is read, ranked or driven -- every session start (buildInitiativeFocusSection through goalsReview.js), every Planner cycle (initiativeLugIndex + rankByInitiativePrecedence in src/planner/planner.js), and every autopilot launch (driveApReadyInitiatives from runAdvisorAutopilot, src/otto/advisorAutopilot.js) -- src/conductor/initiativeFocus.js
- **live-apply-announce** (hook_event): a prompt is submitted (UserPromptSubmit event)
- **liveness-lease** (on_demand): a supervised dispatched session runs -- the running session calls the one sanctioned refresh (refreshLivenessLease / leaseForStep, src/lugTracking/livenessLease.js, or `node scripts/liveness-lease.js refresh`) before any step longer than its remaining countdown, and the launch supervisor (src/basher/idleWatchdog.js) reads the lease off the lug on every tick of the child's life
- **lug-edges** (on_demand): a lug's edges are written or read -- every applyLugVerb transition runs checkLugEdges (src/lugTracking/lugEdges.js) at the one sanctioned mutation path; `node scripts/lug-edges.js up|down|verifications|chain|relates|audit` reads them on demand; and the two pre-existing consumers of the fields, chainDisposition.resolveChain and pickupReverification.dependencyRefs, now import the shared normalizer instead of re-reading derived_from
- **lug-integrity-checksum** (hook_event): a turn ends (Stop event)
- **lug-kernel-verb** (on_demand): an operator or agent runs the verb to change a lug's state
- **lug-lifecycle-tracker** (hook_event): a lug's state field is edited to in_progress or done
- **lug-ownership-claims** (on_demand): a lug's ownership is claimed, contested or diverged -- applyLugVerb (src/lugTracking/lugVerb.js) appends a claim at in_progress and a release at review/done, refusing a lug another LIVE session holds unless --drive=<reason> or --collaborate=<sub-scope>; `node scripts/lug-claim.js list|contend|release` reads the table on demand; the four lug-write guards (bash-lug-guard, definition-complete-gate, ready-gate-stub, lug-lifecycle-tracker) refuse a write to another live session's claimed lug through src/hooks/lib/claimGuard.js; the session-end handoff releases what the ending session held; lugIntegrity.classifyViolation, a dirty-file takeover or `node scripts/lug-divergence.js resolve` write or settle runtime/divergences/<id>.json
- **lug-type-lifecycles** (on_demand): a lug's type-specific lifecycle is consulted -- every applyLugVerb transition reads statesForLug (src/lugTracking/lugType.js) at the one sanctioned mutation path; every schema validation of a lug applies the per-type state enum in schemas/lug.schema.json; and the lug-integrity-checksum heal reads resetStateForLug to pick the entry state of the lug's OWN lifecycle
- **max-persona-boundary-guard** (hook_event): a Write, Edit or NotebookEdit call is about to run from the top-level (non-dispatched) session
- **notification-agent-waiting-notify** (hook_event): Claude Code sends a real permission_prompt or idle_prompt notification
- **orphan-dispatch-disposition** (on_demand): an orphaned dispatch row is re-reconciled against the real evidence its child left on disk -- `node scripts/orphan-disposition.js <instanceRoot>` runs the sweep on demand, and every session start reports the standing result once through goalsReview.js's buildOrphanDispositionSection
- **oversized-canon-write-guard** (hook_event): a Write or Edit call is about to run against a canon entity file or a circle/advisor instructions doc, in any session -- top-level or dispatched
- **pattern-language** (on_demand): a pattern, spoke, group or the wheel is described in the common language -- declarePattern (src/otto/approachPatterns.js) running the value/lift/variant/correction gates at the library's write; describeSpoke/composeView (src/otto/patternLanguage.js) run by `node scripts/pattern-language.js describe|describe-all|view`; and `pattern-language.js vocabulary` tracing every glossary term to disk
- **pickup-time-reverification** (on_demand): work is picked up -- a lug transitions into in_progress, or a dispatch is queued for it
- **planner-cross-segment-ranking** (schedule): every wheel_clock planner_cycle job -- runPlannerCycle -> buildPlannerCycle -> rankCrossSegment (src/planner/planner.js), reading canon/initiatives/ live on each cycle
- **planner-cycle-allocation** (schedule): wheel_clock job planner_cycle (canon/otto.advisor.yaml), declared FIRST so it fires before every other scheduled job
- **precompact-checkpoint** (hook_event): a real context compaction is about to happen (PreCompact event, manual or auto)
- **provider-usage-and-retry** (on_demand): any provider call is made through src/advisor/providerContract.js's callProvider -- every caller: proofer.js (the cross-provider certification path), machineProbe.js, and any script or fixture that calls it directly
- **readiness-certification-sweep** (on_demand): the review-state backlog is swept for real check results -- `node scripts/readiness-sweep.js [instanceRoot] --session-id=<id> [--certify=none|request|run]` walks every review lug and every ready+passed lug in scope (critical first, then the lugs that unblock the most others; --priorities widens), re-runs each lug's own conformance fixture, reads the done gate through the harness's own functions, and asks the kernel verb for done
- **ready-gate-stub** (hook_event): a lug's state field is edited to ready
- **reconcile-ledger** (schedule): wheel_clock job ledger_reconciliation (canon/otto.advisor.yaml)
- **rule-12-live-state-report** (on_demand): a compile runs against a spoke with lugs (run + warn in src/compiler/rules/12-no-oversized-session-start.js, measured once per compile via ctx.sessionStartMeasurement) -- `hf compile`, `wcl compile`, the commit and push gates, wcl's stale-instance step, applyCut's scratch and real recompiles; and on demand when an operator or session runs `node scripts/acknowledge-live-state.js` to shrink the live-state backlog the warning names
- **run-roi-extraction** (on_demand): every autopilot run ENDS here -- finishAutopilotRun (src/conductor/roiExtraction.js) is reached from runAdvisorAutopilot's close path (launch, decline, and its abnormal-end guard alike), from src/conductor/heartbeat.js finish() on an out-of-session no-launch, and from scripts/conductor-heartbeat.mjs's launch arm in its own `finally`; and as the reconciliation sweep over waves opened and never closed -- the wheel-clock open_wave_reconciliation job on its cadence, or scripts/reconcile-open-waves.js on demand
- **scheduler-failure-operator-channel** (on_demand): a wheel_clock job fails on consecutive ticks (evaluated at the end of every real tickWheelScheduler run), and again when a session start composes the goals review
- **secrets-template-migration** (on_demand): a spoke's .env.template meets the secrets manifest -- `wcl <spoke>` step 5 on a spoke with a template and no canon/secrets.manifest.yaml (runSecretsMigrationStep, src/basher/wclCli.js); `node scripts/secrets.js migrate|fallbacks|retirement|show [<spoke>]` on demand; getSecret's cache miss (src/basher/secrets.js, the dual-read); and every applyCut (src/factory/cutUpdate.js), where the measured retirement runs
- **session-continuity-checkpoint** (hook_event): a session starts
- **session-end-handoff** (hook_event): a real session ends (SessionEnd event)
- **session-end-notify** (hook_event): a real session ends
- **session-exit-commit** (hook_event): a real session ends (SessionEnd event), after the handoff is written and the track closed
- **session-registry** (hook_event): a session starts (SessionStart event)
- **session-start-warmup** (hook_event): a session starts
- **session-track-write** (hook_event): a turn ends (Stop event)
- **stop-agent-waiting-notify** (hook_event): a real turn completes -- Claude stopped and is waiting
- **stop-turn-marker** (hook_event): a turn ends (Stop event)
- **success-prediction** (on_demand): a success prediction is registered, superseded or reviewed -- registerPrediction / supersedePrediction / reviewPrediction / reviewDuePredictions (src/conductor/successPrediction.js), via scripts/success-prediction.js on demand; and every session start, where buildSuccessPredictionSection reports verdict counts through goalsReview.js
- **tastegraph-injection** (hook_event): a real prompt is submitted (UserPromptSubmit), after the wakeup block handed the session the merged tastegraph and a master or overlay change has landed since
- **temporary-limit-boost-awareness** (on_demand): a caller asks whether a temporary rate-limit boost is currently active on this account -- every conductor heartbeat tick (detectLimitBoost + boostExpiryAlert), every paceFromReading given a boost fact, and every headless usage poll's own operator-facing output
- **test-lug-traceability** (hook_event): a new test file is written
- **turn-start-attribution** (hook_event): a real prompt is submitted
- **unattended-run-kill-switch** (on_demand): any caller is about to spend, or is already spending, the operator's subscription with nobody at the machine -- checked at every launch gate (executeDispatch, runHeartbeat Gate 0, runAdvisorAutopilot Gate 0) and POLLED by every launch supervisor for the whole life of its child. Raised with `hf stop` or, with no node required, `touch <instance-root>/runtime/stop.flag`.
- **update-discovery** (hook_event): a real session starts (SessionStart event) in any spoke that receives cuts, and the spoke's wheel_clock job update_discovery (JOB_RUNNERS.updateDiscovery) on its declared cadence -- the spoke compares its .cut-status.json to the hub's registry/latest-cut.json, published by hf deploy's cut stage (src/factory/cutPublish.js, from stageCut); Otto's autopilot records who is behind (src/otto/cutLaggards.js) and the hub goals review prints it
- **warmup-goals-review** (hook_event): a session starts
- **wcl-verify-then-launch** (on_demand): the operator runs `wcl <spoke>`
- **wheel-clock-catchup** (hook_event): a real session starts (SessionStart event)
- **worktree-registry** (on_demand): a git worktree is created, removed, judged or handed off by the harness -- addWorktree/removeWorktree (src/factory/worktreeRegistry.js) at every `git worktree add` in src/ (rollbackCut's pinned checkout, hf deploy's fold integrate tree, stageClean's removals); `node scripts/worktree.js add|list|remove|reap` by the orchestrating session in place of raw git; healthSignals.js's stale_worktree signal on every Planner cycle; and buildHandoff at every session end

0 advisor(s):
- none declared

0 intake protocol(s): none

0 live policy/policies -- see the generated CLAUDE.md's "Live policies" section for the current list.

## 3. How the wheel works around it

Hub: wheel-hub (registries, cuts, priority policy, ledger). Cuts: this
spoke absorbs a real cut per its own declared posture -- see
`autonomy_table_defaults.upgrade_absorption`: `absorb_and_report`.
Autonomy table (what this spoke may do alone, here):
- `lug_execution`: `"auto_with_notify"`
- `dependency_changes`: `"review"`
- `external_contact`: `"review"`
- `upgrade_absorption`: `"absorb_and_report"`

## 4. Where to ask for centralized knowledge

Otto's KB (`kb/` at the hub root) and the Custodian's index (phase d,
not yet built). Until then: the ledger (`ledger/ledger.jsonl`) and this
spoke's own canon/ are the authoritative record -- run the compiler
(`wcl compile .`) for current live state.
(This spoke adopts the harness rather than hosting it, so it has no
`src/cli.js` of its own. `wcl` is basher's installed launcher; it
resolves the real harness-factory checkout itself, so no absolute
path to one is baked into this generated text.)

## 5. How to send feedback upward

Insight push (a fire-and-forget Message after each Wilbur checkpoint,
kind: insight), ledger practice rows, and the Signal -> Teaching
pipeline -- never a direct, unreviewed canon edit. See
canon/glossary.md -- not on this spoke, and no registered hub has it either; see .local/known-repos.json's **Insight push** entry.

## 6. How to optimize its own performance

Counter-metrics on circles/policies/transitions, reviewed in the
improve phase; cost and outcome per lug are real ledger fields
(`cost`, `outcome_at_proofer`), never estimated. The ROI rollup
(`buildRoiRollup`, `src/otto/roiRollup.js`) is real and wired into the
wheel clock's `roiRollup` job. It returns `{ perRepo, totals, movement,
vsV1Baseline }`: done-lug counts and measured cost in tokens per repo,
with unmeasured and quarantined-anomaly counts kept separate rather
than zero-substituted; movement since the previous rollup; and a
comparison against the real v1 baseline (per-lug cost measurable,
percent of lugs traceable to a test).

## 7. The footer

Every turn ends with a merged footer, one line, `|`-joined:
`coordinates | localTime | model | frameworkVersion | turnCost-or-"unmeasured" | open: N`
(`formatMergedTurnFooter`, `src/ledger/promptId.js`) -- `coordinates` is
the real id-v3 FROM (never fabricated -- the function throws without
one), `turnCost` is `"unmeasured"` rather than a guessed number when no
real cost was captured, and `open: N` is the real open-item count. The
footer-audit circle checks it fires every turn.

## 8. Preferred approach (disposition)

No tool dispositions declared yet in this spoke's canon.
