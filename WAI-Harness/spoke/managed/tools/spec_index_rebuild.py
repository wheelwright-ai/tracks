#!/usr/bin/env python3
"""spec_index_rebuild.py — rebuild the canonical v4 spec index (spec-spec-system-v1).

Rerunnable, idempotent: regenerates WAI-Harness/spoke/local/WAI-SpecIndex.jsonl
from BOTH real v4 spec source roots:

  - WAI-Harness/spoke/local/lugs/bytype/spec/**
  - WAI-Harness/spoke/managed/knowledge/spec/**

Supersedes the dead v3 tools (hub/managed/tools/regen_spec_index.py and its
hub/local/tools/ duplicate), which never populate data on this repo because
they (1) walk the archived WAI-Spoke/ v3 layout and (2) hardcode
SPEC_STATUSES = ('draft', 'active', 'deprecated'), silently skipping the
'open' and 'completed' status dirs that hold the majority of real specs.
This tool globs every immediate subdirectory under each source root instead
of hardcoding a status allowlist, and writes to the v4 sibling-index
location (alongside WAI-BoltIndex.jsonl and WAI-LugIndex.jsonl at
spoke/local/ root), not the dead WAI-Spoke/ path. The two v3 tools are left
untouched — out of scope for this packet.

Usage:
  python3 spec_index_rebuild.py [--mywheel-path PATH] [--check]
"""
import argparse
import json
import sys
from pathlib import Path

SOURCE_ROOTS = [
    "WAI-Harness/spoke/local/lugs/bytype/spec",
    "WAI-Harness/spoke/managed/knowledge/spec",
]
OUTPUT_PATH = "WAI-Harness/spoke/local/WAI-SpecIndex.jsonl"


def resolve_subject_id(data: dict):
    """3-step fallback: flat subject_id -> subject.id (if dict) -> None."""
    subject_id = data.get("subject_id")
    if isinstance(subject_id, str) and subject_id:
        return subject_id
    subject = data.get("subject")
    if isinstance(subject, dict):
        sid = subject.get("id")
        if isinstance(sid, str) and sid:
            return sid
    return None


def load_spec(path: Path, mywheel_path: Path):
    """Load and flatten one spec JSON file. Returns None on parse failure (warns)."""
    try:
        with path.open() as f:
            data = json.load(f)
    except Exception as exc:
        print(f"WARNING: skipping {path} — could not parse JSON: {exc}", file=sys.stderr)
        return None

    try:
        file_path = str(path.relative_to(mywheel_path))
    except ValueError:
        file_path = str(path)

    return {
        "subject_id": resolve_subject_id(data),
        "id": data.get("id"),
        "title": data.get("title", ""),
        "status": data.get("status", ""),
        "path": file_path,
    }


def collect_specs(mywheel_path: Path):
    """Scan both SOURCE_ROOTS, globbing every status subdirectory (no allowlist).

    Returns (records, count_lugs_bytype_spec, count_managed_knowledge_spec).
    """
    records = []
    per_root_counts = []
    for root in SOURCE_ROOTS:
        root_dir = mywheel_path / root
        root_count = 0
        if not root_dir.is_dir():
            per_root_counts.append(root_count)
            continue
        for status_dir in sorted(p for p in root_dir.iterdir() if p.is_dir()):
            for spec_file in sorted(status_dir.glob("*.json")):
                record = load_spec(spec_file, mywheel_path)
                if record is not None:
                    records.append(record)
                    root_count += 1
        per_root_counts.append(root_count)
    return records, per_root_counts[0], per_root_counts[1]


def write_index(records, out_path: Path):
    """Overwrite out_path, one json.dumps(record) + '\\n' per record."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def check_index(out_path: Path) -> bool:
    """Re-read every line back with json.loads to prove the file is valid JSONL."""
    try:
        with out_path.open() as f:
            for line in f:
                if line.strip():
                    json.loads(line)
    except Exception as exc:
        print(f"CHECK FAILED: {out_path} is not valid JSONL: {exc}", file=sys.stderr)
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description="Rebuild the v4 canonical spec index")
    ap.add_argument("--mywheel-path", default="/home/mario/projects/wheelwright/mywheel")
    ap.add_argument("--check", action="store_true", help="re-validate written JSONL, exit 1 on failure")
    args = ap.parse_args()

    mywheel_path = Path(args.mywheel_path)
    out_path = mywheel_path / OUTPUT_PATH

    records, count_local, count_managed = collect_specs(mywheel_path)
    write_index(records, out_path)

    print(
        f"Indexed {len(records)} specs "
        f"({count_local} from lugs/bytype/spec, {count_managed} from managed/knowledge/spec) "
        f"-> {out_path}"
    )

    if args.check:
        if not check_index(out_path):
            sys.exit(1)


if __name__ == "__main__":
    main()
