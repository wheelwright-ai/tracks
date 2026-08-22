#!/usr/bin/env python3
"""complexity_gate_check.py — the Complexity Gate as a check that can FAIL.

WHAT THIS IS: a detector over RECORDED EVIDENCE, run after the fact. It reads
the current session's track (WAI-Harness/spoke/local/sessions/<id>/track.jsonl)
plus the working tree, and reports a violation when a single session has
modified >= 2 source files with no turn recording a plan/approval marker
(a `decisions` entry, a `phase` of plan, or an explicit operator approval in
`user_msg`).

WHAT THIS IS NOT: a pre-flight block, and it must never be described as one.
It cannot see unrecorded intent. It cannot attribute a working-tree edit to a
session with certainty — tracks record turns, not file writes, so attribution
here is "changed during this session's window", which can over- AND
under-count. It runs after the work, not before it. It exists because the gate
it backs — "2+ files or 6+ steps: propose a plan, wait for approval" — was
prose only: measured 2026-08-17, `grep -i plan` over pre-tool-guard.sh,
pre-write-guard.sh and pre-tool-askquestion.sh returned ZERO hits, and
session-start.sh:345 records that the gate once sat unexecuted for ten days.
A detector that can FAIL is the smallest honest step past prose. It PREVENTS
nothing; it makes the violation visible, which is all a recorded-evidence
check can honestly do.

Exit 0 = no violation detectable from recorded evidence. Exit 1 = violation.
Exit 0 is NOT proof of compliance — a session that planned but never recorded
it looks identical to one that never planned. That is the track contract's
burden, and surfacing it is the point.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys

TOOL_VERSION = "1.0.0"

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))

# Code, not data: lugs, sessions, runtime state and registry churn are records,
# not source — editing them is bookkeeping, not complexity-gate territory.
_SOURCE_EXT_RE = re.compile(
    r"\.(py|sh|bash|js|mjs|cjs|ts|tsx|jsx|go|rs|java|rb|pl)$")

# Extensionless executables are still source: the kernel entry point and the
# hooks tree carry no file extension.
_SOURCE_DIR_RE = re.compile(r"(^|/)(WAI-Harness/kernel|\.claude/hooks)/")

_APPROVAL_RE = re.compile(
    r"\b(approv\w*|go ahead|proceed|lgtm|ship it|do it|yes[,!.]?\s+do)\b", re.I)


def _sessions_dir(root):
    return os.path.join(root, "WAI-Harness", "spoke", "local", "sessions")


def _latest_session_id(root):
    sd = _sessions_dir(root)
    if not os.path.isdir(sd):
        return None
    names = sorted(d for d in os.listdir(sd) if d.startswith("session-"))
    return names[-1] if names else None


def _load_turns(root, session_id):
    """Track entries that are turns (carry user_msg/phase/decisions), in order."""
    path = os.path.join(_sessions_dir(root), session_id, "track.jsonl")
    turns = []
    if not os.path.isfile(path):
        return turns
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if any(k in entry for k in ("user_msg", "phase", "decisions", "thinking")):
                turns.append(entry)
    return turns


def has_plan_marker(turns):
    """True when any turn recorded a plan/approval marker: a `decisions` entry,
    a `phase` of plan, or an explicit operator approval in `user_msg`."""
    for t in turns:
        decisions = t.get("decisions")
        if isinstance(decisions, list) and decisions:
            return True
        if isinstance(decisions, str) and decisions.strip():
            return True
        if "plan" in str(t.get("phase", "")).lower():
            return True
        if _APPROVAL_RE.search(str(t.get("user_msg", ""))):
            return True
    return False


def _is_source_file(relpath):
    if _SOURCE_EXT_RE.search(relpath):
        return True
    return bool(_SOURCE_DIR_RE.search(relpath))


def _git(root, *args):
    try:
        out = subprocess.run(
            ["git", "-C", root] + list(args),
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.stdout if out.returncode == 0 else ""


def session_source_files(root, session_id):
    """Source files modified inside the session's window: committed during the
    window PLUS currently-uncommitted working-tree changes. Attribution is by
    clock, not causation — see the module docstring."""
    m = re.match(r"session-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})", session_id)
    files = set()
    if m:
        since = "{}-{}-{}T{}:{}:00".format(*m.groups())
        out = _git(root, "log", "--since=" + since, "--name-only",
                   "--pretty=format:", "--diff-filter=ACMR")
        files.update(x for x in out.splitlines() if x.strip())
    out = _git(root, "status", "--porcelain", "--untracked-files=no")
    for line in out.splitlines():
        if len(line) > 3:
            files.add(line[3:].strip().split(" -> ")[-1])
    return sorted(f for f in files if _is_source_file(f))


def assess(turns, source_files):
    """Pure core. Returns a violation dict or None. Separated from IO so the
    oracle tests never need a git repo or a track file."""
    if len(source_files) < 2:
        return None
    if has_plan_marker(turns):
        return None
    return {
        "violation": "complexity-gate-unplanned-multi-file",
        "source_files": source_files,
        "turns_examined": len(turns),
        "msg": ("session modified {} source files with no recorded plan/approval "
                "marker in its track".format(len(source_files))),
    }


def check(root, session_id=None):
    session_id = session_id or _latest_session_id(root)
    if not session_id:
        return None, "no session track found"
    turns = _load_turns(root, session_id)
    files = session_source_files(root, session_id)
    violation = assess(turns, files)
    return {"session": session_id, "violation": violation,
            "source_files": files, "turns_examined": len(turns)}, None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="complexity-gate detector over recorded evidence (NOT a block)")
    ap.add_argument("--root", default=_DEFAULT_ROOT)
    ap.add_argument("--session", default=None, help="session id (default: latest)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result, err = check(args.root, args.session)
    if err:
        print("complexity-gate: SKIP — {}".format(err))
        return 0
    v = result["violation"]
    if args.json:
        print(json.dumps(result, indent=2))
    elif v:
        print("complexity-gate: VIOLATION — {} (session {})".format(
            v["msg"], result["session"]))
        for f in v["source_files"][:10]:
            print("  {}".format(f))
    else:
        print("complexity-gate: OK — {} source file(s) in session {}, {}".format(
            len(result["source_files"]), result["session"],
            "plan marker recorded" if result["turns_examined"] else "below threshold"))
    return 1 if v else 0


if __name__ == "__main__":
    sys.exit(main())
