# ARCHITECTURE.md — Tracks Spoke Engineering Guide

**Last updated:** 2026-06-14  
**Audience:** New engineers joining Tracks. Reference: [KnowMe.md](WAI-Spoke/KnowMe.md) (project state), [AGENTS.md](AGENTS.md) (universal WAI patterns), [CLAUDE.md](CLAUDE.md) (Claude Code IDE integration)

---

## 1. Spoke Identity

### What Tracks Is

**Tracks** is a documentation and prompt library spoke within the Wheelwright fleet. It is **not** an application — there is no runtime, no build system, no web server, and no application code.

**Core deliverable:** Portable conversation-record prompt variants that let users extract and continue work from LLM sessions across any model or platform.

- `prompts/closing-request.md` — session wrap and handoff request (retroactive capture)
- `prompts/prep-and-request.md` — preparation and continuation for focused sessions
- `prompts/active-collection.md` — live session capture for AI-assisted continuity

**Why it exists:** Intellectual product created during AI conversations is trapped inside chat interfaces. Tracks provides prompts to free that work and make it portable and reusable.

### What Tracks Is NOT

- **Not a tool or service** — pure documentation and prompts; no CLI, no API
- **Not a deployment surface** — no CI/CD, no release pipeline, no Makefile
- **Not an application spoke** — contains no `package.json`, no `node_modules`, no `src/` with runtime code

### Deliverables vs. Non-Deliverables

| Deliverable | Non-Deliverable |
|-------------|-----------------|
| Track format specification (spec/track-format.md) | Track file viewer or editor (separate spoke) |
| Three prompt variants (prompts/) | Application code or web interface |
| Realistic sample Track files (samples/) | Build system or test automation |
| README and onboarding docs | Database, authentication, runtime dependencies |
| Skill definitions and routing (Skills/) | Delivery automation or release tags |

---

## 2. Directory Structure

```
tracks/
├── README.md                 # User-facing manifesto: portability framing, use cases, Wheelwright funnel
├── AGENTS.md                 # Universal WAI bootstrap (mandatory reading for all contributors)
├── CLAUDE.md                 # Claude Code IDE integration and session-specific rules
├── CHANGELOG.md              # Public version history and release notes
│
├── prompts/                  # Core deliverable: three portable prompt variants
│   ├── closing-request.md    # Retroactive track capture from completed session
│   ├── prep-and-request.md   # Preparation + continuation for focused sessions
│   ├── active-collection.md  # Live session capture for AI-assisted continuity
│   └── *.md                  # Supporting prompt documentation
│
├── spec/                     # Format specifications and contracts
│   └── track-format.md       # Complete WAI Point and Track file schema
│
├── samples/                  # Realistic example Track files demonstrating portability
│   └── *.jsonl               # Real session examples: coding, brainstorming, research
│
├── Skills/                   # Skill routing and command authority
│   ├── index.jsonl           # Routing authority: all callable skills
│   ├── wakeup/               # Wakeup skill (mandatory first turn)
│   │   ├── skill.md          # Skill definition and behavior
│   │   ├── context_prompt.md # Load instruction for the skill
│   │   └── feeds.yaml        # Data inputs and dependencies
│   ├── advisors/             # Advisor skill definitions (documentation, framework_development)
│   │   └── [advisor-id]/     # Per-advisor skill configuration
│   └── [skill-id]/           # Other skill folders by function
│
├── .claude/                  # Claude Code IDE configuration
│   ├── settings.json         # IDE settings: model, permissions, hooks
│   ├── hooks/                # Lifecycle hooks for session management
│   │   ├── user-prompt-submit.sh      # Injects wakeup protocol
│   │   ├── pre-tool-guard.sh          # Pre-tool execution guard
│   │   ├── pre-compact.sh             # Pre-context compression
│   │   └── stop-test-runner.sh        # Test runner lifecycle
│   └── commands/             # Legacy command aliases (backward compat only)
│
├── WAI-Spoke/                # Spoke state, lugs, sessions, teachings (principal work directory)
│   ├── WAI-State.json        # Project metadata, bootstrap, foundation status
│   ├── KnowMe.md             # This spoke's self-aware state snapshot
│   ├── forge-context.md      # Sketch of advisor triggers and session focus
│   │
│   ├── lugs/                 # Work queue: all tasks, features, bugs, signals
│   │   ├── bytype/           # Work organized by lifecycle state
│   │   │   ├── spec/         # Specifications and schema contracts
│   │   │   │   ├── draft/    # Specs being authored
│   │   │   │   ├── open/     # Active specs ready for adoption
│   │   │   │   └── completed/ # Completed and superseded specs
│   │   │   ├── implementation/ # Feature and fix work
│   │   │   │   ├── open/
│   │   │   │   ├── in_progress/
│   │   │   │   └── completed/
│   │   │   ├── task/         # Maintenance and operational work
│   │   │   ├── bug/          # Bug reports and fixes
│   │   │   ├── signal/       # Observations and cross-spoke notifications
│   │   │   └── epic/         # Multi-lug feature initiatives
│   │   └── incoming/         # Intake queue: lugs from hub or other spokes
│   │
│   ├── sessions/             # Session records for continuity (YYYYMMDD-HHMM format)
│   │   └── session-[id]/
│   │       ├── track.jsonl   # WAI Point record of session turns
│   │       └── [artifacts]   # Work artifacts from this session
│   │
│   ├── seed/ingest/          # Teaching adoption queue
│   │   ├── processed/        # Applied teachings (reference)
│   │   └── manual/           # Teachings pending human review
│   │
│   ├── advisors/             # Advisor systems: automation, expertise, monitoring
│   │   ├── documentation/    # Documentation quality and completeness advisor
│   │   │   ├── context_prompt.md
│   │   │   ├── findings-log.jsonl
│   │   │   └── scan_state.json
│   │   ├── framework_development/ # Framework architecture and evolution advisor
│   │   │   ├── context_prompt.md
│   │   │   ├── findings-log.jsonl
│   │   │   └── scan_state.json
│   │   ├── [other-advisors]/ # Additional advisors (deployment, automation, oversight)
│   │   ├── registry.json     # Advisor discovery and status index
│   │   └── schedule-index.json # Run times and last-execution tracking
│   │
│   ├── runtime/              # Session-local state (gitignored, not persisted)
│   │   └── session-guard.json # Session state guard (not WAI-State.json)
│   │
│   └── commands/             # Skill definitions (commands, wakeup sequence)
│       └── [skill-id].md     # Authority for CLI and orchestration
│
├── plans/                    # Planning and design documents
│   └── *.md                  # Skill system evolution, teaching roadmaps, incident reports
│
├── src/                      # Internal implementation (not part of core deliverable)
│   └── [implementation files]
│
├── tools/                    # MCP tools and integrations (if any)
│   └── [tool definitions]
│
└── viewer/                   # Track file viewer (zero-build web interface)
    └── index.html            # Browser-based timeline navigation and search
```

