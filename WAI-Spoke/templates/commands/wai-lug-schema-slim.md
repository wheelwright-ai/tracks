# WAI Lug Schema — Fast Path

> Full protocol: load `wai-lug-schema.md` for deep schema, PEV chains, spec lugs, execute-when gates.

**80% case: creating or updating a lug.** Use this file for quick reference.

---

## Storage Paths

```
WAI-Spoke/lugs/bytype/{type}/{status}/{id}.json
```

| Status | Path |
|--------|------|
| New | `bytype/{type}/open/{id}.json` |
| Active | `bytype/{type}/in_progress/{id}.json` |
| Done | `bytype/{type}/completed/{id}.json` |

---

## Essential Fields (every lug)

```json
{
  "id": "epic-name-20260101",
  "type": "task",
  "status": "open",
  "title": "5+ word descriptive title explaining intent or impact",
  "created_at": "2026-05-26T00:00:00Z",
  "gb": "claude-sonnet-4-6",
  "fw_ver": "3.0.0",
  "impact": 7,
  "effort": 2,
  "urgency": 3,
  "routed_to": "LOCAL",
  "model_fit": "haiku",
  "va": "build",
  "perceive": ["What to read before starting"],
  "execute": ["Concrete numbered steps"],
  "verify": ["How to confirm done"]
}
```

---

## Type Quick Reference

| Type | Use for |
|------|---------|
| `task` | Work item |
| `bug` | Defect |
| `feature` | New capability |
| `epic` | Multi-session effort |
| `implementation` | Non-trivial execution batch |
| `signal` | User-action-required alert → write to hub inbox |
| `spec` | Living behavior documentation |
| `session-summary` | End-of-session record |

---

## Routing

| Value | Meaning |
|-------|---------|
| `LOCAL` | This spoke only |
| `FRAMEWORK` | Framework-level change |
| `SPOKE/{id}` | Another spoke |

Signals: write directly to `{hub_path}/WAI-Hub/signals/inbox/` — do NOT use `routed_to`.

---

## ID Generation

```
id = sha256(title)[:12]
# Named: "epic-slimdown-20260227", "lug-fnd-abc12345"
```

---

## Key Defaults

| Field | Default |
|-------|---------|
| `urgency` | 3 (NORMAL) |
| `model_fit` | `"haiku"` |
| `impact` | `5` |
| `effort` | `2` |
| `routed_to` | `"LOCAL"` |

**`gb` must be the actual model ID** (e.g. `claude-sonnet-4-6`) — never a name or alias.

---

## Lifecycle Move Commands

```bash
# Open → in_progress
mv WAI-Spoke/lugs/bytype/task/open/{id}.json WAI-Spoke/lugs/bytype/task/in_progress/{id}.json

# in_progress → completed
mv WAI-Spoke/lugs/bytype/task/in_progress/{id}.json WAI-Spoke/lugs/bytype/task/completed/{id}.json
```
