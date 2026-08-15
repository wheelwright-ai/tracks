#!/usr/bin/env python3
"""archeologist.py -- deterministic site-survey tool (v5 control-plane, Ruling 10).

Ruling 10 (docs/wheelwright-v5-control-plane-directive.md, Part III) defines three
Archeologist tiers:

  Tier 0  survey   deterministic walk, zero LLM, zero network, $0, seconds.
  Tier 1  lite      cheap-model assist, minutes, cents.        (NOT implemented here)
  Tier 2  deep       full assessment, cost quoted up front,
                     the only tier that may promote a row to `verified-live`.
                                                                (NOT implemented here)

This file implements Tier 0 only: subcommand `survey`. It never calls an LLM,
never touches the network, and costs $0. It surveys seven kinds of things --
directories, manifests, git stats, lug counts, tools, hooks, advisors -- and
writes a catalog keyed by (path, kind), stamped with the git sha of the survey.

Doctrine 1 (catalog everything, claim nothing) means no root is a special
case: directory, git_stat and tool surveyors cover both WAI-Harness/spoke/
and WAI-Harness/hub/ under the same rules. Every row carries a `root` field
(`spoke` | `hub` | `repo`) so counts can be split without re-deriving them
from path prefixes -- a dashboard that silently omitted the hub would look
like the hub had no problems, rather than like nobody looked.

Ruling 9 (Migration Doctrine, Part IV #1) defines five dispositions:
`verified-live`, `observed-unverified`, `legacy`, `orphan`, `dead`. Only Tier 2
oracle passes may assign `verified-live`. This tool enforces that: TIER0_DISPOSITIONS
is the closed set of dispositions Tier 0 may emit, and `verified-live` is not a
member of it. See _assert_tier0_disposition() and the test suite for the guard.

Catalog rows are evidence-bearing: every row carries the concrete pointer
(path, kind, sha, evidence) that justifies its disposition. No narrative fields.

Incremental by git sha: a second survey at the same HEAD sha re-derives nothing
(re_surveyed == 0, catalog byte-identical). A survey at a new sha re-derives only
the (path, kind) rows whose files changed in `git diff <old_sha> <new_sha>`, and
carries every other row forward unchanged (re-stamped with the new sha).

Pre-run surface: before scanning, survey() prints (to stderr, so --json stdout
stays parseable) what will be scanned and the tier's cost/latency profile, so the
operator is in the advised decision-making position (Ruling 10, last sentence).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Disposition contract (Ruling 9 x Ruling 10)
# ---------------------------------------------------------------------------

VERIFIED_LIVE = "verified-live"
OBSERVED_UNVERIFIED = "observed-unverified"
LEGACY = "legacy"
ORPHAN_CANDIDATE = "orphan-candidate"
DEAD_CANDIDATE = "dead-candidate"

# The closed set of dispositions Tier 0 (this file) is permitted to emit.
# verified-live is deliberately NOT a member -- only a Tier 2 oracle pass may
# assign it. This is enforced in code (_assert_tier0_disposition) and proven in
# test_archeologist.py::test_tier0_never_emits_verified_live.
TIER0_DISPOSITIONS = frozenset({
    OBSERVED_UNVERIFIED,
    LEGACY,
    ORPHAN_CANDIDATE,
    DEAD_CANDIDATE,
})

# Legacy-by-shape markers: a path containing any of these substrings is
# flagged `legacy` on sight. "WAI-Spoke" is the v3 phantom root; a v4-only
# spoke must never contain one (see CLAUDE.md, Tool Ownership section).
LEGACY_MARKERS = ("WAI-Spoke", "/v3/", "-v3", "_v3", "deprecated", "_old", ".bak", "/legacy/")

TIER_PROFILE = {
    0: {"name": "survey", "cost": "$0", "latency": "seconds", "llm_calls": 0, "network": False},
    1: {"name": "lite", "cost": "cents (cheap model)", "latency": "minutes", "llm_calls": "many (cheap model)", "network": True},
    2: {"name": "deep", "cost": "quoted up front", "latency": "long", "llm_calls": "many (full model)", "network": True},
}


def _assert_tier0_disposition(disposition: str) -> str:
    if disposition not in TIER0_DISPOSITIONS:
        raise ValueError(
            f"Tier 0 may never emit disposition {disposition!r}; "
            f"only {sorted(TIER0_DISPOSITIONS)} are permitted "
            f"(verified-live requires a Tier 2 oracle pass, Ruling 9)."
        )
    return disposition


# ---------------------------------------------------------------------------
# Base / repo resolution
# ---------------------------------------------------------------------------

DEFAULT_BASE = "WAI-Harness/spoke/local"


def resolve_repo(repo: str) -> Path:
    return Path(repo).resolve()


def resolve_base(repo_root: Path, base: str) -> Path:
    p = Path(base)
    return p if p.is_absolute() else (repo_root / p)


def git(repo_root: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True, text=True, check=False,
    )
    return out.stdout.strip()


def current_sha(repo_root: Path) -> str:
    sha = git(repo_root, "rev-parse", "HEAD")
    return sha if sha else "UNKNOWN"


# ---------------------------------------------------------------------------
# Row helper
# ---------------------------------------------------------------------------

def make_row(path: str, kind: str, disposition: str, sha: str, evidence: dict) -> dict:
    return {
        "path": path,
        "kind": kind,
        "disposition": _assert_tier0_disposition(disposition),
        "sha": sha,
        "root": _infer_root(path),
        "evidence": evidence,
    }


def _is_stub_file(fpath: Path) -> bool:
    """Deterministic shape check: a file with essentially no real content."""
    try:
        text = fpath.read_text(errors="replace")
    except OSError:
        return False
    real_lines = 0
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#") or s.startswith('"""') or s.startswith("'''"):
            continue
        real_lines += 1
    return real_lines <= 2


