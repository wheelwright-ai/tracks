#!/usr/bin/env bash
# autopilot — kick off an Ozi run over work the operator is NOT blocking.
#
# The reliable path. Before this existed the only invocation was
#   python3 WAI-Harness/spoke/managed/tools/ozi_autopilot.py --spoke-path . --not-blocking-me
# which is not something anyone should have to remember, and `autopilot` alone
# resolved to an unrelated Ubuntu package. Basher's TUI has its own fork of the
# runner and does not carry --not-blocking-me at all, so "run autopilot" meant
# three different things depending on where it was typed.
#
# WHAT IT RUNS. Only lugs whose own disposition is auto_build — work that needs no
# decision from the operator. It reads the lug, not the ready-queue cache, so a
# stale index cannot leak operator-gated or ungroomed work into an unattended run.
#
# USAGE
#   ./autopilot                 if a run is IN FLIGHT: live status, refreshing
#                               otherwise: preview (dry-run), changes nothing
#   ./autopilot --live          actually dispatch (batch: verify at the end)
#   ./autopilot --chain -n 5    RECOMMENDED while trust is being built:
#                               one lug at a time, each independently verified
#                               before the next starts. A refusal is remediated
#                               and re-validated until it passes — only a
#                               CONFIRMED verdict advances the chain.
#   ./autopilot --chain --halt-on-refuse
#                               halt on the first refusal instead of remediating
#   ./autopilot --live -n 10    dispatch up to 10 lugs (default 3)
#   ./autopilot --all-work      drop the not-blocking-me filter (normal Ozi rules)
#   ./autopilot --spoke PATH    run against another spoke
#
# STEERING A RUN ALREADY IN FLIGHT (polled between lugs, no kill needed):
#   ./autopilot --stop          finish the current lug, then stop cleanly
#   ./autopilot --skip LUG-ID   do not dispatch that lug
#   ./autopilot --resume        clear all directives
#
# ROUNDS — every live run is one, recorded and undoable:
#   ./autopilot --rounds        list rounds with their verdicts, plus the
#                               cross-round read on whether chaining is paying off
#   ./autopilot --advantage     that read on its own: surviving-claim rate for
#                               chain vs batch, whether remediation converts, and
#                               which fault domains keep recurring
#   ./autopilot --undo ROUND-ID revert exactly that round
#   any other flags pass through to ozi_autopilot.py
#
# DRY-RUN IS THE DEFAULT, deliberately. A live run dispatches to `claude` and
# commits; that must be an explicit act, not what happens when someone types the
# obvious word to see what it does.
#
# AND IT NEVER RUNS TWO AT ONCE. With a run in flight, the bare command watches it
# rather than previewing (a preview would report the backlog as it was and imply
# nothing was happening), and --live refuses outright rather than racing.
set -euo pipefail

# SPOKE resolution must survive BOTH homes this script legitimately has:
# the spoke root (./autopilot, what a human types) and managed/tools/autopilot.sh
# (what the launcher's [a] action execs, and what gets distributed). Deriving it
# from dirname alone was correct only at the root — from managed/tools it silently
# resolved the spoke to .../managed/tools and every path built on it was wrong.
# Walk up looking for the harness instead: v4 layout first, v3 as the fallback,
# so a v4-only spoke is never mistaken for "not a spoke" the way the old
# WAI-Spoke-only detector did (signal-v4-aware-distribution-selectors-v1).
#
# Two passes, not one combined test. A single walk accepting either layout stops
# at the FIRST match, and a stray WAI-Spoke/ directory nested anywhere under the
# harness (there is one at managed/tools/WAI-Spoke/) hijacks the walk and returns
# a "spoke" several levels below the real one. v4 is authoritative: exhaust it
# first, and only then fall back to v3 for genuinely v3 spokes.
_ap_walk_for() {
  local marker="$1" dir="$2"
  while [[ "$dir" != "/" && -n "$dir" ]]; do
    [[ -d "$dir/$marker" ]] && { printf '%s' "$dir"; return 0; }
    dir="$(dirname "$dir")"
  done
  return 1
}

