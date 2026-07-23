#!/usr/bin/env python3
"""Audit existing track.jsonl files for corrupted (incomplete) entries.

Scans for entries with missing REQUIRED fields (marked by the validator as errors)
and produces a report identifying which sessions have corrupted data.

Usage:
    python3 audit_track_corruption.py [<base_dir>]
      base_dir: starting directory to scan for track.jsonl files (default: current dir)

Output:
    Writes report to track-corruption-audit.log with session/turn/field info.
    Returns 0 if audit completes (even if corruption found), 1 if audit fails.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import validate_track_buffer as _vtb
except ImportError:
    print("Error: validate_track_buffer.py not found in same directory", file=sys.stderr)
    sys.exit(1)


def audit_track_file(track_path: Path) -> list:
    """Scan a track.jsonl for corrupted entries. Returns list of (turn, errors)."""
    corrupted = []
    try:
        with track_path.open("r") as f:
            for line_num, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    # Malformed JSON — mark it.
                    corrupted.append((f"line-{line_num}", ["INVALID JSON"]))
                    continue

                # Skip non-turn entries (like metadata or special records).
                if entry.get("event") != "turn":
                    continue

                # Validate via the standard validator.
                result = _vtb.validate(entry, "")
                if result.get("errors"):
                    corrupted.append((entry.get("turn", f"line-{line_num}"), result.get("errors", [])))
    except Exception as e:
        print(f"Error reading {track_path}: {e}", file=sys.stderr)
        return []
    return corrupted


def main():
    base_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

    if not base_dir.is_dir():
        print(f"Error: {base_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    report_path = base_dir / "track-corruption-audit.log"
    corrupted_count = 0
    sessions_affected = 0

    try:
        with report_path.open("w") as report_f:
            report_f.write(f"Track Corruption Audit Report\n")
            report_f.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
            report_f.write(f"Scanning: {base_dir}\n")
            report_f.write("=" * 80 + "\n\n")

            # Find all track.jsonl files under base_dir.
            for track_path in sorted(base_dir.glob("**/track.jsonl")):
                corrupted = audit_track_file(track_path)
                if corrupted:
                    sessions_affected += 1
                    corrupted_count += len(corrupted)

                    # Extract session info from path (e.g. sessions/session-YYYYMMDD-HHMM/).
                    session_dir = track_path.parent.name
                    report_f.write(f"Session: {session_dir}\n")
                    report_f.write(f"Track: {track_path.relative_to(base_dir)}\n")
                    for turn, errors in corrupted:
                        report_f.write(f"  Turn {turn}: {len(errors)} errors\n")
                        for err in errors:
                            report_f.write(f"    - {err}\n")
                    report_f.write("\n")

            report_f.write("=" * 80 + "\n")
            report_f.write(f"Summary: {corrupted_count} corrupted entries in {sessions_affected} session(s)\n")

        print(f"Audit complete. Report: {report_path}")
        print(f"Found {corrupted_count} corrupted entries in {sessions_affected} session(s)")
        sys.exit(0)
    except Exception as e:
        print(f"Audit failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
