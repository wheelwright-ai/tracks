#!/bin/bash
#
# PreToolUse Guard — blocks destructive commands at hook level
# Returns JSON with decision: allow/deny/ask
# Stderr output blocks the action; stdout is informational
#

input=$(cat)
tool=$(echo "$input" | jq -r '.tool_name // ""')

# CSRP AC4 — lane heartbeat (initiative: csrp-intelligent-auto-reconciliation).
# Lanes were only stamped at SessionStart, so a live session older than the 12h TTL
# got reaped from the registry -> every concurrency guard then failed OPEN (blind).
# Refresh this lane's last_seen on tool use, throttled ~5min via a marker (cheap;
# fires for ALL tools, before the Bash-only early-exit).
#
# --no-create is LOAD-BEARING (impl-lane-registry-liveness-authority): this is a pure
# HEARTBEAT, and a heartbeat must NEVER mint a lane. lane-register/lane-resolve default
# to create=True, so without the flag ANY tool call after SessionEnd unregistered the
# lane RESURRECTED it — re-opening the ghost-lane bug (MEASURED: an 11.4h ghost holding
# the tree with zero live processes). Refresh a lane that exists; never author one.
_hb_sid=$(echo "$input" | jq -r '.session_id // ""' 2>/dev/null)
_hb_base="${CLAUDE_PROJECT_DIR:-.}/WAI-Harness/spoke/local"
if [ -n "$_hb_sid" ] && [ -d "$_hb_base" ]; then
  _hb_mark="$_hb_base/runtime/lanes/$_hb_sid/.hb"
  if [ -z "$(find "$_hb_mark" -mmin -5 2>/dev/null)" ]; then
    _hb_wg="${CLAUDE_PROJECT_DIR:-.}/WAI-Harness/spoke/managed/tools/worktree_guard.py"
    if [ -f "$_hb_wg" ]; then
      # Degrade LOUDLY but NOT on stderr: in a PreToolUse hook stderr is a control
      # channel (it blocks the tool call), so a bookkeeping failure must never speak
      # there. The guard's own audit log is the visible surface for this hook.
      _hb_err=$(python3 "$_hb_wg" lane-register --session "$_hb_sid" --base "$_hb_base" \
                  --no-create 2>&1 >/dev/null) || {
        _hb_log="$_hb_base/runtime/guard-audit.log"
        mkdir -p "$(dirname "$_hb_log")" 2>/dev/null
        printf '%s | LANE_HEARTBEAT_FAILED | (heartbeat) | lane-register --no-create failed for %s: %s\n' \
          "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$_hb_sid" \
          "$(printf '%s' "$_hb_err" | head -c 300 | tr '\n' ' ')" >> "$_hb_log" 2>/dev/null || true
      }
    fi
    mkdir -p "$(dirname "$_hb_mark")" 2>/dev/null && touch "$_hb_mark" 2>/dev/null || true
  fi
fi

# Only guard Bash commands — exit 0 silently to allow (no stdout; stdout causes hook error messages)
[[ "$tool" != "Bash" ]] && exit 0

cmd=$(echo "$input" | jq -r '.tool_input.command // ""')

# Extract only executable lines (strip heredoc bodies and quoted strings)
# Take the first line and any lines not inside a heredoc
first_line=$(echo "$cmd" | head -1)

# Policy-review finding: the guard blocked destructive commands but left zero
# evidence trail for denials (and, until this fix, for the fail-open branch
# below). Every block decision — and the sole-ownership-unconfirmed allow —
# now appends one line here: ISO-ts | RULE | command-first-120-chars | reason.
_GUARD_AUDIT_LOG="${CLAUDE_PROJECT_DIR:-.}/WAI-Harness/spoke/local/runtime/guard-audit.log"
_guard_audit_log() {
  local rule="$1" reason="$2"
  local ts cmd120
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cmd120="$(printf '%s' "$first_line" | cut -c1-120)"
  mkdir -p "$(dirname "$_GUARD_AUDIT_LOG")" 2>/dev/null
  printf '%s | %s | %s | %s\n' "$ts" "$rule" "$cmd120" "$reason" >> "$_GUARD_AUDIT_LOG" 2>/dev/null || true
}

