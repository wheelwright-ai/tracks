#!/usr/bin/env bash
# B-024: Clean-clone test — full suite passes from a fresh clone, no ignored/local files.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git clone --quiet "$REPO" "$TMP/clone"

cd "$TMP/clone"

# Fail if the clone has any local/ignored dirt before running tests.
if ! git status --porcelain | grep -q .; then
  echo "CLEAN" >&2
  exit 1
fi

bash tests/run_all.sh </dev/null