_ap_resolve_spoke() {
  _ap_walk_for "WAI-Harness/spoke/local" "$1" && return 0
  _ap_walk_for "WAI-Spoke" "$1" && return 0
  return 1
}

_AP_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPOKE="$(_ap_resolve_spoke "$_AP_HERE")" || SPOKE="$(_ap_resolve_spoke "$(pwd)")" || {
  echo "autopilot: no spoke found above $_AP_HERE or $(pwd)" >&2
  echo "  Pass --spoke PATH explicitly." >&2
  exit 1
}
RUNNER="$SPOKE/WAI-Harness/spoke/managed/tools/ozi_autopilot.py"
BUDGET=3
LIVE=0
CHAIN=0
ON_REFUTE="remediate"
# Plain word, never the flag string: argparse treats a value beginning with "--"
# as the next option and dies with "expected one argument".
SCOPE_NAME="not-blocking-me"
FILTER="--not-blocking-me"
PASSTHRU=()
ACTION=""
ACTION_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --live)      LIVE=1; shift ;;
    # The launcher's [a] action execs `autopilot.sh run --budget N`. The old v3
    # stub had no `run` verb at all, so that button died on "Unknown arg: run"
    # on every spoke, every time — the autopilot entry the operator actually
    # uses has never once dispatched. `run` means the human asked for work, so
    # it implies live; chaining stays opt-in via --chain.
    run)         LIVE=1; shift ;;
    # Chain: one lug at a time, each verified before the next begins. Slower than
    # a batch run by design — while confidence in unattended work is still being
    # established, a bad lug must stop the line rather than have nine more built
    # on top of it. Measured: a batch of 5 came back with 4 claims refuted.
    --chain)     CHAIN=1; LIVE=1; shift ;;
    --halt-on-refuse) ON_REFUTE="stop"; shift ;;
    --all-work)  FILTER=""; SCOPE_NAME="all-work"; shift ;;
    -n|--budget) BUDGET="$2"; shift 2 ;;
    --spoke)     SPOKE="$2"; RUNNER="$SPOKE/WAI-Harness/spoke/managed/tools/ozi_autopilot.py"; shift 2 ;;
    # Mid-run control and read-only queries. These used to act and exit INSIDE the
    # loop, which made them order-dependent in the worst possible way: `--advantage
    # --spoke basher` ran against the CURRENT spoke because --spoke had not been
    # parsed yet, and reported another wheel's numbers under basher's name. A flag
    # that silently answers about the wrong spoke is a false report, not a quirk.
    # So: record the action, finish parsing, then act once SPOKE is final.
    --stop)      ACTION="stop"; shift ;;
    --skip)      ACTION="skip"; ACTION_ARG="$2"; shift 2 ;;
    --rounds)    ACTION="rounds"; shift ;;
    --advantage) ACTION="advantage"; shift ;;
    --undo)      ACTION="undo"; ACTION_ARG="$2"; shift 2 ;;
    --resume)    ACTION="resume"; shift ;;
    -h|--help)   sed -n '2,36p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)           PASSTHRU+=("$1"); shift ;;
  esac
done

CONTROL="$SPOKE/WAI-Harness/spoke/local/runtime/autopilot-control.json"
ROUND_TOOL="$SPOKE/WAI-Harness/spoke/managed/tools/autopilot_round.py"
ADV_TOOL="$SPOKE/WAI-Harness/spoke/managed/tools/chain_advantage.py"

case "$ACTION" in
  stop)
    mkdir -p "$(dirname "$CONTROL")"
    echo '{"stop": true}' > "$CONTROL"
    echo "autopilot: STOP signalled — the run finishes its current lug, then stops cleanly."
    echo "  (clear with: ./autopilot --resume)"
    exit 0 ;;
  skip)
    mkdir -p "$(dirname "$CONTROL")"
    python3 -c "import json,sys;p=sys.argv[1];d={};
