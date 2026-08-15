"""claim_triage.py — Ruling 23: sort unprovable completed-lug completion
claims into RETIRE / LINK / BACKFILL, in that order, because RETIRE shrinks
everything downstream and LINK is cheaper than writing a new check.

THE REFRAME (Ruling 23, verbatim from the directive): the 1449 unprovable
completions this tool triages are not a test-writing backlog. They are 1449
sentences describing what should be true. This module sorts them
mechanically using three instruments that now exist:

  - the Archeologist catalog (what code is actually on disk) + the live
    filesystem, for RETIRE;
  - the managed test corpus, for LINK (a PROPOSED candidate only — see the
    honesty note below);
  - bursar.py's ready-backlog demand model, to mark which BACKFILL items an
    ACTIVE initiative still depends on.

READ-ONLY over the lug corpus. Nothing in this module writes to, moves, or
mutates any lug file — see test_claim_triage.py's mtime-invariance test for
the proof. Nothing here auto-closes a RETIRE candidate or auto-links a LINK
candidate; both are reported as evidence for a human (or the Confirmer) to
act on, never as an assertion of a fact.

THE HONESTY RULE (carried over from verification_objects.compute_coverage):
a LINK proposed by this module is a CANDIDATE, never a verification. It
must never be represented to compute_coverage as an EXECUTABLE verification
with a coverage entry — doing so would manufacture false proof, which is
the exact failure Ruling 23 exists to end. If a proposed link is ever lifted
into the v5 verification graph, it must carry executability=UNEXECUTABLE
(or an equivalent unconfirmed marker) until a human confirms it, so
compute_coverage's honesty rule keeps it out of coverage automatically.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from pathlib import Path as pathlib_Path
from typing import Any, Iterable

_THIS = Path(__file__).resolve()
TOOLS_DIR = _THIS.parent
REPO_ROOT = _THIS.parents[4]  # tools -> managed -> spoke -> WAI-Harness -> repo root

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import bursar as _bursar  # noqa: E402
import verification_objects as vo  # noqa: E402

LUGS_ROOT = REPO_ROOT / "WAI-Harness" / "spoke" / "local" / "lugs"
CATALOG_PATH = REPO_ROOT / "WAI-Harness" / "spoke" / "local" / "archeologist" / "catalog.jsonl"
TESTS_ROOT = REPO_ROOT / "WAI-Harness" / "spoke" / "managed" / "tests"

# Calibration: a generous matcher makes the LINK bucket look bigger, which is
# exactly the wrong incentive here (Ruling 23's own calibration warning — a
# wrong link is worse than no link). 0.75 requires BOTH a structural module
# match (the test actually imports/targets the same module the claim names)
# AND that at least some of the claim's own named symbols are found in that
# test's body. A module match alone caps at 0.55 and is never proposed.
DEFAULT_LINK_CONFIDENCE_THRESHOLD = 0.75


# ---------------------------------------------------------------------------
# Corpus loading (read-only — never write, move, or mutate a lug file here)
# ---------------------------------------------------------------------------

def iter_completed_lugs(lugs_root: Path = LUGS_ROOT):
    """Yield (path, record) for every JSON file under bytype/*/completed/.

    Malformed JSON is skipped, not fatal — the triage must survive one bad
    file in a corpus of thousands, same posture as bursar.iter_lug_records.
    """
    bytype = lugs_root / "bytype"
    if not bytype.is_dir():
        return
    for type_dir in sorted(bytype.iterdir()):
        completed_dir = type_dir / "completed"
        if not completed_dir.is_dir():
            continue
        for f in sorted(completed_dir.glob("*.json")):
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            yield f, rec


def is_unprovable_claim(record: dict) -> bool:
    """FALLBACK classifier, used only when no lug-reconcile results are on
    disk (see unprovable_claims() below, which prefers those). A completed
    lug's claim is unprovable when its own verify block, classified by the
    v4->v5 honesty-rule instrument the directive already uses for this
    exact judgement (verification_objects.migrate_v4_verify), does not
    land as a machine-executable oracle. Prose-only, mixed prose+command,
    and absent verify content all classify UNEXECUTABLE.
    """
    v = vo.migrate_v4_verify(record, {"model": "claim_triage"}, "1970-01-01T00:00:00Z")
    return v["executability"] == "UNEXECUTABLE"


# The Ruling 20 reconciler (impl-v5-warmup-reconciles-lug-claims-to-code-v1)
# already walked all 1459 completed lugs and ACTUALLY RAN each one's own
# verify block, producing one of RECONCILED / DIVERGED / UNRECONCILABLE per
# lug. This is strictly stronger evidence than the syntactic
# migrate_v4_verify classification above (it reflects real execution, not
# just command-shape), and it is the literal source of the '1449 of 1459'
# figure this triage lug and Ruling 23 both cite. Preferring it here is
# what makes this triage's counts match ratified canon instead of a fresh
# approximation of it.
RECONCILE_RESULTS_PATH = REPO_ROOT / "WAI-Harness" / "spoke" / "local" / "lug-reconcile" / "results.jsonl"


def load_reconciliation_results(path: Path = RECONCILE_RESULTS_PATH) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def iter_all_lugs(lugs_root: Path = LUGS_ROOT):
    """Every lug on disk regardless of status directory, so a moved lug is still findable."""
    if not lugs_root.is_dir():
        return
    for path in sorted(lugs_root.rglob("*.json")):
        try:
            yield path, json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue


def unprovable_paths_from_reconciliation(path: Path = RECONCILE_RESULTS_PATH) -> set[Path]:
    """Absolute paths of every completed lug whose reconciliation outcome
    was UNRECONCILABLE (its verify block could not be run at all — refused,
    prose, or missing). Deliberately excludes DIVERGED: a DIVERGED claim
    WAS run and its own check now fails, which is a live regression, not
    an unprovable claim — a different problem this triage does not own."""
    out: set[Path] = set()
    for row in load_reconciliation_results(path):
        if row.get("outcome") == "UNRECONCILABLE":
            p = row.get("path")
            if p:
                out.add(Path(p))
    return out


def unprovable_claims(lugs_root: Path = LUGS_ROOT, reconcile_path: Path = RECONCILE_RESULTS_PATH):
    """Yield (path, record, source) for every completed lug carrying an
    unprovable completion claim. Prefers the authoritative lug-reconcile
    results (real execution outcomes, see above); falls back to the
    migrate_v4_verify honesty-rule classifier when no reconciliation data
    exists on disk, so this tool still works on a spoke that has not run
    the Ruling 20 reconciler."""
    reconciled_paths = unprovable_paths_from_reconciliation(reconcile_path)
    if reconciled_paths:
        # A MEMBER THAT MOVED IS STILL A MEMBER. The ratified population is 1,449 CLAIMS, not
        # 1,449 file paths, and a lug that changes directory has not stopped carrying an
        # unprovable claim. The first cut skipped any path that was no longer a file, so the
        # count silently dropped to 1,448 the moment one lug moved from completed/ back to
        # open/ -- and the test pinning the ratified figure blocked a push over a number that
        # was wrong for the right reason.
        #
        # Same lesson as the duplicate-id bug earlier the same day: identity is the id, never
        # the path. Falling back to a by-id search keeps the population whole; a claim whose
        # lug is genuinely gone is still counted, because deleting the file does not settle
        # the claim -- it only hides it.
        by_id: dict[str, pathlib_Path] = {}
        for moved, rec in iter_all_lugs(lugs_root):
            ident = rec.get("id") or rec.get("lug_id") or rec.get("i")
            if ident:
                by_id.setdefault(str(ident), moved)

        for p in sorted(reconciled_paths):
            target, rec = p, None
            if p.is_file():
                try:
                    rec = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    rec = None
            if rec is None:
                relocated = by_id.get(p.stem)
                if relocated is not None:
                    try:
                        rec = json.loads(relocated.read_text(encoding="utf-8"))
                        target = relocated
                    except Exception:
                        rec = None
            # Still counted when the lug cannot be read at all: the claim was ratified as
            # unprovable, and losing the file does not make it provable.
            yield target, (rec if rec is not None else {"id": p.stem, "_missing": True}), "reconciled"
        return
    for path, rec in iter_completed_lugs(lugs_root):
        if is_unprovable_claim(rec):
            yield path, rec, "heuristic"


# ---------------------------------------------------------------------------
# RETIRE — the claim names a mechanism no longer on disk
# ---------------------------------------------------------------------------

def load_catalog(catalog_path: Path = CATALOG_PATH) -> list[dict]:
    rows: list[dict] = []
    if not catalog_path.is_file():
        return rows
    for line in catalog_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def catalog_index(rows: Iterable[dict]) -> dict[str, dict]:
    """path -> its catalog row. The Archeologist catalog is a Tier-0 survey
    (802 rows: manifests, directories, hooks, tools, advisors, lug buckets)
    — it is corroborating evidence, not an exhaustive file inventory. It
    never overrides a positive filesystem hit and never substitutes for the
    filesystem when it has no entry for a path."""
    idx: dict[str, dict] = {}
    for row in rows:
        p = row.get("path")
        if p:
            idx[p] = row
    return idx


# Path segments may themselves start with a dot (.claude/, .github/) — the
# segment character class includes '.' so a dotted directory is not silently
# dropped from the match, which would otherwise turn an absolute path like
# '/repo/.claude/hooks/x.py' into the unresolvable relative 'claude/hooks/x.py'.
_PATH_RE = re.compile(r"(?:/|\.{1,2}/)?(?:[\w.\-]+/)+[\w\-.]+\.\w+")


def _candidate_paths_from_text(text: Any) -> set[str]:
    if not isinstance(text, str):
        return set()
    return set(_PATH_RE.findall(text))


def named_paths(record: dict) -> set[str]:
    """Every path this claim names: its declared file_targets, plus any
    path-shaped token mentioned in its verify text (Ruling 23: 'the lug's
    file_targets and any paths named in its verify').

    file_targets are run through the SAME path-extraction regex as verify
    text rather than trusted as literal strings — this corpus has
    file_targets entries shaped like
    '/abs/path/to/file.py (canonical — some annotation ...)', a path plus
    trailing human commentary in one string. Treating the whole annotated
    string as a literal path makes a real, on-disk file look absent (a
    guaranteed false RETIRE) purely because of the comment glued onto it.
    Extracting the path-shaped token first is what makes the known-bad
    fixture (a claim naming a path that DOES exist) correctly refuse to
    classify RETIRE."""
    paths: set[str] = set()
    for ft in record.get("file_targets") or []:
        if isinstance(ft, str) and ft.strip():
            extracted = _candidate_paths_from_text(ft)
            if extracted:
                paths |= extracted
            else:
                # No regex-shaped path inside it (e.g. a bare relative
                # token with no slash) — fall back to the raw string so we
                # never silently drop a target.
                paths.add(ft.strip())
    verify = record.get("verify")
    if isinstance(verify, list):
        verify_items = [x for x in verify if isinstance(x, str)]
    elif isinstance(verify, str):
        verify_items = [verify]
    else:
        verify_items = []
    for item in verify_items:
        paths |= _candidate_paths_from_text(item)
    return paths


# verify text is command prose, e.g. 'python3 tools/foo.py --check' — that
# is written relative to whatever directory the lug's author had as cwd
# when they wrote it, which this corpus does NOT record. Observed cwd
# conventions in this corpus: the repo root, and WAI-Harness/spoke/managed/
# (where most tools/tests actually live, so 'tools/foo.py' commonly means
# WAI-Harness/spoke/managed/tools/foo.py). A relative path is checked
# against every plausible base and counts as existing if ANY resolves —
# this is the conservative direction for RETIRE, whose whole purpose is
# 'nothing it names is real'; a base-directory guess should never be what
# makes a live mechanism look dead.
_RELATIVE_PATH_BASES = (
    REPO_ROOT,
    REPO_ROOT / "WAI-Harness" / "spoke" / "managed",
    REPO_ROOT / "WAI-Harness" / "spoke" / "local",
    REPO_ROOT / "WAI-Harness" / "spoke",
)


def _exists_on_disk(rel_path: str, repo_root: Path = REPO_ROOT) -> bool:
    """Absolute paths are checked as-is; relative ones are resolved against
    every plausible base directory in _RELATIVE_PATH_BASES (with repo_root
    substituted for REPO_ROOT when the caller passes a different one, e.g.
    a test fixture). Uses a single leading './' strip, NOT
    str.lstrip('./') — lstrip treats its argument as a character set, so
    it would eat the leading '/' off an absolute path too and silently
    turn it relative."""
    p = rel_path[2:] if rel_path.startswith("./") else rel_path
    path_obj = Path(p)
    try:
        if path_obj.is_absolute():
            return path_obj.exists()
        bases = _RELATIVE_PATH_BASES if repo_root == REPO_ROOT else (repo_root,)
        return any((base / p).exists() for base in bases)
    except (OSError, ValueError):
        return False


def classify_retire(record: dict, cat_idx: dict, repo_root: Path = REPO_ROOT) -> tuple[bool, dict]:
    """RETIRE iff the claim names at least one path AND every named path is
    absent from the filesystem. A claim naming NOTHING resolvable is left
    unresolved (never defaulted to RETIRE) — it falls through to LINK/
    BACKFILL instead, because 'nothing to check against' is not evidence of
    death."""
    paths = named_paths(record)
    if not paths:
        return False, {
            "reason": "no file_targets or path-like tokens named; unresolvable, not RETIRE by default",
            "paths": [],
        }
    per_path = []
    all_absent = True
    for p in sorted(paths):
        exists_fs = _exists_on_disk(p, repo_root)
        cat_row = cat_idx.get(p) or cat_idx.get(p.lstrip("./"))
        entry = {"path": p, "exists_on_disk": exists_fs}
        if cat_row is not None:
            entry["catalog_disposition"] = cat_row.get("disposition")
            entry["catalog_evidence_exists"] = (cat_row.get("evidence") or {}).get("exists")
        per_path.append(entry)
        if exists_fs:
            all_absent = False
    reason = (
        "every named path is absent from the filesystem"
        if all_absent
        else "at least one named path exists on disk"
    )
    return all_absent, {"reason": reason, "paths": per_path}


# ---------------------------------------------------------------------------
# LINK — an existing test already proves the claim (PROPOSED, never asserted)
# ---------------------------------------------------------------------------

def build_test_index(tests_root: Path = TESTS_ROOT) -> list[dict]:
    index: list[dict] = []
    if not tests_root.is_dir():
        return index
    for f in sorted(tests_root.rglob("test_*.py")):
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = f.relative_to(REPO_ROOT).as_posix()
        test_functions = re.findall(r"^def (test_[a-zA-Z0-9_]+)\(", content, re.MULTILINE)
        imported = set(re.findall(r"^\s*import ([a-zA-Z_][a-zA-Z0-9_]*)", content, re.MULTILINE))
        imported |= set(re.findall(r"^\s*from ([a-zA-Z_][a-zA-Z0-9_.]*) import", content, re.MULTILINE))
        index.append({
            "path": rel,
            "content": content,
            "test_functions": test_functions,
            "imported_modules": imported,
        })
    return index


def _module_targets(record: dict) -> set[str]:
    mods = set()
    for ft in record.get("file_targets") or []:
        if isinstance(ft, str) and ft.endswith(".py"):
            mods.add(Path(ft).stem)
    return mods


# Generic prose words that regularly show up shaped like "identifier(" or in
# backticks in lug text without naming any actual symbol (e.g. "the change
# sets (...)", "this gate (...)").  Left in, these manufacture symbol_hits
# against ANY test that happens to use the same common English word,
# which is precisely the over-linking the calibration warning names.
_SYMBOL_STOPWORDS = {
    "block", "sets", "clear", "clears", "gate", "step", "drain", "yaml",
    "lugs", "using", "based", "print", "tests", "test", "with", "from",
    "this", "that", "when", "then", "have", "will", "must", "each", "into",
    "over", "under", "about", "after", "before", "again", "still", "never",
    "always", "should", "would", "could", "does", "make", "made", "used",
    "calls", "call", "runs", "run", "check", "checks", "class", "def",
    "claude", "dispatch", "behavior", "archival", "enum",
}


def _claim_symbols(record: dict) -> set[str]:
    parts: list[str] = []
    for key in ("title", "execute", "verify", "perceive", "acceptance_criteria"):
        v = record.get(key)
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            parts.extend(x for x in v if isinstance(x, str))
    blob = " ".join(parts)
    calls = set(re.findall(r"\b([a-z_][a-z0-9_]{3,})\s*\(", blob))
    backticked = set(re.findall(r"`([a-zA-Z_][a-zA-Z0-9_./]{3,})`", blob))
    return (calls | backticked) - _SYMBOL_STOPWORDS


def _module_popularity(test_index: list[dict]) -> dict[str, int]:
    """How many test files import each module. A module imported by many
    test files is a weak discriminator on its own — it identifies a shared
    utility, not the one test that actually proves THIS claim."""
    pop: dict[str, int] = {}
    for t in test_index:
        for m in t["imported_modules"]:
            pop[m] = pop.get(m, 0) + 1
    return pop


_GENERIC_MODULE_POPULARITY = 3  # imported by more than this many test files -> generic


def propose_link(
    record: dict,
    lug_id: str,
    test_index: list[dict],
    threshold: float = DEFAULT_LINK_CONFIDENCE_THRESHOLD,
) -> dict | None:
    """Propose a CANDIDATE link between an unprovable claim and an existing
    test. Requires a structural module match (the test file actually
    imports, or is named after, a module the claim's own file_targets
    name) — a bare module match without any shared symbol caps at 0.55 and
    is never returned, because that alone is coincidence, not proof. When
    the matched module is a generic/shared utility (imported by more than
    _GENERIC_MODULE_POPULARITY test files), a single incidental symbol
    overlap is not trusted either — at least two distinct symbol hits are
    required before that test is even considered a candidate."""
    modules = _module_targets(record)
    if not modules:
        return None
    symbols = _claim_symbols(record)
    popularity = _module_popularity(test_index)
    best = None
    for t in test_index:
        module_hits = {
            m for m in modules
            if m in t["imported_modules"] or re.search(rf"\b{re.escape(m)}\b", t["path"])
        }
        if not module_hits:
            continue
        symbol_hits = {s for s in symbols if re.search(rf"\b{re.escape(s)}\b", t["content"])}
        is_generic = all(popularity.get(m, 0) > _GENERIC_MODULE_POPULARITY for m in module_hits)
        if is_generic and len(symbol_hits) < 2:
            # A generic/shared module plus at most one coincidental word is
            # not evidence this specific test proves this specific claim.
            continue
        score = 0.55
        if symbols:
            score += 0.45 * (len(symbol_hits) / len(symbols))
        else:
            # No distinct symbols named in the claim at all: a module match
            # by itself is too weak to trust, and must never round-trip
            # above the bare-module-match cap.
            score = min(score, 0.55)
        if best is None or score > best["confidence"]:
            test_id = t["path"]
            for fn in t["test_functions"]:
                if any(s in fn for s in symbol_hits):
                    test_id = f"{t['path']}::{fn}"
                    break
            best = {
                "lug_id": lug_id,
                "matched_test_id": test_id,
                "confidence": round(score, 3),
                "evidence": {
                    "module_hits": sorted(module_hits),
                    "symbol_hits": sorted(symbol_hits),
                    "claim_symbols_total": len(symbols),
                },
            }
    if best is None or best["confidence"] < threshold:
        return None
    return best


# ---------------------------------------------------------------------------
# BACKFILL — whatever remains, cross-referenced against active demand
# ---------------------------------------------------------------------------

def active_initiative_ids(lugs_root: Path = LUGS_ROOT) -> set[str]:
    """Initiatives an ACTIVE effort still depends on = initiatives that
    currently carry ready (open, unblocked) backlog demand, per bursar's
    demand model (§21). '_none' (no initiative on the lug) is excluded —
    it is a bucket, not an initiative."""
    demand = _bursar.compute_ready_backlog(lugs_root)
    return {k for k, v in demand.by_initiative.items() if k != "_none" and v.get("count", 0) > 0}


def _initiative_of(record: dict) -> str:
    return record.get("initiative_id") or record.get("initiative") or "_none"


# ---------------------------------------------------------------------------
# The triage pipeline — RETIRE, then LINK, then BACKFILL
# ---------------------------------------------------------------------------

def triage(
    lugs_root: Path = LUGS_ROOT,
    catalog_path: Path = CATALOG_PATH,
    tests_root: Path = TESTS_ROOT,
    reconcile_path: Path = RECONCILE_RESULTS_PATH,
    link_threshold: float = DEFAULT_LINK_CONFIDENCE_THRESHOLD,
) -> dict:
    cat_idx = catalog_index(load_catalog(catalog_path))
    test_index = build_test_index(tests_root)
    active_initiatives = active_initiative_ids(lugs_root)

    total_completed = sum(1 for _ in iter_completed_lugs(lugs_root))

    unprovable_ids: list[str] = []
    retire: list[dict] = []
    link: list[dict] = []
    backfill: list[dict] = []
    source = None

    for path, rec, src in unprovable_claims(lugs_root, reconcile_path):
        source = src
        lug_id = rec.get("id") or path.stem
        unprovable_ids.append(lug_id)
        rel_path = str(path.relative_to(REPO_ROOT))

        is_retire, retire_ev = classify_retire(rec, cat_idx)
        if is_retire:
            retire.append({"lug_id": lug_id, "path": rel_path, "evidence": retire_ev})
            continue

        proposed = propose_link(rec, lug_id, test_index, threshold=link_threshold)
        if proposed is not None:
            proposed["path"] = rel_path
            link.append(proposed)
            continue

        init_id = _initiative_of(rec)
        depended_upon = init_id in active_initiatives
        backfill.append({
            "lug_id": lug_id,
            "path": rel_path,
            "initiative_id": init_id,
            "depended_upon_by_active_initiative": depended_upon,
        })

    depended_upon_count = sum(1 for b in backfill if b["depended_upon_by_active_initiative"])

    return {
        "total_completed_lugs": total_completed,
        "unprovable_claim_count": len(unprovable_ids),
        "unprovable_population_source": source or "none",
        "retire_count": len(retire),
        "link_count": len(link),
        "backfill_count": len(backfill),
        "depended_upon_backfill_count": depended_upon_count,
        "link_confidence_threshold": link_threshold,
        "retire": retire,
        "link": link,
        "backfill": backfill,
    }


def main(argv=None):  # pragma: no cover - thin CLI wrapper
    import argparse

    parser = argparse.ArgumentParser(
        description="Ruling 23 triage: sort unprovable completed-lug claims into RETIRE/LINK/BACKFILL. Read-only."
    )
    parser.add_argument("--link-threshold", type=float, default=DEFAULT_LINK_CONFIDENCE_THRESHOLD)
    parser.add_argument("--json", action="store_true", help="print the full JSON report")
    args = parser.parse_args(argv)

    report = triage(link_threshold=args.link_threshold)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"completed lugs scanned: {report['total_completed_lugs']}")
        print(f"unprovable completion claims: {report['unprovable_claim_count']}")
        print(f"  RETIRE:   {report['retire_count']}")
        print(f"  LINK:     {report['link_count']} (confidence >= {report['link_confidence_threshold']})")
        print(f"  BACKFILL: {report['backfill_count']}")
        print(f"    depended-upon by an ACTIVE initiative: {report['depended_upon_backfill_count']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
