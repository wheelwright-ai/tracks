#!/usr/bin/env bash
# B-028: the worktree-no-uncommitted scout ignores the wheel's own lug store files.
# In a throwaway clone of HEAD (as clean_clone.sh does): the scout passes when
# only .wheel/backlog.jsonl is modified, and fails when any other file is
# modified or untracked.
# Usage: bash tests/scout_lugstore.sh
set -u
root="$(cd "$(dirname "$0")/.." && pwd)" || exit 2
export PYTHONDONTWRITEBYTECODE=1
sha=$(git -C "$root" rev-parse HEAD) || { echo "FAIL: not a git repo" >&2; exit 2; }
tmp=$(mktemp -d "${TMPDIR:-/tmp}/scout-lugstore.XXXXXX") || exit 2
trap 'rm -rf "$tmp"' EXIT
clone="$tmp/clone"
git clone --quiet --no-checkout "$root" "$clone" || { echo "FAIL: clone" >&2; exit 1; }
git -C "$clone" checkout --quiet --detach "$sha" || { echo "FAIL: checkout" >&2; exit 1; }

scout() { ( cd "$clone" && python3 -B .wheel/hooks/scouts.py run worktree-no-uncommitted </dev/null >/dev/null 2>&1 ); }
fail=0
expect() { # expect pass|fail label
  scout; rc=$?
  if [ "$1" = pass ] && [ $rc -ne 0 ]; then echo "FAIL: $2: scout failed, expected pass" >&2; fail=1
  elif [ "$1" = fail ] && [ $rc -eq 0 ]; then echo "FAIL: $2: scout passed, expected fail" >&2; fail=1
  else echo "ok: $2"; fi
}

expect pass "clean clone"
echo '{}' >> "$clone/.wheel/backlog.jsonl"
expect pass "only .wheel/backlog.jsonl modified"
echo x >> "$clone/README.md"
expect fail "README.md also modified"
git -C "$clone" show HEAD:README.md > "$clone/README.md"
expect pass "README.md restored"
echo x > "$clone/untracked_file.txt"
expect fail "an untracked file"
rm -f "$clone/untracked_file.txt"   # file we just made in our own temp clone
expect pass "untracked file removed"

[ $fail -eq 0 ] && echo "PASS: scout ignores the lug store files and still catches other changes"
exit $fail
