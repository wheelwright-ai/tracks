#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# WAI CANONICAL — wai-enter.sh
# Home:     WAI-Harness/spoke/managed/tools/wai-enter.sh  (mywheel = is_master)
# Author:   mywheel authors this file; Basher DISTRIBUTES it (managed→live, fleet).
#           Edit here and recut MANIFEST in the same commit. Never edit a
#           distributed copy — the edit strands and the fork re-forms.
# Aliases:  wcl, wgm, wcx, woc, wpup, wqw → point here via ai-tools.sh
# harness-aware v2 (2026-07-15) — resolver VENDORED (see _wai_local_base below);
#           SCRIPT_DIR (where this file sits) is now distinct from CANON_ROOT
#           (the spoke root it was deployed into). See the CANON_ROOT block.
# Promoted from basher/wai-enter.sh @1790 lines (the only copy with worktree
# isolation + the dup guard). Supersedes the 660-line mywheel/wai-enter.sh and
# the 405-line v3 relic at managed/templates/spoke/wai-enter.sh.
# ─────────────────────────────────────────────────────────────────────────────
#
# wai-enter.sh — WAI pre-tool launch wrapper (hub-aware)
#
# Auto-detects hub vs spoke and runs appropriate prep steps.
# Hub detection: WAI-Hub/ directory present
# Spoke detection: WAI-Spoke/WAI-State.json present
#
# Usage:
#   ./wai-enter.sh           # launches claude (default)
#   ./wai-enter.sh gemini    # launches gemini
#   ./wai-enter.sh codex     # launches codex
#

# ── Live-edit immunity (snapshot-and-reexec) ─────────────────────────────────
# This is the ONE shared launcher every spoke's `wcl` runs. Bash reads a script
# file INCREMENTALLY, so if a basher session edits this file while a wcl sits
# paused at the menu, bash later re-reads half-written bytes and dies with a
# spurious parse error (observed: `line 966: syntax error near unexpected token
# ';;'`). Defuse it: on first entry, copy this file to a private temp snapshot
# and re-exec from there. The snapshot is never touched, so the in-flight run is
# immune to concurrent edits of the canonical file. The guard var prevents an
# exec loop; the real install dir is passed through so SCRIPT_DIR still resolves
# to the canonical tree (the snapshot lives in /tmp). Best-effort: if mktemp/copy
# fails we fall through and run in place (original behavior).
if [[ -z "${_WAI_ENTER_PINNED:-}" ]]; then
    _wai_self="$(readlink -f "${BASH_SOURCE[0]:-$0}")"
    _wai_real_dir="$(cd "$(dirname "$_wai_self")" && pwd)"
    _wai_snap="$(mktemp "${TMPDIR:-/tmp}/wai-enter.XXXXXX.sh" 2>/dev/null)" || _wai_snap=""
    if [[ -n "$_wai_snap" ]] && cat "$_wai_self" > "$_wai_snap" 2>/dev/null; then
        export _WAI_ENTER_PINNED="$_wai_real_dir"
        bash "$_wai_snap" "$@"; _wai_rc=$?
        rm -f "$_wai_snap" 2>/dev/null
        exit "$_wai_rc"
    fi
    [[ -n "$_wai_snap" ]] && rm -f "$_wai_snap" 2>/dev/null
fi

# SCRIPT_DIR resolves to the canonical install. Honor the pinned dir passed by the
# snapshot re-exec above (the snapshot's own $0 points at /tmp, not the install).
SCRIPT_DIR="${_WAI_ENTER_PINNED:-$(cd "$(dirname "$(readlink -f "$0")")" && pwd)}"
# Consume it: the pin is EXPORTED, so it is meant to cross exactly ONE hop (parent
# -> snapshot child). It was never unset, so it kept propagating to every
# descendant — including the launched tool and everything spawned inside it. A
# nested wai-enter.sh anywhere under a live session therefore inherited the OUTER
# launcher's install dir as its own SCRIPT_DIR: the re-exec was skipped and
# SCRIPT_DIR silently pointed at a DIFFERENT REPO. Harmless while SCRIPT_DIR was
# only an install path; not harmless now that CANON_ROOT derives from it and
# selects which spoke's WAI-State we read. Verified live: a shell under a wcl
# session carries _WAI_ENTER_PINNED=/home/mario/projects/basher.
unset _WAI_ENTER_PINNED
PROJECT_DIR="${PWD}"

# ── CANON_ROOT — the spoke root this launcher was DEPLOYED into ───────────────
# SCRIPT_DIR and CANON_ROOT were the SAME thing while this file lived at basher's
# repo root (a repo root IS a spoke root). Now that canon lives at
# WAI-Harness/spoke/managed/tools/, they are NOT the same, and every former
# "$SCRIPT_DIR is a spoke root" assumption would resolve to the TOOLS dir and
# silently read the wrong spoke's state / miss every tool. So:
#   SCRIPT_DIR = where this file physically sits (…/managed/tools when deployed)
#   CANON_ROOT = the spoke root above it
# Walk up past the known suffix when present; otherwise CANON_ROOT == SCRIPT_DIR,
# which preserves today's behavior byte-for-byte for a root-deployed launcher.
CANON_ROOT="$SCRIPT_DIR"
case "$SCRIPT_DIR" in
    */WAI-Harness/spoke/managed/tools)
        CANON_ROOT="${SCRIPT_DIR%/WAI-Harness/spoke/managed/tools}"
        [ -n "$CANON_ROOT" ] || CANON_ROOT="/"   # deployed at filesystem root
        ;;
esac

# ── Harness-aware working-state base (v4 when ACTIVATED, else v3) ─────────────
# Resolve BEFORE project-type detection: a pure-v4 spoke keeps its state at
# WAI-Harness/spoke/local/WAI-State.json (no WAI-Spoke/), so detecting only the
# v3 path would mis-classify it as "not a WAI project" and skip the menu.
#
# VENDORED, not sourced. The old line reached into
# "$SCRIPT_DIR/dotfiles/.config/basher/lib/harness.sh" — basher's private
# dotfiles. Managed canon must not reach into a sibling repo's tree, and that
# path exists nowhere in mywheel, so sourcing it here would ALWAYS miss and
# silently degrade every spoke to the v3 "$1/WAI-Spoke" stub — including pure-v4
# spokes, which would then be mis-detected as non-WAI projects.
# These bodies are deliberate byte-equivalent twins of harness.sh:25-76
# (basher_wai_local / _advisors / _state / _master_root). Same precedent, and
# for the same reason, as _wai_local_base in wai-exit.sh:33-44. If harness.sh
# ever changes, these must be re-twinned.
# NOTE: _master_root previously had NO fallback stub (only _local and _advisors
# did), so a missing harness.sh left the :485 call as a "command not found".
# All four are defined here, so the resolver is now complete by construction.
basher_wai_local() {
    local root="$1" v4="$1/WAI-Harness" l4="$1/WAI-Harness/spoke/local"
    case "${WAI_HARNESS_MODE:-}" in
        v3) printf '%s' "$root/WAI-Spoke"; return 0 ;;
        v4) [ -d "$l4" ] && { printf '%s' "$l4"; return 0; } ;;
    esac
    if [ -d "$v4" ] && { [ -e "$v4/.activated" ] || [ -f "$l4/WAI-State.json" ]; }; then
        printf '%s' "$l4"
    else
        printf '%s' "$root/WAI-Spoke"
    fi
}

basher_wai_advisors() {
    local root="$1" base
    base="$(basher_wai_local "$root")"
    case "$base" in
        */WAI-Harness/spoke/local) printf '%s' "$root/WAI-Harness/spoke/advisors" ;;
        *)                         printf '%s' "$root/WAI-Spoke/advisors" ;;
    esac
}

basher_wai_state() {
    printf '%s/WAI-State.json' "$(basher_wai_local "$1")"
}

