#!/usr/bin/env python3
"""bench_assert.py — capture an AFTER-state and diff it against a bench_snapshot.

Companion to bench_snapshot.py (see that file's docstring for the doctrine
this implements: Migration doctrine 5, both benches, every phase).

What it does:
  1. Re-captures the same scope (file_manifest, lug_counts, oracle_results)
     bench_snapshot.py captured, using the SAME scope_dirs recorded in the
     before-snapshot (so a round-trip on an unchanged tree is apples-to-apples).
  2. Diffs after vs before: added/removed/changed files, lug count deltas,
     oracle result deltas. "drift" is true iff anything in scope changed.
  3. Optionally evaluates phase-specific assertions (--assert KEY=EXPR) — a
     tiny expression language: `file_exists:<relpath>`, `lug_count_gte:<key>:<n>`,
     `oracle_clean:<name>` (oracle returncode == 0).
  4. Optionally attaches the result onto a certification lug's `bench_results`
     field under a bench label (greenfield/brownfield), per Migration doctrine
     5's "a phase's certification lug must attach both bench results."

     NOTE ON WIRING: no phase-gate mechanism exists yet in this harness that
     READS bench_results before permitting phase advancement — this tool only
     builds the attachment POINT (the field, populated with real evidence).
     Wiring a gate that consults it is separate, not-yet-built work.

Usage:
    bench_assert.py --root /path --snapshot before.json --out after.json
    bench_assert.py --root /path --snapshot before.json --out after.json \\
        --assert file_exists:CLAUDE.md --assert lug_count_gte:impl/open:1
    bench_assert.py --root /path --snapshot before.json --out after.json \\
        --attach-to-lug /path/to/cert-lug.json --bench-label brownfield
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bench_snapshot  # noqa: E402


def diff_manifests(before: dict, after: dict) -> dict:
    b_keys, a_keys = set(before), set(after)
    added = sorted(a_keys - b_keys)
    removed = sorted(b_keys - a_keys)
    changed = sorted(k for k in (b_keys & a_keys) if before[k] != after[k])
    return {"added": added, "removed": removed, "changed": changed}


def diff_lug_counts(before: dict, after: dict) -> dict:
    keys = set(before) | set(after)
    deltas = {}
    for k in sorted(keys):
        b, a = before.get(k, 0), after.get(k, 0)
        if b != a:
            deltas[k] = {"before": b, "after": a, "delta": a - b}
    return deltas


def diff_oracles(before: dict, after: dict) -> dict:
    keys = set(before) | set(after)
    deltas = {}
    for k in sorted(keys):
        b, a = before.get(k), after.get(k)
        if b != a:
            deltas[k] = {"before": b, "after": a}
    return deltas


def evaluate_assertions(specs: list[str], after: dict, root: Path) -> list[dict]:
    results = []
    for spec in specs:
        parts = spec.split(":")
        kind = parts[0]
        ok, detail = False, "unknown assertion kind"
        try:
            if kind == "file_exists":
                relpath = ":".join(parts[1:])
                ok = (root / relpath).exists()
                detail = f"{relpath} exists={ok}"
            elif kind == "lug_count_gte":
                key, n = parts[1], int(parts[2])
                actual = after.get("lug_counts", {}).get(key, 0)
                ok = actual >= n
                detail = f"{key} count={actual} (need >= {n})"
            elif kind == "oracle_clean":
                name = parts[1]
                rc = after.get("oracle_results", {}).get(name, {}).get("returncode")
                ok = rc == 0
                detail = f"{name} returncode={rc} (need 0)"
            else:
                detail = f"unrecognized assertion kind: {kind!r}"
        except (IndexError, ValueError) as e:
            detail = f"malformed assertion {spec!r}: {e}"
        results.append({"spec": spec, "pass": ok, "detail": detail})
    return results


def attach_to_lug(lug_path: Path, bench_label: str, result: dict) -> None:
    lug = json.loads(lug_path.read_text(encoding="utf-8"))
    lug.setdefault("bench_results", {})
    lug["bench_results"][bench_label] = {
        "captured_at": result["after"]["captured_at"],
        "drift": result["drift"],
        "assertions": result.get("assertions", []),
        "assertions_all_pass": result.get("assertions_all_pass"),
        "snapshot_root": result["after"]["root"],
    }
    lug_path.write_text(json.dumps(lug, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="spoke root to assert against")
    ap.add_argument("--snapshot", required=True, help="before-state snapshot JSON (from bench_snapshot.py)")
    ap.add_argument("--out", required=True, help="path to write the after-state + diff JSON")
    ap.add_argument("--label", default=None, help="e.g. greenfield / brownfield")
    ap.add_argument("--no-oracles", action="store_true")
    ap.add_argument("--assert", dest="assertions", action="append", default=[],
                    help="repeatable; see docstring for the mini-DSL")
    ap.add_argument("--attach-to-lug", default=None,
                    help="certification lug JSON to attach bench_results onto")
    ap.add_argument("--bench-label", default=None, choices=["greenfield", "brownfield"],
                    help="required with --attach-to-lug")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"ERROR: root does not exist: {root}", file=sys.stderr)
        return 2

    snap_path = Path(args.snapshot)
    if not snap_path.exists():
        print(f"ERROR: snapshot not found: {snap_path}", file=sys.stderr)
        return 2
    before = json.loads(snap_path.read_text(encoding="utf-8"))
    if not before.get("file_manifest"):
        print(f"ERROR: before-snapshot {snap_path} has an empty file_manifest — "
              "it predates the empty-scope hard-fail fix or was hand-edited. "
              "Re-capture it with bench_snapshot.py before asserting against it.",
              file=sys.stderr)
        return 3

    scope_dirs = before.get("scope_dirs", bench_snapshot.DEFAULT_SCOPE_DIRS)
    try:
        after = bench_snapshot.capture(root, scope_dirs, args.label,
                                        with_oracles=not args.no_oracles,
                                        scope_note=before.get("scope_resolution"))
    except bench_snapshot.EmptyScopeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    manifest_diff = diff_manifests(before.get("file_manifest", {}), after["file_manifest"])
    lug_diff = diff_lug_counts(before.get("lug_counts", {}), after["lug_counts"])
    oracle_diff = (diff_oracles(before.get("oracle_results", {}), after.get("oracle_results", {}))
                   if not args.no_oracles else {})

    drift = bool(manifest_diff["added"] or manifest_diff["removed"]
                 or manifest_diff["changed"] or lug_diff or oracle_diff)

    assertion_results = evaluate_assertions(args.assertions, after, root)
    assertions_all_pass = all(r["pass"] for r in assertion_results) if assertion_results else None

    result = {
        "before_snapshot": str(snap_path),
        "after": after,
        "manifest_diff": manifest_diff,
        "lug_count_diff": lug_diff,
        "oracle_diff": oracle_diff,
        "drift": drift,
        "assertions": assertion_results,
        "assertions_all_pass": assertions_all_pass,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"[bench_assert] wrote {out_path} — drift={drift} "
          f"(+{len(manifest_diff['added'])} -{len(manifest_diff['removed'])} "
          f"~{len(manifest_diff['changed'])} files, {len(lug_diff)} lug-count deltas, "
          f"{len(oracle_diff)} oracle deltas)")
    if assertion_results:
        for r in assertion_results:
            print(f"  [{'PASS' if r['pass'] else 'FAIL'}] {r['spec']} — {r['detail']}")

    if args.attach_to_lug:
        if not args.bench_label:
            print("ERROR: --attach-to-lug requires --bench-label", file=sys.stderr)
            return 2
        attach_to_lug(Path(args.attach_to_lug), args.bench_label, result)
        print(f"[bench_assert] attached bench_results.{args.bench_label} -> {args.attach_to_lug}")

    if drift:
        return 0  # drift is informational, not a failure by itself
    return 0


if __name__ == "__main__":
    sys.exit(main())