def _has_legacy_marker(path_str: str) -> bool:
    return any(marker in path_str for marker in LEGACY_MARKERS)


def _infer_root(path_str: str) -> str:
    """Which named root (spoke/hub) a catalog row belongs to, derived from the
    path itself so counts can be split without re-deriving from prefixes later.
    Doctrine 1: catalog everything -- the hub is not a special case."""
    if path_str.startswith("WAI-Harness/hub/"):
        return "hub"
    if path_str.startswith("WAI-Harness/spoke/"):
        return "spoke"
    return "repo"


def _dir_is_empty(dpath: Path) -> bool:
    for _root, _dirs, files in os.walk(dpath):
        if files:
            return False
    return True


_CORPUS_EXTS = (".py", ".sh", ".md", ".json")
_CORPUS_EXCLUDE_DIRS = {".git", "node_modules", "__pycache__"}


def _build_reference_corpus(repo_root: Path) -> dict:
    """Read every .py/.sh/.md/.json file in the repo once, for consumer-reference
    lookups (Ruling 9 Doctrine 1/3: orphan means no consumer, not no test)."""
    corpus = {}
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in _CORPUS_EXCLUDE_DIRS]
        for fname in filenames:
            if Path(fname).suffix not in _CORPUS_EXTS:
                continue
            fpath = Path(dirpath) / fname
            rel = str(fpath.relative_to(repo_root))
            try:
                corpus[rel] = fpath.read_text(errors="replace")
            except OSError:
                continue
    return corpus


def _reference_pattern(stem: str):
    # Word-boundary match: "untested_tool" must not match inside
    # "referenced_untested_tool" (a real substring collision we hit in
    # testing). \b treats "_" as a word char, so this correctly rejects that.
    return re.compile(r"(?<!\w)" + re.escape(stem) + r"(?!\w)")


def _has_inbound_reference(stem: str, self_rel: str, corpus: dict) -> bool:
    # Two-stage for speed at ~13k-file scale: a plain substring test (C-speed,
    # str.find) rejects the overwhelming majority instantly; only the rare
    # substring hit pays for a regex word-boundary check to rule out
    # collisions like "untested_tool" inside "referenced_untested_tool".
    pattern = None
    for path, content in corpus.items():
        if path == self_rel or stem not in content:
            continue
        if pattern is None:
            pattern = _reference_pattern(stem)
        if pattern.search(content):
            return True
    return False


