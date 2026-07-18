"""Validate a track-buffer entry before it is flushed to track.jsonl.

The measurable "full-feature" gate from spec-wai-track-collection-v2.0.2: an entry is
full-feature iff source='model' AND every REQUIRED-every-turn field is present and
non-empty. This validator is ANNOTATE-don't-drop: it never blocks a flush — it returns
the entry annotated with a slim `_validation` note so an incomplete buffer still lands
(degraded), and a complete one passes clean.

Returns a dict:
  ok: bool                 — no required-field errors
  errors: [str]            — REQUIRED field failures
  warnings: [str]          — soft-required / quality gaps
  annotated_entry: dict    — the entry with a slim `_validation` note when not clean

Usage (standalone):  python3 validate_track_buffer.py <buffer_path> [<state_path>]
Integrated (flush):  from validate_track_buffer import validate; validate(entry, spoke)
PostToolUse hook:     piped CC hook JSON on stdin (real-time same-turn repair signal).
"""
import json
import sys
from pathlib import Path

# v2.0.2 envelope + required-every-turn set. `source` is the full-feature discriminator
# (must be 'model'); ts_source records the clock provenance (SI1 — no invented time).
REQUIRED = [
    "event", "turn", "source", "ts", "ts_source",
    "phase", "focus",
    "user_msg", "user_intent",
    "action", "outcome", "thinking",
]

# v2.0.2 soft-required: emit unless genuinely empty this turn.
SOFT_REQUIRED = ["decisions", "insights", "open"]

VALID_SOURCES = {"model", "transcript-synth", "stop-hook-transcript", "sdk-synth"}


def validate(entry: dict, spoke_name: str = "") -> dict:
    errors, warnings = [], []

    for field in REQUIRED:
        val = entry.get(field)
        if val is None:
            errors.append(f"MISSING required field: {field}")
        elif isinstance(val, str) and not val.strip():
            errors.append(f"EMPTY required field: {field}")

    # Full-feature discriminator: source must be model-authored.
    source = entry.get("source", "")
    if source and source != "model":
        warnings.append(f"source={source!r} — not model-authored; not a full-feature entry")

    for field in SOFT_REQUIRED:
        if entry.get(field) is None:
            warnings.append(f"missing soft-required field: {field}")

    # thinking: 3-8 sentences of why/tradeoffs.
    thinking = entry.get("thinking", "")
    if isinstance(thinking, str) and thinking.strip():
        sentences = [s for s in thinking.replace("!", ".").replace("?", ".").split(".") if s.strip()]
        if len(sentences) < 3:
            warnings.append(f"thinking too short ({len(sentences)} sentences; need 3-8)")

    # user_msg verbatim cap.
    um = entry.get("user_msg", "")
    if isinstance(um, str) and len(um) > 500:
        warnings.append("user_msg exceeds 500 chars (should be ellipsis-truncated)")

    result = {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}

    # Annotate a COPY of the entry. The note is a SLIM dict (ok/errors/warnings only) —
    # it must NOT reference `result`, or `result['annotated_entry']['_validation']` would
    # point back to `result` and json.dumps(result) would raise "Circular reference".
    annotated = dict(entry)
    if errors or warnings:
        annotated["_validation"] = {"ok": result["ok"], "errors": list(errors), "warnings": list(warnings)}
    result["annotated_entry"] = annotated
    return result


def _spoke_from_state(state_path) -> str:
    try:
        state = json.loads(Path(state_path).read_text())
        return (state.get("wheel", {}) or {}).get("name", "") or state.get("spoke", {}).get("short_name", "")
    except Exception:
        return ""


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: validate_track_buffer.py <buffer_path> [<state_path>]"}))
        sys.exit(1)

    buffer_path = Path(sys.argv[1])
    spoke_name = _spoke_from_state(sys.argv[2]) if len(sys.argv) > 2 else ""

    if not buffer_path.exists():
        print(json.dumps({"error": f"Buffer not found: {buffer_path}"}))
        sys.exit(1)
    try:
        entry = json.loads(buffer_path.read_text())
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON in buffer: {e}"}))
        sys.exit(1)

    result = validate(entry, spoke_name)
    # Persist the full (now acyclic) result for hook consumption.
    (buffer_path.parent / "track-validation-last.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({"status": "OK" if result["ok"] else "FAIL",
                      "errors": result["errors"], "warnings": result["warnings"]}, indent=2))
    sys.exit(0 if result["ok"] else 1)


def hook_main() -> None:
    """PostToolUse entry — fires right after a Write; gives same-turn repair feedback."""
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw) if raw.strip() else {}
    except Exception:
        hook_input = {}
    tool_name = hook_input.get("tool_name", "")
    file_path = str((hook_input.get("tool_input") or {}).get("file_path", ""))
    if tool_name != "Write" or not file_path.endswith("track-buffer.json"):
        sys.exit(0)  # silent allow — not our file
    try:
        entry = json.loads(Path(file_path).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"track-buffer.json unreadable: {e}", file=sys.stderr)
        sys.exit(0)
    result = validate(entry, "")
    turn_n = entry.get("turn", "?")
    if result["ok"] and not result["warnings"]:
        sys.exit(0)
    lines = []
    if result["errors"]:
        lines.append(f"TRACK BUFFER T{turn_n} — repair before this turn ends:")
        lines += [f"  missing/empty: {e}" for e in result["errors"]]
    if result["warnings"]:
        lines += [f"  warn: {w}" for w in result["warnings"]]
    # Non-blocking advisory on stderr (exit 0): annotate-don't-drop, never fail the turn.
    print("\n".join(lines), file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
    else:
        hook_main()
