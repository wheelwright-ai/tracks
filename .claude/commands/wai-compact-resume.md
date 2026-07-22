# WAI Compact Resume — Post-Compaction Recovery Protocol

**Trigger:** Context compaction just occurred (`<wai-post-compact>` block in context, or you notice working context is lost).

**Goal:** Restore full WAI awareness in ≤2 tool calls. Compaction is survivable — not catastrophic.

---

## Recovery Sequence

### Resolve the active harness base FIRST (harness-mode-aware)

Resolve these once; every path below is relative to them, so this works on v4-only
(`WAI-Harness/spoke/local`), v3-only (`WAI-Spoke`), and coexist spokes alike.

```bash
BASE=$(python3 WAI-Harness/spoke/managed/tools/wai_paths.py --root . --json 2>/dev/null \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('_base') or '')")
[ -z "$BASE" ] && { [ -d WAI-Harness/spoke/local ] && BASE="WAI-Harness/spoke/local" || BASE="WAI-Spoke"; }
TOOLS="WAI-Harness/spoke/managed/tools"; [ -d "$TOOLS" ] || TOOLS="tools"
```

Do NOT hardcode `WAI-Harness/spoke/` — on a v4-only spoke it does not exist. Use `{BASE}/…` for data-tree paths and `{TOOLS}/…` for tools.

**Step 0 — Read the resume pointer FIRST (1 tool call, often all you need):**

```
Read: {BASE}/runtime/compact-resume.json
```

Written by `pre-compact.sh` at the moment of compaction. Carries the live facts a
compacted session loses: `session_id`, `lane_track_path`, `base`, `active_initiative_id`,
`focus_lock`, `savepoint_status`, and the most-recent `in_progress_lug_ids` (with
`in_progress_total`). If present, you already have session id + track path — skip straight
to Step 2 (read the track). If absent (older compaction, or the file was never written),
fall through to Step 1.

**Step 1 — Read WAI-State.json (1 tool call):**

```
Read: {BASE}/WAI-State.json
```

Extract:
- `_session_state.track_path` — path to session track (e.g. `{BASE}/sessions/session-XXXX/track.jsonl`)
- `_session_state.next_session_recommendation` — what was planned next
- `_savepoint` — if `status == "pending"`, a savepoint is active; read `lug_id` + `resume_note`
- `_session_state.last_session_id` — current session name

**Step 2 — Read recent track entries (1 tool call):**

```
Read: {track_path from Step 1}  (last 10 lines)
```

Look for: last action, `open` items, in-progress lug IDs, any `completed: true` markers.

**Done.** You are now WAI-aware. Proceed with the work that was in progress.

---

## If Mid-Closeout

Re-invoke `/wai-closeout` — it's idempotent. The track shows the last completed step.

---

## Compaction Survival Matrix

| Artifact | Survives? | Why |
|----------|-----------|-----|
| CLAUDE.md | **YES** | System-level injection — re-loaded every turn |
| MEMORY.md | **YES** | System-level injection — re-loaded every turn |
| Per-turn UserPromptSubmit reminders (ledger, track heartbeat) | **YES** | UserPromptSubmit fires every turn |
| `<wai-compact-resume>` / `<wai-post-compact>` injection | **YES** | SessionStart `compact` matcher + the flag path fire once after compaction |
| Full SessionStart wakeup briefing | **NO** | Does NOT re-fire on compaction — only the light compact-resume injector runs (a compacted session is not a new session; wakeup-canonical is deliberately not re-invoked) |
| `compact-resume.json` pointer | **YES** | Filesystem — written by `pre-compact.sh`, read at Step 0 |
| WAI-State.json | **YES** | Filesystem — read on resume |
| Lugs (all statuses) | **YES** | Filesystem — read on resume |
| Skill file bodies | **NO** | Context only — re-invoke to restore |
| Track ledger entries | **NO** | Compressed away — read last N lines |
| Tool output context | **NO** | Compressed away |
| In-session reasoning | **NO** | Compressed away |

**Key insight:** The filesystem always survives compaction. Only the conversation context is compressed — and the full wakeup briefing does **not** re-run, so do not wait for it. Recovery means reading `compact-resume.json` + the track — not starting over, and not re-waking.

---

## What Each Infrastructure Piece Does

| Component | Purpose | Compaction-specific? |
|-----------|---------|----------------------|
| `pre-compact.sh` | Writes `compacted.flag` + `compact-resume.json` (live pointers) + a summary hint | YES |
| `compact-resume.json` in `{BASE}/runtime/` | Persisted pointers (session/track/initiative/lugs) — read at Step 0 | YES |
| `compact-resume-inject.sh` (SessionStart `compact`) | Light injector — emits `<wai-compact-resume>` with pointers; does NOT re-run wakeup | YES |
| `compacted.flag` in `{BASE}/runtime/` | Signals post-compaction to next turn's hook (belt-and-braces path) | YES |
| `<wai-post-compact>` / `<wai-compact-resume>` block | Re-orients Claude after compaction; names `/wai-compact-resume` | YES |
| CLAUDE.md Critical Rules "survive compaction" | Documents what survives | YES |
| Session guard (`session-guard.json`) | General session hygiene (also helps post-compaction) | NO |
| Ledger turn reminders | General session hygiene (also helps post-compaction) | NO |