# Block: rm -rf / (root deletion) — only on first line to avoid heredoc false positives
if echo "$first_line" | grep -qE '^\s*\\?rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\s*$|^\s*\\?rm\s+-rf\s+/'; then
  echo "BLOCKED: rm -rf / — destructive root deletion" >&2
  _guard_audit_log "RM_RF_ROOT" "destructive root deletion blocked"
  exit 2
fi

# Block: force push — check full command but only as a standalone git command
if echo "$first_line" | grep -qE '^\s*git\s+push\s+(-f|--force)'; then
  echo "BLOCKED: git push --force — use regular push" >&2
  _guard_audit_log "FORCE_PUSH" "git push --force/-f blocked"
  exit 2
fi

# CSRP P3 — destructive-op guard: blind worktree reverts silently discard another
# live lane's uncommitted hunks (basher s260617-231315 incident). Redirect to
# revert-mine.sh, which snapshots to refs/recovery/ FIRST, then reverts. Catches the
# path-revert forms ONLY — branch switches (git checkout <branch> / -b) are allowed.
if echo "$first_line" | grep -qE '^\s*git\s+checkout\s+(--\s|\.\s*$|\.\s)' \
   || { echo "$first_line" | grep -qE '^\s*git\s+restore\s' && ! echo "$first_line" | grep -qE '\-\-staged'; } \
   || echo "$first_line" | grep -qE '^\s*git\s+clean\s+-[a-zA-Z]*f'; then
  echo "BLOCKED: blind git checkout/restore/clean can discard another live lane's uncommitted work." >&2
  echo "  Use the recoverable path:  WAI-Harness/spoke/managed/tools/revert-mine.sh -- <paths>   (snapshots to refs/recovery/ first)" >&2
  echo "  Or, if you are sure:        revert-mine.sh --reset-hard | --clean | --check <path>" >&2
  _guard_audit_log "BLIND_REVERT" "blind git checkout/restore/clean blocked"
  exit 2
fi

# ── CSRP shared-tree write guard: cd-aware target resolution + FAIL-CLOSED ──
# Blanket-scope git writes on the SHARED main tree can sweep/discard another live
# lane's work: `git add -A/--all/.`, `git commit -a/-am`, `git reset --hard`,
# `git {cherry-pick,rebase,merge} --abort`. Two lessons baked in:
#   * s260701-213406: resolve the command's TARGET repo (honor a leading `cd <dir>`
#     or `git -C <dir>`), not the hook's own cwd — else a reset aimed at shared main
#     from an isolated worktree slips through.
#   * Isolation is only a launcher convenience (a running session can't relocate its
#     own CWD), so this guard FAILS CLOSED: on the shared main tree of a WAI repo it
#     blocks add/commit unless it can POSITIVELY confirm sole ownership, and blocks
#     reset/*-abort when the tree is DIRTY. Override: inline BASHER_ALLOW_HARD_RESET=1
#     (reset/abort only). Non-git target -> fail open (never brick a non-repo).
_tgt_dir=""
if echo "$first_line" | grep -qE '\bgit[[:space:]]+-C[[:space:]]'; then
  _tgt_dir="$(echo "$first_line" | sed -nE 's/.*\bgit[[:space:]]+-C[[:space:]]+("[^"]+"|[^[:space:];]+).*/\1/p' | tr -d '"' | head -1)"
elif echo "$first_line" | grep -qE '^[[:space:]]*cd[[:space:]]'; then
  _tgt_dir="$(echo "$first_line" | sed -nE 's/^[[:space:]]*cd[[:space:]]+("[^"]+"|[^[:space:];&]+).*/\1/p' | tr -d '"' | head -1)"
