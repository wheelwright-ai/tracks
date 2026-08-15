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


def main() -> bool:
    """Returns True iff a turn event was actually appended to track.jsonl.

    bug-track-records-zero-turns-and-mints-a-session-per-turn-v1 (MEASURED
    2026-08-06): commit 81fafd1ad turned validate_track_buffer's documented
    "ANNOTATE-don't-drop... never blocks a flush" contract into a hard reject —
    "Do NOT flush incomplete entries." Every turn this session lacked the
    model-authored rich fields (user_msg, thinking, ...), so EVERY turn was
    rejected, for a full day, with zero errors anywhere. The caller
    (stop-track-flush.sh) treated the buffer's mere on-disk PRESENCE as proof
    of a successful flush and set BUFFER_PRESENT=1 regardless — which told
    synthesize_turn.py's Layer-2 safety net "layer 1 already wrote this turn,
    nothing to do," so the net that exists specifically to catch this never
    fired either. Two independent layers, both silently defeated by one
    over-strict gate: the return value here is instrumentation FOR the caller
    to make BUFFER_PRESENT mean "actually flushed," not "file exists."

    Fix: honor the validator's own contract. A degraded (annotated,
    _validation-flagged) entry always lands — recoverable — instead of a
    perfect one or nothing, which was the unrecoverable failure mode Ruling 37
    scores at the top of the criticality scale.
    """
    if len(sys.argv) < 4:
        return False

    state_path, buffer_path, project_dir = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        track_path = _resolve_track(state_path, project_dir)
        if track_path is None:
            return False

        track_path.parent.mkdir(parents=True, exist_ok=True)

        entry = json.loads(Path(buffer_path).read_text())

        # W1.6 re-stamp defense: detect (log-only, non-blocking) a clobbered/omitted
        # hook-owned envelope before the buffer is deleted below.
        _check_restamp(entry, buffer_path)

        # VALIDATE AND ANNOTATE (never reject — validate_track_buffer.py's own
        # contract is "annotate-don't-drop": an incomplete entry still lands,
        # degraded and flagged, so it is recoverable instead of silently gone).
        # Best-effort — if the validator itself is broken, log it and proceed
        # with the entry unchanged (never block the turn).
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import validate_track_buffer as _vtb
            _res = _vtb.validate(entry, _vtb._spoke_from_state(state_path))

            if _res.get("errors"):
                # Log for audit/backfill visibility, but STILL FLUSH — degraded,
                # not dropped. Same log name kept for continuity with prior audit
                # trails; entries after this fix are DEGRADED-FLUSHED, not rejected.
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
                    f.write(f"{ts} DEGRADED-FLUSHED session={session_id} turn={turn_n} errors=[{errors_str}] buffer={buffer_path}\n")
                entry = _res.get("annotated_entry", entry)
            elif _res.get("warnings"):
                # Annotate with warnings even if valid (for soft-required fields).
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
        return True
    except Exception:
        return False  # silent fail — track is best-effort, but the caller must know


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
