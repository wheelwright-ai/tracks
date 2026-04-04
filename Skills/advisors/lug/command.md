# Command: Lug Advisor

Run this advisor when work may be landing in the wrong lug or moving through a
lug lifecycle incorrectly.

## Watch For

- tasks recorded in the wrong queue or missing a queue entirely
- lifecycle state that no longer matches the actual work
- new work that should be durable but is staying only in chat
- stale lug items that block routing confidence or handoff clarity

## Behavior

1. Identify the routing or lifecycle mismatch.
2. Name the likely correct durable destination.
3. Recommend the smallest update that restores tracking integrity.
4. Stay quiet when the current lug state already matches the work.
