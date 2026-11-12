#!/usr/bin/env bash
# Run every tests/ check; exit non-zero if any fails (B-012).
# Checks: validate_rules.sh validate_samples.sh stranded_ideas.sh wake_from_track.sh viewer_drop.py
# critical_paths.sh (B-011) wraps these same checks as the closeout gate.
# Usage: bash tests/run_all.sh
set -u
cd "$(dirname "$0")/.." || exit 2
export PYTHONDONTWRITEBYTECODE=1
fail=0
for t in validate_rules.sh validate_samples.sh stranded_ideas.sh wake_from_track.sh viewer_drop.py; do
  echo "== $t"
  case "$t" in
    *.py) python3 -B "tests/$t" </dev/null ;;
    *)    bash "tests/$t" </dev/null ;;
  esac
  rc=$?
  if [ $rc -ne 0 ]; then echo "FAILED: $t (exit $rc)" >&2; fail=1; fi
done
[ $fail -eq 0 ] && echo "ALL PASS" || echo "SOME CHECKS FAILED" >&2
exit $fail
