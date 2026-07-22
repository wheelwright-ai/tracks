#!/usr/bin/env python3
"""pathgraph_generate.py — build the 3 generative PathGraph horizons (current,
near-future, vision) plus index.json, from the live lug corpus and session
tracks, per wilbur/docs/pathgraph-spec.md v1.1.0 ("Multi-File Structure",
"Lugs as PathGraph Nodes", "Aspiration Record Schema").

history.jsonl is a separate, already-working producer (ozi_autopilot.py's
_append_trace) and is read here only to report its count — never written.

current.json and near-future.json are fully rebuilt each run (spec: "rebuilt
from the lug corpus on each PathGraph refresh"). vision.jsonl is append-only:
existing records are preserved and only their status field is updated
(fulfilled), new aspirations are appended, nothing is ever deleted.

Usage:
  python3 tools/pathgraph_generate.py [spoke_root]   # default: .
"""

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools import wai_paths as _wp

# Lug types that map straight to the Current horizon with the generic field
# set (title/perceive/execute/verify/roi/effort_score). epic and spec are
# handled separately — they route to Current and/or Near-future per the
# spec's "Lugs as PathGraph Nodes" table.
GENERIC_CURRENT_TYPES = {
    "task", "feature", "impl", "implementation", "bug", "fix", "chore",
    "idea", "decision", "change", "notation", "other", "refinement",
    "review", "needs-you", "signal", "notice", "ack", "chain", "completion",
    "report", "session-summary", "work", "foundation",
}
OPEN_STATUS_DIRS = ("open", "in_progress")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_spoke_id(root: Path) -> str:
    """Best-effort spoke_id: hub-registry (matched by path) > WAI-State wheel
    abbrev > directory name. Never fabricated beyond these real sources."""
    registry = root / "WAI-Harness" / "hub" / "local" / "hub-registry.json"
    try:
        reg = json.loads(registry.read_text())
        for w in reg.get("wheels", []):
            if Path(w.get("path", "")).resolve() == root.resolve():
                return w.get("spoke_id") or w.get("wheel_id") or root.name
    except (OSError, json.JSONDecodeError):
        pass
    state_path = root / "WAI-Harness" / "spoke" / "local" / "WAI-State.json"
    try:
        state = json.loads(state_path.read_text())
        abbrev = (state.get("wheel") or {}).get("abbrev")
        if abbrev:
            return abbrev
    except (OSError, json.JSONDecodeError):
        pass
    return root.name


def _iter_open_lugs(wai_spoke: Path):
    """Yield (lug_type_dir_name, status_dir_name, lug_dict) for every lug
    under lugs/bytype/*/{open,in_progress}/*.json."""
    bytype = wai_spoke / "lugs" / "bytype"
    if not bytype.is_dir():
        return
    for type_dir in sorted(bytype.iterdir()):
        if not type_dir.is_dir():
            continue
        for status_dir_name in OPEN_STATUS_DIRS:
            status_dir = type_dir / status_dir_name
            if not status_dir.is_dir():
                continue
            for lug_file in sorted(status_dir.glob("*.json")):
                try:
                    lug = json.loads(lug_file.read_text())
                except (OSError, json.JSONDecodeError):
                    continue
                yield type_dir.name, status_dir_name, lug


def _completed_lug_ids(wai_spoke: Path) -> set:
    bytype = wai_spoke / "lugs" / "bytype"
    if not bytype.is_dir():
        return set()
    return {f.stem for f in bytype.glob("*/completed/*.json")}


def build_current_and_near_future(wai_spoke: Path):
    current_items = []
    near_future_epics = []
    near_future_specs = []

    for type_name, status_name, lug in _iter_open_lugs(wai_spoke):
        lug_id = lug.get("id")
        title = lug.get("title")
        if not lug_id or not title:
            continue

        if type_name == "epic":
            initiative_id = lug.get("initiative_id") or lug.get("initiative")
            if initiative_id:
                near_future_epics.append({
                    "id": lug_id,
                    "title": title,
                    "initiative_id": initiative_id,
                    "phase": lug.get("phase"),
                    "status": status_name,
                })
            else:
                current_items.append({
                    "id": lug_id,
                    "type": type_name,
                    "status": status_name,
                    "title": title,
                    "acceptance_criteria": lug.get("acceptance_criteria"),
                    "phase": lug.get("phase"),
                    "blocked_by": lug.get("blocked_by"),
                })
            continue

        if type_name == "spec":
            entry = {
                "id": lug_id,
                "title": title,
                "what": lug.get("what"),
                "why": lug.get("why"),
                "acceptance_criteria": lug.get("acceptance_criteria"),
                "status": status_name,
            }
            current_items.append({**entry, "type": type_name})
            near_future_specs.append(entry)
            continue

        if type_name in GENERIC_CURRENT_TYPES:
            current_items.append({
                "id": lug_id,
                "type": type_name,
                "status": status_name,
                "title": title,
                "perceive": lug.get("perceive"),
                "execute": lug.get("execute"),
                "verify": lug.get("verify"),
                "roi": lug.get("roi"),
                "effort_score": lug.get("effort_score"),
            })

    near_future_initiatives = []
    idx_path = wai_spoke / "initiatives" / "index.json"
    try:
        idx = json.loads(idx_path.read_text())
        for init in idx.get("initiatives", []):
            near_future_initiatives.append({
                "id": init.get("id"),
                "label": init.get("label"),
                "description": init.get("description"),
                "status": init.get("status"),
                "impact_rank": init.get("impact_rank"),
                "lifecycle_state": init.get("lifecycle_state"),
            })
    except (OSError, json.JSONDecodeError):
        pass

    near_future = {
        "generated_at": _now_iso(),
        "initiatives": near_future_initiatives,
        "epics": near_future_epics,
        "specs": near_future_specs,
    }
    near_future["count"] = (
        len(near_future_initiatives) + len(near_future_epics) + len(near_future_specs)
    )

    current = {
        "generated_at": _now_iso(),
        "count": len(current_items),
        "items": current_items,
    }
    return current, near_future


