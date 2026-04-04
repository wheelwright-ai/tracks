# Command: Context Advisor

Run this advisor when the session may be losing, fragmenting, or overloading
working context.

## Watch For

- long threads with unresolved decisions or hidden assumptions
- work that depends on details not yet written to durable state
- handoffs that would force the next agent to reconstruct intent
- task switches that may strand important in-flight context

## Behavior

1. Identify what context is at risk.
2. Recommend the lightest useful preservation step.
3. Prefer checkpoints, compact summaries, or track output over raw repetition.
4. Highlight resume blockers before they become handoff failures.
