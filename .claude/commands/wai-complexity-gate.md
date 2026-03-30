# Complexity Gate

Planning gate for multi-file or multi-step tasks; exempts utility commands.

## What It Does

Auto-triggers when:
- Task affects 2+ files, OR
- Implementation requires 6+ steps

Prevents scope creep by requiring structured planning before complex work.

**Exempted:** All WAI utility commands (wakeup, closeout, status, etc.)

## When It Triggers

Example 1: Refactoring
User: Refactor auth module (will touch service, middleware, tests, config)
AI: Complex task detected. Planning required. Propose a plan?

Example 2: Multi-step feature
User: Implement new teach command workflow (6+ steps)
AI: Complex task detected. Planning required. Propose a plan?

Example 3: Simple fix (NOT triggered)
User: Fix typo in CLAUDE.md
AI: (Proceeds autonomously, no planning gate)

## Expected Workflow

**User requests complex task →**
**AI detects (2+ files OR 6+ steps) →**
**AI blocks and asks for plan →**
**User says PLAN ACCEPTED →**
**AI proceeds with implementation →**
**Result: Intentional work, no surprises**

## Example Session

User: I want to refactor the skill system to add versioning (touches: WAI-Skills.jsonl, 8 skill files, auto-teaching (closeout Step 9b).md, manifest.json, tests). Should take 10+ steps.

AI: Complex task detected (9 files, 10+ steps).

**Proposed Plan:**

Step 1: Add version field to skill schema
Step 2: Update WAI-Skills.jsonl schema docs
Step 3-10: Add version to each skill file
Step 11: Update auto-teaching (closeout Step 9b).md to compare versions
Step 12: Write tests
Step 13: Update manifest.json

Ready? (yes/no)

User: PLAN ACCEPTED

AI: (Proceeds with implementation)

## Model-Task Awareness

In addition to complexity, this gate watches for **architectural signals** — indicators that the current task needs stronger model judgment than the active model may provide.

### Architectural Signals

- User is correcting fundamental assumptions about system design
- Task involves defining new protocols or boundaries
- Decisions affect multiple spokes or the entire wheel
- Task requires "should we?" judgment, not "how do we?" execution
- Agent is making assumptions about projects it hasn't verified
- Agent is creating multiple new artifacts without user validation

### When Detected

Prompt the user **once per session** (not repeatedly):

> "This work involves architectural decisions. I'm running as {model_name}. For design-level work where judgment matters, consider `/model` to switch to Sonnet or Opus."

### Model Tier Guidance

| Tier | Good For | Watch Out |
|------|----------|-----------|
| Haiku | Execution, file ops, following plans, tests | Misses assumption errors, treats design as execution |
| Sonnet | Balanced work, moderate design + execution | May miss novel architectural issues |
| Opus | Architecture, protocol design, reviewing prior work | Higher token cost; use when judgment matters |

### Session Logging

Model switches are recorded in `WAI-State.json` under `model_log`. On closeout, note which models were active and what task types they handled. This enables retrospective analysis.

See lug: `decision-model-task-awareness-protocol` for full protocol and incident record.

## Non-Trivial Functionality: Lug Required Before Showing

**Hard rule:** When discussing any non-trivial new functionality (new feature, skill, advisor, protocol behavior, architectural change), a lug with a complete PEV contract must be created AND validated before presenting to the user.

**Trigger:** Any proposal for new functionality that is not a trivial fix (<20 lines, 1 file, no new behavior).

**Required before showing:**
1. Lug exists at `bytype/{type}/open/{id}.json`
2. `perceive` — points to real, findable files or clearly observable current state
3. `execute` — concrete steps, not vague intentions ("refactor" without specifics fails)
4. `verify` — concrete done-state the user can confirm (not "looks good")
5. Lug is self-contained — a cold reader with no session context can act on it

**Cold-reader test:** Could a naive agent execute this lug with only the file contents and no memory of this conversation? If no → fix it first.

**Never do:** Show a lug draft and ask the user to help fill in the PEV fields. The improvement step happens before the user sees it.

---

## Plan Validation (Before Showing to User)

When creating an implementation plan (epic + child lugs), self-validate before presenting:

**Required on each implementation lug:**
- `behavior_specification` — input schema, process steps, output schema, state changes
- `test_requirements` — at least unit tests + integration tests, with one concrete example test case
- `acceptance_criteria` — specific, testable, objective (not "looks good")
- `dependencies` — `requires` (blocks), `blocks` (blocked-by), valid DAG

**Required on epic:**
- Child tasks ordered by sequence
- Parallelization declared (which tasks can run in parallel)
- Dependency graph with no circular deps

**Validation gates:**
- No vague language ("make it better", "refactor", "improve" without specifics)
- Each acceptance criterion maps to a named test
- Behavior spec has all three: input + process + output

**Only present plan to user after self-validation passes.** Append to plan:
```
✅ Plan validated — behavior, tests, acceptance criteria, and dependencies complete.
```

**Scope thresholds for when validation is required:**
- Always: epics, implementation lugs, 3+ files affected, anything with test requirements
- Optional: small bug fixes (<20 lines, 1 file), documentation updates, config changes

---

## Post-Execution Falsification (After Every Code Change)

**Principle: Assume the change is wrong until proven otherwise.**

After completing any code change, remediation, migration, or fleet-wide operation — verify by searching for evidence it FAILED, not evidence it passed. Green tool output is not proof. Absence of the problem across the full search space is proof.

**Required after every change:**

1. **Falsify the change itself:**
   - Re-run the failing condition that motivated the change. Does it now pass?
   - Introduce the old state temporarily. Does the fix actually catch it?

2. **Falsify the surroundings:**
   - What other files, templates, or spokes depend on or reference the thing you changed?
   - Search the **filesystem** (`find`), not just the registry or known locations
   - Templates, test-bench, demo-wheel, examples, archived projects — check all downstream copies

3. **Falsify the fleet:**
   - After fleet-wide changes: `find /home/mario/projects -name "{retired_file}"` across the ENTIRE project tree
   - The registry is not the truth — the filesystem is
   - Unregistered spokes, archived projects, and template files are all propagation vectors

4. **Prove done by absence:**
   - "Done" means: the problem cannot be found anywhere, not just that the fix was applied where you looked
   - Show the `find` command output. Empty result = proven. Any match = not done.

**When to run:**
- After every file deletion or rename (prove no copies remain)
- After every schema change (prove no old-format references survive)
- After every teaching publication (prove it applies cleanly on a real spoke clone)
- After every fleet remediation (prove the retired artifact is gone from ALL spokes, including unregistered ones)

**Anti-pattern this prevents:** "17/17 HEALTHY" that misses the template propagating the retired file to every future spoke. Verifying registered spokes is confirming; searching the filesystem is falsifying.

## Related Skills

- /wai-rules — Show scope boundaries
- /wai-stewardship-guard — Detect scope drift
