#!/usr/bin/env bash
# Prove spec and validator agree.
#  1. every rule ID in spec/track-format.md has a broken fixture tests/fixtures/Rnn-*.jsonl
#     that the validator rejects with that ID named;
#  2. the validator uses no rule ID the spec lacks, and checks every spec rule;
#  3. a known-good fixture and every sample pass.
# Usage: bash tests/validate_rules.sh
set -u
cd "$(dirname "$0")/.." || exit 2
shopt -s nullglob
fail=0
spec_ids=$(grep -oE '^\| R[0-9]+ ' spec/track-format.md | tr -d '| ' | sort -u)
[ -n "$spec_ids" ] || { echo "FAIL: no rule IDs in spec" >&2; exit 1; }
for id in $spec_ids; do
  fx=(tests/fixtures/$id-*.jsonl)
  if [ "${#fx[@]}" -eq 0 ]; then echo "FAIL: $id has no fixture" >&2; fail=1; continue; fi
  out=$(python3 tools/validate_track.py --check-name "${fx[0]}" 2>&1)
  rc=$?
  if [ $rc -eq 0 ] || ! grep -q "\[$id\]" <<<"$out"; then
    echo "FAIL: $id fixture ${fx[0]} not rejected with [$id]" >&2; echo "$out" >&2; fail=1
  fi
done
used=$(grep -oE '"R[0-9]+"' tools/validate_track.py | tr -d '"' | sort -u)
for id in $used; do
  grep -qx "$id" <<<"$spec_ids" || { echo "FAIL: validator uses $id, not in spec" >&2; fail=1; }
done
for id in $spec_ids; do
  grep -qx "$id" <<<"$used" || { echo "FAIL: spec rule $id never checked by validator" >&2; fail=1; }
done
python3 tools/validate_track.py tests/fixtures/good.jsonl samples/*.jsonl >/dev/null || { echo "FAIL: good fixture or a sample rejected" >&2; fail=1; }
[ "$fail" -eq 0 ] && echo "PASS: $(wc -w <<<"$spec_ids") spec rules each checked; each broken fixture fails naming its rule; samples pass"
exit $fail
