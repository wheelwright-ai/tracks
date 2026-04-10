#!/bin/bash
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
CHANGED=$(git -C "$PROJECT_DIR" diff --name-only HEAD 2>/dev/null)
STAGED=$(git -C "$PROJECT_DIR" diff --cached --name-only 2>/dev/null)
ALL_CHANGED="$CHANGED$STAGED"
[[ -z "$ALL_CHANGED" ]] && exit 0
if [[ -f "$PROJECT_DIR/package.json" ]] && echo "$ALL_CHANGED" | grep -qE '\\.(js|ts|jsx|tsx)$'; then
  cd "$PROJECT_DIR"
  if command -v bun &>/dev/null && [[ -f "bun.lock" ]]; then
    RESULT=$(bun test 2>&1)
  elif command -v npm &>/dev/null; then
    RESULT=$(npm test 2>&1)
  else
    exit 0
  fi
elif echo "$ALL_CHANGED" | grep -qE '\\.py$'; then
  cd "$PROJECT_DIR"
  [[ -d "tests" ]] && RESULT=$(python3 -m pytest tests/ -x -q --tb=short 2>&1) || exit 0
else
  exit 0
fi
EXIT_CODE=$?
if [[ $EXIT_CODE -ne 0 ]]; then
  echo "<test-failure>"; echo "Tests failed. Fix before continuing."; echo "$RESULT" | tail -20; echo "</test-failure>"; exit 1
fi
exit 0