def _load_vision_records(vision_path: Path):
    records = []
    if not vision_path.exists():
        return records
    for line in vision_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _aspiration_id(source_session: str, text: str) -> str:
    digest = hashlib.sha1(f"{source_session}|{text}".encode("utf-8")).hexdigest()[:8]
    slug = "".join(c if c.isalnum() else "-" for c in text.lower())[:40].strip("-")
    return f"aspiration-{slug}-{digest}"


def build_vision(wai_spoke: Path):
    """Append-only merge. Scan sessions/*/track.jsonl 'open' entries (the
    spec's Step 1 scan target: "open array contains unresolved items") for
    aspiration candidates not already recorded; mark existing lug_completed
    ones fulfilled once their target lug lands in completed/.

    Records conform to wilbur/schemas/pathgraph-index.schema.json
    (additionalProperties: false — no ad hoc fields). module has no
    per-spoke enum value yet (schema predates the framework->mywheel rename
    tracked separately); "framework" is the closest legal value for this
    spoke's own aspirations until that schema gets a dedicated update."""
    vision_path = wai_spoke / "pathgraph" / "vision.jsonl"
    records = _load_vision_records(vision_path)
    known_ids = {r.get("id") for r in records}
    completed_ids = _completed_lug_ids(wai_spoke)

    # Drift Detection Protocol step 1: fulfillment check against completed lugs.
    for rec in records:
        if rec.get("status") != "open":
            continue
        related = rec.get("related_lug_ids") or []
        if related and related[0] in completed_ids:
            rec["status"] = "fulfilled"
            rec["fulfilled_lug"] = related[0]

    sessions_dir = wai_spoke / "sessions"
    new_records = []
    if sessions_dir.is_dir():
        for track_file in sorted(sessions_dir.glob("*/track.jsonl")):
            session_name = track_file.parent.name
            try:
                lines = track_file.read_text().splitlines()
            except OSError:
                continue
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("event") != "turn":
                    continue
                for item in row.get("open") or []:
                    if not isinstance(item, dict):
                        continue
                    text = item.get("text")
                    if not text:
                        continue
                    if len(text) < 10:
                        continue  # schema: text minLength 10
                    aid = _aspiration_id(session_name, text)
                    if aid in known_ids:
                        continue
                    known_ids.add(aid)
                    landing = item.get("landing") or {}
                    lug_ref = landing.get("id") if landing.get("kind") == "lug_completed" else None
                    fulfilled = bool(lug_ref and lug_ref in completed_ids)
                    new_records.append({
                        "id": aid,
                        "source_session": session_name,
                        "extracted_at": _now_iso(),
                        "module": "framework",
                        "text": text,
                        "confidence": "inferred",
                        "status": "fulfilled" if fulfilled else "open",
                        "drift_level": None,
                        "fulfilled_session": None,
                        "fulfilled_lug": lug_ref if fulfilled else None,
                        "related_lug_ids": [lug_ref] if lug_ref else [],
                        "tags": [],
                    })

    return records + new_records


def write_pathgraph(root: str):
    working_base, mode = _wp.resolve_wai_root(root)
    if not working_base:
        raise SystemExit(f"No WAI working base found at {root}")
    wai_spoke = Path(working_base)
    pathgraph_dir = wai_spoke / "pathgraph"
    pathgraph_dir.mkdir(parents=True, exist_ok=True)

    current, near_future = build_current_and_near_future(wai_spoke)
    (pathgraph_dir / "current.json").write_text(json.dumps(current, indent=2) + "\n")
    (pathgraph_dir / "near-future.json").write_text(json.dumps(near_future, indent=2) + "\n")

    vision_records = build_vision(wai_spoke)
    with open(pathgraph_dir / "vision.jsonl", "w") as fh:
        for rec in vision_records:
            fh.write(json.dumps(rec) + "\n")

    history_path = pathgraph_dir / "history.jsonl"
    history_count = 0
    if history_path.exists():
        history_count = sum(1 for line in history_path.read_text().splitlines() if line.strip())

    index = {
        "spoke_id": _resolve_spoke_id(Path(root).resolve()),
        "version": "1.0.0",
        "last_rebuild": _now_iso(),
        "mode": mode,
        "files": {
            "history": "history.jsonl",
            "current": "current.json",
            "near_future": "near-future.json",
            "vision": "vision.jsonl",
        },
        "horizon_counts": {
            "history": history_count,
            "current": current["count"],
            "near_future": near_future["count"],
            "vision": len(vision_records),
        },
    }
    (pathgraph_dir / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    return index


def main():
    parser = argparse.ArgumentParser(description="Generate PathGraph horizons")
    parser.add_argument("spoke_root", nargs="?", default=".", help="Path to spoke root (default: .)")
    args = parser.parse_args()
    index = write_pathgraph(args.spoke_root)
    print(json.dumps(index["horizon_counts"], indent=2))


if __name__ == "__main__":
    main()
