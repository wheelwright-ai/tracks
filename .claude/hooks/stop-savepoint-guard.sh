#!/bin/bash
# stop-savepoint-guard.sh — Stop-hook safety net for the savepoint EXISTENCE guarantee.
# (impl-savepoint-loss-safety-net-v1, spec-savepoint-resume-contract-v1)
#
# v4 guarantees a savepoint's QUALITY once written, but nothing guaranteed one got
# written at all — savepoint creation lived only in /wai-closeout, which a session
# can skip (context blowout, abandon, /clear, crash). This hook, on every Stop,
# auto-ejects a DEGRADED-but-DURABLE savepoint when the session ends with unfinished
# work and none exists yet. Idempotent + non-blocking: always exits 0.
#
# Harness-mode-aware: sources harness_mode.sh to resolve the active root, then locates
# auto_eject_savepoint.py in the v4 managed tools (canonical) or the v3 tools/ (dogfood).

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
# Capture the Stop payload (drains the pipe so it never blocks). The CC session_id /
# transcript basename is this session's lane key — used below to auto-eject against
# THIS session's track, not whichever session dir is newest by mtime.
_SPG_INPUT=$(cat 2>/dev/null)
_SPG_SID=$(printf '%s' "$_SPG_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
_SPG_TRANSCRIPT=$(printf '%s' "$_SPG_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)
[[ -z "$_SPG_SID" && -n "$_SPG_TRANSCRIPT" ]] && _SPG_SID=$(basename "$_SPG_TRANSCRIPT" .jsonl)

emit() {  # $1 = message. Surface a session-end notice via the top-level `systemMessage`
  # field — the schema-valid Stop-hook channel for a user-facing notice. (NOT a bare
  # `hookSpecificOutput` string, which fails validation; and NOT `additionalContext`,
  # which would re-engage the model on a session that is ending.)
  _SPG_MSG="$1" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
print(json.dumps({"systemMessage": os.environ.get("_SPG_MSG", "")}))
PYEOF
}

# Resolve the DATA-plane tree the SAME way stop-track-flush.sh does (I-2 fix). The
# savepoint floor must protect the tree where the live session ledger + savepoints
# actually get written. In coexist that is v3 (WAI-Spoke), NOT HARNESS_ACTIVE — which
# defaults to v4 for managed-tooling currency and would make this guard protect the
# STALE migrated tree. Sourcing harness_mode.sh exports HARNESS_V3/V4/MODE/ACTIVE/ROOT;
# an explicit WAI_HARNESS_MODE override still wins (v4-only forced regression test).
HM="$PROJECT_DIR/.claude/hooks/harness_mode.sh"
if [[ -f "$HM" ]]; then
  # shellcheck disable=SC1090
  source "$HM" "$PROJECT_DIR"
else
  # Degraded fallback: infer presence from on-disk dirs.
  HARNESS_V3=0; HARNESS_V4=0
  [[ -d "$PROJECT_DIR/WAI-Spoke" ]]   && HARNESS_V3=1
  [[ -d "$PROJECT_DIR/WAI-Harness" ]] && HARNESS_V4=1
fi

# Data-plane selection. Follow HARNESS_ACTIVE — the MARKER-AWARE resolution from
# harness_mode.sh — NOT a local "any WAI-Spoke/ dir => v3" re-derivation.
#
# The old re-derivation (HARNESS_V3==1 => DATA_ACTIVE=v3) was the SAVEPOINT
# PHANTOM-RECREATOR: a CUTOVER spoke (activated to v4) that still carries a lingering
# WAI-Spoke/ husk would auto-eject its savepoint INTO that v3 husk, perpetually
# re-growing the phantom (basher, keeping-open-lines — flagged BROKEN by
# contract_validate "auto-eject leaked to v3"). harness_mode.sh already resolves this
# correctly: in coexist it stays v3 UNTIL the spoke is activated (.activated marker or a
# v4 local/WAI-State.json), then flips to v4 — so a genuine overlap spoke keeps writing
# v3 (no data loss) while a cutover-with-husk spoke writes v4 (no phantom). That is
# exactly the data plane the savepoint floor must protect, so adopt it directly.
# An explicit WAI_HARNESS_MODE override still wins (forced regression test); the degraded
# no-harness_mode.sh fallback prefers v4 when present.
DATA_ACTIVE=""
case "${WAI_HARNESS_MODE:-}" in
  v4) [[ "$HARNESS_V4" == 1 ]] && DATA_ACTIVE=v4 ;;
  v3) [[ "$HARNESS_V3" == 1 ]] && DATA_ACTIVE=v3 ;;
esac
if [[ -z "$DATA_ACTIVE" ]]; then
  if   [[ -n "${HARNESS_ACTIVE:-}" && "$HARNESS_ACTIVE" != "none" ]]; then DATA_ACTIVE="$HARNESS_ACTIVE"
  elif [[ "$HARNESS_V4" == 1 ]]; then DATA_ACTIVE=v4
  elif [[ "$HARNESS_V3" == 1 ]]; then DATA_ACTIVE=v3
  else exit 0; fi
fi

# Working base (where sessions/ + savepoints/ live for the data-plane mode).
if [[ "$DATA_ACTIVE" == v4 ]]; then BASE="$PROJECT_DIR/WAI-Harness/spoke/local"; else BASE="$PROJECT_DIR/WAI-Spoke"; fi

# Locate the tool: v4 managed canon first, then v3 dogfood copy.
TOOL=""
for cand in "$PROJECT_DIR/WAI-Harness/spoke/managed/tools/auto_eject_savepoint.py" "$PROJECT_DIR/tools/auto_eject_savepoint.py"; do
  [[ -f "$cand" ]] && TOOL="$cand" && break
