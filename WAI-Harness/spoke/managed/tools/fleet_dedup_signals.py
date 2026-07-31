#!/usr/bin/env python3
"""
Fleet Signal Deduplication Tool

Scans all spoke signal directories and removes redundant copies of signals,
keeping only the canonical version in the hub. Run periodically (e.g., weekly)
to prevent fleet-wide signal duplication accumulation.

Usage:
    python3 fleet_dedup_signals.py --dry-run    # Show what would be removed
    python3 fleet_dedup_signals.py               # Remove duplicate signals
    python3 fleet_dedup_signals.py --report      # Generate dedup report
"""

import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

HUB_DIR = Path("/home/mario/projects/wheelwright/mywheel/WAI-Harness/hub/local")
CANONICAL_SIGNAL_DIR = HUB_DIR / "WAI-Hub" / "lugs" / "bytype" / "signal" / "canonical"
HUB_REGISTRY = HUB_DIR / "hub-registry.json"

# Spokes to scan
ACTIVE_SPOKES = ["basher", "pathfinder", "solutions-by-mv", "minder", "website"]


def load_registry() -> Dict:
    """Load hub registry to find spoke paths."""
    try:
        with open(HUB_REGISTRY) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"wheels": []}


def get_spoke_paths() -> Dict[str, Path]:
    """Get paths for all active spokes."""
    registry = load_registry()
    spoke_paths = {}

    for wheel in registry.get("wheels", []):
        wheel_id = wheel.get("wheel_id")
        path = wheel.get("path")
        if wheel_id and path:
            spoke_paths[wheel_id] = Path(path)

    # Fallback to standard paths for spokes not in registry
    for spoke in ACTIVE_SPOKES:
        standard_path = Path(f"/home/mario/projects/{spoke}")
        if standard_path.exists() and spoke not in spoke_paths:
            spoke_paths[spoke] = standard_path

    return spoke_paths


def load_signal(path: Path) -> Dict:
    """Load a signal JSON file."""
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def get_spoke_signal_dirs(spoke_path: Path) -> List[Path]:
    """Get all signal directories in a spoke."""
    dirs = []
    for status in ["delivered", "undelivered"]:
        signal_dir = spoke_path / "WAI-Harness" / "spoke" / "local" / "lugs" / "bytype" / "signal" / status
        if signal_dir.exists():
            dirs.append(signal_dir)
    return dirs


def scan_spoke_signals(spoke_name: str, spoke_path: Path) -> Dict[str, List[Path]]:
    """Scan all signals in a spoke and group by signal ID."""
    signals_by_id = {}
    signal_dirs = get_spoke_signal_dirs(spoke_path)

    for signal_dir in signal_dirs:
        for signal_file in signal_dir.glob("*.json"):
            signal_id = signal_file.stem
            if signal_id not in signals_by_id:
                signals_by_id[signal_id] = []
            signals_by_id[signal_id].append(signal_file)

    return signals_by_id


def get_canonical_signal_ids() -> set:
    """Get the set of canonical signal IDs from the hub."""
    canonical_ids = set()
    if CANONICAL_SIGNAL_DIR.exists():
        for signal_file in CANONICAL_SIGNAL_DIR.glob("*.json"):
            canonical_ids.add(signal_file.stem)
    return canonical_ids


def archive_signal(signal_path: Path) -> Path:
    """Move a signal to a .retired suffix instead of deleting."""
    retired_path = signal_path.parent / f".retired-{signal_path.stem}-{datetime.now().isoformat()}.json"
    shutil.move(str(signal_path), str(retired_path))
    return retired_path


def dedup_fleet_signals(dry_run: bool = True) -> Tuple[int, int, List[str]]:
    """Scan all spokes and remove duplicate signals.

    Returns:
        (total_removed, total_retired, summary_lines)
    """
    spoke_paths = get_spoke_paths()
    canonical_ids = get_canonical_signal_ids()
    total_removed = 0
    summary = []

    for spoke_name, spoke_path in spoke_paths.items():
        if not spoke_path.exists():
            continue

        signals_by_id = scan_spoke_signals(spoke_name, spoke_path)
        spoke_removed = 0
        spoke_summary = []

        for signal_id, signal_paths in signals_by_id.items():
            # Skip signals without a canonical version (local signals)
            if signal_id not in canonical_ids:
                continue

            # If more than one copy exists, remove all but one
            if len(signal_paths) > 1:
                for extra_path in signal_paths[1:]:
                    if dry_run:
                        spoke_summary.append(f"  Would retire: {extra_path}")
                    else:
                        archive_signal(extra_path)
                        spoke_summary.append(f"  Retired: {extra_path}")
                    spoke_removed += 1
                    total_removed += 1

        if spoke_removed > 0:
            summary.append(f"{spoke_name}: {spoke_removed} duplicates {'would be retired' if dry_run else 'retired'}")
            summary.extend(spoke_summary)

    summary.insert(0, f"Total: {total_removed} duplicate signals {'would be' if dry_run else ''} retired")
    return total_removed, len(canonical_ids), summary


def generate_report() -> None:
    """Generate a detailed dedup report."""
    spoke_paths = get_spoke_paths()
    canonical_ids = get_canonical_signal_ids()
    report = {
        "timestamp": datetime.now().isoformat(),
        "canonical_signal_count": len(canonical_ids),
        "spokes": {},
    }

    for spoke_name, spoke_path in spoke_paths.items():
        if not spoke_path.exists():
            continue

        signals_by_id = scan_spoke_signals(spoke_name, spoke_path)
        spoke_info = {
            "total_signals": len(signals_by_id),
            "canonical_signals": 0,
            "local_signals": 0,
            "duplicates": 0,
        }

        for signal_id, signal_paths in signals_by_id.items():
            if signal_id in canonical_ids:
                spoke_info["canonical_signals"] += 1
                if len(signal_paths) > 1:
                    spoke_info["duplicates"] += len(signal_paths) - 1
            else:
                spoke_info["local_signals"] += 1

        report["spokes"][spoke_name] = spoke_info

    report_path = HUB_DIR / "WAI-Hub" / "lugs" / "bytype" / "signal" / "dedup_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fleet signal deduplication tool")
    parser.add_argument("--dry-run", action="store_true", help="Preview dedup without making changes")
    parser.add_argument("--report", action="store_true", help="Generate a detailed dedup report")
    args = parser.parse_args()

    if args.report:
        generate_report()
        return

    if not CANONICAL_SIGNAL_DIR.exists():
        print(f"Error: canonical signal directory not found at {CANONICAL_SIGNAL_DIR}")
        sys.exit(1)

    dry_run = args.dry_run
    removed, canonical_count, summary = dedup_fleet_signals(dry_run=dry_run)

    print("\n".join(summary))
    print(f"\nCanonical signals in hub: {canonical_count}")
    print(f"Dry-run: {dry_run}")

    if not dry_run:
        print("\nDedup complete. Duplicate signals have been retired (moved to .retired-* files).")


if __name__ == "__main__":
    main()
