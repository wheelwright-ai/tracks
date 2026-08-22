#!/usr/bin/env python3
"""recovery_scan.py — fleet-wide Claude session-store recovery scanner.

Crash/restart strands user-driven Claude Code sessions. Raw git-dirtiness is a
false signal (mostly harness state churn: WAI-State.json, autoeject savepoints,
session tracks, receipts). The WAI-native unit of interrupted work is the
UNCLAIMED SAVEPOINT (sp-session-*.json / *-autoeject.json written by the
stop/pre-compact safety net but never committed or reunified to main) plus
genuinely ORPHANED SOURCE work (dirty tree minus a state-churn allowlist).

Walks every directory under ~/.claude/projects/ (one dir per distinct working
directory Claude Code has ever been run in), decodes it back to a real
filesystem path, and for the NEWEST transcript in that directory:
  - classifies the transcript itself: closed / non-user / api-error-interrupted
    / interrupted (has real work, no closeout signal)
  - if the path still exists as a git repo, classifies its working-tree state:
    unclaimed savepoints / orphaned source / state-churn-only
  - emits a combined verdict + a ready-to-paste `cd <path> && claude -r <uuid>`

Age is a DISPLAY dimension only ("cold context" label past --cold-days) — it
NEVER suppresses a flagged session. A stale-but-orphaned session is exactly the
kind of thing this scanner exists to surface.

Path decoding: Claude Code names a project dir by replacing every '/', '.' and
'_' in the absolute cwd with '-' (see encode_path below). That's lossy — a
literal '-' in a real directory name is indistinguishable from an encoded
separator. decode_project_dir() reverses it with a greedy longest-match probe
against the real filesystem (os.path.isdir), also trying '.' / '_' variants at
segment boundaries that came from a collapsed double-separator (e.g. the
".worktrees" in ".../basher/.worktrees/s260617-162744" round-trips through
"--worktrees-s260617-162744"). Each segment match is confirmed on disk as it's
found, so a decode is "resolved" only when every segment — not just the
overall shape — was verified to actually exist.

Usage:
  recovery_scan.py [--claude-projects-dir DIR] [--cold-days N] [--spoke PATH] [--json]
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone

CLAUDE_PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
COLD_CONTEXT_DAYS = 7

SAVEPOINT_RE = re.compile(r"(^|/)sp-session-.*\.json$")

# System-injected wrapper tags that mean "not a human-typed prompt" even though
# they land in a type=="user" transcript entry.
_AUTOMATION_PREFIXES = (
    "<task-notification", "<system-reminder", "<user-prompt-submit-hook",
    "<local-command-stdout", "<command-", "<local-command-stderr",
)

CLOSE_PHRASES = (
    "clear to exit", "cleared to exit", "clear to close", "safe to exit",
    "safe-to-exit", "session closed", "session is closed", "closeout complete",
    "closeout ceremony complete", "migration complete", "migration-complete",
    "you are clear to exit", "definitive exit",
)

# Relative-path prefixes/exacts treated as harness state-churn, never
# "orphaned source" (they're the byproduct of the harness itself running, not
# user-directed work). Savepoint files are pulled into their own bucket BEFORE
# this check even though they physically sit under an allowlisted prefix.
_STATE_CHURN_EXACT = {
    "WAI-Harness/spoke/local/WAI-State.json",
    "WAI-Spoke/WAI-State.json",
    ".claude/settings.json",
}
_STATE_CHURN_PREFIXES = (
    "WAI-Harness/spoke/local/initiatives/savepoints/",
    "WAI-Harness/spoke/local/savepoints/",
    "WAI-Spoke/initiatives/savepoints/",
    "WAI-Spoke/savepoints/",
    "WAI-Harness/spoke/local/sessions/",
    "WAI-Spoke/sessions/",
    "WAI-Harness/spoke/local/maintenance/receipts/",
    "WAI-Spoke/maintenance/receipts/",
    ".claude/hooks/",
    ".claude/commands/",
)
_ADVISOR_LOGS_RE = re.compile(r"(^|/)advisors/[^/]+/logs(/|$)")


# ── path decoding ─────────────────────────────────────────────────────────────

def encode_path(abspath: str) -> str:
    """Claude Code's project-dir encoding: '/', '.', '_' -> '-'."""
    return "".join("-" if ch in "/._" else ch for ch in abspath)


