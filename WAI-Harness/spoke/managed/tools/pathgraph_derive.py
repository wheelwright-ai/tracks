#!/usr/bin/env python3
"""pathgraph_derive.py -- derive a PathGraph from code and tests, on any project.

v5 control-plane, Ruling 24/25/26/28 (docs/wheelwright-v5-control-plane-directive.md).

THE INVERSION (Ruling 24). Historically the RECORD was primary and code was described
by it: a lug asserts what exists, and the code is whatever it happens to be. That is why
this wheel accumulated 1449 completion claims that point at nothing -- an assertion with
nothing to contradict it just sits there. This tool flips it. The code is the substrate.
Everything else attaches to it, in this order, and only the last link is authored:

    CODE NODE   <- observable on disk, cannot drift, it IS the reality
    <- TEST EDGE   derived from imports/references, never declared
    <- RESULT      an execution, with timing and outcome
    <- SCHEDULE    when it runs next (or an honest "unscheduled")
    <- INTENT      a lug claiming the node -- attached LAST, and OPTIONAL

THE ACCEPTANCE CASE IS BROWNFIELD. This tool must produce a useful graph for a project
that has never heard of Wheelwright: no lugs, no catalog, no WAI history. Every input
that references WAI machinery (--lugs-dir, --gitnexus-index) is optional and additive;
the core derivation (`scan_project`) never requires any of it.

Ruling 28's six constraints, structural to this module:
  28.1  identity is content-hash + symbol-shape, not path -- rename survives (see
        `diff_snapshots`, MOVED handling).
  28.2  dead-code needs a DECLARED entry-point set (`--entry-points`); absent that,
        dead-code analysis reports UNAVAILABLE, never a guess (`dead_code_analysis`).
  28.3  every edge carries `derivation` and `strength` ("strong" | "weak"); actions gate
        on strength (`safe_to_act`).
  28.4  the graph is diffable from run one (`diff_snapshots` / `--prev`).
  28.5  small projects are scored on trajectory + disposition presence, not absolute
        coverage (`scoring_mode`, GREENFIELD_NODE_THRESHOLD).
  28.6  every node/edge state string is a key in STATE_CONSUMERS -- a state nothing
        consumes is a bug, not a feature (see test_pathgraph_derive.py::test_no_orphan_states).

Never auto-deletes anything. `safe_to_act` is a tier the operator reads, not an action
this tool takes.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

# --------------------------------------------------------------------------------------
# Constants / doctrine
# --------------------------------------------------------------------------------------

GREENFIELD_NODE_THRESHOLD = 10  # Ruling 28.5

DEFAULT_EXCLUDE_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache",
    ".gitnexus", "dist", "build", ".mypy_cache", ".tox", "site-packages",
    ".eggs", "*.egg-info",
}

TEST_FILE_RE = re.compile(r"(^test_.*\.py$)|(.*_test\.py$)")
TEST_DIR_NAMES = {"tests", "test"}

# Ruling 31.1 -- disposition thresholds. A file touched this recently is far more
# likely mid-build than abandoned; the number is a heuristic, never a verdict on
# its own -- it is one signal among several, reported as evidence.
RECENT_AUTHORSHIP_DAYS = 45

# Lug statuses treated as "no longer actively watching this file" for the purpose
# of the ADOPT/DEPRECATE signal. A lug in one of these states is not "open" intent.
CLOSED_LUG_STATUSES = {
    "completed", "done", "closed", "archived", "retired", "resolved",
    "implemented", "delivered", "rejected", "skipped",
}

# Weak, honest heuristic for "this was explicitly marked obsolete" -- a comment,
# not a proof. Combined with absence of tests/lug-refs/recent authorship before it
# ever drives a DEPRECATE disposition (see disposition_for_candidate).
DEPRECATION_MARKER_RE = re.compile(r"(?i)#.*\b(deprecated|superseded)\b")

# Ruling 28.6 -- the closed registry of node/edge/claim states this tool may emit.
# Every state string that appears anywhere in an output document must be a key here.
# A state with no consumer is deleted from the model, never merely documented.
STATE_CONSUMERS = {
    "UNTESTED": "functional_identity.tested_fraction; overlay dead-code eligibility",
    "TESTED": "functional_identity.tested_fraction",
    "UNPROVEN": "functional_identity.proven_fraction; never renders as covered/green",
    "PROVEN": "functional_identity.proven_fraction; safe_to_act eligibility",
    "PASS": "results.outcome feeds PROVEN state",
    "FAIL": "results.outcome feeds PROVEN state (failing != unproven)",
    "NEW": "delta.added -- operator review queue",
    "MOVED": "delta.moved -- preserves lineage instead of birth+death",
    "REMOVED": "delta.removed -- operator review queue",
    "UNCHANGED": "delta -- suppressed from action queues (no news)",
    "PROPOSAL": "operator disposal queue (safe_to_act='proposal' tier)",
    "QUESTION": "operator disposal queue (safe_to_act='question' tier, needs review)",
    "UNAVAILABLE": "dead_code_analysis dashboard gauge -- honest non-answer",
    "AVAILABLE": "dead_code_analysis dashboard gauge -- entry points were declared",
    "NOT_DEAD": "dead_code_analysis -- reachable from a declared entry point",
    "UNSCHEDULED": "advisor scheduling backlog (maintenance-schedule gap finding)",
    "SCHEDULED": "advisor scheduling backlog (edge is covered by a cadence)",
    "RESOLVED": "overlay -- lug claim needs nothing, code already represents it",
    "UNRESOLVED": "overlay backlog -- unimplemented-intent candidate for the operator",
    "DEPRECATE": "dead_code disposition -- superseded/obsolete, routed to an authorised "
                 "deletion wave, never deleted automatically (Ruling 31.1)",
    "ADOPT": "dead_code disposition -- sound but never wired in, becomes an ACTIVATION "
             "candidate naming what would consume it and what wiring costs (Ruling 31.1)",
    "UNDECIDED": "dead_code disposition -- the honest default; stays visible on the "
                 "operator queue rather than aging into silence (Ruling 31.1)",
}


# --------------------------------------------------------------------------------------
# Small deterministic helpers
# --------------------------------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _should_exclude(path: Path, root: Path) -> bool:
    for part in path.relative_to(root).parts[:-1]:
        if part in DEFAULT_EXCLUDE_DIRS:
            return True
    return False


def _is_test_path(rel_path: str) -> bool:
    p = Path(rel_path)
    if TEST_FILE_RE.match(p.name):
        return True
    return any(part in TEST_DIR_NAMES for part in p.parts[:-1])


# --------------------------------------------------------------------------------------
# CODE NODES
# --------------------------------------------------------------------------------------

def _extract_python_symbols(source: str) -> list:
    """Top-level symbol shape: sorted function/class names, methods as Class.method.

    Never raises on unparsable source -- a syntax error is itself a finding, not a
    crash; the caller records it as `parse_error` and the node gets an empty shape.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    names = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            names.append(node.name)
            for sub in ast.iter_child_nodes(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.append(f"{node.name}.{sub.name}")
    return sorted(set(names))


# --------------------------------------------------------------------------------------
# PROVENANCE CLASSES + RUNWAY (Ruling 33, and the correction to Ruling 25)
# --------------------------------------------------------------------------------------
#
# Ruling 25 as originally written rebuilds the graph entirely from the codebase. Applied
# literally that is a data-loss event disguised as a maintenance operation: it would
# delete every conversation-derived node -- a year of reasoning about WHY things are the
# way they are -- during an upgrade that reports success. Nothing would alarm, because
# regenerating discovered nodes IS what it was asked to do.
#
# The fix is that the two classes have DIFFERENT SOURCES OF TRUTH:
#
#   DISCOVERED   derived from code. Thin, factual, regenerable, disposable. The code is
#                its truth, so re-derivation should overwrite it without ceremony.
#   COLLABORATED derived from conversation: reasoning, rejected paths, why it matters.
#                Derivable from NOTHING. Re-derivation must CARRY it, never regenerate it.
#
# And when a collaborated node's code is gone, it does not vanish -- it becomes RUNWAY.
# The reasoning outlives the file. Runway is not debt: the takeoff is already recorded,
# so it carries its origin (who said it, when) and a landing condition, preferably one a
# machine can check.
#
# AUTHORSHIP PRECEDENCE (Ruling 34.3) is the sharp edge. A collaborated node outranks a
# discovered one for INTENT and ORDERING -- a crafted lug beats a generated item in the
# backlog. It never outranks it on FACT. A collaborated node asserting code that does not
# exist resolves to RUNWAY; it must NOT produce a graph entry claiming the code is there.
# Authority orders the work. It does not get to assert reality.

DISCOVERED = "DISCOVERED"
COLLABORATED = "COLLABORATED"
RUNWAY = "RUNWAY"

# Doctrine 3: every node feeds exactly one circle, or it is rejected at the gate. A node
# feeding no circle is inert -- it accumulates without ever being checked, learned from,
# or completed, which is how a graph silently becomes a landfill.
CIRCLE_BY_PROVENANCE = {
    DISCOVERED: "verification",
    COLLABORATED: "learning",
    RUNWAY: "completion",
}


def stamp_provenance(node: dict, provenance: str) -> dict:
    """Tag a node with its class and the single circle it feeds. Stamp at CREATION.

    Stamping later would mean the graph briefly holds unclassified nodes, and anything
    that reads it in that window cannot tell regenerable from irreplaceable.
    """
    node["provenance"] = provenance
    node["circle"] = CIRCLE_BY_PROVENANCE[provenance]
    return node


def validate_node(node: dict) -> list:
    """Return the reasons this node must be REJECTED. Empty list means acceptable."""
    reasons = []
    prov = node.get("provenance")
    if prov not in CIRCLE_BY_PROVENANCE:
        reasons.append(f"unknown provenance {prov!r}")
        return reasons  # nothing below can be judged without a valid class
    if node.get("circle") != CIRCLE_BY_PROVENANCE[prov]:
        reasons.append(
            f"circle {node.get('circle')!r} does not match provenance {prov} "
            f"(expected {CIRCLE_BY_PROVENANCE[prov]!r})")
    if prov == DISCOVERED:
        # Derived facts only. Inflating a discovered node with speculation to make the
        # classes look uniform is how the irreplaceable half stops being distinguishable.
        for speculative in ("why", "rejected", "landing_condition"):
            if node.get(speculative):
                reasons.append(f"discovered node carries speculative field {speculative!r}")
    if prov == RUNWAY:
        if not node.get("origin"):
            reasons.append("runway item has no origin")
        if not node.get("landing_condition"):
            reasons.append("runway item has no landing condition")
    return reasons


def to_runway(collab: dict, reason: str) -> dict:
    """Convert a collaborated node whose code is absent into a runway item.

    The node is not deleted and not rewritten into something claiming the code exists.
    Its reasoning is preserved verbatim; only its class, circle and status change.
    """
    item = dict(collab)
    item["status"] = RUNWAY
    item["runway_reason"] = reason
    item.pop("node_id", None)  # a runway item names no content, because there is none
    return stamp_provenance(item, RUNWAY)


def merge_provenance(discovered: dict, collaborated: list) -> dict:
    """Re-derivation, done correctly.

    `discovered` is the freshly scanned node map (path -> node); it is REGENERATED every
    run and simply replaces whatever was there. `collaborated` is loaded from the durable
    store and CARRIED -- each record passes through byte-identical when its path still
    resolves to code.

    Returns {nodes, runway, rejected}. Nothing is ever silently dropped: a record that
    cannot be carried becomes runway, and a record that fails the gate lands in `rejected`
    with its reasons rather than disappearing.
    """
    nodes = {}
    for path, node in discovered.items():
        nodes[path] = stamp_provenance(dict(node), DISCOVERED)

    runway, rejected = [], []
    for collab in collaborated or []:
        record = stamp_provenance(dict(collab), COLLABORATED)
        path = record.get("path")
        if path and path in discovered:
            # The code is there: carry the collaborated record UNCHANGED. This is the
            # byte-identical guarantee, and it is the whole correction to Ruling 25.
            bad = validate_node(record)
            if bad:
                rejected.append({"record": record, "reasons": bad})
            else:
                # KEY BY PATH *AND* ORDINAL. Keying by path alone silently overwrote:
                # MEASURED 2026-08-07 by the v5 self-graph, 13 rulings attached to 4 files
                # produced 3 collaborated nodes, because eleven rulings governing
                # pathgraph_derive.py collapsed onto one key and the last one won. That is
                # the SAME silent data loss as Ruling 25, at a smaller scale and inside the
                # very function written to prevent it -- found only because the graph was
                # pointed at its own construction.
                #
                # One file legitimately carries many collaborated records: a module can be
                # governed by a dozen decisions, and each is a separate thing someone meant.
                ordinal = sum(1 for k in nodes if k.startswith("collab::" + path + "#"))
                nodes[f"collab::{path}#{ordinal}"] = record
            continue
        # The code is gone -- or was never there. Either way authority does not get to
        # assert it into existence; the record becomes runway.
        item = to_runway(record, "underlying code absent" if path else "no path asserted")
        bad = validate_node(item)
        if bad:
            rejected.append({"record": item, "reasons": bad})
        else:
            runway.append(item)

    return {"nodes": nodes, "runway": runway, "rejected": rejected}


def load_collaborated(collaborated_file: str | None) -> list:
    """Load the durable collaborated store. Absence is normal, never an error.

    Stored in a FILE committed with the code (Ruling 29): evidence that lives anywhere
    else gets separated from what it describes the first time a branch moves.
    """
    if not collaborated_file:
        return []
    path = Path(collaborated_file)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    if isinstance(data, dict):
        data = data.get("collaborated") or []
    return data if isinstance(data, list) else []


def build_code_node(path: Path, root: Path) -> dict:
    rel_path = _rel(path, root)
    raw = path.read_bytes()
    content_hash = _sha256_bytes(raw)
    language = "python" if path.suffix == ".py" else "unknown"
    symbols = None
    parse_error = False
    if language == "python":
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        symbols = _extract_python_symbols(text)
        if symbols is None:
            parse_error = True
            symbols = []
    else:
        symbols = []
    shape_hash = _sha256_text(json.dumps(symbols, sort_keys=True)) if symbols else None
    is_test = _is_test_path(rel_path)
    return {
        "node_id": content_hash,
        "path": rel_path,
        "kind": "test" if is_test else "module",
        "language": language,
        "symbols": symbols,
        "symbol_shape_hash": shape_hash,
        "parse_error": parse_error,
        "loc": raw.count(b"\n") + 1,
    }


def scan_project(root: Path, include_ext=(".py",)) -> dict:
    """Enumerate CODE NODES from the filesystem alone. No WAI concept required.

    This is the brownfield floor: a project with zero WAI history produces a full
    node set from this function and nothing else.
    """
    nodes = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in include_ext:
            continue
        if _should_exclude(path, root):
            continue
        node = build_code_node(path, root)
        nodes[node["path"]] = node
    return nodes


# --------------------------------------------------------------------------------------
# Module resolution (for import-graph + test edges)
# --------------------------------------------------------------------------------------

def _module_name_candidates(rel_path: str) -> set:
    """All plausible dotted/bare names a file could be imported as.

    Handles both packaged imports (pkg.sub.mod) and the flat-script style this
    wheel's own tools/ directory uses (import archeologist), by also registering
    the bare stem and the stem with parent dirs stripped.
    """
    p = Path(rel_path)
    stem_parts = list(p.with_suffix("").parts)
    dotted = ".".join(stem_parts)
    names = {dotted, p.stem}
    if stem_parts and stem_parts[-1] == "__init__":
        pkg_dotted = ".".join(stem_parts[:-1])
        if pkg_dotted:
            names.add(pkg_dotted)
    return {n for n in names if n}


def build_module_index(nodes: dict) -> dict:
    """module-name -> rel_path, for every non-test node. Ambiguous names are dropped
    (recorded, never guessed at) so a resolved edge is always unambiguous."""
    name_to_paths = {}
    for rel_path, node in nodes.items():
        if node["kind"] == "test":
            continue
        for name in _module_name_candidates(rel_path):
            name_to_paths.setdefault(name, set()).add(rel_path)
    index = {}
    ambiguous = set()
    for name, paths in name_to_paths.items():
        if len(paths) == 1:
            index[name] = next(iter(paths))
        else:
            ambiguous.add(name)
    return {"index": index, "ambiguous": ambiguous}


def _parse_imports(source: str) -> list:
    """Return list of imported dotted names (module-level, best-effort). Never raises."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
                for alias in node.names:
                    names.append(f"{node.module}.{alias.name}")
            else:
                names.append("*relative*")  # `from . import x` -- unresolved marker
    return names


def _find_subprocess_string_refs(source: str, candidate_stems: set) -> set:
    """Weak signal: a test that shells out to a script by literal filename
    (`subprocess.run(["python3", "archeologist.py", ...])`) instead of importing it.
    Common in this wheel's tools/. Detected as a plain string search -- deliberately
    dumb, so its weakness is honest rather than dressed up as static analysis."""
    hits = set()
    for stem in candidate_stems:
        if re.search(rf'["\']([^"\']*/)?{re.escape(stem)}\.py["\']', source):
            hits.add(stem)
    return hits


def derive_test_edges(root: Path, nodes: dict, module_idx: dict) -> list:
    """TEST EDGES: derived from static imports (strong) or literal subprocess
    filename references (weak). Never declared, never invented -- an unattributable
    test stays unattributed, which is itself reported (see UNTESTED)."""
    edges = []
    index = module_idx["index"]
    module_stems = {Path(p).stem for p, n in nodes.items() if n["kind"] != "test"}
    for rel_path, node in nodes.items():
        if node["kind"] != "test" or node["language"] != "python":
            continue
        full_path = root / rel_path
        source = full_path.read_text(encoding="utf-8", errors="replace")
        imported = _parse_imports(source)
        resolved_targets = set()
        for name in imported:
            if name in index:
                resolved_targets.add(index[name])
                continue
            # also try last dotted segment against bare stems (e.g. "from tools import archeologist")
            tail = name.rsplit(".", 1)[-1]
            if tail in index:
                resolved_targets.add(index[tail])
        for target_path in sorted(resolved_targets):
            edges.append({
                "test_path": rel_path,
                "code_path": target_path,
                "derivation": "static_import",
                "strength": "strong",
            })
        weak_hits = _find_subprocess_string_refs(source, module_stems - {Path(t).stem for t in resolved_targets})
        for stem in sorted(weak_hits):
            candidates = [p for p, n in nodes.items() if n["kind"] != "test" and Path(p).stem == stem]
            for target_path in candidates:
                edges.append({
                    "test_path": rel_path,
                    "code_path": target_path,
                    "derivation": "subprocess_name_reference",
                    "strength": "weak",
                })
    return edges


def derive_module_import_edges(root: Path, nodes: dict, module_idx: dict) -> list:
    """Module->module static import graph, used only for reachability (28.2)."""
    edges = []
    index = module_idx["index"]
    for rel_path, node in nodes.items():
        if node["kind"] == "test" or node["language"] != "python":
            continue
        full_path = root / rel_path
        source = full_path.read_text(encoding="utf-8", errors="replace")
        for name in _parse_imports(source):
            target = index.get(name) or index.get(name.rsplit(".", 1)[-1])
            if target and target != rel_path:
                edges.append({
                    "from": rel_path,
                    "to": target,
                    "derivation": "static_import",
                    "strength": "strong",
                })
    return edges


# --------------------------------------------------------------------------------------
# RESULTS (execution)
# --------------------------------------------------------------------------------------

def run_tests(root: Path, test_paths: list, timeout: int = 120) -> dict:
    """Execute pytest over the discovered test files and return per-file outcome +
    duration via junit-xml. Never fabricates a result: if pytest cannot run, every
    test node is reported UNPROVEN with an explicit reason, never blank or green."""
    if not test_paths:
        return {"attempted": False, "reason": "no test files discovered", "per_file": {}}
    with tempfile.TemporaryDirectory() as tmp:
        junit_path = Path(tmp) / "junit.xml"
        cmd = [sys.executable, "-m", "pytest", "-q", f"--junit-xml={junit_path}"] + [
            str(root / p) for p in test_paths
        ]
        try:
            subprocess.run(
                cmd, cwd=str(root), capture_output=True, timeout=timeout, text=True
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            return {"attempted": True, "reason": f"execution failed: {exc}", "per_file": {}}
        if not junit_path.exists():
            return {"attempted": True, "reason": "no junit report produced", "per_file": {}}
        per_file = {}
        try:
            tree = ET.parse(junit_path)
        except ET.ParseError as exc:
            return {"attempted": True, "reason": f"junit parse failed: {exc}", "per_file": {}}
        for testcase in tree.iter("testcase"):
            classname = testcase.get("classname", "")
            filename = testcase.get("file")
            rel = filename
            if rel is None:
                # reconstruct from classname (dots -> path) as a fallback
                rel = classname.replace(".", "/") + ".py"
            duration = float(testcase.get("time", 0.0))
            failed = testcase.find("failure") is not None or testcase.find("error") is not None
            skipped = testcase.find("skipped") is not None
            entry = per_file.setdefault(rel, {"pass": 0, "fail": 0, "skip": 0, "duration_seconds": 0.0})
            entry["duration_seconds"] += duration
            if skipped:
                entry["skip"] += 1
            elif failed:
                entry["fail"] += 1
            else:
                entry["pass"] += 1
        return {"attempted": True, "reason": "ok", "per_file": per_file}


def _normalize_test_result_key(rel_path: str, per_file: dict) -> dict | None:
    if rel_path in per_file:
        return per_file[rel_path]
    # pytest sometimes reports the path relative to cwd differently; try suffix match
    for key, val in per_file.items():
        if key.endswith(rel_path) or rel_path.endswith(key):
            return val
    return None


# --------------------------------------------------------------------------------------
# SCHEDULE
# --------------------------------------------------------------------------------------

def load_schedule(schedule_file: str | None) -> dict:
    if not schedule_file:
        return {}
    p = Path(schedule_file)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return data.get("test_cadence", {}) if isinstance(data, dict) else {}


def schedule_for(test_path: str, schedule_map: dict) -> dict:
    for pattern, cadence in schedule_map.items():
        if Path(test_path).match(pattern) or test_path == pattern:
            return {"status": "SCHEDULED", "cadence": cadence}
    return {"status": "UNSCHEDULED", "cadence": None}


# --------------------------------------------------------------------------------------
# GitNexus (Ruling 26 -- read an existing index where present, never require it)
# --------------------------------------------------------------------------------------

def read_gitnexus_index(root: Path) -> dict:
    """Best-effort read of an existing GitNexus cache manifest. The full symbol graph
    lives in a proprietary store this tool has no business parsing by hand; what's
    safe and honest to use is the manifest's own file inventory + stats as a coarse
    cross-check, never as a silent replacement for our own static analysis."""
    manifest = root / ".gitnexus" / "gitnexus.json"
    if not manifest.exists():
        return {"available": False}
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"available": False}
    file_hashes = data.get("fileHashes", {})
    return {
        "available": True,
        "stats": data.get("stats", {}),
        "indexed_file_count": len(file_hashes) if isinstance(file_hashes, dict) else None,
        "indexed_at": data.get("indexedAt"),
    }


# --------------------------------------------------------------------------------------
# Entry points / dead-code (28.2)
# --------------------------------------------------------------------------------------

def load_entry_points(entry_points_file: str | None, nodes: dict) -> list | None:
    """Returns a resolved list of rel_paths, or None if no set was declared."""
    if not entry_points_file:
        return None
    p = Path(entry_points_file)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    raw = data.get("entry_points", data if isinstance(data, list) else [])
    resolved = [ep for ep in raw if ep in nodes]
    return resolved


# --------------------------------------------------------------------------------------
# Entry-point DERIVATION (Ruling 28.2 + impl-v5-declare-entry-points-for-dead-code-v1).
#
# "An entry point without evidence of what invokes it is a guess wearing a
# declaration." Every entry this module derives carries a `derivation` explaining
# WHERE it came from: a hook bound in .claude/settings.json, a `__main__` guard, or
# a live crontab line. Nothing here is invented -- a source that cannot be read
# (missing settings.json, no crontab, unreadable file) contributes nothing rather
# than a guess. `hand_declare_entry_points()` is the one place a human name goes in,
# and it is kept separate so a reader can see exactly what was NOT derivable.
# --------------------------------------------------------------------------------------

_MAIN_GUARD_RE = re.compile(r'if\s+__name__\s*==\s*[\'"]__main__[\'"]\s*:')
_HOOK_SCRIPT_BINDING_RE = re.compile(
    r'\$\{CLAUDE_PROJECT_DIR\}/\.claude/hooks/([A-Za-z0-9_.\-]+\.sh)'
)
_SCRIPT_PY_REF_RE = re.compile(r'(?:tools|hooks)/([A-Za-z0-9_]+\.py)')


def derive_main_guard_entry_points(nodes: dict, root: Path) -> dict:
    """CLI tools: a module with `if __name__ == "__main__":` is, by construction,
    designed to be run directly. Strong, cheap, and exactly what this wheel's
    tools/ directory is built from (flat scripts, not a package)."""
    found = {}
    for rel_path, node in nodes.items():
        if node["kind"] == "test" or node["language"] != "python":
            continue
        full_path = root / rel_path
        try:
            source = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _MAIN_GUARD_RE.search(source):
            found[rel_path] = {
                "kind": "cli_tool",
                "derivation": "derived",
                "evidence": f"{rel_path} contains `if __name__ == \"__main__\":`",
            }
    return found


def derive_hook_bound_entry_points(root: Path, nodes: dict, settings_file: str | None = None) -> dict:
    """Hooks: read .claude/settings.json for the hook scripts Claude Code actually
    binds to a lifecycle event, then grep each bound script for the tools/*.py or
    hooks/*.py files it invokes. A script sitting in .claude/hooks/ that nothing in
    settings.json binds is NOT included here -- unbound is not an entry point."""
    found = {}
    settings_path = Path(settings_file) if settings_file else (root / ".claude" / "settings.json")
    if not settings_path.exists():
        return found
    try:
        settings_text = settings_path.read_text(encoding="utf-8")
    except OSError:
        return found
    bound_scripts = sorted(set(_HOOK_SCRIPT_BINDING_RE.findall(settings_text)))
    hooks_dir = root / ".claude" / "hooks"
    for script_name in bound_scripts:
        script_path = hooks_dir / script_name
        if not script_path.exists():
            continue
        try:
            script_source = script_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for py_name in sorted(set(_SCRIPT_PY_REF_RE.findall(script_source))):
            for candidate in (f"tools/{py_name}", f".claude/hooks/{py_name}"):
                if candidate in nodes and candidate not in found:
                    found[candidate] = {
                        "kind": "hook_invocation",
                        "derivation": "derived",
                        "evidence": (
                            f"invoked by .claude/hooks/{script_name}, which is bound "
                            f"in .claude/settings.json"
                        ),
                    }
    return found


def derive_cron_entry_points(root: Path, nodes: dict, crontab_text: str | None = None) -> dict:
    """Cron: the ACTUAL crontab (`crontab -l`), not a file someone once wrote down.
    A line naming a path under `root` is a live, running entry point. Never raises
    if cron is unavailable (containers, CI, no crontab installed)."""
    found = {}
    if crontab_text is None:
        try:
            proc = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True, timeout=10
            )
            crontab_text = proc.stdout if proc.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            crontab_text = ""
    root_str = str(root.resolve())
    for line in crontab_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for token in line.split():
            if token.endswith(".py") and root_str in token:
                abs_candidate = token.split(root_str, 1)[-1].lstrip("/")
                if abs_candidate in nodes:
                    found[abs_candidate] = {
                        "kind": "cron_job",
                        "derivation": "derived",
                        "evidence": f"live crontab line: {line}",
                    }
    return found


def hand_declare_entry_points(nodes: dict) -> dict:
    """Whatever cannot be derived from settings.json bindings, __main__ guards, or
    the live crontab. Empty by default -- add here ONLY with a human-readable reason,
    never silently. Kept as its own function so a reader sees exactly what a human
    asserted rather than the tool observed."""
    return {}


def derive_entry_points_registry(root: Path, nodes: dict, settings_file: str | None = None,
                                  crontab_text: str | None = None) -> dict:
    """Assemble the full entry-point registry: every source layered in, each entry
    keeping the strongest/first evidence it was found under. Returns the exact
    document shape written to registry/entry-points.json."""
    sources = {}
    # Order matters: setdefault() keeps the FIRST evidence found, so more specific
    # runtime bindings (hook/cron -- something actually invokes this on a schedule
    # or lifecycle event) win over the weaker "it merely has a __main__ guard"
    # signal when both are true of the same file.
    for deriver in (
        lambda: derive_hook_bound_entry_points(root, nodes, settings_file),
        lambda: derive_cron_entry_points(root, nodes, crontab_text),
        lambda: derive_main_guard_entry_points(nodes, root),
    ):
        for path, info in deriver().items():
            sources.setdefault(path, info)

    hand_declared = hand_declare_entry_points(nodes)
    for path, info in hand_declared.items():
        sources.setdefault(path, info)

    return {
        "schema_version": 1,
        "root": str(root),
        "entry_points": sorted(sources.keys()),
        "sources": sources,
        "hand_declared": sorted(hand_declared.keys()),
        "derived_count": len(sources) - len(hand_declared),
        "hand_declared_count": len(hand_declared),
    }


def dead_code_analysis(nodes: dict, module_edges: list, test_edges: list, entry_points):
    if entry_points is None:
        return {"status": "UNAVAILABLE", "reason": "no declared entry-point set", "candidates": []}
    reachable = set(entry_points)
    frontier = list(entry_points)
    adj = {}
    for e in module_edges:
        adj.setdefault(e["from"], set()).add(e["to"])
    while frontier:
        cur = frontier.pop()
        for nxt in adj.get(cur, ()):
            if nxt not in reachable:
                reachable.add(nxt)
                frontier.append(nxt)

    tested_paths = {e["code_path"] for e in test_edges}
    weak_inbound = {e["code_path"] for e in test_edges if e["strength"] == "weak"}
    strong_inbound_module = {e["to"] for e in module_edges if e["strength"] == "strong"}

    candidates = []
    for rel_path, node in nodes.items():
        if node["kind"] == "test":
            continue
        if rel_path in reachable:
            continue
        has_strong_inbound = rel_path in strong_inbound_module or (
            rel_path in tested_paths and rel_path not in weak_inbound
        )
        if has_strong_inbound:
            # reachable via a strong signal our BFS missed (e.g. entry itself never
            # imported anything) -- not a candidate.
            continue
        tier = "QUESTION" if rel_path in weak_inbound else "PROPOSAL"
        candidates.append({"path": rel_path, "safe_to_act": tier})
    return {"status": "AVAILABLE", "candidates": candidates}


# --------------------------------------------------------------------------------------
# Disposition (Ruling 31.1) -- unreachable is a QUESTION, not a verdict.
#
# Every dead-code candidate resolves to DEPRECATE / ADOPT / UNDECIDED. This wheel has
# a documented pattern of building something correct and never wiring it in; a
# detector that only ever proposes deletion destroys exactly that value at the
# moment it becomes visible. The signal (tests, recent authorship, an open lug)
# is reported as evidence, never used to silently auto-delete anything.
# --------------------------------------------------------------------------------------

def _lug_reference_index(lugs_dir: str | None, node_paths: set) -> dict:
    """path -> list of {lug_id, lug_type, lug_status} for every lug whose
    file_targets resolve to that path, open or closed. Distinct from overlay_lugs()
    (Ruling 25), which only reports UNRESOLVED targets -- here we want every
    reference, because a CLOSED lug pointing at a live file is itself a DEPRECATE
    signal, not silence."""
    index = {}
    if not lugs_dir:
        return index
    root = Path(lugs_dir)
    if not root.exists():
        return index
    node_path_suffixes = {p.split("/")[-1]: p for p in node_paths}
    for lug_file in sorted(root.rglob("*.json")):
        try:
            lug = json.loads(lug_file.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        targets = lug.get("file_targets") or []
        for t in targets:
            t_norm = t.lstrip("/")
            hit_path = None
            if t_norm in node_paths:
                hit_path = t_norm
            else:
                for p in node_paths:
                    if t_norm.endswith(p) or p.endswith(t_norm):
                        hit_path = p
                        break
                if hit_path is None:
                    hit_path = node_path_suffixes.get(Path(t_norm).name)
            if hit_path:
                index.setdefault(hit_path, []).append({
                    "lug_id": lug.get("id", lug_file.stem),
                    "lug_type": lug.get("type"),
                    "lug_status": lug.get("status"),
                })
    return index


def _git_days_since_commit(root: Path, rel_path: str) -> float | None:
    """Days since the last commit touching rel_path, or None if unavailable --
    not a git repo, git missing, or the file is untracked. Never raises, never
    fabricates a number."""
    try:
        proc = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", rel_path],
            cwd=str(root), capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = proc.stdout.strip()
    if proc.returncode != 0 or not out:
        return None
    try:
        commit_ts = int(out)
    except ValueError:
        return None
    import time as _time
    return (_time.time() - commit_ts) / 86400.0


def _has_deprecation_marker(root: Path, rel_path: str) -> bool:
    """Weak textual signal only: a `# deprecated` / `# superseded` comment near the
    top of the file. Never sufficient alone to justify deletion -- only ever
    contributes to a DEPRECATE disposition, which itself is a proposal, not an
    action (Ruling 28's 'never auto-delete, at any confidence')."""
    try:
        full_path = root / rel_path
        text = full_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    head = "\n".join(text.splitlines()[:40])
    return bool(DEPRECATION_MARKER_RE.search(head))


def disposition_for_candidate(rel_path: str, root: Path, has_tests: bool,
                               lug_refs: list, days_since_commit: float | None,
                               superseded_marker: bool) -> tuple:
    """Returns (disposition, evidence). DEPRECATE requires an explicit supersede
    signal (marker, or ONLY closed lugs referencing it with no test coverage and no
    recent authorship) -- absence of evidence is never itself evidence of
    obsolescence. ADOPT fires on any positive signal: tests, an open lug, or recent
    authorship. UNDECIDED is the default when nothing distinguishes the node either
    way -- it stays visible rather than being silently defaulted to either side."""
    open_lug_refs = [l for l in lug_refs if (l.get("lug_status") or "") not in CLOSED_LUG_STATUSES]
    closed_lug_refs = [l for l in lug_refs if l not in open_lug_refs]
    recent = days_since_commit is not None and days_since_commit <= RECENT_AUTHORSHIP_DAYS

    evidence = {
        "has_tests": has_tests,
        "open_lug_references": open_lug_refs,
        "closed_lug_references": closed_lug_refs,
        "days_since_last_commit": days_since_commit,
        "recent_authorship": recent,
        "superseded_marker": superseded_marker,
    }

    if has_tests or open_lug_refs or recent:
        return "ADOPT", evidence
    if superseded_marker or closed_lug_refs:
        return "DEPRECATE", evidence
    return "UNDECIDED", evidence


def add_dispositions(candidates: list, nodes: dict, test_edges: list, root: Path,
                      lugs_dir: str | None) -> None:
    """Mutates each candidate in place, adding `disposition`, `disposition_evidence`,
    and -- for ADOPT only -- an honest `activation_candidate` stub naming what is
    NOT yet known (consumer, wiring cost) rather than fabricating an answer."""
    if not candidates:
        return
    tested_paths = {e["code_path"] for e in test_edges}
    node_paths = set(nodes.keys())
    lug_index = _lug_reference_index(lugs_dir, node_paths)
    for c in candidates:
        rel_path = c["path"]
        has_tests = rel_path in tested_paths
        lug_refs = lug_index.get(rel_path, [])
        days = _git_days_since_commit(root, rel_path)
        marker = _has_deprecation_marker(root, rel_path)
        disposition, evidence = disposition_for_candidate(
            rel_path, root, has_tests, lug_refs, days, marker
        )
        c["disposition"] = disposition
        c["disposition_evidence"] = evidence
        if disposition == "ADOPT":
            c["activation_candidate"] = {
                "summary": (
                    f"{rel_path} is unreachable from every declared entry point but "
                    "carries a positive signal (tests, an open lug, or recent "
                    "authorship) -- likely built-and-unwired rather than obsolete."
                ),
                "consumer_hint": "not derivable -- needs operator review to name what should call this",
                "wiring_cost_hint": "not derivable -- needs operator review to estimate",
            }


# --------------------------------------------------------------------------------------
# Overlay (Ruling 25) -- legacy lug corpus laid over the derived graph, read-only
# --------------------------------------------------------------------------------------

def overlay_lugs(lugs_dir: str | None, nodes: dict) -> dict:
    """Never writes into the graph. A lug whose file_targets all resolve to nodes
    needs nothing. A lug with an unresolved target is a backlog candidate: work that
    was described and never built."""
    if not lugs_dir:
        return {"checked": 0, "resolved": 0, "backlog_candidates": []}
    root = Path(lugs_dir)
    if not root.exists():
        return {"checked": 0, "resolved": 0, "backlog_candidates": []}
    node_paths = set(nodes.keys())
    node_path_suffixes = {p.split("/")[-1] for p in node_paths}
    checked = 0
    resolved = 0
    backlog = []
    for lug_file in sorted(root.rglob("*.json")):
        try:
            lug = json.loads(lug_file.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        targets = lug.get("file_targets")
        if not targets:
            continue
        checked += 1
        missing = []
        for t in targets:
            t_norm = t.lstrip("/")
            hit = (
                t_norm in node_paths
                or any(p.endswith(t_norm) or t_norm.endswith(p) for p in node_paths)
                or Path(t_norm).name in node_path_suffixes
            )
            if not hit:
                missing.append(t)
        if missing:
            backlog.append({
                "lug_id": lug.get("id", lug_file.stem),
                "lug_type": lug.get("type"),
                "lug_status": lug.get("status"),
                "state": "UNRESOLVED",
                "missing_targets": missing,
                "evidence": {"lug_path": str(lug_file), "declared_targets": targets},
            })
        else:
            resolved += 1
    return {"checked": checked, "resolved": resolved, "backlog_candidates": backlog}


# --------------------------------------------------------------------------------------
# Snapshot assembly + rename detection + delta (28.1 / 28.4)
# --------------------------------------------------------------------------------------

def derive_graph(
    root: Path,
    entry_points_file: str | None = None,
    schedule_file: str | None = None,
    lugs_dir: str | None = None,
    run_tests_flag: bool = True,
    test_timeout: int = 120,
    collaborated_file: str | None = None,
) -> dict:
    root = root.resolve()
    nodes = scan_project(root)
    module_idx = build_module_index(nodes)
    test_edges = derive_test_edges(root, nodes, module_idx)
    module_edges = derive_module_import_edges(root, nodes, module_idx)

    test_paths = [p for p, n in nodes.items() if n["kind"] == "test"]
    results = run_tests(root, test_paths, timeout=test_timeout) if run_tests_flag else {
        "attempted": False, "reason": "--no-run-tests", "per_file": {}
    }

    schedule_map = load_schedule(schedule_file)
    gitnexus = read_gitnexus_index(root)
    entry_points = load_entry_points(entry_points_file, nodes)
    dead_code = dead_code_analysis(nodes, module_edges, test_edges, entry_points)
    add_dispositions(dead_code["candidates"], nodes, test_edges, root, lugs_dir)

    # --- per-node state assembly ---
    tested_by_path = {}
    for e in test_edges:
        tested_by_path.setdefault(e["code_path"], []).append(e)

    node_states = {}
    for rel_path, node in nodes.items():
        if node["kind"] == "test":
            continue
        edges_here = tested_by_path.get(rel_path, [])
        if not edges_here:
            node_states[rel_path] = {"tested": "UNTESTED", "proof": "UNPROVEN"}
            continue
        proven = "UNPROVEN"
        for e in edges_here:
            res = _normalize_test_result_key(e["test_path"], results["per_file"])
            if res and res.get("pass", 0) > 0:
                proven = "PROVEN"
                break
            if res and res.get("fail", 0) > 0:
                proven = "PROVEN"  # a failing-but-executed test still PROVES the edge ran
        node_states[rel_path] = {"tested": "TESTED", "proof": proven}

    schedule_states = {}
    for rel_path in test_paths:
        schedule_states[rel_path] = schedule_for(rel_path, schedule_map)

    overlay = overlay_lugs(lugs_dir, nodes)

    node_count_modules = sum(1 for n in nodes.values() if n["kind"] != "test")
    tested_count = sum(1 for s in node_states.values() if s["tested"] == "TESTED")
    proven_count = sum(1 for s in node_states.values() if s["proof"] == "PROVEN")
    scheduled_count = sum(1 for s in schedule_states.values() if s["status"] == "SCHEDULED")

    scoring_mode = "trajectory" if node_count_modules <= GREENFIELD_NODE_THRESHOLD else "absolute"
    every_node_has_disposition = all(
        rel_path in node_states for rel_path, n in nodes.items() if n["kind"] != "test"
    )

    # --- provenance merge (Ruling 33) ---
    # `nodes` is the DISCOVERED layer, freshly regenerated from disk. The collaborated
    # layer is loaded from its durable store and CARRIED. Until this call existed,
    # merge_provenance was tested code that no derivation ever ran -- the graph could not
    # emit runway, and every node was silently unclassified.
    #
    # Runs BEFORE functional_identity because the scorecard reports its counts, and a
    # number the scorecard cannot see is a number nobody acts on.
    provenance = merge_provenance(nodes, load_collaborated(collaborated_file))
    provenance_counts = {
        "runway": provenance["runway"],
        "rejected": provenance["rejected"],
        "collaborated": sum(1 for n in provenance["nodes"].values()
                            if n.get("provenance") == COLLABORATED),
    }

    functional_identity = {
        "node_count": node_count_modules,
        "tested_count": tested_count,
        "tested_fraction": (tested_count / node_count_modules) if node_count_modules else None,
        "proven_count": proven_count,
        "proven_fraction": (proven_count / node_count_modules) if node_count_modules else None,
        "test_edge_count": len(test_edges),
        "scheduled_count": scheduled_count,
        "scheduled_fraction": (scheduled_count / len(test_paths)) if test_paths else None,
        "unresolvable_claims_count": len(overlay["backlog_candidates"]),
        "dead_code_status": dead_code["status"],
        "dead_code_proposal_count": sum(
            1 for c in dead_code["candidates"] if c["safe_to_act"] == "PROPOSAL"
        ),
        "dead_code_question_count": sum(
            1 for c in dead_code["candidates"] if c["safe_to_act"] == "QUESTION"
        ),
        "entry_point_count": len(entry_points) if entry_points is not None else None,
        "dead_code_adopt_count": sum(
            1 for c in dead_code["candidates"] if c.get("disposition") == "ADOPT"
        ),
        "dead_code_deprecate_count": sum(
            1 for c in dead_code["candidates"] if c.get("disposition") == "DEPRECATE"
        ),
        "dead_code_undecided_count": sum(
            1 for c in dead_code["candidates"] if c.get("disposition") == "UNDECIDED"
        ),
        "scoring_mode": scoring_mode,
        "every_node_has_disposition": every_node_has_disposition,
        # Runway is unlanded intent whose takeoff is already recorded. Counting it here
        # rather than only in the snapshot body means it shows up wherever the scorecard
        # is read -- a number nobody surfaces is a number nobody acts on.
        "runway_count": len(provenance_counts["runway"]),
        "collaborated_count": provenance_counts["collaborated"],
        "provenance_rejected_count": len(provenance_counts["rejected"]),
        "greenfield_note": (
            "small project (<= {} modules): scored on trajectory + disposition "
            "presence, not absolute coverage -- see Ruling 28.5".format(GREENFIELD_NODE_THRESHOLD)
            if scoring_mode == "trajectory" else None
        ),
    }

    # provenance_nodes is a SEPARATE key, never a replacement for `nodes`: every existing
    # reader (diff_snapshots, dead_code, the rename detector) indexes `nodes` by path and
    # expects only code there. Folding collaborated records in would make a
    # conversation-derived node look like a file to a rename detector.
    snapshot = {
        "schema_version": 1,
        "root": str(root),
        "nodes": nodes,
        "provenance_nodes": provenance["nodes"],
        "runway": provenance["runway"],
        "provenance_rejected": provenance["rejected"],
        "node_states": node_states,
        "test_edges": test_edges,
        "module_edges": module_edges,
        "results": results,
        "schedule": schedule_states,
        "dead_code": dead_code,
        "overlay": overlay,
        "gitnexus_index": gitnexus,
        "functional_identity": functional_identity,
    }
    return snapshot


# --------------------------------------------------------------------------------------
# Delta (28.4) + rename detection (28.1)
# --------------------------------------------------------------------------------------

def diff_snapshots(prev: dict, cur: dict) -> dict:
    prev_nodes = prev.get("nodes", {})
    cur_nodes = cur.get("nodes", {})

    prev_by_content = {}
    for path, n in prev_nodes.items():
        prev_by_content.setdefault(n["node_id"], []).append(path)
    prev_by_shape = {}
    for path, n in prev_nodes.items():
        if n.get("symbol_shape_hash"):
            prev_by_shape.setdefault(n["symbol_shape_hash"], []).append(path)

    prev_paths = set(prev_nodes.keys())
    cur_paths = set(cur_nodes.keys())

    added_paths = cur_paths - prev_paths
    removed_paths = prev_paths - cur_paths

    moved = []
    truly_added = set(added_paths)
    truly_removed = set(removed_paths)

    for new_path in sorted(added_paths):
        n = cur_nodes[new_path]
        # exact content match against a now-missing path -> confident MOVE
        candidates = [p for p in prev_by_content.get(n["node_id"], []) if p in truly_removed]
        derivation = "content_hash"
        if not candidates and n.get("symbol_shape_hash"):
            shape_candidates = [
                p for p in prev_by_shape.get(n["symbol_shape_hash"], []) if p in truly_removed
            ]
            # only trust a shape-only match when it is unambiguous
            if len(shape_candidates) == 1:
                candidates = shape_candidates
                derivation = "symbol_shape"
        if candidates:
            old_path = sorted(candidates)[0]
            moved.append({"from": old_path, "to": new_path, "state": "MOVED", "derivation": derivation})
            truly_added.discard(new_path)
            truly_removed.discard(old_path)

    # test-edge deltas, keyed by code path (post-move: map old removed path -> new path)
    rename_map = {m["from"]: m["to"] for m in moved}

    def _canon(path):
        return rename_map.get(path, path)

    prev_tested = {e["code_path"] for e in prev.get("test_edges", [])}
    cur_tested = {e["code_path"] for e in cur.get("test_edges", [])}
    prev_tested_canon = {_canon(p) for p in prev_tested}

    newly_untested = sorted(prev_tested_canon - cur_tested)
    newly_tested = sorted(cur_tested - prev_tested_canon)

    prev_callers = {}
    for e in prev.get("module_edges", []):
        prev_callers.setdefault(e["to"], set()).add(e["from"])
    cur_callers = {}
    for e in cur.get("module_edges", []):
        cur_callers.setdefault(e["to"], set()).add(e["from"])

    lost_all_callers = sorted(
        target for target, callers in prev_callers.items()
        if callers and not cur_callers.get(_canon(target))
        and _canon(target) not in truly_removed
    )
    gained_caller = sorted(
        target for target, callers in cur_callers.items()
        if callers and target not in prev_callers and target not in {m["to"] for m in moved}
    )

    return {
        "added": sorted(truly_added),
        "removed": sorted(truly_removed),
        "moved": moved,
        "newly_untested": newly_untested,
        "newly_tested": newly_tested,
        "lost_all_callers": lost_all_callers,
        "gained_caller": gained_caller,
    }


# --------------------------------------------------------------------------------------
# JSON-safe serialization (sets -> sorted lists)
# --------------------------------------------------------------------------------------

def _json_default(obj):
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"not JSON serializable: {type(obj)}")


def to_json(obj, indent=2) -> str:
    return json.dumps(obj, indent=indent, sort_keys=True, default=_json_default)


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def _cmd_derive(args):
    root = Path(args.root)
    snapshot = derive_graph(
        root,
        entry_points_file=args.entry_points,
        schedule_file=args.schedule_file,
        lugs_dir=args.lugs_dir,
        collaborated_file=getattr(args, "collaborated_file", None),
        run_tests_flag=not args.no_run_tests,
        test_timeout=args.test_timeout,
    )
    delta = None
    if args.prev:
        prev_path = Path(args.prev)
        if prev_path.exists():
            prev_snapshot = json.loads(prev_path.read_text(encoding="utf-8"))
            delta = diff_snapshots(prev_snapshot, snapshot)
    output = dict(snapshot)
    if delta is not None:
        output["delta"] = delta
    if args.out:
        Path(args.out).write_text(to_json(output) + "\n", encoding="utf-8")
    if args.json or not args.out:
        print(to_json(output if args.full else _summary_view(output)))
    return 0


def _cmd_derive_entry_points(args):
    root = Path(args.root).resolve()
    nodes = scan_project(root)
    registry = derive_entry_points_registry(root, nodes, settings_file=args.settings)
    text = to_json(registry) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    if args.json or not args.out:
        print(text, end="")
    return 0


def _summary_view(snapshot: dict) -> dict:
    """The DEFAULT read. What is absent here is, in practice, invisible.

    `runway` and `provenance_rejected` are included deliberately. Runway is unlanded
    intent whose takeoff is already recorded -- the single most actionable thing the graph
    produces -- and leaving it to --full would have reproduced the exact pattern this
    wheel keeps repeating: build the mechanism, then surface it nowhere and wonder why
    nothing acts on it. Rejected records are included for the same reason inverted: a
    record the gate threw out must not vanish quietly, or the gate becomes a shredder.

    `provenance_nodes` stays OUT: it is the full node map again, which would bloat the
    summary back into the thing --full exists for.
    """
    keys = ["schema_version", "root", "functional_identity", "dead_code", "overlay",
            "gitnexus_index", "runway", "provenance_rejected", "delta"]
    return {k: snapshot[k] for k in keys if k in snapshot}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pathgraph_derive.py",
        description="Derive a PathGraph (code nodes, test edges, results, schedule, "
                     "intent overlay) from a project's code and tests. Works with zero "
                     "WAI history.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("derive", help="derive a PathGraph snapshot for a project root")
    d.add_argument("--root", required=True, help="project root to scan")
    d.add_argument("--out", help="write full snapshot JSON to this path")
    d.add_argument("--prev", help="previous snapshot JSON, for delta/rename detection")
    d.add_argument("--entry-points", help="JSON file declaring the entry-point set (28.2)")
    d.add_argument("--schedule-file", help="JSON file mapping test paths/globs to cadence")
    d.add_argument("--lugs-dir", help="legacy lug corpus to overlay (read-only, optional)")
    d.add_argument("--collaborated-file", dest="collaborated_file",
                   help="durable store of COLLABORATED nodes -- conversation-derived reasoning "
                        "that a rebuild must carry, never regenerate (Ruling 33). Optional: a "
                        "brownfield project has none, and absence is not an error.")
    d.add_argument("--no-run-tests", action="store_true", help="skip test execution (static only)")
    d.add_argument("--test-timeout", type=int, default=120)
    d.add_argument("--json", action="store_true", help="print summary JSON to stdout")
    d.add_argument("--full", action="store_true", help="print the full snapshot to stdout, not the summary")
    d.set_defaults(func=_cmd_derive)

    e = sub.add_parser(
        "derive-entry-points",
        help="derive an entry-point registry (28.2) from settings.json hook bindings, "
             "__main__ guards, and the live crontab -- writes the shape consumed by "
             "`derive --entry-points`",
    )
    e.add_argument("--root", required=True, help="project root to scan")
    e.add_argument("--settings", help="path to .claude/settings.json (default: <root>/.claude/settings.json)")
    e.add_argument("--out", help="write the registry JSON to this path")
    e.add_argument("--json", action="store_true", help="print the registry JSON to stdout")
    e.set_defaults(func=_cmd_derive_entry_points)

    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
