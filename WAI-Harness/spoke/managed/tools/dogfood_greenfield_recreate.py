#!/usr/bin/env python3
"""dogfood_greenfield_recreate.py — wipe + recreate the greenfield dogfood bench.

Migration doctrine 5 (docs/wheelwright-v5-control-plane-directive.md, Part IV):
"Greenfield bench (fresh dogfood spoke — tests the first-run experience)... A
phase certifies only when both [benches] pass." This is the greenfield half.

WHAT THIS DOES (end to end, no interactive step required):
  1. Wipes the target dogfood spoke directory (default:
     /home/mario/projects/wheelwright/v5-dogfood) and recreates it empty.
  2. `git init` — the dogfood spoke is its own real git repo, never nested
     inside mywheel (constraint: never create a phantom root, never touch
     mywheel's own git state from here).
  3. Runs harness_init.py --node spoke --layout v4-only against it, from THIS
     wheel's current managed/ cut — "cut from the dogfood, never authored
     separately" (bootstrap_cut.py's principle, reused here for consistency).
  4. Records a FIRST-RUN TRANSCRIPT: a deterministic simulation of what a
     brand-new operator's turn 1 would surface — the exact wakeup file chain
     CLAUDE.md's "Wakeup (MANDATORY — First Turn)" section specifies, read in
     order, with each file's content captured. This is not a live LLM
     session (spawning one recursively from inside a bench tool is out of
     scope and unsafe); it is the deterministic input a first turn would
     read, which is what actually varies release to release.
  5. Writes the transcript under a bench-artifacts directory in MYWHEEL
     (not the dogfood repo) so it survives dogfood wipes and is reviewable
     alongside other phase evidence.

Usage:
    dogfood_greenfield_recreate.py
    dogfood_greenfield_recreate.py --target /path/to/v5-dogfood --artifacts-dir /path
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MYWHEEL_ROOT = HERE.parent.parent.parent.parent  # .../mywheel
HUB_LOCAL = MYWHEEL_ROOT / "WAI-Harness" / "hub" / "local"

DEFAULT_TARGET = Path("/home/mario/projects/wheelwright/v5-dogfood")
DEFAULT_ARTIFACTS_DIR = MYWHEEL_ROOT / "WAI-Harness" / "spoke" / "local" / "bench" / "artifacts"

# The exact wakeup chain CLAUDE.md's "Wakeup (MANDATORY — First Turn)" section
# specifies, in order. First existing file in the "Follow the first wakeup
# file that exists" group wins, matching real wakeup behavior.
WAKEUP_FIXED = ["AGENTS.md", "WAI-Harness/spoke/local/WAI-State.json"]
WAKEUP_FIRST_OF = [
    ".claude/commands/wai.md",
    "WAI-Harness/spoke/commands/wai.md",
    "WAI-Harness/spoke/skills/wai/wai.md",
]


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}" + (f"   (cwd={cwd})" if cwd else ""))
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                           capture_output=True, text=True)


def wipe_and_recreate(target: Path) -> None:
    if target.exists():
        print(f"[1] Wiping existing dogfood spoke at {target}")
        shutil.rmtree(target)
    else:
        print(f"[1] No existing dogfood spoke at {target} — creating fresh")
    target.mkdir(parents=True, exist_ok=True)


def git_init(target: Path) -> dict:
    print(f"[2] git init {target}")
    r = run(["git", "init"], cwd=target)
    run(["git", "config", "user.email", "dogfood@wheelwright.local"], cwd=target)
    run(["git", "config", "user.name", "wheelwright-dogfood-bench"], cwd=target)
    return {"returncode": r.returncode, "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}


def run_harness_init(target: Path) -> dict:
    print("[3] harness_init.py --node spoke --layout v4-only")
    init_script = HERE / "harness_init.py"
    cmd = [sys.executable, str(init_script),
           "--target", str(target),
           "--name", "V5 Dogfood",
           "--node", "spoke",
           "--layout", "v4-only",
           "--hub-path", str(HUB_LOCAL),
           "--force"]
    r = run(cmd)
    print(r.stdout[-3000:])
    if r.returncode != 0:
        print(r.stderr[-2000:], file=sys.stderr)
    return {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}


def capture_first_run_transcript(target: Path) -> dict:
    """Deterministic capture of what turn-1 wakeup would read, in the order
    CLAUDE.md's wakeup protocol specifies."""
    entries = []
    for rel in WAKEUP_FIXED:
        p = target / rel
        entries.append({
            "path": rel,
            "exists": p.exists(),
            "content": p.read_text(encoding="utf-8") if p.exists() else None,
        })

    first_hit = None
    checked = []
    for rel in WAKEUP_FIRST_OF:
        p = target / rel
        exists = p.exists()
        checked.append({"path": rel, "exists": exists})
        if exists and first_hit is None:
            first_hit = rel
    entries.append({
        "wakeup_file_chain_checked": checked,
        "first_existing_wakeup_file": first_hit,
        "content": (target / first_hit).read_text(encoding="utf-8") if first_hit else None,
    })
    return {"entries": entries, "first_existing_wakeup_file": first_hit}


def write_transcript(artifacts_dir: Path, target: Path, git_result: dict,
                      init_result: dict, transcript: dict) -> Path:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = artifacts_dir / f"greenfield-first-run-{ts}.json"

    doc = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Greenfield dogfood bench — first-run transcript. Migration doctrine 5.",
        "dogfood_target": str(target),
        "git_init": git_result,
        "harness_init": {"returncode": init_result["returncode"],
                          "stdout_tail": init_result["stdout"][-3000:],
                          "stderr_tail": init_result["stderr"][-1500:]},
        "wakeup_transcript": transcript,
    }
    out_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Human-readable sibling for quick review.
    md_path = out_path.with_suffix(".md")
    lines = [f"# Greenfield first-run transcript — {doc['captured_at']}", "",
             f"Dogfood target: `{target}`", "",
             f"## git init", "", f"returncode: {git_result['returncode']}", "",
             f"## harness_init.py", "", f"returncode: {init_result['returncode']}", "",
             "## Wakeup chain (what turn 1 reads, in order)", ""]
    for e in transcript["entries"]:
        if "path" in e:
            lines.append(f"### `{e['path']}` (exists={e['exists']})")
            lines.append("```")
            lines.append((e["content"] or "(missing)")[:4000])
            lines.append("```")
        else:
            lines.append(f"### First existing wakeup pointer: `{e['first_existing_wakeup_file']}`")
            lines.append("```")
            lines.append((e["content"] or "(none found)")[:4000])
            lines.append("```")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=str(DEFAULT_TARGET))
    ap.add_argument("--artifacts-dir", default=str(DEFAULT_ARTIFACTS_DIR))
    args = ap.parse_args()

    target = Path(args.target).resolve() if Path(args.target).exists() or True else Path(args.target)
    target = Path(args.target)
    artifacts_dir = Path(args.artifacts_dir)

    wipe_and_recreate(target)
    git_result = git_init(target)
    init_result = run_harness_init(target)
    if init_result["returncode"] != 0:
        print("ERROR: harness_init.py failed — see stderr above", file=sys.stderr)
        return 1

    transcript = capture_first_run_transcript(target)
    out_path = write_transcript(artifacts_dir, target, git_result, init_result, transcript)

    print(f"\n[done] dogfood spoke recreated at {target}")
    print(f"[done] first-run transcript written to {out_path} "
          f"(and {out_path.with_suffix('.md')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