basher_wai_master_root() {
    local root="$1" state hp
    state="$(basher_wai_state "$root")"
    [ -f "$state" ] || return 0
    hp=$(python3 -c "
import json,sys
try: print(json.load(open(sys.argv[1])).get('wheel',{}).get('hub_path',''))
except Exception: print('')
" "$state" 2>/dev/null)
    [ -n "$hp" ] && printf '%s' "${hp%/WAI-Harness/hub}"
}

# A dir is a spoke if EITHER the v3 (WAI-Spoke/) or the resolver-chosen v4
# (WAI-Harness/spoke/local/) WAI-State.json exists. Checks both for coexist safety.
_wai_is_spoke() {
    [[ -f "$1/WAI-Spoke/WAI-State.json" ]] && return 0
    [[ -f "$(basher_wai_local "$1")/WAI-State.json" ]] && return 0
    return 1
}

# ── Detect project type ──────────────────────────────────────────────────────
IS_HUB=false
IS_SPOKE=false
[[ -d "$PROJECT_DIR/WAI-Hub" ]] && IS_HUB=true
_wai_is_spoke "$PROJECT_DIR" && IS_SPOKE=true

# Walk up from CWD if not found at the root level
if [[ "$IS_HUB" == "false" && "$IS_SPOKE" == "false" ]]; then
    _wai_walk="$(dirname "$PROJECT_DIR")"
    while [[ "$_wai_walk" != "/" ]]; do
        if _wai_is_spoke "$_wai_walk"; then
            PROJECT_DIR="$_wai_walk"; IS_SPOKE=true; break
        elif [[ -d "$_wai_walk/WAI-Hub" ]]; then
            PROJECT_DIR="$_wai_walk"; IS_HUB=true; break
        fi
        _wai_walk="$(dirname "$_wai_walk")"
    done
    unset _wai_walk
fi

# Truly not a WAI project — launch tool directly (no SCRIPT_DIR fallback;
# falling back to the canonical's own WAI-State injected basher's state into
# unrelated directories).
#
# DRY-RUN (W5): this exec sat ABOVE the seam, so WAI_DRY_RUN=1 launched a REAL
# tool here and printed NO trace — the seam lied twice over, and every oracle
# built on the seam inherited that lie. Do NOT exec under dry-run: record the
# reason and fall through to the seam, which traces it and exits 0. Nothing
# between here and the seam mutates anything, so falling through is free.
# (The non-dry path is byte-for-byte unchanged.)
if [[ "$IS_HUB" == "false" && "$IS_SPOKE" == "false" ]]; then
    if [[ "${WAI_DRY_RUN:-0}" == "1" ]]; then
        _WAI_PASSTHRU="passthrough-not-wai"
    else
        exec "${1:-claude}" "${@:2}"
    fi
fi

# ── Harness-aware working-state base (v4 when ACTIVATED, else v3) ─────────────
# Resolver + fallbacks were sourced above (before project-type detection); here
# we just resolve the concrete working-state paths for the detected PROJECT_DIR.
WAI_LOCAL="$(basher_wai_local "$PROJECT_DIR")"
WAI_ADV="$(basher_wai_advisors "$PROJECT_DIR")"
_WL_REL="${WAI_LOCAL#"$PROJECT_DIR"/}"   # WAI-Spoke (v3) or WAI-Harness/spoke/local (v4)

# Validate: detected project must be registered in hub-registry.json.
# Prevents WAI scaffolding from running in stale clones, abandoned spokes, or
# directories that happen to contain a WAI-Spoke/ but aren't part of the fleet.
if [[ "$IS_SPOKE" == "true" ]]; then
    _wai_hub_path=$(jq -r '.wheel.hub_path // ""' "$WAI_LOCAL/WAI-State.json" 2>/dev/null)
    if [[ -n "$_wai_hub_path" && -f "$_wai_hub_path/hub-registry.json" ]]; then
        _wai_registered=$(PROJECT_DIR="$PROJECT_DIR" REG="$_wai_hub_path/hub-registry.json" python3 -c "
import json, os
try:
    target = os.path.realpath(os.environ['PROJECT_DIR'])
    reg = json.load(open(os.environ['REG']))
    for w in reg.get('wheels', []):
        p = w.get('path', '')
        if p and os.path.realpath(p) == target:
            print('yes'); break
    else:
        print('no')
except Exception:
    print('unknown')
" 2>/dev/null)
        if [[ "$_wai_registered" == "no" ]]; then
            # DRY-RUN (W5): same bug as the not-a-WAI exec above — this fired
            # before the seam and launched a REAL tool. Under dry-run, record the
            # reason and fall through to the seam (trace + exit 0). The banner is
            # suppressed too: it claims "launching claude", which a dry-run does
            # not do, and the trace is the dry-run's whole output contract.
            if [[ "${WAI_DRY_RUN:-0}" == "1" ]]; then
                _WAI_PASSTHRU="passthrough-unregistered"
                unset _wai_hub_path _wai_registered
            else
                printf "  \e[33m◇\e[0m  WAI: %s not in hub-registry — launching %s without WAI wrapper\n" \
                    "$PROJECT_DIR" "${1:-claude}" >&2
                unset _wai_hub_path _wai_registered
                exec "${1:-claude}" "${@:2}"
            fi
        fi
    fi
    unset _wai_hub_path _wai_registered
fi

# ── Style helpers ────────────────────────────────────────────────────────────
_W_BOLD='\e[1m'; _W_DIM='\e[2m'; _W_RST='\e[0m'
_W_GRN='\e[32m'; _W_YLW='\e[33m'; _W_CYN='\e[36m'
_wai_ok()   { printf "  ${_W_GRN}●${_W_RST}  %-12s %s\n" "$1" "$2"; }
_wai_warn() { printf "  ${_W_YLW}◇${_W_RST}  %-12s %s\n" "$1" "$2"; }
_wai_info() { printf "  ${_W_DIM}·${_W_RST}  %-12s %s\n" "$1" "$2"; }
_WAI_BRIEF_STATUS="scanning"

# ═════════════════════════════════════════════════════════════════════════════
# W5 SEAM — WAI_DRY_RUN=1 + shared launch-decision functions
# ═════════════════════════════════════════════════════════════════════════════
# WHY THIS EXISTS: this launcher was executed by ZERO tests because it had no
# seam — every path ended in a real `exec claude`. WAI_DRY_RUN=1 resolves
# everything exactly as a real launch would, prints a machine-parseable trace,
# and exits 0 WITHOUT executing any tool and WITHOUT mutating any state (no
# lane reserve, no worktree, no file writes, no mkdir).
#
# ── TRACE CONTRACT (STABLE — tests assert on this exact format) ──────────────
# One `KEY=value` per line, no blank lines, no ANSI. Keys emitted, in order:
#   WAI_DRY_RUN        always 1
#   TOOL               the resolved tool name
#   ARGV               full resolved argv, %q-quoted, space-joined
#   LAUNCH_MODE        direct | seed-two-phase | help-passthrough
#                      | passthrough-not-wai | passthrough-unregistered
#   CWD                PWD at trace time
#   SCRIPT_DIR         where this file physically sits
#   CANON_ROOT         the spoke root this launcher was deployed into
#   PROJECT_DIR        the detected spoke/hub root
#   IS_CONTINUATION    yes | no
#   HELP_SHORTCIRCUIT  yes | no
#   ISOLATION          yes | no      (would this launch isolate?)
#   ISOLATION_WHY      reason
#   LANE_LIVE          integer — OTHER live lanes (never counts our own token)
#   LANE_WHY           reason / how the count was obtained
#   LANE_TOKEN         the minted WAI_LAUNCH_TOKEN (reserved only when NOT dry)
#   DUPGUARD           fired | skipped
#   DUPGUARD_WHY       reason
#   OPEN_PROMPT_SET    yes | no
#
# ── PASSTHROUGH MODES (W5 fix) ───────────────────────────────────────────────
# Two escape hatches ABOVE this seam launch the tool raw, with no WAI wrapper:
#   passthrough-not-wai        cwd is not a WAI project at all      (see :~174)
#   passthrough-unregistered   a spoke, but not in hub-registry     (see :~205)
# Both used to `exec` outright, so WAI_DRY_RUN=1 launched a REAL tool and printed
# nothing. They now set _WAI_PASSTHRU and fall through to here.
#
# The KEY SET IS INVARIANT across every mode — parsers must never have to special-
# case which lines exist. On a passthrough the WAI wrapper is not applied at all,
# so the keys that describe wrapper decisions are emitted with an explicit value
# rather than omitted:
#   TOOL / ARGV        REAL — the exact raw argv the non-dry path would exec
#                      (raw by construction: no --model injection, no -r strip)
#   PROJECT_DIR        not-wai -> the cwd as probed; unregistered -> the spoke root
#   ISOLATION          always `no`      + ISOLATION_WHY  "na (<mode>) — ..."
#   LANE_LIVE          always `0`       + LANE_WHY       "na (<mode>) — ..."
#   DUPGUARD           always `skipped` + DUPGUARD_WHY   "na (<mode>) — ..."
#   OPEN_PROMPT_SET    always `no`      (a passthrough is never seeded)
#   LANE_TOKEN         minted as always, but NEVER reserved and never exported
#                      into a tool (a passthrough dry-run execs nothing at all)
#
# DRY-RUN CAVEAT (deliberate, documented): the interactive menu is NOT run in
# dry-run — it needs a TTY and writes session-intent.json. So OPEN_PROMPT_SET
# reflects seed mode (WAI_SEED_PROMPT) only; an interactive menu launch would
# resolve its prompt later. Every other key is the real resolved value.
_WAI_DRY="${WAI_DRY_RUN:-0}"
_WAI_PASSTHRU="${_WAI_PASSTHRU:-}"   # set by an above-seam escape hatch, else empty

# ── Launch token (W2) ────────────────────────────────────────────────────────
# Minted UNCONDITIONALLY and exported, so the SessionStart hook can adopt the
# reservation into a real lane keyed by the claude session id.
# Minted fresh every run on purpose: an inherited WAI_LAUNCH_TOKEN from an outer
# session would make this launcher adopt SOMEONE ELSE'S lane. (Same class of bug
# as the _WAI_ENTER_PINNED leak fixed above — an exported var that was meant to
# cross one hop and instead crossed every hop.)
WAI_LAUNCH_TOKEN="wcl-$(date +%s)-$$-${RANDOM}"
export WAI_LAUNCH_TOKEN
_WAI_RESERVED_TOKEN=""   # set only once a reserve actually lands

# Release a reservation that never became a real lane. Safe to call any number of
# times and in any state: once the SessionStart hook adopts the token, lane-adopt
# DELETES the token key (the token lane BECOMES the sid lane), so this is a no-op
# on the normal path. It only bites on an abort-before-boot, which is exactly the
# ghost-lane case it exists to prevent.
_wai_release_reservation() {
    [[ -n "${_WAI_RESERVED_TOKEN:-}" && -n "${_WG:-}" && -n "${_ISO_BASE:-}" ]] || return 0
    python3 "$_WG" lane-unregister --base "$_ISO_BASE" \
        --session "$_WAI_RESERVED_TOKEN" >/dev/null 2>&1 || true
}

# %q-quoted, space-joined argv — stable and parseable even when an arg (a seeded
# prompt) contains spaces or newlines.
_wai_argv_str() {
    local out="" a
    for a in "$@"; do out+="$(printf '%q' "$a") "; done
    printf '%s' "${out% }"
}

# ── Resolve TOOL + _TOOL_ARGS ────────────────────────────────────────────────
# THE shared resolver: the real launch and the dry-run trace both call this, so
# the trace can never drift from what actually gets executed. Call with "$@".
_wai_resolve_tool_args() {
    TOOL="${1:-}"
    if [[ -z "$TOOL" ]]; then
        if [[ "$_WAI_DRY" == "1" ]]; then
            TOOL="claude"          # never block a dry-run on a TTY prompt
        else
            read -r -p "  Tool to launch (claude/gemini/codex/uvx): " TOOL
        fi
    fi
    _TOOL_ARGS=("${@:2}")

    # --help/--version is a raw passthrough (see the short-circuit below): no -r
    # strip, no --model injection — exactly the argv the user typed.
    [[ "${_WAI_HELP:-false}" == "true" ]] && return 0

    # -r / --raw are wai-enter-PRIVATE flags and must never reach the binary —
    # but ONLY where they are ours to claim. `-r` is ALSO gemini's short form of
    # `--resume`, so stripping it unconditionally turned `wgm -r latest` into a
    # FRESH gemini session with the literal string 'latest' as its prompt.
    # `--raw` is ours for every tool; `-r` is ours for claude only.
    if [[ "$_RAW_MODE" == "true" ]]; then
        local _wai_filtered=() _a
        for _a in "${_TOOL_ARGS[@]}"; do
            [[ "$_a" == "--raw" ]] && continue
            [[ "$_a" == "-r" && "$TOOL" == "claude" ]] && continue
            _wai_filtered+=("$_a")
        done
        _TOOL_ARGS=("${_wai_filtered[@]}")
    fi

    # Default claude to opus unless --model already supplied.
    if [[ "$TOOL" == "claude" ]]; then
        local _wai_has_model=false _a
        for _a in "${_TOOL_ARGS[@]}"; do
            if [[ "$_a" == "--model" || "$_a" == --model=* ]]; then
                _wai_has_model=true; break
            fi
        done
        [[ "$_wai_has_model" == "false" ]] && _TOOL_ARGS=(--model opus "${_TOOL_ARGS[@]}")
    fi
}

# ── Lane count (W2) ──────────────────────────────────────────────────────────
# Sets _LANE_LIVE (OTHER live lanes) + _LANE_WHY. NEVER counts our own
# reservation — see the ordering note in _wai_isolation_decide.
_wai_lane_count() {
    _LANE_LIVE=0; _LANE_WHY=""
    if [[ "$_WAI_DRY" == "1" ]]; then
        # Read the registry FILE directly, read-only. We cannot call `lanes` here:
        # it reaps and RE-SAVES sessions-live.json (creating it when absent), which
        # would break the dry-run no-mutation contract.
        _LANE_LIVE=$(_WAI_REG="$_ISO_BASE/runtime/sessions-live.json" python3 -c "
import json, os
try:
    d = json.load(open(os.environ['_WAI_REG']))
    print(len(d.get('lanes', {})))
except Exception:
    print(0)
" 2>/dev/null)
        [[ "$_LANE_LIVE" =~ ^[0-9]+$ ]] || _LANE_LIVE=0
        _LANE_WHY="dry-run: raw read of ${_ISO_BASE}/runtime/sessions-live.json (no reap, no write, no reserve)"
        return 0
    fi
    python3 "$_WG" lane-reap --base "$_ISO_BASE" >/dev/null 2>&1 || true
    python3 "$_WG" wt-reap   --repo "$_MAIN"    >/dev/null 2>&1 || true
    # "0 lanes" and "cannot determine" are DIFFERENT answers. The old form stacked
    # suppressions so ANY failure collapsed to 0 -> no isolation, no message. But a
    # corrupt/unreadable registry usually MEANS concurrent writers — so the one case
    # where isolation matters most was the case that disabled it. FAIL TOWARD
    # ISOLATING: a needless worktree is cheap; a shared tree under concurrency is not.
    _LANE_LIVE=$(python3 "$_WG" lanes --base "$_ISO_BASE" 2>/dev/null \
        | _WAI_TOK="$WAI_LAUNCH_TOKEN" python3 -c "
import sys, json, os
tok = os.environ.get('_WAI_TOK', '')
d = json.load(sys.stdin)
# Exclude OUR OWN reservation: we reserve BEFORE this read (see the ordering note),
# so counting every key would make this launcher see itself and always self-isolate.
print(sum(1 for k in d.get('lanes', {}) if k != tok))
" 2>/dev/null)
    local _rc=$?
    if [[ $_rc -ne 0 || -z "$_LANE_LIVE" || ! "$_LANE_LIVE" =~ ^[0-9]+$ ]]; then
        _wai_warn "Isolation" "cannot read lane registry at ${_ISO_BASE} (rc=${_rc}) — assuming concurrent sessions and isolating"
        _LANE_LIVE=1
        _LANE_WHY="lane registry unreadable (rc=${_rc}) — failing toward isolation"
        return 0
    fi
    _LANE_WHY="live lanes in ${_ISO_BASE} excluding our own token ${WAI_LAUNCH_TOKEN}"
}

# ── Isolation: DECIDE (read-only) ────────────────────────────────────────────
# Sets _ISO_SHOULD (yes/no) + _ISO_WHY, and _WG/_MAIN/_ISO_BASE for apply.
# Creates NO worktree and performs no cd. In a real (non-dry) run it DOES reserve
# a lane — that is the one deliberate write, and it is what closes the pre-exec
# race (see the ordering note below).
_wai_isolation_decide() {
    _ISO_SHOULD=no; _ISO_WHY=""; _LANE_LIVE=0; _LANE_WHY=""
    _WG=""; _MAIN=""; _ISO_BASE=""
    if [[ "${_WAI_HELP:-false}" == "true" ]]; then
        _ISO_WHY="--help/--version passthrough"; _LANE_WHY="n/a (help passthrough)"; return 0
    fi
    if [[ "$IS_SPOKE" != "true" ]]; then
        _ISO_WHY="not a spoke"; _LANE_WHY="n/a (not a spoke)"; return 0
    fi
    if [[ "$TOOL" != "claude" ]]; then
        _ISO_WHY="tool is ${TOOL}, not claude"; _LANE_WHY="n/a (non-claude tool)"; return 0
    fi
    if [[ "${WAI_NO_ISOLATE:-0}" == "1" ]]; then
        _ISO_WHY="WAI_NO_ISOLATE=1"; _LANE_WHY="n/a (isolation disabled)"; return 0
    fi
    local _a
    for _a in "${_TOOL_ARGS[@]}"; do
        if [[ "$_a" == "-p" || "$_a" == "--print" ]]; then
            _ISO_WHY="headless (-p) — shared tree by design"; _LANE_WHY="n/a (headless)"; return 0
        fi
    done
    # Canon-relative fallbacks + a LOUD miss. Every other tool lookup in this file
    # degrades with a message; this one used to have no fallback at all, so a spoke
    # without the tool silently got NO isolation and no hint as to why.
    _WG="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/worktree_guard.py"
    [[ -f "$_WG" ]] || _WG="$PROJECT_DIR/tools/worktree_guard.py"
    [[ -f "$_WG" ]] || _WG="$SCRIPT_DIR/worktree_guard.py"
    [[ -f "$_WG" ]] || _WG="$CANON_ROOT/WAI-Harness/spoke/managed/tools/worktree_guard.py"
    if [[ ! -f "$_WG" ]]; then
        _WG=""
        [[ "$_WAI_DRY" != "1" ]] && _wai_warn "Isolation" "worktree_guard.py not found — this session shares the tree (concurrent sessions may collide)"
        _ISO_WHY="worktree_guard.py not found — sharing tree"; _LANE_WHY="no worktree_guard.py"
        return 0
    fi
    # MAIN worktree root: lanes + worktrees live there (shared across worktrees).
    _MAIN=$(git -C "$PROJECT_DIR" worktree list --porcelain 2>/dev/null | awk '/^worktree /{print $2; exit}')
    _MAIN="${_MAIN:-$PROJECT_DIR}"
    # Use the RESOLVER, not a hand-rolled -d test: the resolver additionally requires
    # .activated OR local/WAI-State.json, so on a v4-dormant spoke a -d test would read
    # lanes from a base the hooks never write to -> count always 0 -> isolation NEVER
    # fires, silently, in exactly the half-migrated state where it matters most.
    _ISO_BASE="$(basher_wai_local "$_MAIN")"
    # Skip if we're ALREADY inside a worktree (don't nest isolation).
    if [[ "$(git -C "$PROJECT_DIR" rev-parse --show-toplevel 2>/dev/null)" != "$_MAIN" ]]; then
        _ISO_WHY="already inside a worktree — no nested isolation"; _LANE_WHY="n/a (already isolated)"
        return 0
    fi

    # ── W2 ORDERING: RESERVE **BEFORE** THE READ ─────────────────────────────
    # MEASURED hazard: a ~7s window where the launcher had read lanes, found 0, and
    # exec'd — but no lane existed yet, because registration happened POST-exec in a
    # hook. Two launches inside that window both saw 0, neither isolated, and both
    # landed in the shared tree — the exact collision isolation exists to prevent.
    #
    # Reserving AFTER the read would leave that window wide open (both read 0, then
    # both reserve, then both share). So we reserve FIRST — the lane is visible to
    # every other launcher from t=0 — and defuse the self-isolation trap by having
    # _wai_lane_count EXCLUDE OUR OWN TOKEN from the count rather than by delaying
    # the reserve. Worst case two launchers reserve simultaneously and BOTH isolate:
    # that is the safe direction (a needless worktree is cheap; a shared tree under
    # concurrency is not).
    if [[ "$_WAI_DRY" != "1" ]]; then
        if python3 "$_WG" lane-reserve --base "$_ISO_BASE" --token "$WAI_LAUNCH_TOKEN" \
                --pid "$$" --cwd "$PROJECT_DIR" >/dev/null 2>&1; then
            _WAI_RESERVED_TOKEN="$WAI_LAUNCH_TOKEN"
            # Release the reservation if this launch dies before its claude ever boots
            # (dup-guard abort, user declines, crash). No-op once the hook adopts it.
            trap _wai_release_reservation EXIT
        fi
    fi

    _wai_lane_count
    if [[ "${_LANE_LIVE:-0}" -ge 1 ]]; then
        _ISO_SHOULD=yes; _ISO_WHY="${_LANE_LIVE} other live session(s)"
    else
        _ISO_WHY="0 other live lanes — shared tree (zero cost)"
    fi
}

# ── Isolation: APPLY (mutates — creates the worktree and cds into it) ────────
_wai_isolation_apply() {
    local _HDEV="" _WTNAME _WT
    [[ -d "$_MAIN/WAI-Harness/hub" ]] && _HDEV="--harness-dev"
    _WTNAME="s$(date +%y%m%d-%H%M%S)"
    _WT=$(python3 "$_WG" wt-new "$_WTNAME" --repo "$_MAIN" $_HDEV 2>/dev/null \
          | python3 -c 'import sys,json;print(json.load(sys.stdin).get("worktree",""))' 2>/dev/null)
    [[ -n "$_WT" && -d "$_WT" ]] || return 0
    # Announce only what has ACTUALLY happened, and set the flag ONLY on a successful
    # cd. The old order printed "isolating..." BEFORE the cd, then ran `cd "$_WT" || true`
    # and set _WAI_ISOLATED=1 UNCONDITIONALLY. If the cd failed, the session stayed in the
    # SHARED tree while the banner claimed otherwise, AND the flag lied to the dup guard
    # below — which skips itself when _WAI_ISOLATED=1. A failed cd turned BOTH safety
    # nets off at once and reported success. (`cd || true` satisfies shellcheck SC2164 —
    # the lint-pleasing idiom IS the bug here. Do not "fix" it back.)
    printf "\n  ${_W_YLW}⚠ %s live session(s)${_W_RST} — isolating this one in its own worktree:\n    %s\n" "$_LANE_LIVE" "$_WT"
    if cd "$_WT"; then
        _WAI_ISOLATED=1
        printf "  ${_W_DIM}closeout reconciles it (worktree_guard wt-finish %s --repo %s --merge).${_W_RST}\n" "$_WTNAME" "$_MAIN"
    else
        printf "  ${_W_YLW}⚠ ISOLATION FAILED${_W_RST} — could not enter %s\n" "$_WT"
        printf "  ${_W_YLW}  This session stays in the SHARED tree alongside %s other live session(s).${_W_RST}\n" "$_LANE_LIVE"
        printf "  ${_W_DIM}  Duplicate-session guard stays armed. Ctrl-C now if that is not what you want.${_W_RST}\n"
    fi
}

# ── Duplicate-session guard: DECIDE (read-only) ──────────────────────────────
# A second INTERACTIVE claude in the same PROJECT_DIR receives mirrored keystrokes
# via zellij's dual-layer focus (the floating-twin bug). Sets _DUP_STATE
# (fired/skipped) + _DUP_WHY + _dup_pids.
# NOTE: the /proc scan stays. A later wave retires it once the lane registry is
# proven authoritative; retiring it now would trade false positives for false
# negatives, which is strictly worse.
_wai_dupguard_decide() {
    _DUP_STATE="skipped"; _DUP_WHY=""; _dup_pids=()
    if [[ "${_WAI_HELP:-false}" == "true" ]]; then _DUP_WHY="--help/--version passthrough"; return 0; fi
    if [[ "$TOOL" != "claude" ]]; then _DUP_WHY="tool is ${TOOL}, not claude"; return 0; fi
    if [[ "${WAI_ALLOW_DUP:-0}" == "1" ]]; then _DUP_WHY="WAI_ALLOW_DUP=1"; return 0; fi
    # In dry-run nothing is applied, so _WAI_ISOLATED is still 0 — consult the
    # DECISION instead, so the trace reports what would really happen.
    if [[ "${_WAI_ISOLATED:-0}" == "1" ]] \
       || [[ "$_WAI_DRY" == "1" && "${_ISO_SHOULD:-no}" == "yes" ]]; then
        _DUP_WHY="source-isolated in its own worktree (different CWD)"; return 0
    fi
    local _a _pd _dp
    for _a in "${_TOOL_ARGS[@]}"; do
        if [[ "$_a" == "-p" || "$_a" == "--print" ]]; then _DUP_WHY="headless (-p)"; return 0; fi
    done
    local _st
    for _pd in /proc/[0-9]*; do
        _dp="${_pd#/proc/}"
        [[ "$_dp" == "$$" ]] && continue
        [[ "$(cat "$_pd/comm" 2>/dev/null)" == "claude" ]] || continue
        # LIVENESS: a ZOMBIE claude (exited, parent never reaped it) still has
        # comm=claude and a cwd link, so the old check counted it as a running session
        # and blocked a fresh launch with "a live Claude session already runs" when there
        # was NONE (operator, 2026-07-20: dead pid 630438 reported as live). Skip anything
        # not runnable; `kill -0` does NOT catch this — it succeeds for zombies too. Parse
        # the state robustly: comm is parenthesised and may contain spaces, so split on the
        # LAST ')' and take the next field, never awk $3.
        _st=$(cat "$_pd/stat" 2>/dev/null); _st="${_st##*) }"; _st="${_st%% *}"
        case "$_st" in Z|X|x|"") continue ;; esac
        [[ "$(readlink "$_pd/cwd" 2>/dev/null)" == "$PROJECT_DIR" ]] || continue
        tr '\0' ' ' < "$_pd/cmdline" 2>/dev/null | grep -qE ' -p( |$)| --print' && continue
        _dup_pids+=("$_dp")
    done
    if [[ "${#_dup_pids[@]}" -gt 0 ]]; then
        _DUP_STATE="fired"
        _DUP_WHY="${#_dup_pids[@]} live interactive claude session(s) in ${PROJECT_DIR} (pid: ${_dup_pids[*]})"
    else
        _DUP_WHY="no live interactive claude in ${PROJECT_DIR}"
    fi
}

# ── Duplicate-session guard: APPLY (prompts; may abort the launch) ───────────
_wai_dupguard_apply() {
    local _dp _dup_ans
    printf "\n  ${_W_YLW}⚠ duplicate-session guard${_W_RST}\n"
    printf "  A live Claude session already runs in this project (%s):\n" "$(basename "$PROJECT_DIR")"
    for _dp in "${_dup_pids[@]}"; do
        printf "    pid %s  tty %s\n" "$_dp" "$(ps -o tty= -p "$_dp" 2>/dev/null | tr -d ' ')"
    done
    printf "  A second interactive session here causes keystroke mirroring (the floating-twin bug).\n"
    if [[ -t 0 ]]; then
        printf "  Launch another anyway? [y/N] "
        read -r _dup_ans
        if [[ ! "$_dup_ans" =~ ^[Yy] ]]; then
            printf "  ${_W_DIM}Aborted — attach to the existing session instead (WAI_ALLOW_DUP=1 to force).${_W_RST}\n"
            # The EXIT trap releases our reservation — without it this abort would
            # leave a ghost lane that isolates every future launch for 15 minutes.
            exit 0
        fi
    else
        printf "  ${_W_DIM}No TTY — aborting to avoid a silent twin (WAI_ALLOW_DUP=1 to force).${_W_RST}\n"
        exit 0
    fi
}

# ── The trace itself ─────────────────────────────────────────────────────────
# THE ONLY emitter. $1 optionally forces LAUNCH_MODE (the above-seam passthroughs
# pass their mode here) — deliberately ONE function so a passthrough trace can
# never drift from a normal one. A forced mode is always prompt-less: an
# escape-hatch launch never carries an opening prompt.
_wai_dry_run_trace() {
    local _mode="${1:-}" _prompt_set="no"
    if [[ -n "$_mode" ]]; then
        :                                   # forced (passthrough) — prompt_set stays no
    elif [[ "${_WAI_HELP:-false}" == "true" ]]; then
        _mode="help-passthrough"
    else
        _mode="direct"
        if [[ -n "${_OPEN_PROMPT:-}" ]]; then
            _prompt_set="yes"
            [[ "$TOOL" == "claude" && "$_IS_CONTINUATION" == "false" ]] && _mode="seed-two-phase"
        fi
    fi
    printf 'WAI_DRY_RUN=1\n'
    printf 'TOOL=%s\n'              "$TOOL"
    printf 'ARGV=%s\n'              "$(_wai_argv_str "$TOOL" "${_TOOL_ARGS[@]}")"
    printf 'LAUNCH_MODE=%s\n'       "$_mode"
    printf 'CWD=%s\n'               "$PWD"
    printf 'SCRIPT_DIR=%s\n'        "$SCRIPT_DIR"
    printf 'CANON_ROOT=%s\n'        "$CANON_ROOT"
    printf 'PROJECT_DIR=%s\n'       "$PROJECT_DIR"
    printf 'IS_CONTINUATION=%s\n'   "$([[ "$_IS_CONTINUATION" == "true" ]] && echo yes || echo no)"
    printf 'HELP_SHORTCIRCUIT=%s\n' "$([[ "${_WAI_HELP:-false}" == "true" ]] && echo yes || echo no)"
    printf 'ISOLATION=%s\n'         "${_ISO_SHOULD:-no}"
    printf 'ISOLATION_WHY=%s\n'     "${_ISO_WHY:-}"
    printf 'LANE_LIVE=%s\n'         "${_LANE_LIVE:-0}"
    printf 'LANE_WHY=%s\n'          "${_LANE_WHY:-}"
    printf 'LANE_TOKEN=%s\n'        "$WAI_LAUNCH_TOKEN"
    printf 'DUPGUARD=%s\n'          "${_DUP_STATE:-skipped}"
    printf 'DUPGUARD_WHY=%s\n'      "${_DUP_WHY:-}"
    printf 'OPEN_PROMPT_SET=%s\n'   "$_prompt_set"
}

# ── Herald status (active cross-spoke auto-answer/action daemon) ──────────────
# Surfaced at the TOP of every launch so you can see whether Herald is running.
# Consumes Herald's stable `status --oneline` contract instead of poking the
# pidfile/json directly, so the banner survives Herald runtime refactors
# (completion-herald-status-oneline-contract-v1). Stays silent when Herald isn't
# present in this spoke. One short python subprocess on the launch path.
_wai_herald_status() {
    local hd="${WAI_LOCAL}/runtime/herald"
    [[ -d "$hd" ]] || return 0                       # Herald not present here — say nothing
    local hp="${PROJECT_DIR}/WAI-Harness/spoke/managed/tools/herald_poll.py"
    [[ -f "$hp" ]] || return 0
    # Contract: "<state> | <N> queued", state in {running, enabled-idle, inactive}.
    local oneline state rest inbox
    oneline="$(python3 "$hp" --spoke-root "$PROJECT_DIR" status --oneline 2>/dev/null)"
    [[ -n "$oneline" ]] || return 0
    state="${oneline%% *}"                            # first token
    rest="${oneline##*| }"; inbox="${rest%% queued*}" # the N in "| N queued"
    local q=""; [[ "${inbox:-0}" -gt 0 ]] && q=" · ${inbox} queued"
    case "$state" in
        running)      _wai_ok   "Herald" "running${q}" ;;
        enabled-idle) _wai_warn "Herald" "enabled, idle${q}  (basher herald start)" ;;
        *)            _wai_info "Herald" "inactive${q}" ;;
    esac
}
# ── 1a0. --help/--version short-circuit (W3) ────────────────────────────────
# `wcl -h` used to traverse the capability runner, a ~15s ozi pre-scan, the full
# menu and both guards just to print a help string — and then printed it TWICE,
# because a pending savepoint set an opening prompt and the two-phase block ran
# claude once to seed and once to resume. Help is a pure passthrough: nothing
# below this point has any bearing on it.
_WAI_HELP=false
for _arg in "${@:2}"; do
    case "$_arg" in
        -h|--help|-v|--version) _WAI_HELP=true; break ;;
    esac
