"""Per-turn insight generation engine (feature-track-per-turn-insight-rewrites-v1).

Generates two succinct machine rewrites per turn, written into the track point:
  user_insight  - a rewrite of what the user submitted, generated at UserPromptSubmit.
  agent_insight - a rewrite of what the agent did, generated at Stop.

The stream of these across a session's track.jsonl is CUMULATIVE — each rewrite is
generated with the last few prior rewrites as context, so the operator can read the
sequence as an arc. Context is bounded to the last N prior insights (never the full
transcript) so cost/latency stay bounded even on sonnet.

Mirrors basher's scripts/lens-insight.sh engine: an ephemeral `claude -p` call from a
NEUTRAL cwd (no CLAUDE.md / WAI-State.json, so the nested call's own hooks see no
project and exit immediately -- this is what prevents recursion, not a special-case
guard) with a scrubbed env (drops ANTHROPIC_API_KEY so it bills to subscription, drops
CLAUDE_PROJECT_DIR/ZELLIJ* so it can never pick up this project's own session
identity), sonnet model, bounded timeout. Fail-open throughout: any failure (missing
claude binary, timeout, non-zero exit, unparseable output) returns None and the caller
writes the point without the field -- never raises, never blocks.

USER-SESSIONS-ONLY: is_autopilot_session() gates out dispatched/autopilot/headless
callers. In practice WAI_AP_DISPATCH sessions never reach the interactive
UserPromptSubmit/Stop surface at all (stop-track-flush.sh exits before this module is
even imported), but every entry point re-checks so a standalone or test invocation is
never accidentally generative in an autonomous context.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

DEFAULT_MODEL = os.environ.get("WAI_TRACK_INSIGHT_MODEL", "sonnet")
DEFAULT_TIMEOUT = int(os.environ.get("WAI_TRACK_INSIGHT_TIMEOUT", "45"))
DEFAULT_CONTEXT_N = int(os.environ.get("WAI_TRACK_INSIGHT_CONTEXT_N", "5"))

_SCAN_WINDOW = 200  # cap lines scanned in track.jsonl for recent-insight context


def is_autopilot_session() -> bool:
    """USER-SESSIONS-ONLY gate: true when this process is a dispatched/autopilot/
    headless worker, not an interactive user session."""
    if os.environ.get("WAI_AP_DISPATCH"):
        return True
    if os.environ.get("BASHER_AUTOPILOT"):
        return True
    if os.environ.get("WAI_HERALD_SPAWN"):
        return True
    # BASHER_NO_TOAST alone marks a headless auto-answer responder (herald / lens
    # background worker) when there is no real project cwd behind it.
    if os.environ.get("BASHER_NO_TOAST") and not os.environ.get("CLAUDE_PROJECT_DIR"):
        return True
    return False


def recent_insights(track_path, limit: int = DEFAULT_CONTEXT_N):
    """Last <limit> prior user_insight/agent_insight strings from this session's
    track.jsonl, oldest first. Bounded scan window -- never the full transcript."""
    out = []
    if not track_path:
        return out
    try:
        p = Path(track_path)
        if not p.is_file():
            return out
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in lines[-_SCAN_WINDOW:]:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if entry.get("event") != "turn":
                continue
            for key in ("user_insight", "agent_insight"):
                v = entry.get(key)
                if v:
                    out.append(str(v))
    except Exception:
        return []
    return out[-limit:]


def _neutral_dir() -> str:
    d = Path(tempfile.gettempdir()) / "wai-track-insight-neutral"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def _run_claude(prompt: str, model: str, timeout: int):
    """Spawn the ephemeral claude -p rewrite call. Returns rewrite text, or None on
    any failure/timeout (fail-open -- never raises)."""
    if not prompt or not prompt.strip():
        return None
    try:
        env = dict(os.environ)
        for k in ("ANTHROPIC_API_KEY", "CLAUDE_PROJECT_DIR",
                  "ZELLIJ", "ZELLIJ_PANE_ID", "ZELLIJ_SESSION_NAME"):
            env.pop(k, None)
        env["BASHER_NO_TOAST"] = "1"
        env["WAI_AP_DISPATCH"] = "1"  # belt-and-suspenders: no recursion on the nested call
        result = subprocess.run(
            ["claude", "-p", "--model", model, "--output-format", "json"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=_neutral_dir(),
            env=env,
        )
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    text = ""
    try:
        outer = json.loads(result.stdout)
        text = outer.get("result", "") if isinstance(outer, dict) else ""
    except Exception:
        text = result.stdout
    text = (text or "").strip()
    return text or None


def _context_block(track_path, context_n) -> str:
    recent = recent_insights(track_path, context_n)
    if not recent:
        return ""
    body = "\n".join(f"- {r}" for r in recent)
    return f"RECENT SESSION INSIGHTS (oldest first, for continuity -- do not repeat them):\n{body}\n\n"


def _lock(lock_dir: Path) -> bool:
    """mkdir single-flight lock. Returns True if acquired (caller owns cleanup)."""
    try:
        lock_dir.mkdir(parents=True, exist_ok=False)
        return True
    except Exception:
        return False


def _unlock(lock_dir: Path) -> None:
    try:
        lock_dir.rmdir()
    except Exception:
        pass


def generate_user_insight(prompt_text, track_path=None, lane_dir=None,
                           model=DEFAULT_MODEL, timeout=DEFAULT_TIMEOUT,
                           context_n=DEFAULT_CONTEXT_N):
    """Rewrite of the submitted prompt, considering recent prior insights.
    Fail-open: returns None on any failure/skip -- never raises."""
    if is_autopilot_session():
        return None
    lock_dir = Path(lane_dir) / "insight-user.lock" if lane_dir else None
    if lock_dir is not None and not _lock(lock_dir):
        return None  # a generation is already in flight for this lane -- pileup guard
    try:
        ctx = _context_block(track_path, context_n)
        sys_prompt = (
            "You rewrite a user's submitted prompt into a clear, succinct-but-not-terse "
            "one-to-two sentence summary of WHAT THEY ARE ASKING FOR, considering the "
            "conversation so far. Do not answer the request or add commentary. Emit ONLY "
            "the rewrite text -- no preamble, no quotes, no JSON, no markdown."
        )
        full = f"{sys_prompt}\n\n{ctx}SUBMITTED PROMPT:\n{prompt_text}"
        return _run_claude(full, model, timeout)
    finally:
        if lock_dir is not None:
            _unlock(lock_dir)


def generate_agent_insight(work_text, track_path=None, lane_dir=None,
                            model=DEFAULT_MODEL, timeout=DEFAULT_TIMEOUT,
                            context_n=DEFAULT_CONTEXT_N):
    """Rewrite of what the agent did this turn, considering recent prior insights.
    Fail-open: returns None on any failure/skip -- never raises."""
    if is_autopilot_session():
        return None
    lock_dir = Path(lane_dir) / "insight-agent.lock" if lane_dir else None
    if lock_dir is not None and not _lock(lock_dir):
        return None
    try:
        ctx = _context_block(track_path, context_n)
        sys_prompt = (
            "You rewrite an AI agent's turn into a clear, succinct-but-not-terse "
            "one-to-two sentence summary of WHAT WAS DONE, considering the session so "
            "far. Emit ONLY the rewrite text -- no preamble, no quotes, no JSON, no markdown."
        )
        full = f"{sys_prompt}\n\n{ctx}AGENT TURN:\n{work_text}"
        return _run_claude(full, model, timeout)
    finally:
        if lock_dir is not None:
            _unlock(lock_dir)


# ── Cross-hook handoff: user_insight is generated (background, at UserPromptSubmit)
# before the turn's Stop point exists. A turn-numbered side file -- not the live
# track-buffer.json -- carries it across, because the buffer gets pre-seeded for the
# NEXT turn before a slow background generation for THIS turn can finish; a side file
# keyed by turn number survives that overwrite. ────────────────────────────────────

def _pending_path(lane_dir, turn) -> "Path | None":
    if not lane_dir:
        return None
    return Path(lane_dir) / f"pending-user-insight-{turn}.json"


def write_pending_user_insight(lane_dir, turn, text) -> None:
    p = _pending_path(lane_dir, turn)
    if p is None:
        return
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps({"turn": turn, "user_insight": text}))
        tmp.replace(p)
    except Exception:
        pass


def read_pending_user_insight(lane_dir, turn):
    """Consume (read + delete) the pending user_insight for this turn, if any. Also
    sweeps stale pending files from earlier turns (abandoned -- the Stop point that
    would have consumed them already flushed) so they never pile up."""
    if not lane_dir:
        return None
    lane = Path(lane_dir)
    result = None
    try:
        for f in lane.glob("pending-user-insight-*.json"):
            try:
                data = json.loads(f.read_text())
            except Exception:
                data = {}
            if data.get("turn") == turn and data.get("user_insight"):
                result = str(data["user_insight"])
            f.unlink(missing_ok=True)
    except Exception:
        pass
    return result


# ── CLI: background entry point invoked (detached) by user-prompt-submit.sh ────────

def _cli_generate_user(argv) -> None:
    """generate-user --turn N --lane-dir D [--track-path T] [--model M] [--timeout S]
    Reads the submitted prompt text from stdin. Always exits 0 -- best-effort."""
    opts = {}
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            opts[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            i += 1
    turn = opts.get("turn")
    lane_dir = opts.get("lane-dir")
    track_path = opts.get("track-path")
    model = opts.get("model", DEFAULT_MODEL)
    timeout = int(opts.get("timeout", DEFAULT_TIMEOUT))
    try:
        import sys as _sys
        prompt_text = _sys.stdin.read()
    except Exception:
        prompt_text = ""
    if not prompt_text.strip() or turn is None:
        return
    text = generate_user_insight(prompt_text, track_path=track_path, lane_dir=lane_dir,
                                  model=model, timeout=timeout)
    if text:
        write_pending_user_insight(lane_dir, int(turn), text)


def main() -> None:
    import sys as _sys
    argv = _sys.argv[1:]
    if not argv:
        return
    try:
        if argv[0] == "generate-user":
            _cli_generate_user(argv[1:])
    except Exception:
        pass  # best-effort CLI -- never raise to the caller shell


if __name__ == "__main__":
    main()
