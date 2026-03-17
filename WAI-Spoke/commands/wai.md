# WAI Wakeup - v2 Protocol (10 Steps)

## Overview

Execute the 10-step wakeup protocol to initialize the spoke, discover new teachings, and get ready for work.

---

## Step 1: Load WAI-State.json

Load the spoke's technical spec, foundation, and session state:

```bash
cat WAI-Spoke/WAI-State.json
```

Key sections to check:
- `_project_foundation` - Project identity, boundaries, approach
- `_session_state` - Last session info, session count
- `_auto_implementation` - Auto-execution settings (if exists)

---

## Step 2: Load WAI-State.md

Load the strategic context and vision:

```bash
cat WAI-Spoke/WAI-State.md
```

This complements the technical spec in WAI-State.json.

---

## Step 3a: Auto-Discovery of New Hub Teachings

Poll the hub's teachings folder to discover new framework updates:

```bash
# Scan hub/framework/*.teaching
ls -1 /home/mario/projects/wheelwright/hub/framework/*.teaching 2>/dev/null | wc -l
```

For each teaching in hub/framework/:
1. Check if already adopted (exists in WAI-Spoke/seed/processed/)
2. If new, add to discovery queue
3. If `safe_to_auto_adopt: true`, mark for auto-adopt
4. If `safe_to_auto_adopt: false` or not set, prompt for approval

**Display discovery queue:**
```
### Teaching Discovery from Hub
🎯 {count} new teachings found
🔒 Auto-Adopt: {enabled|disabled}

Queue:
- ✅ teaching-1 - {title} (safe: true)
- ✅ teaching-2 - {title} (safe: true)
- ⚠️  teaching-3 - {title} (safe: false)
```

---

## Step 3: Load Skills

Load active skills from WAI-Skills.jsonl:

```bash
cat WAI-Spoke/WAI-Skills.jsonl
```

Report any active advisory watches and skills that recommend themselves at session start.

---

## Step 4: Load Lugs and Signals

Load active work and learnings:

```bash
cat WAI-Spoke/WAI-Lugs.jsonl
cat WAI-Spoke/WAI-Signals.jsonl
```

---

## Step 5: Display Briefing

Show unified WAI Point briefing:
- Project identity and phase
- Current environment
- Active work (prioritized backlog)
- Context health (tokens, hub, git)
- Recent high-impact changes
- Next actions

---

## Step 6: Auto-Implementation Queue

Check for auto-implementation work:

If `_auto_implementation.enabled == true`:
- Build queue from WAI-Lugs.jsonl
- Sort by natural priority (bugs > flagged > tasks)
- Display queue in awareness mode

```
### Auto-Implementation Queue (Awareness Mode)
🎯 {count} items in queue
🔒 Auto-Implement: {enabled|disabled}

Queue (confidence = N/10):
- 🔴 bug-001 - Fix authentication (conf: 9)
- 🟡 feature-002 - Add payment processing (conf: 6) [review]
- 🟢 task-001 - Update API docs (conf: 8)
```

---

## Step 6.1: Interactive Review (Low-Confidence Work)

For low-confidence items (confidence < 8), provide interactive review:

1. Show analysis
2. Offer 6 options:
   - [1] 🚀 Approve with current confidence
   - [2] ⬆️ Improve + Approve
   - [3] 🔍 Request review
   - [4] ⏸️ Defer
   - [5] ❌ Reject
   - [6] ⚙️  Override

---

## Step 7: Session Check

Check session state:
- `last_modified_by` / `last_modified_at`
- `requires_review` - surface reason if true
- `session_count` - increment on significant update

---

## Step 8: Environment Detection

Auto-detect environment:
- Tool (claude-code, cursor, etc.)
- Machine (hostname or WAI_MACHINE env var)
- OS
- Parent session (WAI_PARENT_SESSION)

Scan WAI-Spoke/sessions/ to surface recent activity from other tools/machines.

---

## Step 9: Initialize Session Track

Create session tracking:

```bash
# Create session directory
SESSION_DIR="WAI-Spoke/session-$(date +%Y%m%d-%H%M)"
mkdir -p "$SESSION_DIR"

# Initialize track.jsonl
touch "$SESSION_DIR/track.jsonl"
```

---

## Step 10: Ready Prompt

After completing all steps, ask:

"Wake complete. Ready to work. What would you like to do next?"

---

## Multi-Environment Sessions

Each environment (tool + machine) gets its own session log:
```
WAI-Spoke/sessions/
  claude-code-laptop.jsonl
  cursor-desktop.jsonl
```