fi
_tgt_dir="${_tgt_dir:-${CLAUDE_PROJECT_DIR:-.}}"

_v_add=0; _v_reset=0
echo "$first_line" | grep -qE '\bgit[[:space:]]+(-C[[:space:]]+\S+[[:space:]]+)?add\b.*(-A|--all|(^|[[:space:]])\.([[:space:]]|$))' && _v_add=1
echo "$first_line" | grep -qE '\bgit[[:space:]]+(-C[[:space:]]+\S+[[:space:]]+)?commit[[:space:]]+(-a|-am|--all)' && _v_add=1
echo "$first_line" | grep -qE '\bgit[[:space:]]+(-C[[:space:]]+\S+[[:space:]]+)?reset\b.*--hard\b' && _v_reset=1
echo "$first_line" | grep -qE '\bgit[[:space:]]+(-C[[:space:]]+\S+[[:space:]]+)?(cherry-pick|rebase|merge)\b.*--abort\b' && _v_reset=1

if [ "$_v_add" = 1 ] || [ "$_v_reset" = 1 ]; then
  repo="$(git -C "$_tgt_dir" rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "$repo" ]; then
    main="$(git -C "$repo" worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2; exit}')"; main="${main:-$repo}"
    isolated=0; [ "$repo" != "$main" ] && isolated=1
    wg="$main/WAI-Harness/spoke/managed/tools/worktree_guard.py"
    base="$main/WAI-Harness/spoke/local"; [ -d "$base" ] || base="$main/WAI-Spoke"
    is_wai=0; [ -d "$base" ] && is_wai=1

    # reset --hard / *-abort: block on a NON-isolated DIRTY target unless overridden.
    if [ "$_v_reset" = 1 ] && [ "$isolated" = 0 ]; then
      if ! echo "$first_line" | grep -qE 'BASHER_ALLOW_HARD_RESET=1'; then
        dirty=0; [ -n "$(git -C "$repo" status --porcelain 2>/dev/null)" ] && dirty=1
        if [ "$dirty" = 1 ]; then
          echo "BLOCKED (CSRP): git reset --hard / --abort on a DIRTY shared tree ($repo) can discard another live lane's uncommitted work (s260701-213406)." >&2
          echo "  Recoverable path:  WAI-Harness/spoke/managed/tools/revert-mine.sh --reset-hard    (snapshots to refs/recovery/ first)" >&2
          echo "  Override if you are sure:  BASHER_ALLOW_HARD_RESET=1 git reset --hard <ref>" >&2
          _guard_audit_log "RESET_HARD_DIRTY" "reset --hard / *-abort on dirty shared tree ($repo) blocked"
          exit 2
        fi
      fi
    fi

    # add -A / commit -a: fail-closed on the shared main tree of a WAI repo unless
    # positively sole-owner (exactly one live lane). The current lane is heartbeat-
    # registered above, so a genuine solo session reads count==1 and is allowed.
    #
    # Policy-review calibration: count==-1 means the machinery FAILED to positively
    # confirm anything (worktree_guard.py missing, or its lanes call errored) — that
    # is not evidence of contention, it is an unknown. Blocking on unknown punished
    # every spoke whose tooling had drifted. Only a POSITIVE read of count>1 (genuine
    # multi-lane contention) still blocks; count==-1 now allows through with an audit
    # trail so the blind spot is visible instead of silently gating all work.
    if [ "$_v_add" = 1 ] && [ "$isolated" = 0 ] && [ "$is_wai" = 1 ]; then
      _cnt=-1
      if [ -f "$wg" ]; then
        _cnt="$(python3 "$wg" lanes --base "$base" 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("count",-1))' 2>/dev/null || echo -1)"
      fi
      if [ "$_cnt" = "-1" ]; then
        _guard_audit_log "ADD_SOLE_OWNER_UNCONFIRMED" "worktree_guard.py missing or errored (count=-1) — allowed, sole ownership NOT positively confirmed"
      elif [ "$_cnt" != "1" ]; then
        echo "BLOCKED (CSRP fail-closed): git add -A / commit -a on the shared main tree can sweep another lane's staged files (${_cnt} live lanes detected)." >&2
        echo "  Use:  WAI-Harness/spoke/managed/tools/commit-mine.sh -m \"msg\" -- <your paths>    (scopes to your files only)" >&2
        echo "  Or isolate:  python3 $wg wt-new <name>   then work in the worktree." >&2
        _guard_audit_log "ADD_SOLE_OWNER_BLOCKED" "multiple live lanes detected (count=${_cnt}) — blocked"
        exit 2
      fi
    fi
  fi