---

## 3. Lug Schema

A **lug** is a work unit in Wheelwright representing a task, feature, bug, signal, or specification. Every lug is a JSON file following this schema. Understanding the schema is essential for reading work queue and creating new tasks.

### Core Fields (Present in All Lugs)

| Field | Type | Purpose |
|-------|------|---------|
| `id` | string | Unique identifier (format: `[project-slug]-[date]-[time]`) |
| `type` | enum | Work kind: `spec`, `implementation`, `task`, `bug`, `signal`, `epic` |
| `title` | string | Human-readable work summary (one-liner) |
| `status` | enum | Lifecycle: `draft`, `open`, `in_progress`, `completed`, `blocked`, `canceled` |
| `routed_to` | enum | Routing destination: `LOCAL` (this spoke), `HUB` (hub-scoped), `SIGNAL` (cross-spoke notification), `FRAMEWORK` (framework proposal) |
| `authored_by` | string | Creator identifier: `mario`, `ozi-autopilot`, `advisor-[name]` |
| `created_at` | ISO 8601 | Timestamp of creation |

### Tracks-Specific Fields

| Field | Values | Meaning |
|-------|--------|---------|
| `initiative` | `crew-maintenance`, `prompt-quality`, `spec-evolution`, `foundation` | What program of work this belongs to |
| `model_fit` | `haiku`, `sonnet`, `opus` | Recommended model tier for execution |
| `effort_score` | 1–5 | Estimated complexity (1=trivial, 5=major effort) |
| `quality_score` | 1–10 | Completion standard (1=rough draft, 10=shipping quality) |
| `execution_mode` | `auto` (autonomous advisor), `gastown` (builder subprocess), `manual` (human review) | How this gets done |
| `urgency` | 1–10 | Relative priority (1=low, 10=critical) |

### PEV Contract Fields

Every lug includes a **Perceive → Execute → Verify (PEV)** contract describing the work:

