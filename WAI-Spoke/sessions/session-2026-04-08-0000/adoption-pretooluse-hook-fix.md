# Teaching Applied: PreToolUse Hook Fix

**Teaching:** signal-20260407-2255-from-minder.md.teaching
**Applied:** 2026-04-08
**Issue:** PreToolUse hooks must not output JSON to stdout on allow — causes hook error messages

## Summary
Applied rule about PreToolUse hook behavior:
- Allow: exit 0 (no stdout, no JSON)
- Block: exit 2 + stderr only
- Add 2>/dev/null to all jq calls in hook scripts

**Current spoke status:** No PreToolUse hook found in .claude/hooks/ - this rule is documented for future use when hook exists.

**Status:** APPLIED (rule documented)