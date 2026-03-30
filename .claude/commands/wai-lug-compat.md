# WAI Lug Compatibility Advisor

**Version-aware lug lifecycle — identify outdated lugs, review them against the current framework, send improved versions back to the hub so other spokes don't repeat the same work.**

---

## Execution Context

- **Nodes:** spoke, hub
- **Exposure:** spoke.chat:local
- **Trigger:** `/wai-lug-compat` or automatically at wakeup when stale lug count exceeds threshold

---

## The Problem This Solves

Lugs travel across sessions, models, spokes, and time. A lug authored under framework v1.0 may give guidance that contradicts v3.0 protocol. Without a version stamp, no agent can tell the difference between a trustworthy lug and an archaic one.

**Symptoms of unversioned lug rot:**
- Agent follows an old lug's protocol and gets contradictory results
- Multiple spokes independently review and discard the same outdated lug
- Hub distributes stale advice to every new spoke that comes online

This skill fixes all three by adding version stamps at authoring time, defining a review protocol, and routing improved lugs back to the hub.

---

## New Schema Fields

### `fw_ver` — Framework Version (authoring stamp)

```json
"fw_ver": "3.0.0"
```

- Set at lug creation time to the current `wheel.version` from `WAI-State.json`
- **Never updated after creation** — it records when the lug was written, not when it was last touched
- Required on all new lugs and signals from this version forward

### `reviewed_fw_ver` — Review Version

```json
"reviewed_fw_ver": "3.0.0"
```

Set when a lug passes through the review protocol. Records the framework version in use at review time.

### `review_status` — Review Outcome

```json
"review_status": "valid | outdated_protocol | superseded | contradicts_current"
```

| Value | Meaning |
|-------|---------|
| `valid` | Still accurate under current framework |
| `outdated_protocol` | References a protocol that has changed — guidance needs updating |
| `superseded` | A newer lug covers this ground |
| `contradicts_current` | Actively conflicts with current framework — must be reconciled |

### `hub_origin` — Distribution Tracking

```json
"hub_origin": true
```

Set to `true` when a lug was received from hub distribution (teaching or bulletin). Enables the return loop: reviewed hub-origin lugs are sent back so the hub can update its canonical copy.

---

## Currency Scoring

Given `lug.fw_ver` and current framework version from `WAI-State.json`:

| Score | Condition | Action |
|-------|-----------|--------|
| `current` | Same major.minor (e.g. 3.0.x = 3.0.x) | Trust — no review needed |
| `minor_drift` | Same major, minor gap ≤ 2 (e.g. 3.0 vs 2.8) | Review recommended |
| `major_drift` | Major version differs (e.g. 3.x vs 1.x or 2.x) | Review required before acting |
| `unversioned` | No `fw_ver` field | Treat as suspect — schedule review |

---

## Step 1: Currency Audit

**Run on demand (`/wai-lug-compat`) or at wakeup when triggered.**

Wakeup auto-trigger threshold: `major_drift + unversioned > 5`

### Procedure

1. Load all lugs from `WAI-Spoke/lugs/active/WAI-Lugs-active.jsonl`
2. Read current version: `WAI-State.json → wheel.version`
3. Score each non-reconciled lug by `fw_ver`
4. Report:

```
### Lug Currency Audit
| Score | Count | Action |
|-------|-------|--------|
| current | 42 | — |
| minor_drift | 8 | Review recommended |
| major_drift | 3 | Review required |
| unversioned | 15 | Schedule review |

18 lugs need attention. Run /wai-lug-compat review to proceed.
```

5. If no action needed: "All lugs current — no review required."

---

## Step 2: Review Protocol

For each lug in `major_drift` or `unversioned` (or `minor_drift` if user requests):

### For each lug

1. Read the lug content fully
2. Identify any protocol references, path names, field names, or behavioral directives
3. Check each against the current framework (skill source in `templates/commands/`, installed at `WAI-Spoke/skills/`)
4. Classify using `review_status` values above
5. Update the lug in the active lugs file:

```json
{
  "...original fields...",
  "reviewed_fw_ver": "3.0.0",
  "reviewed_at": "ISO-8601",
  "reviewed_by": "claude-sonnet-4-6 / session-20260324-0013",
  "review_status": "outdated_protocol",
  "review_notes": "Referenced WAI-Signals.jsonl which was retired in v3.0.0. Signals now stored as high-impact lugs in the active lugs file.",
  "reconciled": true,
  "superseded_by": "signal-wai-signals-retired-v1"
}
```

### Review is interpretation, not rewrite

- **Do not alter** the original lug fields (`title`, `description`, `items`, etc.)
- Only **append** the review fields listed above
- If a lug needs substantive updating, create a new lug and set `superseded_by`