| Field | Type | Purpose |
|-------|------|---------|
| `perceive` | string | Observation or problem that triggered this lug |
| `execute` | array of strings | Ordered steps to complete the work |
| `verify` | string | Acceptance criteria and verification approach |
| `acceptance_criteria` | string | Detailed success definition |
| `finding_ref` | string | Reference to the advisor finding that originated this (if applicable) |

### Workflow Metadata

Every lug tracks execution state:

```json
"workflow": {
  "current_owner": "ozi-autopilot",
  "assigned_at": "2026-06-14T11:51:27Z",
  "updated_at": "2026-06-14T11:51:27Z",
  "dispatch_method": "autopilot-subprocess",
  "completed_at": "2026-06-14T12:30:00Z"
}
```

### Initiative Values (Tracks Spoke)

Work in Tracks is organized by initiative:

- **`crew-maintenance`** — Advisor runs, status updates, routine quality checks
- **`prompt-quality`** — Improvements to prompt clarity, structure, or outputs
- **`spec-evolution`** — Changes to Track format specification, schema expansion
- **`foundation`** — Core onboarding, identity refinement, policy documentation

---

## 4. Advisor System

Advisors are autonomous systems that monitor spoke health, surface findings, and propose work. Tracks has two primary advisors, plus additional operational advisors.

### Documentation Advisor

**Domain:** `documentation`  
**Department:** Knowledge  
**Schedule:** Weekly  
**Model Preference:** Haiku (lightweight scans)

**Mission:** Maintain quality, completeness, and structural integrity of documentation and prompt library.

**Responsibilities:**
- **Content completeness:** Flag missing sections, undefined terms, stub placeholders
- **Writing quality:** Detect ambiguous instructions, inconsistent terminology, structural anti-patterns
- **Freshness monitoring:** Identify stale content, deprecated behaviors, obsolete schema references
- **Coverage mapping:** Track which features have documentation; report gaps
- **Cross-reference integrity:** Verify internal links, advisor references, skill pointers resolve correctly

**Escalation Rule:** Escalate to Ozi when documentation gaps affect cross-spoke contracts, when 3+ stale-content findings accumulate in same area across runs, or when quality issues suggest structural problems.

**Output:** Findings appended to `WAI-Spoke/advisors/documentation/findings-log.jsonl` as implementation task lugs.

### Framework Development Advisor

**Domain:** `framework_development`  
**Department:** Engineering  
**Schedule:** Weekly  
**Model Preference:** Sonnet (architectural review)

**Mission:** Maintain architectural integrity and evolutionary health of WAI framework protocols and teaching infrastructure.

**Responsibilities:**
- **Architecture oversight:** Review changes to lug schema, PEV contracts, signal routing, cross-spoke sovereignty
- **History and evolution tracking:** Flag new patterns that diverge from established doctrine without explicit supersession
- **Teaching infrastructure quality:** Assess completeness and accuracy of skills, commands, seed teachings
- **Timeline awareness:** Monitor open framework-level work; flag stalled or overdue implementation
- **Tech debt signaling:** Identify accumulated inconsistencies, deprecated patterns, anti-violations

**Escalation Rule:** Escalate to Ozi when a change affects cross-spoke contracts (lug schema, signal types, registry), when 3+ unresolved tech-debt signals accumulate in same area, or when decisions exceed this spoke's authority alone.

**Output:** Findings appended to `WAI-Spoke/advisors/framework_development/findings-log.jsonl` as implementation task lugs.

### Advisor Lifecycle

```
Weekly Schedule:
  Mon 04:00 UTC → [Gardener fleet]: Teaching adoption, lug intake, signal routing
       08:00 UTC → [documentation advisor]: Scan doc quality, emit findings
       14:00 UTC → [framework_development]: Scan architecture, emit findings
       20:00 UTC → [Ozi autopilot]: Review advisor findings, dispatch builder lugs
```

**Advisor Finding Flow:**
1. Advisor runs scan according to `context_prompt.md`
2. Findings appended to `findings-log.jsonl` (one JSON per finding)
3. For actionable finding, advisor creates implementation task lug in `WAI-Spoke/lugs/bytype/task/open/`
4. Builder sub-agent receives lug, executes per PEV contract
5. Lug moves to `in_progress/`, then to `completed/` with verification notes

---

## 5. Signal Routing

Signals are cross-spoke notifications used to broadcast observations, risks, or framework-level events that affect multiple spokes simultaneously.

### Signal Types