try:  d=json.load(open(p))
except Exception: pass
d.setdefault('skip',[]).append(sys.argv[2]);json.dump(d,open(p,'w'),indent=2)" \
      "$CONTROL" "$ACTION_ARG"
    echo "autopilot: will skip $ACTION_ARG (takes effect at the next lug boundary)"
    exit 0 ;;
  rounds)
    python3 "$ROUND_TOOL" --root "$SPOKE" --list
    # A list of verdicts says what happened; it does not say whether verifying
    # each step is EARNING its extra wall-clock. Print the cross-round read
    # alongside it so the justification for chain mode stays measured rather
    # than assumed.
    if [[ -f "$ADV_TOOL" ]]; then echo; python3 "$ADV_TOOL" --root "$SPOKE"; fi
    exit 0 ;;
  advantage)
    if [[ ! -f "$ADV_TOOL" ]]; then
      echo "autopilot: chain_advantage.py is not installed on $SPOKE." >&2
      echo "  This spoke has not yet received the harness cut that carries it." >&2
      exit 1
    fi
    python3 "$ADV_TOOL" --root "$SPOKE"
    exit $? ;;
  undo)
    python3 "$ROUND_TOOL" --root "$SPOKE" --undo "$ACTION_ARG"
    exit $? ;;
  resume)
    rm -f "$CONTROL"
    echo "autopilot: control cleared — no directives in force."
    exit 0 ;;
esac

if [[ ! -f "$RUNNER" ]]; then
  echo "autopilot: no ozi_autopilot.py under $SPOKE" >&2
  echo "  This spoke may predate the 4.13.x harness. Check WAI-Harness/VERSION." >&2
  exit 1
fi

# ── LIVE RUN? Then show the run, not a preview of one ────────────────────────
#
# A preview that ignores an in-flight run is worse than useless: it reports the
# backlog as it was, implies nothing is happening, and starts a second competing
# scan of the same lugs. If a run is already going, the only useful thing to show
# is that run.
#
# Progress is DERIVED — commits landed, lug transitions, whether a dispatched
# child is currently thinking — because the runner writes no per-run state file.
# Everything below is observable from outside it, so this needs no cooperation
# from the runner and cannot drift from what it is actually doing.
LIVE_PID="$(pgrep -f "ozi_autopilot.py --spoke-path $SPOKE" | head -1 || true)"

if [[ -n "$LIVE_PID" && "$LIVE" != "1" ]]; then
  # Anchor on when the RUN started, not when watching started. Using HEAD-at-watch
  # reported "landed: 0" over a run that had already committed twice — a live view
  # that under-reports progress is the same false-green class as everything else.
  RUN_START="$(ps -o lstart= -p "$LIVE_PID" 2>/dev/null | sed 's/^ *//')"
  echo "autopilot: a run is ALREADY IN FLIGHT (pid $LIVE_PID) — showing it live."
  echo "  Not starting a preview: a second scan would contend with it."
  echo "  Ctrl-C stops watching; it does NOT stop the run."
  echo

  while kill -0 "$LIVE_PID" 2>/dev/null; do
    ELAPSED="$(ps -o etime= -p "$LIVE_PID" 2>/dev/null | tr -d ' ')"
    CHILD="$(pgrep -P "$LIVE_PID" -a 2>/dev/null | grep -o 'model [a-z-]*' | head -1 || true)"
    # A dispatched child means a lug is being worked right now. No child means the
    # runner is between lugs — grooming, committing, or picking the next one.
    if [[ -n "$CHILD" ]]; then
      NOW="working a lug (${CHILD})"
    else
      NOW="between lugs (grooming / committing / selecting next)"
    fi
    LANDED="$(git -C "$SPOKE" log --oneline --since="$RUN_START" 2>/dev/null | wc -l | tr -d ' ')"
    DIRTY="$(git -C "$SPOKE" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"

    printf '\033[H\033[2J'
    echo "autopilot — LIVE  (pid $LIVE_PID, elapsed ${ELAPSED:-?})"
    echo
    echo "  now:      $NOW"
    echo "  landed:   $LANDED commit(s) this run"
    echo "  dirty:    $DIRTY uncommitted path(s)"
    echo
    if [[ "$LANDED" -gt 0 ]]; then
      echo "  commits:"
      git -C "$SPOKE" log --oneline --since="$RUN_START" 2>/dev/null | sed 's/^/    /'
      echo
    fi
    echo "  last activity:"
    tail -1 "$SPOKE/WAI-Harness/spoke/advisors/autopilot/activity-log.jsonl" 2>/dev/null \
      | python3 -c "
