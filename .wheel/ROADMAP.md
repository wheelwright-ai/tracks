# Roadmap

Goal, then the initiatives that serve it, then their lugs, then what is finished. Generated from .wheel/backlog.jsonl by backlog.py roadmap; do not edit by hand. Progress counts done lugs against lugs not dropped.

## Goal 1: The product

A portable, model-neutral record of an AI conversation that anyone can use.

### I-001 Start here: the current prompt, a sample track and a way to check your own

*2 of 2 lugs done · done · owner sign-off: signed off by owner on 2026-11-08*

- **Outcome:** Someone new opens the Tracks README, copies the current recommended prompt, sees a sample track, and checks their own track file in a few steps.
- **Why now:** Anyone can use it is the product goal, but the lab's v4.0.0 prompt written on 10-28 is still not in the library and there is no single place to start.
- **In scope:** A start section at the top of the README with the recommended prompt, a sample track and how to validate a file; v4.0.0 published as the library's current variant with its sample.
- **Not in scope:** The claude.ai connector, a hosted service, or new prompt research.
- **Done when:** The README opens with the start section; the prompt file matches the lab's v4.0.0 text and the variants table lists it as latest (provisional until the lab's bench names a winner); validate_track.py passes on every sample track, including the new one.

- Done: B-001 Start here: one page with the recommended prompt, a sample track and how to check your own file, 2026-11-09 (wake-f95d17/checker)
- Done: B-002 Publish v4.0.0 to the library as the latest prompt, marked provisional until track-prompt-lab's bench names a winner, 2026-11-09 (wake-f95d17/checker)

### I-002 The format holds: spec, validator and viewer agree

*2 of 2 lugs done · done · owner sign-off: signed off by owner on 2026-11-08*

- **Outcome:** Every rule in the format spec is checked by the validator, a broken file fails with the rule named, and any valid track opens in the viewer as a static page with no server.
- **Why now:** A portable record is only portable if the spec and the tools agree; today the viewer needs serve.py and no test ties spec rules to validator checks.
- **In scope:** A test mapping each spec rule to a validator check; a broken fixture per rule; the viewer opening a dropped track file as a static page.
- **Not in scope:** Changing the format itself, editing tracks in the viewer, or hosting the viewer.
- **Done when:** A test maps each spec rule to a validator check, all samples pass and a broken fixture fails with its rule named; a browser test drops a sample track on the static viewer and sees its turns, decisions and open items with no server running.

- Done: B-004 The viewer opens any track file dropped on it, as a static page, 2026-11-08 (wake-4e0064/checker)
- Done: B-003 Format spec and validator agree: every rule in the spec is checked, every sample passes, 2026-11-09 (wake-f95d17/checker)

### I-004 Keep tracks healthy and current

*7 of 8 lugs done · active · owner sign-off: signed off by owner on 2026-11-08*

- **Outcome:** The project's own checks are trustworthy: tests and CI pass on a clean clone, known security gaps are closed, old uncommitted work is landed or retired, and its tooling follows the wheel's standing directives.
- **Why now:** The advisors' first sweep found broken CI, failing tests, security gaps and stale work that make every other result harder to trust.
- **In scope:** The Spotter's proposed fixes for this project from its first round, approved by the owner: CI, tests, security fixes, stale files, and the bun directive.
- **Not in scope:** New features, redesigns, and anything that changes production data or deploys without the owner.
- **Done when:** Every lug in this initiative is done: CI or the project's tests pass on a clean checkout, the named security fixes have tests, and no file named in the findings stays uncommitted for more than a day.

