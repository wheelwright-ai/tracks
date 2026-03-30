# Skill: Ozi Work Queue Monitor

**ID:** ozi-work-queue-monitor  
**Type:** orchestrator-extension  
**Lifecycle:** stable  
**Safety Level:** 10  
**Enabled by default:** No

---

## Context

This skill enables Ozi (your Chief of Staff) to actively monitor work queues between wakeup/status checks, not just during them. Without this skill, Ozi only checks the queue when you explicitly run `wai wakeup` or `wai status`.

With this skill enabled, Ozi:
- Watches for new lugs created
- Detects status changes (published → ready → in_progress → complete)
- Identifies stale work (>4hrs no activity)
- Auto-dispatches only when the current session has auto mode enabled
- Auto-triggers verification
- Processes teachings as they arrive

**When to enable:** You want autonomous work management with minimal oversight.  
**When to disable:** You prefer manual control over work assignment.

---

## When to Activate

This skill activates in two scenarios:

### 1. On Every Wakeup/Status Check
Even without daemon mode, this skill adds queue monitoring to:
- `wai wakeup` - Ozi checks queue and dispatches ready work
- `wai status` - Ozi provides queue health check
- `wai closeout` - Ozi processes completed work

Auto-dispatch is session-local. A planning/frontier session can stay observational while a separate builder session enables `/wai-auto-on`.

### 2. Continuous Monitoring (Future: Daemon Mode)
For true "set it and forget it" operation:
```bash
$ wai ozi daemon start    # Future feature
```

---

## Protocol

### Step 1: Scan Work Queue

On wakeup/status, check for work requiring action:

```python
def scan_work_queue():
    """Identify all work needing Ozi's attention"""
    
    queue = {
        # New work ready for assignment
        'ready_for_dispatch': get_lugs(status='ready'),
        
        # Work completed, needs verification
        'ready_for_verification': get_lugs(status='ready_for_recheck'),
        
        # Work verified, needs user acceptance
        'ready_for_acceptance': get_lugs(status='accepted', user_reviewed=False),
        
        # Work blocked, needs user input
        'needs_clarification': get_lugs(status='needs_clarification'),
        
        # Work stale, needs reassignment
        'stale_work': get_lugs(status='in_progress', 
                                updated_before=now() - timedelta(hours=4)),
        
        # Active work (monitoring only)
        'in_progress': get_lugs(status='in_progress', updated_recently=True),
        
        # New teachings to process
        'new_teachings': scan_hub_teachings(processed=False)
    }
    
    return queue
```

### Step 2: Auto-Dispatch Ready Work

For lugs with `status='ready'`, attempt auto-assignment:

```python
def auto_dispatch_ready_work(ready_lugs):
    """Assign ready work to available agents"""
    
    for lug in ready_lugs:
        # Skip high-risk lug types
        if lug['type'] in ['implementation', 'epic', 'review']:
            continue
        
        # Find available builder
        # (For now, we'll use sub-agents via Task tool)
        
        if session_auto_mode_enabled():
            print(f"🚀 Ozi: Dispatching {lug['id']} to sub-agent...")
            
            # Create focused implementation prompt
            prompt = create_implementation_prompt(lug)
            
            # Launch sub-agent
            task_id = launch_subagent(prompt, lug['id'])
            
            # Update lug status
            lug['status'] = 'in_progress'
            lug['workflow'] = {
                'current_owner': f"builder-subagent-{task_id[:8]}",
                'assigned_at': now(),
                'updated_at': now(),
                'task_id': task_id
            }
            save_lug(lug)
            
            log_ozi_action({
                'action': 'auto_dispatched',
                'lug_id': lug['id'],
                'assigned_to': lug['workflow']['current_owner']
            })
```

### Step 3: Process Safe Teachings

For teachings with `safe_to_auto_adopt=true`:

```python
def auto_process_teachings(teachings):
    """Auto-adopt safe teachings"""
    
    for teaching in teachings:
        if teaching.get('safe_to_auto_adopt') == True:
            print(f"✅ Ozi: Auto-adopting {teaching['id']}...")
            
            # Apply teaching
            apply_teaching(teaching)
            
            # Move to processed
            move_to_processed(teaching)
            
            # Log to changelog
            append_changelog({
                'type': 'teaching_adopted',
                'teaching_id': teaching['id'],
                'auto_adopted': True,
                'adopted_by': 'ozi'
            })
        else:
            # Create review lug for user
            create_review_lug(teaching)
```

### Step 4: Generate Briefing