import sys, json
try:
    d = json.loads(sys.stdin.read())
    print('    %s  %s' % (str(d.get('ts',''))[:19], d.get('mode') or d.get('event_type','?')))
except Exception:
    print('    (none yet)')" 2>/dev/null || echo "    (none yet)"
    echo
    echo "  refreshing every 10s — Ctrl-C to stop watching (run continues)"
    sleep 10
  done

  echo
  echo "autopilot: run $LIVE_PID has FINISHED."
  git -C "$SPOKE" log --oneline --since="$RUN_START" 2>/dev/null | sed 's/^/  /'
  echo "  dirty tree: $(git -C "$SPOKE" status --porcelain | wc -l) path(s) — review before committing."
  exit 0
fi

if [[ -n "$LIVE_PID" && "$LIVE" == "1" ]]; then
  echo "autopilot: REFUSING to start — a run is already in flight (pid $LIVE_PID)." >&2
  echo "  Two concurrent runs would dispatch the same lugs twice and race on commits." >&2
  echo "  Watch it with: ./autopilot     (no flags)" >&2
  exit 1
fi

# ── CHAIN MODE: verify each lug before the next one runs ─────────────────────
if [[ "$CHAIN" == "1" && -f "$SPOKE/WAI-Harness/spoke/managed/tools/autopilot_round.py" ]]; then
  echo "autopilot: CHAIN mode — $BUDGET step(s), each verified before the next."
  echo "  scope: $SCOPE_NAME | on refusal: $ON_REFUTE"
  echo "  Slower on purpose: a refuted step halts the line instead of having the"
  echo "  rest built on top of it."
  echo
  exec python3 "$SPOKE/WAI-Harness/spoke/managed/tools/autopilot_round.py" \
    --root "$SPOKE" --chain "$BUDGET" --scope "$SCOPE_NAME" \
    --on-refute "$ON_REFUTE"
fi

# Show what is actually runnable before doing anything. A run that dispatches
# nothing and a run that was never going to look identical from the outside
# otherwise, which is how "I ran autopilot" turns into a false sense of progress.
SPLIT="$SPOKE/WAI-Harness/spoke/managed/tools/work_split.py"
if [[ -f "$SPLIT" ]]; then
  python3 "$SPLIT" --spoke-root "$SPOKE" --limit 3 || true
  echo
fi

# Recent rounds. Trust in autonomous work is a TREND, not a single verdict — a
# string of CLEAN rounds is the evidence that earns a bigger budget, and a REFUTED
# one in the history is what should make the next run smaller.
ROUND_TOOL="$SPOKE/WAI-Harness/spoke/managed/tools/autopilot_round.py"
if [[ -f "$ROUND_TOOL" ]]; then
  _ROUNDS="$(python3 "$ROUND_TOOL" --root "$SPOKE" --list 2>/dev/null | tail -6)"
  if [[ -n "$_ROUNDS" ]]; then
    echo "RECENT ROUNDS"
    echo "$_ROUNDS" | sed 's/^/  /'
    echo
  fi
fi

MODE_NOTE="DRY RUN — nothing will be dispatched or committed. Re-run with --live to execute."
DRY="--dry-run"
if [[ "$LIVE" == "1" ]]; then
  MODE_NOTE="LIVE — dispatching up to $BUDGET lug(s) to claude, and committing."
  DRY=""
fi

