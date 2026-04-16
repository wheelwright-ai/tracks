#!/bin/bash
#
# wai-exit.sh — WAI post-tool wrapper
#
# Runs after the AI tool exits. Regenerates wakeup-brief.json so the
# next wai-enter.sh always finds a fresh brief regardless of how the
# session ended (clean closeout, interrupt, or crash).
#
# Called automatically by wai-enter.sh after the tool exits.
# Can also be run manually after any session.
#
# Usage:
#   ./wai-exit.sh
#

PROJECT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

# Silent no-op if not a WAI project
[[ -f "$PROJECT_DIR/WAI-Spoke/WAI-State.json" ]] || exit 0

echo "[wai-exit] Closing session..."

# ── 1. Regenerate brief for next session ────────────────────────────────────
if [[ -f "$PROJECT_DIR/tools/generate_wakeup_brief.py" ]]; then
    if python3 "$PROJECT_DIR/tools/generate_wakeup_brief.py"; then
        echo "[wai-exit] Brief: ready for next session"
    else
        echo "[wai-exit] Brief: generation failed"
    fi
else
    echo "[wai-exit] Brief: generator not found — skipping"
fi

# ── 2. Refresh context feeds in background ──────────────────────────────────
if [[ -f "$PROJECT_DIR/tools/advisor_context_refresh.py" ]]; then
    mkdir -p "$HOME/.claude/logs"
    python3 "$PROJECT_DIR/tools/advisor_context_refresh.py" \
        --quiet --spoke-path "$PROJECT_DIR" \
        >> "$HOME/.claude/logs/context-refresh-$(date +%Y%m%d).log" 2>&1 &
    echo "[wai-exit] Feeds: refresh running in background"
fi

echo "[wai-exit] Done. Next wakeup will use fast path."