| Type | Source | Audience | Example |
|------|--------|----------|---------|
| **documentation-gap** | documentation advisor | this spoke, related spokes | "ARCHITECTURE.md missing sections" |
| **tech-debt** | framework_development advisor | engineering team | "Lug schema inconsistency across spokes" |
| **teaching-conflict** | gardener | framework team | "Two teachings define same skill differently" |
| **schema-drift** | framework_development advisor | framework team | "Implementation code diverged from spec" |

### Routing Rules

```
Signal routed by routed_to field:
  LOCAL      → Filed in WAI-Spoke/lugs/bytype/signal/open/
  HUB        → Relayed to hub/WAI-Hub/signals/incoming/framework/
  FRAMEWORK  → Escalated to framework spoke for architectural decision
  SIGNAL     → Cross-spoke: delivered to hub, broadcast to all wheels
```

**Escalation Criteria for SIGNAL:**
- **Impact ≥ 8 AND applies to every active spoke immediately**
- Affects core contracts (lug schema, signal types, routing protocol)
- Requires coordinated action across multiple spokes simultaneously
- Examples: Teaching adoption blocker, critical schema bug, framework-wide protocol change

**Default:** Most work is `LOCAL` or `FRAMEWORK`. Spoke-specific improvements stay LOCAL. Framework improvements go FRAMEWORK. Only cross-spoke simultaneity → SIGNAL.

### Signal Delivery Flow

```
Spoke creates signal
  ↓
routed_to: HUB
  ↓
WAI-Spoke/lugs/bytype/signal/open/[signal-id].json
  ↓
[Gardener]:
  Read signal, append to hub/WAI-Hub/signals/incoming/framework/
  OR route to specific spoke based on routed_to
  ↓
[Hub]:
  Process signal, route to relevant spokes' incoming/ queues
  OR escalate to framework
```

---

## 6. Teaching Adoption

**Teachings** are packaged framework improvements, protocol updates, or pattern changes distributed from the hub to all wheels for adoption.

### Teaching Lifecycle

```
Hub creates teaching
  ↓
hub/teachings_repo/spoke/current/[teaching-id].md
  ↓
[Gardener]: Discover teaching, ingest to WAI-Spoke/seed/ingest/processed/
  ↓
Policy decision:
  ├─ Auto-adopt? → Apply immediately, close
  ├─ Manual review? → Move to seed/ingest/manual/
  └─ Reject? → Log reason, skip
  ↓
[Human or Advisor]: Review teaching, accept/reject
  ↓
When accepted:
  ├─ Apply changes to files (e.g., Skills/, AGENTS.md, lug templates)
  ├─ Update WAI-State.json evolution_log with date + rationale
  ├─ Update wai-context.md if teaching affects session protocol
  └─ Commit: "chore: gardener lifecycle YYYY-MM-DD — teachings + work"
```

### Teaching Adoption Rules for Tracks

| Teaching Type | Auto-Adopt? | Why |
|---|---|---|
| Skill routing updates | Yes | Skills/index.jsonl is single source of truth |
| Lug schema changes | No | Requires explicit acknowledgment and KnowMe.md update |
| Session protocol updates | No | CLAUDE.md and AGENTS.md versioning must be explicit |
| Documentation patterns | Maybe | Review by documentation advisor first |
| Signal type additions | No | Affects cross-spoke contracts |

### WaiContext.md Update Protocol

When a teaching affects session behavior (e.g., new wakeup step, new advisor activation), update:

1. **WAI-State.json** `evolution_log` — document the change and rationale
2. **CLAUDE.md** or **AGENTS.md** — update the changed section with version bump
3. **KnowMe.md** — refresh `Current stage` and `Architecture` sections if applicable
4. Commit message includes teaching ID and rationale

---

## 7. Work Lifecycle

Every lug follows a state machine from creation through completion. Understanding this lifecycle is essential for navigating the work queue and understanding what Ozi autopilot is doing.

### Lug State Diagram

```
┌──────────┐
│  DRAFT   │         (Authored, not ready)
└─────┬────┘
      │
      │ (Human approval / advisor find)
      ↓
┌──────────┐
│   OPEN   │         (Ready to be picked up by builder)
└─────┬────┘
      │
      │ (Builder dispatched via ozi-autopilot)
      ↓
┌─────────────────┐
│   IN_PROGRESS   │  (Builder actively working)
└─────┬───────────┘
      │
      │ (PEV contract fulfilled, verification done)
      ↓
┌───────────────┐
│   COMPLETED   │  (Work done, in completed/ folder, ready for close-out)
└───────────────┘

Alternate paths:
  OPEN → BLOCKED     (Dependency or decision blocker)
  ANY  → CANCELED    (Scope change, deprioritization)
```

