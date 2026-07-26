#!/usr/bin/env python3
"""taste_contract.py — the always-on communication contract (TasteGraph Tier A).

THE PROBLEM (measured s138, felt again 2026-07-24): TasteGraph injection is
non-binding. Prefs get sampled as a sparse per-activity vector and compete with
everything else as suggestion, so the ONE class that must always hold — how to
speak to this operator — gets dropped. The operator caught it directly: emojis,
trailing summaries, a "7 questions" count that did not match what was shown, and
an ADHD/dyslexia access requirement that was not in the taste system at all.

THE FIX (two-tier taste):
  Tier A — this file. The small, stable set of communication/accessibility prefs
    that must bind EVERY turn. Rendered as an imperative contract and injected on
    the same per-turn rail as the track obligations (user-prompt-submit.sh), which
    is the rail that provably binds. Terse by design: it is paid on every turn.
  Tier B — tastegraph_vector.py. The large rotating domain/approach/workflow prefs.
    Sampling is fine there; those are suggestions, not a contract.

SELECTION: any taste.user.yaml entry with `binding: always_on` and status accepted.
Each emits its short `directive` (falls back to a truncated `preference`). Editing
the contract = marking/unmarking entries in taste.user.yaml. One source of truth.

CLI:
    taste_contract.py            # emit the injectable contract block (empty if none)
    taste_contract.py --list     # show which entries are in the contract
    taste_contract.py --taste PATH   # override the taste file location
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_MASTER = Path("/home/mario/projects/wheelwright/mywheel/WAI-Harness")
_MAX_DIRECTIVE = 240   # a per-turn cost; keep each line short


def _taste_path() -> Path:
    env = os.environ.get("WAI_TASTE_FILE")
    if env:
        return Path(env)
    master = Path(os.environ.get("WAI_HARNESS_MASTER", str(DEFAULT_MASTER)))
    return master / "hub" / "local" / "taste.user.yaml"


def _load_entries(path: Path) -> list:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        import yaml  # PyYAML is present in the harness env
        doc = yaml.safe_load(text) or {}
        return doc.get("entries", []) or []
    except Exception:
        # Never let a bad taste file break the per-turn hook — degrade to no contract.
        return []


def always_on(entries: list) -> list:
    """The Tier-A set: accepted entries flagged binding: always_on, in file order."""
    out = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if e.get("binding") != "always_on":
            continue
        if e.get("status") not in (None, "accepted"):
            continue
        text = (e.get("directive") or e.get("preference") or "").strip()
        if not text:
            continue
        if len(text) > _MAX_DIRECTIVE:
            text = text[: _MAX_DIRECTIVE - 1].rstrip() + "…"
        out.append({"id": e.get("id", "?"), "text": text})
    return out


def render(items: list) -> str:
    """The injectable block. Empty string when there is nothing to bind."""
    if not items:
        return ""
    lines = [
        "<wai-voice-contract>",
        "How to communicate with this operator (a BINDING contract, not a suggestion — "
        "the same weight as the track obligations above). Apply every turn:",
    ]
    for i, it in enumerate(items, 1):
        lines.append(f"  {i}. {it['text']}")
    lines.append("If you cannot honor one this turn, say so plainly rather than ignoring it.")
    lines.append("</wai-voice-contract>")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="show the contract entries, not the block")
    ap.add_argument("--taste", default=None, help="override taste.user.yaml path")
    args = ap.parse_args()

    path = Path(args.taste) if args.taste else _taste_path()
    items = always_on(_load_entries(path))

    if args.list:
        if not items:
            print("(no always_on entries)")
            return 0
        for it in items:
            print(f"{it['id']}: {it['text']}")
        return 0

    block = render(items)
    if block:
        print(block)
    return 0


if __name__ == "__main__":
    sys.exit(main())
