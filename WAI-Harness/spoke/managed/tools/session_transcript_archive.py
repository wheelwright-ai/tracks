#!/usr/bin/env python3
"""session_transcript_archive.py — per-spoke clone/archive of Claude Code session transcripts.

Basher-owned, fleet-distributed. Each spoke runs this against ITS OWN Claude Code log
dir (~/.claude/projects/<encoded-spoke-path>/) to keep a near-full, durable clone of the
conversation and work. The ONLY stripdown is file-edit/read output bodies — everything else
(user turns, assistant text + reasoning, tool_use "the work", and non-file tool_results) is
kept verbatim. Operator has explicitly accepted file size and local PII; the single guardrail
is local + gitignored (see WAI-Harness/spoke/local/archive/ in .gitignore) so nothing raw is
ever committed or bubbled to hub.

Protocol:
  --clone <sid>   refresh live/<sid>.jsonl (cheap incremental, watermarked) — Stop hook + savepoint
  --archive <sid> promote live/<sid>.jsonl -> closed/<sid>.jsonl (write-once, immutable) — closeout
  --report        interrupted-session report (transcript/live present, closed absent) — closeout
  --backfill      first run: sweep all existing transcripts -> closed/, active -> live/

Strip rule (the ONLY stripdown):
  KEEP verbatim   user turns; assistant text + reasoning/thinking; tool_use blocks (the work);
                  tool_result from non-file tools (Bash/Grep/Glob/...), with a configurable cap.
  STUB            Read/Write/Edit/NotebookEdit — the tool_result body AND any embedded
                  file-content payload (Write content, Edit old_string/new_string,
                  NotebookEdit new_source) -> one-line stub {tool, path, bytes, status}.
  DROP            pure-noise lines: attachment, file-history-snapshot, mode, permission-mode,
                  last-prompt, ai-title.

Idempotent + watermarked: per-session (sessionId, byte offset, line count, mtime, tool_index)
in archive/transcripts/_watermark.json — only new lines are processed on re-run.

Stdlib only — no third-party deps, so every spoke can run it as-is.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
import tempfile

# ---- strip-rule constants ---------------------------------------------------

NOISE_TYPES = {
    "attachment",
    "file-history-snapshot",
    "mode",
    "permission-mode",
    "last-prompt",
    "ai-title",
}
FILE_TOOLS = {"Read", "Write", "Edit", "NotebookEdit"}
# heavy file-content payloads embedded in a file-tool's input block
HEAVY_INPUT_FIELDS = {"content", "old_string", "new_string", "new_source"}

INTERRUPTED_MAX_AGE_DAYS = 7  # anti-pattern: stale interrupted sessions add no actionable value


# ---- path resolution --------------------------------------------------------

def encode_spoke_path(abspath: str) -> str:
    """Encode an absolute spoke path the way Claude Code names its projects dir:
    leading '/', plus every '/', '.' and '_' -> '-'."""
    out = []
    for ch in abspath:
        out.append("-" if ch in "/._" else ch)
    return "".join(out)


def claude_log_dir(spoke_root: str) -> str:
    enc = encode_spoke_path(os.path.abspath(spoke_root))
    return os.path.join(os.path.expanduser("~/.claude/projects"), enc)


def resolve_base(spoke_root: str) -> str:
    """Active data-plane base (harness-mode-aware), absolute."""
    v4 = os.path.join(spoke_root, "WAI-Harness", "spoke", "local")
    if os.path.isdir(v4):
        return v4
    return os.path.join(spoke_root, "WAI-Spoke")


def archive_root(spoke_root: str) -> str:
    return os.path.join(resolve_base(spoke_root), "archive", "transcripts")


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---- watermark --------------------------------------------------------------

def watermark_path(arch_root: str) -> str:
    return os.path.join(arch_root, "_watermark.json")


def load_watermark(arch_root: str) -> dict:
    p = watermark_path(arch_root)
    try:
        with open(p) as f:
            wm = json.load(f)
    except (FileNotFoundError, ValueError):
        wm = {}
    wm.setdefault("sessions", {})
    return wm


def save_watermark(arch_root: str, wm: dict) -> None:
    os.makedirs(arch_root, exist_ok=True)
    _atomic_write(watermark_path(arch_root), json.dumps(wm, indent=1))


def _atomic_write(path: str, text: str) -> None:
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".swap")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ---- strip engine -----------------------------------------------------------

def _content_len(body) -> int:
    if isinstance(body, str):
        return len(body)
    if isinstance(body, list):
        n = 0
        for b in body:
            if isinstance(b, dict):
                n += len(b.get("text", "")) or len(json.dumps(b))
            else:
                n += len(str(b))
        return n
    if body is None:
        return 0
    return len(json.dumps(body))


def _cap_body(body, cap: int):
    """Truncate a kept (non-file) tool_result body to `cap` bytes if it exceeds it."""
    if not cap or cap <= 0:
        return body
    if isinstance(body, str) and len(body) > cap:
        return body[:cap] + f"\n…[truncated {len(body) - cap} bytes by --bash-cap]"
    if isinstance(body, list):
        for b in body:
            if isinstance(b, dict) and isinstance(b.get("text"), str) and len(b["text"]) > cap:
                b["text"] = b["text"][:cap] + f"\n…[truncated {len(b['text']) - cap} bytes by --bash-cap]"
    return body


def _process_block(b: dict, cap: int, tool_index: dict):
    if not isinstance(b, dict):
        return b
    bt = b.get("type")

    if bt == "tool_use":
        name = b.get("name")
        tid = b.get("id")
        inp = b.get("input") if isinstance(b.get("input"), dict) else {}
        path = inp.get("file_path") or inp.get("notebook_path") or inp.get("path")
        if tid:
            tool_index[tid] = {"tool": name, "path": path}
        if name in FILE_TOOLS:
            stripped = 0
            new_inp = {}
            for k, v in inp.items():
                if k in HEAVY_INPUT_FIELDS and isinstance(v, str):
                    stripped += len(v)
                    continue
                if k == "edits" and isinstance(v, list):  # MultiEdit-style payloads
                    stripped += len(json.dumps(v))
                    continue
                new_inp[k] = v
            new_inp["_stub"] = {
                "tool": name, "path": path, "bytes": stripped, "status": "stripped",
            }
            b["input"] = new_inp
        return b

    if bt == "tool_result":
        tid = b.get("tool_use_id")
        meta = tool_index.get(tid, {})
        name = meta.get("tool")
        path = meta.get("path")
        status = "error" if b.get("is_error") else "ok"
        if name in FILE_TOOLS:
            n = _content_len(b.get("content"))
            b["content"] = json.dumps(
                {"stub": True, "tool": name, "path": path, "bytes": n, "status": status}
            )
        else:
            # non-file tool (Bash/Grep/Glob/...) kept verbatim, subject to the size cap
            b["content"] = _cap_body(b.get("content"), cap)
        return b

    return b


def process_obj(obj: dict, cap: int, tool_index: dict):
    """Return the stripped object, or None to DROP the line entirely."""
    if not isinstance(obj, dict):
        return obj
    if obj.get("type") in NOISE_TYPES:
        return None
    msg = obj.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("content"), list):
        msg["content"] = [_process_block(b, cap, tool_index) for b in msg["content"]]
    return obj


def _read_complete_lines(src: str, offset: int):
    """Read from `offset` to EOF; return (objs_text_lines, bytes_consumed). Only whole
    (newline-terminated) lines are consumed so a partially-written final line is left for
    the next run."""
    with open(src, "rb") as f:
        f.seek(offset)
        raw = f.read()
    last_nl = raw.rfind(b"\n")
    if last_nl == -1:
        return [], 0
    consumed = last_nl + 1
    text = raw[:consumed].decode("utf-8", errors="replace")
    return text.splitlines(), consumed


# ---- modes ------------------------------------------------------------------

def _strip_lines(lines, cap, tool_index):
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        res = process_obj(obj, cap, tool_index)
        if res is None:
            continue
        out.append(json.dumps(res, ensure_ascii=False))
    return out


def clone(sid: str, log_dir: str, arch_root: str, cap: int, wm: dict) -> dict:
    """Incremental refresh of live/<sid>.jsonl (overwrite/grow-in-place current snapshot)."""
    src = os.path.join(log_dir, f"{sid}.jsonl")
    if not os.path.isfile(src):
        return {"sid": sid, "status": "no-transcript"}
    live_dir = os.path.join(arch_root, "live")
    dst = os.path.join(live_dir, f"{sid}.jsonl")

    entry = wm["sessions"].get(sid, {})
    offset = entry.get("offset", 0)
    tool_index = dict(entry.get("tool_index", {}))
    st = os.stat(src)
    size = st.st_size

    # rotation/truncation or missing live file -> full reprocess
    if offset > size or not os.path.exists(dst):
        offset, tool_index, mode, prior_lines = 0, {}, "w", 0
    elif offset == size and entry.get("mtime") == st.st_mtime:
        return {"sid": sid, "status": "unchanged", "lines": entry.get("lines", 0)}
    else:
        mode, prior_lines = "a", entry.get("lines", 0)

    lines, consumed = _read_complete_lines(src, offset)
    stripped = _strip_lines(lines, cap, tool_index)

    os.makedirs(live_dir, exist_ok=True)
    if mode == "w":
        _atomic_write(dst, ("\n".join(stripped) + "\n") if stripped else "")
    elif stripped:
        with open(dst, "a") as f:
            f.write("\n".join(stripped) + "\n")

    total = prior_lines + len(stripped)
    wm["sessions"][sid] = {
        "offset": offset + consumed,
        "lines": total,
        "mtime": st.st_mtime,
        "tool_index": tool_index,
        "last_clone": now_iso(),
        "closed": entry.get("closed", False),
    }
    return {"sid": sid, "status": "cloned", "lines": total, "added": len(stripped)}


def archive_closed_from_source(sid: str, log_dir: str, arch_root: str, cap: int, wm: dict) -> dict:
    """Backfill path: strip the WHOLE transcript straight into closed/ (write-once)."""
    closed_dir = os.path.join(arch_root, "closed")
    closed = os.path.join(closed_dir, f"{sid}.jsonl")
    if os.path.exists(closed):
        wm["sessions"].setdefault(sid, {})["closed"] = True
        return {"sid": sid, "status": "already-closed"}
    src = os.path.join(log_dir, f"{sid}.jsonl")
    if not os.path.isfile(src):
        return {"sid": sid, "status": "no-transcript"}
    st = os.stat(src)
    lines, consumed = _read_complete_lines(src, 0)
    tool_index: dict = {}
    stripped = _strip_lines(lines, cap, tool_index)
    os.makedirs(closed_dir, exist_ok=True)
    _atomic_write(closed, ("\n".join(stripped) + "\n") if stripped else "")
    os.chmod(closed, 0o444)  # immutable: write-once
    wm["sessions"][sid] = {
        "offset": consumed, "lines": len(stripped), "mtime": st.st_mtime,
        "tool_index": {}, "closed": True, "archived_at": now_iso(),
    }
    return {"sid": sid, "status": "archived-closed", "lines": len(stripped)}


def archive(sid: str, log_dir: str, arch_root: str, cap: int, wm: dict) -> dict:
    """Promote live/<sid>.jsonl -> closed/<sid>.jsonl (write-once; refuse overwrite)."""
    closed_dir = os.path.join(arch_root, "closed")
    closed = os.path.join(closed_dir, f"{sid}.jsonl")
    if os.path.exists(closed):
        return {"sid": sid, "status": "already-closed", "refused_overwrite": True}
    # ensure the live snapshot is fully current before sealing
    clone(sid, log_dir, arch_root, cap, wm)
    live = os.path.join(arch_root, "live", f"{sid}.jsonl")
    if not os.path.exists(live):
        # no live clone ever made (e.g. session never hit a Stop hook) — seal from source
        return archive_closed_from_source(sid, log_dir, arch_root, cap, wm)
    os.makedirs(closed_dir, exist_ok=True)
    shutil.copyfile(live, closed)
    os.chmod(closed, 0o444)  # immutable
    wm["sessions"].setdefault(sid, {})["closed"] = True
    wm["sessions"][sid]["archived_at"] = now_iso()
    return {"sid": sid, "status": "archived", "path": closed}


def newest_sid(log_dir: str) -> str | None:
    """The active session = the newest-mtime transcript in the spoke's Claude log dir.
    Lets ceremonies clone/archive `current` without threading the CC session UUID."""
    if not os.path.isdir(log_dir):
        return None
    newest, newest_m = None, -1.0
    for f in os.listdir(log_dir):
        if not f.endswith(".jsonl"):
            continue
        m = os.stat(os.path.join(log_dir, f)).st_mtime
        if m > newest_m:
            newest, newest_m = f, m
    return newest[:-6] if newest else None


def backfill(log_dir: str, arch_root: str, cap: int, wm: dict, current: str | None) -> dict:
    if not os.path.isdir(log_dir):
        return {"status": "no-log-dir", "log_dir": log_dir, "results": []}
    transcripts = sorted(
        f for f in os.listdir(log_dir) if f.endswith(".jsonl")
    )
    if current is None:
        # active session = newest-mtime transcript
        newest, newest_m = None, -1.0
        for f in transcripts:
            m = os.stat(os.path.join(log_dir, f)).st_mtime
            if m > newest_m:
                newest, newest_m = f, m
        current = newest[:-6] if newest else None
    results = []
    for f in transcripts:
        sid = f[:-6]
        if sid == current:
            results.append(clone(sid, log_dir, arch_root, cap, wm))
        else:
            results.append(archive_closed_from_source(sid, log_dir, arch_root, cap, wm))
    return {"status": "ok", "current": current, "count": len(results), "results": results}


def _death_point(path: str) -> dict:
    """Last-turn timestamp + last action from a (possibly stripped) jsonl file."""
    last_ts, last_action = None, None
    try:
        with open(path, errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                ts = obj.get("timestamp")
                if ts:
                    last_ts = ts
                msg = obj.get("message")
                if isinstance(msg, dict) and isinstance(msg.get("content"), list):
                    for b in msg["content"]:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "tool_use":
                            inp = b.get("input") if isinstance(b.get("input"), dict) else {}
                            p = inp.get("file_path") or inp.get("path") or inp.get("command")
                            last_action = f"{b.get('name')}({p})" if p else f"{b.get('name')}"
                        elif b.get("type") == "text" and b.get("text"):
                            last_action = "text: " + b["text"][:80].replace("\n", " ")
    except FileNotFoundError:
        pass
    return {"last_turn": last_ts, "last_action": last_action}


def report(log_dir: str, arch_root: str, max_age_days: int = INTERRUPTED_MAX_AGE_DAYS) -> dict:
    """Interrupted = a sessionId with a transcript on disk OR a live/ entry, but no closed/ entry."""
    live_dir = os.path.join(arch_root, "live")
    closed_dir = os.path.join(arch_root, "closed")
    closed = {f[:-6] for f in os.listdir(closed_dir)} if os.path.isdir(closed_dir) else set()

    candidates: dict[str, str] = {}  # sid -> path to read death point from
    if os.path.isdir(log_dir):
        for f in os.listdir(log_dir):
            if f.endswith(".jsonl"):
                candidates[f[:-6]] = os.path.join(log_dir, f)
    if os.path.isdir(live_dir):
        for f in os.listdir(live_dir):
            if f.endswith(".jsonl"):
                candidates.setdefault(f[:-6], os.path.join(live_dir, f))

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)
    interrupted, stale = [], 0
    for sid, path in sorted(candidates.items()):
        if sid in closed:
            continue
        dp = _death_point(path)
        # age filter: skip sessions whose last turn is older than the cutoff (no actionable context)
        if dp["last_turn"]:
            try:
                lt = datetime.datetime.fromisoformat(dp["last_turn"].replace("Z", "+00:00"))
                if lt < cutoff:
                    stale += 1
                    continue
            except ValueError:
                pass
        interrupted.append({"sessionId": sid, **dp,
                            "has_live": os.path.exists(os.path.join(live_dir, f"{sid}.jsonl"))})
    return {"status": "ok", "interrupted_count": len(interrupted),
            "stale_skipped": stale, "interrupted": interrupted}


# ---- cli --------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--backfill", action="store_true",
                   help="first run: sweep all transcripts -> closed/, active -> live/")
    g.add_argument("--clone", metavar="SID",
                   help="refresh live/<SID>.jsonl (incremental); SID='current' = newest transcript")
    g.add_argument("--archive", metavar="SID",
                   help="promote live/<SID> -> closed/<SID> (write-once); SID='current' = newest")
    g.add_argument("--report", action="store_true", help="interrupted-session report")
    ap.add_argument("--spoke-root", default=os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd(),
                    help="spoke root whose Claude log dir to read (default: $CLAUDE_PROJECT_DIR or cwd)")
    ap.add_argument("--current", metavar="SID", default=None,
                    help="active session id (backfill: routed to live/ instead of closed/)")
    ap.add_argument("--bash-cap", type=int, default=0, metavar="BYTES",
                    help="cap kept (non-file) tool_result bodies to BYTES (0 = unlimited, default)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args(argv)

    spoke_root = os.path.abspath(args.spoke_root)
    log_dir = claude_log_dir(spoke_root)
    arch_root = archive_root(spoke_root)
    wm = load_watermark(arch_root)

    if args.report:
        # report is read-only — no watermark write
        out = report(log_dir, arch_root)
    elif args.backfill:
        out = backfill(log_dir, arch_root, args.bash_cap, wm, args.current)
        save_watermark(arch_root, wm)
    elif args.clone:
        sid = newest_sid(log_dir) if args.clone == "current" else args.clone
        out = {"status": "no-active-session"} if not sid else \
            clone(sid, log_dir, arch_root, args.bash_cap, wm)
        save_watermark(arch_root, wm)
    elif args.archive:
        sid = newest_sid(log_dir) if args.archive == "current" else args.archive
        out = {"status": "no-active-session"} if not sid else \
            archive(sid, log_dir, arch_root, args.bash_cap, wm)
        save_watermark(arch_root, wm)
    else:  # unreachable (group is required)
        ap.error("no mode selected")
        return 2

    if args.json:
        print(json.dumps(out, indent=1))
    else:
        _print_human(out)
    return 0


def _print_human(out: dict) -> None:
    if "interrupted" in out:
        n = out["interrupted_count"]
        if n == 0:
            print(f"No interrupted sessions ({out['stale_skipped']} stale skipped).")
            return
        print(f"Interrupted sessions: {n} ({out['stale_skipped']} stale skipped)")
        for s in out["interrupted"]:
            print(f"  • {s['sessionId']}  last_turn={s['last_turn']}  "
                  f"last_action={s['last_action']}  live={s['has_live']}")
        return
    if "results" in out:
        print(f"Backfill: current={out.get('current')}  processed={out.get('count')}")
        for r in out["results"]:
            print(f"  {r.get('status'):>16}  {r.get('sid')}  "
                  f"lines={r.get('lines', '-')}")
        return
    print(json.dumps(out))


if __name__ == "__main__":
    sys.exit(main())
