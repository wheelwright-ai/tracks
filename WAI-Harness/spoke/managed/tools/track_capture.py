#!/usr/bin/env python3
"""Capture a turn into the track from ANY platform, not just Claude Code.

WHY THIS EXISTS. Measured on this spoke 2026-08-17 across 1,850 tracked turns:

    user_intent   85%   <- written by a hook
    thinking      47%   <- written by the agent
    action        47%
    focus         47%
    phase         47%

Zero turns in 1,850 where agent discipline succeeded and the mechanism had not
already fired. Instructed behaviour runs at 47%; computed behaviour runs at 85%.

That 85% is the most reliable thing in the harness -- and it only exists under
Claude Code. The capture lives in `.claude/hooks/`, invoked by UserPromptSubmit and
Stop. On Gemini CLI, on a raw API loop, on whatever the operator uses next, those
events do not exist and the number is 0%.

    Mechanisms in the REPO port. Mechanisms in the HOST do not.

The operator's requirement is "value regardless of the platform our work is done on
or model interpreting our directions." A capture layer bolted to one vendor's event
model cannot deliver that, however well it performs where it runs.

DELEGATES, DOES NOT FORK. Every line of the actual synthesis stays in
synthesize_turn.py. This repo already carries 66 divergent duplicate groups; a second
copy of the track logic would be the 67th, and the fix that lands in one of them
would silently miss the other. This file owns the ENTRY POINT and nothing else.

WHY NOT JUST CALL THE HOOK DIRECTLY. Three reasons, all measured rather than
supposed:
  1. Its CLI is positional and undocumented -- `synthesize_turn.py a b c 1` -- with
     no --help. Undiscoverable is unusable from another platform.
  2. It swallows every exception by design ("track is best-effort; never break the
     session"). Correct inside a hook. Wrong for an explicit caller, who gets silent
     success and an empty track.
  3. `.claude/` is Claude Code's namespace by convention. A Gemini integration
     reaching into it is a coupling nobody would choose deliberately.

WHAT THIS DOES NOT SOLVE, measured while building it. synthesize_turn.live() is
TRANSCRIPT-driven: live(state_path, transcript_path, project_dir, buffer_present)
parses Claude Code's session JSONL. So the 85% mechanism is not merely host-INVOKED,
it is host-FORMAT-coupled, and relocating the entry point does not port it. A Gemini
or raw-API loop has no such transcript to hand it.

This tool therefore delivers the half that is real today -- capture callable from any
platform GIVEN a Claude-Code-shaped transcript, which covers backfill, replay and
recovery -- and `doctor` states the remaining gap out loud rather than reporting a
portability we do not have. The text-mode entry point synthesize_turn would need is
tracked separately; claiming it here would be the kind of unearned green this harness
spent a night removing.

USAGE
  track_capture.py turn --session <id> --state <p> --transcript <p>
  track_capture.py backfill --session <id> --state <p> --transcript <p>
  track_capture.py doctor          # can this platform capture, and how far?
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SPOKE_ROOT = TOOLS.parents[3]

# The single implementation. Both entries -- hook and CLI -- run THIS file.
_IMPL_CANDIDATES = (
    ".claude/hooks/synthesize_turn.py",
    "WAI-Harness/spoke/managed/.claude/hooks/synthesize_turn.py",
)


def _load_impl(root: Path):
    """(module, path) or (None, reason). Never raises -- doctor reports, callers decide."""
    for rel in _IMPL_CANDIDATES:
        p = root / rel
        if not p.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location("_wai_synth", p)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod, str(p)
        except Exception as exc:                    # noqa: BLE001 - reported, not hidden
            return None, f"{p} present but failed to import: {exc}"
    return None, ("no synthesize_turn.py found at " + " or ".join(_IMPL_CANDIDATES))


def _buffer_path(root: Path) -> Path:
    return root / "WAI-Harness/spoke/local/runtime/track-buffer.json"


def cmd_doctor(args) -> int:
    """Can this platform capture? Answer honestly, including on the parts that are
    still host-bound."""
    root = Path(args.root).resolve()
    mod, detail = _load_impl(root)
    buf = _buffer_path(root)
    sessions = root / "WAI-Harness/spoke/local/sessions"

    print(f"spoke        : {root}")
    print(f"implementation: {'OK ' + detail if mod else 'MISSING — ' + detail}")
    print(f"buffer path  : {buf} ({'exists' if buf.exists() else 'absent (created on first write)'})")
    print(f"sessions dir : {sessions} ({'exists' if sessions.is_dir() else 'ABSENT'})")

    host = bool(os.environ.get("CLAUDE_PROJECT_DIR"))
    print(f"host hooks   : {'Claude Code detected — hooks will also fire' if host else 'no Claude Code — this CLI is the only capture path'}")
    if not mod:
        print("\nVERDICT: cannot capture. The synthesis implementation is unreachable.")
        return 1
    print(f"transcript   : REQUIRED — live() parses Claude Code session JSONL")
    print("\nVERDICT: capture available from this platform, GIVEN a "
          "Claude-Code-shaped transcript.")
    print("         Not yet portable to a platform that produces no such transcript;")
    print("         that needs a text-mode entry point in synthesize_turn, which")
    print("         does not exist. Stated rather than glossed.")
    return 0


def cmd_turn(args) -> int:
    root = Path(args.root).resolve()
    mod, detail = _load_impl(root)
    if mod is None:
        # LOUD. The hook swallows failures because a broken track must never kill a
        # session; an explicit caller asked for this and gets told when it did not work.
        print(f"track_capture: cannot capture — {detail}", file=sys.stderr)
        return 1

    if not Path(args.transcript).is_file():
        print(f"track_capture: transcript not readable: {args.transcript}",
              file=sys.stderr)
        return 2

    fn = getattr(mod, "live", None)
    if not callable(fn):
        print("track_capture: synthesize_turn exposes no live() entry point — the "
              "implementation changed shape and this entry point needs updating "
              "(deliberately NOT falling back to a private copy)", file=sys.stderr)
        return 1
    try:
        fn(args.state, args.transcript, str(root), bool(args.buffer_present))
    except Exception as exc:                        # noqa: BLE001 - explicit caller
        print(f"track_capture: capture failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"ok": True, "session": args.session,
                          "impl": detail, "buffer": str(_buffer_path(root))}))
    return 0


def cmd_backfill(args) -> int:
    root = Path(args.root).resolve()
    mod, detail = _load_impl(root)
    if mod is None:
        print(f"track_capture: cannot backfill — {detail}", file=sys.stderr)
        return 1
    fn = getattr(mod, "backfill", None)
    if not callable(fn):
        print("track_capture: synthesize_turn exposes no backfill()", file=sys.stderr)
        return 1
    try:
        fn(args.state, args.transcript, str(root))
    except Exception as exc:                        # noqa: BLE001
        print(f"track_capture: backfill failed: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(SPOKE_ROOT))
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("turn", help="capture one turn")
    t.add_argument("--session", required=True)
    t.add_argument("--state", required=True, help="session state path")
    t.add_argument("--transcript", required=True,
                   help="Claude-Code-shaped session JSONL (see the format note above)")
    t.add_argument("--buffer-present", action="store_true",
                   help="a rich buffer was already flushed for this turn")
    t.add_argument("--json", action="store_true")
    t.set_defaults(func=cmd_turn)

    b = sub.add_parser("backfill", help="rebuild a session's track from a transcript")
    b.add_argument("--session", required=True)
    b.add_argument("--state", required=True, help="session state path")
    b.add_argument("--transcript", required=True)
    b.set_defaults(func=cmd_backfill)

    d = sub.add_parser("doctor", help="can this platform capture?")
    d.set_defaults(func=cmd_doctor)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
