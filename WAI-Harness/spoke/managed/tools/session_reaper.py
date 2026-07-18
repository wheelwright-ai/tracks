#!/usr/bin/env python3
"""session_reaper.py — archive stale, closeout-less session dirs into sessions/_archive/.

Arm of the hygiene advisor (impl-hygiene-advisor-and-arms-v1). A session dir under
`sessions/` is "reapable" when it carries no evidence it was ever properly closed
out (no `{"event": "closeout", ...}` row in its track.jsonl, or an empty/missing
track) AND it is old enough that it is very unlikely to be a session someone will
resume. This tool never calls git itself except when explicitly told to (--apply
--exec-git); by default (dry-run) it only PRINTS the planned `git mv` set so a
human/orchestrator retains git custody, per the standing rule that arms build
files + dry-run only and the orchestrator owns git.

FLOORS (hard, non-bypassable — no flag can turn these off):
  1. Never the live/current session, and never a session with an open lane.
     Both are the SAME check: a lane's `wai_session` field (from the lanes
     registry, `runtime/sessions-live.json`, read via worktree_guard.live_lanes())
     IS the session dir it owns. Scanning `runtime/lanes/` directly would only
     yield cc_sid directories, not session names — the registry is the correct,
     authoritative source (Fable Agent B correction on the parent lug).
     Defense-in-depth: WAI-State.json's `_session_state.current_session` and
     `last_session_id` are ALSO always protected, even if stale/inconsistent
     with the registry.
  2. Never younger than --age-days. Age is computed from the session dir NAME's
     embedded `YYYYMMDD-HHMM` timestamp (assumed UTC — that is how
     worktree_guard._allocate_wai_session stamps it), taking the MORE RECENT of
     (name timestamp, last valid track.jsonl line's `ts` field) as "last activity"
     — never filesystem mtime, which a worktree checkout or `git mv` can reset
     (Fable Agent B correction).
  3. A session dir whose name carries no parseable timestamp is SKIPPED entirely
     (never reaped, never assumed stale) — unparseable is not evidence of age.

Reap rule: no closeout row OR empty track, AND age_days >= --age-days, AND not
floor-protected.

Dry-run is the DEFAULT. Nothing is moved unless --apply is passed. Even with
--apply, this tool moves files itself only via `git mv` subprocess (never `rm`,
never a plain filesystem move) so history is preserved — pass --exec-git along
with --apply to actually execute; without --exec-git, --apply still only prints
(belt-and-suspenders: a single flag typo can never cause a live mutation).

A JSON receipt is written to <spoke-root>/WAI-Harness/hub/local/maintenance/receipts/
and mirrored to .../hub/local/maintenance/session-reaper-latest.json.

CLI:
    python3 session_reaper.py --spoke-root DIR [--age-days 3] [--apply --exec-git] [--quiet]
Exit: 0 on a clean run (even when reap candidates exist — this is an advisory/
      report tool, not a pass/fail gate); 2 on an internal error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import wai_paths  # noqa: E402
import worktree_guard  # noqa: E402

_TS_RE = re.compile(r"(\d{8})-(\d{4})")
DEFAULT_AGE_DAYS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_name_ts(name: str):
    m = _TS_RE.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _track_info(track_path: Path):
    """Return (has_closeout: bool, is_empty: bool, last_ts: datetime|None)."""
    if not track_path.exists() or track_path.stat().st_size == 0:
        return False, True, None
    has_closeout = False
    last_ts = None
    saw_line = False
    try:
        for line in track_path.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            saw_line = True
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("event") == "closeout":
                has_closeout = True
            ts = _parse_iso(d.get("ts"))
            if ts is not None and (last_ts is None or ts > last_ts):
                last_ts = ts
    except OSError:
        return False, True, None
    return has_closeout, not saw_line, last_ts


def _protected_sessions(spoke_root: str, base: str) -> set:
    protected = set()
    try:
        for meta in worktree_guard.live_lanes(base).values():
            wai = meta.get("wai_session")
            if wai:
                protected.add(wai)
    except Exception:
        pass
    state_path = Path(base) / "WAI-State.json"
    try:
        state = json.loads(state_path.read_text())
        ss = state.get("_session_state", {})
        for key in ("current_session", "last_session_id"):
            v = ss.get(key)
            if v:
                protected.add(v)
    except Exception:
        pass
    return protected


def scan(spoke_root: str, age_days: int = DEFAULT_AGE_DAYS) -> dict:
    base, mode = wai_paths.resolve_wai_root(spoke_root)
    if base is None:
        return {"ok": False, "error": f"no WAI working base found under {spoke_root}"}
    sessions_dir = Path(base) / "sessions"
    if not sessions_dir.is_dir():
        return {"ok": False, "error": f"no sessions dir at {sessions_dir}"}

    protected = _protected_sessions(spoke_root, base)
    now = _now()
    threshold = now.timestamp() - age_days * 86400

    reapable, skipped_protected, skipped_young, skipped_has_closeout, skipped_unparseable = [], [], [], [], []

    for entry in sorted(sessions_dir.iterdir()):
        if not entry.is_dir() or entry.name == "_archive":
            continue
        name = entry.name
        if name in protected:
            skipped_protected.append(name)
            continue
        name_ts = _parse_name_ts(name)
        if name_ts is None:
            skipped_unparseable.append(name)
            continue
        track_path = entry / "track.jsonl"
        has_closeout, is_empty, last_track_ts = _track_info(track_path)
        last_activity = name_ts
        if last_track_ts is not None and last_track_ts > last_activity:
            last_activity = last_track_ts
        age_ok = last_activity.timestamp() <= threshold
        if has_closeout and not is_empty:
            skipped_has_closeout.append(name)
            continue
        if not age_ok:
            skipped_young.append({
                "name": name,
                "age_days": round((now - last_activity).total_seconds() / 86400, 2),
            })
            continue
        reapable.append({
            "name": name,
            "last_activity": last_activity.isoformat(),
            "age_days": round((now - last_activity).total_seconds() / 86400, 2),
            "has_closeout": has_closeout,
            "track_empty": is_empty,
            "src": str(entry.relative_to(spoke_root)) if _is_relative(entry, spoke_root) else str(entry),
            "dst": str((sessions_dir / "_archive" / name).relative_to(spoke_root)) if _is_relative(sessions_dir, spoke_root) else str(sessions_dir / "_archive" / name),
        })

    return {
        "ok": True,
        "spoke_root": os.path.abspath(spoke_root),
        "base": base,
        "harness_mode": mode,
        "age_days_threshold": age_days,
        "ts": now.isoformat(),
        "protected_sessions": sorted(protected),
        "count_reapable": len(reapable),
        "reapable": reapable,
        "count_skipped_protected": len(skipped_protected),
        "skipped_protected": skipped_protected,
        "count_skipped_too_young": len(skipped_young),
        "skipped_too_young": skipped_young,
        "count_skipped_has_closeout": len(skipped_has_closeout),
        "count_skipped_unparseable_name": len(skipped_unparseable),
        "skipped_unparseable_name": skipped_unparseable,
    }


def _is_relative(p: Path, root) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


def apply_reap(spoke_root: str, manifest: dict, exec_git: bool = False) -> dict:
    """Execute the planned git mv set. Only actually runs git when exec_git=True
    (belt-and-suspenders on top of --apply, per the module docstring)."""
    moves = []
    archive_dir = Path(manifest["base"]) / "sessions" / "_archive"
    for item in manifest["reapable"]:
        src = os.path.join(spoke_root, item["src"])
        dst = os.path.join(spoke_root, item["dst"])
        moves.append({"src": src, "dst": dst})
        if exec_git:
            archive_dir.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "mv", item["src"], item["dst"]], cwd=spoke_root, check=True)
    return {"executed": bool(exec_git), "moves": moves, "count": len(moves)}


def _write_receipt(spoke_root: str, manifest: dict, apply_result: dict | None) -> list:
    receipt = {
        "receipt_id": f"session-reaper-{manifest['ts'].replace(':', '')}",
        "tool": "session_reaper.py",
        "ts": manifest["ts"],
        "spoke_root": manifest["spoke_root"],
        "age_days_threshold": manifest["age_days_threshold"],
        "count_reapable": manifest["count_reapable"],
        "count_skipped_protected": manifest["count_skipped_protected"],
        "count_skipped_too_young": manifest["count_skipped_too_young"],
        "count_skipped_has_closeout": manifest["count_skipped_has_closeout"],
        "count_skipped_unparseable_name": manifest["count_skipped_unparseable_name"],
        "reapable_names": [r["name"] for r in manifest["reapable"]],
        "applied": bool(apply_result and apply_result.get("executed")),
    }
    hub_maint = Path(spoke_root) / "WAI-Harness" / "hub" / "local" / "maintenance"
    written = []
    try:
        receipts_dir = hub_maint / "receipts"
        receipts_dir.mkdir(parents=True, exist_ok=True)
        p = receipts_dir / f"{receipt['receipt_id']}.json"
        p.write_text(json.dumps(receipt, indent=2))
        written.append(str(p))
        latest = hub_maint / "session-reaper-latest.json"
        latest.write_text(json.dumps(receipt, indent=2))
        written.append(str(latest))
    except OSError as e:
        receipt["_receipt_write_error"] = str(e)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Archive stale, closeout-less sessions into sessions/_archive/.")
    ap.add_argument("--spoke-root", default=".", help="spoke root (contains WAI-Harness/)")
    ap.add_argument("--age-days", type=int, default=DEFAULT_AGE_DAYS)
    ap.add_argument("--apply", action="store_true", help="write the receipt as an apply run (still requires --exec-git to actually move anything)")
    ap.add_argument("--exec-git", action="store_true", help="actually run `git mv` for each reapable session (requires --apply)")
    ap.add_argument("--quiet", action="store_true", help="suppress the human-readable header, print only JSON")
    args = ap.parse_args(argv)

    manifest = scan(args.spoke_root, args.age_days)
    if not manifest.get("ok"):
        print(json.dumps(manifest, indent=2))
        return 2

    if not args.quiet:
        print(f"session_reaper: {manifest['count_reapable']} reapable "
              f"(age >= {manifest['age_days_threshold']}d, no closeout row), "
              f"{manifest['count_skipped_protected']} protected, "
              f"{manifest['count_skipped_too_young']} too young.")
        for item in manifest["reapable"][:20]:
            print(f"  git mv {item['src']}  {item['dst']}   # age={item['age_days']}d closeout={item['has_closeout']}")
        if manifest["count_reapable"] > 20:
            print(f"  ... and {manifest['count_reapable'] - 20} more")

    apply_result = None
    if args.apply:
        apply_result = apply_reap(args.spoke_root, manifest, exec_git=args.exec_git)
        if not args.quiet:
            print(json.dumps({"apply": apply_result}, indent=2))

    written = _write_receipt(args.spoke_root, manifest, apply_result)
    manifest["_receipt_written"] = written

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