def decode_project_dir(name: str):
    """Reverse encode_path() via a greedy longest-match filesystem probe.

    Returns (path, resolved) where resolved is True iff EVERY segment of the
    path was confirmed on disk via os.path.isdir during the probe. False with
    a non-None path means the probe fell back to a raw dash-join guess for
    the tail once a segment failed to resolve — normally a leaf that has since
    been removed (e.g. a session worktree already merged + reaped). Note:
    re-encoding the returned path always round-trips to `name` regardless of
    `resolved` (encode_path is many-to-one), so that check alone is NOT a
    confidence signal — resolved is tracked directly, per-segment, instead.

    A collapsed double-separator (two of '/', '.', '_' in a row, e.g. the '/'
    then '.' in ".../basher/.worktrees/...") produces one empty token when
    the name is split on '-'. The extra char could belong to either side of
    that boundary — leading onto the next segment (".worktrees") or trailing
    onto the previous one (a real dir ending in '_' immediately followed by
    '/', e.g. a tempdir like "rs-decode-988zwm1_"). Both directions are tried.

    A real dir name can also mix literal '-' with an encoded '.'/'_' in the
    SAME flat component (e.g. "space_rust", or a tempdir prefix like
    "rs-decode-ap_bavn3" where only one of the three dashes is really an
    underscore) — a single find-and-replace across the whole span would wrongly
    flip the literal dashes too. Each dash position is tried independently
    instead, bounded to short spans so the combinatorics stay tiny.
    """
    if not name.startswith("-"):
        return None, False
    tokens = name[1:].split("-")
    path = ""
    i, n = 0, len(tokens)
    resolved = True
    while i < n:
        matched = False
        for j in range(n, i, -1):
            seg = "-".join(tokens[i:j])
            candidates = [seg]
            if tokens[i] == "" and seg:
                # a collapsed double-separator: the real char was '.' or '_',
                # not a literal leading '-'.
                candidates = ["." + seg[1:], "_" + seg[1:], seg]
            dash_positions = [k for k, ch in enumerate(seg) if ch == "-"]
            if seg and 0 < len(dash_positions) <= 6:
                for combo in itertools.product("-_.", repeat=len(dash_positions)):
                    if all(ch == "-" for ch in combo):
                        continue  # already tried as the literal seg above
                    chars = list(seg)
                    for pos, ch in zip(dash_positions, combo):
                        chars[pos] = ch
                    candidates.append("".join(chars))
            advance_to = j
            for cand_seg in candidates:
                cand_path = path + "/" + cand_seg
                if os.path.isdir(cand_path):
                    path = cand_path
                    matched = True
                    break
            if not matched and seg and j < n and tokens[j] == "":
                # the boundary char could instead trail onto THIS segment
                # (consuming the empty marker token so the next segment
                # starts clean).
                for cand_seg in (seg + ".", seg + "_"):
                    cand_path = path + "/" + cand_seg
                    if os.path.isdir(cand_path):
                        path = cand_path
                        advance_to = j + 1
                        matched = True
                        break
            if matched:
                i = advance_to
                break
        if not matched:
            # No existing dir for any join starting here — assume the rest of
            # the tokens name a single (possibly now-missing) final component.
            path = path + "/" + "-".join(tokens[i:])
            resolved = False
            i = n
    return path or None, resolved


# ── git helpers ───────────────────────────────────────────────────────────────

