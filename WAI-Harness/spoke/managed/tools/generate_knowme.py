#!/usr/bin/env python3
"""Generate KnowMe.md for any WAI spoke using Claude Haiku.

Reads project context from WAI-State.json, CLAUDE.md, and CHANGELOG.md,
then calls the Anthropic API to synthesize a compact cold-start orientation file.

Usage:
    python3 tools/generate_knowme.py [--spoke-path PATH] [--dry-run]

Options:
    --spoke-path PATH   Root of the spoke to generate for (default: cwd)
    --dry-run           Print context package and exit; do not call API or write files
"""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

HAIKU_MODEL = "claude-haiku-4-5-20251001"
PROMPT_FILE = Path(__file__).parent / "knowme_prompt.md"

# Where a spoke's self-portrait may live, in resolution order. A spoke has ONE.
# README.md is listed first because a portrait the reader already opens beats one
# they must be told about — but the declared path in WAI-State.json wins over both.
PORTRAIT_CANDIDATES = (
    Path("README.md"),
    Path("KnowMe.md"),
    Path("WAI-Harness/dev/root-docs/KnowMe.md"),
)
# A stub is a pointer, not a portrait: it must not count as an existing portrait
# and must not block a real one being written.
STUB_MARKERS = ("superseded", "no longer maintained")


def _is_stub(path: Path) -> bool:
    try:
        head = path.read_text(errors="replace")[:600].lower()
    except OSError:
        return False
    return any(m in head for m in STUB_MARKERS)


def resolve_portrait_destination(spoke_path: Path):
    """Return (destination, conflict) for this spoke's single portrait.

    `destination` is where the portrait should be written. `conflict` is a
    DIFFERENT path that already holds a real (non-stub) portrait, or None.

    Resolution order:
      1. wheel.portrait_path in WAI-State.json — an explicit operator decision.
      2. The first existing non-stub candidate — respect where the spoke already
         keeps it rather than relocating it silently.
      3. KnowMe.md — the historical default, for a spoke that has none yet.

    The conflict return is the point of the function. Writing a portrait beside
    an existing one is how a repo ends up with two, drifting apart, both read as
    authoritative — measured on mywheel 2026-08-01, eight minor versions apart.
    """
    declared = None
    state_file = spoke_path / "WAI-Harness" / "spoke" / "local" / "WAI-State.json"
    if not state_file.exists():
        state_file = spoke_path / "WAI-Harness" / "spoke" / "WAI-State.json"
    if state_file.exists():
        try:
            declared = (json.loads(state_file.read_text())
                        .get("wheel", {}).get("portrait_path"))
        except (json.JSONDecodeError, OSError):
            declared = None

    existing = [spoke_path / c for c in PORTRAIT_CANDIDATES
                if (spoke_path / c).exists() and not _is_stub(spoke_path / c)]

    if declared:
        dest = spoke_path / declared
    elif existing:
        dest = existing[0]
    else:
        dest = spoke_path / "KnowMe.md"

    conflict = next((p for p in existing if p.resolve() != dest.resolve()), None)
    return dest, conflict


# ---------------------------------------------------------------------------
# Context extraction
# ---------------------------------------------------------------------------

def load_state(spoke_path: Path) -> dict:
    state_file = spoke_path / "WAI-Spoke" / "WAI-State.json"
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text())
    except json.JSONDecodeError as e:
        print(f"[generate_knowme] WARNING: WAI-State.json parse error: {e}", file=sys.stderr)
        return {}


def extract_claude_md_rules(spoke_path: Path, max_chars: int = 500) -> str:
    claude_md = spoke_path / "CLAUDE.md"
    if not claude_md.exists():
        return "(no CLAUDE.md found)"
    text = claude_md.read_text()
    # Extract the Critical Rules section if present
    match = re.search(r"## Critical Rules.*?(?=\n## |\Z)", text, re.DOTALL)
    if match:
        excerpt = match.group(0).strip()
    else:
        # Fall back to first max_chars characters
        excerpt = text.strip()
    return excerpt[:max_chars]


def extract_changelog(spoke_path: Path, max_entries: int = 3) -> str:
    changelog = spoke_path / "CHANGELOG.md"
    if not changelog.exists():
        return "(no CHANGELOG.md found)"
    text = changelog.read_text()
    # Split on version headers: ## v or ## [version]
    entries = re.split(r"\n(?=## (?:v|\[))", text)
    recent = [e.strip() for e in entries if e.strip()][:max_entries]
    return "\n\n".join(recent) if recent else "(no entries found)"


def count_lugs(spoke_path: Path) -> dict[str, int]:
    bytype = spoke_path / "WAI-Spoke" / "lugs" / "bytype"
    counts: dict[str, int] = {}
    if not bytype.exists():
        return counts
    for type_dir in sorted(bytype.iterdir()):
        if not type_dir.is_dir():
            continue
        for status in ("open", "in_progress"):
            status_dir = type_dir / status
            try:
                n = len(list(status_dir.glob("*.json")))
                if n:
                    counts[f"{type_dir.name}/{status}"] = n
            except (FileNotFoundError, PermissionError):
                pass
    return counts


