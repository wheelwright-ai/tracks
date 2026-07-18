#!/usr/bin/env python3
"""test_path_sanity — guards against corrupt path segments under lugs/bytype + sessions.

Covers bug-basher-literal-unexpanded-paths-in-writes-v1:
  (1) literal 'session-$(date +%Y%m%d-%H%M)' dirs (unexpanded shell cmd-subst), and
  (2) a bytype dir literally named '[\\n  "signal"\\n]' (json.dumps(list) as a path).
"""
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

PASS = FAIL = 0
def ok(m):  globals().__setitem__("PASS", PASS + 1); print(f"  PASS: {m}")
def no(m):  globals().__setitem__("FAIL", FAIL + 1); print(f"  FAIL: {m}")

# 1. _scalar_type coerces a list and rejects unsafe segments
from new_lug import _scalar_type
try:
    ok("list type coerced to scalar") if _scalar_type(["signal"]) == "signal" else no("list not coerced")
except Exception as e:
    no(f"list coercion raised: {e}")
for bad in (["signal"] and '[\n  "signal"\n]', "session-$(date +%Y%m%d)", "a\nb"):
    try:
        _scalar_type(bad); no(f"unsafe type accepted: {bad!r}")
    except ValueError:
        ok(f"unsafe type rejected: {bad[:20]!r}")
try:
    _scalar_type("signal"); ok("valid scalar accepted")
except Exception as e:
    no(f"valid scalar rejected: {e}")

# 2. Tree scan: no corrupt segment under any lugs/bytype or sessions path
BAD_TOKENS = ("[", "]", "\n", "$(", '"')
# Frozen historical trees keep their original (possibly-corrupt) names verbatim.
SKIP = ("/archive/", "/graveyard/", "/.git/", "/_archive/")
root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
def skip(p): return any(s in str(p) for s in SKIP)
corrupt = []
for base in root.glob("**/lugs/bytype"):
    if skip(base): continue
    for p in base.rglob("*"):
        if not skip(p) and any(t in seg for seg in p.relative_to(base).parts for t in BAD_TOKENS):
            corrupt.append(str(p))
for base in root.glob("**/sessions"):
    if skip(base) or not base.is_dir(): continue
    for p in base.iterdir():
        if not skip(p) and any(t in p.name for t in BAD_TOKENS):
            corrupt.append(str(p))
ok("no corrupt path segments in tree") if not corrupt else no(f"corrupt paths: {corrupt[:3]}")

print(f"\n===== path sanity: {PASS} passed, {FAIL} failed =====")
sys.exit(0 if FAIL == 0 else 1)
