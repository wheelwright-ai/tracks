# Roadmap

Goal, then the initiatives that serve it, then their lugs, then what is finished. Generated from .wheel/backlog.jsonl by backlog.py roadmap; do not edit by hand. Progress counts done lugs against lugs not dropped.

## Goal 1: The product

A portable, model-neutral record of an AI conversation that anyone can use.

### I-001 Start here: the current prompt, a sample track and a way to check your own

*0 of 2 lugs done · proposed · owner sign-off: pending*

- **Outcome:** Someone new opens the Tracks README, copies the current recommended prompt, sees a sample track, and checks their own track file in a few steps.
- **Why now:** Anyone can use it is the product goal, but the lab's v4.0.0 prompt written on 10-28 is still not in the library and there is no single place to start.
- **In scope:** A start section at the top of the README with the recommended prompt, a sample track and how to validate a file; v4.0.0 published as the library's current variant with its sample.
- **Not in scope:** The claude.ai connector, a hosted service, or new prompt research.
- **Done when:** The README opens with the start section; the prompt file matches the lab's v4.0.0 text and the variants table names it current; validate_track.py passes on every sample track, including the new one.

| rank | lug | kind | status |
|---:|---|---|---|
| 1 | B-001 Start here: one page with the recommended prompt, a sample track and how to check your own file | autopilot | ready |
| 2 | B-002 Publish the lab's winning prompt (v4.0.0) as the library's current variant | autopilot | ready |

### I-002 The format holds: spec, validator and viewer agree

*0 of 2 lugs done · proposed · owner sign-off: pending*

- **Outcome:** Every rule in the format spec is checked by the validator, a broken file fails with the rule named, and any valid track opens in the viewer as a static page with no server.
- **Why now:** A portable record is only portable if the spec and the tools agree; today the viewer needs serve.py and no test ties spec rules to validator checks.
- **In scope:** A test mapping each spec rule to a validator check; a broken fixture per rule; the viewer opening a dropped track file as a static page.
- **Not in scope:** Changing the format itself, editing tracks in the viewer, or hosting the viewer.
- **Done when:** A test maps each spec rule to a validator check, all samples pass and a broken fixture fails with its rule named; a browser test drops a sample track on the static viewer and sees its turns, decisions and open items with no server running.

| rank | lug | kind | status |
|---:|---|---|---|
| 3 | B-003 Format spec and validator agree: every rule in the spec is checked, every sample passes | autopilot | ready |
| 4 | B-004 The viewer opens any track file dropped on it, as a static page | autopilot | ready |

## Goal 2: Use it ourselves

The wheel's own sessions and wake-ups run on Tracks.

### I-003 The wheel's own sessions pick up from their last track

*0 of 2 lugs done · proposed · owner sign-off: pending*

- **Outcome:** A new session in a wheel project opens with the last session's open items and decisions from its track, and ideas stranded in old tracks are listed as lug candidates.
- **Why now:** Using Tracks ourselves is the proof it is worth using; the wheel's wake-ups still read other records, and old tracks hold ideas no one picked up.
- **In scope:** A session-start step that prints the last track's open items and decisions; a read-only script that lists open ideas in old tracks with their track and line.
- **Not in scope:** Writing lugs automatically, changing the hub's wake-up beyond reading the last track, or other people's projects.
- **Done when:** In a test project a session start prints the last track's open items and decisions, covered by a fixture test; a script over sample tracks lists open ideas with their track and line and writes nothing.

| rank | lug | kind | status |
|---:|---|---|---|
| 5 | B-005 A new session in a project opens from the last session's track | autopilot | proposed |
| 6 | B-006 Find stranded ideas in old tracks and offer them as backlog candidates | autopilot | proposed |

## Goal 3: Make it the best

Measure prompt variants across models and keep the winner.

No initiative yet.

## Goal 4: Distribute

Define and prove the claude.ai connector.

No initiative yet.

## Completed history

Nothing finished yet.
