# Changelog: tracks

What changed in this project, newest first: every finished work item (lug) and every bug fix that reached main. Each entry says what changed, why it matters, the initiative it serves, how it was proven, and where to look (lug id, commit, files). Generated from .wheel/backlog.jsonl and the main branch's history by `lug render`; do not edit by hand.

## The latest week at a glance (7 days to 2026-11-14)

- 14 changes: 6 new, 3 fixes, 5 upkeep
- I-004 Keep tracks healthy and current: 8
- I-001 Start here: the current prompt, a sample track and a way to check your own: 2
- I-002 The format holds: spec, validator and viewer agree: 2
- I-003 The wheel's own sessions pick up from their last track: 2

## 2026-11-14

### Upkeep · Stop scout runs from dirtying the tree

- **What changed:** untrack and gitignore .wheel/scouts/*/status.json
- **Why it matters:** This is the root cause behind B-008 and B-014 (the same scout break minted twice) and the decision hub triage already made on 2026-11-12 under the owner's standing rule, which no builder applied. It is not owner work. When this lands, B-009 should be closed on it rather than re-asked.
- **Initiative:** I-004 Keep tracks healthy and current
- **Proven by:** the check: `grep -q 'scouts/\*/status.json' .gitignore && test -z "$(git ls-files '.wheel/scouts/*/status.json')"` exits 0, then `python3 .wheel/hooks/scouts.py run worktree-no-uncommitted && test -z "$(git status --porcelain)"`...; what the closer saw (wake-45c344/checker): check passed: I ran each part of the check as a separate command, because chaining isn't allowed. All of them exited 0. (1) `grep -q 'scouts/\*/status.json' .gitignore` matched, so the ignore rule is present. (2) `
- **Find it:** lug B-017 (`lug.py history B-017`) · no commit on main names it yet: the work may sit on a branch, or be outside the code (a decision, a setting)

## 2026-11-12

### Fix · Scout worktree-no-uncommitted broke

- **What changed:** git status shows no changed or untracked files
- **Why it matters:** scout worktree-no-uncommitted failed: c1: 12 line(s), more than 0
- **Initiative:** I-004 Keep tracks healthy and current
- **Proven by:** the check: Running `python3 .wheel/hooks/scouts.py run worktree-no-uncommitted` prints PASS for every check of the scout and exits 0; what the closer saw (wake-2e6a57/checker): check passed: I ran `python3 -B .wheel/hooks/scouts.py run worktree-no-uncommitted`. It printed `PASS worktree-no-uncommitted` and `PASS c1: git status shows no changed or untracked files`. The scout has only one c
- **Find it:** lug B-014 (`lug.py history B-014`) · no commit on main names it yet: the work may sit on a branch, or be outside the code (a decision, a setting)

### Fix · Scout critical-paths-stays-red-until-real broke

- **What changed:** the stub still exits 1 and says it is not implemented
- **Why it matters:** scout critical-paths-stays-red-until-real failed: c1: tests/critical_paths.sh lacks the expected text
- **Initiative:** I-004 Keep tracks healthy and current
- **Proven by:** the check: Running `python3 .wheel/hooks/scouts.py run critical-paths-stays-red-until-real` prints PASS for every check of the scout and exits 0; what the closer saw (wake-2e6a57/checker): check passed: I ran `python3 -B .wheel/hooks/scouts.py run critical-paths-stays-red-until-real`. It printed PASS for the scout and PASS for each of its three checks: c1 (the gate runs the real validator check), c2
- **Find it:** lug B-013 (`lug.py history B-013`) · no commit on main names it yet: the work may sit on a branch, or be outside the code (a decision, a setting)

### Upkeep · Replace the red tests/critical_paths.sh stub with real deterministic tests over the viewer, track validator an

- **Why it matters:** tests/critical_paths.sh prints NOT YET IMPLEMENTED and exits 1; /wai-closeout hard-blocks on it, and the I-004 done_when is unmet
- **Initiative:** I-004 Keep tracks healthy and current
- **Proven by:** the check: bash tests/critical_paths.sh exits 0 and runs at least one real assertion per critical path; what the closer saw (wake-3e8b53/checker): check passed: `bash tests/critical_paths.sh` ran without an error and printed CRITICAL-PATHS: PASS. The script ends with `exit $fail`, and `fail` stays 0 unless a sub-check exits non-zero. I did not read the exit c
- **Find it:** lug B-011 · commits `5b3397e`, `7dc3142` (`git show 5b3397e`) · files: `tests/critical_paths.sh`, `tests/run_all.sh`

### Upkeep · Add one runner that executes every tests/ check and exits non-zero on any failure

- **Why it matters:** tests/ holds five shell and Python checks with no single entry point, and overwatch reports tests as none
- **Initiative:** I-004 Keep tracks healthy and current
- **Proven by:** the check: a single command runs validate_rules.sh, validate_samples.sh, stranded_ideas.sh, wake_from_track.sh and viewer_drop.py and exits 0 on the current tree; what the closer saw (wake-3e8b53/checker): check passed: I ran `bash tests/run_all.sh` on the current tree. It ran all five checks, validate_rules.sh, validate_samples.sh, stranded_ideas.sh, wake_from_track.sh and viewer_drop.py, and each printed PASS. The
- **Find it:** lug B-012 · commit `7dc3142` (`git show 7dc3142`) · files: `tests/run_all.sh`

