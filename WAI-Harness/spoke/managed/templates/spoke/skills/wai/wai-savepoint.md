# Skill: WAI Savepoint (Spoke Copy)

## Spoke-Local Savepoint Steps

This file contains spoke-specific savepoint instructions. The main savepoint protocol
lives at `templates/commands/wai-savepoint.md`.

### 8b. Live-Clone the Session Transcript Archive

As part of the savepoint (after the brief is regenerated, before the staging buffer is
written), refresh this session's near-full transcript clone (file-dumps stripped) into the
local, gitignored archive so a paused/interrupted session still leaves a durable
ground-truth record of its reasoning and work. Cheap incremental (watermarked); best-effort;
never blocks the savepoint.

```bash
TOOLS=$([ -d WAI-Harness/spoke/managed/tools ] && echo WAI-Harness/spoke/managed/tools || echo tools)
python3 "$TOOLS/session_transcript_archive.py" --clone current --spoke-root . 2>/dev/null || true
```

The clone lands in `WAI-Harness/spoke/local/archive/transcripts/live/<sessionId>.jsonl`
(local + gitignored — never committed, never bubbled to hub). It is promoted to a write-once
`closed/` archive at `/wai-closeout`.