done
unset _arg
# Non-dry: exec straight through, exactly as typed (no --model, no -r strip).
# Dry-run falls through so the trace can prove the short-circuit happened.
if [[ "$_WAI_HELP" == "true" && "$_WAI_DRY" != "1" ]]; then
    exec "${1:-claude}" "${@:2}"
fi

# ── 1b. Intent probe (spoke sessions only) ──────────────────────────────────
# ── ONE NOTION OF CONTINUATION (W3) ─────────────────────────────────────────
# This probe understood `-c` and NOTHING else, which silently broke four things.
# `_IS_CONTINUATION` is now the single concept: true when ANY signal says "this
# session already has history". A continuation must never be re-seeded with an
# opening prompt — it HAS its context. (--fork-session is NOT the fix: it clones
# the session rather than resuming it.)
#
# Signals, and why each is here:
#   -c / --continue   continue the most recent session. `--continue` was never
#                     matched, so `wcl --continue` rendered the menu, built an
#                     opening prompt, and died on
#                     `claude --session-id X -p '...' --continue`:
#                     "Error: --session-id can only be used with --continue or
#                     --resume if --fork-session is also specified."
#   --resume [id]     the picker (scripts/claude-resume-picker.sh:132) execs
#                     `wai-enter claude --resume <id>`. Unmatched, so the operator
#                     re-answered a menu they had ALREADY answered in the picker,
#                     phase 1 died on the error above (LOSING the opening prompt
#                     silently), and phase 2 emitted a duplicate --resume that
#                     landed in the right session only by accident of last-wins
#                     arg parsing.
#   -r                claude ONLY. `-r` is this launcher's private raw-mode flag
#                     AND gemini's short `--resume`. The claim was untooled, so
#                     `wgm -r latest` launched a FRESH gemini with 'latest' as its
#                     prompt. See the matching TOOL gate in _wai_resolve_tool_args.
#   --raw             ours for every tool; not a real flag of any of them.
#
# Raw-mode nuance: an EXPLICIT target (-r, --resume, --raw) means the operator has
# already chosen — go raw, no priority auto-select. Bare -c/--continue keeps its
# existing auto-select behavior (it only ever writes session-intent.json; the
# opening prompt is gated off for every continuation regardless).
_CONTINUE_MODE=false
_RAW_MODE=false
_IS_CONTINUATION=false
_WAI_TOOL_PROBE="${1:-claude}"
for _arg in "${@:2}"; do
    case "$_arg" in
        -c|--continue)
            _CONTINUE_MODE=true; _IS_CONTINUATION=true ;;
        --resume|--resume=*)
            _CONTINUE_MODE=true; _IS_CONTINUATION=true; _RAW_MODE=true ;;
        --raw)
            _CONTINUE_MODE=true; _IS_CONTINUATION=true; _RAW_MODE=true ;;
        -r)
            # claude only — gemini's own --resume short flag must survive.
            if [[ "$_WAI_TOOL_PROBE" == "claude" ]]; then
                _CONTINUE_MODE=true; _IS_CONTINUATION=true; _RAW_MODE=true
            fi ;;
    esac
done
unset _arg _WAI_TOOL_PROBE

# ── Seed-prompt mode (basher TUI) ───────────────────────────────────────────
# An external caller (the basher TUI's review/do-it-all items) supplies the opening
# prompt via WAI_SEED_PROMPT and wants a FRESH auto-submitting session launched
# through THIS same launcher — so it inherits isolation + dup-guard + wai-exit and
# never diverges from wcl. Reuse continue-mode's menu-skip; the prompt is delivered
# by the shared two-phase launch below. This is the single source of truth: the TUI
# no longer reimplements `claude --session-id -p`/`--resume`.
_SEED_MODE=false
if [[ -n "${WAI_SEED_PROMPT:-}" ]]; then
    _SEED_MODE=true
    _CONTINUE_MODE=true
fi

# ── W5 SEAM: dry-run exit point ──────────────────────────────────────────────
# Placed HERE on purpose: everything above is pure resolution (paths, harness
# base, project type, the intent probe); everything below mutates state (brief
# generation, capability runner, ozi pre-scan, the menu's session-intent.json,
# mkdirs, doctor, the launch itself). Dry-run resolves the tool + argv and the
# two launch decisions through the SAME functions the real path calls, prints the
# trace, and exits — so the trace can never drift from real behavior.
if [[ "$_WAI_DRY" == "1" ]]; then
    # An above-seam escape hatch already decided to launch raw with no WAI wrapper.
    # Report exactly that and exit 0 — WITHOUT exec'ing (the bug this fixes) and
    # without running the wrapper decisions, which do not apply to a raw launch.
    if [[ -n "$_WAI_PASSTHRU" ]]; then
        # Mirror the passthrough exec lines byte-for-byte: `exec "${1:-claude}" "${@:2}"`.
        # Raw by construction — no --model injection, no -r strip. Set directly (not
        # via _wai_resolve_tool_args) because that resolver applies wrapper argv
        # rewriting the passthrough path deliberately skips.
        TOOL="${1:-claude}"; _TOOL_ARGS=("${@:2}")
        _ISO_SHOULD="no";      _ISO_WHY="na (${_WAI_PASSTHRU}) — WAI wrapper not applied"
        _LANE_LIVE="0";        _LANE_WHY="na (${_WAI_PASSTHRU}) — no lane registry consulted"
        _DUP_STATE="skipped";  _DUP_WHY="na (${_WAI_PASSTHRU}) — WAI wrapper not applied"
        _OPEN_PROMPT=""
        _wai_dry_run_trace "$_WAI_PASSTHRU"
        exit 0
    fi
    [[ "$_SEED_MODE" == "true" ]] && _OPEN_PROMPT="${WAI_SEED_PROMPT:-}"
    # Mirror the real path: a continuation never carries an opening prompt.
    [[ -n "${_OPEN_PROMPT:-}" && "$_IS_CONTINUATION" == "true" ]] && _OPEN_PROMPT=""
    _wai_resolve_tool_args "$@"
    _wai_isolation_decide
    _wai_dupguard_decide
    _wai_dry_run_trace
    exit 0
fi

[[ "$IS_SPOKE" == "true" ]] && _wai_herald_status

# ── 1. Generate fresh wakeup brief ──────────────────────────────────────────
if [[ "$IS_HUB" == "true" && -f "$PROJECT_DIR/tools/octo_brief.py" ]]; then
    if python3 "$PROJECT_DIR/tools/octo_brief.py" 2>/dev/null; then
        _WAI_BRIEF_STATUS="ready"
    else
        _WAI_BRIEF_STATUS="failed (live scan)"
    fi
elif [[ -f "$PROJECT_DIR/WAI-Harness/spoke/managed/tools/generate_wakeup_brief.py" ]]; then
    # v4-aware: the spoke's OWN distributed generator (resolves via wai_paths ->
    # WAI-Harness/spoke/local). Preferred — basher's legacy tools/ copy is v3-pathed
    # and skips on v4 spokes (looks for the absent WAI-Spoke/WAI-State.json).
    if python3 "$PROJECT_DIR/WAI-Harness/spoke/managed/tools/generate_wakeup_brief.py" --spoke-path "$PROJECT_DIR" 2>/dev/null; then
        _WAI_BRIEF_STATUS="ready"
    else
        _WAI_BRIEF_STATUS="failed (live scan)"
    fi
elif [[ -f "$PROJECT_DIR/tools/generate_wakeup_brief.py" ]]; then
    if python3 "$PROJECT_DIR/tools/generate_wakeup_brief.py" 2>/dev/null; then
        _WAI_BRIEF_STATUS="ready"
    else
        _WAI_BRIEF_STATUS="failed (live scan)"
    fi
elif [[ -f "$SCRIPT_DIR/generate_wakeup_brief.py" ]]; then
    # SIBLING: this launcher lives in managed/tools/, so canon's brief generator sits
    # right next to it. Look here before anything else — this is the copy that shipped
    # with this launcher, so it is version-matched to it by construction.
    if python3 "$SCRIPT_DIR/generate_wakeup_brief.py" --spoke-path "$PROJECT_DIR" 2>/dev/null; then
        _WAI_BRIEF_STATUS="ready"
    else
        _WAI_BRIEF_STATUS="failed (live scan)"
    fi
elif [[ -f "$CANON_ROOT/WAI-Harness/spoke/managed/tools/generate_wakeup_brief.py" ]]; then
    # CANON_ROOT's managed canon — reached when the launcher was deployed somewhere
    # other than managed/tools (e.g. a repo-root install, where CANON_ROOT==SCRIPT_DIR
    # and this arm is exactly the old behavior).
    if python3 "$CANON_ROOT/WAI-Harness/spoke/managed/tools/generate_wakeup_brief.py" --spoke-path "$PROJECT_DIR" 2>/dev/null; then
        _WAI_BRIEF_STATUS="ready"
    else
        _WAI_BRIEF_STATUS="failed (live scan)"
    fi
elif [[ -f "$CANON_ROOT/tools/generate_wakeup_brief.py" ]]; then
    # legacy v3-pathed last resort (a stale tools/ — kept only for pure-v3 spokes)
    if python3 "$CANON_ROOT/tools/generate_wakeup_brief.py" --spoke-path "$PROJECT_DIR" 2>/dev/null; then
        _WAI_BRIEF_STATUS="ready"
    else
        _WAI_BRIEF_STATUS="failed (live scan)"
    fi
else
    _WAI_BRIEF_STATUS="failed (live scan)"
fi


# ── 1a2. Capability runner (spoke entry) ─────────────────────────────────────
# Runs hub-base + spoke-local capabilities flagged trigger=on-entry/auto=true
# (e.g. track-prompt-sync). Self-documenting registry: hub/WAI-Hub/reference/
# capabilities-base.json + WAI-Spoke/capabilities.json. Always exits 0; skipped
# on -c (continue) to avoid resume noise.
if [[ "$IS_SPOKE" == "true" && "$_CONTINUE_MODE" == "false" ]]; then
    _CAP_HUB=$(jq -r '.wheel.hub_path // ""' "$WAI_LOCAL/WAI-State.json" 2>/dev/null)
    _CAP_RUNNER="$_CAP_HUB/tools/capability_runner.py"
    if [[ -n "$_CAP_HUB" && -f "$_CAP_RUNNER" ]]; then
        while IFS= read -r _cap_line; do
            [[ -n "$_cap_line" ]] && _wai_ok "capability" "$_cap_line"
        done < <(python3 "$_CAP_RUNNER" --spoke "$PROJECT_DIR" --hub "$_CAP_HUB" --trigger on-entry 2>/dev/null)
    fi
    unset _CAP_HUB _CAP_RUNNER _cap_line
fi

# ── 1c. Ozi pre-scan (spoke entry, non-continue) ────────────────────────────
# Runs Phase 0 + 0.5 (groom) + 1.5 only — populates needs_attention and ready
# counts in the activity-log before the menu reads metrics. Skipped in continue
# mode (-c) to avoid resume noise. Never blocks launch on failure.
# OPERATOR KILL SWITCH — advisors/disabled.json is the single, discoverable place
# to pause an advisor without editing code. Checked here so a disabled autopilot
# costs nothing at launch; remove the entry to re-enable. Fails OPEN (runs the
# pre-scan) if the file is missing or unparseable — a broken kill switch must not
# silently disable the harness.
_PRESCAN_DISABLED=$(python3 -c "
import json
try:
    d = json.load(open('$PROJECT_DIR/WAI-Harness/spoke/advisors/disabled.json'))
    print('yes' if 'autopilot' in d.get('disabled', {}) else 'no')
except Exception:
    print('no')
" 2>/dev/null || echo "no")

if [[ "$_PRESCAN_DISABLED" == "yes" ]]; then
    printf '  Ozi pre-scan: DISABLED via advisors/disabled.json (remove the autopilot entry to re-enable)\n'
elif [[ "$IS_SPOKE" == "true" && "$_CONTINUE_MODE" == "false" ]]; then
    # Resolve Ozi HARNESS-FIRST. The legacy tree read from WAI-State
    # `wheelwright.framework_path` is deprecated and is a fallback ONLY — it
    # self-retires the moment canon grows `--pre-scan`, with no edit here.
    #
    # SAFETY — the feature-detect below is load-bearing, do not "simplify" it:
    # canon's ozi_autopilot.py (WAI-Harness/spoke/managed) currently has NO
    # --pre-scan flag. Invoking it without the flag does NOT degrade to a
    # cheap scan — it runs the FULL autopilot, which dispatches lugs to
    # `claude` and commits. Running that from an interactive launcher would be
    # far worse than the stall this block was written to fix. So: only ever run
    # a copy that actually advertises --pre-scan, and skip entirely otherwise.
    # RETIRED 2026-07-26 — the `wheelwright.framework_path` fallback candidate is GONE.
    # It was written as fallback-only, self-retiring "the moment canon grows --pre-scan".
    # The opposite happened: canon never grew the flag, the deprecated repo's copy DID
    # have it, and the deprecated repo is still on disk — so the fallback stopped being a
    # fallback and became the ONLY match. Measured live: every wai-enter pre-scan was
    # running /wheelwright/framework/tools/ozi_autopilot.py, dead code, against the
    # operator's current project, on his primary entry path.
    #
    # A self-retiring guard that never fires is a permanent redirect. Removing the
    # candidate restores the intended behaviour stated above: if no copy advertises
    # --pre-scan, skip the pre-scan entirely.
    _PRESCAN_OZI=""
    for _ozi_cand in \
        "$PROJECT_DIR/WAI-Harness/spoke/managed/tools/ozi_autopilot.py" \
        "$SCRIPT_DIR/ozi_autopilot.py" \
        "$CANON_ROOT/WAI-Harness/spoke/managed/tools/ozi_autopilot.py"; do
        [[ -n "$_ozi_cand" && -f "$_ozi_cand" ]] || continue
        grep -q -- '"--pre-scan"' "$_ozi_cand" 2>/dev/null || continue
        _PRESCAN_OZI="$_ozi_cand"
        break
    done
    unset _ozi_cand
    if [[ -n "$_PRESCAN_OZI" ]]; then
        # Time-bound the pre-scan. It is a count-refresh convenience, never a
        # reason to block entry. Ozi's Phase 0 shells to `npx gitnexus analyze`
        # whenever the index SHA != HEAD (measured 15-53s here, and bounded only
        # by ITS own 120s timeout), so an unbounded call stalls the launcher on
        # the first launch after any commit.
        # Progress is streamed line-buffered and the `[ozi]` prefix is passed
        # through as well as `[autopilot]` — the slow reindex reports under
        # `[ozi] gitnexus:`, so an `[autopilot]`-only filter renders the stall
        # completely silent, which is what made this look like a hang.
        _PRESCAN_T="${BASHER_PRESCAN_TIMEOUT:-15}"
        _wai_info "Ozi" "pre-scan: running (<=${_PRESCAN_T}s, Ctrl-C skips)"
        timeout "$_PRESCAN_T" python3 "$_PRESCAN_OZI" --spoke-path "$PROJECT_DIR" --pre-scan 2>&1 \
            | grep --line-buffered -E '^\[(autopilot|ozi)\]' \
            | sed -u 's/^/  [prescan] /'
        _PRESCAN_RC="${PIPESTATUS[0]}"
        case "$_PRESCAN_RC" in
            0)   _wai_info "Ozi" "pre-scan: done" ;;
            124) _wai_warn "Ozi" "pre-scan: timed out at ${_PRESCAN_T}s — counts may be stale (raise BASHER_PRESCAN_TIMEOUT)" ;;
            130) _wai_info "Ozi" "pre-scan: skipped (interrupted)" ;;
            *)   _wai_warn "Ozi" "pre-scan: failed (rc=${_PRESCAN_RC}) — counts may be stale" ;;
        esac
        # Re-generate wakeup brief so menu counts reflect groomed state
        if [[ -f "$PROJECT_DIR/WAI-Harness/spoke/managed/tools/generate_wakeup_brief.py" ]]; then
            timeout "${BASHER_BRIEF_TIMEOUT:-20}" python3 "$PROJECT_DIR/WAI-Harness/spoke/managed/tools/generate_wakeup_brief.py" \
                --spoke-path "$PROJECT_DIR" >/dev/null 2>&1 || true
        elif [[ -f "$SCRIPT_DIR/generate_wakeup_brief.py" ]]; then
            timeout "${BASHER_BRIEF_TIMEOUT:-20}" python3 "$SCRIPT_DIR/generate_wakeup_brief.py" \
                --spoke-path "$PROJECT_DIR" >/dev/null 2>&1 || true
        elif [[ -f "$CANON_ROOT/WAI-Harness/spoke/managed/tools/generate_wakeup_brief.py" ]]; then
            timeout "${BASHER_BRIEF_TIMEOUT:-20}" python3 "$CANON_ROOT/WAI-Harness/spoke/managed/tools/generate_wakeup_brief.py" \
                --spoke-path "$PROJECT_DIR" >/dev/null 2>&1 || true
        fi
        unset _PRESCAN_T _PRESCAN_RC
    else
        # Reached when no reachable ozi advertises --pre-scan. Deliberately a
        # silent-but-visible skip: counts stay as the brief left them, and the
        # launcher enters immediately. This is the correct degrade — see the
        # SAFETY note above for why we never fall back to a flagless invocation.
        _wai_info "Ozi" "pre-scan: skipped (no ozi with --pre-scan support)"
    fi
    unset _PRESCAN_OZI
fi

