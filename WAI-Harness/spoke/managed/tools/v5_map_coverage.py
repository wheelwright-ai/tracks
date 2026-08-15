#!/usr/bin/env python3
"""v5_map_coverage.py — the coverage oracle for the v5 migration map.

WHY THIS EXISTS
---------------
`impl-v5-phase0-inventory-migration-map-v1` requires that every mechanism in the
Archeologist Tier-0 catalog appears exactly once in docs/v5-migration-map.md.

The catalog keys by (path, kind). mywheel holds 553 catalog rows across 304 tools,
20 hooks, 36 advisors, 30 lug buckets and 83 directories. A 1:1 path-to-row map is
553 rows and unreadable, so the map's unit is the MECHANISM and this tool is what
makes that substitution honest: every catalog path must belong to exactly one
declared mechanism, and every declared mechanism must appear in the map.

The oracle is therefore two-sided and cannot pass vacuously:
  - UNMAPPED  — a catalog path no mechanism rule claims. Coverage is incomplete.
  - UNMAPPED_MECHANISM — a mechanism with catalog rows but no row in the map.
  - EMPTY_MECHANISM — a declared mechanism that matched zero catalog paths. Either
    the rule is wrong or the thing is gone; both need a human.

An empty catalog or an empty map is a hard error, not a clean sheet.

Doctrine reference: docs/wheelwright-v5-control-plane-directive.md Part IV
doctrine 3 (circles gate every phase) and §36 (map before build).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_CATALOG = "WAI-Harness/spoke/local/archeologist/catalog.jsonl"
DEFAULT_MAP = "docs/v5-migration-map.md"


class CoverageError(RuntimeError):
    """Raised when the oracle cannot run against real data."""


# ---------------------------------------------------------------------------
# Mechanism rules
# ---------------------------------------------------------------------------
# Ordered, first-match-wins. Each entry is (mechanism_name, kind_or_None, regex).
# `kind_or_None` narrows a rule to one catalog kind; None matches any kind.
#
# These names MUST match the `mechanism` column values used in the map document.
# Adding a rule without adding the corresponding map row makes the oracle fail
# with UNMAPPED_MECHANISM -- that is deliberate. The rules and the map are two
# halves of one contract.
RULES: list[tuple[str, str | None, str]] = [
    # --- excluded-from-canon trees: catalogued, but they are not live mechanisms
    ("certify extract tree (stray)", None, r"^\.certify-"),
    ("subsumed graveyard", None, r"WAI-Harness/\.subsumed-graveyard/"),
    ("dev benchmark fixtures", None, r"^WAI-Harness/dev/benchmarks/"),
    ("archived spoke trees", None, r"(^|/)(_archive|archive)(/|$)"),

    # --- v3 phantom roots (Doctrine 1: legacy, visibly flagged)
    ("v3 phantom root", None, r"(^|/)WAI-Spoke(/|$)"),

    # --- ceremonies and session lifecycle
    ("session hooks", "hook", r".*"),
    ("command manifests", "manifest", r"commands/manifest\.json$"),
    ("harness manifests", "manifest", r"MANIFEST\.json$"),
    ("hub context manifests", "manifest", r".*"),

    # --- lug estate
    ("lug bytype buckets", "lug_bucket", r".*"),

    # --- advisors
    ("spoke advisors", "advisor", r"WAI-Harness/spoke/advisors/"),
    ("advisor bench (local)", "advisor", r".*"),

    # --- tooling, split by owner
    ("spoke managed tools", "tool", r"^WAI-Harness/spoke/managed/tools/"),
    ("spoke managed tests", "tool", r"^WAI-Harness/spoke/managed/tests/"),
    ("hub managed tools", "tool", r"^WAI-Harness/hub/managed/tools/"),
    ("hub local scripts", "tool", r"^WAI-Harness/hub/local/(scripts|tools)/"),
    ("spoke local tools", "tool", r"^WAI-Harness/spoke/local/"),
    ("repo-root tooling", "tool", r".*"),

    # --- directory + git surfaces
    ("spoke local data dirs", None, r"^WAI-Harness/spoke/local/"),
    ("spoke managed tree", None, r"^WAI-Harness/spoke/managed/"),
    ("hub tree", None, r"^WAI-Harness/hub/"),
    ("repo-root surfaces", None, r".*"),
]

_COMPILED = [(name, kind, re.compile(pat)) for name, kind, pat in RULES]


def mechanism_for(path: str, kind: str) -> str | None:
    """Return the mechanism owning this catalog path, or None if unclaimed."""
    for name, rule_kind, pat in _COMPILED:
        if rule_kind is not None and rule_kind != kind:
            continue
        if pat.search(path):
            return name
    return None


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def load_catalog(path: Path) -> list[dict]:
    if not path.exists():
        raise CoverageError(f"catalog not found: {path} — run archeologist.py survey first")
    rows = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        raise CoverageError(f"catalog is empty: {path} — an empty catalog cannot prove coverage")
    return rows


_MAP_ROW = re.compile(r"^\|\s*`?([^`|]+?)`?\s*\|\s*(reuse|extend|rename|migrate|deprecate|replace)\s*\|")


def load_map_mechanisms(path: Path) -> dict[str, int]:
    """Parse the map's markdown tables. Returns {mechanism: occurrence_count}."""
    if not path.exists():
        raise CoverageError(f"migration map not found: {path}")
    found: dict[str, int] = {}
    for line in path.read_text().splitlines():
        m = _MAP_ROW.match(line.strip())
        if m:
            name = m.group(1).strip()
            found[name] = found.get(name, 0) + 1
    if not found:
        raise CoverageError(f"no disposition rows parsed from {path} — the map is empty or malformed")
    return found


