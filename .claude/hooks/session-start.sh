#!/bin/bash
#
# Thin SessionStart wrapper for Wheelwright spokes.
# If the canonical spoke hook exists, delegate to it. Otherwise exit quietly.
#

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# _wai_detach: launch a background daemon that Claude Code will NOT count as an
# active shell at session exit and that never flashes a terminal window. The old
# `( cmd & )` subshell left the child in this shell's session + process group, so
# CC still tracked it. setsid puts the child in a BRAND-NEW session with no
# controlling terminal (full detach); nohup is the portable fallback where setsid
# is absent (e.g. stock macOS). stdin is closed (</dev/null) so no piped-stdin
# wait can hang startup, all FDs are redirected, and the job is disowned so bash
# stops tracking it. Best-effort: a missing tool or failed spawn never breaks start.
# Usage: _wai_detach <LOGFILE|/dev/null> <cmd> [args...]
_wai_detach() {
  local _log="$1"; shift
  if command -v setsid >/dev/null 2>&1; then
    setsid "$@" </dev/null >>"$_log" 2>&1 &
  else
    nohup "$@" </dev/null >>"$_log" 2>&1 &
  fi
  disown 2>/dev/null || true
}

# --- Herald responder LIGHT-PATH (WAI_HERALD_SPAWN) ---------------------------
# When Herald spawns a responder (claude -p) for ONE lug, load LIGHT: skip the upgrade,
# the full wakeup briefing, and never claim chains. The responder gets its full
# instructions from its -p prompt; it only needs to process the one lug.
# This early-exit is also what keeps the Herald auto-spawn below from recursing.
#
# REGISTER THE LANE ANYWAY (impl-lane-registry-liveness-authority). This path used to
# skip lane registration along with the briefing — but a herald responder's own prompt
# tells it to COMMIT AND PUSH. An unlaned session that writes git is INVISIBLE to
# concurrent-session isolation: peers see one fewer live session and may blind-commit
# over it. Skip the BRIEFING (cost), never the REGISTRATION (safety).
# Autopilot-dispatched agents take the same LIGHT path as Herald responders: they
# process one lug and exit, and must not run wakeup, claim chains, or mint a
# session of their own.
if [ -n "${WAI_AP_DISPATCH:-}" ]; then
  exit 0
fi

