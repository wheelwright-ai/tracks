#!/usr/bin/env python3
"""bootstrap_cut.py — produce a WAI bootstrap from the harness we actually run.

WHAT A BOOTSTRAP IS, and how it differs from distribution. Fleet spokes PULL
incremental spoke updates from mywheel and already have a wheel; that path exists
and works (harness_distribute_fleet.py). A BOOTSTRAP is the other case entirely: a
stranger with nothing, pulling a git project to stand up their own wheel — a hub
AND a spoke — from zero. Full hydration, not an update.

CUT FROM THE DOGFOOD, NEVER AUTHORED SEPARATELY. The payload is assembled from the
live managed tree that this wheel runs every day. A hand-maintained bootstrap
becomes a brochure: it drifts from reality, and drift is invisible until someone
adopts it and fails. This is the same reason the dogfood spoke must self-heal
rather than be hand-fixed.

INCLUDE, DO NOT EXCLUDE. The obvious design is a deny-list of deprecated things.
That was tried and immediately produced a false positive — deploy_commands.py was
flagged "deprecated" because the word appears in its prose ABOUT something else,
minutes after it was used in production. A wrong exclusion ships a broken harness
to someone who cannot debug it, so this builds from an explicit include set and
reports removal CANDIDATES for human review rather than acting on a guess.

WHAT IS DELIBERATELY LEFT OUT: this wheel's local state. Its lugs, sessions,
savepoints, tracks, registry and hub data are mywheel's memory, not a starting
point. A new wheel begins with an empty brain and fills it by living.

Usage:
    bootstrap_cut.py build --out DIR [--dry-run]
    bootstrap_cut.py candidates          # removal candidates, for human review
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANAGED = HERE.parent
ROOT = MANAGED.parent.parent.parent

# The include set. Everything a wheel needs to EXIST and to improve itself.
INCLUDE = [
    ("tools", "spoke/managed/tools"),
    (".claude/commands", "spoke/managed/.claude/commands"),
    (".claude/hooks", "spoke/managed/.claude/hooks"),
    ("templates", "spoke/managed/templates"),
    ("tests", "spoke/managed/tests"),
    ("schemas", "spoke/managed/schemas"),
]

# Local memory — deliberately NOT carried. A new wheel starts empty.
EXCLUDE_NAMES = {"__pycache__", ".DS_Store", "harness.db", "harness.db-wal",
                 "harness.db-shm", "events-journal.jsonl"}
EXCLUDE_SUFFIX = {".pyc", ".bak", ".tmp", ".log"}


def _skip(p: Path) -> bool:
    return (p.name in EXCLUDE_NAMES or p.suffix in EXCLUDE_SUFFIX
            or any(part in EXCLUDE_NAMES for part in p.parts))


def _copy_tree(src: Path, dst: Path, dry=False):
    n = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_NAMES]
        for f in files:
            s = Path(root) / f
            if _skip(s):
                continue
            rel = s.relative_to(src)
            d = dst / rel
            if not dry:
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s, d)
            n += 1
    return n


def trim_capabilities(payload_files, dry=False):
    """Carry only the cards whose files actually shipped.

    The operator's requirement: the bootstrap includes the CG for the current
    harness WITHOUT the unused aspects, so it stays light and the receiving hub
    grows it from its own wheel's activity. A card pointing at a file the adopter
    does not have is worse than an absent card — it describes a capability they
    cannot verify or use.
    """
    src = MANAGED / "capabilities-graph.json"
    if not src.exists():
        return None
    cg = json.load(open(src))
    kept, dropped = [], []
    for e in cg.get("entries", []):
        paths = e.get("file_paths") or []
        if not paths or any(os.path.basename(p) in payload_files for p in paths):
            kept.append(e)
        else:
            dropped.append(e.get("id"))
    cg["entries"] = kept
    cg["bootstrap_note"] = (
        "Trimmed for bootstrap: cards whose files did not ship were removed. A card "
        "pointing at a file the adopter does not have describes a capability they can "
        "neither verify nor use. The receiving hub grows this graph from its own "
        "wheel's activity — that is the point of the circle, not a gap to backfill.")
    return cg, dropped


def removal_candidates():
    """Report what MIGHT be removable. Never act on it.

    Deliberately advisory. The first attempt at automatic deprecation detection
    flagged a tool that had been used in production minutes earlier, because the
    word 'deprecated' appeared in its prose about something else. A wrong removal
    ships a broken harness to someone with no way to debug it, so this reports and
    a human decides.
    """
    out = []
    for t in sorted((MANAGED / "tools").glob("*.py")):
        head = t.read_text(errors="ignore")[:2000]
        first = head.split('"""')[1][:200] if '"""' in head else ""
        if re.search(r"^\s*(DEPRECATED|RETIRED)\b", first, re.M | re.I):
            out.append({"file": t.name, "signal": "docstring opens with DEPRECATED/RETIRED",
                        "confidence": "high"})
        elif re.search(r"\bWAI-Spoke\b", head) and "v3" in head:
            out.append({"file": t.name, "signal": "references the v3 WAI-Spoke layout",
                        "confidence": "low — may be a deliberate legacy fallback"})
    return out


def build(out_dir, dry=False):
    out = Path(out_dir)
    report = {"ok": True, "dry_run": dry, "out": str(out), "copied": {}, "payload_files": 0}

    version = (ROOT / "WAI-Harness" / "VERSION").read_text().strip() if (ROOT / "WAI-Harness" / "VERSION").exists() else "unknown"
    report["harness_version"] = version

    payload_files = set()
    for dest_rel, src_rel in INCLUDE:
        src = ROOT / "WAI-Harness" / src_rel
        if not src.exists():
            report["copied"][dest_rel] = 0
            continue
        dst = out / "harness" / dest_rel
        n = _copy_tree(src, dst, dry)
        report["copied"][dest_rel] = n
        for root, _, files in os.walk(src):
            for f in files:
                if not _skip(Path(root) / f):
                    payload_files.add(f)
    report["payload_files"] = len(payload_files)

    trimmed = trim_capabilities(payload_files, dry)
    if trimmed:
        cg, dropped = trimmed
        report["capabilities"] = {"kept": len(cg["entries"]), "dropped": len(dropped)}
        if not dry:
            (out / "harness").mkdir(parents=True, exist_ok=True)
            json.dump(cg, open(out / "harness" / "capabilities-graph.json", "w"),
                      indent=2, ensure_ascii=False)

    report["removal_candidates"] = removal_candidates()

    if not dry:
        (out / "harness").mkdir(parents=True, exist_ok=True)
        (out / "harness" / "VERSION").write_text(version + "\n")
        _write_install(out, version, report)
        _write_install_sh(out)
    return report



INSTALL_SH = r"""#!/usr/bin/env bash
# install.sh — stand up a wheel from this bootstrap.
#
# WHY THIS EXISTS. harness_init.py scaffolds a node: directories, CLAUDE.md,
# AGENTS.md, state. It does NOT place the harness payload, because in the fleet it
# runs inside a repo that already HAS one. From a bootstrap there is nothing to
# copy from, so a scaffold-only install leaves a wheel with 0 tools that looks
# correct and does nothing. Caught by standing up an actual wheel and running its
# instruments — file counts alone would have reported success.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() { echo "usage: install.sh --target DIR --name NAME --node {hub|spoke} [--hub-path DIR]"; exit 2; }
TARGET=""; NAME=""; NODE="spoke"; HUBPATH=""
while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --name)   NAME="$2";   shift 2 ;;
    --node)   NODE="$2";   shift 2 ;;
    --hub-path) HUBPATH="$2"; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$TARGET" ] && [ -n "$NAME" ] || usage