def _git(cwd, *args, timeout=15):
    try:
        r = subprocess.run(["git", "-C", cwd, *args],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return 1, "", str(e)


def _git_status_porcelain(cwd, timeout=15):
    # --untracked-files=all: without it, git collapses an entirely-untracked
    # directory into a single "?? dir/" line, which would hide a savepoint
    # file nested inside an untracked dir behind an undifferentiated
    # directory entry instead of surfacing it as its own recovery unit.
    return _git(cwd, "status", "--porcelain", "--untracked-files=all", timeout=timeout)


def is_git_repo(path: str) -> bool:
    rc, out, _ = _git(path, "rev-parse", "--is-inside-work-tree")
    return rc == 0 and out.strip() == "true"


def current_branch(path: str):
    rc, out, _ = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    return out.strip() if rc == 0 else None


def _main_ref(path: str):
    for ref in ("main", "master"):
        rc, _, _ = _git(path, "rev-parse", "--verify", "--quiet", ref)
        if rc == 0:
            return ref
    return None


def is_branch_merged(path: str, branch: str, main_ref: str) -> bool:
    rc, out, _ = _git(path, "branch", "--merged", main_ref)
    if rc != 0:
        return False
    names = {ln.strip().lstrip("* ").strip() for ln in out.splitlines()}
    return branch in names


def _porcelain_paths(path: str):
    rc, out, _ = _git_status_porcelain(path)
    if rc != 0:
        return []
    rels = []
    for line in out.splitlines():
        if not line.strip():
            continue
        rest = line[3:] if len(line) > 3 else line.lstrip("? MADRCU").strip()
        if " -> " in rest:  # rename: "old -> new"
            rest = rest.split(" -> ", 1)[1]
        rels.append(rest.strip().strip('"'))
    return rels


def _unmerged_commit_files(path: str, main_ref: str):
    rc, out, _ = _git(path, "diff", "--name-only", f"{main_ref}...HEAD")
    if rc != 0:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def is_state_churn(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    if rel in _STATE_CHURN_EXACT:
        return True
    if any(rel.startswith(p) for p in _STATE_CHURN_PREFIXES):
        return True
    if _ADVISOR_LOGS_RE.search(rel):
        return True
    return False


def classify_git_tree(path: str):
    """Split a repo's changed files into unclaimed-savepoint / orphaned-source /
    state-churn buckets. Includes commits unique to a non-main branch that
    hasn't been reunified yet (stuck-on-a-branch work is just as orphaned as
    uncommitted work)."""
    if not is_git_repo(path):
        return None
    branch = current_branch(path)
    buckets = {"unclaimed_savepoints": [], "orphaned_source": [], "state_churn": []}
    seen = set()

    def add(rel):
        rel = rel.strip()
        if not rel or rel in seen:
            return
        seen.add(rel)
        if SAVEPOINT_RE.search(rel):
            buckets["unclaimed_savepoints"].append(rel)
        elif is_state_churn(rel):
            buckets["state_churn"].append(rel)
        else:
            buckets["orphaned_source"].append(rel)

    for rel in _porcelain_paths(path):
        add(rel)

    main_ref = _main_ref(path)
    merged = False
    if branch and main_ref and branch != main_ref:
        merged = is_branch_merged(path, branch, main_ref)
        if not merged:
            for rel in _unmerged_commit_files(path, main_ref):
                add(rel)

    return {"branch": branch, "merged_to_main": merged, **buckets}


# ── transcript classification ────────────────────────────────────────────────

def _text_blocks(content):
    if isinstance(content, str):
        return [content]
    out = []
    if isinstance(content, list):
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                out.append(b["text"])
    return out


def _is_real_user_text(text: str) -> bool:
    t = text.lstrip()
    return bool(t) and not t.startswith(_AUTOMATION_PREFIXES)


def newest_transcript(project_dir: str):
    if not os.path.isdir(project_dir):
        return None
    best, best_m = None, -1.0
    for f in os.listdir(project_dir):
        if not f.endswith(".jsonl"):
            continue
        full = os.path.join(project_dir, f)
        try:
            m = os.stat(full).st_mtime
        except OSError:
            continue
        if m > best_m:
            best, best_m = full, m
    return best


def classify_transcript(transcript_path: str):
    """One forward pass: last real external user turn, last assistant text,
    whether any real user turn exists at all, and the very last entry (for the
    api-error-interrupted signal)."""
    has_real_user = False
    last_user_ts = last_user_text = None
    last_assistant_ts = last_assistant_text = None
    last_ts = None
    last_is_api_error = False

    try:
        with open(transcript_path, errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                ts = o.get("timestamp")
                if ts:
                    last_ts = ts
                otype = o.get("type")
                msg = o.get("message") if isinstance(o.get("message"), dict) else {}
                if otype == "user" and "toolUseResult" not in o:
                    for t in _text_blocks(msg.get("content")):
                        if _is_real_user_text(t):
                            has_real_user = True
                            last_user_ts, last_user_text = ts, t
                            last_is_api_error = False
                elif otype == "assistant":
                    texts = _text_blocks(msg.get("content"))
                    if texts:
                        last_assistant_ts, last_assistant_text = ts, texts[-1]
                    last_is_api_error = bool(o.get("isApiErrorMessage"))
    except FileNotFoundError:
        pass

    prose = " ".join(t for t in (last_assistant_text, last_user_text) if t).lower()
    closed_signal = any(p in prose for p in CLOSE_PHRASES)

    if not has_real_user:
        base = "NON-USER"
    elif last_is_api_error:
        base = "API-ERROR-INTERRUPTED"
    elif closed_signal:
        base = "CLOSED"
    else:
        base = "INTERRUPTED"

    return {
        "base": base,
        "has_real_user": has_real_user,
        "last_turn": last_ts,
        "last_user_preview": (last_user_text or "")[:200],
        "last_assistant_preview": (last_assistant_text or "")[:200],
    }


# ── session scan ──────────────────────────────────────────────────────────────

def _age_days(iso_ts):
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
    except ValueError:
        return None


def _verdict(transcript, tree):
    base = transcript["base"]
    has_orphaned = bool(tree and tree["orphaned_source"])
    has_unclaimed = bool(tree and tree["unclaimed_savepoints"])
    if base == "API-ERROR-INTERRUPTED":
        primary = base
    elif has_orphaned:
        primary = "ORPHANED-SOURCE"
    else:
        primary = base
    if has_unclaimed:
        return f"{primary}-with-unclaimed-savepoint", has_orphaned, has_unclaimed
    return primary, has_orphaned, has_unclaimed


def scan_session(project_dir_name: str, projects_root: str, cold_days: int):
    project_dir = os.path.join(projects_root, project_dir_name)
    path, resolved = decode_project_dir(project_dir_name)
    path_exists = bool(path and os.path.isdir(path))

    transcript = newest_transcript(project_dir)
    if not transcript:
        return None
    session_uuid = os.path.basename(transcript)[:-len(".jsonl")]

    t = classify_transcript(transcript)
    tree = classify_git_tree(path) if path_exists else None
    verdict, has_orphaned, has_unclaimed = _verdict(t, tree)

    age_d = _age_days(t["last_turn"])
    cold = age_d is not None and age_d > cold_days

    recovery_worthy = verdict not in ("NON-USER", "CLOSED")

    resume_cmd = None
    if path_exists:
        resume_cmd = f"cd {shlex.quote(path)} && claude -r {session_uuid}"

    return {
        "project_dir": project_dir_name,
        "path": path,
        "path_exists": path_exists,
        "path_fully_resolved": resolved,
        "session_uuid": session_uuid,
        "verdict": verdict,
        "recovery_worthy": recovery_worthy,
        "last_turn": t["last_turn"],
        "cold_context": cold,
        "age_days": round(age_d, 1) if age_d is not None else None,
        "last_user_preview": t["last_user_preview"],
        "last_assistant_preview": t["last_assistant_preview"],
        "tree": tree,
        "resume_cmd": resume_cmd,
    }


def scan_fleet(projects_root=CLAUDE_PROJECTS_DIR, cold_days=COLD_CONTEXT_DAYS, spoke_filter=None):
    if not os.path.isdir(projects_root):
        return {"generated_at": datetime.now(timezone.utc).isoformat(),
                "error": f"no such dir: {projects_root}", "sessions": []}
    sessions = []
    for name in sorted(os.listdir(projects_root)):
        full = os.path.join(projects_root, name)
        if not os.path.isdir(full):
            continue
        rec = scan_session(name, projects_root, cold_days)
        if rec is None:
            continue
        if spoke_filter and not (rec["path"] and os.path.abspath(rec["path"]).startswith(
                os.path.abspath(spoke_filter))):
            continue
        sessions.append(rec)

    sessions.sort(key=lambda r: (not r["recovery_worthy"], r["last_turn"] or ""), reverse=True)
    counts = {}
    for r in sessions:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cold_context_days": cold_days,
        "count": len(sessions),
        "recovery_worthy_count": sum(1 for r in sessions if r["recovery_worthy"]),
        "by_verdict": counts,
        "sessions": sessions,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def _print_human(report):
    if "error" in report:
        print(f"[recovery-scan] ERROR: {report['error']}")
        return
    print(f"[recovery-scan] {report['count']} session(s), "
          f"{report['recovery_worthy_count']} recovery-worthy "
          f"({report['generated_at']})")
    for v, n in sorted(report["by_verdict"].items(), key=lambda kv: -kv[1]):
        print(f"  {v}: {n}")
    print()
    for r in report["sessions"]:
        if not r["recovery_worthy"]:
            continue
        cold = " [cold context]" if r["cold_context"] else ""
        print(f"• {r['verdict']}{cold}  {r['project_dir']}")
        print(f"    path   : {r['path'] or '(unresolved)'}")
        print(f"    uuid   : {r['session_uuid']}")
        print(f"    last   : {r['last_turn']}  ({r['age_days']}d ago)"
              if r["age_days"] is not None else "    last   : unknown")
        if r["tree"]:
            t = r["tree"]
            if t["unclaimed_savepoints"]:
                print(f"    unclaimed savepoints: {', '.join(t['unclaimed_savepoints'])}")
            if t["orphaned_source"]:
                print(f"    orphaned source     : {', '.join(t['orphaned_source'][:8])}"
                      + (" ..." if len(t["orphaned_source"]) > 8 else ""))
        if r["resume_cmd"]:
            print(f"    resume : {r['resume_cmd']}")
        print()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--claude-projects-dir", default=CLAUDE_PROJECTS_DIR,
                    help="Claude Code session-store root (default: ~/.claude/projects)")
    ap.add_argument("--cold-days", type=int, default=COLD_CONTEXT_DAYS,
                    help="age threshold for the 'cold context' DISPLAY label (never a filter)")
    ap.add_argument("--spoke", default=None,
                    help="restrict output to sessions resolving under this path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    report = scan_fleet(args.claude_projects_dir, args.cold_days, args.spoke)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_human(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
