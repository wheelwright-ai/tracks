"""Flush track-buffer.json to the current session's track.jsonl.

Harness-mode-aware: the calling Stop hook (stop-track-flush.sh) resolves the active
v3/v4 data tree via harness_mode.sh and exports WAI_TRACK_PATH — the absolute resolved
track.jsonl under that tree (WAI-Spoke/ in v3, WAI-Harness/spoke/local/ in v4). We honor
it. If unset (direct invocation), we fall back to the legacy v3 computation from
_session_state.track_path so the script still works standalone.

Usage: python3 flush_buffer.py <state_path> <buffer_path> <project_dir>
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# W1.6 re-stamp defense: hook-owned envelope fields that user-prompt-submit.sh
# pre-seeds every turn. If a model turn clobbers or omits one, this is a
# DETECTION mechanism (log it) not an enforcement gate — the flush always proceeds.
_HOOK_OWNED_KEYS = ("event", "turn", "source", "ts", "ts_source", "model")


def _check_restamp(entry, buffer_path):
    """Log (never raise/block) when hook-owned keys are missing or empty at flush
    time -- signals the model overwrote/omitted the hook's pre-seeded envelope."""
    try:
        missing = [k for k in _HOOK_OWNED_KEYS if k not in entry or entry.get(k) in (None, "")]
        if not missing:
            return
        log_path = Path(buffer_path).resolve().parent / "track-restamp-warnings.log"
        ts = datetime.now(timezone.utc).isoformat()
        with log_path.open("a") as f:
            f.write(f"{ts} restamp-warning missing/altered hook-owned keys={missing} buffer={buffer_path}\n")
    except Exception:
        pass  # detection is best-effort; must never affect the flush


def _resolve_track(state_path, project_dir):
    """Harness-resolved track path (env) wins; else legacy v3 from state."""
    env = os.environ.get("WAI_TRACK_PATH", "")
    if env:
        return Path(env)
    try:
        state = json.loads(Path(state_path).read_text())
        rel = state.get("_session_state", {}).get("track_path", "")
        if rel:
            return Path(project_dir) / rel
    except Exception:
        pass
    return None


def main() -> None:
    if len(sys.argv) < 4:
        return

    state_path, buffer_path, project_dir = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        track_path = _resolve_track(state_path, project_dir)
        if track_path is None:
            return

        track_path.parent.mkdir(parents=True, exist_ok=True)

        entry = json.loads(Path(buffer_path).read_text())

        # W1.6 re-stamp defense: detect (log-only, non-blocking) a clobbered/omitted
        # hook-owned envelope before the buffer is deleted below.
        _check_restamp(entry, buffer_path)

        # VALIDATE AND REJECT on missing REQUIRED fields. Best-effort — if the
        # validator is broken, log it and proceed (never block the turn).
        validation_passed = True
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import validate_track_buffer as _vtb
            _res = _vtb.validate(entry, _vtb._spoke_from_state(state_path))

            # Hard gate: reject writes with missing REQUIRED fields.
            if _res.get("errors"):
                validation_passed = False
                # Log the rejection with full context for audit/backfill.
                log_path = Path(buffer_path).resolve().parent / "track-validation-rejections.log"
                ts = datetime.now(timezone.utc).isoformat()
                session_id = "unknown"
                try:
                    state = json.loads(Path(state_path).read_text())
                    session_id = state.get("_session_state", {}).get("session_id", "unknown")
                except Exception:
                    pass
                turn_n = entry.get("turn", "?")
                errors_str = "; ".join(_res.get("errors", []))
                with log_path.open("a") as f:
                    f.write(f"{ts} REJECTED session={session_id} turn={turn_n} errors=[{errors_str}] buffer={buffer_path}\n")
                # Do NOT flush incomplete entries.
                return

            # Annotate with warnings even if valid (for soft-required fields).
            if _res.get("warnings"):
                entry = _res.get("annotated_entry", entry)
        except Exception as e:
            # Validator broken or missing — log and proceed (never block).
            log_path = Path(buffer_path).resolve().parent / "track-validation-errors.log"
            ts = datetime.now(timezone.utc).isoformat()
            with log_path.open("a") as f:
                f.write(f"{ts} validator-error {type(e).__name__}: {str(e)[:200]} buffer={buffer_path}\n")

        with track_path.open("a") as f:
            f.write(json.dumps(entry) + "\n")

        Path(buffer_path).unlink()
    except Exception:
        pass  # silent fail — track is best-effort


if __name__ == "__main__":
    main()