[ -d "$TARGET" ] || { echo "target does not exist: $TARGET"; exit 1; }

echo "[wai] 1/3 scaffolding $NODE ..."
ARGS=(--target "$TARGET" --name "$NAME" --node "$NODE")
[ -n "$HUBPATH" ] && ARGS+=(--hub-path "$HUBPATH")
python3 "$HERE/harness/tools/harness_init.py" "${ARGS[@]}" >/dev/null

echo "[wai] 2/3 placing the harness payload ..."
DEST="$TARGET/WAI-Harness/spoke/managed"
mkdir -p "$DEST"
for d in tools templates tests schemas; do
  [ -d "$HERE/harness/$d" ] && cp -R "$HERE/harness/$d" "$DEST/"
done
mkdir -p "$DEST/.claude"
for d in commands hooks; do
  [ -d "$HERE/harness/.claude/$d" ] && cp -R "$HERE/harness/.claude/$d" "$DEST/.claude/"
done
[ -f "$HERE/harness/capabilities-graph.json" ] && cp "$HERE/harness/capabilities-graph.json" "$DEST/"
[ -f "$HERE/harness/VERSION" ] && cp "$HERE/harness/VERSION" "$TARGET/WAI-Harness/VERSION"

# The RUNNING copy. Canon is what ships; .claude/ at the root is what executes.
# Skipping this is the drift that hid a dead gate for ten days in the wheel that
# produced this bootstrap.
echo "[wai] 3/3 deploying the running copy ..."
mkdir -p "$TARGET/.claude/commands" "$TARGET/.claude/hooks"
cp -R "$DEST/.claude/commands/." "$TARGET/.claude/commands/" 2>/dev/null || true
cp -R "$DEST/.claude/hooks/."    "$TARGET/.claude/hooks/"    2>/dev/null || true
chmod +x "$TARGET/.claude/hooks/"* 2>/dev/null || true
chmod +x "$DEST/tools/"*.py 2>/dev/null || true

