#!/usr/bin/env python3
"""
wai-savepoints — List savepoints with lug status from disk.

Lists all savepoints from WAI-State.json _savepoints array with current disk status.

Usage:
    wai_savepoints.py [--spoke-path PATH]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List


def interrogate(root: Path) -> Optional[tuple]:
    """Given a SPOKE ROOT, return (state_dir, layout) or None.

    OPERATOR RULING 2026-08-14: expect v6, and on meeting an older spoke DETECT and
    interrogate it rather than assume a layout. v6 REUSES the name `WAI-Spoke`, so the
    kernel's installed.json marker — not directory presence — separates v6 from v3.
    Order matters: a v6 spoke usually ALSO carries a WAI-Harness tree, so checking the
    marker first is what stops it reading as v4.
    """
    root = Path(root)
    if root.joinpath("WAI-Spoke/installed.json").is_file() and \
       root.joinpath("WAI-Spoke/WAI-State.json").is_file():
        return (root / "WAI-Spoke", "v6")
    if root.joinpath("WAI-Harness/spoke/local/WAI-State.json").is_file():
        return (root / "WAI-Harness/spoke/local", "v4")
    if root.joinpath("WAI-Spoke/WAI-State.json").is_file():
        return (root / "WAI-Spoke", "v3")
    # The root may itself BE the state dir (callers that pass a resolved local/ tree).
    if root.joinpath("WAI-State.json").is_file():
        return (root, "state-dir")
    return None


def resolve_spoke_path(root: Optional[Path] = None) -> tuple:
    """Resolve (state_dir, layout) from a spoke root, else by searching upward."""
    if root is not None:
        found = interrogate(root)
        if found:
            return found
        return (Path(root), "unresolved")

    current = Path.cwd()
    for _ in range(10):
        found = interrogate(current)
        if found:
            return found
        if current == current.parent:
            break
        current = current.parent

    return (Path("WAI-Harness/spoke/local"), "unresolved")


def load_state(spoke_path: Path) -> Optional[Dict[str, Any]]:
    """Load WAI-State.json."""
    state_file = spoke_path / "WAI-State.json"
    if not state_file.exists():
        return None

    try:
        with open(state_file) as f:
            return json.load(f)
    except Exception:
        return None


def find_lug_file(spoke_path: Path, lug_id: str) -> Optional[Path]:
    """Find lug file in bytype directory structure."""
    lugs_dir = spoke_path / "lugs" / "bytype"
    if not lugs_dir.exists():
        return None

    # Search in all type directories
    for type_dir in lugs_dir.iterdir():
        if not type_dir.is_dir():
            continue

        # Search in status directories
        for status_dir in type_dir.iterdir():
            if not status_dir.is_dir():
                continue

            # Try pattern: {lug_id}.json
            lug_file = status_dir / f"{lug_id}.json"
            if lug_file.exists():
                return lug_file

            # Try pattern: {lug_id}.{status}.json (some files have status suffix)
            for f in status_dir.glob(f"{lug_id}.*"):
                if f.is_file() and f.suffix == ".json":
                    return f

    return None


def get_lug_title(lug_file: Optional[Path]) -> str:
    """Extract title from lug file."""
    if not lug_file or not lug_file.exists():
        return "[missing]"

    try:
        with open(lug_file) as f:
            lug = json.load(f)
            title = lug.get("title")
            if not title:
                return "--"
            # Truncate if too long for table display
            max_len = 60
            if len(title) > max_len:
                return title[:max_len - 3] + "..."
            return title
    except Exception:
        return "[error]"


def get_disk_status(spoke_path: Path, lug_id: str) -> str:
    """Get the disk status of a lug (open/in_progress/completed/etc)."""
    lugs_dir = spoke_path / "lugs" / "bytype"
    if not lugs_dir.exists():
        return ""

    # Search in all type directories
    for type_dir in lugs_dir.iterdir():
        if not type_dir.is_dir():
            continue

        # Check in status directories
        for status_dir in type_dir.iterdir():
            if not status_dir.is_dir():
                continue

            # Try pattern: {lug_id}.json
            lug_file = status_dir / f"{lug_id}.json"
            if lug_file.exists():
                return status_dir.name

            # Try pattern: {lug_id}.{status}.json (some files have status suffix)
            for f in status_dir.glob(f"{lug_id}.*"):
                if f.is_file() and f.suffix == ".json":
                    return status_dir.name

    return ""


def format_date(date_str: Optional[str]) -> str:
    """Format ISO date to short date string."""
    if not date_str:
        return ""

    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return date_str[:10] if len(date_str) >= 10 else date_str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List savepoints with lug status from disk"
    )
    parser.add_argument(
        "--spoke-path",
        type=Path,
        default=None,
        help="Path to spoke root (auto-detected if not specified)",
    )
    args = parser.parse_args()

    # Resolve spoke path. --spoke-path names the spoke ROOT and is INTERROGATED, not
    # used verbatim as the state dir — passing a v6 spoke root used to fail outright.
    spoke_path, layout = resolve_spoke_path(args.spoke_path)

    # Load state
    state = load_state(spoke_path)
    if not state:
        print(
            f"Error: no WAI-State.json found for {args.spoke_path or Path.cwd()} "
            f"(layout={layout}; looked for v6 WAI-Spoke/installed.json+WAI-State.json, "
            f"v4 WAI-Harness/spoke/local/WAI-State.json, v3 WAI-Spoke/WAI-State.json)",
            file=sys.stderr,
        )
        sys.exit(1)
    # Always name the store that was read. A bare "No savepoints recorded." is ambiguous
    # between "none pending" and "read the wrong tree" — never leave that unstated.
    print(f"[layout: {layout}] {spoke_path}", file=sys.stderr)

    # Get savepoints array
    savepoints = state.get("_savepoints", [])

    # No savepoints
    if not savepoints:
        print("No savepoints recorded.")
        return

    # Print header
    print(
        f"{'ID':<12} | {'Title':<62} | {'Saved At':<10} | {'Status':<12} | {'Disk Status':<15}"
    )
    print("-" * 120)

    # Print each savepoint
    for sp in savepoints:
        lug_id = sp.get("lug_id") or "--"
        saved_at = format_date(sp.get("saved_at"))
        entry_status = sp.get("status", "unknown")

        # For lookup, use actual lug_id if present
        actual_lug_id = sp.get("lug_id")
        if actual_lug_id:
            lug_file = find_lug_file(spoke_path, actual_lug_id)
            title = get_lug_title(lug_file)
            disk_status = get_disk_status(spoke_path, actual_lug_id)
        else:
            title = "--"
            disk_status = ""

        # Truncate lug_id for display
        display_id = lug_id if len(lug_id) <= 12 else lug_id[:9] + "..."

        print(
            f"{display_id:<12} | {title:<62} | {saved_at:<10} | {entry_status:<12} | {disk_status:<15}"
        )


if __name__ == "__main__":
    main()