Ozi presents queue status in briefing:

```markdown
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👔 OZI'S BRIEFING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{greeting_based_on_time}! Here's your work queue:

{if completed_work}
🎉 COMPLETED (Since Last Session)
  {list completed work with verification status}
{/if}

{if needs_attention}
❓ NEEDS YOUR ATTENTION
  {list clarifications, reviews, acceptances}
{/if}

{if in_progress}
⚡ IN PROGRESS
  {list active work with health indicators}
{/if}

{if ready_work and session_auto_mode_enabled}
🚀 DISPATCHING NOW
  {list work being auto-assigned}
{/if}

{if ready_work and not session_auto_mode_enabled}
🆕 READY FOR WORK
  {list available work}
  💡 Tip: Enable builder mode with:
     /wai-auto-on
{/if}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Configuration

### Enable/Disable

```bash
# Enable Ozi work queue monitoring
$ wai skill enable ozi-work-queue-monitor

✅ Ozi work queue monitoring ENABLED
I'll now watch for new work and dispatch autonomously.

# Disable (back to manual)
$ wai skill disable ozi-work-queue-monitor

Ozi work queue monitoring DISABLED.
Work assignment is now manual.
```

### Check Status

```bash
$ wai-auto-status

Ozi Work Queue Monitor:
  Status: ENABLED
  Auto mode: ACTIVE FOR THIS SESSION
  
  Current Queue:
    Ready: 2 lugs
    In Progress: 3 lugs
    Ready for Verification: 1 lug
    Ready for Acceptance: 2 lugs
    Needs Clarification: 0 lugs
```

---

## Integration with Wakeup Protocol

This skill integrates into wakeup Step 1b:

**Without this skill:**
```
Step 1: Load WAI-State.json
Step 2: Check hub for teachings
Step 3: Show briefing
```

**With this skill:**
```
Step 1: Load WAI-State.json
Step 1b: 🆕 Ozi scans work queue
         - Identifies ready work
         - Auto-dispatches if this session enabled auto mode
         - Processes safe teachings
         - Generates queue briefing
Step 2: Check hub for teachings (handled by Ozi)
Step 3: Show Ozi's briefing
```

---

## Success Metrics

Track Ozi's effectiveness:

```bash
$ wai ozi stats

Ozi Work Queue Monitor Stats (Last 7 Days):
  
  Auto-dispatched: 23 lugs
  Auto-adopted teachings: 5
  Reassigned stale work: 2
  Triggered verifications: 18
  
  Average time to assignment: 12 minutes
  User intervention rate: 8%
  
  Efficiency: 92% autonomous
```

---

## Use Cases

### Immediate: Canonical Evolution Backlog

```
Current state:
- impl-idempotent-closeout-concurrency-v1 (ready, downscoped)
- bug-validation-errors-14 (needs creation)
- Plus epic backlog

With Ozi enabled:
$ wai wakeup

Ozi: "Good morning! I see:
      - 1 implementation lug ready (impl-idempotent-closeout)
      - Canonical evolution backlog
      
      Want me to start working on these? [Y/n]"

User: "Yes"

Ozi: "🚀 Dispatching impl-idempotent-closeout to sub-agent...
      I'll notify you when ready for verification."

[3 hours later]

Ozi: "✅ impl-idempotent-closeout completed!
      Ready for your acceptance testing."
```

---

## Future Enhancements

### Daemon Mode (Phase 2)
Continuous background monitoring:
```bash
$ wai ozi daemon start
```

### Smart Scheduling (Phase 3)
Ozi learns optimal dispatch times:
- High-priority work during business hours
- Long-running work overnight
- Testing during low-activity periods

### Multi-Project Coordination (Phase 4)
Ozi manages work across all your spokes:
```bash
$ wai ozi --all-projects

Ozi: "Scanning 5 projects...
      - framework: 3 ready
      - waiweb: 2 ready
      - scribe: 1 ready
      
      Total: 6 items ready for dispatch"
```

---

## Relationship to Core Ozi

**Ozi (Built-in):**
- Always present as orchestrator identity
- Coordinates guards
- Generates briefings
- Responds to commands

**This Skill (Optional):**
- Adds active queue monitoring
- Enables autonomous dispatch
- Processes work automatically

Think of it as: "Base Ozi" vs "Ozi with work queue autopilot"

---

Use `/wai-auto-on`, `/wai-auto-off`, `/wai-auto-status`, and `/wai-auto-parallel <n>` to control session-local builder behavior.

*"I'm watching the queue. I've got this handled." - Ozi*