# ---------------------------------------------------------------------------
# Kind surveyors -- each returns {(path, kind): row} for its slice.
# ---------------------------------------------------------------------------

def _survey_scope_roots(repo_root: Path, base: Path) -> list:
    """The set of top-level scan roots: spoke (base + managed) AND hub (local +
    managed), same rules, no special-casing. `base` is the CLI-resolved spoke
    local dir; the hub side is always WAI-Harness/hub/{local,managed} -- the hub
    is a fixed sibling root in this repo, not something --base repoints."""
    candidates = [
        base,
        repo_root / "WAI-Harness" / "spoke" / "managed",
        repo_root / "WAI-Harness" / "hub" / "local",
        repo_root / "WAI-Harness" / "hub" / "managed",
    ]
    return [r for r in candidates if r.is_dir()]


def survey_directories(repo_root: Path, base: Path, sha: str) -> dict:
    rows = {}
    for root in _survey_scope_roots(repo_root, base):
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name == "__pycache__":
                continue
            rel = str(entry.relative_to(repo_root))
            if _dir_is_empty(entry):
                disp = DEAD_CANDIDATE
            elif _has_legacy_marker(rel):
                disp = LEGACY
            else:
                disp = OBSERVED_UNVERIFIED
            evidence = {"exists": True, "empty": _dir_is_empty(entry)}
            rows[(rel, "directory")] = make_row(rel, "directory", disp, sha, evidence)
    return rows


def survey_manifests(repo_root: Path, sha: str) -> dict:
    rows = {}
    candidates = sorted(set(
        list(repo_root.glob("**/MANIFEST.json")) + list(repo_root.glob("**/manifest.json"))
    ))
    for mpath in candidates:
        if "node_modules" in mpath.parts or ".git" in mpath.parts:
            continue
        rel = str(mpath.relative_to(repo_root))
        evidence = {"exists": True}
        disp = OBSERVED_UNVERIFIED
        try:
            data = json.loads(mpath.read_text())
            if isinstance(data, dict) and "is_master" in data:
                evidence["is_master"] = data["is_master"]
        except (OSError, json.JSONDecodeError) as exc:
            disp = DEAD_CANDIDATE
            evidence["parse_error"] = type(exc).__name__
        if _has_legacy_marker(rel):
            disp = LEGACY
        rows[(rel, "manifest")] = make_row(rel, "manifest", disp, sha, evidence)
    return rows


def survey_git_stats(repo_root: Path, base: Path, sha: str) -> dict:
    rows = {}
    for root in _survey_scope_roots(repo_root, base):
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name == "__pycache__":
                continue
            rel = str(entry.relative_to(repo_root))
            file_count = sum(1 for _r, _d, files in os.walk(entry) for _f in files)
            last_commit = git(repo_root, "log", "-1", "--format=%H|%cI", "--", rel)
            last_sha, _, last_date = last_commit.partition("|")
            evidence = {
                "file_count": file_count,
                "last_commit_sha": last_sha or None,
                "last_commit_date": last_date or None,
            }
            rows[(rel, "git_stat")] = make_row(rel, "git_stat", OBSERVED_UNVERIFIED, sha, evidence)
    return rows


def survey_lug_buckets(repo_root: Path, base: Path, sha: str) -> dict:
    rows = {}
    bytype = base / "lugs" / "bytype"
    if not bytype.is_dir():
        return rows
    names = sorted(p.name for p in bytype.iterdir() if p.is_dir())
    for name in names:
        tdir = bytype / name
        counts = {}
        for status_dir in sorted(tdir.iterdir()) if tdir.is_dir() else []:
            if not status_dir.is_dir():
                continue
            counts[status_dir.name] = sum(1 for f in status_dir.glob("*.json"))
        rel = str(tdir.relative_to(repo_root))
        disp = OBSERVED_UNVERIFIED
        evidence = {"counts": counts, "total": sum(counts.values())}
        # legacy-by-shape: a bytype dir name that starts with a shorter,
        # otherwise-existing bytype dir name is a probable schema-drift
        # duplicate of the shorter (canonical) one.
        for other in names:
            if other != name and name.startswith(other) and len(name) > len(other):
                disp = LEGACY
                evidence["duplicate_of"] = other
                break
        rows[(rel, "lug_bucket")] = make_row(rel, "lug_bucket", disp, sha, evidence)
    return rows


