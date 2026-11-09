#!/usr/bin/env bash
# Prove tools/stranded_ideas.py lists open ideas with track+line and writes nothing.
set -u
cd "$(dirname "$0")/.." || exit 2
before=$(find . -path ./.git -prune -o -type f -printf '%p %T@\n' | sort | md5sum)
out=$(python3 -B tools/stranded_ideas.py samples/*.jsonl) || { echo "FAIL: script errored" >&2; exit 1; }
after=$(find . -path ./.git -prune -o -type f -printf '%p %T@\n' | sort | md5sum)
[ "$before" = "$after" ] || { echo "FAIL: tree changed" >&2; exit 1; }
echo "$out" | grep -Eq '^samples/coding-session.jsonl:[0-9]+  \[deferred\]  Write tests' || { echo "FAIL: expected coding item missing" >&2; exit 1; }
echo "$out" | grep -q 'Add a check that keeps the guide' || { echo "FAIL: v4 item missing" >&2; exit 1; }
echo "$out" | grep -q 'founder essay' && { echo "FAIL: intentional item listed" >&2; exit 1; }
echo "$out" | grep -q 'Which file is the source of truth' && { echo "FAIL: resolved item listed" >&2; exit 1; }
echo "PASS: stranded ideas listed with line numbers; no writes"
