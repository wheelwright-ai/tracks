# Command: Stewardship Advisor

Run this advisor when proposed work appears to change:
- project identity
- in-scope or out-of-scope boundaries
- foundational constraints
- the declared purpose of the wheel

## Behavior

1. Compare requested work against `WAI-State.json` and `WAI-State.md`
2. Identify whether the request is within foundation, an edge case, or clear drift
3. If drift is detected:
   - explain the mismatch
   - present the proposed evolution plainly
   - require explicit acknowledgment before proceeding
4. If the request is within scope:
   - stay silent or note that it is aligned

## Override Model

This advisor inherits default settings from `Skills/advisors/SKILL.md`.

Local `advisor.json` overrides:
- exposure
- watcher patterns
- mode sensitivity
- safety level