### Fix · Scout worktree-no-uncommitted broke

- **What changed:** git status shows no changed or untracked files
- **Why it matters:** scout worktree-no-uncommitted failed: c1: 4 line(s), more than 0
- **Initiative:** I-004 Keep tracks healthy and current
- **Proven by:** the check: Running `python3 .wheel/hooks/scouts.py run worktree-no-uncommitted` prints PASS for every check of the scout and exits 0; what the closer saw (wake-3e8b53/checker): check passed: I ran `python3 -B .wheel/hooks/scouts.py run worktree-no-uncommitted` from the check worktree. It printed `PASS worktree-no-uncommitted` and `PASS c1: git status shows no changed or untracked files`.
- **Find it:** lug B-008 (`lug.py history B-008`) · no commit on main names it yet: the work may sit on a branch, or be outside the code (a decision, a setting)

### Upkeep · Decide the fate of .claude/.deploy-quarantine/hooks (9 hook files, not gitignored)

- **Why it matters:** the folder exists and is not in .gitignore; the quarantine name suggests the hooks were set aside but they are still tracked
- **Initiative:** I-004 Keep tracks healthy and current
- **Proven by:** the check: the folder is either removed, or gitignored with a note on why, and git status stays clean; what the closer saw (wake-3e8b53/checker): check passed: `git status --short` printed nothing, so the tree is clean. `git ls-files .claude/.deploy-quarantine` printed nothing, so no file in the folder is tracked, and `ls .claude` shows no such folder in thi
- **Find it:** lug B-010 · commit `e56fa20` (`git show e56fa20`) · files: `.claude/.deploy-quarantine/hooks/flush_buffer.py`, `.claude/.deploy-quarantine/hooks/harness_mode.sh`, `.claude/.deploy-quarantine/hooks/post-tool-use.sh`, `.claude/.deploy-quarantine/hooks/session-start.sh`, `.claude/.deploy-quarantine/hooks/stop-savepoint-guard.sh`, `.claude/.deploy-quarantine/hooks/stop-test-runner.sh` and 4 more

## 2026-11-08

### New · Find stranded ideas in old tracks and offer them as backlog candidates

- **Why it matters:** Goal 2, lower
- **Initiative:** I-003 The wheel's own sessions pick up from their last track
- **Proven by:** the check: a script over sample tracks lists open ideas with their track and line; no writes anywhere; what the closer saw (wake-8f6ad2/checker): check passed: I read tools/stranded_ideas.py. It only opens files in read mode, uses json and sys, and prints to stdout. It sets sys.dont_write_bytecode and has no write, open-for-write, or subprocess calls. Runnin
- **Find it:** lug B-006 · commit `f8289b0` (`git show f8289b0`) · files: `tests/stranded_ideas.sh`, `tools/stranded_ideas.py`

### New · A new session in a project opens from the last session's track

- **Why it matters:** Goal 2: using it ourselves; overlaps the hub's wake-up work, so check with the hub first
- **Initiative:** I-003 The wheel's own sessions pick up from their last track
- **Proven by:** the check: in a test project, a session start prints the last track's open items and decisions; covered by a fixture test; what the closer saw (wake-f95d17/checker): check passed: Running `bash tests/wake_from_track.sh` printed PASS and exited 0. The test pipes a SessionStart payload into `.wheel/hooks/wake_from_track.py` for the fixture project `tests/fixtures/wake`, which has
- **Find it:** lug B-005 · commit `4a06895` (`git show 4a06895`) · files: `tests/fixtures/wake/.wheel/tracks/WAI_Track-20261101-0900-Claude-claude-sonnet-5-5.jsonl`, `tests/fixtures/wake/.wheel/tracks/WAI_Track-20261102-1000-Claude-claude-sonnet-5-5.jsonl`, `tests/wake_from_track.sh`

### New · Format spec and validator agree

- **What changed:** every rule in the spec is checked, every sample passes
- **Why it matters:** Goal 1: model-neutral means the spec, not one tool, defines it
- **Initiative:** I-002 The format holds: spec, validator and viewer agree
- **Proven by:** the check: a test maps each spec rule to a validator check; all samples pass; a broken fixture fails with the rule named; what the closer saw (wake-f95d17/checker): check passed: tests/validate_rules.sh exits 0 and prints 'PASS: 19 spec rules each checked; each broken fixture fails naming its rule; samples pass'. It reads the rule IDs (R01-R19) from spec/track-format.md and re
- **Find it:** lug B-003 · commit `c4ac73f` (`git show c4ac73f`) · files: `spec/track-format.md`, `tests/fixtures/R01-badname.jsonl`, `tests/fixtures/R02-broken.jsonl`, `tests/fixtures/R03-broken.jsonl`, `tests/fixtures/R04-broken.jsonl`, `tests/fixtures/R05-broken.jsonl` and 17 more