### File Movement During Lifecycle

```
Creation:
  1. Author writes lug JSON with status=draft or open
  2. File appears in WAI-Spoke/lugs/bytype/[type]/draft/  OR  open/

When status changes to in_progress:
  2. Lug is copied to WAI-Spoke/lugs/bytype/[type]/in_progress/
  3. Original removed from open/

When status changes to completed:
  3. Lug is copied to WAI-Spoke/lugs/bytype/[type]/completed/
  4. Original removed from in_progress/
  5. Updated timestamp, workflow.completed_at, execution notes added

Signals flow: open/ → completed/ after delivery to hub
Specs flow: open/ → completed/ when superseded or archived
```

### Builder Sub-Agent Dispatch

```
[Ozi Autopilot] (orchestration controller)
  ↓
Scans: WAI-Spoke/lugs/bytype/[type]/open/
  ↓
For each open lug:
  1. Check model_fit (haiku/sonnet/opus) against available agents
  2. Check execution_mode:
     - auto     → advisory run (advisor context, find)
     - gastown  → builder subprocess (full repo, git, implementation)
     - manual   → flag for human review
  3. Dispatch to Builder Sub-Agent
     with PEV contract from lug
  ↓
[Builder Sub-Agent]:
  1. Read lug JSON
  2. Follow PEV: Perceive → Execute → Verify
  3. Update lug status: draft → in_progress → completed
  4. Move lug file to completed/
  5. Append workflow.completed_at, execution notes
  ↓
[Ozi] (post-execution):
  Monitor completed lugs for signal delivery, teach adoption,
  cascade to next phase (e.g., integration into framework)
```

### Signal Delivery Flow

```
Signal created: routed_to=HUB or SIGNAL
  ↓
[Gardener] (on schedule):
  Scans: WAI-Spoke/lugs/bytype/signal/open/
  ↓
  For routed_to=HUB:
    Appends signal to hub/WAI-Hub/signals/incoming/framework/
    Moves signal to WAI-Spoke/lugs/bytype/signal/completed/
  ↓
  For routed_to=SIGNAL:
    Broadcasts to hub
    Relayed to ALL wheels' incoming/ queues
    Marked for cross-spoke escalation
  ↓
[Hub or Framework]:
  Processes signal, routes to affected spokes
  May trigger new lugs in receiving spokes
```

### Teaching Integration Flow

```
[Gardener] discovers new teaching from hub
  ↓
Reads: hub/teachings_repo/spoke/current/[teaching-id].md
  ↓
Policy check (Tracks automation):
  Auto-adopt? → Apply immediately
  Manual review? → Queue to seed/ingest/manual/
  ↓
When accepted:
  1. Apply changes to affected files (e.g., Skills/, AGENTS.md)
  2. Update WAI-State.json evolution_log
  3. Update wai-context.md if protocol changed
  4. Move teaching to seed/ingest/processed/
  ↓
[Next session]:
  Recognizes applied teaching, prevents re-adoption
```

---

## 8. Onboarding Checklist

New engineer joining Tracks should work through this in order:

### Phase 1: Foundation (1–2 hours)
- [ ] Read [AGENTS.md](AGENTS.md) — understand WAI bootstrap and universal patterns
- [ ] Read [CLAUDE.md](CLAUDE.md) — Claude Code IDE integration and session lifecycle
- [ ] Read [KnowMe.md](WAI-Spoke/KnowMe.md) — this spoke's current state and constraints
- [ ] Skim [README.md](README.md) — user-facing value proposition

### Phase 2: Architecture (2–3 hours)
- [ ] Read this file (ARCHITECTURE.md) — complete reference for internal structure
- [ ] Explore directory layout: run `ls -R` through WAI-Spoke/, Skills/, prompts/
- [ ] Read one completed lug from `WAI-Spoke/lugs/bytype/implementation/completed/`
- [ ] Review advisor context: read both `context_prompt.md` files in advisors/

### Phase 3: Hands-On (3–4 hours)
- [ ] Create a draft implementation lug in WAI-Spoke/lugs/bytype/task/draft/
- [ ] Run `/wai` command and read the briefing output
- [ ] Review a teaching from `seed/ingest/manual/` (if any pending)
- [ ] Add yourself to a session track.jsonl to understand WAI Point format

