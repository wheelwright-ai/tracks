#!/bin/bash
#
# WAI Stop Hook — Test Runner
# Runs tests after Claude finishes a response that modified source files.
# Adapts to the project's test framework automatically.
#
# Must exit 0 on success or no-op. Exit 1 only for actual test failures.
# Never exit non-zero for infrastructure errors — that blocks Claude.
#

set -o pipefail 2>/dev/null || true

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

# Bail early if not a git repo
git -C "$PROJECT_DIR" rev-parse --git-dir >/dev/null 2>&1 || exit 0

# Detect changed files (gracefully handle missing HEAD, empty repos, etc.)
CHANGED=$(git -C "$PROJECT_DIR" diff --name-only HEAD 2>/dev/null || true)
STAGED=$(git -C "$PROJECT_DIR" diff --cached --name-only 2>/dev/null || true)
ALL_CHANGED="${CHANGED}${STAGED}"

# Skip if nothing changed
[[ -z "$ALL_CHANGED" ]] && exit 0

# Detect test framework and run
cd "$PROJECT_DIR" || exit 0

# Count Python test files under a directory.
_count_py_tests() {
  find "$1" -type f \( -name 'test_*.py' -o -name '*_test.py' \) 2>/dev/null | wc -l
}

# --- Python suite discovery --------------------------------------------------
# This hook ships to every spoke, and spokes disagree about where the suite
# lives. Most keep it at ./tests. Some keep only scripts there and hold the
# real suite in a nested package (mywheel: ./tests holds a single .sh, while
# the 147-file suite lives under WAI-Harness/spoke/managed/tests). Hardcoding
# a second path would just relocate the narrow-surface bug, so DISCOVER the
# suite instead.
#
# Rule: a "suite root" is a directory named tests/ or test/ that actually
# contains Python test files — the old `[[ -d tests ]]` guard checked only
# that the directory EXISTS, which is why mywheel's script-only ./tests
# sailed through it. Prefer ./tests or ./test when it qualifies (the common
# case, and cheap). Otherwise take the DOMINANT root: most test files wins,
# ties broken by shallowest, then by the sorted order of find — so the pick
# is deterministic rather than filesystem-order-dependent.
#
# Deliberately NOT "run every test root found": a repo can vendor a foreign
# component whose tests are not this project's suite and do not run here
# (mywheel vendors WAI-Harness/hub/managed/tests, which is red on collection
# by itself). Dragging those in would block every edit for reasons the editor
# cannot fix. The dominant root is this project's suite.
discover_python_suite() {
  local d count depth best="" best_count=0 best_depth=99

  for d in tests test; do
    if [[ -d "$d" ]] && (( $(_count_py_tests "$d") > 0 )); then
      printf '%s\n' "$d"
      return 0
    fi
  done

  # The VENDORED-HARNESS exclusion. WAI-Harness/*/managed/tests is the harness's own
  # suite. On the harness MASTER (mywheel, is_master:true) that suite IS this project's
  # suite and must be discovered. In a CONSUMING SPOKE it is vendored — master's tests,
  # shipped in, testing master's tools against a tree that has no hub. It is red there by
  # construction and is not the spoke's to fix, so running it would block every edit in
  # that spoke for a failure its author cannot repair.
  #
  # Found 2026-07-14 the hard way: 4.6.7 armed this gate fleet-wide, and 6 registered
  # spokes have no ./tests of their own — they would have discovered the vendored suite
  # (97 failed / 23 errors there vs 1204/0 on master) and blocked on every .py edit.
  #
  # is_master is the exact discriminator and already exists in the MANIFEST. No new state.
  local _vendor_prune=()
  if [[ -f WAI-Harness/spoke/managed/MANIFEST.json ]] \
     && ! grep -q '"is_master"[[:space:]]*:[[:space:]]*true' WAI-Harness/spoke/managed/MANIFEST.json 2>/dev/null; then
    _vendor_prune=( -not -path './WAI-Harness/*' )
  fi

  while IFS= read -r d; do
    count=$(_count_py_tests "$d")
    (( count > 0 )) || continue
    depth=$(awk -F/ '{print NF}' <<<"$d")
    if (( count > best_count )) || { (( count == best_count )) && (( depth < best_depth )); }; then
      best="$d"; best_count=$count; best_depth=$depth
    fi
  done < <(find . -maxdepth 6 -type d \( -name tests -o -name test \) \
             -not -path '*/.git/*' -not -path '*/node_modules/*' \
             -not -path '*/.venv/*' -not -path '*/venv/*' \
             -not -path '*/site-packages/*' -not -path '*/.worktrees/*' \
             "${_vendor_prune[@]}" \
             2>/dev/null | sort)

  [[ -n "$best" ]] && printf '%s\n' "$best"
}

FAIL_MSG="Tests failed after your last change. Fix before continuing."

if [[ -f "package.json" ]] && echo "$ALL_CHANGED" | grep -qE '\.(js|ts|jsx|tsx)$'; then
  # Node.js project with JS/TS changes
  if command -v bun &>/dev/null && [[ -f "bun.lock" ]]; then
    RESULT=$(bun test 2>&1); EXIT_CODE=$?
  elif command -v npm &>/dev/null; then
    RESULT=$(npm test 2>&1); EXIT_CODE=$?
  else
    exit 0
  fi