if [[ "$IS_SPOKE" == "true" ]]; then
    _INTENT_FILE="$WAI_LOCAL/runtime/session-intent.json"
    _BRIEF_FILE="$WAI_LOCAL/wakeup-brief.json"
    _STATE_FILE="$WAI_LOCAL/WAI-State.json"
    _IS_FRAMEWORK=$(jq -r '(.wheel.qualifiers.project_types // []) | contains(["framework"])' "$_STATE_FILE" 2>/dev/null || echo "false")

    _SPOKES_FILE="/tmp/wai-enter-spokes-$$.json"
    _HAS_METRICS=false
    if [[ -f "$PROJECT_DIR/tools/wai_enter_metrics.py" ]]; then
        _METRICS=$(python3 "$PROJECT_DIR/tools/wai_enter_metrics.py" \
            --spoke-path "$PROJECT_DIR" --spokes-out "$_SPOKES_FILE" 2>/dev/null)
        _HAS_METRICS=true
    else
        _METRICS=""
    fi
    _TEACH=$(echo "$_METRICS" | grep '^teach=' | cut -d= -f2)
    _SESSION_HINT=$(echo "$_METRICS" | grep '^session=' | cut -d= -f2)
    _SP_STATUS=$(echo "$_METRICS" | grep '^sp_status=' | cut -d= -f2)
    _SP_LUG=$(echo "$_METRICS" | grep '^sp_lug=' | cut -d= -f2)
    _SP_NOTE=$(echo "$_METRICS" | grep '^sp_note=' | cut -d= -f2)
    _BLOCKED=$(echo "$_METRICS" | grep '^blocked=' | cut -d= -f2)
    _TEACH_MANUAL=$(echo "$_METRICS" | grep '^manual_teach=' | cut -d= -f2)
    _SPOKES=$(echo "$_METRICS" | grep '^spokes_count=' | cut -d= -f2)
    _INC_UNGROOMED=$(echo "$_METRICS" | grep '^incoming_ungroomed=' | cut -d= -f2)
    _INC_HAIKU=$(echo "$_METRICS" | grep '^incoming_haiku_groomed=' | cut -d= -f2)
    _INC_SONNET=$(echo "$_METRICS" | grep '^incoming_sonnet_groomed=' | cut -d= -f2)
    _ATTN_OZI=$(echo "$_METRICS" | grep '^attn_from_ozi=' | cut -d= -f2)
    _STALLED=$(echo "$_METRICS" | grep '^stalled_in_progress=' | cut -d= -f2)
    _INTERRUPTED=$(echo "$_METRICS" | grep '^interrupted_count=' | cut -d= -f2)
    _SIGNALS=$(echo "$_METRICS" | grep '^signals=' | cut -d= -f2)
    _REFINE=$(echo "$_METRICS" | grep '^refine=' | cut -d= -f2)
    : "${_TEACH:=0}" "${_SESSION_HINT:=unknown}" "${_SP_STATUS:=}" "${_SP_LUG:=}" \
      "${_SP_NOTE:=}" "${_SP_COUNT:=0}" "${_SP_SELECTED_FILE:=}" \
      "${_BLOCKED:=0}" "${_TEACH_MANUAL:=0}" "${_SPOKES:=0}" \
      "${_INC_UNGROOMED:=0}" "${_INC_HAIKU:=0}" "${_INC_SONNET:=0}" \
      "${_ATTN_OZI:=0}" "${_STALLED:=0}" "${_INTERRUPTED:=0}" \
      "${_SIGNALS:=0}" "${_REFINE:=0}"
    _SP_IDS=(); _SP_NOTES=(); _SP_FILES=(); _SP_WORKS=()

    # ── Basher version gate ──────────────────────────────────────────────────
    # Compare last-recorded basher version against current.
    # If they differ, flag doctor as stale so we surface the drift warning.
    _DOCTOR_STALE=false
    _DOCTOR_CUR_VER="unknown"
    _DOCTOR_LAST_VER=""
    # CANON_ROOT, not SCRIPT_DIR: this reads the WAI-State of the tree the LAUNCHER
    # lives in (its harness version) to compare against the last doctor run. That
    # tree is the spoke root — under the old repo-root install SCRIPT_DIR *was* that
    # root, but from managed/tools/ it is the tools dir, which has no WAI-State.json,
    # so the resolver would hand back <tools>/WAI-Spoke/WAI-State.json: a path that
    # never exists -> _DOCTOR_CUR_VER stays "unknown" -> the version gate silently
    # never fires. No error, no warning, gate just gone. This is constraint 2 exactly.
    _SCRIPT_STATE="$(basher_wai_state "$CANON_ROOT")"
    if [[ -f "$_SCRIPT_STATE" ]]; then
        _DOCTOR_CUR_VER=$(jq -r '.wheel.version // "unknown"' "$_SCRIPT_STATE" 2>/dev/null || echo "unknown")
    fi
    _DOCTOR_RUNTIME="$WAI_LOCAL/runtime/basher-doctor-last-run.json"
    if [[ -f "$_DOCTOR_RUNTIME" ]]; then
        _DOCTOR_LAST_VER=$(jq -r '.basher_version // ""' "$_DOCTOR_RUNTIME" 2>/dev/null || echo "")
    fi
    if [[ "$_DOCTOR_CUR_VER" != "unknown" && ( -z "$_DOCTOR_LAST_VER" || "$_DOCTOR_LAST_VER" != "$_DOCTOR_CUR_VER" ) ]]; then
        _DOCTOR_STALE=true
    fi

    # Auto-run doctor when stale and not run in the last 8 hours (foreground, before menu).
    _DOCTOR_BG=false  # true = ran auto this session; false = stale but ran recently
    if [[ "$_DOCTOR_STALE" == "true" ]] && command -v basher >/dev/null 2>&1; then
        _DOCTOR_LAST_RUN_AT=$(jq -r '.run_at // ""' "$_DOCTOR_RUNTIME" 2>/dev/null || echo "")
        _doctor_should_run=false
        if [[ -z "$_DOCTOR_LAST_RUN_AT" ]]; then
            _doctor_should_run=true
        else
            _DOCTOR_STALE_SECS=$(python3 -c "
import datetime, sys
try:
    then = datetime.datetime.fromisoformat('${_DOCTOR_LAST_RUN_AT}'.replace('Z','+00:00'))
    now  = datetime.datetime.now(datetime.timezone.utc)
    print(int((now - then).total_seconds()))
except Exception:
    print(99999)
" 2>/dev/null || echo "99999")
            (( ${_DOCTOR_STALE_SECS:-99999} >= 28800 )) && _doctor_should_run=true
        fi
        if [[ "$_doctor_should_run" == "true" ]]; then
            mkdir -p "$HOME/.claude/logs"
            _dr_log="$HOME/.claude/logs/doctor-auto-$(date +%Y%m%d-%H%M%S).log"
            printf "  ${_W_DIM}·  Doctor: auto-running (v%s → v%s)...${_W_RST}\n" "${_DOCTOR_LAST_VER:-never}" "$_DOCTOR_CUR_VER"
            (cd "$PROJECT_DIR" && basher doctor) > "$_dr_log" 2>&1 || true
            _DOCTOR_LAST_VER=$(jq -r '.basher_version // ""' "$_DOCTOR_RUNTIME" 2>/dev/null || echo "")
            if [[ "$_DOCTOR_LAST_VER" == "$_DOCTOR_CUR_VER" ]]; then
                _DOCTOR_STALE=false
                printf "  ${_W_DIM}·  Doctor: updated to v%s${_W_RST}\n" "$_DOCTOR_CUR_VER"
            else
                printf "  ${_W_DIM}·  Doctor: ran — still v%s (log: %s)${_W_RST}\n" "${_DOCTOR_LAST_VER:-?}" "$_dr_log"
            fi
            _DOCTOR_BG=true
            unset _dr_log
        fi
        unset _doctor_should_run
    fi

    # ── Brief fallback: fill counts when metrics script absent ────────────────
    # Runs AFTER defaults so it overwrites zeros with real values.
    # Savepoint and lug counts are read separately to avoid read splitting on
    # spaces inside the savepoint note.
    if [[ "$_HAS_METRICS" == "false" ]]; then
        # Savepoints + interrupted sessions are scanned ALWAYS by the resume-scan
        # tool below (independent of metrics), so the fallback only fills lug counts.

        # Lug counts: scan bytype/*/open/, skip signals/epics/specs (non-executable)
        read -r _INC_HAIKU _INC_SONNET _INC_UNGROOMED _BLOCKED < <(python3 -c "
import json, glob
_SKIP_TYPES = {'signal', 'epic', 'spec', 'phone-home'}
haiku = sonnet = ungroomed = blocked_ct = 0
try:
    for f in glob.glob('$WAI_LOCAL/lugs/bytype/*/open/*.json'):
        try:
            d = json.load(open(f))
            ltype = (d.get('type') or d.get('ty') or '').lower()
            if ltype in _SKIP_TYPES:
                continue
            model = (d.get('model_fit') or d.get('model', '')).lower()
            if 'haiku' in model:
                haiku += 1
            elif model:
                sonnet += 1
            else:
                ungroomed += 1
        except Exception:
            pass
    for _ in glob.glob('$WAI_LOCAL/lugs/bytype/*/blocked/*.json'):
        blocked_ct += 1
except Exception:
    pass
print(haiku, sonnet, ungroomed, blocked_ct)
" 2>/dev/null)
        : "${_INC_HAIKU:=0}" "${_INC_SONNET:=0}" "${_INC_UNGROOMED:=0}" "${_BLOCKED:=0}"
    fi

    # ── Resume surfaces: savepoints + interrupted sessions (ALWAYS) ───────────
    # Built by the testable scanner (tools/wai_enter_resume_scan.py), not inline,
    # so the menu shows clean one-line titles + the initiative silo_label + a
    # recommended action per interrupted session (tests/test_wai_enter_resume_scan.py).
    # It unifies BOTH savepoint sources during v3/v4 coexistence:
    #   - initiatives/savepoints/<iid>/*.json (v4 on-disk store; the file IS the
    #     savepoint — replaces the old flat savepoints/ scan)
    #   - ._savepoint embedded in WAI-State.json (legacy; v4 local + v3 candidate)
    # _SP_EMBEDDED[i] tells the resume prompt which shape to claim. The scanner is
    # promoted INTO canon beside this launcher, so it ships with it and every spoke
    # gets a version-matched copy.
    _SP_COUNT=0; _SP_IDS=(); _SP_TITLES=(); _SP_SILOS=(); _SP_NOTES=(); _SP_FILES=(); _SP_EMBEDDED=(); _SP_INITS=()
    _INIT_COUNT=0; _INIT_IDS=(); _INIT_LABELS=(); _INIT_STATES=(); _INIT_FOCUS=(); _INIT_SP_IDX=(); _SP_UNGROUPED_IDX=""
    _INT_COUNT=0; _INT_IDS=(); _INT_TITLES=(); _INT_ACTIONS=(); _INT_FILES=()
    # Sibling first (promoted to managed/tools/ alongside this launcher), then
    # CANON_ROOT's managed canon, then the legacy tools/ path for old installs.
    _RESUME_SCAN="$SCRIPT_DIR/wai_enter_resume_scan.py"
    [[ -f "$_RESUME_SCAN" ]] || _RESUME_SCAN="$CANON_ROOT/WAI-Harness/spoke/managed/tools/wai_enter_resume_scan.py"
    [[ -f "$_RESUME_SCAN" ]] || _RESUME_SCAN="$CANON_ROOT/tools/wai_enter_resume_scan.py"
    if [[ -f "$_RESUME_SCAN" ]]; then
        eval "$(python3 "$_RESUME_SCAN" --wai-local "$WAI_LOCAL" \
            --state "$WAI_LOCAL/WAI-State.json" \
            --state "$PROJECT_DIR/WAI-Spoke/WAI-State.json" 2>/dev/null)"
    fi

    # ── Continuation menu (framework wakeup-brief) ───────────────────────────
    # Reads open sessions with outstanding goals + claimable initiatives from the
    # framework spoke's wakeup-brief.json. Falls back silently when unavailable.
    _CM_SES_COUNT=0; _CM_SES_IDS=(); _CM_SES_LABELS=(); _CM_SES_REWARMS=(); _CM_SES_OZI=()
    _CM_INI_COUNT=0; _CM_INI_IDS=(); _CM_INI_LABELS=(); _CM_INI_CLAIMED=(); _CM_INI_CLAIMERS=()
    _CM_SEL_SESSION=""; _CM_SEL_REWARM=""; _CM_SEL_INITIATIVE=""; _CM_SEL_INI_LABEL=""
    _CM_CLAIM_SESSION=""; _CM_WORKTREE_PATH=""
    _FRAMEWORK_ROOT="$(basher_wai_master_root "$PROJECT_DIR")"
    _CM_BRIEF="$_FRAMEWORK_ROOT/WAI-Harness/spoke/local/wakeup-brief.json"
    [[ -f "$_CM_BRIEF" ]] || _CM_BRIEF="$_FRAMEWORK_ROOT/WAI-Spoke/wakeup-brief.json"
    _CM_CLAIMS="$_FRAMEWORK_ROOT/WAI-Spoke/runtime/initiative-claims.json"
    if [[ -f "$_CM_BRIEF" ]]; then
        _cm_out=$(python3 - "$_CM_BRIEF" "$_CM_CLAIMS" <<'PYEOF' 2>/dev/null
import json, sys, shlex
from pathlib import Path
try:
    d = json.load(open(sys.argv[1]))
    cm = d.get("continuation_menu", {})
    claims = {}
    claims_path = Path(sys.argv[2])
    if claims_path.exists():
        try:
            from datetime import datetime, timedelta, timezone
            raw = json.loads(claims_path.read_text() or "{}")
            now = datetime.now(timezone.utc)
            for iid, rec in raw.items():
                try:
                    held_at = datetime.fromisoformat(rec["held_at"].replace("Z", "+00:00"))
                    if held_at + timedelta(hours=int(rec.get("lease_ttl_hours", 8))) > now:
                        claims[iid] = rec
                except Exception:
                    pass
        except Exception:
            pass
    sessions = cm.get("open_sessions", [])
    print(f"_CM_SES_COUNT={len(sessions[:5])}")
    for s in sessions[:5]:
        sid = s.get("session_id", "")
        init_id = s.get("initiative_id", "") or "no initiative"
        ozi = "1" if s.get("ozi_eligible") else "0"
        rewarm = s.get("rewarm_hint", "")
        label = f"{sid} · {init_id}"
        print(f"_CM_SES_IDS+=({shlex.quote(sid)})")
        print(f"_CM_SES_LABELS+=({shlex.quote(label)})")
        print(f"_CM_SES_REWARMS+=({shlex.quote(rewarm)})")
        print(f"_CM_SES_OZI+=({shlex.quote(ozi)})")
    initiatives = cm.get("initiatives", [])
    print(f"_CM_INI_COUNT={len(initiatives[:6])}")
    for init in initiatives[:6]:
        iid = init.get("id", "")
        label = init.get("label", iid)
        claimed_by = init.get("claimed_by", "") or ""
        if not claimed_by and iid in claims:
            claimed_by = claims[iid].get("held_by", "")
        print(f"_CM_INI_IDS+=({shlex.quote(iid)})")
        print(f"_CM_INI_LABELS+=({shlex.quote(label)})")
        print(f"_CM_INI_CLAIMED+=({shlex.quote('true' if claimed_by else 'false')})")
        print(f"_CM_INI_CLAIMERS+=({shlex.quote(claimed_by)})")
except Exception:
    pass
PYEOF
        )
        eval "$_cm_out" 2>/dev/null || true
        unset _cm_out
    fi
    unset _CM_BRIEF _CM_CLAIMS _FRAMEWORK_ROOT

    # ── Teachings: removed ────────────────────────────────────────────────────
    # The teachings concept is deprecated (see feature-wcl-launcher-revision-v1).
    # Counters are neutralized so no teaching gate/menu/intent renders. Full
    # subsystem removal is tracked in feature-teachings-subsystem-removal-v1.
    _TEACH=0
    _TEACH_MANUAL=0
    _PENDING_COUNT=0
    _PENDING_TEACHINGS=""
    _TEACHING_HUB_PATH=""

    # ── Aggregates ───────────────────────────────────────────────────────────
    # Interrupted sessions are their own actionable [i] section now, NOT folded
    # into Needs Action — so they don't double-count here.
    _ATTN=$(( _ATTN_OZI + _STALLED + _BLOCKED ))
    _WORK=$(( _INC_UNGROOMED + _INC_HAIKU + _INC_SONNET ))

    # ── Backlog-lock detector ─────────────────────────────────────────────────
    # LOCKED = work present AND no in_progress focus AND no priority-tagged ready lug.
    read -r _IP_COUNT _HAS_PRIORITY_READY < <(python3 -c "
import json, glob
lugs_base = '$WAI_LOCAL/lugs/bytype'
ip = 0; has_prio = 0
try:
    for f in glob.glob(lugs_base + '/*/in_progress/*.json'):
        ip += 1
    for f in glob.glob(lugs_base + '/*/open/*.json'):
        try:
            d = json.load(open(f))
            if d.get('priority') or d.get('initiative') or d.get('initiative_id'):
                has_prio = 1; break
        except Exception:
            pass
except Exception:
    pass
print(ip, has_prio)
" 2>/dev/null || echo "0 0")
    : "${_IP_COUNT:=0}" "${_HAS_PRIORITY_READY:=0}"
    _LOCKED=false
    if (( _WORK > 0 )) && (( ${_IP_COUNT:-0} == 0 )) && [[ "${_HAS_PRIORITY_READY:-0}" == "0" ]]; then
        _LOCKED=true
    fi

    if [[ "$_SEED_MODE" == "true" ]]; then
        # Seed mode: the opening prompt is supplied externally (WAI_SEED_PROMPT);
        # no priority auto-select, no menu. _OPEN_PROMPT is set just before launch.
        _INTENT="raw"; _INTENT_LABEL="Seed prompt (from launcher)"
    elif [[ "$_CONTINUE_MODE" == "true" ]]; then
        # -r/--raw/--resume: force raw regardless of what's pending (no priority
        # auto-select). The operator already picked the target — in the picker, or
        # on the command line — so re-deriving an intent here would contradict them.
        if [[ "$_RAW_MODE" == "true" ]]; then
            _INTENT="raw"; _INTENT_LABEL="Raw — no opening prompt"
        # -c flag: auto-select highest-priority intent
        elif (( _SP_COUNT > 0 )); then
            _SP_SELECTED_FILE="${_SP_FILES[0]}"; _SP_SELECTED_EMBEDDED="${_SP_EMBEDDED[0]}"
            _SP_LUG="${_SP_IDS[0]}"; _SP_NOTE="${_SP_NOTES[0]}"
            _INTENT="savepoint"   ; _INTENT_LABEL="Resume — ${_SP_TITLES[0]}"
        elif (( _SIGNALS > 0 )); then
            _INTENT="signals"     ; _INTENT_LABEL="Messages to the User (${_SIGNALS})"
        elif (( _SPOKES > 0 )); then
            _INTENT="spokes"      ; _INTENT_LABEL="Messages to the Spoke (${_SPOKES})"
        elif (( _ATTN > 0 )); then
            _INTENT="attention"   ; _INTENT_LABEL="Needs Your Action (${_ATTN})"
        elif (( ${_INT_COUNT:-0} > 0 )); then
            _INTENT="interrupted" ; _INTENT_LABEL="Interrupted (${_INT_COUNT})"
        else
            _INTENT="raw"         ; _INTENT_LABEL="Raw — no opening prompt"
        fi
        _INTENT_CHOICE=""
        printf "  ${_W_DIM}→ auto-selected: %s${_W_RST}\n" "$_INTENT_LABEL"
    else
        _READY_ACTION=""

        # ── Header ───────────────────────────────────────────────────────────
        printf "\n"
        printf "  ${_W_BOLD}WAI · Session Start${_W_RST}\n"
        printf "  ${_W_DIM}────────────────────────────────────────────${_W_RST}\n"
        if [[ "$_WAI_BRIEF_STATUS" == "ready" ]]; then
            _wai_ok  "Brief" "ready"
        else
            _wai_warn "Brief" "$_WAI_BRIEF_STATUS"
        fi

        # ── Net-net (last session bottom line) ────────────────────────────────
        # Shows the bottom_line from the last time an agent wrote a net-net in
        # this spoke. Gives instant context on what the previous session achieved.
        _NN_FILE="$WAI_LOCAL/runtime/net-net-latest.json"
        if [[ -f "$_NN_FILE" ]]; then
            _NN_BL=$(jq -r '.bottom_line // empty' "$_NN_FILE" 2>/dev/null | head -1)
            [[ -n "$_NN_BL" ]] && _wai_info "Last" "$_NN_BL"
            unset _NN_BL
        fi
        unset _NN_FILE

        # ── Spoke health: version, git, session, inbox ────────────────────────
        {
            _SH_VER=$(jq -r '.wheel.version // "?"' "$_STATE_FILE" 2>/dev/null || echo "?")
            _SH_HEAD=$(jq -r '.wheel.at_head // "unknown"' "$_STATE_FILE" 2>/dev/null || echo "unknown")
            if [[ "$_SH_HEAD" == "true" ]]; then
                _wai_ok  "version" "v${_SH_VER} · at head"
            else
                _wai_warn "version" "v${_SH_VER} · BEHIND hub"
            fi

            # (git status intentionally not shown — worktrees + closeout own the
            #  working tree; an uncommitted count here is noise, not an action.)

            _SH_SESS=$(jq -r '._session_status.status // "unknown"' "$_STATE_FILE" 2>/dev/null || echo "unknown")
            if [[ "$_SH_SESS" == "clean" ]]; then
                _wai_ok  "session" "clean"
            else
                _wai_warn "session" "INTERRUPTED — closeout recommended"
            fi

            _SH_INBOX=$(find "$WAI_LOCAL/lugs/inbox" -name "*.json" \
                -not -path "*/processed/*" 2>/dev/null | wc -l | tr -d ' ')
            (( ${_SH_INBOX:-0} > 0 )) && _wai_warn "inbox" "${_SH_INBOX} lug(s) need triage"

            _SESSION_STATE="${_SH_SESS:-unknown}"  # preserve for menu before unset
            unset _SH_VER _SH_HEAD _SH_GIT _SH_SESS
            # _SH_INBOX preserved for "Messages to the Spoke" sub-note
        }
        # ── End spoke health checks ───────────────────────────────────────────

        # ── Spoke health: doctor stale ────────────────────────────────────────
        if [[ "$_DOCTOR_STALE" == "true" ]]; then
            printf "  ${_W_YLW}────────────────────────────────────────────${_W_RST}\n"
            _wai_warn "basher" "doctor drift (v${_DOCTOR_LAST_VER:-never} → v${_DOCTOR_CUR_VER}) — ran recently, still stale"
            printf "  ${_W_YLW}────────────────────────────────────────────${_W_RST}\n"
        fi

        # ── Session-start sync trigger (daemonless TTL schedule) ──────────────
        # Self-heals config drift inline (fast) and, when >7d stale, refreshes apps
        # in the background. Keeps latest-greatest apps+config current without a cron.
        if command -v basher >/dev/null 2>&1; then
            basher tools auto 2>/dev/null || true
        fi
        printf "\n"

        # ── Priority gate ─────────────────────────────────────────────────────
        # Operator-mailbox signals (Messages to the User) and cross-spoke work lugs
        # (Messages to the Spoke) gate other work — top priority below savepoint
        # resume. Signals outrank work lugs (they need the operator). User sees the
        # priority item until done (or override). Savepoint resume stays Enter-default.
        _HAS_GATE=false
        if (( _SIGNALS > 0 || _SPOKES > 0 )); then
            _HAS_GATE=true
        fi
        while true; do  # back-support loop: re-enters when [b] is pressed in a submenu
        _INTENT=""
        _READY_ACTION=""

        # ── Menu ─────────────────────────────────────────────────────────────
        # Enter (↵) — resume savepoint when pending; else highest-priority default
        # Space / [r] — Raw (new session, no opening prompt)
        printf "  ${_W_DIM}How do you want to start?${_W_RST}\n\n"

        # ── Continuation surface: Open Sessions ──────────────────────────────
        # Sessions with outstanding goals sourced from framework wakeup-brief.json.
        # [r] opens a sub-menu; entries labeled [r1], [r2]... with rewarm context.
        if (( _CM_SES_COUNT > 0 )); then
            printf "  ${_W_DIM}┌─ Open Sessions (%d with outstanding goals) ──────────────────${_W_RST}\n" "$_CM_SES_COUNT"
            for (( _cms_i=0; _cms_i<_CM_SES_COUNT; _cms_i++ )); do
                _ozi_tag=""; [[ "${_CM_SES_OZI[$_cms_i]:-0}" == "1" ]] && _ozi_tag="  ${_W_DIM}Ozi-eligible${_W_RST}"
                printf "  ${_W_BOLD}[r%d]${_W_RST} %s%s\n" \
                    "$(( _cms_i+1 ))" "${_CM_SES_LABELS[$_cms_i]}" "$_ozi_tag"
            done
            printf "\n"
            unset _cms_i _ozi_tag
        fi

        # ── Continuation surface: Start Initiative ───────────────────────────
        # Claimable initiatives from framework wakeup-brief.json.
        # [n] opens a sub-menu; entries labeled [i1], [i2]...
        if (( _CM_INI_COUNT > 0 )); then
            printf "  ${_W_DIM}├─ Start Initiative ───────────────────────────────────────────${_W_RST}\n"
            for (( _cmi_i=0; _cmi_i<_CM_INI_COUNT; _cmi_i++ )); do
                if [[ "${_CM_INI_CLAIMED[$_cmi_i]:-false}" == "true" ]]; then
                    printf "  ${_W_DIM}[i%d] ⬤ %s  ← CLAIMED by %s${_W_RST}\n" \
                        "$(( _cmi_i+1 ))" "${_CM_INI_LABELS[$_cmi_i]}" "${_CM_INI_CLAIMERS[$_cmi_i]}"
                else
                    printf "  ${_W_BOLD}[i%d]${_W_RST}   %s\n" \
                        "$(( _cmi_i+1 ))" "${_CM_INI_LABELS[$_cmi_i]}"
                fi
            done
            printf "\n"
            unset _cmi_i
        fi

        # Savepoint (always shown — available regardless of gate). Each line is the
        # savepoint's IDENTITY (clean title + initiative silo + short note), never
        # its raw work_done contents. silo_label (when the harness has stamped it)
        # shows the initiative the savepoint fits under; blank for legacy savepoints.
        _sp_silo_tag() { [[ -n "${1:-}" ]] && printf "  ${_W_DIM}[%s]${_W_RST}" "$1"; }

        # ── Initiative tree (v4): show off live initiatives + their child savepoints.
        # Flat one-screen tree — DIGIT selects an initiative (status-check prompt),
        # LETTER selects a savepoint (resume). Savepoint letters skip every reserved
        # top-level key (u m f a i h b r x q). Built fresh each render; the letter→sp
        # map drives selection in the read loop. Only active when initiatives exist;
        # otherwise the legacy savepoint block (else branch) renders unchanged.
        declare -A _SP_LETTER_TO_IDX=()
        _SP_LETTERS="cdegjklnopstvwyz"; _li=0
        _print_child_sp() {   # $1 = savepoint index into _SP_* arrays
            local _m="$1" _ltr="${_SP_LETTERS:$_li:1}"
            # The letter pool is 16 wide; the savepoint count is not bounded by it.
            # Past the end, ${_SP_LETTERS:_li:1} is EMPTY, and `_SP_LETTER_TO_IDX[""]=`
            # is a hard 'bad array subscript' error (observed 2026-07-23 with 17
            # savepoints) — and an empty key is an unreachable hotkey anyway. Degrade
            # instead: only consume a letter (and map it) while one is available;
            # beyond that, show the savepoint with a '·' marker so it stays VISIBLE,
            # just not directly selectable. Never assign an empty subscript.
            if [[ -n "$_ltr" ]]; then
                _li=$(( _li + 1 )); _SP_LETTER_TO_IDX[$_ltr]=$_m
            else
                _ltr="·"
            fi
            printf "          ${_W_DIM}└─${_W_RST} ${_W_BOLD}[%s]${_W_RST}  %-30s%s${_W_DIM}%s${_W_RST}\n" \
                "$_ltr" "${_SP_TITLES[$_m]}" "$(_sp_silo_tag "${_SP_SILOS[$_m]}")" "${_SP_NOTES[$_m]:+  — ${_SP_NOTES[$_m]}}"
        }
        if (( ${_INIT_COUNT:-0} > 0 )); then
            printf "  ${_W_DIM}digit = initiative status-check · letter = resume savepoint${_W_RST}\n\n"
            for (( _ii=0; _ii<_INIT_COUNT; _ii++ )); do
                _focus_mark=""; [[ "${_INIT_FOCUS[$_ii]}" == "1" ]] && _focus_mark="  ${_W_BOLD}▶${_W_RST}"
                printf "  ${_W_BOLD}[%d]${_W_RST}  ${_W_BOLD}●${_W_RST} %-28s ${_W_DIM}[%s]${_W_RST}%s\n" \
                    "$(( _ii+1 ))" "${_INIT_LABELS[$_ii]}" "${_INIT_STATES[$_ii]}" "$_focus_mark"
                if [[ -z "${_INIT_SP_IDX[$_ii]// }" ]]; then
                    printf "          ${_W_DIM}└─ (no savepoints)${_W_RST}\n"
                else
                    for _m in ${_INIT_SP_IDX[$_ii]}; do _print_child_sp "$_m"; done
                fi
            done
            if [[ -n "${_SP_UNGROUPED_IDX// }" ]]; then
                printf "  ${_W_DIM}(no initiative)${_W_RST}\n"
                for _m in $_SP_UNGROUPED_IDX; do _print_child_sp "$_m"; done
            fi
            printf "\n"
        elif (( _SP_COUNT == 1 )); then
            printf "  ${_W_BOLD}[↵]${_W_RST}  %-20s  ${_W_DIM}%s${_W_RST}%s${_W_DIM}%s${_W_RST}\n" \
                "Resume" "${_SP_TITLES[0]}" "$(_sp_silo_tag "${_SP_SILOS[0]}")" "${_SP_NOTES[0]:+  — ${_SP_NOTES[0]}}"
        elif (( _SP_COUNT > 1 )); then
            printf "  ${_W_BOLD}[↵]${_W_RST}  %-20s  ${_W_DIM}(%d)${_W_RST}\n" \
                "Savepoints" "$_SP_COUNT"
            for (( _sp_i=0; _sp_i<_SP_COUNT; _sp_i++ )); do
                printf "         ${_W_DIM}%d.${_W_RST}  %-34s%s${_W_DIM}%s${_W_RST}\n" \
                    "$(( _sp_i+1 ))" "${_SP_TITLES[$_sp_i]}" "$(_sp_silo_tag "${_SP_SILOS[$_sp_i]}")" "${_SP_NOTES[$_sp_i]:+  — ${_SP_NOTES[$_sp_i]}}"
            done
        fi

        # Interrupted sessions — presented like savepoints (openable + a recommended
        # action), NOT a passive count. [i] opens triage for them.
        if (( ${_INT_COUNT:-0} > 0 )); then
            printf "  ${_W_BOLD}[i]${_W_RST}    %-20s  ${_W_DIM}(%d — open + recommended action)${_W_RST}\n" \
                "Interrupted" "$_INT_COUNT"
            for (( _int_i=0; _int_i<_INT_COUNT; _int_i++ )); do
                printf "         ${_W_DIM}%s  — %s${_W_RST}\n" \
                    "${_INT_IDS[$_int_i]}" "${_INT_ACTIONS[$_int_i]}"
            done
        fi

        # ── Inbox preview helper — shared by gate + full modes ───────────────────
        _print_inbox_preview() {
            python3 - "$WAI_LOCAL" "$_SIGNALS" <<'PYEOF' 2>/dev/null
import json, sys
from pathlib import Path
wai_local = Path(sys.argv[1])
total = int(sys.argv[2])
sig_dir = wai_local / "lugs" / "bytype" / "signal" / "open"
files = sorted(sig_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
shown = 0
for f in files:
    if shown >= 3:
        break
    try:
        d = json.load(open(f))
        title  = (d.get("title") or f.stem)[:52]
        source = (d.get("source_spoke") or d.get("source") or "spoke")[:12]
        print(f"       \033[2m↑  {source:<14}  {title}\033[0m")
        shown += 1
    except Exception:
        pass
remaining = total - shown
if remaining > 0:
    print(f"       \033[2m+  {remaining} more\033[0m")
PYEOF
        }

        _print_spokes_preview() {
            [[ -f "$_SPOKES_FILE" ]] || return
            python3 - "$_SPOKES_FILE" <<'PYEOF' 2>/dev/null
import json, sys
from collections import defaultdict

items = json.load(open(sys.argv[1]))

# Group by sender, sort within each group by urgency desc then created_at asc (oldest first)
groups = defaultdict(list)
for item in items:
    groups[item.get("sender_name", "?")].append(item)

for sender in sorted(groups.keys()):
    group = sorted(
        groups[sender],
        key=lambda x: (-x.get("urgency", 2), x.get("created_at", ""))
    )
    for item in group[:2]:
        urgency = item.get("urgency_label", "Normal")[:8]
        title   = item.get("title", "")[:40]
        age     = item.get("created_at", "")[:10]
        print(f"       \033[2m{sender:<16}  {urgency:<8}  {title}  {age}\033[0m")
    if len(group) > 2:
        print(f"       \033[2m{sender:<16}  +{len(group)-2} more\033[0m")
PYEOF
        }

        # ── Menu: ordered by priority ─────────────────────────────────────────

        # Lane keycaps: when initiatives own the digit keys (tree above), the lanes
        # drop their digit alias and use their letter alias only — so a digit always
        # means "select initiative N", never a lane. Each lane keeps its letter.
        if (( ${_INIT_COUNT:-0} > 0 )); then
            _KC_SPOKE="m"; _KC_REFINE="f"; _KC_ATTN="a"; _KC_CLOSE="x"
        else
            _KC_SPOKE="1/m"; _KC_REFINE="2/f"; _KC_ATTN="3/a"; _KC_CLOSE="8/x"
        fi

        # Messages to the User — the operator mailbox (type:signal): items the spoke
        # raised that need YOUR decision. THIS is the user-facing channel; it is the
        # top gate when any exist. (Distinct from inter-spoke work lugs below, which
        # the spoke triages itself.)
        if (( _SIGNALS > 0 )); then
            printf "  ${_W_BOLD}[u]${_W_RST}    %-20s  ${_W_DIM}(%d — needs you)${_W_RST}\n" "Messages to the User" "$_SIGNALS"
            _print_inbox_preview
        else
            printf "  ${_W_GRN}●${_W_RST}      %-22s  ${_W_DIM}clear${_W_RST}\n" "Messages to the User"
        fi
        # Messages to the Spoke — cross-spoke incoming WORK lugs the spoke triages
        # autonomously (these are NOT messages for the operator).
        if (( _SPOKES > 0 )); then
            printf "  ${_W_BOLD}[%s]${_W_RST}  %-20s  ${_W_DIM}(%d work lug(s))${_W_RST}\n" "$_KC_SPOKE" "Messages to the Spoke" "$_SPOKES"
            _print_spokes_preview
        else
            printf "  ${_W_GRN}●${_W_RST}      %-22s  ${_W_DIM}clear${_W_RST}\n" "Messages to the Spoke"
        fi
        # Local inbox — folded under spoke messages
        (( ${_SH_INBOX:-0} > 0 )) && printf "        ${_W_DIM}%3d  local inbox item(s)${_W_RST}\n" "${_SH_INBOX}"

        # Refinement — lugs missing PEV
        if (( _REFINE > 0 )); then
            printf "  ${_W_BOLD}[%s]${_W_RST}  %-20s  ${_W_DIM}(%d non-signal lugs need PEV)${_W_RST}\n" "$_KC_REFINE" "Refinement" "$_REFINE"
        else
            printf "  ${_W_GRN}●${_W_RST}      %-22s  ${_W_DIM}ok${_W_RST}\n" "Refinement"
        fi

        # Needs Action — lugs requiring human review
        if (( _ATTN > 0 )); then
            printf "  ${_W_BOLD}[%s]${_W_RST}  %-20s  ${_W_DIM}(%d)${_W_RST}\n" "$_KC_ATTN" "Needs Action" "$_ATTN"
            (( _ATTN_OZI > 0 ))     && printf "        ${_W_DIM}%3d  Ozi decision needed${_W_RST}\n" "$_ATTN_OZI"
            (( _STALLED > 0 ))      && printf "        ${_W_DIM}%3d  stalled in-progress${_W_RST}\n" "$_STALLED"
            (( _BLOCKED > 0 ))      && printf "        ${_W_DIM}%3d  blocked lugs${_W_RST}\n" "$_BLOCKED"
        else
            printf "  ${_W_GRN}●${_W_RST}      %-22s  ${_W_DIM}ok${_W_RST}\n" "Needs Action"
        fi

        # Autopilot — autopilot-managed work (NOT user-actioned, NOT health). Shown
        # as a quiet status lane so the queue depth is visible without competing with
        # the "what needs you" items above. Autopilot drains it on its nightly run.
        if (( _WORK > 0 )); then
            printf "\n  ${_W_DIM}Autopilot (runs nightly — no action needed):${_W_RST}\n"
            _ap_parts=""
            (( _INC_UNGROOMED > 0 )) && _ap_parts+="${_INC_UNGROOMED} grooming · "
            (( _INC_HAIKU > 0 ))     && _ap_parts+="${_INC_HAIKU} haiku · "
            (( _INC_SONNET > 0 ))    && _ap_parts+="${_INC_SONNET} sonnet · "
            printf "   ${_W_DIM}·  %d queued: %s${_W_RST}\n" "$_WORK" "${_ap_parts%· }"
            printf "\n"
        fi

        # ── Backlog-lock recommendation (informational, non-blocking) ─────────
        if [[ "$_LOCKED" == "true" ]]; then
            printf "  ${_W_YLW}◇${_W_RST}  Backlog: %d ready lug(s), no focus set — run the backlog-resolution review\n" "$_WORK"
            printf "        ${_W_DIM}lets review the backlog and incoming to determine a plan to resolution,${_W_RST}\n"
            printf "        ${_W_DIM}what direction is needed or input on my part so next round of autopilot${_W_RST}\n"
            printf "        ${_W_DIM}can make progress${_W_RST}\n"
            printf "\n"
        fi

        [[ "${_SESSION_STATE:-}" == "interrupted" ]] && \
            printf "  ${_W_BOLD}[%s]${_W_RST}  %-22s  ${_W_DIM}wrap up interrupted session${_W_RST}\n" "$_KC_CLOSE" "Closeout"
        printf "  ${_W_BOLD}[h]${_W_RST}    %-22s  ${_W_DIM}verify harness+tool alignment · operational state · capabilities · settings${_W_RST}\n" "Spoke Details"
        printf "  ${_W_BOLD}[q]${_W_RST}    Quit\n"
        printf "\n  ${_W_DIM}────────────────────────────────────────────${_W_RST}\n"
        # Drain keystrokes buffered while header/menu rendered (jq, git, Python all take time).
        # Without this, a '1' pressed during loading fires instantly on the wrong read.
        [[ -t 0 ]] && read -r -t 0.5 -n 512 _ 2>/dev/null || true
        printf "  > "

        while true; do
            read -rsn1 _INTENT_CHOICE
            # Initiative tree pre-empt (only when initiatives are shown): a DIGIT
            # selects an initiative → status-check intent; a mapped LETTER selects a
            # child savepoint → resume. Checked before the lane case so digits mean
            # "initiative N" here, not a lane (lanes keep their letter alias).
            if (( ${_INIT_COUNT:-0} > 0 )); then
                if [[ "$_INTENT_CHOICE" =~ ^[1-9]$ ]] && (( _INTENT_CHOICE <= _INIT_COUNT )); then
                    printf "%s\n" "$_INTENT_CHOICE"
                    _ii=$(( _INTENT_CHOICE - 1 ))
                    _INTENT="initiative"
                    _INIT_SEL_ID="${_INIT_IDS[$_ii]}"
                    _INIT_SEL_LABEL="${_INIT_LABELS[$_ii]}"
                    _INTENT_LABEL="Status check — ${_INIT_SEL_LABEL} (${_INIT_SEL_ID})"
                    break
                fi
                if [[ -n "${_SP_LETTER_TO_IDX[$_INTENT_CHOICE]:-}" ]]; then
                    printf "%s\n" "$_INTENT_CHOICE"
                    _sp_idx="${_SP_LETTER_TO_IDX[$_INTENT_CHOICE]}"
                    _INTENT="savepoint"
                    _SP_SELECTED_FILE="${_SP_FILES[$_sp_idx]}"
                    _SP_SELECTED_EMBEDDED="${_SP_EMBEDDED[$_sp_idx]}"
                    _SP_LUG="${_SP_IDS[$_sp_idx]}"
                    _SP_NOTE="${_SP_NOTES[$_sp_idx]}"
                    _INTENT_LABEL="Resume — ${_SP_TITLES[$_sp_idx]}"
                    break
                fi
            fi
            case "${_INTENT_CHOICE}" in
                8|x|X)
                    if [[ "${_SESSION_STATE:-}" == "interrupted" ]]; then
                        printf "8\n"; _INTENT="closeout"; _INTENT_LABEL="Closeout — wrap up interrupted session"; break
                    fi ;;
                u|U)
                    if (( _SIGNALS > 0 )); then
                        printf "u\n"; _INTENT="signals"; _INTENT_LABEL="Messages to the User — ${_SIGNALS} signal(s) awaiting your decision"; break
                    fi ;;
                1|m|M)
                    if (( _SPOKES > 0 )); then
                        printf "1\n"; _INTENT="spokes"; _INTENT_LABEL="Messages to the Spoke — process ${_SPOKES} inter-spoke work lug(s)"; break
                    fi ;;
                2|f|F)
                    if (( _REFINE > 0 )); then
                        printf "2\n"; _INTENT="refinement"; _INTENT_LABEL="Refinement — non-signal lugs missing PEV"; break
                    fi ;;
                3|a|A)
                    if (( _ATTN > 0 )); then
                        printf "3\n"; _INTENT="attention"; _INTENT_LABEL="Needs Action"; break
                    fi ;;
                i|I)
                    if (( _CM_INI_COUNT > 0 )); then
                        printf "i"; read -rsn1 _i_sel
                        if [[ "$_i_sel" =~ ^[1-9]$ ]] && (( _i_sel <= _CM_INI_COUNT )); then
                            printf "%s\n" "$_i_sel"
                            _cm_ini_idx=$(( _i_sel - 1 ))
                            if [[ "${_CM_INI_CLAIMED[$_cm_ini_idx]:-false}" == "true" ]]; then
                                printf "  ${_W_YLW}Already claimed by %s.${_W_RST} Choose a different initiative or resume the existing session.\n  > " \
                                    "${_CM_INI_CLAIMERS[$_cm_ini_idx]}"
                            else
                                _CM_SEL_INITIATIVE="${_CM_INI_IDS[$_cm_ini_idx]}"
                                _CM_SEL_INI_LABEL="${_CM_INI_LABELS[$_cm_ini_idx]}"
                                _cm_ini_fw="$(basher_wai_master_root "$PROJECT_DIR")"
                                _cm_ini_slug=$(printf '%s' "$_CM_SEL_INITIATIVE" | tr -c 'A-Za-z0-9-' '-' | tr '[:upper:]' '[:lower:]')
                                _cm_ini_wt_name="session-$(date +%Y%m%d-%H%M%S)-${_cm_ini_slug:0:20}"
                                _CM_WORKTREE_PATH="$_cm_ini_fw/.claude/worktrees/$_cm_ini_wt_name"
                                if git -C "$_cm_ini_fw" worktree add "$_CM_WORKTREE_PATH" HEAD 2>/dev/null; then
                                    _CM_CLAIM_SESSION="${_SESSION_HINT:-wcl-$(date +%Y%m%d%H%M%S)}"
                                    _cm_ini_claim=$(python3 "$_cm_ini_fw/tools/initiative_lease.py" claim \
                                        "$_CM_SEL_INITIATIVE" "$_CM_CLAIM_SESSION" \
                                        --worktree-path "$_CM_WORKTREE_PATH" 2>/dev/null)
                                    if printf '%s' "$_cm_ini_claim" | python3 -c "import sys,json; sys.exit(0 if json.load(sys.stdin).get('claimed') else 1)" 2>/dev/null; then
                                        printf "  ${_W_GRN}●${_W_RST}  Claimed %s — worktree: %s\n" "$_CM_SEL_INITIATIVE" "$_CM_WORKTREE_PATH"
                                        _INTENT="initiative_start"
                                        _INTENT_LABEL="Start initiative — ${_CM_SEL_INI_LABEL}"
                                        unset _cm_ini_fw _cm_ini_slug _cm_ini_wt_name _cm_ini_idx _cm_ini_claim _i_sel
                                        break
                                    else
                                        git -C "$_cm_ini_fw" worktree remove --force "$_CM_WORKTREE_PATH" 2>/dev/null || true
                                        _CM_WORKTREE_PATH=""
                                        printf "  ${_W_YLW}Could not claim initiative — try another.${_W_RST}\n  > "
                                    fi
                                else
                                    printf "  ${_W_YLW}Could not create worktree — try another.${_W_RST}\n  > "
                                fi
                                unset _cm_ini_fw _cm_ini_slug _cm_ini_wt_name _cm_ini_claim
                            fi
                            unset _cm_ini_idx
                        else
                            printf "\n  > "
                        fi
                        unset _i_sel
                    elif (( ${_INT_COUNT:-0} > 0 )); then
                        printf "i\n"; _INTENT="interrupted"; _INTENT_LABEL="Interrupted — open ${_INT_COUNT} session(s) + take the recommended action"; break
                    fi ;;
                h|H)
                    printf "h\n"
                    if command -v basher >/dev/null 2>&1; then
                        basher spoke || printf "  ${_W_YLW}basher errored — run: basher doctor${_W_RST}\n"
                    else
                        printf "  ${_W_YLW}basher not in PATH — install basher first${_W_RST}\n"
                    fi
                    # Spoke Details is an INFO detour, not a launch choice. Drain its exit
                    # keypress and RETURN to the launch menu (continue re-reads) — do NOT
                    # break, which would fall through and launch claude unintentionally.
                    [[ -t 0 ]] && read -r -t 0.3 -n 512 _ 2>/dev/null || true
                    printf "\n  ${_W_DIM}── back at launch menu — digit/letter to pick · [q] to quit${_W_RST}\n  > "
                    continue ;;
                b|B)
                    ;; # back — no-op at top level, re-prompts silently
                r|R)
                    if (( _CM_SES_COUNT > 0 )); then
                        printf "r"; read -rsn1 _r_sel
                        if [[ "$_r_sel" =~ ^[1-9]$ ]] && (( _r_sel <= _CM_SES_COUNT )); then
                            printf "%s\n" "$_r_sel"
                            _cm_ses_idx=$(( _r_sel - 1 ))
                            _CM_SEL_SESSION="${_CM_SES_IDS[$_cm_ses_idx]}"
                            _CM_SEL_REWARM="${_CM_SES_REWARMS[$_cm_ses_idx]}"
                            printf "\n  ${_W_DIM}Rewarm hint:${_W_RST}\n"
                            printf '%s\n' "$_CM_SEL_REWARM" | while IFS= read -r _rw_line; do
                                printf "  ${_W_DIM}%s${_W_RST}\n" "$_rw_line"
                            done
                            printf "\n"
                            _INTENT="cm_resume"; _INTENT_LABEL="Resume session — ${_CM_SEL_SESSION}"
                            unset _r_sel _cm_ses_idx
                            break
                        else
                            printf "\n  > "
                            unset _r_sel _cm_ses_idx
                        fi
                    else
                        printf "r\n"; _INTENT="raw"; _INTENT_LABEL="Raw — no opening prompt"; break
                    fi ;;
                " ")
                    # space — Raw (hidden shortcut; no opening prompt)
                    printf "r\n"; _INTENT="raw"; _INTENT_LABEL="Raw — no opening prompt"; break ;;
                0|q|Q)
                    printf "quit\n"; echo; rm -f "$_SPOKES_FILE"; return 0 2>/dev/null || exit 0 ;;
                "")
                    # Enter — resume savepoint if pending, else highest-priority default
                    printf "\n"
                    # With initiatives shown, Enter defaults to the focus-pinned
                    # initiative's status check (if any); otherwise it falls through
                    # to the savepoint/lane priority below.
                    _focus_ii=-1
                    if (( ${_INIT_COUNT:-0} > 0 )); then
                        for (( _ii=0; _ii<_INIT_COUNT; _ii++ )); do
                            [[ "${_INIT_FOCUS[$_ii]}" == "1" ]] && { _focus_ii=$_ii; break; }
                        done
                    fi
                    if (( _focus_ii >= 0 )); then
                        _INTENT="initiative"
                        _INIT_SEL_ID="${_INIT_IDS[$_focus_ii]}"
                        _INIT_SEL_LABEL="${_INIT_LABELS[$_focus_ii]}"
                        _INTENT_LABEL="Status check — ${_INIT_SEL_LABEL} (${_INIT_SEL_ID})"
                    elif (( _SP_COUNT == 1 )); then
                        _INTENT="savepoint"  ; _INTENT_LABEL="Resume — ${_SP_TITLES[0]}"
                        _SP_SELECTED_FILE="${_SP_FILES[0]}"; _SP_SELECTED_EMBEDDED="${_SP_EMBEDDED[0]}"
                        _SP_LUG="${_SP_IDS[0]}"; _SP_NOTE="${_SP_NOTES[0]}"
                    elif (( _SP_COUNT > 1 )); then
                        # Show numbered sub-menu for multi-savepoint selection
                        printf "\n  ${_W_DIM}Which savepoint?${_W_RST}\n\n"
                        for (( _sp_i=0; _sp_i<_SP_COUNT; _sp_i++ )); do
                            printf "  ${_W_BOLD}[%d]${_W_RST}  %-34s%s${_W_DIM}%s${_W_RST}\n" \
                                "$(( _sp_i+1 ))" "${_SP_TITLES[$_sp_i]}" "$(_sp_silo_tag "${_SP_SILOS[$_sp_i]}")" "${_SP_NOTES[$_sp_i]:+  — ${_SP_NOTES[$_sp_i]}}"
                        done
                        printf "  ${_W_BOLD}[r]${_W_RST}  Raw  ${_W_DIM}[b]${_W_RST}  Back  ${_W_DIM}[q]${_W_RST}  Quit\n"
                        printf "\n  > "
                        while true; do
                            read -rsn1 _SP_SEL
                            if [[ "$_SP_SEL" =~ ^[1-9]$ ]] && (( _SP_SEL <= _SP_COUNT )); then
                                _SP_SEL_IDX=$(( _SP_SEL - 1 ))
                                printf "%s\n" "$_SP_SEL"
                                _INTENT="savepoint"
                                _SP_SELECTED_FILE="${_SP_FILES[$_SP_SEL_IDX]}"
                                _SP_SELECTED_EMBEDDED="${_SP_EMBEDDED[$_SP_SEL_IDX]}"
                                _SP_LUG="${_SP_IDS[$_SP_SEL_IDX]}"
                                _SP_NOTE="${_SP_NOTES[$_SP_SEL_IDX]}"
                                _INTENT_LABEL="Resume — ${_SP_TITLES[$_SP_SEL_IDX]}"
                                break
                            elif [[ "$_SP_SEL" == "r" || "$_SP_SEL" == "R" ]]; then
                                printf "r\n"; _INTENT="raw"; _INTENT_LABEL="Raw — no opening prompt"; break
                            elif [[ "$_SP_SEL" == "b" || "$_SP_SEL" == "B" ]]; then
                                printf "b\n"; break  # back — _INTENT unset, re-renders main menu
                            elif [[ "$_SP_SEL" == "q" || "$_SP_SEL" == "Q" ]]; then
                                printf "quit\n"; echo; rm -f "$_SPOKES_FILE"; return 0 2>/dev/null || exit 0
                            fi
                        done
                    elif (( _SIGNALS > 0 )); then
                        _INTENT="signals"    ; _INTENT_LABEL="Messages to the User"
                    elif (( _SPOKES > 0 )); then
                        _INTENT="spokes"     ; _INTENT_LABEL="Messages to the Spoke"
                    elif (( _ATTN > 0 )); then
                        _INTENT="attention"  ; _INTENT_LABEL="Needs Your Action"
                    elif (( _WORK > 0 )); then
                        _INTENT="ready_work" ; _INTENT_LABEL="Ready to Process"
                    else
                        _INTENT="raw"        ; _INTENT_LABEL="Raw — no opening prompt"
                    fi
                    break ;;
                *) ;; # invalid key — re-prompt silently
            esac
        done

        # ── Sub-menu: Work Queue ──────────────────────────────────────────────
        if [[ "$_INTENT" == "ready_work" ]]; then
            printf "\n"
            printf "  ${_W_DIM}Work Queue — what next?${_W_RST}\n\n"
            printf "  ${_W_BOLD}[9/r]${_W_RST}  %-22s  ${_W_DIM}Enter${_W_RST}\n" "Review items"
            printf "  ${_W_BOLD}[a]${_W_RST}    %-22s  ${_W_DIM}runs: basher autopilot --budget %d${_W_RST}\n" \
                "Send to Autopilot" "$_WORK"
            printf "  ${_W_BOLD}[b]${_W_RST}    Back\n"
            printf "  ${_W_BOLD}[0/q]${_W_RST}  Quit\n"
            printf "\n  > "

            while true; do
                read -rsn1 _SUB_CHOICE
                case "$_SUB_CHOICE" in
                    r|R|"")
                        printf "r\n"; _READY_ACTION="review"; break ;;
                    a|A)
                        printf "a\n"; _READY_ACTION="autopilot"; break ;;
                    b|B)
                        printf "b\n"; _INTENT=""; _READY_ACTION=""; break ;;  # back to main menu
                    q|Q)
                        printf "quit\n"; echo; rm -f "$_SPOKES_FILE"
                        return 0 2>/dev/null || exit 0 ;;
                    *) ;; # invalid key — re-prompt silently
                esac
            done

            if [[ "$_READY_ACTION" == "autopilot" ]]; then
                rm -f "$_SPOKES_FILE"
                # Sibling first (autopilot.sh is canon in managed/tools/), then
                # CANON_ROOT's managed canon, then the legacy scripts/ path.
                _AUTOPILOT_SCRIPT="$SCRIPT_DIR/autopilot.sh"
                [[ -f "$_AUTOPILOT_SCRIPT" ]] || _AUTOPILOT_SCRIPT="$CANON_ROOT/WAI-Harness/spoke/managed/tools/autopilot.sh"
                [[ -f "$_AUTOPILOT_SCRIPT" ]] || _AUTOPILOT_SCRIPT="$CANON_ROOT/scripts/autopilot.sh"
                if [[ -f "$_AUTOPILOT_SCRIPT" ]]; then
                    printf "\n  ${_W_DIM}Sending %d item(s) to autopilot...${_W_RST}\n\n" "$_WORK"
                    bash "$_AUTOPILOT_SCRIPT" run --budget "$_WORK"
                else
                    printf "  ${_W_YLW}ERROR:${_W_RST} autopilot.sh not found at %s\n" "$_AUTOPILOT_SCRIPT"
                fi
                return 0 2>/dev/null || exit 0
            fi
            # _READY_ACTION == "review" — fall through to normal launch with ready_work prompt
            # _READY_ACTION == ""       — [b] back pressed, restart menu
            [[ -z "$_READY_ACTION" ]] && continue
        fi

        break  # intent set and no back request — exit back-support loop
        done  # end back-support loop

    fi

    _SP_RESUMED="false"
    [[ "$_INTENT" == "savepoint" ]] && _SP_RESUMED="true"
    export _SP_SELECTED_FILE _SP_SELECTED_EMBEDDED

    mkdir -p "$WAI_LOCAL/runtime"
    _INTENT="$_INTENT" _INTENT_LABEL="$_INTENT_LABEL" _SESSION_HINT="$_SESSION_HINT" \
    _SP_RESUMED="$_SP_RESUMED" _INTENT_CHOICE="$_INTENT_CHOICE" _INTENT_FILE="$_INTENT_FILE" \
    _SP_SELECTED_FILE="$_SP_SELECTED_FILE" \
    _INIT_SEL_ID="${_INIT_SEL_ID:-}" _INIT_SEL_LABEL="${_INIT_SEL_LABEL:-}" \
    _CM_SEL_SESSION="${_CM_SEL_SESSION:-}" _CM_SEL_INITIATIVE="${_CM_SEL_INITIATIVE:-}" \
    _CM_CLAIM_SESSION="${_CM_CLAIM_SESSION:-}" _CM_WORKTREE_PATH="${_CM_WORKTREE_PATH:-}" \
    python3 -c "