if [ -n "${WAI_HERALD_SPAWN:-}" ]; then
  # Resolve the lane key from the SessionStart payload. `timeout` guards the read so a
  # spawn with no piped stdin can never hang startup.
  _HS_STDIN=$(timeout 2 cat 2>/dev/null || true)
  _HS_SID=$(printf '%s' "$_HS_STDIN" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
  _HS_TRANSCRIPT=$(printf '%s' "$_HS_STDIN" | python3 -c "import json,sys; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)
  [ -z "$_HS_SID" ] && [ -n "$_HS_TRANSCRIPT" ] && _HS_SID=$(basename "$_HS_TRANSCRIPT" .jsonl)
  # BASE the same way the data-plane hooks resolve it (v4 canon, v3 fallback). This runs
  # before harness_mode.sh is sourced, so infer from on-disk dirs.
  if [ -d "$PROJECT_DIR/WAI-Harness" ]; then _HS_BASE="$PROJECT_DIR/WAI-Harness/spoke/local"
  else _HS_BASE="$PROJECT_DIR/WAI-Spoke"; fi
  _HS_WG="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/worktree_guard.py"
  if [ -n "$_HS_SID" ] && [ -f "$_HS_WG" ]; then
    _HS_ERR=$(mktemp 2>/dev/null || echo /tmp/wai-herald-lane-err.$$)
    if ! python3 "$_HS_WG" lane-adopt --token "${WAI_LAUNCH_TOKEN:-}" --session "$_HS_SID" \
           --base "$_HS_BASE" --transcript "$_HS_TRANSCRIPT" >/dev/null 2>"$_HS_ERR"; then
      # Loud degrade (same contract as the CLAUDE_PROJECT_DIR guard below): a responder
      # that commits while unlaned is exactly the invisible-writer hazard.
      echo "[WAI] DEGRADED: herald responder lane registration FAILED — $(head -c 300 "$_HS_ERR" 2>/dev/null | tr '\n' ' '). This session is INVISIBLE to concurrent-session isolation; it must commit scoped (never git add -A) and push only its own branch." >&2
    fi
    rm -f "$_HS_ERR" 2>/dev/null
  elif [ -n "$_HS_SID" ]; then
    echo "[WAI] DEGRADED: herald responder could not register a lane (no worktree_guard.py at $_HS_WG) — session invisible to isolation; commit scoped only." >&2
  fi
  python3 -c 'import json; print(json.dumps({"hookSpecificOutput":"HERALD RESPONDER - LIGHT MODE. Do NOT run wakeup, do NOT claim chains, do NOT scan the backlog. Process ONLY the lug named in your prompt: read it, follow PEV (perceive/execute/verify), run its verify/tests, commit CSRP-scoped (never git add -A), push your OWN session/herald branch (never main), deliver a completion (or refinement) lug back to the originating spoke, then exit."}))' 2>/dev/null \
    || echo "HERALD RESPONDER (light): process only the assigned lug; no wakeup; no chain-claim; scoped commit; push own branch; confirm back."
  exit 0
fi


# I-1 guard (resolve-check, NOT absolute-path materialization): ${CLAUDE_PROJECT_DIR}
# is the canon hook-path variable — docs-confirmed to expand across all hook events, so
# it stays. Its ONE failure mode is an unset/unresolved value, which would silently break
# every ${CLAUDE_PROJECT_DIR}-based hook command. This is the first hook to run, so make
# that failure LOUD here (degraded-mode JSON) instead of a mute, broken session. An
# environment fault — not a wiring fault; the canonical paths remain correct.
if [ -z "${CLAUDE_PROJECT_DIR:-}" ] || [ ! -d "${CLAUDE_PROJECT_DIR:-/nonexistent}" ]; then
  python3 -c 'import json; print(json.dumps({"hookSpecificOutput": "WAI DEGRADED: CLAUDE_PROJECT_DIR is unset or not a directory — every ${CLAUDE_PROJECT_DIR}-based hook command will fail to resolve. Hook wiring is degraded for this session (environment fault, not a wiring fault). Canonical paths use ${CLAUDE_PROJECT_DIR} per Claude Code docs."}))' 2>/dev/null \
    || echo "WAI DEGRADED: CLAUDE_PROJECT_DIR unset/unresolved — hook paths will not resolve."
fi

# Resolve v3/v4 coexistence (exports HARNESS_ACTIVE / HARNESS_ROOT). v3-safe.
_HM="$(dirname "${BASH_SOURCE[0]:-$0}")/harness_mode.sh"
[ -f "$_HM" ] && source "$_HM" "$PROJECT_DIR" 2>/dev/null

# v4 pull-on-spin-up (own-copy, upgrade-when-newer): bring this spoke's managed/
# current from the master. Cheap no-op when current; never touches local/;
# best-effort + presence-guarded (no-op offline / no master / no WAI-Harness).
# Runs the MASTER's engine so a spoke carrying an old copy still self-updates.
# Master path resolves PORTABLY (clone-and-run on any machine): $WAI_HARNESS_MASTER ->
# per-spoke WAI-Harness/.harness-master -> built-in default. Unreachable -> pull no-ops.
#
# impl-dist-spoke-pullcheck-v1: prefer harness_pullcheck.py's `check` over a bare
# `harness_upgrade.py pull`. It resolves this spoke's GROUP (hub-registry.json +
# groups.json) and gates the pull to that group's hub-AVAILABLE (certified) version
# instead of master's raw HEAD -- an uncertified cut is never pulled. It is
# fail-open by design: no group resolved, or the group has no AVAILABLE version
# recorded yet, falls straight through to today's unconditioned pull, so this is a
# safe drop-in. Falls back to the bare pull when the newer tool isn't present yet
# (older master pin) so self-heal never regresses mid-rollout.
# --- Pull gate (change-autopilot-headless-dispatch-reverts-managed-edits-every-lug-v1) ---
# Two guards run BEFORE the pull-on-spin-up, because the pull overwrites
# WAI-Harness/spoke/managed/** from canon and used to do so silently:
#   1. WAI_NO_HARNESS_PULL: a headless dispatched subprocess (autopilot / herald /
#      certifier / measurer worker) must never self-upgrade the spoke mid-run — the
#      parent process already resolved the harness version when it started. The
#      dispatchers export this in the child env.
#   2. Dirty managed/ tree: spoke-local edits under WAI-Harness/spoke/managed
#      (tracked modifications, staged changes, or untracked files — git status
#      --porcelain covers all three) mean a pull would clobber local work. Skip
#      LOUDLY, naming the files: fail-LOUD, not fail-open. A spoke with local
#      managed/ edits keeps them and is told why it is not updating.
_WAI_PULL_SKIP=""
if [ -n "${WAI_NO_HARNESS_PULL:-}" ]; then
  echo "[WAI] pull-on-spin-up SKIPPED: WAI_NO_HARNESS_PULL is set (headless dispatch — parent session owns the harness version)." >&2
  _WAI_PULL_SKIP=1
elif [ -d "$PROJECT_DIR/WAI-Harness/spoke/managed" ]; then
  _WAI_MANAGED_DIRTY="$(git -C "$PROJECT_DIR" status --porcelain -- WAI-Harness/spoke/managed 2>/dev/null)"
  if [ -n "$_WAI_MANAGED_DIRTY" ]; then
    echo "[WAI] pull-on-spin-up SKIPPED: spoke-local edits under WAI-Harness/spoke/managed — refusing to overwrite them. Dirty: $(printf '%s\n' "$_WAI_MANAGED_DIRTY" | cut -c4- | tr '\n' ' ')" >&2
    _WAI_PULL_SKIP=1
  fi
fi

_WMASTER="${WAI_HARNESS_MASTER:-$(cat "$PROJECT_DIR/WAI-Harness/.harness-master" 2>/dev/null)}"
[ -z "$_WMASTER" ] && _WMASTER="/home/mario/projects/wheelwright/mywheel/WAI-Harness"
_HUP="$_WMASTER/spoke/managed/tools/harness_upgrade.py"
_HPC="$_WMASTER/spoke/managed/tools/harness_pullcheck.py"
if [ -z "$_WAI_PULL_SKIP" ] && [ -d "$PROJECT_DIR/WAI-Harness" ]; then
  if [ -f "$_HPC" ]; then
    python3 "$_HPC" check --spoke-root "$PROJECT_DIR" --master "$_WMASTER" >/dev/null 2>&1
  elif [ -f "$_HUP" ]; then
    python3 "$_HUP" pull --spoke-root "$PROJECT_DIR" --master "$_WMASTER" >/dev/null 2>&1
  else
    # DEGRADED (visible, not silent): master resolution dangled — no reachable engine at
    # $_WMASTER. Self-update pull SKIPPED. .harness-master is now a per-machine gitignored
    # pin (fix-harness-master-pin-untrack-v1), so an absent/wrong pin must announce itself.
    echo "[WAI] degraded: harness master unresolved (no reachable engine at $_HUP) — self-update pull SKIPPED. Set \$WAI_HARNESS_MASTER or create WAI-Harness/.harness-master." >&2
  fi
fi

# Hygiene advisor INNATE seat (impl-hygiene-advisor-and-arms-v1): write a fresh
# spoke/local/maintenance/hygiene-latest.json EVERY session start, with ZERO manual
# invocation — this is what makes hygiene innate rather than "works when called".
# hygiene_run.py is read-only/signal-only (never reaps or prunes anything itself);
# backgrounded + fully presence-guarded + best-effort so a missing/broken tool can
# never delay or break session start. Mirrors the herald_poll.py backgrounding
# pattern below. Closeout + Ozi nightly are secondary/defense-in-depth seats — this
# post-pull hook is the primary one (never the sole thing that has to work).
_HYGIENE="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/hygiene_run.py"
[ -f "$_HYGIENE" ] && _wai_detach /dev/null python3 "$_HYGIENE" --spoke-root "$PROJECT_DIR"

# Standing silent-failure oracles, surfaced to STDERR at every session start.
# Cron (07:15) writes them to a log nobody opens; this puts the non-green lines
# in front of the agent BEFORE it can describe the spoke as healthy. Session 139:
# the agent told the operator "Herald is already active" from a line in this very
# file — Herald had never run. --brief prints ONLY non-green, so a clean wheel
# stays silent and a real finding cannot be mistaken for noise. Best-effort and
# presence-guarded; never delays or breaks session start.
_IPROBE="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/integrity_probe.py"
[ -f "$_IPROBE" ] && timeout 90 python3 "$_IPROBE" --root "$PROJECT_DIR" --brief --emit-lugs 2>/dev/null >&2 || true

# v4 on-load trigger: notice the upgrade and, ONLY when WAI-Harness/ACTIVATE
# exists, migrate. Dormant + idempotent + dry-run-first by design — safe to call
# every load. Presence-guarded: no-op where the harness isn't installed.
# stdout->/dev/null: SessionStart hook stdout must stay clean for the canonical.
_HACT="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/harness_activate.py"
[ -f "$_HACT" ] && python3 "$_HACT" --spoke-root "$PROJECT_DIR" check >/dev/null 2>&1

# Hook self-heal (basher canon owner). A NON-additive writer of ~/.claude/settings.json
# — e.g. the WAI managed-settings deploy — can DISPLACE a basher-declared global hook by
# claiming the same event (this is exactly how notify-reset.sh got dropped off
# UserPromptSubmit: user-prompt-submit.sh replaced the slot instead of appending). That
# silently kills the ⏳/✅/🔴 tab-status glyphs AND the per-pane transcript map lens uses
# to tell same-spoke sessions apart. Re-assert any basher-declared hook missing from live
# settings, ADDITIVELY (find-or-create the event+matcher rule, never replace). Cheap no-op
# when in sync; fully fail-safe; only writes when it actually repairs drift. This heals the
# registration from OUTSIDE the session that caused it — any new session restores the canon
# without anyone restarting the displacing session. (Mirrors restore.sh _restore_hooks.)
_BJ="$PROJECT_DIR/WAI-Harness/spoke/basher.json"
[ -f "$_BJ" ] && [ -f "$HOME/.claude/settings.json" ] && \
  python3 - "$_BJ" "$HOME/.claude/settings.json" >/dev/null 2>&1 <<'PY'
import json, sys
from pathlib import Path
try:
    declared = json.loads(Path(sys.argv[1]).read_text()).get("hooks", [])
    cfgp = Path(sys.argv[2]); cfg = json.loads(cfgp.read_text())
except Exception:
    sys.exit(0)
hooks = cfg.setdefault("hooks", {}); added = 0
for dh in declared:
    ev, cmd = dh.get("event"), dh.get("command")
    if not ev or not cmd:
        continue
    if any(h.get("command") == cmd for r in hooks.get(ev, []) for h in r.get("hooks", [])):
        continue
    matcher = dh.get("matcher", ".*")
    rules = hooks.setdefault(ev, [])
    rule = next((r for r in rules if r.get("matcher") == matcher), None)
    if rule is None:
        rule = {"matcher": matcher, "hooks": []}; rules.append(rule)
    rule["hooks"].append({"type": "command", "command": cmd, "timeout": dh.get("timeout", 10)})
    added += 1
if added:
    cfgp.write_text(json.dumps(cfg, indent=2) + "\n")
PY

# v4 concurrency: lane registration (the liveness signal for concurrent-session
# isolation) is done by the canonical wakeup (wakeup-canonical.sh runs
# `worktree_guard.py lane-adopt --token <WAI_LAUNCH_TOKEN> --session <cc_sid> --base
# <base>`, which upgrades the launcher's pre-exec reservation, or registers outright when
# there is no token), which has the SessionStart stdin payload carrying the CC session_id.
# The lane is RELEASED by the SessionEnd hook (session-end-lane.sh).
# The herald light-path above registers its own lane before its early exit.
# A bare, argless call here was
# a dead argparse no-op — and a hook could not isolate anyway: a running session cannot
# relocate its own CWD, so SOURCE isolation must happen at LAUNCH (wai-enter auto-
# worktrees the 2nd+ live session), never from inside a hook.
# (impl-basher-concurrent-session-autoisolation-v1: removed the no-op; registration is wakeup-side.)

# v4 liveness indicator: emit ONE visible line so a human can SEE v4 is live in the
# session banner. This is the only stdout this wrapper produces; v3-only spokes
# (no WAI-Harness/) stay silent. Printed before exec so it lands above the canonical
# wakeup output. ASCII separators only (no em-dash) to stay encoding-safe.
[ "$HARNESS_V4" = "1" ] && echo "[v4 ACTIVE] managed current | mode=$HARNESS_MODE active=$HARNESS_ACTIVE"

# --- Converge gate (operator directive 2026-07-22) ----------------------------
# "First session to do work should attempt the converge if needed. This way we are
# always reconciling before we create our own branch."
#
# Convergence was only ever asked about at the END of a session (/wai-converge,
# closeout, savepoint). Nothing asked at the START, so a session forked its own
# branch off a tree that still had another lane's committed work outside it —
# which is how one lane sat unmerged for three days while later sessions branched
# around it. Read-only, always exits 0, silent when there is nothing to reconcile.
# It ANNOUNCES; it never merges: reconciling has a lease, a test gate and a safety
# triple, and a hook that merged on its own would be a silent writer at the least
# examined moment of a session.
_CGATE="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/converge_gate.py"
[ -f "$_CGATE" ] && timeout 20 python3 "$_CGATE" --root "$PROJECT_DIR" 2>/dev/null

# --- Git hygiene ACT seat (git_hygiene.py, impl-git-hygiene-act-arm-v1) --------
# The ACTIONABLE counterpart to hygiene_run's read-only signal and converge_gate's
# announce. A session that auto-ejects or crashes leaves carryover: self-owned runtime
# churn uncommitted (247+ files is normal here) and the session branch drifted ahead of a
# now-stale main. Nothing healed it until the next CLEAN closeout -- the exact path a crash
# skips -- so it piled up for days. This heals it at the next start, on the QUIET tree
# (last session's leftovers, before this session mutates anything).
# SAFE BY CONSTRUCTION: only self-owned runtime state is committed; .claude/**,
# **/managed/**, and authored source are NEVER committed (surfaced only); reunify is
# FAST-FORWARD ONLY (a diverged main is surfaced, never force-pushed) and is skipped while
# another session holds the CSRP converge.lock lease. Runs SYNCHRONOUSLY (never backgrounded
# -- a git-writing job racing the session is exactly what concurrency isolation forbids) and
# best-effort (always exits 0) so it can never block launch; self-gates to a no-op when the
# tree is clean and main is already current (no commit, no network round-trip).
_GHYG="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/git_hygiene.py"
if [ "$HARNESS_V4" = "1" ] && [ -f "$_GHYG" ]; then
  timeout 30 python3 "$_GHYG" heal --base WAI-Harness/spoke/local --root "$PROJECT_DIR" \
    --session-id "session-start-heal" --best-effort >/dev/null 2>&1 || true
fi

# --- Auto-sync the RUNNING copy from canon (s138) -----------------------------
# "Are we running the latest locally, all the time?" The honest answer used to be
# no: managed/ is canon, but .claude/commands is what actually executes, and
# nothing kept them in step. They matched only when somebody remembered to run
# deploy_commands.py by hand.
#
# That gap is not theoretical. A mandatory adversarial plan-review gate sat
# unexecuted for ten days in this repo because it was edited in a layer that
# deploys nowhere, and later in the same session a fix I had just committed was
# still not live until a deploy was run. Both were invisible: no error, clean
# commit, everything reading as done.
#
# So the sync happens at session start, every session, before any work. Scoped to
# commands (never a blanket copy), best-effort, and silent when already current
# so a clean spoke costs nothing and says nothing.
if [ "$HARNESS_V4" = "1" ] && [ -f "$PROJECT_DIR/WAI-Harness/spoke/managed/tools/deploy_commands.py" ]; then
  _DC_OUT="$(python3 "$PROJECT_DIR/WAI-Harness/spoke/managed/tools/deploy_commands.py" \
              --root "$PROJECT_DIR" 2>/dev/null | head -1)"
  case "$_DC_OUT" in
    *"0 synced"*) : ;;                       # already current: stay quiet
    *synced*) echo "[v4 SYNC] running copy updated from canon: ${_DC_OUT#*synced }" ;;
  esac