done
[[ -z "$TOOL" ]] && exit 0

# Resolve THIS session's wai_session via its lane (idempotent LOOKUP, never a create).
# Falls back to the newest session dir only when no lane key is available (older CC /
# direct run) or the lane is genuinely gone.
#
# --no-create is LOAD-BEARING (impl-lane-registry-liveness-authority): this is a Stop
# hook — a pure HEARTBEAT — and a heartbeat must NEVER mint a lane. Without the flag,
# lane-resolve aliases lane-register with create=True, so this hook RESURRECTED a lane
# for a session that had just ended (and re-created it after a SessionEnd unregister),
# which is one of the ways a ghost lane held the tree for hours.
SESSION=""
_WG="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/worktree_guard.py"
if [[ -n "$_SPG_SID" && -f "$_WG" ]]; then
  _SPG_LANE_ERR=$(mktemp 2>/dev/null || echo /tmp/wai-spg-lane-err.$$)
  _SPG_LANE=$(python3 "$_WG" lane-resolve --session "$_SPG_SID" --base "$BASE" --no-create 2>"$_SPG_LANE_ERR")
  if [[ $? -ne 0 ]]; then
    # Loud, not silent: a broken lane lookup means the savepoint may land in the wrong
    # session dir. Announce, then fall through to the mtime fallback below.
    echo "[WAI] degraded: lane-resolve failed in stop-savepoint-guard — $(head -c 300 "$_SPG_LANE_ERR" 2>/dev/null | tr '\n' ' '). Falling back to newest session dir." >&2
  else
    SESSION=$(printf '%s' "$_SPG_LANE" | python3 -c "import json,sys; print((json.load(sys.stdin) or {}).get('wai_session',''))" 2>/dev/null)
  fi
  rm -f "$_SPG_LANE_ERR" 2>/dev/null
fi
if [[ -z "$SESSION" && -d "$BASE/sessions" ]]; then
  SESSION=$(ls -t "$BASE/sessions" 2>/dev/null | head -1)
fi
[[ -z "$SESSION" ]] && exit 0

RESULT=$(python3 "$TOOL" --session "$SESSION" --root "$PROJECT_DIR" --mode "$DATA_ACTIVE" 2>/dev/null || true)
ACTION=$(printf '%s' "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('action',''))" 2>/dev/null || true)

if [[ "$ACTION" == "wrote" ]]; then
  emit "Auto-eject savepoint written (session ended with unfinished work and no savepoint). It is degraded/machine-reconstructed — run /wai-closeout or refresh it next session."
fi

# ── CSRP P6: cooperative self-converge ──────────────────────────────────────
# If a convergence LEAD asked this lane to converge, honor it at session end:
# the auto-eject above already wrote our resume-contract; now commit our lane's
# work to its branch and unregister the lane so the lead merges us into the single
# tree. Cooperative (we self-close at our own turn-end) — no session is force-killed.
CC="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/converge_closeout.py"
WG="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/worktree_guard.py"
if [[ -n "$_SPG_SID" && -f "$CC" ]]; then
  REQS=$(python3 "$CC" drain-signals --base "$BASE" --session-id "$_SPG_SID" 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('count',0))" 2>/dev/null || echo 0)
  if [[ "$REQS" =~ ^[0-9]+$ && "$REQS" -gt 0 ]]; then
    # Does this lane GENUINELY own a private worktree? The old code asserted in a comment
    # that it was committing "our OWN tree (the worktree we run in)" and unconditionally
    # ran `git add -A`. That assertion is false for a lane converging in the MAIN tree:
    # there, `add -A` sweeps every OTHER live session's in-flight files into our commit —
    # violating this project's never-git-add-A rule and recreating the exact S45
    # silent-revert collision convergence exists to resolve.
    # Canonical linked-worktree test: a linked worktree's own git dir differs from the
    # repo's shared common dir. Main tree -> they are equal.
    _SPG_GITDIR=$(git -C "$PROJECT_DIR" rev-parse --absolute-git-dir 2>/dev/null)
    _SPG_COMMON=$(git -C "$PROJECT_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
    _SPG_OWNS_WT=0
    [[ -n "$_SPG_GITDIR" && -n "$_SPG_COMMON" && "$_SPG_GITDIR" != "$_SPG_COMMON" ]] && _SPG_OWNS_WT=1

    if [[ "$_SPG_OWNS_WT" == 1 ]]; then
      # Private checkout: everything in it is ours by construction, so a full add is safe.
      git -C "$PROJECT_DIR" add -A >/dev/null 2>&1
      git -C "$PROJECT_DIR" commit -m "converge: self-commit lane on lead request ($_SPG_SID)" >/dev/null 2>&1
      [[ -f "$WG" ]] && python3 "$WG" lane-unregister --base "$BASE" --session "$_SPG_SID" >/dev/null 2>&1
      emit "Converge request honored: committed this lane's worktree + unregistered. The lead session will merge it into the single tree."
    else
      # SHARED tree: never blind-add. Release the lane (the lead is waiting on that, and
      # the auto-eject savepoint above already durably captured our resume-contract), but
      # leave the working tree exactly as-is for a scoped, human/session-owned commit.
      [[ -f "$WG" ]] && python3 "$WG" lane-unregister --base "$BASE" --session "$_SPG_SID" >/dev/null 2>&1
      emit "Converge request honored: lane unregistered. This lane runs in the SHARED tree (no private worktree), so it did NOT auto-commit — a blind 'git add -A' here would sweep other live sessions' in-flight files. Your savepoint is written; commit your own files scoped, or re-run this session in its own worktree (worktree_guard.py wt-new)."
    fi
  fi
fi
exit 0