import json, datetime, os
data = {
    'intent': os.environ['_INTENT'],
    'intent_label': os.environ['_INTENT_LABEL'],
    'selected_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'session_id_hint': os.environ['_SESSION_HINT'],
    'savepoint_resumed': os.environ['_SP_RESUMED'] == 'true',
    'savepoint_file': os.environ.get('_SP_SELECTED_FILE', ''),
    'initiative_id': os.environ.get('_INIT_SEL_ID', ''),
    'initiative_label': os.environ.get('_INIT_SEL_LABEL', ''),
    'raw_choice': os.environ['_INTENT_CHOICE'],
    'cm_resumed_session': os.environ.get('_CM_SEL_SESSION', ''),
    'cm_initiative_id': os.environ.get('_CM_SEL_INITIATIVE', ''),
    'cm_claim_session': os.environ.get('_CM_CLAIM_SESSION', ''),
    'cm_worktree_path': os.environ.get('_CM_WORKTREE_PATH', ''),
}
with open(os.environ['_INTENT_FILE'], 'w') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null

    if [[ "$_CONTINUE_MODE" == "false" ]]; then
        case "$_INTENT" in
            initiative)
                # Selecting an initiative drops a STATUS-CHECK prompt scoped to it —
                # review open lugs + parked savepoints + recent results, report where
                # it stands. No new work until the user confirms.
                _OPEN_PROMPT=$(
                    printf "Status check on the %s initiative (%s) — do NOT start new work yet; report where it stands.\n\n" "$_INIT_SEL_LABEL" "$_INIT_SEL_ID"
                    printf "Review, scoped to this initiative:\n"
                    printf "  1. Open + in-progress lugs in %s/lugs/bytype/*/ whose initiative_id is %s (or that reference it).\n" "$_WL_REL" "$_INIT_SEL_ID"
                    printf "  2. Parked child savepoints in %s/initiatives/savepoints/%s/ — what each one left off on.\n" "$_WL_REL" "$_INIT_SEL_ID"
                    printf "  3. Recent results: the initiative's current_position + any bolts in %s/bolts/ for this silo.\n\n" "$_WL_REL"
                    printf "Then report: where it stands, what is blocked, and the single best next action. Ask me whether to pin focus to this initiative and proceed.\n"
                ) ;;
            savepoint)
                # _SP_SELECTED_FILE is where the savepoint actually lives; the shape
                # differs by source (see the resume-scan tool):
                #   embedded=1  -> the savepoint is the ._savepoint object inside a WAI-State.json
                #   embedded='' -> the file in savepoints/ IS the savepoint object
                # Claim/commit THAT file with the matching jq path.
                _SP_STATE_REL="${_SP_SELECTED_FILE#"$PROJECT_DIR"/}"
                if [[ "${_SP_SELECTED_EMBEDDED:-}" == "1" ]]; then
                    _SP_SID=$(jq -r '._savepoint.session_id // ""' "${_SP_SELECTED_FILE}" 2>/dev/null || echo "")
                    _SP_OBJ_DESC="the ._savepoint object in ${_SP_STATE_REL}"
                    _SP_CLAIM_DESC="Set ._savepoint.status='active' and ._savepoint.claimed_at"
                else
                    _SP_SID=$(jq -r '.session_id // ""' "${_SP_SELECTED_FILE}" 2>/dev/null || echo "")
                    _SP_OBJ_DESC="${_SP_STATE_REL} (the file IS the savepoint object)"
                    _SP_CLAIM_DESC="Set status='active' and claimed_at"
                fi
                _SP_TRACK_PATH=""
                for _spt in "${_WL_REL}/sessions/${_SP_SID}/track.jsonl" "WAI-Spoke/sessions/${_SP_SID}/track.jsonl"; do
                    [[ -n "$_SP_SID" && -f "$PROJECT_DIR/$_spt" ]] && { _SP_TRACK_PATH="$_spt"; break; }
                done
                _OPEN_PROMPT="Resume the pending savepoint. Read ${_SP_OBJ_DESC} for context. Fields: work_done (what was completed last session), work_context (the larger goal), resume_note (first action now), user_next_step, open_threads.${_SP_TRACK_PATH:+ Also read ${_SP_TRACK_PATH} (prior session track) for full context before resuming.} ${_SP_CLAIM_DESC}=$(date -u +%Y-%m-%dT%H:%M:%SZ) in ${_SP_STATE_REL}, then git add ${_SP_STATE_REL} && git commit -m 'savepoint: claim ${_SP_LUG}' && git push origin main. Then continue from resume_note.${_SP_NOTE:+ Note: ${_SP_NOTE}}" ;;
            interrupted)
                _OPEN_PROMPT=$(
                    printf "Open and resolve %d interrupted session(s) — read each track, then take the recommended action (resume the unfinished work, or complete + closeout). Confirm with me before any destructive step:\n\n" "$_INT_COUNT"
                    for (( _int_i=0; _int_i<_INT_COUNT; _int_i++ )); do
                        printf "  %d. %s — %s\n     track: %s\n" "$(( _int_i+1 ))" "${_INT_IDS[$_int_i]}" "${_INT_ACTIONS[$_int_i]}" "${_INT_FILES[$_int_i]#"$PROJECT_DIR"/}"
                    done
                    printf "\nWalk them oldest-first. State the recommended action + a one-line rationale for each before acting.\n"
                ) ;;
            refinement)
                _OPEN_PROMPT=$(
                    printf "Refine %d non-signal lug(s) missing PEV fields.\n\n" "$_REFINE"
                    printf "For each lug in ${_WL_REL}/lugs/incoming/ or bytype/*/open/ that lacks perceive/execute/verify:\n"
                    printf "  1. Read the lug — understand the intent.\n"
                    printf "  2. Fill in perceive (what to read/verify first), execute (exact steps), verify (how to confirm done).\n"
                    printf "  3. Assign model_fit and target_files if missing.\n\n"
                    printf "Do not implement — refine only. State each fill before writing."
                ) ;;
            signals)
                _OPEN_PROMPT=$(
                    printf "You have %d signal(s) in the operator mailbox (${_WL_REL}/lugs/bytype/signal/open/) — items the spoke raised that need YOUR decision.\n\n" "$_SIGNALS"
                    printf "For each signal, present it as a one-glance decision: the blocker, the decision needed, the options + my recommended default, and the cost of waiting. Then help me resolve it and record the outcome on the signal. These are the only items that warrant interrupting me — everything else the spoke handles itself.\n"
                ) ;;
            spokes)
                _OPEN_PROMPT=$(python3 -c "
import json
try:
    items = json.load(open('$_SPOKES_FILE'))
    out = ['Process {} inter-spoke work lug(s) in ${_WL_REL}/lugs/incoming/ — work delivered FOR this spoke by other spokes. These are NOT messages requiring my decision; triage them yourself.'.format(len(items)), '', 'Items:']
    for i, item in enumerate(items, 1):
        out.append('  {}. [{}] from {}: {}'.format(
            i, item.get('urgency_label','Normal'), item.get('sender_name','?'), item.get('title','')))
    out += ['', 'For each lug, autonomously:',
            '  1. Read the file in ${_WL_REL}/lugs/incoming/.',
            '  2. Evaluate fit against this spoke mission and current priorities.',
            '  3. Decide: accept (route to ${_WL_REL}/lugs/bytype/{type}/open/), defer (add deferred_until note), or reject (counter-lug to source_spoke with the reason).',
            '',
            'Process them yourself — do not ask me to adjudicate spoke work. Raise an item to me ONLY if it meets the signal bar (a blocker only I can clear); if so, write it to the operator mailbox (bytype/signal/) rather than asking inline.']
    print('\n'.join(out))
except Exception:
    print('Process the inter-spoke work lugs in ${_WL_REL}/lugs/incoming/ autonomously: read each, decide accept/defer/reject, route accordingly. These are spoke work, not operator messages.')
" 2>/dev/null) ;;
            attention)
                _OPEN_PROMPT=$(
                    printf "Resolve %d item(s) needing decision in this spoke. For each category, take the action below:\n\n" "$_ATTN"
                    (( _ATTN_OZI > 0 ))     && printf "Ozi-flagged (%d): read each lug under ${_WL_REL}/lugs/bytype/*/ozi_review/. Decide accept / decompose / reject and record the reason on the lug.\n\n" "$_ATTN_OZI"
                    (( _STALLED > 0 ))      && printf "Stalled in-progress (%d): for each lug in_progress >24h, choose unstick / retry / defer / close and update its status with a note.\n\n" "$_STALLED"
                    (( _BLOCKED > 0 ))      && printf "Blocked lugs (%d): for each lug in ${_WL_REL}/lugs/bytype/*/blocked/, verify the blocking lug still exists and is unresolved. If clear, move the lug back to open/. If still real, document why on the lug.\n\n" "$_BLOCKED"
                    printf "Walk the categories in order. Before acting on individual items, state the intended decision so I can interject."
                ) ;;
            ready_work)
                _OPEN_PROMPT=$(
                    printf "Process %d item(s) in the work queue.\n\n" "$_WORK"
                    (( _INC_UNGROOMED > 0 )) && printf "Ungroomed (%d): in ${_WL_REL}/lugs/incoming/. Read each, score effort (1-10), assign model_fit (haiku/sonnet/opus), and route to ${_WL_REL}/lugs/bytype/{type}/open/. Report each scoring decision before routing.\n\n" "$_INC_UNGROOMED"
                    (( _INC_HAIKU > 0 ))     && printf "Haiku-ready (%d): autonomous builds in ${_WL_REL}/lugs/bytype/*/open/ with model_fit=haiku.\n\n" "$_INC_HAIKU"
                    (( _INC_SONNET > 0 ))    && printf "Sonnet-ready (%d): builds in ${_WL_REL}/lugs/bytype/*/open/ with model_fit=sonnet.\n\n" "$_INC_SONNET"
                    printf "Steps:\n"
                    printf "  1. Groom all ungroomed items first.\n"
                    printf "  2. Then propose: launch \`basher autopilot run --budget %d\` for the haiku/sonnet queue, or hand specific items back for review.\n" "$_WORK"
                ) ;;
            cm_resume)
                _OPEN_PROMPT=$(
                    printf "Resuming session %s.\n\n" "$_CM_SEL_SESSION"
                    printf "%s\n" "$_CM_SEL_REWARM"
                ) ;;
            initiative_start)
                _OPEN_PROMPT=$(
                    printf "You have claimed the '%s' initiative (%s).\n\n" "$_CM_SEL_INI_LABEL" "$_CM_SEL_INITIATIVE"
                    printf "Your working worktree is at: %s\n\n" "$_CM_WORKTREE_PATH"
                    printf "Begin by:\n"
                    printf "  1. cd %s\n" "$_CM_WORKTREE_PATH"
                    printf "  2. Read the WAI state and any open lugs for this initiative.\n"
                    printf "  3. Pick up the next task and proceed.\n"
                ) ;;
            raw|*)
                _OPEN_PROMPT="" ;;
        esac
        # NOTE: the opening-prompt is DISPLAYED later, immediately before the
        # "Launching..." line, so the audit output below it (doctor/config/anomaly)
        # cannot scroll it off-screen. _OPEN_PROMPT is only computed here.
    fi

    rm -f "$_SPOKES_FILE"
