#!/usr/bin/env bash
# Prove a session start in a test project prints the last track's open items and decisions.
# Fixture project: tests/fixtures/wake (two tracks; only the newest may be shown).
# Usage: bash tests/wake_from_track.sh
set -u
cd "$(dirname "$0")/.." || exit 2
fail=0
want() { grep -qF -- "$2" <<<"$1" || { echo "FAIL: missing '$2'" >&2; fail=1; }; }
nowant() { grep -qF -- "$2" <<<"$1" && { echo "FAIL: should not show '$2'" >&2; fail=1; }; }
proj=$PWD/tests/fixtures/wake
out=$(echo "{\"cwd\":\"$proj\",\"source\":\"startup\"}" | python3 .wheel/hooks/wake_from_track.py)
ctx=$(python3 -c 'import json,sys; d=json.load(sys.stdin)["hookSpecificOutput"]; assert d["hookEventName"]=="SessionStart"; print(d["additionalContext"])' <<<"$out") \
  || { echo "FAIL: not valid SessionStart JSON: $out" >&2; exit 1; }
want "$ctx" "Pick a migration tool"
want "$ctx" "Benchmark writes [deferred]"
want "$ctx" "Use sqlite for the cache"
want "$ctx" "Keep the schema flat"
nowant "$ctx" "OLD-OPEN"
nowant "$ctx" "OLD-DECISION"
# a project with no track: silent success
empty=$(mktemp -d)
[ -z "$(echo "{\"cwd\":\"$empty\"}" | python3 .wheel/hooks/wake_from_track.py)" ] || { echo "FAIL: output with no track" >&2; fail=1; }
# the hook is registered for SessionStart
grep -q wake_from_track.py .claude/settings.json || { echo "FAIL: hook not in .claude/settings.json" >&2; fail=1; }
# fixtures are valid tracks
python3 tools/validate_track.py tests/fixtures/wake/.wheel/tracks/*.jsonl >/dev/null || { echo "FAIL: fixture tracks invalid" >&2; fail=1; }
[ $fail -eq 0 ] && echo "PASS: session start prints last track's open items and decisions"
exit $fail
