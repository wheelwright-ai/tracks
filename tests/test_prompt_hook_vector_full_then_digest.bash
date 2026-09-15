#!/usr/bin/env bash
# The per-turn injection must stay on the rail while costing far less.
#
# MEASURED 2026-08-21 (basher session-20260821-1724, 10 turns): the per-turn
# payload was 22,416 B / ~5,639 tok, and turn 1 vs turn 10 were 99.9% byte-identical
# (22,398 of 22,416 B). ~56,000 tokens per session re-sending bodies already in
# context. Cost has no failure mode, which is why it survived unnoticed.
#
# The fix must NOT reintroduce what s137 fixed. s137's finding was ABSENCE from the
# per-turn rail (the graph was rendered once at SessionStart and never again, and
# adherence collapsed). So these tests care about two things at once: the payload
# gets small, AND the contract stays present on every single turn.
set -uo pipefail
ROOT="${BASHER_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HOOK="$ROOT/.claude/hooks/user-prompt-submit.sh"
MARK="$ROOT/WAI-Harness/spoke/local/runtime/tgv-sent"
FAILED=0
_ok()   { printf '  ok   %s\n' "$1"; }
_fail() { printf '  FAIL %s\n' "$1"; FAILED=1; }

echo "── per-turn injection: full once, digest after ──────────────────────"
[[ -f "$HOOK" ]] || { _fail "hook not found: $HOOK"; exit 1; }
command -v python3 >/dev/null || { _ok "python3 absent — skipping"; exit 0; }

TMPD=$(mktemp -d); trap 'rm -rf "$TMPD"; [[ -n "${_SAVED:-}" ]] && printf "%s" "$_SAVED" > "$MARK"' EXIT
# Preserve the live marker: this test must not disturb the running session's state.
_SAVED=""; [[ -f "$MARK" ]] && _SAVED="$(cat "$MARK")"

# CLAUDE_PROJECT_DIR is what the hook resolves PROJECT_DIR (and therefore the
# marker path) from. Without pinning it, running another spoke's hook via
# BASHER_DIR still read THIS tree's marker — the hook under test and the state it
# reads came from different trees, and the guard reported failures that were
# entirely its own. A portable guard has to carry its tree with it.
run() { # $1 = unique prompt, $2 = out name  -> stdout file path
    local out="$TMPD/$2"
    printf '{"prompt":"%s","session_id":"regression-test-session"}' "$1" \
        | CLAUDE_PROJECT_DIR="$ROOT" WAI_LOCAL="$ROOT/WAI-Harness/spoke/local" \
          bash "$HOOK" 2>/dev/null > "$out"
    printf '%s' "$out"
}

rm -f "$MARK"
T1=$(run "probe-one" t1); T2=$(run "probe-two" t2); T3=$(run "probe-three" t3)

# 1. Cold turn sends the bodies.
grep -q 'state="full"' "$T1" && _ok "turn 1 sends the vector in FULL" \
    || _fail "turn 1 did not send state=\"full\""
[[ -f "$MARK" ]] && _ok "marker written so later turns know" || _fail "no marker written"

# 2. Warm turns send a digest instead.
grep -q 'state="in-force-unchanged"' "$T2" && _ok "turn 2 sends the digest" \
    || _fail "turn 2 did not send the unchanged digest"
grep -q 'state="in-force-unchanged"' "$T3" && _ok "turn 3 still on the rail" \
    || _fail "turn 3 dropped the vector block entirely"

# 3. The saving is real and large.
S1=$(wc -c < "$T1"); S2=$(wc -c < "$T2")
PCT=$(( 100 * (S1 - S2) / S1 ))
if (( PCT >= 70 )); then _ok "warm turn is ${PCT}% smaller (${S1} -> ${S2} B)"
else _fail "warm turn only ${PCT}% smaller (${S1} -> ${S2} B) — expected >=70%"; fi

# 4. THE THING THAT MUST NOT BE LOST. Presence on every turn is the s137 fix;
#    a cheaper payload that drops the contract is a regression, not an optimisation.
for f in "$T1" "$T2" "$T3"; do
    n=$(basename "$f")
    grep -q "STATUSLINE (NON-WAIVABLE" "$f" || _fail "$n lost the statusline obligation"
    grep -q "RICH ENTRY" "$f"               || _fail "$n lost the track-buffer obligation"
    grep -q "<wai-voice-contract>" "$f"     || _fail "$n lost the Tier A voice contract"
    grep -q "<tastegraph-vector"  "$f"      || _fail "$n has no vector block at all"
done
_ok "track obligations + Tier A contract present on every turn"

# 5. Volatile block last, so the byte-stable region stays contiguous (cache).
LAST=$(grep -oE "^<[a-z-]+" "$T2" | tail -1)
[[ "$LAST" == "<wai-track-turn" ]] && _ok "volatile block emitted LAST (cache ordering)" \
    || _fail "last block is '$LAST', expected <wai-track-turn"

# 6. Changed preferences must re-send the bodies, not silently keep the stale digest.
printf 'regression-test-session:0000000000' > "$MARK"
T4=$(run "probe-four" t4)
grep -q 'state="CHANGED-resending-full"' "$T4" \
    && _ok "a changed digest re-sends the FULL bodies" \
    || _fail "changed digest did not trigger a full re-send — stale prefs would go silent"

exit $FAILED
