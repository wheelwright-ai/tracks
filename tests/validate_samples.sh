#!/usr/bin/env bash
# Run the track validator on every sample; exit non-zero on any failure.
# Also proves the validator can fail: a deliberately bad track must be rejected.
# Usage: bash tests/validate_samples.sh
set -u
cd "$(dirname "$0")/.." || exit 2
shopt -s nullglob
samples=(samples/*.jsonl)
if [ "${#samples[@]}" -eq 0 ]; then echo "FAIL: no samples found" >&2; exit 1; fi
python3 tools/validate_track.py "${samples[@]}" || { echo "FAIL: a sample is invalid" >&2; exit 1; }
bad=$(mktemp)
echo '{"turn":"x","phase":"nope"}' > "$bad"
if python3 tools/validate_track.py "$bad" >/dev/null; then
  echo "FAIL: validator accepted a bad track" >&2; exit 1
fi
echo "PASS: ${#samples[@]} samples valid; validator rejects bad input"
