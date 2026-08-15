#!/usr/bin/env python3
"""symbol_loss.py - detect NET SYMBOL LOSS between two versions of a file.

Built for impl-detect-harness-pull-reverts-before-they-commit-v1: a harness
pull (or a raw git operation) can silently overwrite a managed/ file with an
OLDER version. Bytes differ, but nothing about a byte-diff says "regression" —
it takes naming what disappeared to make that visible. That is what this module
computes: the set of top-level python `def`/`class` names, or shell `name()`
function names, present in a BEFORE text and absent from an AFTER text.

Deliberately narrow and stdlib-only:
  - python: module-level (non-nested) def/class names via `ast` (robust to
    formatting; a real parser, not a regex heuristic).
  - shell: `name()` / `function name` definitions at any indent, via regex —
    `ast` has no shell grammar in stdlib, and shell functions are not reliably
    nested the way python defs are, so indentation is not a useful filter here.

Reused by two callers (harness_upgrade.py's post-pull guard and
.claude/hooks/pre-commit-gate.sh's staged-diff check), which is why this lives
as its own importable module rather than inline in either.
"""
from __future__ import annotations

import ast
import re

# Which language a path implies, by suffix. Anything else -> no symbols (not
# an error; a lost .json/.md byte diff is not this module's concern).
_PY_SUFFIXES = (".py",)
_SH_SUFFIXES = (".sh", ".bash")

_SHELL_FUNC_RE = re.compile(
    r'^\s*(?:function\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\(\s*\))?|'
    r'([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\))\s*\{',
    re.MULTILINE,
)


def python_symbols(text):
    """Top-level (module-body, non-nested) def/class names in `text`.

    A SyntaxError (the after-text of a revert can be truncated/corrupt, or the
    text simply isn't valid python) yields an EMPTY set rather than raising —
    callers treat "could not parse" as "nothing provably lost", never as a
    crash. This mirrors the fail-safe posture of the rest of the harness tools:
    an unparseable file is reported upstream (verify_post/md5 already catches
    that), not double-reported here as a phantom symbol loss.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def shell_symbols(text):
    """`name() { ... }` / `function name { ... }` definitions anywhere in `text`."""
    names = set()
    for m in _SHELL_FUNC_RE.finditer(text):
        names.add(m.group(1) or m.group(2))
    return names


def symbols_for(text, filename):
    """Dispatch on filename suffix. Unknown suffix -> empty set (not an error;
    this module only ever asserts loss for languages it understands)."""
    name = (filename or "").lower()
    if name.endswith(_PY_SUFFIXES):
        return python_symbols(text)
    if name.endswith(_SH_SUFFIXES):
        return shell_symbols(text)
    return set()


def diff_symbols(before_text, after_text, filename):
    """{"lost": sorted[...], "gained": sorted[...]} for one file's before/after.

    `lost` = present before, absent after — this is the regression signal.
    `gained` is returned alongside for context/reporting (a rename shows up as
    one lost + one gained; see the DOCUMENTED decision in test_symbol_loss.py
    on why a rename is still reported as a loss — the module has no notion of
    "this def became that def", only "this name existed and now does not").
    """
    before_syms = symbols_for(before_text, filename)
    after_syms = symbols_for(after_text, filename)
    return {
        "lost": sorted(before_syms - after_syms),
        "gained": sorted(after_syms - before_syms),
    }


SUPERSESSION_FILE = "superseded-symbols.json"


def load_supersessions(managed_root):
    """Declared renames, as {relpath: {old_name: new_name}}. Missing file -> {}.

    WHY DECLARED AND NOT DETECTED, measured 2026-08-11. hub could not upgrade: the guard
    named test_install_ships_always_clean_gitignore and
    test_overloaded_counts_only_human_items as lost, and both had been RENAMED on purpose in
    commit ed32cb4c3, one of them with its assertion deliberately inverted because the old
    version narrowed an alarm until it could never fire. The guard was not wrong about the
    bytes; it has no notion of "this def became that def", as its own diff_symbols docstring
    says. Every spoke on an older cut would refuse for the same two names forever.

    The alternative was matching renames by body similarity, which is a guess, and this
    module exists because guessing about regressions is how the regressions got through. A
    supersession is a claim the AUTHOR makes, in the open, in canon, next to the code.
    """
    import json as _json
    from pathlib import Path as _Path
    path = _Path(managed_root) / SUPERSESSION_FILE
    try:
        doc = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(doc, dict):
        return {}
    out = {}
    for entry in doc.get("supersessions") or []:
        if not isinstance(entry, dict):
            continue
        rel, was, now = entry.get("file"), entry.get("was"), entry.get("now")
        if rel and was and now:
            out.setdefault(str(rel), {})[str(was)] = str(now)
    return out


def net_symbol_loss(before_text, after_text, filename, supersessions=None):
    """Convenience: just the sorted list of lost symbol names (may be empty).

    `supersessions`: {old_name: new_name} for THIS file. A lost symbol is forgiven only when
    its declared successor is actually PRESENT in after_text. That second condition is the
    load-bearing one: without it a stale declaration would mask a genuine deletion forever,
    and the escape hatch would have quietly become a permanent hole in the guard.
    """
    lost = diff_symbols(before_text, after_text, filename)["lost"]
    if not supersessions:
        return lost
    after_syms = symbols_for(after_text, filename)
    return [name for name in lost
            if supersessions.get(name) not in after_syms]


def scan_for_loss(file_pairs):
    """file_pairs: iterable of (relpath, before_text, after_text).

    Returns {relpath: [lost symbol names]} for every file with non-empty loss.
    Files with no loss (including files this module doesn't understand) are
    simply absent from the result — an empty dict means "no net symbol loss
    found", the HALT-worthy signal callers check for.
    """
    out = {}
    for relpath, before_text, after_text in file_pairs:
        lost = net_symbol_loss(before_text, after_text, relpath)
        if lost:
            out[relpath] = lost
    return out
