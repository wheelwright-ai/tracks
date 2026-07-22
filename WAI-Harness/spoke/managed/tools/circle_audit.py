#!/usr/bin/env python3
"""circle_audit.py — canonical circle-continuity auditor (epic-circle-audit-open-loops-and-orphans-v1).

A circle is a closed loop: initiation point -> stages -> return edge that feeds back.
Half a circle looks exactly like a whole one from the half that works, so this tool
never asks "does the component run" — it verifies (a) the ENFORCEMENT SURFACE that
initiates circles (Claude settings bindings, both scopes) against what is actually
installed and what Basher's MANIFEST says it manages, and (b) the RETURN-EDGE
EVIDENCE each declared circle must leave behind.

Three-way enforcement join (operator directive s138):
    settings-bound  x  live-installed  x  MANIFEST-managed
Any leg missing is a named finding. A live enforcement file with no manifest entry
is UNKNOWN OWNERSHIP — unknown ownership is itself a finding, never a silent state.

Circle verdicts:
    CLOSED           initiator bound + handler installed + deps present + evidence fresh
    OPEN             fires, but a dep or the return-edge artifact is missing/stale
    PHANTOM          initiator bound to a missing handler, or bound in no scope at all
    (each verdict carries config_dependency: which settings scope(s) make it fire)

Cadence contract (operator-ratified 2026-07-22): cheap tier every session start via
hygiene_run.py; deep tier demanded on version change — --write-latest stamps the
audited harness_version, and staleness (live VERSION != stamp) is reported so a
minor version bump automatically flags the audit as due.

Worktree-safe: everything resolves from --root (default cwd); no hardcoded repo
paths. Read-only except --write-latest. Stdlib only.

Usage:
    circle_audit.py [--root PATH] [--json] [--write-latest] [--quiet]
Exit: 0 clean; 1 findings (phantom/open/unknown-ownership/bound-missing); 2 cannot audit.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Declared circles — the canonical map. Each entry names the enforcement half
# (initiator event + handler basename, optional return hook) and the data half
# (deps that must exist, return-edge evidence artifacts with freshness bounds).
# evidence kinds: file | glob (required, freshness-checked when max_age_h set)
#                 optional_file | optional_glob (absence is NOT a break — the
#                 artifact only exists after the circle's trigger condition)
# ---------------------------------------------------------------------------
CIRCLES = [
    {
        "id": "track-per-turn",
        "name": "Per-turn track ledger",
        "initiator": ("UserPromptSubmit", "user-prompt-submit.sh"),
        "return_hook": ("Stop", "stop-track-flush.sh"),
        "deps": [
            ".claude/hooks/flush_buffer.py",
            ".claude/hooks/synthesize_turn.py",
            ".claude/hooks/validate_track_buffer.py",
            "WAI-Harness/spoke/managed/tools/worktree_guard.py",
        ],
        "evidence": [
            ("glob", "WAI-Harness/spoke/local/sessions/*/track.jsonl", 96),
            ("file", "WAI-Harness/spoke/local/runtime/capture-fired.log", 96),
        ],
    },
    {
        "id": "savepoint-floor",
        "name": "Savepoint existence floor (auto-eject)",
        "initiator": ("Stop", "stop-savepoint-guard.sh"),
        "deps": [
            "WAI-Harness/spoke/managed/tools/auto_eject_savepoint.py",
            "WAI-Harness/spoke/managed/tools/converge_closeout.py",
            "WAI-Harness/spoke/managed/tools/worktree_guard.py",
        ],
        "evidence": [("optional_glob", "WAI-Harness/spoke/local/savepoints/**/*.json", None)],
    },
    {
        "id": "compact-resume",
        "name": "Compaction context round-trip",
        "initiator": ("PreCompact", "pre-compact.sh"),
        "return_hook": ("SessionStart", "compact-resume-inject.sh"),
        "deps": ["WAI-Harness/spoke/managed/tools/auto_eject_savepoint.py"],
        "evidence": [("optional_file", "WAI-Harness/spoke/local/runtime/compact-resume.json", None)],
    },
    {
        "id": "lane-csrp",
        "name": "Concurrent-session lanes (register at start, release at end)",
        "initiator": ("SessionStart", "session-start.sh"),
        "return_hook": ("SessionEnd", "session-end-lane.sh"),
        "deps": ["WAI-Harness/spoke/managed/tools/worktree_guard.py"],
        "evidence": [("optional_glob", "WAI-Harness/spoke/local/runtime/lanes/*", None)],
    },
    {
        "id": "hygiene-innate",
        "name": "Innate hygiene (session-start writes, next entry surfaces)",
        "initiator": ("SessionStart", "session-start.sh"),
        "deps": ["WAI-Harness/spoke/managed/tools/hygiene_run.py"],
        "evidence": [("file", "WAI-Harness/spoke/local/maintenance/hygiene-latest.json", 336)],
    },
    {
        # s138 rebuild: formerly "activity-lug-sync" (3-stage PHANTOM — unbound, and both
        # consumers never existed on v4). Rebuilt as single-purpose syntax-check feedback;
        # if the activity/lug-sync circle returns, re-declare it here WITH its consumers.
        "id": "edit-feedback",
        "name": "Immediate Python syntax feedback on Write/Edit",
        "initiator": ("PostToolUse", "post-tool-use.sh"),
        "deps": [],
        "evidence": [],
    },
    {
        "id": "test-gate",
        "name": "Edit-scoped managed test gate",
        "initiator": ("Stop", "stop-test-runner.sh"),
        "deps": ["WAI-Harness/spoke/managed/tests", "WAI-Harness/spoke/managed/MANIFEST.json"],
        "evidence": [],
    },
    {
        "id": "worktree-hygiene",
        "name": "Abandoned-worktree detection at stop",
        "initiator": ("Stop", "stop-worktree-hygiene.sh"),
        "deps": [],
        "evidence": [("optional_file", ".claude/hooks/worktree-hygiene.log", None)],
    },
]

# Handlers legitimately present in .claude/hooks without their own settings binding:
# sourced or exec'd by a bound handler. Anything else unbound is an orphan.
INDIRECT_HANDLERS = {
    "harness_mode.sh": "sourced by stop-track-flush.sh / stop-savepoint-guard.sh / others",
    "flush_buffer.py": "invoked by stop-track-flush.sh",
    "synthesize_turn.py": "invoked by stop-track-flush.sh",
    "validate_track_buffer.py": "invoked by flush path",
    "wakeup-canonical.sh": "invoked by session-start.sh",
}
IGNORE_HOOK_DIR_ENTRIES = {"__pycache__"}
CRUFT_SUFFIXES = (".log", ".bak")


def _load_json(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


def _md5(p):
    try:
        return hashlib.md5(Path(p).read_bytes()).hexdigest()
    except Exception:
        return None


def _fresh(path, max_age_h):
    if max_age_h is None:
        return True
    try:
        return (time.time() - os.path.getmtime(path)) <= max_age_h * 3600
    except OSError:
        return False


def _handler_from_command(cmd, root):
    """Resolve the handler script a settings hook command actually targets."""
    m = re.search(r'\$\{CLAUDE_PROJECT_DIR\}(/[^"]+)', cmd)
    if m:
        return str(Path(root) / m.group(1).lstrip("/")), True  # (path, silent_wrapper likely)
    m = re.search(r'(/[^\s";]+\.(?:sh|py|cjs|js))', cmd)
    if m:
        return m.group(1), False
    return None, False


def collect_bindings(root):
    """Parse both settings scopes into a flat binding list."""
    scopes = {
        "global": Path.home() / ".claude" / "settings.json",
        "project": Path(root) / ".claude" / "settings.json",
    }
    bindings = []
    for scope, sp in scopes.items():
        cfg = _load_json(sp)
        if not cfg:
            continue
        for event, matchers in (cfg.get("hooks") or {}).items():
            for m in matchers:
                for h in m.get("hooks", []):
                    cmd = h.get("command", "")
                    handler, wrapped = _handler_from_command(cmd, root)
                    silent = wrapped or ("; true" in cmd or "|| true" in cmd)
                    bindings.append({
                        "scope": scope, "event": event,
                        "matcher": m.get("matcher", ""),
                        "handler": handler, "command": cmd,
                        "installed": bool(handler and os.path.exists(handler)),
                        "silent_on_missing": silent,
                    })
    return bindings


def enforcement_findings(root, bindings):
    """Three-way join: settings-bound x live-installed x MANIFEST-managed."""
    findings = []
    # 1. bound -> missing handler
    for b in bindings:
        if b["handler"] and not b["installed"]:
            findings.append({
                "kind": "BOUND_MISSING",
                "detail": f"{b['scope']} {b['event']}:{b['matcher']} -> {b['handler']} does not exist"
                          + (" (fails SILENTLY: wrapper returns true)" if b["silent_on_missing"] else ""),
            })
    # 2. duplicate bindings (same event+handler bound N times across scopes/matchers)
    seen = {}
    for b in bindings:
        if not b["handler"]:
            continue
        key = (b["event"], os.path.basename(b["handler"]))
        seen.setdefault(key, []).append(f"{b['scope']}:{b['matcher']}")
    for (event, hname), where in seen.items():
        if len(where) > 1:
            findings.append({
                "kind": "MULTI_BOUND",
                "detail": f"{event} -> {hname} bound {len(where)}x ({', '.join(where)}) — dedup behavior is harness-defined, not ours",
            })
    # 3. installed-but-unbound project handlers
    hooks_dir = Path(root) / ".claude" / "hooks"
    bound_names = {os.path.basename(b["handler"]) for b in bindings if b["handler"]}
    manifest = _load_json(Path(root) / "WAI-Harness" / "spoke" / "managed" / "MANIFEST.json") or {}
    mfiles = manifest.get("files", {})
    if hooks_dir.is_dir():
        for f in sorted(hooks_dir.iterdir()):
            if f.name in IGNORE_HOOK_DIR_ENTRIES:
                continue
            if f.name.endswith(CRUFT_SUFFIXES):
                findings.append({"kind": "CRUFT_IN_HOOKS", "detail": f".claude/hooks/{f.name}"})
                continue
            if f.name not in bound_names and f.name not in INDIRECT_HANDLERS:
                findings.append({"kind": "INSTALLED_UNBOUND", "detail": f".claude/hooks/{f.name} — installed, bound by nothing"})
            rel = f".claude/hooks/{f.name}"
            entry = mfiles.get(rel)
            if entry is None:
                findings.append({"kind": "UNKNOWN_OWNERSHIP", "detail": f"{rel} live but absent from MANIFEST — no Basher management record"})
            elif _md5(f) != entry.get("md5"):
                findings.append({"kind": "MANAGED_DRIFT", "detail": f"{rel} md5 differs from MANIFEST (manifest v{entry.get('version')})"})
    # 3b. ownership join for the non-hook enforcement dirs (agents/commands/workflows):
    # a live file with no manifest entry is UNKNOWN OWNERSHIP; md5 mismatch is DRIFT.
    for sub in ("agents", "commands", "workflows"):
        d = Path(root) / ".claude" / sub
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if not f.is_file() or f.name in IGNORE_HOOK_DIR_ENTRIES:
                continue
            rel = f".claude/{sub}/{f.name}"
            entry = mfiles.get(rel)
            if entry is None:
                findings.append({"kind": "UNKNOWN_OWNERSHIP", "detail": f"{rel} live but absent from MANIFEST — no Basher management record"})
            elif _md5(f) != entry.get("md5"):
                findings.append({"kind": "MANAGED_DRIFT", "detail": f"{rel} md5 differs from MANIFEST (manifest v{entry.get('version')})"})
    # settings.json itself
    sj = Path(root) / ".claude" / "settings.json"
    entry = mfiles.get(".claude/settings.json")
    if sj.exists() and entry and _md5(sj) != entry.get("md5"):
        findings.append({"kind": "MANAGED_DRIFT", "detail": ".claude/settings.json md5 differs from MANIFEST — local extensions are indistinguishable from tamper (no overlay model)"})
    # 4. manifest-declared enforcement never installed
    for rel, entry in mfiles.items():
        if rel.startswith(".claude/") and not (Path(root) / rel).exists():
            findings.append({"kind": "DECLARED_NOT_INSTALLED", "detail": f"{rel} in MANIFEST (v{entry.get('version')}) but not on disk"})
    # 5. global handler dir orphans
    ghooks = Path.home() / ".claude" / "hooks"
    if ghooks.is_dir():
        for f in sorted(ghooks.rglob("*")):
            # _retired-by-* dirs are the sanctioned retirement convention (recorded
            # dispositions, restorable) — their contents are settled, not findings.
            if any(part.startswith("_retired") for part in f.relative_to(ghooks).parts):
                continue
            if f.is_file() and not f.name.endswith(CRUFT_SUFFIXES) and f.suffix != ".md":
                if f.name not in bound_names:
                    findings.append({"kind": "GLOBAL_UNBOUND", "detail": f"~/.claude/hooks/{f.relative_to(ghooks)} — bound by nothing in either scope"})
    return findings


def apply_exemptions(root, findings):
    """Recorded dispositions, not silence: an exemptions file downgrades matching
    findings to exempt=true (still reported, excluded from the hard count). Each
    entry: {kind, pattern (fnmatch vs the finding detail), reason, recorded_by, date}.
    An exemption with no reason is invalid and ignored — a disposition must say why."""
    import fnmatch
    exf = Path(root) / "WAI-Harness" / "spoke" / "local" / "maintenance" / "circle-audit-exemptions.json"
    entries = (_load_json(exf) or {}).get("exemptions", [])
    for f in findings:
        for e in entries:
            if not e.get("reason"):
                continue
            if e.get("kind") and e["kind"] != f["kind"]:
                continue
            if fnmatch.fnmatch(f["detail"], e.get("pattern", "*")) or e.get("pattern", "") in f["detail"]:
                f["exempt"] = True
                f["exempt_reason"] = e["reason"]
                break
    return findings


def audit_circles(root, bindings):
    results = []
    by_event = {}
    for b in bindings:
        if b["handler"]:
            by_event.setdefault((b["event"], os.path.basename(b["handler"])), []).append(b)
    for c in CIRCLES:
        event, hname = c["initiator"]
        binds = by_event.get((event, hname), [])
        scopes = sorted({b["scope"] for b in binds})
        missing_deps = [d for d in c.get("deps", []) if not (Path(root) / d).exists()]
        breaks, verdict = [], "CLOSED"
        if not binds:
            verdict = "PHANTOM"
            breaks.append(f"initiator {event}->{hname} bound in NO scope")
        elif not any(b["installed"] for b in binds):
            verdict = "PHANTOM"
            breaks.append(f"initiator {event}->{hname} bound but handler missing (silent)")
        rh = c.get("return_hook")
        if rh and verdict == "CLOSED":
            rbinds = by_event.get((rh[0], rh[1]), [])
            if not rbinds or not any(b["installed"] for b in rbinds):
                verdict = "OPEN"
                breaks.append(f"return hook {rh[0]}->{rh[1]} not bound+installed")
        if verdict == "CLOSED" and missing_deps:
            verdict = "OPEN"
            breaks.append("missing deps: " + ", ".join(missing_deps))
        if verdict == "CLOSED":
            for ev in c.get("evidence", []):
                kind, pat, age = ev[0], ev[1], (ev[2] if len(ev) > 2 else None)
                optional = kind.startswith("optional_")
                hits = list(Path(root).glob(pat)) if "glob" in kind else ([Path(root) / pat] if (Path(root) / pat).exists() else [])
                fresh = [h for h in hits if _fresh(h, age)]
                if not fresh and not optional:
                    verdict = "OPEN"
                    breaks.append(f"return-edge evidence missing/stale: {pat}")
        results.append({
            "id": c["id"], "name": c["name"], "verdict": verdict,
            "config_dependency": scopes or ["<none>"],
            "config_dependent": len(scopes) == 1,
            "breaks": breaks, "missing_deps": missing_deps,
        })
    return results


def unmerged_lane_findings(root):
    """Operator ruling (2026-07-22): an unmerged session branch IS an incomplete
    workflow — work was produced and never returned to main (the git-lifecycle
    circle open at its return edge). Detection triggers the obligation: run a
    TRACK REVIEW of that lane to divine what was in flight, what completed, and
    what still should. Heuristic: session* branch not merged to main, tip older
    than 1h (a live lane mid-work is not a finding), no live lane claiming it."""
    findings = []
    try:
        out = subprocess.run(
            ["git", "-C", root, "for-each-ref", "--format=%(refname:short) %(committerdate:unix)",
             "refs/heads/session*", "refs/heads/*/session*"],
            capture_output=True, text=True, timeout=10).stdout
        main_sha = subprocess.run(["git", "-C", root, "rev-parse", "main"],
                                  capture_output=True, text=True, timeout=10).stdout.strip()
        if not main_sha:
            return findings
        now = time.time()
        for ln in out.splitlines():
            parts = ln.rsplit(" ", 1)
            if len(parts) != 2:
                continue
            branch, ts = parts[0], int(parts[1])
            merged = subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", branch, "main"],
                                    capture_output=True, timeout=10).returncode == 0
            if merged:
                continue
            age_h = (now - ts) / 3600
            if age_h < 1:
                continue  # live work in progress, not a finding
            findings.append({
                "kind": "UNMERGED_LANE",
                "detail": f"branch {branch} unmerged to main, tip {age_h:.1f}h old — incomplete workflow: "
                          f"run a track review of that lane (what was in flight, what completed, what still should), "
                          f"then converge or record the keep-open decision",
            })
    except Exception:
        pass  # git unavailable — reported implicitly by absence, never a crash
    return findings


def hub_checks(root):
    """The hub child has its own scope and mission — audit its instruments."""
    hub = Path(root) / "WAI-Harness" / "hub"
    out = {"present": hub.is_dir()}
    if not hub.is_dir():
        return out
    man = _load_json(hub / "managed" / "MANIFEST.json") or {}
    payload = [k for k in man.get("files", {}) if k.startswith(".claude/")]
    out["managed_claude_payload"] = len(payload)
    out["live_claude_dir"] = (hub / ".claude").is_dir()
    out["declared_only_enforcement"] = bool(payload) and not out["live_claude_dir"]
    for name, rel in [("contract_validate", "local/scripts/contract_validate.py"),
                      ("verify_foundation", "local/scripts/verify_foundation.py"),
                      ("conductor", "local/scripts/conductor.py")]:
        out[name] = (hub / rel).exists()
    # is contract_validate on any live schedule?
    try:
        cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5).stdout
        live = [ln for ln in cron.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        out["contract_validate_scheduled"] = any("contract_validate" in ln or "conductor" in ln for ln in live)
    except Exception:
        out["contract_validate_scheduled"] = None  # unknown, reported as such
    return out


def version_staleness(root):
    vfile = Path(root) / "WAI-Harness" / "VERSION"
    live = vfile.read_text().strip() if vfile.exists() else None
    latest = _load_json(Path(root) / "WAI-Harness" / "spoke" / "local" / "maintenance" / "circle-audit-latest.json")
    stamped = latest.get("harness_version") if latest else None
    return {"live_version": live, "last_audited_version": stamped,
            "stale": bool(live and stamped and live != stamped) or (live is not None and stamped is None)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Circle-continuity auditor (enforcement joins + closure evidence).")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--write-latest", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    root = str(Path(args.root).resolve())
    if not (Path(root) / ".claude").is_dir() and not (Path(root) / "WAI-Harness").is_dir():
        print(f"circle_audit: {root} has neither .claude/ nor WAI-Harness/ — cannot audit", file=sys.stderr)
        return 2

    bindings = collect_bindings(root)
    findings = apply_exemptions(root, enforcement_findings(root, bindings) + unmerged_lane_findings(root))
    circles = audit_circles(root, bindings)
    hub = hub_checks(root)
    ver = version_staleness(root)

    n_phantom = sum(1 for c in circles if c["verdict"] == "PHANTOM")
    n_open = sum(1 for c in circles if c["verdict"] == "OPEN")
    n_closed = sum(1 for c in circles if c["verdict"] == "CLOSED")
    hard = [f for f in findings if not f.get("exempt")
            and f["kind"] in ("BOUND_MISSING", "UNKNOWN_OWNERSHIP", "MANAGED_DRIFT", "DECLARED_NOT_INSTALLED", "INSTALLED_UNBOUND", "UNMERGED_LANE")]
    verdict = "BROKEN" if (n_phantom or n_open or hard) else "CLEAN"

    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root": root, "harness_version": ver["live_version"], "verdict": verdict,
        "summary": {"circles_closed": n_closed, "circles_open": n_open, "circles_phantom": n_phantom,
                    "enforcement_findings": len(findings), "hard_findings": len(hard)},
        "version_staleness": ver, "circles": circles,
        "enforcement_findings": findings, "hub": hub,
        "bindings_count": len(bindings),
    }
    if args.write_latest:
        outp = Path(root) / "WAI-Harness" / "spoke" / "local" / "maintenance" / "circle-audit-latest.json"
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(report, indent=2))
        report["_written"] = str(outp)

    if args.json:
        print(json.dumps(report, indent=2))
    elif not args.quiet:
        print(f"circle_audit {report['ts']}  verdict={verdict}  "
              f"closed={n_closed} open={n_open} phantom={n_phantom}  findings={len(findings)}")
        for c in circles:
            flag = "" if c["verdict"] == "CLOSED" else "  <-- " + "; ".join(c["breaks"])
            dep = " [single-scope: " + c["config_dependency"][0] + "]" if c["config_dependent"] else ""
            print(f"  [{c['verdict']:7}] {c['id']}{dep}{flag}")
        for f in findings:
            tag = "~ EXEMPT" if f.get("exempt") else "!"
            print(f"  {tag} {f['kind']}: {f['detail']}" + (f"  [{f['exempt_reason']}]" if f.get("exempt") else ""))
        if hub.get("present"):
            sched = hub.get("contract_validate_scheduled")
            print(f"  hub: claude_payload={hub.get('managed_claude_payload')} declared_only={hub.get('declared_only_enforcement')} "
                  f"contract_validate={'present' if hub.get('contract_validate') else 'MISSING'} "
                  f"scheduled={'UNKNOWN' if sched is None else sched}")
        if ver["stale"]:
            print(f"  ! AUDIT STALE: live version {ver['live_version']} != last audited {ver['last_audited_version']} — deep audit due")
    return 0 if verdict == "CLEAN" else 1


if __name__ == "__main__":
    sys.exit(main())