fi

# Block: drop database — only on first line
if echo "$first_line" | grep -qiE '^\s*.*drop\s+(database|table)'; then
  echo "BLOCKED: DROP DATABASE/TABLE — destructive DB operation" >&2
  _guard_audit_log "DROP_DB" "DROP DATABASE/TABLE blocked"
  exit 2
fi

# Block: destructive ops on the v4 protected substrate (harness.db, the append-only
# event journal patterns/*.jsonl, and managed/). Authored by wheelwright-framework,
# placed here by Basher and distributed to every spoke: inert where these paths do
# not exist, protective where they do. Edits to this substrate go through the
# sanctioned tools (atomic_write/event_bus/db_writer), never raw rm/truncate/mv.
if echo "$first_line" | grep -qE '(^|[[:space:]/])harness\.db([[:space:]]|$)|/patterns/[^[:space:]]*\.jsonl([[:space:]]|$)|/managed/'; then
  if echo "$first_line" | grep -qE '^\s*\\?(rm|shred|truncate)\s|^\s*mv\s'; then
    echo "BLOCKED: destructive op on a protected harness path (harness.db / patterns/*.jsonl journal / managed/). Append-only substrate — use the sanctioned tool, not raw rm/truncate/mv." >&2
    _guard_audit_log "PROTECTED_SUBSTRATE" "destructive op on harness.db / patterns/*.jsonl / managed/ blocked"
    exit 2
  fi
fi

# Intercept: rm within ~/projects — redirect to trash bin with reflective path
# Matches: rm, rm -f, rm -rf, \rm, \rm -f on files/dirs under ~/projects/
TRASH_BIN="$HOME/projects/trash_bin"
if echo "$first_line" | grep -qE '^\s*\\?rm\s'; then
  # Extract target paths (skip flags)
  targets=$(echo "$first_line" | sed -E 's/^\s*\\?rm\s+(-[a-zA-Z]+\s+)*//g')
  # Only intercept if targets are under ~/projects/
  if echo "$targets" | grep -qE "(^|/)(~/projects/|\$HOME/projects/|/home/[^/]+/projects/)"; then
    # Build the rewritten command: mkdir -p trash dest, mv instead of rm
    rewrite="# Soft-delete: redirected to trash bin"$'\n'
    for target in $targets; do
      # Expand ~ and $HOME
      expanded=$(echo "$target" | sed "s|^~|$HOME|; s|\\\$HOME|$HOME|")
      # Strip the ~/projects/ prefix to get relative path
      rel_path="${expanded#$HOME/projects/}"
      trash_dest="$TRASH_BIN/$rel_path"
      trash_dir=$(dirname "$trash_dest")
      rewrite+="mkdir -p \"$trash_dir\" && mv \"$expanded\" \"$trash_dest\""$'\n'
    done
    echo "SOFT-DELETE: rm intercepted — files moved to $TRASH_BIN/ instead of deleted. Rewrite:" >&2
    echo "$rewrite" >&2
    _guard_audit_log "RM_TRASH_REDIRECT" "rm under ~/projects/ intercepted, redirected to trash bin"
    exit 2
  fi
fi

# Allow everything else — exit 0 silently (no stdout)
exit 0