### Phase 4: Specialization
- **Prompt engineer?** Start with `prompts/` and `spec/track-format.md`
- **Framework architecture?** Deep-dive into `Skills/`, `AGENTS.md`, signal routing
- **Advisor expert?** Review both advisor `context_prompt.md` and `findings-log.jsonl`

---

## 9. Key Concepts

### Spoke vs. Wheel

- **Spoke:** The code repository and configuration template (e.g., `/home/mario/projects/wheelwright/tracks/`)
- **Wheel:** An active instance of a spoke with persistent state and session history (has a `WAI-Spoke/` directory)

### Hub vs. Framework

- **Hub:** Coordination center (`/home/mario/projects/wheelwright/hub/`) — routing, teaching distribution, signal relay
- **Framework:** Core WAI system (`/home/mario/projects/wheelwright/framework/`) — CLI, teaching engine, lug templates, universal protocols

### Builder Sub-Agent vs. Gardener

- **Builder:** Specialized agent dispatched to execute a single lug; starts fresh; has full git/MCP access
- **Gardener:** Fleet of Haiku agents running on schedule; autonomous; processes teachings, routes signals, files lugs

### Teaching vs. Signal

- **Teaching:** Framework improvement or pattern update distributed FROM hub TO all wheels (one-way push)
- **Signal:** Cross-spoke observation or notification, often FROM spokes TO hub (reports upward)

---

## 10. Standing Rules

These are non-negotiable patterns in Tracks work:

| Rule | Why | Example |
|------|-----|---------|
| Lug first, code second | All work tracked before execution; PEV contract is the spec | Create lug in draft/, review, move to open/ before starting |
| No git push unless explicit | Commits OK; push requires lug-directed or user request | Commit work, leave push to user or lug workflow step |
| Skills/ is source of truth | Not WAI-Spoke/WAI-Skills.jsonl (mirror only) | Update Skills/index.jsonl and skill folder, never mirror directly |
| Teaching adoption is policy | Not ad-hoc manual applies | Route through seed/ingest/, policy check, evolution_log entry |
| Signals escalate UP | Not sideways to other spokes | routed_to=HUB for hub decision, routed_to=SIGNAL for broadcast |
| Broken references block work | All links must resolve | Test doc links, verify advisor references before merge |
| Absolute paths in hooks | Shell vars like $CLAUDE_PROJECT_DIR cause silent failures | Use `/home/mario/projects/wheelwright/` in .claude/hooks/ |

---

## 11. Reference Links

- **Universal bootstrap:** [AGENTS.md](AGENTS.md) — WAI architecture, agent types, key paths
- **IDE integration:** [CLAUDE.md](CLAUDE.md) — Claude Code wakeup, commands, session tracking
- **Project state:** [KnowMe.md](WAI-Spoke/KnowMe.md) — current priorities, constraints, evolution log
- **User guide:** [README.md](README.md) — what Tracks is, why it matters, how to use prompts
- **Format spec:** [spec/track-format.md](spec/track-format.md) — WAI Point and Track schema
- **Skills routing:** [Skills/index.jsonl](Skills/index.jsonl) — skill discovery and callable commands
- **Lug templates:** [WAI-Spoke/lugs/](WAI-Spoke/lugs/) — examples of all lug types and states

---

## 12. FAQ

**Q: Where do I file a new task?**  
A: Create JSON in `WAI-Spoke/lugs/bytype/task/draft/` with id, title, perceive, execute, verify. When ready, move to `open/`.

**Q: How do advisors know what to do?**  
A: Each advisor has a `context_prompt.md` describing their mission and responsibilities. Gardener fleet runs these on schedule.

**Q: Can I edit Skills/index.jsonl directly or do I need to create a lug first?**  
A: Always create an implementation or task lug first (PEV contract), then execute. Skills/ is too critical to change without tracking.

**Q: What does "routed_to=SIGNAL" mean?**  
A: Cross-spoke broadcast. Affects multiple wheels immediately. Reserve for high-impact framework changes. Default is LOCAL.

**Q: How does a teaching get applied?**  
A: Hub publishes it → Gardener discovers it → Policy check (auto or manual) → If accepted, apply changes, update evolution_log, move to processed/.

**Q: Who is Ozi?**  
A: Ozi is the orchestration autopilot. It dispatches builder lugs, monitors advisor findings, routes signals, and manages work flow.

---

**Generated:** 2026-06-14  
**Status:** Ready for engineering onboarding  
**Feedback:** File issues in WAI-Spoke/lugs/bytype/task/ or escalate to documentation advisor