elif echo "$ALL_CHANGED" | grep -qE '\.py$'; then
  # Python project with Python changes
  SUITE=$(discover_python_suite)
  [[ -n "$SUITE" ]] || exit 0   # no Python suite in this repo — nothing to gate
  # BOUNDED (2026-07-23, s117): a Stop hook that outruns Claude Code's per-hook budget
  # surfaces as "Stop hook error: Failed with non-blocking status code" on EVERY turn —
  # noise, not a verdict. basher's suite is ~43s and this hook was unbounded, so a slow
  # run (or the same hook double-registered in project + global settings) blew the budget.
  # Per this file's own contract ("never exit non-zero for infrastructure errors"), a
  # timeout is infra: bound the run and treat a timeout as a NO-OP. Raise
  # STOP_TEST_TIMEOUT to re-widen. pytest never emits 124; only `timeout` does, so it
  # can't mask a verdict.
  #
  # THIS BLOCK USED TO SAY "the real gate is pre-commit-gate.sh (blocks red-on-main),
  # so degrading to silence loses nothing". NO FILE OF THAT NAME EXISTS ANYWHERE IN THE
  # TREE (verified 2026-07-30 — the only occurrences are this comment and its copies).
  # A commit gate DOES exist: core.hooksPath=.githooks, and .githooks/pre-commit blocks
  # on manifest drift, secrets, structure health and lug validity. It has NO test
  # dimension — grep pytest there returns nothing. So the justification for degrading
  # quietly was load-bearing on a gate that does not test, and this hook is in fact the
  # ONLY thing between a red suite and nobody knowing. That is precisely how three real
  # failures lived undetected. Do not re-weaken this on the assumption that something
  # downstream catches it — see change-commit-time-test-gate-does-not-exist-v1.
  # HEADROOM, NOT A TIGHT FIT (s117 2026-07-24). The bound was first set to 45s off a
  # 43s measurement. The suite then grew to 47s and the gate began timing out on EVERY
  # run — reporting success while never executing a single test. A bound sized to the
  # CURRENT runtime is a gate with an expiry date; give it real headroom and make the
  # timeout LOUD (below) so growth degrades visibly instead of silently.
  RESULT=$(timeout "${STOP_TEST_TIMEOUT:-420}" python3 -m pytest "$SUITE" -x -q --tb=short 2>&1); EXIT_CODE=$?

  # pytest exit codes:
  #   0 all passed | 1 tests failed | 2 collection error / interrupted
  #   3 internal error | 4 usage error | 5 no tests collected
  #
  # 5 is NOT a failure. "Nothing to run here" is not "the suite is red", and
  # blocking on it would brick every .py edit in a repo whose discovered dir
  # holds no COLLECTIBLE tests (files can match test_*.py yet define no tests).
  # This cannot mask a genuinely broken suite: a suite that is broken rather
  # than absent fails during COLLECTION and exits 2 — which still blocks below.
  # Distinguishing 2 from 5 is exactly what keeps "no tests" honest.
  #
  # 3 and 4 are pytest infrastructure/usage errors, not verdicts about the
  # code. Per this hook's contract they must never block Claude.
  case $EXIT_CODE in
    5) exit 0 ;;
    3|4) exit 0 ;;
    124)
      # A TIMEOUT MUST BE LOUD, NEVER SILENT. This was a bare `exit 0`, which meant a
      # gate that had quietly stopped running still reported green — the exact
      # green-washing hole pre-commit-gate.sh was written to close. Still exit 0 (the
      # contract forbids blocking on infra), but SAY the suite did not run.
      # ...and LOUD means it reaches a READER. This block wrote to stdout and exited 0,
      # which the harness discards entirely — so the third occurrence of this bug ran
      # undetected: the bound was 90s against a 128s suite, meaning the gate timed out
      # on EVERY turn and reported success while three real failures sat in the suite.
      # Twice before (45s vs 43s, then vs 47s) the same undersized-bound failure was
      # found and patched with a slightly bigger number; a bound sized to today's
      # runtime always expires. MEASUREMENTS (2026-07-30): 138s on an idle machine, 214s
      # while an autopilot round held the box. The bound must clear the LOADED figure,
      # not the idle one — an earlier note here claimed 2.3x headroom by sizing against
      # the idle number alone, which was really 1.4x. 420s is ~2x the loaded measurement.
      # If this fires again, raise the bound AND record the new measurement here.
      {
        echo "<test-gate-not-run>"
        echo "Test gate TIMED OUT after ${STOP_TEST_TIMEOUT:-420}s — the suite did NOT run; this turn is UNVERIFIED."
        echo "Raise STOP_TEST_TIMEOUT or run: python3 -m pytest ${SUITE} -q"
        echo "</test-gate-not-run>"
      } | tee /dev/stderr
      exit 0 ;;
    2) FAIL_MSG="Test collection FAILED after your last change (pytest exit 2 — broken import or conftest). The suite could not run. Fix before continuing." ;;
  esac
elif echo "$ALL_CHANGED" | grep -qE '\.rs$'; then
  # Rust project
  RESULT=$(cargo test 2>&1); EXIT_CODE=$?
else
  exit 0
fi

if [[ $EXIT_CODE -ne 0 ]]; then
  # Emit on BOTH streams. Stop hooks that exit non-zero are reported to the
  # operator as "Failed with non-blocking status code: No stderr output" and the
  # stdout payload is discarded — so a red suite surfaced as an opaque hook error
  # with the actual failing test nowhere in sight (measured s138: the suite had
  # been red on a stranded command template and the message never reached anyone).
  # A gate whose diagnostic does not reach a reader is a silent failure, which is
  # the exact class this hook exists to prevent.
  {
    echo "<test-failure>"
    echo "$FAIL_MSG"
    echo ""
    echo "$RESULT" | tail -20
    echo "</test-failure>"
  } | tee /dev/stderr
  exit 1
fi

exit 0
