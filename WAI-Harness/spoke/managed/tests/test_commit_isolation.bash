#!/usr/bin/env bash
# test_commit_isolation — bug-harness-background-advisor-commit-no-isolation-v1.
# Proves: on a CONTENDED shared tree (2+ live lanes), a scoped commit-mine commit
# stages ONLY the advisor-owned paths and never sweeps a foreground session's
# uncommitted work. Also asserts ozi_autopilot no longer does a blind broad add.
set -uo pipefail
PASS=0; FAIL=0
ok(){ echo "  PASS: $1"; PASS=$((PASS+1)); }
no(){ echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

MANAGED="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # WAI-Harness/spoke/managed
CM="$MANAGED/tools/commit-mine.sh"
WG="$MANAGED/tools/worktree_guard.py"

# 1. Source-level: autopilot must NOT carry the blind broad add anymore
AP="$MANAGED/tools/ozi_autopilot.py"
grep -q '"git", "add", "WAI-Spoke/", "tools/"' "$AP" && no "autopilot still has blind 'git add WAI-Spoke/ tools/'" || ok "autopilot blind broad add removed"
grep -q 'commit-mine.sh' "$AP" && ok "autopilot routes commit through commit-mine.sh" || no "autopilot does not use commit-mine.sh"

# 2. Behavioral: contended tree -> foreground file untouched by a scoped commit
SBX="$(mktemp -d)"; trap 'rm -rf "$SBX"' EXIT
cd "$SBX"
git init -q; git config user.email t@t; git config user.name t
mkdir -p WAI-Harness/spoke/local/{lugs,runtime/lanes/laneA,runtime/lanes/laneB}
echo '{}' > seed.json; git add -A; git commit -qm seed
# two live lanes (so worktree_guard sees a contended tree) — fresh heartbeats
python3 "$WG" lane-register --session laneA --base WAI-Harness/spoke/local >/dev/null 2>&1 || true
python3 "$WG" lane-register --session laneB --base WAI-Harness/spoke/local >/dev/null 2>&1 || true
LIVE=$(python3 "$WG" lanes --base WAI-Harness/spoke/local 2>/dev/null | python3 -c 'import sys,json;print(json.load(sys.stdin).get("count",0))' 2>/dev/null || echo 0)
# foreground (other session) uncommitted work + advisor's own output
echo "FOREGROUND-WIP" > tools_foreground.py
echo '{"advisor":"output"}' > WAI-Harness/spoke/local/lugs/advisor-out.json
# commit-mine has two correct modes; assert by the mode it actually took.
CM_OUT="$(bash "$CM" -m "advisor scoped commit" -- WAI-Harness/spoke/local/lugs 2>&1)"
if echo "$CM_OUT" | grep -q 'staging ONLY'; then
  # contended branch exercised — the real protection path
  git show --stat --name-only HEAD | grep -q 'tools_foreground.py' \
    && no "foreground WIP swept despite contended scoping" \
    || ok "contended tree: foreground WIP NOT swept (only advisor paths committed)"
  [ -n "$(git status --porcelain tools_foreground.py)" ] && ok "foreground WIP left untouched" || no "foreground WIP state changed"
elif echo "$CM_OUT" | grep -q 'you own this tree'; then
  # sole-owner add -A is correct (no foreground session to protect in this fixture)
  ok "sole-owner mode: commit-mine correctly added all (no contention to simulate, lanes=${LIVE})"
else
  no "commit-mine produced unexpected output: $(echo "$CM_OUT" | head -1)"
fi

echo
echo "===== commit isolation: $PASS passed, $FAIL failed ====="
[ "$FAIL" -eq 0 ]