### Upkeep · Add a small validator test run that checks every sample against the spec

- **Why it matters:** Overwatch shows tests none and no CI, so the format claim in goal 1 has no automatic check.
- **Initiative:** I-004 Keep tracks healthy and current
- **Proven by:** the check: A single command runs the validator on all samples and exits non-zero on a failure; what the closer saw (wake-f95d17/checker): check passed: Running `bash tests/validate_samples.sh` validated all 4 samples (coding, learning, strategy and v4-session) and printed PASS. The script exits 1 if no samples are found or if the validator fails on a
- **Find it:** lug B-007 · commit `1e79de4` (`git show 1e79de4`) · files: `tests/validate_samples.sh`

### New · Publish v4.0.0 to the library as the latest prompt, marked provisional until track-prompt-lab's bench names a winner

- **Why it matters:** Goal 1: the library should hand out the best prompt we have
- **Initiative:** I-001 Start here: the current prompt, a sample track and a way to check your own
- **Proven by:** the check: The prompt file matches track-prompt-lab's v4.0.0 text, the variants table lists it as latest (provisional, not current), and its sample validates; what the closer saw (wake-f95d17/checker): check passed: prompts/v4.0.0.md has the same SHA-256 as track-prompt-lab/prompts/v4.0.0.md (08734e61…47e990), so the two files are byte-identical. prompts/README.md row 1 lists v4.0.0 as '**latest, provisional**: n
- **Find it:** lug B-002 · commit `b878f60` (`git show b878f60`) · files: `prompts/README.md`, `prompts/v4.0.0.md`, `samples/v4-session.jsonl`

### New · Start here: one page with the recommended prompt, a sample track and how to check your own file

- **Why it matters:** Goal 1: a stranger should get a track in minutes
- **Initiative:** I-001 Start here: the current prompt, a sample track and a way to check your own
- **Proven by:** the check: README opens with the start section; validate_track.py passes on every sample track; the viewer opens the sample; what the closer saw (wake-f95d17/checker): check passed: README.md puts '## Start here' first, after only the title, tagline and badges (lines 11-28). `python3 tools/validate_track.py` printed OK for all three samples: coding-session, learning-session and s
- **Find it:** lug B-001 · commit `a879572` (`git show a879572`) · files: `README.md`, `tools/validate_track.py`

### New · The viewer opens any track file dropped on it, as a static page

- **Why it matters:** Goal 1: reading a track should need nothing installed
- **Initiative:** I-002 The format holds: spec, validator and viewer agree
- **Proven by:** the check: a browser test drops a sample track and sees its turns, decisions and open items; no server needed; what the closer saw (wake-4e0064/checker): check passed: I ran `python3 tests/viewer_drop.py`, which exited 0 and printed: PASS: dropped coding-session.jsonl: 10 turns, 9 decisions, 8 open items shown. The test opens viewer/index.html in headless Chromium f
- **Find it:** lug B-004 · commit `458a4b5` (`git show 458a4b5`) · files: `tests/viewer_drop.py`, `viewer/app.js`, `viewer/index.html`, `viewer/styles.css`

## 2026-07-15

### Fix · fix(wai-exit): replace divergent fork with the canonical thin wrapper

- **What changed:** This spoke ran its own forked copy of wai-exit.sh carrying two verified bugs: 1. SILENT NO-PUSH. The fork gated on `! -f "$PROJECT_DIR/WAI-Spoke/WAI-State.json" -> exit 0`. This spoke is pure v4 — WAI-Spoke/ does not exist — so the gate was FALSE and the script exit-0'd BEFORE the push block, rep...
- **Initiative:** none (a fix made outside a work item)
- **Find it:** commit `be173f5` (`git show be173f5`) · files: `wai-exit.sh`

## 2026-06-22

### Fix · fix(restore): track durable work-state; retire blanket spoke/local ignore

- **What changed:** Restore-completeness: durable brain (WAI-State, lugs, initiatives) was git-ignored by the blanket spoke/local/** rule -> empty brain after clone+basher restore. Granular ignore now (runtime/sessions/advisor-caches only). v4 self-audit s134. Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
- **Initiative:** none (a fix made outside a work item)
- **Find it:** commit `6f48103` (`git show 6f48103`) · files: `WAI-Harness/.gitignore`, `WAI-Harness/spoke/local/WAI-State.json`, `WAI-Harness/spoke/local/lugs/bytype/epic/open/epic-spoke-maintenance-gardener-v1.json`, `WAI-Harness/spoke/local/lugs/bytype/epic/open/epic-station-master-lines-v1.json`, `WAI-Harness/spoke/local/lugs/bytype/impl/completed/impl-db-keepalive-sidecar-v1.json`, `WAI-Harness/spoke/local/lugs/bytype/implementation/completed/coverage-eval-20260604-114005.json` and 146 more

## 2026-04-01

### Fix · fix: install missing .claude/commands/wai.md [gardener edge-case]

- **Initiative:** none (a fix made outside a work item)
- **Find it:** commit `b969175` (`git show b969175`) · files: `.claude/commands/wai.md`