# Same rules, no special-casing: every place executable tooling lives, on
# either root. The hub keeps its tools in three places (managed/tools,
# local/scripts, local/tools) rather than spoke's one; all three are scanned.
_TOOL_SOURCE_DIRS = (
    "WAI-Harness/spoke/managed/tools",
    "WAI-Harness/hub/managed/tools",
    "WAI-Harness/hub/local/scripts",
    "WAI-Harness/hub/local/tools",
)
_TOOL_TEST_DIRS = (
    "WAI-Harness/spoke/managed/tests",
    "WAI-Harness/hub/managed/tests",
    "WAI-Harness/hub/local/tests",
)


def survey_tools(repo_root: Path, sha: str) -> dict:
    rows = {}
    tool_dirs = [repo_root / d for d in _TOOL_SOURCE_DIRS if (repo_root / d).is_dir()]
    if not tool_dirs:
        return rows
    test_stems = set()
    for tests_dir in (repo_root / d for d in _TOOL_TEST_DIRS):
        if tests_dir.is_dir():
            test_stems |= {p.stem for p in tests_dir.glob("test_*.py")}
    corpus = _build_reference_corpus(repo_root)
    for tools_dir in tool_dirs:
        for fpath in sorted(tools_dir.rglob("*.py")):
            if "__pycache__" in fpath.parts:
                continue
            rel = str(fpath.relative_to(repo_root))
            stem = fpath.stem
            has_test = f"test_{stem}" in test_stems
            test_evidence = {"has_test": has_test}
            if not has_test:
                test_evidence["expected_test"] = f"test_{stem}.py"
            if _has_legacy_marker(rel):
                disp = LEGACY
                evidence = {}
            elif _is_stub_file(fpath):
                disp = DEAD_CANDIDATE
                evidence = {"reason": "stub-shaped (<=2 real lines)"}
            elif not _has_inbound_reference(stem, rel, corpus):
                # orphan means no CONSUMER (Ruling 9 Doctrine 1/3), never "untested".
                # Test coverage is recorded separately in evidence and never drives
                # this disposition -- a referenced-but-untested tool stays
                # observed-unverified, not orphan-candidate.
                disp = ORPHAN_CANDIDATE
                evidence = {"reason": "no inbound reference", "searched": len(corpus) - 1}
                evidence.update(test_evidence)
            else:
                disp = OBSERVED_UNVERIFIED
                evidence = dict(test_evidence)
            rows[(rel, "tool")] = make_row(rel, "tool", disp, sha, evidence)
    return rows


def survey_v3_phantom_roots(repo_root: Path, sha: str) -> dict:
    """Any directory named `WAI-Spoke`, at any depth, is a v3 phantom-root
    marker -- catalogued `legacy` even if empty (a v4-only spoke must never
    contain one; see CLAUDE.md Tool Ownership section)."""
    rows = {}
    for dirpath, dirnames, _filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in _CORPUS_EXCLUDE_DIRS]
        if Path(dirpath).name == "WAI-Spoke":
            rel = str(Path(dirpath).relative_to(repo_root))
            evidence = {"reason": "v3 phantom root marker"}
            rows[(rel, "directory")] = make_row(rel, "directory", LEGACY, sha, evidence)
    return rows


def survey_hooks(repo_root: Path, sha: str) -> dict:
    rows = {}
    hooks_dir = repo_root / ".claude" / "hooks"
    settings_path = repo_root / ".claude" / "settings.json"
    settings_text = ""
    if settings_path.is_file():
        try:
            settings_text = settings_path.read_text()
        except OSError:
            settings_text = ""
    if not hooks_dir.is_dir():
        return rows
    for fpath in sorted(hooks_dir.iterdir()):
        if not fpath.is_file() or fpath.suffix not in (".sh", ".py"):
            continue
        rel = str(fpath.relative_to(repo_root))
        if _has_legacy_marker(rel):
            disp = LEGACY
            evidence = {}
        elif fpath.name not in settings_text:
            disp = ORPHAN_CANDIDATE
            evidence = {"reason": "not referenced in .claude/settings.json"}
        else:
            disp = OBSERVED_UNVERIFIED
            evidence = {"wired_in_settings": True}
        rows[(rel, "hook")] = make_row(rel, "hook", disp, sha, evidence)
    return rows


