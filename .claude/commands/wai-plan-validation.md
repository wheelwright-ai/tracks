# WAI Plan Validation

Before an implementation plan (epic + child lugs) is **shown to the user**, run the mandatory review gate (Step 0) and then self-validate it (Step 1). Invalid plans are refined first; only reviewed and validated plans reach the user.

## When it applies

Any time you produce an implementation plan as lugs — especially after the complexity gate triggers (2+ files OR 6+ steps). Referenced by `wai-complexity-gate.md`.

---

## Step 0 — Mandatory Adversarial Implementability Review (NON-SKIPPABLE)

Before running the validation checklist, spawn a subagent in **implementer persona** to adversarially review the plan against the actual repo/codebase state.

**This step is REQUIRED for any 0-to-1 or multi-phase build plan. Skipping it is a protocol violation.**

Why: Plans read as complete to their authors. The failure mode is confident-but-wrong premises that only surface mid-implementation, when they are most expensive. An adversarial review that checks claims against the real filesystem/DB/config state catches these for cents.

### Reviewer model

Use `sonnet`-class or better. Frontier is not required; sonnet was sufficient in the known trigger case (~60k tokens, ~4 min). Set `model_fit: "sonnet"` on the review invocation.

### Reviewer prompt template

```
You are an experienced implementer reviewing a build plan for implementability defects BEFORE any code is written.

Your job is adversarial: assume the plan WILL mislead a naive agent and find where.

## Plan under review

<paste full plan document here>

## Repo/codebase access

You have read access to the project tree. Use it. Do NOT rely solely on what the plan claims about the codebase — verify claims against actual files.

## Required analysis

### 1. Section-by-section judgment gaps
For every phase/step/section: where would an implementer be FORCED to guess or invent a decision not stated in the plan? List each as a GAP with the section reference.

### 2. Factual premise verification (CRITICAL)
Check each factual claim the plan makes about the actual codebase state:
- File/directory paths: do they exist?
- Table/schema names: are they used elsewhere with conflicting schemas?
- Function signatures: do they match what's in the code?
- Config keys/env vars: are they actually set or expected?
- Dependency versions: are they available?
- "We will create X" / "X does not exist yet": verify X truly does not exist (false negative = corruption risk)

For each claim that FAILS verification, report it as a BLOCKER with the evidence (what the plan says vs. what the filesystem/DB shows).

### 3. Data model vs. promised features cross-check
If a schema, migrations, or data model is present in the plan:
- Does the schema support every feature the plan promises?
- Are there naming collisions with legacy tables/columns that would cause silent data corruption (e.g. CREATE TABLE IF NOT EXISTS attaching new code to an old incompatible table)?
- Are migration operations safe under existing live data?

### 4. Severity triage

For every finding, assign:
- **BLOCKER** — plan will fail or corrupt data without this fix; must be resolved before approval
- **GAP** — plan will require on-the-fly invention; must be explicitly assigned to a named phase or converted to a decision lug
- **DEFER-OK** — noted but acceptable to handle during implementation

## Output format

```
REVIEW SUMMARY
==============
Blockers: N
Gaps: M
Defer-OK: K
Verdict: [PASS — ready for approval | FAIL — must revise before approval]

BLOCKERS
--------
B1. [Section X] <what the plan claims> vs. <what the filesystem shows>
...

GAPS
----
G1. [Section X] <where judgment is required that the plan does not provide>
...

DEFER-OK
--------
D1. [Section X] <acceptable uncertainty>
...
```

If verdict is PASS and all blockers are zero: state "REVIEW PASSED — no blockers found."
```

### Review resolution gate

After the subagent completes:

1. **Any BLOCKERs** → fix them in the plan document, re-run the review. Do not advance until verdict is PASS.
2. **Any GAPs** → either fix them in the plan OR convert each to an explicitly named phase assignment or decision lug. Do not leave unresolved blanks.
3. **Add a `review_resolution` section** to the plan document (or epic lug description) recording:
   - Review run date + reviewer model
   - Number of blockers found and how each was resolved
   - Number of gaps found and their disposition (fixed | assigned to phase X | deferred as decision lug Y)
   - Any solo decisions taken (captured for provenance)

**A plan WITHOUT a `review_resolution` section MUST NOT be presented to the user. This is a gate.**

---

## Step 1 — Validation checklist (per child lug)

Each lug in the plan must pass ALL:

1. **Complete PEV** — non-empty `perceive`, `execute`, `verify`.
2. **Testable verify** — `verify` is concrete (>50 chars, contains an action verb + an observable check), not "it works".
3. **Explicit acceptance_criteria** — at least one, falsifiable.
4. **Effort + model_fit** — set, not inferred-blank. See model-tier routing in `wai-lug-schema.md`.
5. **File targets** — `target_files` names real paths.
6. **Dependency clarity** — if it depends on another lug in the plan, `blocked_by` says so (enables parallelism; no hidden sequential assumptions).

## Step 2 — Plan-level checks

- **Parallel-ready:** lugs with no `blocked_by` between them can run concurrently — confirm the dependency graph is explicit, not implied by ordering.
- **No orphan ACs:** every epic acceptance criterion maps to at least one child lug.
- **Hypothesis present (ideation):** for feature/idea-origin plans, the epic carries `hypothesis` + `expected_lift` + `measure` (see `wai-lug-schema.md`) so the lift is checkable later.

---

## Outcome

- **Review PASS + all checklist items pass** → present the plan to the user.
- **Review FAIL or any checklist item fails** → fix first, re-check. Do NOT show a plan with `[gap]` placeholders or missing `review_resolution`.

### After plan approval: mandatory lug generation

Once the user approves the plan:

1. **Generate implementation lugs immediately** — this is mandatory, not optional follow-up.
2. Every lug must carry: complete PEV, `acceptance_criteria`, `effort`, `model_fit`, `subagent_guidance`, and `target_files`.
3. **Assign model tier per complexity** (see `wai-lug-schema.md` model-tier routing table):
   - Mechanical / baked-in work (exact SQL, commands fully specified, no architectural judgment) → `model_fit: "haiku"`
   - Integration judgment, multi-file coordination, design decisions → `model_fit: "sonnet"`
   - Frontier only when genuinely novel or high-stakes architectural work — state the reason in `model_fit_reason`.
   - **Default to the affordable tier. Escalation requires a stated reason.**

## Why

Plans read as complete to their authors. The adversarial review catches false premises against the real codebase state — not just internal consistency. Paired with model-routed lug generation, every approved plan becomes cheap, parallelizable execution instead of expensive frontier-model improvisation.