def build_context(spoke_path: Path, state: dict) -> str:
    wheel = state.get("wheel", {})
    pf = state.get("_project_foundation", {})
    identity = pf.get("identity", {})
    ss = state.get("_session_state", {})

    name = wheel.get("name") or identity.get("name") or "Unknown"
    version = wheel.get("version", "Unknown")
    phase = state.get("context", {}).get("current_phase") or "Unknown"
    node_type = wheel.get("node_type", "spoke")
    one_liner = identity.get("one_liner") or wheel.get("one_liner") or "Unknown / To Confirm"
    session_count = ss.get("session_count", "Unknown")

    lug_counts = count_lugs(spoke_path)
    epics = sum(v for k, v in lug_counts.items() if k.startswith("epic/"))
    features = sum(v for k, v in lug_counts.items() if k.startswith("feature/"))
    other_open = sum(v for k, v in lug_counts.items()
                     if not k.startswith(("epic/", "feature/")))

    claude_rules = extract_claude_md_rules(spoke_path)
    changelog = extract_changelog(spoke_path)

    lines = [
        "SPOKE CONTEXT",
        "=============",
        f"name:           {name}",
        f"phase:          {phase}",
        f"node_type:      {node_type}",
        f"version:        {version}",
        f"session_count:  {session_count}",
        f"one_liner:      {one_liner}",
        "",
        "OPEN WORK SUMMARY",
        f"  epics:        {epics}",
        f"  features:     {features}",
        f"  other:        {other_open}",
        "",
        "RECENT CHANGELOG (last 3 entries)",
        changelog,
        "",
        "CONSTRAINTS (from CLAUDE.md, critical rules excerpt, max 500 chars)",
        claude_rules,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def call_haiku(context_block: str, prompt_template: str, api_key: str) -> str:
    try:
        import anthropic
    except ImportError:
        print("[generate_knowme] ERROR: anthropic SDK not installed. Run: pip install anthropic",
              file=sys.stderr)
        sys.exit(1)

    full_prompt = f"{context_block}\n\n---\n\n{prompt_template}"
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": full_prompt}],
    )
    return message.content[0].text if message.content else ""


# ---------------------------------------------------------------------------
# WAI-State stamping
# ---------------------------------------------------------------------------

def stamp_state(spoke_path: Path, version: str) -> None:
    state_file = spoke_path / "WAI-Spoke" / "WAI-State.json"
    if not state_file.exists():
        return
    try:
        state = json.loads(state_file.read_text())
        ss = state.setdefault("_session_state", {})
        ss["knowme_last_generated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        ss["knowme_version"] = version
        ss["knowme_stale"] = False
        state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[generate_knowme] WARNING: could not stamp WAI-State.json: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spoke-path", default=".", help="Root of the spoke (default: cwd)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print context package and prompt; do not call API or write files")
    args = parser.parse_args()

    spoke_path = Path(args.spoke_path).resolve()
    if not spoke_path.exists():
        print(f"[generate_knowme] ERROR: spoke path does not exist: {spoke_path}", file=sys.stderr)
        return 1

    # Load prompt template
    if not PROMPT_FILE.exists():
        print(f"[generate_knowme] ERROR: prompt template not found: {PROMPT_FILE}", file=sys.stderr)
        return 1
    prompt_template = PROMPT_FILE.read_text()
    # Strip the header / system-context documentation — keep only the Prompt section content
    match = re.search(r"## Prompt\s*\n(.*)", prompt_template, re.DOTALL)
    prompt_body = match.group(1).strip() if match else prompt_template.strip()

    # Build context
    state = load_state(spoke_path)
    if not state:
        print(f"[generate_knowme] WARNING: WAI-State.json not found or empty at {spoke_path}",
              file=sys.stderr)
    context_block = build_context(spoke_path, state)

    if args.dry_run:
        print("=== CONTEXT PACKAGE ===")
        print(context_block)
        print("\n=== PROMPT (first 500 chars) ===")
        print(prompt_body[:500])
        return 0

    # API key
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("[generate_knowme] ERROR: ANTHROPIC_API_KEY environment variable not set",
              file=sys.stderr)
        return 1

    # Generate
    print(f"[generate_knowme] Calling {HAIKU_MODEL} for {spoke_path.name}...")
    try:
        content = call_haiku(context_block, prompt_body, api_key)
    except Exception as e:
        print(f"[generate_knowme] ERROR: API call failed: {e}", file=sys.stderr)
        return 1

    if not content.strip():
        print("[generate_knowme] ERROR: API returned empty content", file=sys.stderr)
        return 1

    # Write the portrait to the spoke's ONE portrait destination.
    #
    # This used to hardcode <spoke>/KnowMe.md, which quietly created a SECOND
    # portrait wherever a spoke already kept one elsewhere. mywheel measured the
    # result on 2026-08-01: README.md (the live portrait) had drifted eight minor
    # harness versions while dev/root-docs/KnowMe.md carried its own independent
    # version, and BOTH were being read as authoritative. Two writers and two
    # readers for one logical artifact is the defect; resolving a single
    # destination and refusing to write a competing one removes the class.
    # (fix-knowme-single-portrait-destination-v1)
    out_path, conflict = resolve_portrait_destination(spoke_path)
    if conflict is not None:
        print(
            "[generate_knowme] REFUSING to write a second portrait.\n"
            f"  would write : {out_path}\n"
            f"  already have: {conflict}\n"
            "  A spoke has one portrait. Point 'portrait_path' in WAI-State.json\n"
            "  at the one you want, or remove the other.",
            file=sys.stderr,
        )
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content if content.endswith("\n") else content + "\n")
    line_count = content.count("\n")
    print(f"[generate_knowme] Written: {out_path} ({line_count} lines)")

    # Stamp WAI-State
    version = state.get("wheel", {}).get("version", "unknown")
    stamp_state(spoke_path, version)
    print("[generate_knowme] Stamped WAI-State._session_state.knowme_last_generated_at")

    return 0


if __name__ == "__main__":
    sys.exit(main())