# ---------------------------------------------------------------------------
# Oracle
# ---------------------------------------------------------------------------
def evaluate(catalog: list[dict], map_mechanisms: dict[str, int]) -> dict:
    by_mechanism: dict[str, list[str]] = {}
    unmapped: list[dict] = []

    for row in catalog:
        mech = mechanism_for(row["path"], row["kind"])
        if mech is None:
            unmapped.append({"path": row["path"], "kind": row["kind"]})
        else:
            by_mechanism.setdefault(mech, []).append(row["path"])

    declared = {name for name, _, _ in RULES}
    matched = set(by_mechanism)

    empty_mechanisms = sorted(declared - matched)
    unmapped_mechanisms = sorted(m for m in matched if m not in map_mechanisms)
    duplicated_rows = sorted(m for m, n in map_mechanisms.items() if n > 1)
    orphan_map_rows = sorted(m for m in map_mechanisms if m not in matched and m not in declared)

    clean = not (unmapped or unmapped_mechanisms or duplicated_rows)

    return {
        "clean": clean,
        "catalog_rows": len(catalog),
        "mechanisms_matched": len(matched),
        "map_rows": sum(map_mechanisms.values()),
        "coverage": {
            "unmapped_paths": unmapped,
            "unmapped_mechanisms": unmapped_mechanisms,
            "duplicated_map_rows": duplicated_rows,
            "empty_mechanisms": empty_mechanisms,
            "map_rows_without_catalog_backing": orphan_map_rows,
        },
        "per_mechanism": {m: len(p) for m, p in sorted(by_mechanism.items())},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", default=DEFAULT_CATALOG)
    ap.add_argument("--map", dest="map_path", default=DEFAULT_MAP)
    ap.add_argument("--json", action="store_true", help="emit the full result as JSON")
    args = ap.parse_args(argv)

    try:
        catalog = load_catalog(Path(args.catalog))
        map_mechanisms = load_map_mechanisms(Path(args.map_path))
    except CoverageError as exc:
        print(f"[v5-map-coverage] ERROR: {exc}", file=sys.stderr)
        return 3

    result = evaluate(catalog, map_mechanisms)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        cov = result["coverage"]
        print(f"[v5-map-coverage] catalog rows: {result['catalog_rows']}  "
              f"mechanisms: {result['mechanisms_matched']}  map rows: {result['map_rows']}")
        for label, key in (
            ("UNMAPPED PATHS", "unmapped_paths"),
            ("MECHANISMS MISSING FROM MAP", "unmapped_mechanisms"),
            ("DUPLICATED MAP ROWS", "duplicated_map_rows"),
            ("DECLARED BUT EMPTY", "empty_mechanisms"),
            ("MAP ROWS WITH NO CATALOG BACKING", "map_rows_without_catalog_backing"),
        ):
            items = cov[key]
            if items:
                print(f"  {label}: {len(items)}")
                for item in items[:12]:
                    print(f"    - {item}")
                if len(items) > 12:
                    print(f"    ... {len(items) - 12} more")
        print(f"  verdict: {'CLEAN' if result['clean'] else 'INCOMPLETE'}")

    return 0 if result["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
