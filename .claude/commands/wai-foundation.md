# WAI Foundation

**Project identity, goals, and boundaries - the project's personality and memory.**

---

## Execution Context

- **Nodes:** spoke, hub
- **Exposure:** spoke.chat:local, spoke.chat:external
- **Paths Required:** spoke_path (current directory)
- **Lug Storage:** `WAI-Spoke/lugs/active/WAI-Lugs-active.jsonl` with `ty: "foundation"`

---

## When to Use

- **First session** - No foundation lugs exist
- **Scope change** - User wants to add/remove from boundaries
- **Goal shift** - Project purpose evolves
- **Constraint change** - New limitations or freedoms
- **Periodic review** - Validate foundation still accurate

## Prerequisites

- WAI-Spoke/ directory exists
- `lugs/active/WAI-Lugs-active.jsonl` exists (or will be created)

## Follow-ons

- Work can begin once foundation established
- `/wai-closeout` — Captures foundation evolution in session
- `/wai (Step 3a: auto-discovery)` — High-impact foundation changes shared to hub

## Use Cases

**Use Case 1: New Project**
- Situation: First AI session, no foundation exists
- Action: Run foundation to establish identity, goals, boundaries
- Result: Foundation lug v1 created, work can begin

**Use Case 2: Scope Expansion**
- Situation: User wants to add features outside original scope
- Action: Run foundation to evolve boundaries with rationale
- Result: Foundation lug v(n+1) captures change and why

**Use Case 3: Pivot**
- Situation: Project purpose fundamentally shifts
- Action: Run foundation to capture new identity
- Result: Evolution chain shows the journey

**Use Case 4: Onboarding New AI**
- Situation: Different AI/session needs project context
- Action: Query foundation lugs for current state + history
- Result: AI understands project personality and evolution

---

## Foundation Lug Schema

### Initial Foundation (v1)

```json
{
  "id": "lug-fnd-{8-char-hex}",
  "ty": "foundation",
  "v": 1,
  "title": "Initial Foundation",
  "created_at": "ISO-8601",
  "gathered_by": "AI-name",

  "identity": {
    "name": "project-name",
    "purpose": "One-sentence description of what this project does",
    "type": "code|research|writing|design|mixed",
    "done_looks_like": "What success means for this project"
  },

  "boundaries": {
    "in_scope": ["things", "we", "will", "do"],
    "out_scope": ["things", "we", "avoid"],
    "constraints": ["limitations", "requirements"]
  },

  "approach": {
    "tools": ["technologies", "frameworks"],
    "ai_style": "initiative|check-in|mixed",
    "decision_review": "How decisions get reviewed"
  }
}
```

### Evolution Foundation (v2+)

```json
{
  "id": "lug-fnd-{8-char-hex}",
  "ty": "foundation",
  "v": 2,
  "title": "Brief: what changed",
  "created_at": "ISO-8601",
  "gathered_by": "AI-name",
  "evolved_from": "lug-fnd-{previous-id}",

  "rationale": "Why this change was made",
  "acknowledged_by": "User confirmation or name",

  "changes": {
    "identity.purpose": {"was": "old", "now": "new"},
    "boundaries.in_scope": {"added": ["new"], "removed": ["old"]},
    "constraints": {"added": ["new constraint"]}
  },

  "full_state": {
    "identity": {...},
    "boundaries": {...},
    "approach": {...}
  }
}
```

---

## Foundation Procedure

### 1. Check Existing Foundation

```
Query lugs/active/WAI-Lugs-active.jsonl:
  foundation_lugs = lugs where ty="foundation"
  current = foundation_lugs | sort by created_at desc | first
```

If no foundation exists → **Gather New Foundation**
If foundation exists → **Verify or Evolve**

### 2. Gather New Foundation (First Time)

Ask conversationally (not a form):

**Identity:**
> "What's the one-sentence description of this project?"
> "Is this code, research, writing, design, or a mix?"
> "What does 'done' look like for you?"

**Boundaries:**
> "What's definitely IN scope for this project?"
> "What should we explicitly AVOID or consider out of scope?"
> "Any constraints I should know about? (time, tech, resources)"

**Approach:**
> "What tools or technologies are we using?"
> "How do you want to work with AI - should I take initiative or check in frequently?"
> "How should decisions get reviewed?"

### 3. Write Foundation Lug

After gathering answers:

1. Generate `id`: `lug-fnd-{random-8-hex}`
2. Set `v: 1`, `ty: "foundation"`
3. Populate identity, boundaries, approach from answers
4. Append to `lugs/active/WAI-Lugs-active.jsonl`
5. Update `WAI-State.json` cache (see below)

### 4. Verify or Evolve (Returning Session)

Present current foundation summary:

```markdown
**Current Foundation** (v{n}, established {date})

**Identity:** {purpose}
**In Scope:** {list}
**Out of Scope:** {list}
**Constraints:** {list}

Is this still accurate? (yes / needs update)
```

If needs update → **Evolve Foundation**

### 5. Evolve Foundation

When scope/goals change:

1. Ask: "What's changing and why?"
2. Create evolution lug with:
   - `v`: previous + 1
   - `evolved_from`: previous lug id
   - `rationale`: why the change
   - `changes`: diff of what changed
   - `full_state`: complete current state
3. Append to `lugs/active/WAI-Lugs-active.jsonl`
4. Update `WAI-State.json` cache

---

## WAI-State.json Cache

`_project_foundation` in WAI-State.json caches latest foundation for fast wakeup:

```json
{
  "_project_foundation": {
    "source_lug": "lug-fnd-abc12345",
    "version": 3,
    "cached_at": "ISO-8601",
    "identity": {...},
    "boundaries": {...},
    "approach": {...},
    "completed": true
  }
}
```

**Rule:** Lugs are source of truth. WAI-State.json is cache for performance.

---

## Querying Foundation

### Current State
```
lugs where ty="foundation" | sort created_at desc | first
```

### Evolution History
```
lugs where ty="foundation" | sort created_at asc
```

### Why Did Scope Change?
```
lugs where ty="foundation" AND v > 1 | read rationale chain
```

---

## Impact Threshold

Foundation changes are **always high-impact (impact >= 8)** because they affect all future work:

- Initial foundation: impact = 9
- Scope expansion: impact = 8
- Pivot/major change: impact = 10
- Minor constraint update: impact = 8

These automatically become signals for `/wai (Step 3a: auto-discovery)`.

---

## Related Skills

- `/wai-closeout` — Captures foundation evolution in session summary
- `/wai (Step 3a: auto-discovery)` — Shares foundation patterns to hub
- `/wai-status` — Shows current foundation summary

---

*Foundation = The project's personality and memory. Evolves over time, never lost.*
