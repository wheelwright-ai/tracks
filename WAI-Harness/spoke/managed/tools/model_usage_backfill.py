#!/usr/bin/env python3
"""
Model usage backfill — Tier-0 telemetry for model-interface profiles.

Walks sessions/*/track.jsonl and emits one `model_usage` event per model-tagged
turn into model-usage/usage.jsonl, via model_usage_logger's writer (single
schema owner — this tool defines no event shape of its own).

Idempotent on dedupe key (session_id, turn): reruns add zero rows.
quality_rating / rework_required stay null here by design — they join from
deterministic oracle results in the profile builder, never from track prose.

Usage:
    python3 tools/model_usage_backfill.py                 # all sessions
    python3 tools/model_usage_backfill.py --session session-20260712-1817
    python3 tools/model_usage_backfill.py --dry-run

Spec: spec-model-interface-profiles-v1 (Tier 0 must cost zero marginal tokens).
Lug:  impl-model-usage-telemetry-activation-v1.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import model_usage_logger as mul


def resolve_base(spoke_root="."):
    """Data-plane base (v4: WAI-Harness/spoke/local), same resolver the logger uses."""
    try:
        from wai_paths import resolve_wai_root

        root, mode = resolve_wai_root(str(spoke_root))
        if root and mode != "none":
            return Path(root)
    except Exception:
        pass
    return Path(spoke_root) / "WAI-Spoke"


def existing_keys(usage_file: Path):
    """(session_id, turn) pairs already present among model_usage events."""
    keys = set()
    if not usage_file.exists():
        return keys
    with open(usage_file) as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "model_usage" and e.get("session_id") is not None and e.get("turn") is not None:
                keys.add((e["session_id"], e["turn"]))
    return keys


def provider_for(model: str) -> str:
    return "anthropic" if str(model).startswith("claude") else "unknown"


def iter_track_turns(session_dir: Path):
    track = session_dir / "track.jsonl"
    if not track.exists():
        return
    with open(track) as f:
        for line in f:
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("event") == "turn" and e.get("model") and e.get("turn") is not None:
                yield e


def backfill(base: Path, only_session=None, dry_run=False):
    sessions_dir = base / "sessions"
    usage_file = base / "model-usage" / "usage.jsonl"

    # Point the logger's module-level target at our resolved base explicitly
    # (its import-time cwd resolution and ours must never diverge).
    mul.USAGE_DIR = usage_file.parent
    mul.USAGE_FILE = usage_file

    seen = existing_keys(usage_file)
    per_model, emitted, skipped = {}, 0, 0

    session_dirs = sorted(d for d in sessions_dir.iterdir() if d.is_dir()) if sessions_dir.is_dir() else []
    if only_session:
        session_dirs = [d for d in session_dirs if d.name == only_session]

    for sdir in session_dirs:
        session_id = sdir.name
        for e in iter_track_turns(sdir):
            key = (session_id, e["turn"])
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            model = e["model"]
            if not dry_run:
                mul.log_event(
                    "model_usage",
                    provider=provider_for(model),
                    model=model,
                    task_type=e.get("phase") or "session-turn",
                    complexity=None,
                    tokens_in=e.get("input_tokens"),
                    tokens_out=e.get("output_tokens"),
                    cache_read_tokens=e.get("cache_read_tokens"),
                    cache_creation_tokens=e.get("cache_creation_tokens"),
                    cost_estimate=None,
                    duration_ms=None,
                    quality_rating=None,
                    rework_required=None,
                    session_id=session_id,
                    turn=e["turn"],
                    ts=e.get("ts"),
                    spoke_id="mywheel",
                    source="track_backfill",
                )
            per_model[model] = per_model.get(model, 0) + 1
            emitted += 1

    return {"emitted": emitted, "skipped_existing": skipped, "per_model": per_model, "usage_file": str(usage_file)}


def main():
    ap = argparse.ArgumentParser(description="Backfill model_usage events from session tracks")
    ap.add_argument("--spoke-root", default=".")
    ap.add_argument("--session", help="only this session id (closeout uses this)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base = resolve_base(args.spoke_root)
    result = backfill(base, only_session=args.session, dry_run=args.dry_run)

    print(f"model_usage_backfill: {result['emitted']} emitted, {result['skipped_existing']} already present")
    for m, c in sorted(result["per_model"].items(), key=lambda kv: -kv[1]):
        print(f"  {m}: {c}")
    print(f"  -> {result['usage_file']}")


if __name__ == "__main__":
    main()
