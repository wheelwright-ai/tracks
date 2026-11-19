#!/usr/bin/env bash
# B-024: clean-clone test. Clone this repo's HEAD into a temp directory (so no
# ignored or local file comes along: lugs/, runtime/, .harness/, WAI-Spoke/ and
# anything uncommitted are all absent), run tests/run_all.sh there, and fail if
# the run fails or leaves the clone's git status dirty.
# Not part of run_all.sh itself: it runs run_all.sh, so listing it there would recurse.
# Usage: bash tests/clean_clone.sh
set -u
root="$(cd "$(dirname "$0")/.." && pwd)" || exit 2
export PYTHONDONTWRITEBYTECODE=1

sha=$(git -C "$root" rev-parse HEAD) || { echo "FAIL: not a git repo: $root" >&2; exit 2; }
tmp=$(mktemp -d "${TMPDIR:-/tmp}/clean-clone.XXXXXX") || exit 2
trap 'rm -rf "$tmp"' EXIT   # our own mktemp dir, removed on exit

clone="$tmp/clone"
git clone --quiet --no-checkout "$root" "$clone" || { echo "FAIL: git clone failed" >&2; exit 1; }
git -C "$clone" checkout --quiet --detach "$sha" || { echo "FAIL: cannot check out $sha in the clone" >&2; exit 1; }
echo "clean clone of $sha in $clone"

# Local-only dirs must not exist in a clean clone; if one does, it is tracked (or the clone is not clean).
for d in lugs runtime .harness WAI-Spoke; do
  if [ -e "$clone/$d" ]; then echo "NOTE: $d/ is present in the clone (tracked content)"; fi
done

fail=0
( cd "$clone" && bash tests/run_all.sh </dev/null )
rc=$?
if [ $rc -ne 0 ]; then echo "FAIL: tests/run_all.sh exited $rc in the clean clone" >&2; fail=1; fi

dirty=$(git -C "$clone" status --porcelain)
if [ -n "$dirty" ]; then
  echo "FAIL: the run left the clone's git status dirty:" >&2
  echo "$dirty" >&2
  fail=1
fi

[ $fail -eq 0 ] && echo "PASS: full suite passes from a clean clone of $sha and leaves it clean"
exit $fail
