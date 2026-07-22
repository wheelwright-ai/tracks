#!/bin/bash
#
# WAI UserPromptSubmit hook — harness-mode-aware (v4 + v3 fallback).
#
# Per-turn duties:
#   (1) CSRP AC4 lane heartbeat — refresh this lane's last_seen EVERY turn so a live
#       session is never TTL-reaped from the registry (which blinds every concurrency
#       guard). Initiative: csrp-intelligent-auto-reconciliation. Throttled ~5min.
#   (2) Post-compaction recovery — SessionStart does NOT fire on compaction, so inject
#       recovery context on the first user turn after a compaction.
#   (3) v3 ONLY: inject the pre-computed wakeup brief. On v4 the rich brief is owned by
#       SessionStart (wakeup-canonical.sh) — UPS must NOT re-inject it (double-inject).
#
# Base resolution: v4 first (WAI-Harness/spoke/local), v3 fallback (WAI-Spoke).

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
BASE="$PROJECT_DIR/WAI-Harness/spoke/local"; MODE="v4"
[[ -f "$BASE/WAI-State.json" ]] || { BASE="$PROJECT_DIR/WAI-Spoke"; MODE="v3"; }
STATE_FILE="$BASE/WAI-State.json"
[[ ! -f "$STATE_FILE" ]] && exit 0   # not a WAI project

