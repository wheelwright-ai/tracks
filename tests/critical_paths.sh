#!/usr/bin/env bash
# CRITICAL-PATHS quality gate (B-011): real, deterministic checks over this
# spoke's critical paths. /wai-closeout hard-blocks on red; never fake green.
# Paths and the assertions behind each:
#   1. track validator   validate_samples.sh (every sample valid, bad input rejected)
#                        validate_rules.sh   (each spec rule has a failing fixture; samples pass)
#   2. viewer            viewer_drop.py      (drop a sample on viewer/index.html: turns,
#                        decisions, open items shown, no page errors; needs playwright+chromium)
#   3. session wake      wake_from_track.sh  (newest track's open items/decisions surface)
#   4. stranded ideas    stranded_ideas.sh   (listed with line numbers, no writes)
# Usage: bash tests/critical_paths.sh
set -u
cd "$(dirname "$0")/.." || exit 2
export PYTHONDONTWRITEBYTECODE=1
fail=0
run() { # label script
  echo "== [$1] $2"
  case "$2" in
    *.py) python3 -B "tests/$2" </dev/null ;;
    *)    bash "tests/$2" </dev/null ;;
  esac
  rc=$?
  [ $rc -eq 0 ] || { echo "FAILED: [$1] $2 (exit $rc)" >&2; fail=1; }
}
run validator validate_samples.sh
run validator validate_rules.sh
run viewer viewer_drop.py
run wake wake_from_track.sh
run stranded-ideas stranded_ideas.sh
[ $fail -eq 0 ] && echo "CRITICAL-PATHS: PASS" || echo "CRITICAL-PATHS: FAIL" >&2
exit $fail