fi

# Surface the LAST-KNOWN hygiene verdict at entry (change-basher-surface-hygiene-verdict-at-
# entry-v1, mywheel-authored managed half). hygiene_run.py above is backgrounded, so we read the
# PREVIOUS session's spoke/local/maintenance/hygiene-latest.json (non-blocking, best-effort). Only
# speaks on DRIFT/UNKNOWN so CLEAN is no false alarm; missing/malformed = silent no-op; ASCII-only
# (encoding-safe). Prints before the exec to wakeup-canonical.sh so it lands in the banner.
[ "$HARNESS_V4" = "1" ] && python3 - "$PROJECT_DIR" 2>/dev/null <<'PY'
import json, sys, datetime
from pathlib import Path
p = Path(sys.argv[1]) / "WAI-Harness" / "spoke" / "local" / "maintenance" / "hygiene-latest.json"
try:
    d = json.loads(p.read_text())
except Exception:
    sys.exit(0)  # missing/malformed -> silent no-op
verdict = d.get("verdict", "UNKNOWN")
if verdict == "CLEAN":
    sys.exit(0)  # CLEAN -> no false alarm
age = ""
ts = d.get("ts")
if ts:
    try:
        dt = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        hrs = (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds() / 3600
        age = " age=%.0fh" % hrs
    except Exception:
        pass
h = d.get("health") or {}
print("[HYGIENE %s] phantom=%s v3=%s health_failed=%s%s (last-known; run hygiene_run.py to refresh)"
      % (verdict, "yes" if d.get("phantom_present") else "no",
         d.get("v3_violations", "?"), h.get("failed", "?"), age))
PY

# Herald auto-spawn (opt-in, session-bound). `start` is idempotent and no-ops unless
# herald.json enabled:true, so calling it on every session start is safe fleet-wide --
# only deliberately-enabled spokes spin a daemon. The daemon self-reaps when the live-
# lane count hits zero, so no stop hook is needed. Backgrounded + silenced so it never
# delays the session. A Herald-spawned responder already exited on the LIGHT path above,
# so this never recurses.
_HERALD="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/herald_poll.py"
[ -f "$_HERALD" ] && _wai_detach /dev/null python3 "$_HERALD" --spoke-root "$PROJECT_DIR" start

# v4-native wakeup: the single canonical path. wakeup-canonical.sh is mode-aware —
# it renders the briefing from WAI-Harness/spoke/local (handles coexist + v4-only),
# so any spoke carrying a v4 local tree wakes here regardless of HARNESS_ACTIVE.
_V4WAKE="$(dirname "${BASH_SOURCE[0]:-$0}")/wakeup-canonical.sh"
if [ -d "$PROJECT_DIR/WAI-Harness/spoke/local" ] && [ -x "$_V4WAKE" ]; then
  exec "$_V4WAKE"
fi

# No v4 local tree present. A bare repo (no WAI-Harness/) is simply not a WAI spoke —
# stay silent. But if WAI-Harness/ IS present yet wakeup can't run, say so LOUDLY
# (degraded JSON) instead of a mute exit that silently skips the briefing.
if [ -d "$PROJECT_DIR/WAI-Harness" ]; then
  python3 -c 'import json; print(json.dumps({"hookSpecificOutput": "WAI DEGRADED: WAI-Harness present but no v4 local tree / executable wakeup-canonical.sh — the wakeup briefing did NOT run. Run harness install + activate to adopt v4."}))' 2>/dev/null \
    || echo "WAI DEGRADED: no v4 wakeup (spoke/local + wakeup-canonical.sh) — wakeup did not run."
fi
exit 0
