#!/bin/bash
# session-end-lane.sh — release THIS session's lane the moment the session ends.
# (impl-lane-registry-liveness-authority)
#
# THE MISSING TRANSITION. Lanes had a birth (SessionStart) and a heartbeat, but no
# death: unregistration lived ONLY in stop-savepoint-guard.sh, gated behind an explicit
# converge request. A clean, ordinary exit therefore left a LIVE lane behind until the
# 12h TTL expired. MEASURED: an 11.4h ghost lane with zero live processes — every peer
# session saw a phantom peer and isolated (or refused to commit) against nobody.
#
# SessionEnd is the event that closes that loop. Wired with matcher "*" (the documented
# "match all" form) so EVERY termination reason releases the lane — clear, resume,
# logout, prompt_input_exit, bypass_permissions_disabled, other, and any reason added
# later. Enumerating reasons would silently leak a lane on the one we forgot.
#
# Unregistering is safe on `resume`/`clear` (SessionEnd fires with those reasons): the
# session is not live at that instant, and SessionStart re-registers on its matching
# resume/clear source. A lane that comes back is correct; a lane that never leaves is not.
#
# Always exits 0: a session must never fail to end because of a bookkeeping hook.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# Drain the payload so the pipe never blocks; `timeout` guards a no-stdin invocation.
_SE_INPUT=$(timeout 2 cat 2>/dev/null || true)
_SE_SID=$(printf '%s' "$_SE_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
_SE_TRANSCRIPT=$(printf '%s' "$_SE_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)
[ -z "$_SE_SID" ] && [ -n "$_SE_TRANSCRIPT" ] && _SE_SID=$(basename "$_SE_TRANSCRIPT" .jsonl)
[ -z "$_SE_SID" ] && exit 0   # no lane key -> nothing to release

# Resolve the data-plane base the same way the other data hooks do: v4 canon when the
# v4 tree is present, v3 otherwise. (Cheap on-disk inference — this hook must not depend
# on harness_mode.sh being sourceable at teardown.)
if [ -d "$PROJECT_DIR/WAI-Harness" ]; then BASE="$PROJECT_DIR/WAI-Harness/spoke/local"
else BASE="$PROJECT_DIR/WAI-Spoke"; fi

WG="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/worktree_guard.py"
[ -f "$WG" ] || exit 0

# UNCONDITIONAL: no converge gate, no dirty-tree condition, no "only if we registered".
# The lane is this session's claim on the working tree; the session is over, so the claim
# is over. Any work worth keeping was captured by the Stop-hook savepoint/track flush,
# which run before this.
_SE_ERR=$(mktemp 2>/dev/null || echo /tmp/wai-session-end-lane-err.$$)
if ! python3 "$WG" lane-unregister --base "$BASE" --session "$_SE_SID" >/dev/null 2>"$_SE_ERR"; then
  # LOUD degrade (never `2>/dev/null || true`): a lane we failed to release becomes a
  # ghost that makes every future session think a peer is holding this tree. Name it so
  # a human can clear it, and say exactly how.
  echo "[WAI] DEGRADED: lane-unregister FAILED for session $_SE_SID — $(head -c 300 "$_SE_ERR" 2>/dev/null | tr '\n' ' ')" >&2
  echo "[WAI] This lane may linger as a GHOST (peers will see a phantom live session until its heartbeat goes stale). Clear it with: python3 $WG lane-unregister --base $BASE --session $_SE_SID" >&2
fi
rm -f "$_SE_ERR" 2>/dev/null
exit 0
