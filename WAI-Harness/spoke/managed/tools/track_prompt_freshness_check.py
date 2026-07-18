#!/usr/bin/env python3
"""
Track prompt freshness check — run at wakeup to detect and auto-update outdated
WAI Track prompt versions.

Compares the spoke's local copy against the highest-versioned file in the
canonical source dir (track-prompt-lab/prompts/). Copies and writes a sidecar
meta file if the spoke is behind.

Always exits 0 — a hiccup must never block session entry.
Prints one line if updated; silent if already current.

Usage:
    python3 track_prompt_freshness_check.py --spoke-root /path/to/spoke
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
import datetime
from pathlib import Path

PROMPT_SOURCE_DIR = Path("/home/mario/projects/wheelwright/track-prompt-lab/prompts")
VERSION_STEM_RE = re.compile(r"^v([0-9].*)$")
VERSION_FIELD_RE = re.compile(r"^version:\s*(\S+)", re.MULTILINE)
VERSION_HEADER_RE = re.compile(r"^#\s*WAI Track\s+v([0-9][^\s]*)", re.MULTILINE)


def _semver_key(version_str: str) -> tuple:
    parts = []
    for p in re.split(r"[.\-]", version_str):
        try:
            parts.append((0, int(p)))
        except ValueError:
            parts.append((1, p))
    return tuple(parts)


def find_head():
    if not PROMPT_SOURCE_DIR.exists():
        return None
    candidates = []
    for f in PROMPT_SOURCE_DIR.glob("v*.md"):
        m = VERSION_STEM_RE.match(f.stem)
        if not m:
            continue
        ver = m.group(1)
        try:
            _semver_key(ver)
            candidates.append((ver, f))
        except Exception:
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: _semver_key(x[0]))
    return candidates[-1]


def resolve_ref_dir(spoke_root: Path) -> Path:
    v4 = spoke_root / "WAI-Harness" / "spoke" / "local" / "reference"
    v3 = spoke_root / "WAI-Spoke" / "reference"
    if v4.exists():
        return v4
    if v3.exists():
        return v3
    return v4


def read_local_version(ref_dir: Path) -> str:
    meta = ref_dir / "track-prompt-meta.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text()).get("version", "0.0.0")
        except Exception:
            pass
    prompt = ref_dir / "track-prompt-active.md"
    if prompt.exists():
        try:
            content = prompt.read_text()
            m = VERSION_FIELD_RE.search(content)
            if m:
                return m.group(1)
            m = VERSION_HEADER_RE.search(content)
            if m:
                return m.group(1)
        except Exception:
            pass
    return "0.0.0"


def version_lt(a: str, b: str) -> bool:
    return _semver_key(a) < _semver_key(b)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spoke-root", default=".", help="spoke root directory")
    args = ap.parse_args()

    try:
        spoke_root = Path(args.spoke_root).resolve()
        head = find_head()
        if not head:
            return

        head_version, head_path = head
        ref_dir = resolve_ref_dir(spoke_root)
        local_version = read_local_version(ref_dir)

        if not version_lt(local_version, head_version):
            return

        ref_dir.mkdir(parents=True, exist_ok=True)
        dest = ref_dir / "track-prompt-active.md"
        shutil.copy2(head_path, dest)

        content = head_path.read_text()
        sidecar = {
            "version": head_version,
            "file": "track-prompt-active.md",
            "source": str(head_path),
            "sha256": hashlib.sha256(content.encode()).hexdigest(),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "previous_version": local_version,
        }
        (ref_dir / "track-prompt-meta.json").write_text(json.dumps(sidecar, indent=2) + "\n")
        print(f"Track prompt: updated v{local_version} -> v{head_version}")

    except Exception as exc:
        print(f"track-prompt-freshness: check skipped ({exc})", file=sys.stderr)


if __name__ == "__main__":
    main()