fi

# ── 2. Refresh stale context feeds in background ────────────────────────────
if [[ "$IS_HUB" == "true" && -f "$PROJECT_DIR/tools/hub_context_refresh.py" ]]; then
    mkdir -p "$HOME/.claude/logs"
    python3 "$PROJECT_DIR/tools/hub_context_refresh.py" \
        --quiet \
        >> "$HOME/.claude/logs/hub-context-refresh-$(date +%Y%m%d).log" 2>&1 &
    _wai_info "Feeds" "hub refresh running in background"
else
    EXPEDITER_STATE="$WAI_ADV/expediter/scan_state.json"
    if [[ -f "$EXPEDITER_STATE" && -f "$PROJECT_DIR/tools/advisor_context_refresh.py" ]]; then
        LAST_RUN=$(python3 -c "
import json
try:
    s = json.load(open('$EXPEDITER_STATE'))
    print(s.get('last_run_at','')[:10])
except:
    print('')
" 2>/dev/null || echo "")
        TODAY=$(date +%Y-%m-%d)
        if [[ -n "$LAST_RUN" && "$LAST_RUN" != "$TODAY" ]]; then
            mkdir -p "$HOME/.claude/logs"
            python3 "$PROJECT_DIR/tools/advisor_context_refresh.py" \
                --quiet --spoke-path "$PROJECT_DIR" \
                >> "$HOME/.claude/logs/context-refresh-$(date +%Y%m%d).log" 2>&1 &
            _wai_info "Feeds" "refreshing (last: $LAST_RUN)"
        fi
    fi
fi

# ── 3. Hub: check outbox for pending deliveries ──────────────────────────────
if [[ "$IS_HUB" == "true" ]]; then
    OUTBOX="$PROJECT_DIR/WAI-Hub/outbox"
    if [[ -d "$OUTBOX" ]]; then
        PENDING=$(find "$OUTBOX" -mindepth 2 -maxdepth 2 -name "*.json" 2>/dev/null | wc -l)
        [[ "$PENDING" -gt 0 ]] && _wai_warn "Outbox" "$PENDING pending deliveries"
    fi
fi

# ── 3. Spoke: hook completeness check ───────────────────────────────────────
if [[ "$IS_SPOKE" == "true" && -f "$PROJECT_DIR/.claude/settings.json" ]]; then
    _CONFIG_GAPS=$(python3 -c "
import json, sys
try:
    d = json.load(open('$PROJECT_DIR/.claude/settings.json'))
    required = {'SessionStart','PreToolUse','Stop','PreCompact','UserPromptSubmit'}
    missing = required - set(d.get('hooks',{}).keys())
    deny = d.get('permissions',{}).get('deny',[])
    if missing:
        print('hooks: ' + ', '.join(sorted(missing)))
    if not deny:
        print('deny-rules: none configured')
except: pass
" 2>/dev/null)
    if [[ -n "$_CONFIG_GAPS" ]]; then
        _wai_warn "Config" "gaps detected — run: basher tools update current"
        echo "$_CONFIG_GAPS" | while IFS= read -r line; do
            printf "         ${_W_DIM}%s${_W_RST}\n" "$line"
        done
        echo ""
    fi
fi

# ── 3. Spoke: run basher doctor audit if available ───────────────────────────
if [[ "$IS_HUB" == "false" ]] && command -v basher >/dev/null 2>&1; then
    # Capture the REAL rc. The old form was `$(...) || true` followed by `BASHER_EXIT=$?`,
    # which reads the exit of `|| true` — always 0. So BASHER_EXIT was ALWAYS 0, the
    # `-ne 0` branch below was DEAD, and a hard-failing doctor reported "Basher OK".
    # Assigning on its own line keeps $? pointing at the command substitution.
    BASHER_OUT=$(basher doctor audit 2>&1)
    BASHER_EXIT=$?
    if [[ $BASHER_EXIT -ne 0 ]] || echo "$BASHER_OUT" | grep -qiE 'fixed|changed|updated|repaired'; then
        mkdir -p "$WAI_LOCAL/runtime"
        # Doctor output goes via env, never interpolated into the Python source.
        # It used to land inside a '''…''' literal, so any ''' or trailing backslash
        # in doctor's output broke the parse or executed as code. Same pattern the
        # intent-write block already uses correctly.
        BASHER_OUT="$BASHER_OUT" BASHER_EXIT="$BASHER_EXIT" \
        _AUDIT_OUT="$WAI_LOCAL/runtime/basher-audit-result.json" \
        python3 -c "
import json, datetime, os
result = {
    'run_at': datetime.datetime.now().isoformat(),
    'output': os.environ['BASHER_OUT'][:500],
    'exit_code': int(os.environ['BASHER_EXIT']),
    'changes_detected': True
}
with open(os.environ['_AUDIT_OUT'], 'w') as f:
    json.dump(result, f, indent=2)
" 2>/dev/null || true
        _wai_warn "Basher" "config changes detected — see wakeup blurb"
    else
        _wai_ok "Basher" "OK"
    fi
fi

# ── 4. Spoke: detect anomalies outside WAI-Spoke/ (read-only) ───────────────
if [[ "$IS_HUB" == "false" ]]; then
    ANOMALIES=0

    for d in "$PROJECT_DIR"/session-*/; do
        [[ -d "$d" ]] || continue
        NAME=$(basename "$d")
        TS=$(date +%s)
        python3 -c "
import json, datetime
lug = {
    'id': 'signal-pre-wrapper-anomaly-${TS}-v1',
    'type': 'signal',
    'status': 'undelivered',
    'title': 'Anomaly: session dir at project root: $NAME',
    'source': 'pre-wrapper-scan',
    'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'description': 'Found $d outside ${_WL_REL}/sessions/. Likely misplaced. Verify and move or delete.'
}
import os; os.makedirs('$WAI_LOCAL/lugs/bytype/signal/undelivered', exist_ok=True)
with open('$WAI_LOCAL/lugs/bytype/signal/undelivered/signal-pre-wrapper-anomaly-${TS}-v1.json', 'w') as f:
    json.dump(lug, f, indent=2)
" 2>/dev/null && ANOMALIES=$((ANOMALIES + 1))
    done

    if [[ -f "$PROJECT_DIR/track.jsonl" ]]; then
        TS=$(date +%s)
        python3 -c "
import json, datetime
lug = {
    'id': 'signal-pre-wrapper-anomaly-${TS}-v1',
    'type': 'signal',
    'status': 'undelivered',
    'title': 'Anomaly: track.jsonl found at project root',
    'source': 'pre-wrapper-scan',
    'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'description': 'Found track.jsonl at $PROJECT_DIR root — should be under ${_WL_REL}/sessions/.'
}
import os; os.makedirs('$WAI_LOCAL/lugs/bytype/signal/undelivered', exist_ok=True)
with open('$WAI_LOCAL/lugs/bytype/signal/undelivered/signal-pre-wrapper-anomaly-${TS}-v1.json', 'w') as f:
    json.dump(lug, f, indent=2)
" 2>/dev/null && ANOMALIES=$((ANOMALIES + 1))
    fi

    [[ $ANOMALIES -gt 0 ]] && _wai_warn "Anomalies" "$ANOMALIES signal lug(s) created — handle at wakeup"
fi

# ── 5. Auto-fix inside the resolved working-state base only ─────────────────
# Gated on IS_SPOKE. WAI_LOCAL is resolved from PROJECT_DIR unconditionally, so on
# a HUB (no spoke state) this mkdir fabricated a phantom <hub>/WAI-Spoke/runtime/
# on EVERY launch — creating the very v3 layout the hub does not have, which then
# reads as a half-migrated spoke to anything that probes for WAI-Spoke/.
if [[ "$IS_SPOKE" == "true" ]]; then
    mkdir -p "$WAI_LOCAL/runtime"

    for d in "$WAI_LOCAL/session-"*/; do
        [[ -d "$d" ]] || continue
        NAME=$(basename "$d")
        mkdir -p "$WAI_LOCAL/sessions"
        mv "$d" "$WAI_LOCAL/sessions/$NAME" 2>/dev/null \
            && _wai_info "Fixed" "moved $NAME → ${_WL_REL}/sessions/"
    done
fi

if [[ -d "$PROJECT_DIR/.claude/hooks" ]]; then
    chmod +x "$PROJECT_DIR/.claude/hooks/"*.sh 2>/dev/null || true
fi

# ── 6. Launch tool ──────────────────────────────────────────────────────────
# TOOL + _TOOL_ARGS resolve through the SAME function the dry-run seam calls, so
# the WAI_DRY_RUN=1 trace always reports the argv this path actually executes.
_wai_resolve_tool_args "$@"

if ! command -v "$TOOL" >/dev/null 2>&1; then
    printf "  ${_W_YLW}ERROR:${_W_RST} tool '%s' not found in PATH\n" "$TOOL"
    exit 1
fi

# ── Default into Ozi auto-mode-on (silent, spoke + claude only) ──────────────
# Per /wai-auto-on: session-local builder posture. No wai_ozi daemon consumes
# this in basher today — the in-session agent honors it, and the /wai-auto-*
# skills read the harness-resolved runtime/ozi-sessions dir (v4 or v3). Keyed
# by ZELLIJ_PANE_ID -> WAI session hint -> "default". Always on, no prompt.
if [[ "$IS_SPOKE" == "true" && "$TOOL" == "claude" ]]; then
    _AUTO_KEY="${ZELLIJ_PANE_ID:-${_SESSION_HINT:-default}}"
    _AUTO_KEY=$(printf '%s' "$_AUTO_KEY" | tr -c 'A-Za-z0-9._-' '_')
    # Resolve via wai_paths (v4-aware); fall back to v3 WAI-Spoke on import fail.
    _WAI_PATHS_TOOL="$PROJECT_DIR/WAI-Harness/spoke/managed/tools/wai_paths.py"
    [[ -f "$_WAI_PATHS_TOOL" ]] || _WAI_PATHS_TOOL="$SCRIPT_DIR/wai_paths.py"
    if [[ -f "$_WAI_PATHS_TOOL" ]]; then
        _WAI_RUNTIME=$(python3 "$_WAI_PATHS_TOOL" --root "$PROJECT_DIR" --category runtime 2>/dev/null)
    fi
    # Fall back to the RESOLVED local base, not a hardcoded v3 "WAI-Spoke". When
    # wai_paths.py is missing or errors, _WAI_RUNTIME is empty and the old form
    # expanded to $PROJECT_DIR/WAI-Spoke/runtime — so the mkdir -p below CREATED a
    # phantom WAI-Spoke/ inside a pure-v4 spoke, splitting ozi-sessions across two
    # bases (hooks write v4, launcher writes v3) with no error either way.
    _AUTO_DIR="${_WAI_RUNTIME:-$WAI_LOCAL/runtime}/ozi-sessions"
    unset _WAI_PATHS_TOOL _WAI_RUNTIME
    mkdir -p "$_AUTO_DIR"
    _AUTO_KEY="$_AUTO_KEY" _AUTO_DIR="$_AUTO_DIR" python3 -c "
import json, os, datetime
data = {
    'auto_mode': True,
    'max_parallel': 1,
    'watch_mode': False,
    'poll_interval_minutes': 5,
    'source': 'wcl-default',
    'set_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
path = os.path.join(os.environ['_AUTO_DIR'], os.environ['_AUTO_KEY'] + '.json')
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null
    unset _AUTO_KEY _AUTO_DIR
fi

# ── Zellij: reset tab name + record interaction timestamp ───────────────────
if [[ -n "${ZELLIJ_PANE_ID:-}" && "$TOOL" == "claude" ]]; then
    [ -f ~/.config/basher/tools/zellij-tabindex.sh ] && source ~/.config/basher/tools/zellij-tabindex.sh
    command -v _zellij_tab_prefix >/dev/null 2>&1 || _zellij_tab_prefix() { return 0; }
    command -v _basher_spoke_name >/dev/null 2>&1 || _basher_spoke_name() { local r="${1:-}"; r="${r%/.worktrees/*}"; basename "$r"; }
    command -v _basher_tab_render >/dev/null 2>&1 || _basher_tab_render() { local n="${2:0:$((8-${#3}))}"; printf '%s %s%s' "$1" "$n" "${3:-}"; }
    # Worktree-aware spoke short-name shared with the notify hooks / idle shell / lens,
    # so the launch tab matches everywhere instead of showing a worktree hash.
    _zellij_project=$(_basher_spoke_name "$PROJECT_DIR"); _zellij_project="${_zellij_project:0:15}"
    # Launch glyph: ⏳ (working) — single vocabulary with the notify hooks (no retired ●
    # dot). Fills the gap before claude's first notify event sets ⏳/✅. by-id so it
    # targets THIS pane's tab, not the focused one.
    _zellij_panes=$(zellij action list-panes --json 2>/dev/null || echo "[]")
    _zellij_idx=$(_zellij_tab_prefix "$_zellij_panes" || true)
    _zellij_tabid=$(printf '%s' "$_zellij_panes" | jq -r ".[]|select(.id==${ZELLIJ_PANE_ID} and .is_floating==false)|.tab_id // empty" 2>/dev/null)
    # Render name-first with "-N" kept whole as the suffix (not idx-first glued, which
    # truncated the number and flipped the format vs the notify/idle writers).
    _zellij_lbl=$(_basher_tab_render "⏳" "$_zellij_project" "${_zellij_idx:+-$_zellij_idx}")
    if [ -n "$_zellij_tabid" ]; then
        zellij action rename-tab-by-id "$_zellij_tabid" "$_zellij_lbl" >/dev/null 2>&1 || true
    else
        zellij action rename-tab "$_zellij_lbl" >/dev/null 2>&1 || true
    fi
    mkdir -p /tmp/claude-sessions
    date +%s > "/tmp/claude-sessions/last-interaction-${ZELLIJ_PANE_ID}"
    touch "/tmp/claude-sessions/active-${ZELLIJ_PANE_ID}"
    unset _zellij_project _zellij_idx _zellij_panes _zellij_tabid _zellij_lbl
fi

# ── Idle monitor: auto-savepoint flag after 20 min inactivity ────────────────
if [[ -n "${ZELLIJ_PANE_ID:-}" && "$TOOL" == "claude" ]]; then
    _IDLE_PANE="$ZELLIJ_PANE_ID"
    _IDLE_FLAG="$(basher_wai_local "$PROJECT_DIR")/runtime/auto-savepoint-requested.flag"
    nohup bash -c "
        while true; do
            sleep 60
            [[ ! -f /tmp/claude-sessions/active-${_IDLE_PANE} ]] && exit 0
            _ts=/tmp/claude-sessions/last-interaction-${_IDLE_PANE}
            if [[ -f \"\$_ts\" ]]; then
                _last=\$(cat \"\$_ts\" 2>/dev/null || echo 0)
                _idle=\$(( \$(date +%s) - _last ))
                if [[ \$_idle -ge 1200 ]]; then
                    touch \"${_IDLE_FLAG}\"
                    exit 0
                fi
            fi
        done
    " > /dev/null 2>&1 &
    disown
    unset _IDLE_PANE _IDLE_FLAG
fi

# Doctor auto-runs foreground before the menu (see health check section above).
# No background launch needed.

# Seed mode: the external prompt is the opening prompt (the menu/case was skipped).
[[ "$_SEED_MODE" == "true" ]] && _OPEN_PROMPT="${WAI_SEED_PROMPT:-}"

# A continuation cannot carry an opening prompt (it already has its history, and
# claude rejects --session-id alongside --continue/--resume). The launch tail gates
# the seed on _IS_CONTINUATION, so drop the prompt HERE — otherwise the display
# block below would print an opening prompt that is never delivered, which is the
# exact silent-loss failure this wave exists to remove. Reachable only by asking for
# both at once (e.g. WAI_SEED_PROMPT set alongside --resume): say so, don't guess.
if [[ -n "${_OPEN_PROMPT:-}" && "$_IS_CONTINUATION" == "true" ]]; then
    _wai_warn "Prompt" "continuation (-c/--continue/--resume/-r) — opening prompt NOT sent; the session resumes with its own history"
    _OPEN_PROMPT=""
fi

# ── Opening prompt: displayed LAST so audit output cannot bury it ────────────
if [[ -n "${_OPEN_PROMPT:-}" ]]; then
    printf "\n  ${_W_DIM}Opening prompt:${_W_RST}\n"
    printf "  ${_W_DIM}──────────────────────────────────────────${_W_RST}\n"
    printf '%s\n' "$_OPEN_PROMPT" | while IFS= read -r _wai_line; do
        printf "  ${_W_DIM}%s${_W_RST}\n" "$_wai_line"
    done
    printf "  ${_W_DIM}──────────────────────────────────────────${_W_RST}\n"
fi

# ── Launch-time source isolation: auto-worktree the 2nd+ concurrent session ──
# A running claude cannot relocate its own CWD, so source isolation must happen HERE,
# at launch, before exec — never from a SessionStart hook. 0 OTHER live lanes -> shared
# tree (zero cost). >=1 -> create a git worktree off the MAIN tree and launch in it, so
# two sessions never sweep each other's in-flight files (the S45 `git add -A` hazard).
# Closeout merges the worktree branch back (worktree_guard wt-finish --merge).
# Escape hatch: WAI_NO_ISOLATE=1. Headless (-p) launches keep the shared tree.
# (impl-basher-concurrent-session-autoisolation-v1)
#
# The decision and its application are now separate functions (defined above) so the
# WAI_DRY_RUN=1 seam can drive the decision without creating a worktree. _wai_isolation_decide
# also RESERVES this launch's lane before reading the registry — see the W2 ordering note.
_WAI_ISOLATED=0
_wai_isolation_decide
[[ "$_ISO_SHOULD" == "yes" ]] && _wai_isolation_apply

# ── Duplicate-session guard: stop a twin claude on the same project ──────────
# Decide/apply split for the same reason. Headless (-p), explicit override
# (WAI_ALLOW_DUP=1), and an already source-isolated launch all skip it.
_wai_dupguard_decide
[[ "$_DUP_STATE" == "fired" ]] && _wai_dupguard_apply

printf "\n  ${_W_DIM}Launching %s...${_W_RST}\n\n" "$TOOL"
# ── W3: a CONTINUATION is never re-seeded ────────────────────────────────────
# The two-phase seed exists to give a FRESH session an opening prompt. A
# continuation (-c / --continue / --resume / -r) already carries its own history,
# and claude rejects the combination outright:
#   "Error: --session-id can only be used with --continue or --resume if
#    --fork-session is also specified."
# So phase 1 died and the opening prompt vanished SILENTLY, while phase 2's
# duplicate --resume landed the operator in the right session only by accident of
# last-wins arg parsing. --fork-session is NOT the fix — it clones the session
# instead of resuming it, which is not what any of these callers asked for.
# Gating on _IS_CONTINUATION retires that whole class: wcl-c, wcl-cc, and the
# duplicate --resume.
#
# Phase 1 runs headless (`claude -p`) and prints NOTHING until it exits — for a
# large survey prompt (e.g. basher TUI's "Do it all") that can be several minutes
# of real tool-call latency with zero operator-visible feedback, indistinguishable
# from a hang (bug-tui-doall-claude-p-stalls-no-feedback-v1: reproduced 4m23s and
# 90s runs, both 0 bytes of output before timeout). _wai_seed_headless_run wraps
# phase 1 with a live elapsed-time line and a hard ceiling (WAI_SEED_TIMEOUT,
# default 180s) so silence is never mistaken for a stall and a genuinely stuck
# call can never trap the operator — phase 2 (--resume) always runs after, and
# attaches to whatever the pinned session-id has even if phase 1 was killed.
_wai_seed_headless_run() {
    printf "  ${_W_DIM}Sending your prompt to Claude — this can take a minute or two on a large survey. Working...${_W_RST}\n"
    "$@" &
    local _swpid=$! _swelapsed=0 _swtimeout="${WAI_SEED_TIMEOUT:-180}"
    while kill -0 "$_swpid" 2>/dev/null; do
        sleep 1
        _swelapsed=$((_swelapsed + 1))
        printf "\r  ${_W_DIM}...still working (%ds elapsed)${_W_RST}" "$_swelapsed"
        if (( _swelapsed >= _swtimeout )); then
            printf "\n  ${_W_YLW}◇${_W_RST}  survey is taking longer than expected (${_swelapsed}s) — moving on; the session below picks up wherever it got to\n"
            kill "$_swpid" 2>/dev/null
            wait "$_swpid" 2>/dev/null
            unset _swpid _swelapsed _swtimeout
            return 124
        fi
    done
    wait "$_swpid"; local _swrc=$?
    printf "\r  %*s\r" 60 ""
    unset _swpid _swelapsed _swtimeout
    return $_swrc
}
if [[ -n "${_OPEN_PROMPT:-}" && "$TOOL" == "claude" && "$_IS_CONTINUATION" == "false" ]]; then
    # A positional prompt does NOT auto-submit in Claude Code 2.1.x (it lands in an
    # empty composer). Deliver it the reliable way — the SINGLE path shared by wcl and
    # the basher TUI: seed the prompt into a FRESH pinned session via -p, then resume
    # THAT exact id interactively. (Was: `claude "$prompt"` positional — never ran.)
    _we_headless=false
    for _a in "${_TOOL_ARGS[@]}"; do [[ "$_a" == "-p" || "$_a" == "--print" ]] && _we_headless=true; done
    if [[ "$_we_headless" == "false" ]]; then
        _we_sid="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || uuidgen 2>/dev/null \
                   || python3 -c 'import uuid;print(uuid.uuid4())' 2>/dev/null)"
        if [[ -n "$_we_sid" ]]; then
            _wai_seed_headless_run claude --session-id "$_we_sid" -p "$_OPEN_PROMPT" "${_TOOL_ARGS[@]}"
            printf "\n  ${_W_DIM}── new session · continuing interactively (Ctrl-D to return) ──${_W_RST}\n"
            claude --resume "$_we_sid" "${_TOOL_ARGS[@]}"
        else
            _wai_seed_headless_run claude -p "$_OPEN_PROMPT" "${_TOOL_ARGS[@]}"; claude -c "${_TOOL_ARGS[@]}"
        fi
    else
        claude -p "$_OPEN_PROMPT" "${_TOOL_ARGS[@]}"
    fi
    unset _we_headless _we_sid _a
elif [[ -n "${_OPEN_PROMPT:-}" && "$TOOL" != "claude" ]]; then
    # ── W3: APPEND the prompt, never PREPEND ─────────────────────────────────
    # Non-claude tools take the prompt positionally, and prepending it SHADOWED
    # the real first argument — silently, on every launch with a non-empty backlog:
    #   codex:  `codex "<prompt>" resume --last`  -> prompt eats the subcommand
    #   uvx:    `uvx "<prompt>" code-puppy`       -> uvx resolves the prompt as a
    #                                                PACKAGE NAME
    # Both were silent no-work launches. Appending puts the prompt where these
    # tools actually expect it (`uvx code-puppy "<prompt>"`) and leaves the
    # subcommand intact.
    "$TOOL" "${_TOOL_ARGS[@]}" "$_OPEN_PROMPT"
else
    # Covers the plain launch AND every continuation: the args (including
    # --resume/-c) reach the tool untouched, with no --session-id and no -p seed.
    "$TOOL" "${_TOOL_ARGS[@]}"
fi

# ── Post-exit: reset Zellij tab to open-box icon ─────────────────────────────
if [[ -n "${ZELLIJ_PANE_ID:-}" && "$TOOL" == "claude" ]]; then
    rm -f "/tmp/claude-sessions/active-${ZELLIJ_PANE_ID}"
    command -v _zellij_tab_prefix >/dev/null 2>&1 || _zellij_tab_prefix() { return 0; }
    command -v _basher_tab_label >/dev/null 2>&1 || _basher_tab_label() { local g='□'; [ "$1" = lens ] && g='◆'; local n="${2:0:$((8-${#3}))}"; printf '%s %s%s' "$g" "$n" "${3:-}"; }
    command -v _basher_spoke_name >/dev/null 2>&1 || _basher_spoke_name() { local r="${1:-}"; r="${r%/.worktrees/*}"; basename "$r"; }
    # Idle shell now (claude exited): set □ via rename-tab-by-id so it lands on THIS
    # pane's tab (not the focused one). The shell PROMPT_COMMAND keeps it □ thereafter.
    # Worktree-aware name + "-N" kept whole as the suffix — same geometry as every
    # other writer, so the idle □ tab agrees with the launch/notify tabs.
    _exit_project=$(_basher_spoke_name "$PROJECT_DIR")
    _exit_panes=$(zellij action list-panes --json 2>/dev/null || echo "[]")
    _exit_idx=$(_zellij_tab_prefix "$_exit_panes" || true)
    _exit_tabid=$(printf '%s' "$_exit_panes" | jq -r ".[]|select(.id==${ZELLIJ_PANE_ID} and .is_floating==false)|.tab_id // empty" 2>/dev/null)
    _exit_lbl="$(_basher_tab_label inactive "$_exit_project" "${_exit_idx:+-$_exit_idx}")"
    if [ -n "$_exit_tabid" ]; then
        zellij action rename-tab-by-id "$_exit_tabid" "$_exit_lbl" >/dev/null 2>&1 || true
    else
        zellij action rename-tab "$_exit_lbl" >/dev/null 2>&1 || true
    fi
    unset _exit_project _exit_idx _exit_panes _exit_tabid _exit_lbl
fi

# ── 7. Post-exit: initiative claim cleanup ───────────────────────────────────
# Releases a framework initiative claim when the session left no outstanding goals.
if [[ -n "${_CM_SEL_INITIATIVE:-}" && -n "${_CM_CLAIM_SESSION:-}" ]]; then
    _cm_exit_fw="$(basher_wai_master_root "$PROJECT_DIR")"
    _cm_exit_brief="$_cm_exit_fw/WAI-Harness/spoke/local/wakeup-brief.json"
    [[ -f "$_cm_exit_brief" ]] || _cm_exit_brief="$_cm_exit_fw/WAI-Spoke/wakeup-brief.json"
    # Regenerate framework brief so goal state is fresh
    _cm_exit_gen="$_cm_exit_fw/WAI-Harness/spoke/managed/tools/generate_wakeup_brief.py"
    [[ -f "$_cm_exit_gen" ]] && python3 "$_cm_exit_gen" --spoke-path "$_cm_exit_fw" 2>/dev/null
    # Check if any open sessions still have goals for this initiative
    _cm_exit_goals=$(python3 - "$_cm_exit_brief" "$_CM_SEL_INITIATIVE" <<'PYEOF' 2>/dev/null
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    iid = sys.argv[2]
    for s in d.get("continuation_menu", {}).get("open_sessions", []):
        if s.get("initiative_id") == iid and s.get("goals"):
            print("yes"); sys.exit(0)
    print("no")
except Exception:
    print("no")
PYEOF
    )
    if [[ "${_cm_exit_goals:-no}" == "no" ]]; then
        printf "  ${_W_DIM}Initiative %s: no outstanding goals — releasing claim${_W_RST}\n" "$_CM_SEL_INITIATIVE"
        python3 "$_cm_exit_fw/tools/initiative_lease.py" release \
            "$_CM_SEL_INITIATIVE" "$_CM_CLAIM_SESSION" 2>/dev/null || true
        if [[ -n "${_CM_WORKTREE_PATH:-}" && -d "${_CM_WORKTREE_PATH}" ]]; then
            git -C "$_cm_exit_fw" worktree remove --force "$_CM_WORKTREE_PATH" 2>/dev/null \
                && printf "  ${_W_DIM}Worktree removed: %s${_W_RST}\n" "$_CM_WORKTREE_PATH" || true
        fi
    else
        printf "  ${_W_DIM}Initiative %s has outstanding goals — claim retained for next session${_W_RST}\n" "$_CM_SEL_INITIATIVE"
    fi
    unset _cm_exit_fw _cm_exit_brief _cm_exit_gen _cm_exit_goals
fi

# ── 8. Post-exit: regenerate brief for next session ─────────────────────────
# Resolve via the PATH SHIM first, spoke-local copy only as a fallback.
# This was `[[ -f "$PROJECT_DIR/wai-exit.sh" ]] && "$PROJECT_DIR/wai-exit.sh"` —
# the same root-relative fork bug just fixed in the TUI. It runs whatever stale
# copy happens to sit at a spoke's root, and 2 spokes have NO local copy at all,
# so for them the closeout never ran — silently, with no way to notice. The shim
# is the one canonical entry point; the local copy is legacy.
_WAI_EXIT_BIN="$(command -v wai-exit 2>/dev/null)"
if [[ -n "$_WAI_EXIT_BIN" ]]; then
    "$_WAI_EXIT_BIN"
elif [[ -f "$PROJECT_DIR/wai-exit.sh" ]]; then
    "$PROJECT_DIR/wai-exit.sh"
else
    # Never fail silently: a missing closeout means no brief regen and no state
    # capture for the next session, which is invisible until someone wakes up cold.
    _wai_warn "wai-exit" "not found (no 'wai-exit' in PATH, no ${PROJECT_DIR}/wai-exit.sh) — closeout did NOT run"
fi
unset _WAI_EXIT_BIN
