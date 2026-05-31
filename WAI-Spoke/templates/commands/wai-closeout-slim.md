# WAI Closeout — Fast Path

> Full protocol: load `wai-closeout.md` for delta ceremony detection, Wave 1/2 dispatch, teaching generation, telemetry, full step details.

**Standard ceremony** — covers 90% of sessions. Run these steps in order.

---

## Pre-Flight

```bash
# Check intent
cat WAI-Spoke/runtime/session-intent.json 2>/dev/null || echo "no intent"
```

| intent | ceremony |
|--------|----------|
| `closeout` | Minimal: skip steps 8, 9b, 9c |
| any other | Standard: run all |

---

## Step 2. Intent Gate + Disruption Init

```bash
DISRUPTIONS=()
```

## Step 3. Incomplete Work Capture

Document: status, what's done, what remains, blockers, files. Store in session-summary `incomplete_work`.

## Steps 4–5. Run Closeout Script

```bash
tools/closeout.sh --modified-by {model_id} --track-path {current_track_path}
```

Set `outcome` on each completed lug before archival: `shipped` | `shipped_with_rework` | `abandoned` | `superseded`

Update WAI-State.json:
- `_session_state.next_session_recommendation`
- `_session_state.track_path`

## Step 6. Finalize Session Track

Append terminal entry to `track.jsonl`:
```json
{"event": "closeout", "completed": true, "session_id": "{session_id}", "ts": "{ISO-8601}", "phase": "review", "session_number": N}
```

Append final row to `wai_track_ledger.md`:
```
| {n} | {HH:MM UTC} | closeout | Session closed — {N} turns, {lug_count} lugs worked |
```

## Step 7. CHANGELOG.md

Update CHANGELOG.md if applicable. Generate commit message.

## Step 8. Lug Dogfooding

For each lug created/modified: PEV present? verify testable? verify recorded as run? Flag gaps.

## Step 9. Outgoing Delivery

Scan `WAI-Spoke/lugs/outgoing/` for undelivered lugs. Pre-delivery quality check. Deliver to target spokes.

## Step 9b. Teaching Generation

If teaching-worthy changes: generate to `teachings/`. Run `test-bench/teaching-verify.sh`. If hub connected: publish.

## Step 10. Skill Sync

```bash
\cp templates/commands/*.md .claude/commands/
```

## Step 11. Commit + Push

```bash
git add -A
git commit -m "{type}: {summary}

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main
```

---

## Disruption Lug (if any step failed)

If `DISRUPTIONS` is non-empty, create a task lug with `title: "Closeout disruption: {steps}"` before committing.
