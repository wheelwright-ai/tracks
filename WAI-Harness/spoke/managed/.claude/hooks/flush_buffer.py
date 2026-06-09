"""Flush track-buffer.json to the current session's track.jsonl.

Usage: python3 flush_buffer.py <state_path> <buffer_path> <project_dir>
"""
import json
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 4:
        return

    state_path, buffer_path, project_dir = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        state = json.loads(Path(state_path).read_text())
        track_rel = state.get("_session_state", {}).get("track_path", "")
        if not track_rel:
            return

        track_path = Path(project_dir) / track_rel
        track_path.parent.mkdir(parents=True, exist_ok=True)

        entry = json.loads(Path(buffer_path).read_text())
        with track_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

        Path(buffer_path).unlink()
    except Exception:
        pass  # silent fail — track is best-effort


if __name__ == "__main__":
    main()
