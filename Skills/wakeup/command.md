# Command: Wakeup

Run this skill at session start.

## Protocol Nature

Wakeup is a **protocol skill**. One invocation performs an ordered multi-step process that prepares the spoke for work.

It is not a single atomic operation.

## Phase 1: Load Canonical State

Read, in order:
- `WAI-Spoke/WAI-Guide.md`
- `WAI-Spoke/WAI-State.json`
- `WAI-Spoke/WAI-State.md`

Check:
- `_project_foundation`
- `_session_state`
- `context`

If `WAI-State.json` and `WAI-State.md` disagree, reconcile against the shipped repo artifacts before continuing.

## Phase 2: Validate the Local Repo

Inspect:
- git status
- core deliverables declared by the spoke

Goal:
- confirm the repo still matches its declared identity
- detect drift or stale protocol artifacts before new work starts

## Phase 3: Reconcile Teachings

Inspect hub teachings and compare them against:
- `WAI-Spoke/seed/processed/`
- `WAI-Spoke/WAI-Signals.jsonl`
- verification artifacts already present locally

Before surfacing a teaching as new:
1. check whether the filename already appears in signals
2. check whether the teaching name or leading phrase already appears in signals
3. check whether the expected implementation artifacts already exist

If already implemented but not archived locally:
- copy it to `WAI-Spoke/seed/processed/`
- do not present it as new work

Classify remaining teachings into:
- safe to auto-adopt
- manual review
- malformed metadata

## Phase 4: Load Active Work

Read:
- `WAI-Spoke/WAI-Skills.jsonl`
- `WAI-Spoke/WAI-Lugs.jsonl`
- `WAI-Spoke/WAI-Signals.jsonl`

Summarize:
- active or recently closed work
- important learned signals
- empty or missing registries

## Phase 5: Detect Portable Context

Check for:
- imported `WAI_Track-*.jsonl`
- prior `track_session-*.jsonl`
- predecessor track content already loaded into the conversation

If predecessor context is found:
- report source file, session id, last turn, and last timestamp
- preserve that metadata for continuity and track generation

## Phase 6: Initialize Session

Update active session state:
- mark protocol as completed
- set current session metadata
- set conversation log path
- set canonical internal track path

Canonical conventions:
- live session log: `WAI-Spoke/WAI-Session-Log.jsonl`
- internal track path: `WAI-Spoke/sessions/track_session-YYYYMMDD-HHMM.jsonl`
- external portable export: `WAI_Track-YYYYMMDD-HHMM-Provider-Model.jsonl`

Do not create legacy `WAI-Spoke/session-*/track.jsonl` directories.

## Phase 7: Brief

Produce a short wakeup briefing with:
- project identity
- environment
- git state
- active work
- teaching queue
- next actions

Final line:

`Wake complete. Ready to work. What would you like to do next?`

## Composition Notes

This protocol may later call or delegate to separate skills such as:
- teaching reconciliation
- chat-to-track
- track generation
- advisory checks

Those subskills should remain discrete, but wakeup remains the orchestrator.