| rank | lug | kind | status |
|---:|---|---|---|
| 1 | B-009 Triage the uncommitted file in the main checkout that has been open since 2026-11-11 | you | blocked |
- Done: B-007 Add a small validator test run that checks every sample against the spec, 2026-11-09 (wake-f95d17/checker)
- Done: B-010 Decide the fate of .claude/.deploy-quarantine/hooks (9 hook files, not gitignored), 2026-11-12 (wake-3e8b53/checker)
- Done: B-008 Scout worktree-no-uncommitted broke: git status shows no changed or untracked files, 2026-11-12 (wake-3e8b53/checker)
- Done: B-012 Add one runner that executes every tests/ check and exits non-zero on any failure, 2026-11-12 (wake-3e8b53/checker)
- Done: B-011 Replace the red tests/critical_paths.sh stub with real deterministic tests over the viewer, track validator an, 2026-11-12 (wake-3e8b53/checker)
- Done: B-013 Scout critical-paths-stays-red-until-real broke: the stub still exits 1 and says it is not implemented, 2026-11-13 (wake-2e6a57/checker)
- Done: B-014 Scout worktree-no-uncommitted broke: git status shows no changed or untracked files, 2026-11-13 (wake-2e6a57/checker)

## Goal 2: Use it ourselves

The wheel's own sessions and wake-ups run on Tracks.

### I-003 The wheel's own sessions pick up from their last track

*2 of 2 lugs done · done · owner sign-off: signed off by owner on 2026-11-08*

- **Outcome:** A new session in a wheel project opens with the last session's open items and decisions from its track, and ideas stranded in old tracks are listed as lug candidates.
- **Why now:** Using Tracks ourselves is the proof it is worth using; the wheel's wake-ups still read other records, and old tracks hold ideas no one picked up.
- **In scope:** A session-start step that prints the last track's open items and decisions; a read-only script that lists open ideas in old tracks with their track and line.
- **Not in scope:** Writing lugs automatically, changing the hub's wake-up beyond reading the last track, or other people's projects.
- **Done when:** In a test project a session start prints the last track's open items and decisions, covered by a fixture test; a script over sample tracks lists open ideas with their track and line and writes nothing.

- Done: B-005 A new session in a project opens from the last session's track, 2026-11-09 (wake-f95d17/checker)
- Done: B-006 Find stranded ideas in old tracks and offer them as backlog candidates, 2026-11-09 (wake-8f6ad2/checker)

## Goal 3: Make it the best

Measure prompt variants across models and keep the winner.

No initiative yet.

## Goal 4: Distribute

Define and prove the claude.ai connector.

No initiative yet.

## Completed history

- 2026-11-13 · B-014 Scout worktree-no-uncommitted broke: git status shows no changed or untracked files · done by wake-2e6a57/checker
- 2026-11-13 · B-013 Scout critical-paths-stays-red-until-real broke: the stub still exits 1 and says it is not implemented · done by wake-2e6a57/checker
- 2026-11-12 · B-011 Replace the red tests/critical_paths.sh stub with real deterministic tests over the viewer, track validator an · done by wake-3e8b53/checker
- 2026-11-12 · B-012 Add one runner that executes every tests/ check and exits non-zero on any failure · done by wake-3e8b53/checker
- 2026-11-12 · B-008 Scout worktree-no-uncommitted broke: git status shows no changed or untracked files · done by wake-3e8b53/checker
- 2026-11-12 · B-010 Decide the fate of .claude/.deploy-quarantine/hooks (9 hook files, not gitignored) · done by wake-3e8b53/checker
- 2026-11-09 · B-006 Find stranded ideas in old tracks and offer them as backlog candidates · done by wake-8f6ad2/checker
- 2026-11-09 · B-005 A new session in a project opens from the last session's track · done by wake-f95d17/checker
- 2026-11-09 · B-003 Format spec and validator agree: every rule in the spec is checked, every sample passes · done by wake-f95d17/checker
- 2026-11-09 · B-007 Add a small validator test run that checks every sample against the spec · done by wake-f95d17/checker
- 2026-11-09 · B-002 Publish v4.0.0 to the library as the latest prompt, marked provisional until track-prompt-lab's bench names a winner · done by wake-f95d17/checker
- 2026-11-09 · B-001 Start here: one page with the recommended prompt, a sample track and how to check your own file · done by wake-f95d17/checker
- 2026-11-08 · B-004 The viewer opens any track file dropped on it, as a static page · done by wake-4e0064/checker
