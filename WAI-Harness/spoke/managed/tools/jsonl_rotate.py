#!/usr/bin/env python3
"""jsonl_rotate.py -- split an append-only .jsonl when it gets big. Never drop a record.

OPERATOR DIRECTIVE, 2026-08-22, verbatim:

    "split them once they get too big we dont wnat to loose valuable activity
     interaction data"

That ruling settled a live disagreement. The session had just capped a field to shrink
activity-log.jsonl from 64 MB, which discards data. The operator's answer was that the log
IS the record -- so the size problem is solved by SPLITTING, not by writing less.

MEASURED 2026-08-22, three files past 5 MB in one spoke:

    65 MB  WAI-Harness/spoke/advisors/autopilot/activity-log.jsonl
    57 MB  WAI-Harness/spoke/local/runtime/tastegraph-vector-calls.jsonl
    18 MB  WAI-Harness/spoke/local/runtime/path-claims.jsonl

So this is a shared mechanism, not an activity-log patch.

THE CONSTRAINT THAT SHAPES THE WHOLE DESIGN. Ten-plus tools open the activity log by a
HARDCODED path (token_hygiene_score.py:41 and cost_ledger.py:45 both literally
`Path("WAI-Harness/spoke/advisors/autopilot/activity-log.jsonl")`). If rotation renamed
the live file, every one of those readers would keep working, report no error, and
silently see only the newest slice. That is the exact silent-degradation shape this
harness has spent the session digging out of -- so:

  * THE LIVE PATH NEVER MOVES. `<name>.jsonl` is always the current segment. Every
    existing reader keeps working unchanged and keeps reading recent history.
  * OLDER RECORDS MOVE ASIDE, never away: `<name>.0001.jsonl`, `<name>.0002.jsonl`, ...
    in the same directory. Nothing is ever deleted, truncated, or rewritten.
  * A READER THAT WANTS EVERYTHING CALLS `iter_all()` and gets every segment in order.
  * A SIDECAR INDEX names the segments, so a human or a tool that has never heard of
    rotation can still discover that older data exists rather than concluding the log
    starts where the live segment starts.

WHY NOT gzip the archives: they must stay greppable by the same one-liners people already
use on these files. Compression can come later behind the same iter_all() contract.

CLI:
    jsonl_rotate.py check <path> [--max-mb 16]     # would it rotate? exit 0/1
    jsonl_rotate.py rotate <path> [--max-mb 16]    # rotate if needed
    jsonl_rotate.py status <path>                  # segments, sizes, total records
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_MAX_MB = 16
SEG_WIDTH = 4


def _segments(path):
    """Archive segments for `path`, oldest first. The live file is NOT included."""
    p = Path(path)
    stem, suf = p.stem, p.suffix or ".jsonl"
    out = []
    for cand in p.parent.glob(f"{stem}.*{suf}"):
        tail = cand.name[len(stem) + 1: -len(suf)]
        if tail.isdigit():
            out.append((int(tail), cand))
    return [c for _, c in sorted(out)]


def _next_seq(path):
    segs = _segments(path)
    if not segs:
        return 1
    p = Path(path)
    last = segs[-1].name[len(p.stem) + 1: -len(p.suffix or ".jsonl")]
    return int(last) + 1


def needs_rotation(path, max_mb=DEFAULT_MAX_MB):
    try:
        return Path(path).stat().st_size > max_mb * 1024 * 1024
    except OSError:
        return False


def iter_all(path):
    """Every record ever written, oldest first, across all segments then the live file.

    THE READER CONTRACT. A tool that wants full history calls this instead of open().
    Unparseable lines are skipped rather than raised on: one corrupt line must never hide
    the other million, which is the same rule track_judgment_coverage learned.
    """
    for f in _segments(path) + [Path(path)]:
        if not f.exists():
            continue
        with f.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:  # noqa: BLE001
                    continue


def rotate(path, max_mb=DEFAULT_MAX_MB, force=False):
    """Move the live file aside and start a fresh one. Returns the archive path or None.

    THE FIRST CUT OF THIS FUNCTION DESTROYED DATA AND ADVERSARIAL REVIEW EXECUTED IT.
    It was stat -> glob for next seq -> os.replace -> touch, with no lock, and it claimed
    in its own docstring that nothing could be lost. Measured: two processes both stat the
    oversized file, both glob and both compute seq 1; A replaces live -> .0001 and touches
    a new empty live; B then replaces its 0-byte live OVER .0001. `os.replace` is an atomic
    OVERWRITE -- it clobbers the destination without complaint. Result: LOST=593 records,
    no exception, and the caller swallows exceptions anyway.

    Not hypothetical here: autopilot runs several processes against one tree and this repo's
    own CLAUDE.md says never to assume you are alone.

    TWO INDEPENDENT DEFENCES, because either alone still has a hole:
      1. An exclusive flock around the whole read-modify-write. Serialises rotations on one
         machine, which is where the race was measured.
      2. An O_EXCL claim on the destination before the replace. flock cannot help across a
         filesystem that does not honour it, or if a future caller forgets the lock; O_EXCL
         makes "this sequence number is mine" a property of the filesystem. If the claim
         fails, the sequence is taken -- advance and try again rather than overwrite.

    A rotation that cannot claim any sequence returns None and leaves the log alone. Not
    rotating is a size problem; overwriting an archive is a data-loss problem, and those are
    not the same class.
    """
    p = Path(path)
    if not p.exists():
        return None
    if not force and not needs_rotation(path, max_mb):
        return None

    lock_path = p.parent / f".{p.stem}.rotate.lock"
    try:
        import fcntl  # noqa: PLC0415 -- POSIX only; the fallback below covers the rest
    except ImportError:
        fcntl = None

    lock_fd = None
    try:
        if fcntl is not None:
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        # Re-check UNDER the lock. Another process may have rotated while we waited, and
        # rotating again would archive an almost-empty file for no reason.
        if not force and not needs_rotation(path, max_mb):
            return None
        if not p.exists():
            return None

        seq = _next_seq(path)
        for _ in range(100):
            dest = p.parent / f"{p.stem}.{seq:0{SEG_WIDTH}d}{p.suffix or '.jsonl'}"
            try:
                fd = os.open(str(dest), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                seq += 1          # taken -- never overwrite it
                continue
            os.close(fd)
            # Replaces our own 0-byte claim, never anyone else's archive.
            os.replace(str(p), str(dest))
            p.touch()
            _write_index(path)
            return dest
        return None
    finally:
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                os.close(lock_fd)
            except Exception:  # noqa: BLE001
                pass


def _write_index(path):
    """A sidecar so older data is DISCOVERABLE by something that never heard of rotation.

    Without this, a human running `wc -l` on the live file concludes the history starts
    there. The index is advisory -- iter_all() reads the directory, never this file -- so a
    stale or missing index can never cause a record to be missed.
    """
    p = Path(path)
    idx = p.parent / f"{p.stem}.index.json"
    segs = _segments(path)
    data = {
        "live": p.name,
        "segments": [s.name for s in segs],
        "note": ("Older records live in the numbered segments, oldest first. Read every "
                 "record with jsonl_rotate.iter_all(); the live file alone is a partial "
                 "view. Nothing here is ever deleted."),
        "bytes": {s.name: s.stat().st_size for s in segs if s.exists()},
    }
    try:
        idx.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def status(path):
    p = Path(path)
    segs = _segments(path)
    live = p.stat().st_size if p.exists() else 0
    total = live + sum(s.stat().st_size for s in segs if s.exists())
    return {
        "live": str(p), "live_bytes": live,
        "segments": [str(s) for s in segs],
        "segment_bytes": [s.stat().st_size for s in segs if s.exists()],
        "total_bytes": total,
        "records": sum(1 for _ in iter_all(path)),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "rotate", "status"):
        s = sub.add_parser(name)
        s.add_argument("path")
        s.add_argument("--max-mb", type=float, default=DEFAULT_MAX_MB)
        if name == "rotate":
            s.add_argument("--force", action="store_true")
    a = ap.parse_args()

    if a.cmd == "check":
        need = needs_rotation(a.path, a.max_mb)
        print(f"{'ROTATE' if need else 'ok'}  {a.path}")
        return 1 if need else 0
    if a.cmd == "rotate":
        dest = rotate(a.path, a.max_mb, getattr(a, "force", False))
        print(f"rotated -> {dest}" if dest else "no rotation needed")
        return 0
    print(json.dumps(status(a.path), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