TOOLS=$(ls "$DEST/tools/"*.py 2>/dev/null | wc -l | tr -d ' ')
echo "[wai] done: $NODE at $TARGET, harness $(cat "$TARGET/WAI-Harness/VERSION" 2>/dev/null || echo '?'), $TOOLS tools"
[ "$TOOLS" -gt 0 ] || { echo "[wai] FAILED: no tools placed - this wheel would look correct and do nothing"; exit 1; }
"""


def _write_install_sh(out: Path):
    p = out / "install.sh"
    p.write_text(INSTALL_SH)
    p.chmod(0o755)


def _write_install(out: Path, version, report):
    """The adopter-facing entry point. Two commands, in order, and why."""
    (out / "README.md").write_text(f"""# Wheelwright (WAI) Bootstrap — harness {version}

This creates a **wheel**: a hub and a spoke. Not a library you import — a working
practice your AI agent runs.

## Why a hub first

The hub holds what only makes sense centrally: your inbox, the capabilities graph,
your taste and preferences, and the registry of your spokes. A spoke without a hub
is much less valuable — it can improve itself but it has nowhere to accumulate what
it learns, and nothing to redistribute that learning back from.

So the order matters:

```
./install.sh --target <hub-dir>     --name "My Hub"     --node hub
./install.sh --target <project-dir> --name "My Project" --node spoke --hub-path <hub-dir>
```

The first stands up your hub. The second **inoculates an existing or new project
folder**, turning it into a spoke. Brownfield is expected: your code stays where it
is and the harness lives alongside it.

## What you get

A factory. Your wheel can cut, verify and distribute its own harness updates to its
own spokes, and evolve along a path that suits your providers, your project types
and your way of working. It is not a copy of someone else's setup that you must
keep in sync.

## What you do NOT get, deliberately

This carries **no memory from the wheel that produced it** — no lugs, sessions,
savepoints or history. Those are that wheel's brain, not a starting point. Yours
begins empty and fills by living.

The capabilities graph ships trimmed to what actually shipped here. Your hub grows
it from your own activity. That growth is the point, not a gap to backfill.

## The shared language

Terminology and the self-improvement circles are the one part meant to stay
constant across every wheel. That shared vocabulary is what lets two wheels that
have evolved separately still read each other's capability cards and learn from
each other. Everything below it — your tools, models, advisors, scoring — is yours
to diverge.

---
Cut from a running wheel, not authored separately: this payload is the harness that
wheel uses every day. Files: {report['payload_files']}.
""")


def cmd_build(args):
    rep = build(args.out, args.dry_run)
    tag = "[dry-run] " if rep["dry_run"] else ""
    print(f"{tag}bootstrap cut — harness {rep['harness_version']} -> {rep['out']}")
    for k, v in rep["copied"].items():
        print(f"    {k:22s} {v:4d} files")
    if "capabilities" in rep:
        c = rep["capabilities"]
        print(f"    capabilities           kept {c['kept']}, dropped {c['dropped']} (files not shipped)")
    print(f"  payload files: {rep['payload_files']}")
    rc = rep["removal_candidates"]
    if rc:
        print(f"\n  {len(rc)} removal CANDIDATE(s) — reported, never acted on:")
        for c in rc[:8]:
            print(f"    {c['file']:38s} {c['signal']} [{c['confidence']}]")
        print("    A wrong removal ships a broken harness to someone who cannot debug it.")
    return 0


def cmd_candidates(args):
    for c in removal_candidates():
        print(f"{c['file']:38s} {c['signal']} [{c['confidence']}]")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cut a WAI bootstrap from the running harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", required=True)
    b.add_argument("--dry-run", action="store_true")
    sub.add_parser("candidates")
    args = ap.parse_args(argv)
    return {"build": cmd_build, "candidates": cmd_candidates}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
