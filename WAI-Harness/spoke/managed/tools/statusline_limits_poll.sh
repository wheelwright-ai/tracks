#!/usr/bin/env bash
# Persist the rate-limit numbers Claude Code hands the statusline, so the budget gate
# can read a FIRST-PARTY reading instead of a guess.
#
# OPERATOR 2026-08-15: "cant you get the limits from claude diectly we render it in the
# status line maybe those can just poll back their reported values to navigator"
#
# He was right, and it closes a hole three other approaches could not:
#
#   - no Anthropic API exposes subscription headroom
#   - a hand-typed file reached 583 HOURS stale while still being read as current
#   - Playwright hit an endless human-verification challenge, correctly
#   - an anti-detect browser would risk the account to save ten seconds
#
# Meanwhile Claude Code was already passing the exact numbers to the statusline on stdin,
# every refresh, and statusline.sh was rendering them and throwing them away:
#
#   .rate_limits.five_hour.used_percentage    .rate_limits.five_hour.resets_at
#   .rate_limits.seven_day.used_percentage    .rate_limits.seven_day.resets_at
#
# USAGE. From statusline.sh, after the values are parsed, pass the ALREADY-READ payload:
#
#   printf '%s' "$input" | bash .../statusline_limits_poll.sh "$repo_root"
#
# It costs one small file write per refresh and never blocks the statusline: every failure
# path exits 0 silently, because a broken poller must not stop the operator seeing his own
# status line.
#
# WRITES REMAINING, NOT USED. The payload reports used_percentage; kernel.budget stores
# remaining. Converting here keeps the inversion in exactly one place.
set -uo pipefail

ROOT="${1:-}"
[[ -z "$ROOT" || ! -d "$ROOT" ]] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

payload="$(cat)"
[[ -z "$payload" ]] && exit 0

five_used=$(printf '%s' "$payload" | jq -r '.rate_limits.five_hour.used_percentage // empty' 2>/dev/null)
week_used=$(printf '%s' "$payload" | jq -r '.rate_limits.seven_day.used_percentage // empty' 2>/dev/null)
five_ts=$(printf '%s'   "$payload" | jq -r '.rate_limits.five_hour.resets_at // empty' 2>/dev/null)
week_ts=$(printf '%s'   "$payload" | jq -r '.rate_limits.seven_day.resets_at // empty' 2>/dev/null)

# A payload carrying NEITHER window is not a zero reading, it is no reading. Writing 100%
# remaining here would open the budget gate on the absence of evidence, which is the exact
# failure this whole line of work exists to stop.
[[ -z "$five_used" && -z "$week_used" ]] && exit 0

out="$ROOT/WAI-Harness/spoke/local/runtime/anthropic-usage-observed.json"
mkdir -p "$(dirname "$out")" 2>/dev/null || exit 0
tmp="$out.$$"

{
  printf '{\n'
  printf '  "observed_at": "%s",\n' "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"
  printf '  "source": "claude.ai statusline payload (first-party, polled by statusline_limits_poll.sh)",\n'
  printf '  "windows": {\n'
  first=1
  if [[ -n "$five_used" ]]; then
    printf '    "5h session": { "pct_left": %s, "resets_at": "%s" }' \
      "$(awk -v u="$five_used" 'BEGIN{printf "%.1f", 100-u}')" "$five_ts"
    first=0
  fi
  if [[ -n "$week_used" ]]; then
    [[ $first -eq 0 ]] && printf ',\n'
    printf '    "weekly all-model": { "pct_left": %s, "resets_at": "%s" }' \
      "$(awk -v u="$week_used" 'BEGIN{printf "%.1f", 100-u}')" "$week_ts"
  fi
  printf '\n  }\n}\n'
} > "$tmp" 2>/dev/null || { rm -f "$tmp"; exit 0; }

# Atomic, because the budget gate may read this file at any moment and a half-written
# JSON object is read as a corrupt guard -- which closes the gate rather than opening it,
# but still costs a needless refusal.
mv -f "$tmp" "$out" 2>/dev/null || rm -f "$tmp"
exit 0
