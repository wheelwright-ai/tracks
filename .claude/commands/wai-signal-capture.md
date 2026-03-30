# WAI Signal Capture

Detect and log high-impact decisions and learnings during the session.

## Instructions

During the session, watch for decisions or learnings with impact >= 8:

**Triggers for signal detection:**
- Architectural decisions (how something is built)
- Direction changes (what we're building)
- Protocol establishment (how we work)
- Significant discoveries (what we learned)
- Permanent constraints adopted

**When detected**, log to `WAI-Spoke/lugs/active/WAI-Lugs-active.jsonl` as a signal lug (canonical model — `WAI-Signals.jsonl` is retired):

```json
{
  "id": "signal-<YYYYMMDD-HHMM>-<brief-slug>",
  "type": "signal",
  "title": "<what was decided/learned>",
  "impact": "<8-10>",
  "rationale": "<why it matters>",
  "created_by": "<who decided>",
  "created_at": "<iso>",
  "session_id": "<current session>"
}
```

**At session end** (closeout), surface all signals:
```
📡 High-Impact Signals This Session:
- [signal summary] (impact: X)
  → Logged to active lugs file
```

**Impact scale:**
- 10: Fundamental direction change
- 9: Major architectural decision
- 8: Significant protocol or pattern established
- < 8: Normal decisions, no signal needed

### Proactive Logging

Don't wait for user to ask — log signals as they happen. The user can review
and remove any that don't warrant permanent record.

## Context

This skill replaces the "Signaling High-Impact Learnings" section previously in WAI-Guide.md.

**Why signals matter**: High-impact decisions captured in real-time become the
institutional memory that makes AI context persistence valuable. Without signals,
important choices are lost between sessions.
