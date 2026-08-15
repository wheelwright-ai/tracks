#!/usr/bin/env python3
"""What is actually burning the operator's Anthropic limits. Measured, not estimated.

WHY THIS EXISTS
---------------
The operator reported a "continual and blind burn" against his Max subscription.
It was blind for a concrete reason: every capacity number the harness owned was
one of estimated, hand-entered, or scoped to Conductor alone.

    weekly_spent / tokens_spent_in_window   Conductor's own spend-ledger ONLY
    window_budget_tokens = 800000           a config constant
    weekly_budget_tokens                    hand-entered, operator-adjustable
    five_day_limit_pct                      NO WRITER EXISTS. Found 321h stale.
    Anthropic API                           does not expose Max 5h/weekly windows

Conductor is the hub's unattended autopilot orchestrator. It is a real consumer,
but it is not the big one. INTERACTIVE sessions are, and they were invisible to
all of the above. Measured 2026-08-04: one interactive session burned 48.9M cache
reads by itself, against 8456.8M recorded across 757 Conductor-logged calls.

THE SOURCE THAT WAS ALREADY THERE
---------------------------------
Claude Code writes a transcript per session under ~/.claude/projects/<slug>/*.jsonl,
and every assistant message carries a real `message.usage` block:

    input_tokens, output_tokens,
    cache_read_input_tokens, cache_creation_input_tokens

138206 such files existed when this tool was written and nothing in the harness
read them for usage. Several tools open them for TEXT (compliance detectors, the
transcript archiver, worktree_guard) and step straight over the usage block.

So this is not new instrumentation. It is reading a meter that was already
running.

WHAT THIS IS NOT
----------------
It is NOT the operator's Max-plan percentage. No API exposes that, so nothing can
compute it honestly. This reports what WE consumed, per spoke, per model, per
5-hour window — which is the actionable half. Where a figure is unknown it says
unknown; an unknown is never rendered as a zero, because a confident zero is how
`five_day_limit_pct` sat stale for thirteen days without anyone noticing.

DESIGN NOTES
------------
Incremental by necessity: 5.5GB across 138k files is too much to re-read on a
cron. A cursor records (size, mtime) per file and only new-or-grown files are
parsed. Delete the cursor to force a full rebuild.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import sys
from pathlib import Path

DEFAULT_ROOT = Path.home() / ".claude" / "projects"
CURSOR_NAME = "usage-transcripts-cursor.json"
OUT_NAME = "usage-from-transcripts.json"

USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)

# Claude Code slugifies the project path into the directory name: every "/" and
# "-" both become "-", so the slug is genuinely ambiguous. Splitting on the last
# hyphen is WRONG and was caught on first run — "-home-mario-projects-wheelwright-
# track-prompt-lab" reported as "lab", and any hyphenated project would be
# silently misattributed. Since misattribution is the whole failure this tool
# exists to end, resolve against the filesystem instead of guessing.
_SLUG_CACHE: dict = {}


def spoke_from_slug(slug: str) -> str:
    """Recover the project directory name from a Claude Code path slug.

    Walks the slug left to right rebuilding a real path, preferring a directory
    that exists at each step. Falls back to the raw tail only when nothing
    resolves — and says so, rather than inventing a plausible name.
    """
    if slug in _SLUG_CACHE:
        return _SLUG_CACHE[slug]

    parts = [p for p in slug.split("-") if p]
    current = Path("/")
    index = 0
    while index < len(parts):
        # Greedy: prefer the LONGEST next segment that exists, so "track-prompt-lab"
        # beats "track" when both are directories.
        best = None
        for span in range(len(parts) - index, 0, -1):
            candidate = current / "-".join(parts[index:index + span])
            if candidate.is_dir():
                best = (span, candidate)
                break
        if best is None:
            break
        index += best[0]
        current = best[1]

    if current == Path("/"):
        resolved = (slug.strip("-").rsplit("-", 1)[-1] or "unknown") + "?"
    else:
        resolved = current.name or "unknown"
    _SLUG_CACHE[slug] = resolved
    return resolved


def _parse_ts(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def window_key(when: dt.datetime, hours: int = 5) -> str:
    """Bucket a timestamp into a fixed N-hour window, in UTC.

    Anchored to midnight UTC rather than to first-observed-event, so the same
    event always lands in the same bucket no matter when the tool runs. A bucket
    that moves with the observer is not a measurement.
    """
    when = when.astimezone(dt.timezone.utc)
    start_h = (when.hour // hours) * hours
    return when.replace(hour=start_h, minute=0, second=0, microsecond=0).isoformat()


def iter_usage(path: Path):
    """Yield (timestamp, model, usage_dict) for each assistant message."""
    try:
        handle = path.open("r", errors="replace")
    except OSError:
        return
    with handle:
        for line in handle:
            if '"usage"' not in line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            yield (
                _parse_ts(record.get("timestamp")),
                message.get("model") or record.get("model") or "unknown",
                usage,
            )


def scan(root: Path, cursor: dict, since_days=None):
    """Parse new-or-grown transcripts. Returns (rows, files_read, files_skipped)."""
    rows = []
    read = skipped = 0
    cutoff = None
    if since_days:
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=since_days)

    for path in root.rglob("*.jsonl"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if cutoff and dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc) < cutoff:
            continue

        key = str(path)
        seen = cursor.get(key)
        if seen and seen.get("size") == stat.st_size and seen.get("mtime") == stat.st_mtime:
            skipped += 1
            continue

        spoke = spoke_from_slug(path.parent.name)
        for when, model, usage in iter_usage(path):
            rows.append(
                {
                    "spoke": spoke,
                    "model": model,
                    "ts": when.isoformat() if when else None,
                    **{k: usage.get(k) or 0 for k in USAGE_KEYS},
                }
            )
        cursor[key] = {"size": stat.st_size, "mtime": stat.st_mtime}
        read += 1

    return rows, read, skipped


def aggregate(rows):
    totals = collections.Counter()
    by_spoke = collections.defaultdict(collections.Counter)
    by_model = collections.defaultdict(collections.Counter)
    by_window = collections.defaultdict(collections.Counter)
    undated = 0

    for row in rows:
        for key in USAGE_KEYS:
            value = row[key]
            totals[key] += value
            by_spoke[row["spoke"]][key] += value
            by_model[row["model"]][key] += value
        by_spoke[row["spoke"]]["messages"] += 1
        by_model[row["model"]]["messages"] += 1

        when = _parse_ts(row["ts"])
        if when is None:
            undated += 1
            continue
        bucket = by_window[window_key(when)]
        for key in USAGE_KEYS:
            bucket[key] += row[key]
        bucket["messages"] += 1

    return {
        "totals": dict(totals),
        "messages": len(rows),
        "messages_undated": undated,
        "by_spoke": {k: dict(v) for k, v in by_spoke.items()},
        "by_model": {k: dict(v) for k, v in by_model.items()},
        "by_5h_window": {k: dict(v) for k, v in sorted(by_window.items())},
    }


def _billable(counts):
    """Every token class, summed. Cache reads dominate and must not be hidden."""
    return sum(counts.get(k, 0) or 0 for k in USAGE_KEYS)


def render(data, top=10):
    out = []
    totals = data["totals"]
    add = out.append

    add("ANTHROPIC USAGE — measured from Claude Code transcripts")
    add(f"  window   {data['meta']['scanned_since'] or 'all time'}")
    add(f"  source   {data['meta']['files_read']} file(s) read, "
        f"{data['meta']['files_skipped']} unchanged")
    add(f"  messages {data['messages']:,}")
    add("")

    grand = _billable(totals)
    add("BY TOKEN CLASS")
    for key in USAGE_KEYS:
        value = totals.get(key, 0)
        share = (100.0 * value / grand) if grand else 0.0
        add(f"  {key:32} {value:>16,}  {share:>5.1f}%")
    add(f"  {'TOTAL':32} {grand:>16,}")
    add("")

    add(f"BY SPOKE (top {top})")
    ranked = sorted(data["by_spoke"].items(), key=lambda kv: -_billable(kv[1]))
    for name, counts in ranked[:top]:
        total = _billable(counts)
        share = (100.0 * total / grand) if grand else 0.0
        add(f"  {name:28} {total:>16,}  {share:>5.1f}%   out {counts.get('output_tokens',0):>10,}")
    if len(ranked) > top:
        rest = sum(_billable(c) for _, c in ranked[top:])
        add(f"  {'(%d more)' % (len(ranked)-top):28} {rest:>16,}")
    add("")

    add("BY MODEL")
    for name, counts in sorted(data["by_model"].items(), key=lambda kv: -_billable(kv[1])):
        add(f"  {name:36} {_billable(counts):>16,}")
    add("")

    windows = data["by_5h_window"]
    add("BY 5-HOUR WINDOW (most recent 8)")
    if not windows:
        add("  none — no dated messages in range")
    for key, counts in list(windows.items())[-8:]:
        add(f"  {key}  {_billable(counts):>14,}   out {counts.get('output_tokens',0):>9,}")
    if data["messages_undated"]:
        add(f"  ({data['messages_undated']:,} message(s) carried no timestamp — "
            f"counted in totals, absent from windows)")
    add("")
    add("NOT SHOWN: your Max-plan percentage. No API exposes it, so this tool")
    add("does not guess. This is what WE consumed; the plan ceiling is unknown.")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(DEFAULT_ROOT),
                    help="Claude Code projects dir (default: ~/.claude/projects)")
    ap.add_argument("--state-dir", default="WAI-Harness/hub/local/model-routing",
                    help="where the cursor and output JSON live")
    ap.add_argument("--since-days", type=int, default=None,
                    help="only read transcripts modified in the last N days")
    ap.add_argument("--rebuild", action="store_true",
                    help="ignore the cursor and re-read everything")
    ap.add_argument("--render", action="store_true", help="print the dashboard")
    ap.add_argument("--json", action="store_true", help="print the aggregate as JSON")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser()
    if not root.is_dir():
        print(json.dumps({"error": "transcript root not found", "root": str(root)}))
        return 2

    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    cursor_path = state_dir / CURSOR_NAME
    out_path = state_dir / OUT_NAME

    cursor = {}
    if cursor_path.is_file() and not args.rebuild:
        try:
            cursor = json.loads(cursor_path.read_text())
        except ValueError:
            cursor = {}

    rows, files_read, files_skipped = scan(root, cursor, args.since_days)

    # Merge with prior aggregate so an incremental run reports the whole picture,
    # not just the delta. Without this, a cron would show a shrinking total every
    # time it ran and look like usage had collapsed.
    prior_rows = []
    if out_path.is_file() and not args.rebuild:
        try:
            prior_rows = json.loads(out_path.read_text()).get("_rows", [])
        except ValueError:
            prior_rows = []

    all_rows = prior_rows + rows
    data = aggregate(all_rows)
    data["meta"] = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "root": str(root),
        "files_read": files_read,
        "files_skipped": files_skipped,
        "scanned_since": f"last {args.since_days}d" if args.since_days else None,
        "source": "Claude Code transcripts — message.usage, measured",
        "not_measured": ("Max-plan 5h/weekly percentage: no API exposes it. "
                         "This tool reports consumption, never a plan ceiling."),
    }
    data["_rows"] = all_rows

    out_path.write_text(json.dumps(data, indent=2) + "\n")
    cursor_path.write_text(json.dumps(cursor) + "\n")

    if args.render:
        print(render(data, top=args.top))
    elif args.json:
        shown = dict(data)
        shown.pop("_rows", None)
        print(json.dumps(shown, indent=2))
    else:
        print(f"wrote {out_path} — {data['messages']:,} message(s), "
              f"{files_read} file(s) read, {files_skipped} unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
