#!/usr/bin/env bash
# Pre/PostToolUse hook for the AskUserQuestion tool.
#
# WHY THIS EXISTS: a pending AskUserQuestion's tool_use record is NOT flushed to the
# transcript JSONL until the turn completes (i.e. AFTER you answer). Proven by polling
# the transcript during a 1m43s pending window: size frozen, no pending record on disk.
# So `basher lens` cannot detect a pending question by parsing the transcript — by the
# time it lands it is already answered. This hook is the ONLY real-time source of the
# questions + options while the prompt is open: PreToolUse fires BEFORE you answer with
# the full tool_input, so we snapshot it to a per-pane sidecar lens polls (the same
# pattern notify.sh uses for permission prompts). PostToolUse clears it once answered;
# UserPromptSubmit (notify-reset.sh) is the backstop for reject/interrupt.
set -euo pipefail

STDIN=$(cat)
PANE="${ZELLIJ_PANE_ID:-0}"
SIDE="/tmp/claude-sessions/pending-question-${PANE}.json"
EVENT=$(printf '%s' "$STDIN" | jq -r '.hook_event_name // empty' 2>/dev/null || echo "")

# PostToolUse = the question was answered → clear the sidecar.
if [ "$EVENT" = "PostToolUse" ]; then
    rm -f "$SIDE" 2>/dev/null || true
    exit 0
fi

# PreToolUse = a question is about to be shown → snapshot questions + options.
# json.dumps so free-text option labels never produce unparseable JSON.
mkdir -p /tmp/claude-sessions 2>/dev/null || true
python3 - "$SIDE" "$STDIN" <<'PY' 2>/dev/null || true
import json, sys, time
side, raw = sys.argv[1], sys.argv[2]
try:
    d = json.loads(raw)
except Exception:
    sys.exit(0)
qs = ((d.get("tool_input") or {}).get("questions")) or []
segs, opts = [], []
for qi, q in enumerate(qs):
    if not isinstance(q, dict):
        continue
    hdr = (q.get("header") or q.get("question") or "decision").strip()
    o = [x.get("label", "") for x in (q.get("options") or []) if isinstance(x, dict)]
    o = [x for x in o if x][:4]
    if qi == 0:
        opts = o                       # first question's labels feed the [a] reply chooser
    segs.append((hdr + ((": " + " / ".join(o)) if o else "")).strip())
text = "  ·  ".join(segs) if segs else "waiting for your decision"
json.dump({"text": text, "segs": segs, "opts": opts, "ts": int(time.time())}, open(side, "w"))
PY
exit 0