def survey_advisors(repo_root: Path, base: Path, sha: str) -> dict:
    rows = {}
    roots = [
        repo_root / "WAI-Harness" / "spoke" / "advisors",
        base / "advisors",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or entry.name == "__pycache__":
                continue
            rel = str(entry.relative_to(repo_root))
            if _dir_is_empty(entry):
                disp = DEAD_CANDIDATE
                evidence = {"empty": True}
            elif _has_legacy_marker(rel):
                disp = LEGACY
                evidence = {}
            else:
                has_manifest = any(entry.glob("*.json")) or any(entry.glob("*.md"))
                if not has_manifest:
                    disp = ORPHAN_CANDIDATE
                    evidence = {"reason": "no .json or .md config found in advisor dir"}
                else:
                    disp = OBSERVED_UNVERIFIED
                    evidence = {"has_config": True}
            rows[(rel, "advisor")] = make_row(rel, "advisor", disp, sha, evidence)
    return rows


SURVEYORS_MULTI_ARG = {
    "directory": survey_directories,
    "git_stat": survey_git_stats,
    "lug_bucket": survey_lug_buckets,
    "advisor": survey_advisors,
}
SURVEYORS_REPO_ONLY = {
    "manifest": survey_manifests,
    "tool": survey_tools,
    "hook": survey_hooks,
    "phantom_root": survey_v3_phantom_roots,
}


def run_full_survey(repo_root: Path, base: Path, sha: str) -> dict:
    rows = {}
    for fn in SURVEYORS_MULTI_ARG.values():
        rows.update(fn(repo_root, base, sha))
    for fn in SURVEYORS_REPO_ONLY.values():
        rows.update(fn(repo_root, sha))
    return rows


# ---------------------------------------------------------------------------
# Catalog I/O
# ---------------------------------------------------------------------------

def catalog_paths(base: Path) -> dict:
    d = base / "archeologist"
    return {
        "dir": d,
        "catalog": d / "catalog.jsonl",
        "summary": d / "summary.json",
        "state": d / "state.json",
    }


def load_catalog(catalog_path: Path) -> dict:
    rows = {}
    if not catalog_path.is_file():
        return rows
    with catalog_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            rows[(row["path"], row["kind"])] = row
    return rows


def write_catalog(catalog_path: Path, rows: dict) -> None:
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows.values(), key=lambda r: (r["path"], r["kind"]))
    with catalog_path.open("w") as f:
        for row in ordered:
            f.write(json.dumps(row, sort_keys=True))
            f.write("\n")


def load_state(state_path: Path) -> dict:
    if not state_path.is_file():
        return {}
    try:
        return json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n")


def changed_paths(repo_root: Path, old_sha: str, new_sha: str) -> set:
    if not old_sha or old_sha == "UNKNOWN" or old_sha == new_sha:
        return set()
    out = git(repo_root, "diff", "--name-only", old_sha, new_sha)
    return set(line for line in out.splitlines() if line)


def row_is_affected(row_path: str, diff_set: set) -> bool:
    if row_path in diff_set:
        return True
    prefix = row_path.rstrip("/") + "/"
    return any(p.startswith(prefix) for p in diff_set)


# ---------------------------------------------------------------------------
# Pre-run surface (advised-decision contract)
# ---------------------------------------------------------------------------