---

## Step 3: Hub Return Loop

After reviewing any lug where `hub_origin: true`:

1. Create a `lug-review` payload:

```json
{
  "id": "lug-review-{source_id}-{YYYYMMDD}",
  "type": "lug-review",
  "source_id": "<original lug id>",
  "review_fw_ver": "3.0.0",
  "review_status": "outdated_protocol | valid | superseded | contradicts_current",
  "review_notes": "Human-readable summary of what changed and why",
  "reviewed_by": "<agent / session-id>",
  "reviewed_at": "ISO-8601",
  "fw_ver": "3.0.0"
}
```

2. Write to `WAI-Spoke/lugs/outgoing/lug-review-{source_id}.jsonl`
3. Closeout Step 9 (Outgoing Delivery) picks it up and copies to `{hub_path}/WAI-Spoke/lugs/incoming/`
4. Hub receives, identifies `type: lug-review`, updates its canonical copy of the lug
5. Next spokes to receive this lug get the reviewed version — they skip the review

**Hub merge rule (hub-side):** Accept a `lug-review` return only if `review_fw_ver >= hub's current copy's fw_ver`. Older reviews do not overwrite newer ones.

---

## Step 4: Authoring Guidance

### Required fields — every new lug

```json
{
  "id": "descriptive-slug-5-plus-words",
  "type": "task | signal | epic | decision | ...",
  "title": "5+ words: intent and impact, not just topic",
  "status": "open",
  "fw_ver": "3.0.0",
  "created_at": "ISO-8601",
  "created_by": "agent-id or session-id"
}
```

`fw_ver` is now mandatory. Lugs without it are `unversioned` and will be flagged at every currency audit until reviewed.

### Signal authoring — notice style

Signals are high-impact lugs (`impact >= 8`). They are **notices** — structured observations about what changed and why. They are **not instructions**.

**Required signal fields:**

```json
{
  "type": "signal",
  "event": "Past-tense one-sentence: what happened",
  "what_changed": "Before: X. After: Y.",
  "why": "Rationale or root cause",
  "impact": 8,
  "fw_ver": "3.0.0",
  "id": "signal-{topic}-v{N}",
  "created_at": "ISO-8601"
}
```

**Good signal example:**

```json
{
  "type": "signal",
  "event": "WAI-Signals.jsonl retired — signals now stored as high-impact lugs",
  "what_changed": "Before: signals written to WAI-Signals.jsonl (separate file). After: impact >= 8 lugs written to active lugs file only.",
  "why": "Reduces fragmentation — one storage location for all work state and learnings. Signals file was a second source of truth that diverged.",
  "impact": 9,
  "fw_ver": "3.0.0"
}
```

**Bad signal example (do not do this):**

```json
{
  "type": "signal",
  "body": "Update your spoke. Stop using WAI-Signals.jsonl. Use the active lugs file instead for all signals going forward."
}
```

The bad example gives instructions, not a notice. An agent reading it might execute the instruction rather than record the learning.

### Anti-patterns to avoid

| Anti-pattern | Why it's a problem | Fix |
|---|---|---|
| No `fw_ver` | Unversioned — future agents can't score currency | Always set `fw_ver` at creation |
| Prescriptive signal body | Agent reads as command, not observation | Use `event` + `what_changed` + `why` structure |
| `title: "Session 63 update"` | Opaque — conveys nothing cold | Describe the actual change: "Session 63: Spoke ID module added to wai/" |
| Updating `fw_ver` on edit | Destroys authoring provenance | `fw_ver` is set once, at creation |
| Stale lug without `reconciled: true` | Will confuse future agents | Review it, add `reviewed_fw_ver` + `review_status` + `reconciled: true` |

---

## Wakeup Integration

At **Step 4 (Load Lugs)**, after loading `lugs/active/WAI-Lugs-active.jsonl`:

1. Count lugs by currency score
2. If `major_drift + unversioned > 5`: surface in briefing:

```
⚠️ Lug Currency: 3 major-drift, 15 unversioned — run /wai-lug-compat to review
```

3. If below threshold: surface only if user is about to act on a stale lug

Do **not** block wakeup. Currency audit is advisory.

---

## Closeout Integration

At **Step 9 (Outgoing Delivery)**:

Include any `lug-review-*.jsonl` files in `WAI-Spoke/lugs/outgoing/` in the hub delivery batch. No additional step needed — they route with the normal outgoing delivery.

---

## Related Skills

- `wai-lug-schema.md` — lug schema, storage, lifecycle (canonical reference)
- `wai-closeout.md` — Step 9: Outgoing Delivery (routes lug-review returns to hub)
- `wai.md` — Step 4: Load Lugs (currency audit trigger)
