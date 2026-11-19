#!/usr/bin/env bash
# B-023: repo hygiene. Scout status files are ignored and untracked, the agent
# docs carry no GitNexus block, and running the scouts leaves git status unchanged.
# Usage: bash tests/repo_hygiene.sh
set -u
cd "$(dirname "$0")/.." || exit 2
export PYTHONDONTWRITEBYTECODE=1
fail=0
bad() { echo "FAIL: $*" >&2; fail=1; }

# 1. .gitignore ignores .wheel/scouts/*/status.json (checked against a path that need not exist)
probe=".wheel/scouts/hygiene-probe/status.json"
git check-ignore -q "$probe" || bad ".gitignore does not ignore .wheel/scouts/*/status.json"

# 2. git tracks no scout status file
tracked=$(git ls-files -- '.wheel/scouts/*/status.json')
[ -z "$tracked" ] || bad "tracked scout status file(s): $(echo "$tracked" | tr '\n' ' ')"

# 3. CLAUDE.md and AGENTS.md hold no gitnexus:start marker
for f in CLAUDE.md AGENTS.md; do
  if [ -f "$f" ] && grep -q 'gitnexus:start' "$f"; then bad "$f holds a gitnexus:start marker"; fi
done

# 4. a scout run (recording its results) leaves git status unchanged
before=$(git status --porcelain)
python3 -B .wheel/hooks/scouts.py run --record </dev/null >/dev/null 2>&1
after=$(git status --porcelain)
[ "$before" = "$after" ] || bad "a scout run changed git status"

[ $fail -eq 0 ] && echo "PASS: scout status ignored and untracked; no gitnexus block; scout run leaves git status unchanged"
exit $fail