def print_pre_run_surface(tier: int, repo_root: Path, base: Path, delta_count, stream=None) -> None:
    if stream is None:
        stream = sys.stderr
    profile = TIER_PROFILE[tier]
    print(f"[archeologist] Tier {tier} ({profile['name']}) survey", file=stream)
    print(f"  repo:   {repo_root}", file=stream)
    print(f"  base:   {base}", file=stream)
    print(f"  cost:        {profile['cost']}", file=stream)
    print(f"  latency:     {profile['latency']}", file=stream)
    print(f"  llm calls:   {profile['llm_calls']}", file=stream)
    print(f"  network:     {profile['network']}", file=stream)
    print("  scanning: directories, manifests, git stats, lug counts, tools, hooks, advisors", file=stream)
    if delta_count is not None:
        print(f"  delta since last cataloged sha: {delta_count} path(s) changed", file=stream)
    else:
        print("  delta since last cataloged sha: no prior catalog (full survey)", file=stream)
    print(f"  dispositions permitted at this tier: {sorted(TIER0_DISPOSITIONS)}", file=stream)
    print("  (verified-live is never assigned at Tier 0 -- requires a Tier 2 oracle pass)", file=stream)


# ---------------------------------------------------------------------------
# survey command
# ---------------------------------------------------------------------------

def cmd_survey(args: argparse.Namespace) -> int:
    if args.tier != 0:
        print(
            f"[archeologist] tier {args.tier} is not implemented; only Tier 0 (survey) exists today.",
            file=sys.stderr,
        )
        return 2

    repo_root = resolve_repo(args.repo)
    base = resolve_base(repo_root, args.base)
    sha = current_sha(repo_root)

    paths = catalog_paths(base)
    prev_rows = load_catalog(paths["catalog"])
    state = load_state(paths["state"])
    old_sha = state.get("last_sha")

    if old_sha == sha and prev_rows:
        # Same sha as last survey: nothing to re-derive. Byte-identical output.
        print_pre_run_surface(args.tier, repo_root, base, delta_count=0)
        new_rows = prev_rows
        re_surveyed = 0
    else:
        diff_set = changed_paths(repo_root, old_sha, sha) if old_sha else set()
        print_pre_run_surface(args.tier, repo_root, base, delta_count=len(diff_set) if old_sha else None)

        current_rows = run_full_survey(repo_root, base, sha)
        new_rows = {}
        re_surveyed = 0
        for key, fresh_row in current_rows.items():
            path, _kind = key
            prev_row = prev_rows.get(key)
            if prev_row is None or not old_sha:
                new_rows[key] = fresh_row
                re_surveyed += 1
            elif row_is_affected(path, diff_set):
                new_rows[key] = fresh_row
                re_surveyed += 1
            else:
                carried = dict(prev_row)
                carried["sha"] = sha
                new_rows[key] = carried
        # rows that vanished (deleted paths) are simply not carried forward.

    write_catalog(paths["catalog"], new_rows)
    write_state(paths["state"], {"last_sha": sha})

    disposition_counts = {}
    for row in new_rows.values():
        disposition_counts[row["disposition"]] = disposition_counts.get(row["disposition"], 0) + 1
    kind_counts = {}
    for row in new_rows.values():
        kind_counts[row["kind"]] = kind_counts.get(row["kind"], 0) + 1

    summary = {
        "sha": sha,
        "tier": args.tier,
        "row_count": len(new_rows),
        "re_surveyed": re_surveyed,
        "disposition_counts": disposition_counts,
        "kind_counts": kind_counts,
        "catalog_path": str(paths["catalog"]),
    }
    paths["summary"].parent.mkdir(parents=True, exist_ok=True)
    paths["summary"].write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"[archeologist] survey complete: {len(new_rows)} rows, {re_surveyed} re-surveyed", file=sys.stderr)
        print(json.dumps(summary, sort_keys=True, indent=2), file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="archeologist.py", description="Deterministic site-survey tool (Tier 0).")
    sub = ap.add_subparsers(dest="command", required=True)

    survey = sub.add_parser("survey", help="Tier 0: deterministic, $0, seconds.")
    survey.add_argument("--base", default=DEFAULT_BASE, help="v4 spoke local base (default: %(default)s)")
    survey.add_argument("--repo", default=".", help="repo root (default: cwd)")
    survey.add_argument("--tier", type=int, default=0, choices=[0, 1, 2], help="Archeologist tier (default: 0)")
    survey.add_argument("--json", action="store_true", help="emit summary JSON on stdout")
    survey.set_defaults(func=cmd_survey)

    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