RUNTIME_DIR="$BASE/runtime"
_UPS_INPUT=$(timeout 2 cat 2>/dev/null || true)
_UPS_SID=$(printf '%s' "$_UPS_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
_UPS_TRANSCRIPT=$(printf '%s' "$_UPS_INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)
[[ -z "$_UPS_SID" && -n "$_UPS_TRANSCRIPT" ]] && _UPS_SID=$(basename "$_UPS_TRANSCRIPT" .jsonl)

# ── Mid-session inbox notify (impl-basher-mid-session-inbox-notify-v1) ────────
# Surface lugs that land in lugs/incoming/ DURING a live session so routed-in work
# gets near-real-time action instead of waiting for the next wakeup. Cheap (listdir +
# a per-session marker under runtime/, gitignored). First prompt baselines the existing
# backlog (already shown by the wakeup brief) WITHOUT announcing; thereafter each new
# arrival is announced exactly once. Silent when nothing new.
_INBOX_DIR="$BASE/lugs/incoming"
if [[ -d "$_INBOX_DIR" ]]; then
  _INBOX_MARK="$RUNTIME_DIR/incoming-seen-${_UPS_SID:-nosid}.txt"
  if [[ ! -f "$_INBOX_MARK" ]]; then
    mkdir -p "$RUNTIME_DIR" 2>/dev/null
    ls "$_INBOX_DIR"/*.json 2>/dev/null | xargs -n1 basename 2>/dev/null > "$_INBOX_MARK" || : > "$_INBOX_MARK"
  else
    _INBOX_NEW=""
    for _ilf in "$_INBOX_DIR"/*.json; do
      [[ -f "$_ilf" ]] || continue
      _ibn=$(basename "$_ilf")
      grep -qxF "$_ibn" "$_INBOX_MARK" 2>/dev/null && continue
      _iid=$(jq -r '.id // ""' "$_ilf" 2>/dev/null)
      _ititle=$(jq -r '.title // ""' "$_ilf" 2>/dev/null | head -c 80)
      _ifrom=$(jq -r '.source_wheel_id // .from // .source_spoke // "?"' "$_ilf" 2>/dev/null)
      _INBOX_NEW="${_INBOX_NEW}\n  • [${_ifrom}] ${_iid}: ${_ititle}"
      echo "$_ibn" >> "$_INBOX_MARK"
    done
    if [[ -n "$_INBOX_NEW" ]]; then
      printf '<wai-inbox-notify>\n📥 New lug(s) arrived in incoming/ this session — triage when ready:%b\n</wai-inbox-notify>\n' "$_INBOX_NEW"
    fi
  fi
fi

# (1a) WAI Track per-turn ritual engine (spec-wai-track-collection-v2.0.2). DURABLE trigger:
# injected EVERY turn (not model memory — the proven-failing design) so BOTH rituals fire:
#   (i)  the model-authored rich track entry (Layer-1 = the "full-feature" file), and
#   (ii) the mandatory v2.0.2 statusline.
# The hook resolves the values that must be REAL and never guessed — turn number (lane guard
# turn_count + 1 = this turn, == the track turn-event count), wall-clock in America/Los_Angeles
# (SI1: clock is hook-supplied, never fabricated by the model), and the live model id from the
# transcript — and leaves the model only what it alone knows: the field content + this turn's
# Gold count. tz uses %Z (PDT/PST), never hardcoded.
if [[ -n "$_UPS_SID" ]]; then
  _TR_GUARD="$BASE/runtime/lanes/$_UPS_SID/session-guard.json"
  _TR_TC=$(python3 -c "import json;print(json.load(open('$_TR_GUARD')).get('turn_count',0))" 2>/dev/null || echo 0)
  [[ "$_TR_TC" =~ ^[0-9]+$ ]] || _TR_TC=0
  _TR_N=$(( _TR_TC + 1 ))
  _TR_DATE=$(TZ=America/Los_Angeles date '+%a, %b %-d, %Y' 2>/dev/null)
  _TR_TIME=$(TZ=America/Los_Angeles date '+%-I:%M %p %Z' 2>/dev/null)
  # Live model id from the transcript's last assistant message; fall back to state, then a
  # placeholder the model fills from its own system context.
  _TR_MODEL=$(python3 -c "
import json,sys
m=''
try:
    for l in open('$_UPS_TRANSCRIPT'):
        try: d=json.loads(l)
        except Exception: continue
        if d.get('type')=='assistant':
            mm=(d.get('message') or {}).get('model')
            if mm: m=mm
except Exception: pass
print(m)" 2>/dev/null)
  [[ -z "$_TR_MODEL" ]] && _TR_MODEL=$(python3 -c "import json;print(json.load(open('$STATE_FILE')).get('_session_state',{}).get('ai_id','') or '')" 2>/dev/null)
  # Unresolved model => the honest DATA value "unknown", never the prompt placeholder.
  # "<your-model-id>" is a template token the model is told to substitute in its statusline;
  # writing it into the buffer leaked it through track -> model-usage/usage.jsonl and minted
  # a phantom model-interface/_your-model-id_.json profile the Navigator could route against
  # (observed 2026-07-14). A prompt token is not a data value. model_profile_build.load_usage
  # also drops non-model ids at the read side, so old events and lagging spokes stay harmless.
  [[ -z "$_TR_MODEL" ]] && _TR_MODEL="unknown"
  if [[ "$MODE" == v4 ]]; then _TR_BUF="WAI-Harness/spoke/local/runtime/track-buffer.json"; else _TR_BUF="WAI-Spoke/runtime/track-buffer.json"; fi

  # W1.6: pre-seed the buffer with HOOK-OWNED envelope fields via a real read-update-write
  # (not prose the model must reproduce by hand). Preserve any other keys already present
  # (e.g. a partial write from mid-turn tooling); ts is the hook's own system clock, never
  # model-reported. Best-effort — a write failure here must never block the turn.
  _TR_BUF_ABS="$PROJECT_DIR/$_TR_BUF"
  python3 - "$_TR_BUF_ABS" "$_TR_N" "$_TR_MODEL" <<'PYEOF' 2>/dev/null || true
import json, sys
from pathlib import Path
from datetime import datetime, timezone

buf_path, turn, model = sys.argv[1], sys.argv[2], sys.argv[3]
p = Path(buf_path)
data = {}
if p.exists():
    try:
        loaded = json.loads(p.read_text())
        if isinstance(loaded, dict):
            data = loaded
    except Exception:
        data = {}
data["event"] = "turn"
data["turn"] = int(turn)
data["source"] = "model"
data["ts"] = datetime.now(timezone.utc).isoformat()
data["ts_source"] = "system_clock"
data["model"] = model
p.parent.mkdir(parents=True, exist_ok=True)
tmp = p.with_suffix(p.suffix + ".tmp")
tmp.write_text(json.dumps(data, indent=2))
tmp.replace(p)
PYEOF

  # Harness version in the statusline (operator request, s138). Knowing the
  # running version is useful; knowing it is STALE is equally useful, so the
  # marker is computed rather than just printed:
  #   4.12.3      running the master cut
  #   4.12.3*     DRIFTED — the deployed copy does not match managed canon,
  #               i.e. an edit exists that is not actually running
  #   4.12.3<4.13.0  behind the master cut
  # Silent (empty) if the manifest is unreadable — a statusline must never fail
  # a turn, and an absent marker is honest where a guessed one is not.
  _TR_HV="$(python3 - "$CLAUDE_PROJECT_DIR" <<'HVEOF' 2>/dev/null || true
import json, os, sys, hashlib
root = sys.argv[1] if len(sys.argv) > 1 else "."
try:
    mf = os.path.join(root, "WAI-Harness/spoke/managed/MANIFEST.json")
    ver = json.load(open(mf))["harness_version"]
except Exception:
    sys.exit(0)
marker = ""
try:
    vf = os.path.join(root, "WAI-Harness/VERSION")
    if os.path.exists(vf):
        latest = open(vf).read().strip()
        if latest and latest != ver:
            marker = "<" + latest
    if not marker:
        # Deployed-vs-canon drift: an edit that is committed but not running is
        # the failure mode that hid a dead gate for ten days (s138 audit).
        canon = os.path.join(root, "WAI-Harness/spoke/managed/.claude/commands")
        live = os.path.join(root, ".claude/commands")
        if os.path.isdir(canon) and os.path.isdir(live):
            for n in os.listdir(canon):
                if not n.endswith(".md"):
                    continue
                a, b = os.path.join(canon, n), os.path.join(live, n)
                if not os.path.exists(b) or open(a, "rb").read() != open(b, "rb").read():
                    marker = "*"
                    break
except Exception:
    marker = ""
print("v" + ver + marker)
HVEOF
)"
  [ -n "$_TR_HV" ] && _TR_HV=" | ${_TR_HV}"
  _TR_SL="Turn ${_TR_N} | ${_TR_DATE} | ${_TR_TIME} | ${_TR_MODEL}${_TR_HV} | Gold: +{count}"
  printf '%s\n' "<wai-track-turn>"
  printf '%s\n' "WAI Track v2.0.2 per-turn obligations (an INSTRUCTION to act on, not a message to acknowledge):"
  printf '%s\n' "1. RICH ENTRY (Layer-1, full-feature): before your statusline, READ the pre-seeded ${_TR_BUF}"
  printf '%s\n' "   (the hook already wrote hook-owned keys: event, turn, source, ts, ts_source, model)."
  printf '%s\n' "   Do NOT overwrite the hook-owned keys — ADD your own judgment fields, then write the"
  printf '%s\n' "   full MERGED object back (hook-owned keys preserved verbatim + your fields added)."
  printf '%s\n' "   REQUIRED every turn (never omit): user_msg (verbatim <=500c), user_intent, action, outcome,"
  printf '%s\n' "   thinking (3-8 sentences: why/tradeoffs/what-was-rejected), focus (one line), phase."
  printf '%s\n' "   Soft-required unless empty this turn: decisions, insights, open. History is append-only."
  printf '%s\n' "   INSIGHT CONTRACT (feeds the lens insights view [s], place-awareness): make insights a look-BACK over the WHOLE"
  printf '%s\n' "   session so far, reconciling loose threads into one ACTIONABLE read for this turn; open = work the user"
  printf '%s\n' "   requested that is not yet verified or completed. As verbose as possible WHILE brief: dense and skimmable,"
  printf '%s\n' "   LANDING CONTRACT (non-negotiable): every \`open\` entry is an OBJECT, never a bare string:"
  printf '%s\n' "     {\"text\": \"...\", \"landing\": {\"kind\": \"...\", ...}}"
  printf '%s\n' "   A thread without a landing condition is chatter, not work. Pick the kind that can be"
  printf '%s\n' "   CHECKED BY A MACHINE with no judgement:"
  printf '%s\n' "     lug_completed {\"kind\":\"lug_completed\",\"id\":\"impl-foo-v1\"}      lug reaches completed/"
  printf '%s\n' "     file_exists   {\"kind\":\"file_exists\",\"path\":\"tools/foo.py\"}      path exists"
  printf '%s\n' "     file_contains {\"kind\":\"file_contains\",\"path\":\"x.sh\",\"needle\":\"FOO\"}"
  printf '%s\n' "     commit        {\"kind\":\"commit\",\"sha\":\"abc1234\"}                 sha is an ancestor of HEAD"
  printf '%s\n' "     command       {\"kind\":\"command\",\"cmd\":\"pytest -q tests/x.py\"}    exits 0"
  printf '%s\n' "     manual        {\"kind\":\"manual\",\"note\":\"why a human is required\"}  never auto-lands"
  printf '%s\n' "   The condition must be FALSE right now and become TRUE only when the work is genuinely"
  printf '%s\n' "   done. A condition satisfiable by partial work is a Goodhart target, not an oracle —"
  printf '%s\n' "   if you cannot write an honest one, use manual and say why. Never invent a passing check."
  printf '%s\n' "   so the reader gets place-awareness here and opens chat for full detail."
  printf '%s\n' "2. STATUSLINE (mandatory, NON-WAIVABLE — the LAST line of your response, even on a question/options"
  printf '%s\n' "   list and even if the user says 'no footer'). Emit EXACTLY, replacing {count} with the number of"
  printf '%s\n' "   durable Gold (project/identity-defining) entries you added this turn (0 if none):"
  printf '%s\n' "${_TR_SL}"
  printf '%s\n' "Omit BOTH only in plan mode."
  printf '%s\n' "</wai-track-turn>"
fi

# ── TASTEGRAPH PRESENTATION VECTOR (per-turn, unconditional) ────────────────
#
# s137 measured TasteGraph as near non-binding: preferences sourced ONLY from
# the graph had close to zero compliance. Cause was structural, not willpower —
# the whole graph was rendered once at SessionStart and never again, truncated
# mid-sentence, and 33 preferences were capped out silently.
#
# This fires the PRESENTATION slice every turn, at the moment output is being
# composed, which is where adherence failed most often. It must be a hook and
# never an agent-invoked step: anything that depends on the agent REMEMBERING
# to ask reproduces the exact failure being fixed.
#
# Loud on absent, per the same doctrine as the RESIDENT and TasteGraph blocks
# above — silence is how a dead system stays hidden for months.
# ${PROJECT_DIR} not ${CLAUDE_PROJECT_DIR}: line 16 establishes the :-. fallback.
# Using the raw var meant an unset CLAUDE_PROJECT_DIR resolved to /WAI-Harness/...,
# the [ -f ] test failed, and the whole block vanished SILENTLY — no DEGRADED
# banner. The one config where the feature disappears had the least signal.
_TGV="${PROJECT_DIR}/WAI-Harness/spoke/managed/tools/tastegraph_vector.py"
if [ -f "$_TGV" ]; then
  _TGV_OUT="$(python3 "$_TGV" select --vector presentation \
                --session "${WAI_SESSION:-unknown}" --turn "${_TR_N:-0}" \
                --context "composing turn output" 2>&1)"
  if [ -n "$_TGV_OUT" ]; then
    printf '%s\n' "<tastegraph-vector>"
    printf '%s\n' "These are the operator preferences that govern HOW YOU WRITE THIS REPLY."
    printf '%s\n' "Selected deterministically for the presentation vector; full bodies, never truncated."
    printf '%s\n' "$_TGV_OUT"
    printf '%s\n' "</tastegraph-vector>"
  else
    printf '%s\n' "<tastegraph-vector>DEGRADED: selector present but returned nothing — check ${_TGV}</tastegraph-vector>"
  fi
fi

# (1) CSRP AC4 — per-turn lane heartbeat (throttled ~5min via marker).
#
# --no-create is LOAD-BEARING (impl-lane-registry-liveness-authority): a heartbeat must
# NEVER mint a lane. lane-register defaults to create=True, so a prompt submitted after
# SessionEnd released the lane (or in any session that never registered one) RESURRECTED
# it as a ghost — the 11.4h phantom-peer bug the SessionEnd hook exists to close. Refresh
# a lane that exists; never author one. Birth belongs to SessionStart (lane-adopt) alone.
if [[ -n "$_UPS_SID" ]]; then
  _HBM="$BASE/runtime/lanes/$_UPS_SID/.hb"
  if [[ -z "$(find "$_HBM" -mmin -5 2>/dev/null)" ]]; then
    _WG="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/worktree_guard.py"
    if [[ -f "$_WG" ]]; then
      _UPS_LANE_ERR=$(mktemp 2>/dev/null || echo /tmp/wai-ups-lane-err.$$)
      if ! python3 "$_WG" lane-register --session "$_UPS_SID" --base "$BASE" \
             --transcript "$_UPS_TRANSCRIPT" --no-create >/dev/null 2>"$_UPS_LANE_ERR"; then
        # Loud, not silent: a heartbeat that fails silently is how a LIVE session goes
        # TTL-stale and every concurrency guard starts failing open (blind).
        echo "[WAI] degraded: lane heartbeat failed in user-prompt-submit for $_UPS_SID — $(head -c 300 "$_UPS_LANE_ERR" 2>/dev/null | tr '\n' ' '). This session may go stale in the lane registry; commit scoped (never git add -A)." >&2
      fi
      rm -f "$_UPS_LANE_ERR" 2>/dev/null
    fi
    mkdir -p "$(dirname "$_HBM")" 2>/dev/null && touch "$_HBM" 2>/dev/null || true
  fi
fi

# Per-lane session guard (key by CC session_id so concurrent sessions never clobber).
if [[ -n "$_UPS_SID" ]]; then
  GUARD_FILE="$RUNTIME_DIR/lanes/$_UPS_SID/guard.json"
else
  GUARD_FILE="$RUNTIME_DIR/session-guard.json"
fi
mkdir -p "$(dirname "$GUARD_FILE")"

GUARD_SESSION_ID=""; GUARD_COMPLETED="false"
if [[ -f "$GUARD_FILE" ]]; then
  GUARD_SESSION_ID=$(jq -r '.session_id // ""' "$GUARD_FILE" 2>/dev/null || echo "")
  GUARD_COMPLETED=$(jq -r '.protocol_completed // false' "$GUARD_FILE" 2>/dev/null || echo "false")
fi
LAST_SESSION_ID=$(jq -r '._session_state.last_session_id // ""' "$STATE_FILE" 2>/dev/null || echo "")
if [[ -z "$GUARD_SESSION_ID" || "$GUARD_SESSION_ID" == "$LAST_SESSION_ID" ]]; then
  printf '{"session_id":"session-%s","protocol_completed":false,"started_at":"%s"}\n' \
    "$(date +%Y%m%d-%H%M)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$GUARD_FILE"
  GUARD_COMPLETED="false"
fi

# (2) Post-compaction recovery flag (written by pre-compact.sh).
COMPACT_FLAG="$RUNTIME_DIR/compacted.flag"
POST_COMPACT=false
if [[ -f "$COMPACT_FLAG" ]]; then POST_COMPACT=true; rm -f "$COMPACT_FLAG"; fi
export POST_COMPACT

# Already ran this session and no compaction to recover → nothing more to do
# (the heartbeat above already fired, which is the per-turn essential).
[[ "$GUARD_COMPLETED" == "true" && "$POST_COMPACT" == "false" ]] && exit 0

# Mark protocol triggered (runtime file only — WAI-State.json stays clean).
TMP=$(mktemp)
jq '.protocol_completed = true | .protocol_last_run = (now | strftime("%Y-%m-%dT%H:%M:%SZ"))' "$GUARD_FILE" > "$TMP" 2>/dev/null && mv "$TMP" "$GUARD_FILE" || rm -f "$TMP"

# ── v4: brief is owned by SessionStart. Inject ONLY post-compact recovery. ──
if [[ "$MODE" == "v4" ]]; then
  if [[ "$POST_COMPACT" == "true" ]]; then
    # Belt-and-braces for the SessionStart source=compact matcher (compact-resume-inject.sh):
    # if that matcher does not fire in the installed CC version, this flag path still delivers
    # the persisted pointers + names /wai-compact-resume. Reads the same compact-resume.json.
    python3 - "$RUNTIME_DIR/compact-resume.json" <<'PYEOF'
import json, sys
from pathlib import Path
cr = {}
try:
    cr = json.loads(Path(sys.argv[1]).read_text())
except Exception:
    pass
lines = ["<wai-post-compact>",
         "Context compaction just occurred — restoring WAI session awareness:"]
if cr.get("session_id"):           lines.append(f'  Session:     {cr["session_id"]}')
if cr.get("lane_track_path"):      lines.append(f'  Track:       {cr["lane_track_path"]}')
if cr.get("base"):                 lines.append(f'  BASE:        {cr["base"]}')
if cr.get("active_initiative_id"): lines.append(f'  Initiative:  {cr["active_initiative_id"]}')
if cr.get("savepoint_status"):     lines.append(f'  Savepoint:   {cr["savepoint_status"]}')
if not any(cr.get(k) for k in ("session_id","lane_track_path","active_initiative_id")):
    lines.append("  (compact-resume.json absent — re-read WAI-State.json to restore context)")
lines += [
    "ACTION: Invoke /wai-compact-resume to run the post-compaction recovery protocol.",
    "If mid-closeout: re-read wai-closeout.md and resume from the step you were on.",
    "P1-Persist and P11-Lug-First are still active.",
    "</wai-post-compact>"]
print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "\n".join(lines)}}))
PYEOF
  fi
  exit 0
fi

# ── v3 legacy path: inject the pre-computed wakeup brief (BASE == WAI-Spoke). ──
export PROJECT_DIR
python3 - << 'PYEOF'
import json, os, subprocess
from pathlib import Path

project_dir = Path(os.environ.get('PROJECT_DIR', '.'))
brief_file  = project_dir / 'WAI-Spoke' / 'wakeup-brief.json'
state_file  = project_dir / 'WAI-Spoke' / 'WAI-State.json'
intent_file = project_dir / 'WAI-Spoke' / 'runtime' / 'session-intent.json'
intent = intent_label = None
if intent_file.exists():
    try:
        id_data = json.loads(intent_file.read_text())
        intent = id_data.get('intent'); intent_label = id_data.get('intent_label', '')
    except Exception:
        pass

def brief_freshness(brief):
    try:
        current_sha = subprocess.check_output(['git','rev-parse','HEAD'], cwd=str(project_dir), stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return 'STALE'
    brief_sha = brief.get('git_sha_at_generation', '')
    if not brief_sha: return 'STALE'
    if current_sha == brief_sha: return 'FRESH'
    RELEVANT = ['WAI-Spoke/WAI-State.json','WAI-Spoke/lugs/bytype/','WAI-Spoke/seed/ingest/processed/','templates/commands/wai']
    try:
        changed = subprocess.check_output(['git','diff','--name-only',brief_sha,current_sha], cwd=str(project_dir), stderr=subprocess.DEVNULL).decode().strip().split('\n')
        if not any(any(r in f for r in RELEVANT) for f in changed if f): return 'FRESH'
    except Exception:
        pass
    return 'STALE'

lines = []; status = 'STALE'
if brief_file.exists():
    try:
        brief = json.loads(brief_file.read_text())
        status = brief_freshness(brief)
        if status == 'FRESH':
            try:
                state = json.loads(state_file.read_text())
                name = state.get('wheel', {}).get('name', 'Unknown')
                version = state.get('wheel', {}).get('version', '?')
                sc = state.get('_session_state', {}).get('session_count', 0)
            except Exception:
                name, version, sc = 'Unknown', '?', 0
            qs = brief.get('queue_snapshot', {}); tp = brief.get('teachings_pending', 0)
            hs = brief.get('hub_signals_pending', 0); na = ((brief.get('next_actions') or ['None'])[0])[:120]
            ol = brief.get('open_lug_count', 0)
            lines += [f'Project: {name} v{version}', f'Session: {sc + 1}', f'Active: {ol} open',
                      f'Queue: {qs.get("ready_count",0)} ready | {qs.get("needs_refinement_count",0)} refinement | {qs.get("blocked_count",0)} blocked']
            if tp > 0: lines.append(f'Teachings: {tp} pending')
            if hs > 0: lines.append(f'Hub signals: {hs}')
            lines.append(f'Next: {na}')
    except Exception:
        pass
try:
    n = len([l for l in subprocess.check_output(['git','status','--short'], cwd=str(project_dir), stderr=subprocess.DEVNULL).decode().strip().split('\n') if l])
    lines.append(f'Uncommitted: {n} files')
except Exception:
    pass
if intent: lines.append(f'Intent: {intent} — {intent_label}')
if intent == 'implement':
    directive = ('DIRECTIVE: Intent=implement. Do NOT run /wai or teaching adoption. Read WAI-Spoke/lugs/bytype/task/open/ (1 call), brief user on in-progress lug state, begin implementation.')
elif intent == 'savepoint':
    directive = 'DIRECTIVE: Intent=savepoint resume. Read WAI-State._savepoint (1 call), load named lug, resume work.'
elif intent == 'teachings':
    directive = 'DIRECTIVE: Intent=teachings. Run /wai (wai-learn is deprecated — absorbed into wai Step 3a).'
elif intent == 'closeout':
    directive = 'DIRECTIVE: Intent=closeout. Run /wai-closeout.'
elif intent == 'refinement':
    directive = 'DIRECTIVE: Intent=refinement. Skip teaching adoption. Load needs_refinement queue.'
else:
    directive = ('DIRECTIVE: Run WAI wakeup protocol (/wai skill, templates/commands/wai.md). Include pending teachings in briefing. Do not stop wakeup before briefing is complete.')
post_compact = os.environ.get('POST_COMPACT', 'false') == 'true'
pcb = []
if post_compact:
    pcb = ['', '<wai-post-compact>', 'Context compaction just occurred. Before responding to the user:',
           '1. Invoke /wai-compact-resume to run the post-compaction recovery protocol.',
           '2. Re-read WAI-State.json to restore session context.',
           '3. If mid-closeout: re-read wai-closeout.md and resume from the step you were on.',
           'P1-Persist and P11-Lug-First are still active.', '</wai-post-compact>']
content_lines = ['<wai-session-init>', f'Wakeup brief: {status}'] + lines + pcb + [
    '', directive, 'EXCEPTION: If user message is a closeout command (/wai-closeout), skip briefing.', '</wai-session-init>']
print(json.dumps({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit', 'additionalContext': '\n'.join(content_lines)}}))
PYEOF
exit 0