echo "autopilot: $MODE_NOTE"
echo "  spoke:  $SPOKE"
echo "  scope:  ${FILTER:-all work (normal Ozi rules)}"
echo

# ── OPEN THE ROUND ───────────────────────────────────────────────────────────
# Every live run IS a round: baseline recorded before dispatch, claims verified
# by an independent agent after, impact bounded and undoable. A run that is not a
# round is work nobody checked with a blast radius nobody bounded.
ROUND_TOOL="$SPOKE/WAI-Harness/spoke/managed/tools/autopilot_round.py"
ROUND_REC=""
if [[ "$LIVE" == "1" && -f "$ROUND_TOOL" ]]; then
  ROUND_REC="$(mktemp)"
  # SCOPE_NAME, never FILTER. FILTER is the flag string "--not-blocking-me", and
  # argparse reads a value starting with "--" as the next option, so this call
  # died with "--scope: expected one argument" on every non-chain live run. The
  # failure was silent — stderr only, empty ROUND_REC — so the run continued
  # UNROUNDED: no baseline, no independent verification, no undo, no bounded
  # blast radius. It is why every round record on disk came from a chain run.
  # The warning about exactly this is in this file's own header comment.
  python3 "$ROUND_TOOL" --root "$SPOKE" --open --budget "$BUDGET" \
    --scope "$SCOPE_NAME" > "$ROUND_REC"
  echo "round: $(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['round_id'])" "$ROUND_REC")"
  echo
fi

RUN_FROM="$(date -u +%Y-%m-%dT%H:%M)"

# Not exec'd: the run must be followed by its own verification. A pass that
# reports completions nobody checked is how 40,544 tokens of work ended up
# untracked with the lug claiming done.
python3 "$RUNNER" \
  --spoke-path "$SPOKE" \
  --budget "$BUDGET" \
  ${FILTER:+$FILTER} \
  ${DRY:+$DRY} \
  --trigger-source manual \
  "${PASSTHRU[@]}"
RUN_RC=$?

# ── SAY-DO GATE — native, not optional ───────────────────────────────────────
#
# Every lug the run marked completed must have its declared targets tracked and
# committed. Work that exists only in the working tree is one `git clean` from
# gone while the record claims it is done, and every downstream reader — the work
# split, the readiness verdict, the operator — believes the claim.
#
# HEALS BY DEFAULT after a live run. Leaving the operator to notice and run a
# second command is the same reactive-diligence failure the gate exists to end;
# the heal stages only each lug's OWN declared targets, never `git add -A`.
if [[ "$LIVE" == "1" ]]; then
  VERIFY="$SPOKE/WAI-Harness/spoke/managed/tools/autopilot_verify.py"
  if [[ -f "$VERIFY" ]]; then
    echo
    # Heal recording gaps FIRST, so the independent verifier judges the work as it
    # will actually exist rather than refuting a claim merely for being uncommitted.
    python3 "$VERIFY" --root "$SPOKE" --since "$RUN_FROM" --heal || true
  else
    echo
    echo "autopilot: SAY-DO GATE ABSENT — completions are UNVERIFIED this run." >&2
    echo "  autopilot_verify.py is missing; work may be untracked with lugs claiming done." >&2
  fi

  # ── CLOSE THE ROUND: independent verification of every claim ────────────────
  if [[ -n "$ROUND_REC" && -f "$ROUND_REC" ]]; then
    echo
    python3 "$ROUND_TOOL" --root "$SPOKE" --close "$ROUND_REC" || ROUND_RC=$?
    rm -f "$ROUND_REC"
    # A refuted round must not be followed by another. Stopping here is what makes
    # the impact group controlled rather than merely recorded.
    if [[ "${ROUND_RC:-0}" != "0" ]]; then
      echo
      echo "autopilot: round did NOT come back clean — next round blocked." >&2
      echo "  Review it, then fix the lug or: autopilot_round.py --undo <round-id>" >&2
      exit 2
    fi
  fi
fi

exit $RUN_RC
