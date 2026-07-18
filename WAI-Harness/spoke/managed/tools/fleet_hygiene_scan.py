#!/usr/bin/env python3
"""fleet_hygiene_scan — fleet-wide hygiene scan + per-spoke session triage.

Two complementary modes:

  FLEET mode (--fleet --registry <hub-registry.json>):
    Scans every wheel in the registry for:
      - orphaned agent worktrees (.claude/worktrees/agent-*) that are dirty and
        locked with changes never committed (stranded at 0 commits ahead of main)
      - spokes with dirty trees, unpushed commits, or no upstream
      - stale session dirs (>N days) without a closeout
    Emits a JSON report to <out-dir> and prints a triage summary.

    --rescue: for each stranded/locked agent worktree with no live session,
      commit dirty state to its own branch (wip-rescue trailer), write a recovery
      manifest, then unlock + prune. NEVER runs on main. NEVER touches a worktree
      tied to a live session.

  SPOKE mode (--spoke <root>):
    Single-spoke session lane classification:
      husk        : 0 turns (auto-archive after grace period)
      interrupted : real work, no closeout (review queue)
      closed      : reached a closeout or completed turn
    Emits a review-queue artifact under <spoke>/WAI-Harness/spoke/local/maintenance/.
    --apply archives husks via git mv / move.

Usage:
  fleet_hygiene_scan.py --fleet --registry <hub-registry.json> [--stale-days 14]
                         [--rescue] [--out-dir <path>]
  fleet_hygiene_scan.py --spoke <root> [--apply] [--grace-hours 24] [--json]
"""
import argparse
import glob
import json
import os
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def _base(spoke_root):
    """v4 path or legacy WAI-Spoke."""
    v4 = Path(spoke_root) / "WAI-Harness" / "spoke" / "local"
    return v4 if (v4 / "WAI-State.json").exists() else Path(spoke_root) / "WAI-Spoke"


def _git(cwd, *args, timeout=20):
    try:
        r = subprocess.run(["git", "-C", str(cwd), *args],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ── session classification ────────────────────────────────────────────────────

def classify_session(track_path):
    """Classify a session lane by its track.jsonl.

    husk        : no real work (0 turns; only session_start / empty / missing track)
    closed      : last entry is a closeout OR a completed turn
    interrupted : has work turns but no closeout (needs review)
    """
    p = Path(track_path)
    if not p.exists() or p.stat().st_size == 0:
        return "husk"
    entries = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    if not entries:
        return "husk"
    if any(e.get("event") == "closeout" for e in entries):
        return "closed"
    work = [e for e in entries if e.get("event") not in ("session_start", None)
            or e.get("completed") is not None]
    if not work:
        return "husk"
    if entries[-1].get("completed") is True:
        return "closed"
    return "interrupted"


def _pending_savepoint_sessions(base):
    """Session ids that still have a pending savepoint — never archive these."""
    pending = set()
    for sp in glob.glob(str(base / "initiatives" / "savepoints" / "**" / "*.json"),
                        recursive=True):
        try:
            d = json.load(open(sp))
        except Exception:
            continue
        if d.get("status") not in ("resolved", "completed") and d.get("session_id"):
            pending.add(d["session_id"])
    return pending


def _write_review_queue(base, interrupted):
    """Write a review-queue artifact under maintenance/ for interrupted sessions."""
    maint = base / "maintenance"
    maint.mkdir(parents=True, exist_ok=True)
    stamp = _now_iso().replace(":", "").replace("-", "")[:15]
    out = maint / f"interrupted-sessions-{stamp}.json"
    payload = {
        "generated_at": _now_iso(),
        "count": len(interrupted),
        "sessions": [{"id": s, "action": "operator-review-required"} for s in interrupted],
    }
    out.write_text(json.dumps(payload, indent=2))
    return str(out)


# ── single-spoke session scan ─────────────────────────────────────────────────

def scan_spoke_sessions(spoke_root, apply=False, grace_hours=24):
    """Classify all session lanes in a spoke; archive husks; queue interrupted for review."""
    base = _base(spoke_root)
    sessions_dir = base / "sessions"
    report = {
        "husk_archived": 0, "review_queued": 0, "kept": 0, "savepoint_protected": 0,
        "husks": [], "interrupted": [], "spoke_root": str(spoke_root), "applied": apply,
    }
    if not sessions_dir.is_dir():
        return report
    protected = _pending_savepoint_sessions(base)
    archive_dir = sessions_dir / "_archive"
    now = datetime.now(timezone.utc).timestamp()
    for sess in sorted(sessions_dir.iterdir()):
        if not sess.is_dir() or sess.name == "_archive":
            continue
        klass = classify_session(sess / "track.jsonl")
        if sess.name in protected:
            report["savepoint_protected"] += 1
            report["kept"] += 1
            continue
        if klass == "husk":
            age_h = (now - sess.stat().st_mtime) / 3600
            if age_h < grace_hours:
                report["kept"] += 1
                continue
            report["husks"].append(sess.name)
            if apply:
                archive_dir.mkdir(parents=True, exist_ok=True)
                dst = archive_dir / sess.name
                if subprocess.run(["git", "-C", str(spoke_root), "mv", str(sess), str(dst)],
                                  capture_output=True).returncode != 0:
                    sess.rename(dst)
            report["husk_archived"] += 1
        elif klass == "interrupted":
            report["interrupted"].append(sess.name)
            report["review_queued"] += 1
        else:
            report["kept"] += 1
    if report["interrupted"]:
        report["review_queue_artifact"] = _write_review_queue(base, report["interrupted"])
    return report


# ── fleet-wide worktree scan ──────────────────────────────────────────────────

def scan_worktrees(wheel_path):
    """Return list of agent worktrees with risk flags for a wheel."""
    rc, out, _ = _git(wheel_path, "worktree", "list", "--porcelain")
    if rc != 0:
        return []
    entries, cur = [], {}
    for line in out.splitlines():
        if line.startswith("worktree "):
            if cur:
                entries.append(cur)
            cur = {"path": line.split(" ", 1)[1], "locked": False}
        elif line.startswith("branch "):
            cur["branch"] = line.split(" ", 1)[1].replace("refs/heads/", "")
        elif line.strip() == "locked":
            cur["locked"] = True
    if cur:
        entries.append(cur)

    risky = []
    for e in entries:
        wp = e["path"]
        if "/.claude/worktrees/agent-" not in wp:
            continue
        _, dout, _ = _git(wp, "status", "--porcelain")
        dirty = len([ln for ln in dout.splitlines() if ln.strip()])
        br = e.get("branch", "")
        ahead = "?"
        if br:
            rc2, aout, _ = _git(wheel_path, "rev-list", "--count", f"main..{br}")
            ahead = aout if rc2 == 0 else "?"
        last = None
        for root, dirs, files in os.walk(wp):
            if ".git" in root:
                continue
            for f in files:
                try:
                    mt = os.path.getmtime(os.path.join(root, f))
                    last = mt if last is None else max(last, mt)
                except OSError:
                    pass
        stranded = dirty > 0 and ahead in ("0", "?")
        risky.append({
            "path": wp, "branch": br, "dirty": dirty,
            "commits_ahead_of_main": ahead, "locked": e.get("locked", False),
            "last_modified": datetime.fromtimestamp(last, timezone.utc).isoformat() if last else None,
            "stranded_uncommitted": stranded,
        })
    return risky


def _live_session_pids():
    """PIDs of any live Claude Code / claude process (coarse check)."""
    try:
        out = subprocess.run(["pgrep", "-af", "claude"], capture_output=True, text=True).stdout
        pids = set()
        for line in out.splitlines():
            if "claude" in line and "pgrep" not in line:
                try:
                    pids.add(int(line.split()[0]))
                except (ValueError, IndexError):
                    pass
        return pids
    except Exception:
        return set()


def _worktree_branch_for_rescue(branch):
    """Generate a rescue branch name from the agent worktree branch."""
    base = branch.rstrip("/").split("/")[-1] if branch else "unknown"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"wip-rescue/{base}-{stamp}"


def rescue_worktrees(wheel_path, stranded, dry_run=True):
    """For each stranded agent worktree: commit to rescue branch, write manifest, unlock+prune.

    Guards:
    - Never touches a worktree if live Claude sessions are running (conservative: any live
      session could own any worktree).
    - Never runs on main.
    - Always commits before pruning — no changes are lost.

    Returns a rescue manifest dict.
    """
    live = _live_session_pids()
    manifest = {
        "generated_at": _now_iso(),
        "wheel_path": str(wheel_path),
        "dry_run": dry_run,
        "live_session_guard_triggered": bool(live),
        "rescued": [],
        "skipped": [],
    }
    if live:
        manifest["note"] = (
            f"ABORTED: {len(live)} live Claude session(s) detected (PIDs {sorted(live)}). "
            "Rescue requires no live sessions to avoid race conditions."
        )
        return manifest

    for wt in stranded:
        wp = Path(wt["path"])
        br = wt.get("branch", "")
        if br in ("main", "master"):
            manifest["skipped"].append({"path": str(wp), "reason": "branch is main/master — skip"})
            continue
        rescue_br = _worktree_branch_for_rescue(br)
        entry = {"worktree_path": str(wp), "original_branch": br, "rescue_branch": rescue_br,
                 "dirty_files": wt["dirty"], "dry_run": dry_run}
        if dry_run:
            entry["action"] = "would commit + prune (dry-run)"
            manifest["rescued"].append(entry)
            continue
        # 1. Commit all dirty state to rescue branch
        rc1, _, _ = _git(wp, "checkout", "-b", rescue_br)
        if rc1 != 0:
            # Branch may not exist as a checkout; try add+commit on current branch
            rescue_br = br or "wip-rescue-fallback"
        _git(wp, "add", "-A")
        msg = f"wip-rescue: stranded agent work ({wt['dirty']} files) rescued by fleet_hygiene_scan"
        rc2, _, err2 = _git(wp, "commit", "-m", msg)
        if rc2 != 0:
            entry["error"] = f"commit failed: {err2}"
            manifest["skipped"].append(entry)
            continue
        # 2. Unlock + prune
        _git(wheel_path, "worktree", "unlock", str(wp))
        _git(wheel_path, "worktree", "remove", "--force", str(wp))
        entry["action"] = "committed + pruned"
        entry["rescue_branch"] = rescue_br
        manifest["rescued"].append(entry)

    return manifest


def count_stale_sessions(path, stale_days):
    """Sessions without a closeout, older than N days."""
    sdir = os.path.join(path, "WAI-Harness/spoke/local/sessions")
    if not os.path.isdir(sdir):
        return None
    now = datetime.now(timezone.utc).timestamp()
    total = interrupted = 0
    for d in os.scandir(sdir):
        if not d.is_dir():
            continue
        total += 1
        track = os.path.join(d.path, "track.jsonl")
        if not os.path.exists(track):
            interrupted += 1
            continue
        age_days = (now - d.stat().st_mtime) / 86400
        if age_days < stale_days:
            continue
        try:
            lines = [ln for ln in open(track, encoding="utf-8").read().splitlines() if ln.strip()]
            last = json.loads(lines[-1]) if lines else {}
            blob = json.dumps(last).lower()
            closed = any(k in blob for k in
                         ("closeout", "savepoint", '"clean"', "session_end", "closed"))
            if not closed:
                interrupted += 1
        except Exception:
            interrupted += 1
    return {"total": total, "interrupted_or_husk": interrupted}


# ── per-lug per-state staleness sweep (impl-cert-sweeper-readonly-v1, L2) ────
#
# Extends count_stale_sessions' staleness-threshold pattern (age = now - mtime,
# flag anything over a threshold) from session-directory granularity to lug
# granularity, one level finer: per lug PER STATUS DIRECTORY it currently sits
# in (open/in_progress/needs_attention -- the only states with a meaningful
# "should not sit here forever" SLO; terminal/paused states like completed,
# deferred, parked are excluded from staleness scoring on purpose).
#
# REPORT-ONLY, per the certification-chain landing plan's explicit rollout
# order (L2 must be a report-only sweeper before any enforcement lug):
#   - NEVER moves, edits, or deletes a lug file.
#   - NEVER releases a lease or auto-retires anything.
#   - Only reads mtimes + JSON content and writes its OWN report artifact.
#
# Age approximation: a lug carries no dedicated "time entered this status"
# timestamp today, so age-in-state is approximated by the file's mtime (same
# approximation count_stale_sessions already uses for session dirs). This is a
# known, accepted imprecision -- a lug's mtime updates on every field write,
# not just on a status transition, so a lug edited-in-place without moving
# directories will look "fresher" than it structurally is. Documented here
# rather than silently assumed.

DEFAULT_LUG_STATE_SLO_HOURS = {
    "open": 336,           # 14d — generous backlog dwell budget before a staleness flag
    "in_progress": 24,     # in-flight work should not sit idle long — deliberately far
                           # shorter than `open`, per the landing plan's own guidance
    "needs_attention": 48,
}

# Statuses with no "should not sit here" meaning — excluded from violation scoring
# (still counted in by_status for visibility). Not exhaustive of every status a
# lug schema doc lists; these are the ones observed as physical bytype/*/ dirs.
_LUG_STALENESS_EXEMPT_STATUSES = {
    "completed", "done", "closed", "delivered", "retired",
    "deferred", "parked", "acknowledged", "active", "resolved", "undelivered",
}


def count_stale_lugs(spoke_root, slo_hours=None):
    """Per-lug-per-state staleness sweep, report-only.

    Walks every lugs/bytype/<type>/<status>/*.json, computing age-in-state via
    mtime and comparing against a per-status SLO default (see
    DEFAULT_LUG_STATE_SLO_HOURS). Also aggregates the 3 Goodhart counter-metrics
    the certification chain's landing plan requires be tracked from day one,
    even pre-enforcement (no gate exists yet to push back with):

      - push_back_rate_per_gate: PASS vs non-PASS signature verdicts, per gate
        number, across every signatures[] entry found on any lug (any status).
        A 100% PASS rate is a RED FLAG (rubber-stamping), not a success signal —
        surfaced here as a raw ratio, no verdict rendered by this function.
      - time_in_state distributions: min/median/mean/max age-in-state per
        status, so SLO pressure can be checked against a real baseline instead
        of asserted.
      - evidence_pointer_density: average len(evidence[]) per gate, across the
        same signatures[] population — guards against empty attestations.

    NEVER mutates, moves, or deletes any lug file. Returns a plain dict; does
    not write to disk (see write_lug_staleness_report for the on-disk artifact).
    """
    base = _base(spoke_root)
    bytype_dir = base / "lugs" / "bytype"
    slo = dict(DEFAULT_LUG_STATE_SLO_HOURS)
    if slo_hours:
        slo.update(slo_hours)
    now = datetime.now(timezone.utc).timestamp()

    report = {
        "generated_at": _now_iso(),
        "slo_hours": slo,
        "scanned": 0,
        "by_status": {},
        "violations": [],
        "time_in_state": {},
        "goodhart": {
            "push_back_rate_per_gate": {},
            "evidence_pointer_density_per_gate": {},
            "note": "counter-metrics tracked from day one per the landing plan's Goodhart "
                    "guard — no gate SA exists yet to push back with, so these are a "
                    "pre-enforcement baseline, not yet an anomaly signal.",
        },
    }
    if not bytype_dir.is_dir():
        return report

    ages_by_status = {}
    gate_verdicts = {}   # gate -> {"pass": n, "total": n}
    gate_evidence = {}   # gate -> list of evidence[] lengths

    for type_dir in sorted(p for p in bytype_dir.iterdir() if p.is_dir()):
        for status_dir in sorted(p for p in type_dir.iterdir() if p.is_dir()):
            status = status_dir.name
            for f in sorted(status_dir.glob("*.json")):
                report["scanned"] += 1
                report["by_status"][status] = report["by_status"].get(status, 0) + 1
                try:
                    age_h = (now - f.stat().st_mtime) / 3600
                except OSError:
                    continue
                ages_by_status.setdefault(status, []).append(age_h)

                try:
                    lug = json.loads(f.read_text())
                except Exception:
                    lug = {}

                for sig in (lug.get("signatures") or []):
                    if not isinstance(sig, dict):
                        continue
                    gate = sig.get("gate", "unknown")
                    gv = gate_verdicts.setdefault(gate, {"pass": 0, "total": 0})
                    gv["total"] += 1
                    if str(sig.get("verdict", "")).upper() == "PASS":
                        gv["pass"] += 1
                    gate_evidence.setdefault(gate, []).append(len(sig.get("evidence") or []))

                if status in _LUG_STALENESS_EXEMPT_STATUSES:
                    continue
                threshold = slo.get(status)
                if threshold is None or age_h < threshold:
                    continue
                report["violations"].append({
                    "id": lug.get("id", f.stem),
                    "type": type_dir.name,
                    "status": status,
                    "age_hours": round(age_h, 1),
                    "slo_hours": threshold,
                    "cert_state": lug.get("cert_state"),
                    "cert_weight": lug.get("cert_weight"),
                    "path": str(f.relative_to(base)),
                })

    report["violations"].sort(key=lambda v: -v["age_hours"])

    for status, ages in ages_by_status.items():
        report["time_in_state"][status] = {
            "count": len(ages),
            "min_hours": round(min(ages), 1),
            "median_hours": round(statistics.median(ages), 1),
            "mean_hours": round(statistics.mean(ages), 1),
            "max_hours": round(max(ages), 1),
        }

    for gate, gv in gate_verdicts.items():
        total = gv["total"]
        non_pass = total - gv["pass"]
        report["goodhart"]["push_back_rate_per_gate"][str(gate)] = {
            "total_signatures": total,
            "non_pass": non_pass,
            "push_back_rate": round(non_pass / total, 3) if total else None,
        }
    for gate, lens in gate_evidence.items():
        report["goodhart"]["evidence_pointer_density_per_gate"][str(gate)] = {
            "signatures": len(lens),
            "mean_evidence_pointers": round(statistics.mean(lens), 2) if lens else 0,
            "min_evidence_pointers": min(lens) if lens else 0,
        }

    return report


def write_lug_staleness_report(spoke_root, slo_hours=None):
    """Run count_stale_lugs() and persist it to a fixed-name report artifact under
    maintenance/, so downstream consumers (a future wakeup-brief reader, this
    lug's own future L3/L4/L7 gate consumers, object-contracts.json's
    postcondition_check()) always read the freshest sweep without needing to
    glob a timestamped filename. Report-only: writes exactly one file, touches
    nothing under lugs/.
    """
    base = _base(spoke_root)
    report = count_stale_lugs(spoke_root, slo_hours=slo_hours)
    maint = base / "maintenance"
    maint.mkdir(parents=True, exist_ok=True)
    out = maint / "lug-staleness-latest.json"
    out.write_text(json.dumps(report, indent=2))
    report["_report_path"] = str(out)
    return report


# ── fleet scan (registry-wide) ────────────────────────────────────────────────

def scan_fleet(registry_path, stale_days=14, rescue=False, out_dir=None):
    """Scan every wheel in hub-registry.json for hygiene issues.

    Returns the full report dict and (if rescue) the rescue manifest dict.
    Writes JSON report under out_dir (or a maintenance/ dir next to the registry).
    """
    try:
        reg = json.load(open(registry_path))
    except Exception as e:
        print(f"[fleet-hygiene] ERROR: cannot read registry {registry_path}: {e}", file=sys.stderr)
        return {}, {}
    wheels = reg.get("wheels", [])
    if out_dir is None:
        out_dir = os.path.join(os.path.dirname(registry_path), "..", "maintenance")
    os.makedirs(out_dir, exist_ok=True)

    report = {
        "generated_at": _now_iso(), "stale_days": stale_days,
        "registry": registry_path, "wheels": [], "totals": {},
    }
    t = {
        "wheels": 0, "missing_path": 0, "dirty_wheels": 0, "no_upstream": 0,
        "unpushed_commits": 0, "stranded_worktrees": 0, "stranded_files": 0,
        "interrupted_sessions": 0,
    }
    all_stranded = {}

    for w in wheels:
        p, wid = w.get("path"), w.get("wheel_id")
        rec = {"wheel_id": wid, "path": p}
        t["wheels"] += 1
        if not p or not os.path.isdir(p):
            rec["status"] = "MISSING_PATH"
            t["missing_path"] += 1
            report["wheels"].append(rec)
            continue
        _, _, _ = _git(p, "branch", "--show-current")
        _, dout, _ = _git(p, "status", "--porcelain")
        dirty = len([ln for ln in dout.splitlines() if ln.strip()])
        rc, ahead, _ = _git(p, "rev-list", "--count", "@{u}..HEAD")
        if rc != 0:
            rec["upstream"] = None
            t["no_upstream"] += 1
        else:
            rec["upstream"] = int(ahead)
            t["unpushed_commits"] += int(ahead)
        wts = scan_worktrees(p)
        stranded = [x for x in wts if x["stranded_uncommitted"]]
        rec.update({
            "dirty": dirty,
            "agent_worktrees": len(wts),
            "stranded_worktrees": len(stranded),
            "stranded_files": sum(x["dirty"] for x in stranded),
            "worktree_detail": stranded,
        })
        if dirty:
            t["dirty_wheels"] += 1
        t["stranded_worktrees"] += len(stranded)
        t["stranded_files"] += rec["stranded_files"]
        if stranded:
            all_stranded[p] = stranded
        ss = count_stale_sessions(p, stale_days)
        if ss:
            rec["sessions"] = ss
            t["interrupted_sessions"] += ss["interrupted_or_husk"]
        report["wheels"].append(rec)

    report["totals"] = t
    stamp = report["generated_at"].replace(":", "").replace("-", "")[:15]
    out = os.path.join(out_dir, f"fleet-hygiene-{stamp}.json")
    json.dump(report, open(out, "w"), indent=2)

    rescue_manifest = {}
    if rescue and all_stranded:
        rm_path = os.path.join(out_dir, f"worktree-rescue-{stamp}.json")
        all_rescued = {"generated_at": _now_iso(), "wheels": []}
        for wheel_p, stranded_wts in all_stranded.items():
            rm = rescue_worktrees(wheel_p, stranded_wts, dry_run=False)
            all_rescued["wheels"].append({"wheel_path": wheel_p, "rescue_result": rm})
            if rm.get("live_session_guard_triggered"):
                print(f"[fleet-hygiene] RESCUE SKIPPED for {wheel_p}: {rm.get('note')}")
        json.dump(all_rescued, open(rm_path, "w"), indent=2)
        rescue_manifest = all_rescued
        rescue_manifest["manifest_path"] = rm_path

    return report, rescue_manifest


# ── CLI ───────────────────────────────────────────────────────────────────────

def _main_fleet(args):
    report, rescue = scan_fleet(
        args.registry,
        stale_days=args.stale_days,
        rescue=args.rescue,
        out_dir=args.out_dir,
    )
    t = report.get("totals", {})
    if args.json:
        out = {"report": report}
        if rescue:
            out["rescue_manifest"] = rescue
        print(json.dumps(out, indent=2))
        return 0
    print(f"\nFLEET HYGIENE — {t.get('wheels',0)} wheels  ({report.get('generated_at','')})")
    print(f"  stranded agent worktrees : {t.get('stranded_worktrees',0)}  "
          f"({t.get('stranded_files',0)} uncommitted files at risk)")
    print(f"  spokes with NO upstream  : {t.get('no_upstream',0)}")
    print(f"  total unpushed commits   : {t.get('unpushed_commits',0)}")
    print(f"  dirty wheels             : {t.get('dirty_wheels',0)}")
    print(f"  interrupted/husk sessions: {t.get('interrupted_sessions',0)} (>{args.stale_days}d)")
    print(f"  missing registry paths   : {t.get('missing_path',0)}")
    worst = sorted(
        [w for w in report.get("wheels", []) if w.get("stranded_worktrees")],
        key=lambda x: -x.get("stranded_files", 0))[:5]
    if worst:
        print("  worst stranded worktrees:")
        for w in worst:
            print(f"    {str(w.get('wheel_id','?')):30s} "
                  f"{w.get('stranded_worktrees',0)} worktrees / {w.get('stranded_files',0)} files")
    if args.rescue and rescue:
        rescued_n = sum(len(w.get("rescue_result", {}).get("rescued", []))
                        for w in rescue.get("wheels", []))
        print(f"\n  RESCUE: {rescued_n} worktree(s) committed+pruned")
        print(f"  manifest: {rescue.get('manifest_path','?')}")
    return 0


def _main_spoke(args):
    rep = scan_spoke_sessions(args.spoke, apply=args.apply, grace_hours=args.grace_hours)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    mode = "ARCHIVED" if args.apply else "would archive (dry-run)"
    print(f"[fleet-hygiene] {mode}: {rep['husk_archived']} husk(s) | "
          f"{rep['review_queued']} interrupted->review | {rep['kept']} kept | "
          f"{rep['savepoint_protected']} savepoint-protected")
    for h in rep["husks"]:
        print(f"  husk: {h}")
    for i in rep["interrupted"]:
        print(f"  review: {i}")
    if rep.get("review_queue_artifact"):
        print(f"  review queue: {rep['review_queue_artifact']}")
    return 0


def _main_lugs(args):
    """impl-cert-sweeper-readonly-v1 (L2): per-lug-per-state staleness sweep, report-only."""
    rep = write_lug_staleness_report(args.spoke)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    print(f"[fleet-hygiene] lug staleness sweep — {rep['scanned']} lugs scanned "
          f"across {len(rep['by_status'])} status(es)  ({rep['generated_at']})")
    for status, n in sorted(rep["by_status"].items()):
        print(f"  {status}: {n}")
    if rep["violations"]:
        print(f"  VIOLATIONS ({len(rep['violations'])}) — report-only, no auto-action taken:")
        for v in rep["violations"][:20]:
            print(f"    {v['id']} [{v['type']}/{v['status']}] "
                  f"age={v['age_hours']}h > SLO {v['slo_hours']}h"
                  + (f"  cert_state={v['cert_state']}" if v.get("cert_state") else ""))
    else:
        print("  no violations")
    for gate, gv in rep["goodhart"]["push_back_rate_per_gate"].items():
        print(f"  Goodhart gate {gate}: push_back_rate={gv['push_back_rate']} "
              f"({gv['non_pass']}/{gv['total_signatures']} non-PASS)")
    print(f"  report: {rep.get('_report_path')}")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="mode")

    fleet_p = sub.add_parser("fleet", help="Fleet-wide scan (all wheels in registry)")
    fleet_p.add_argument("--registry", required=True,
                         help="Path to hub-registry.json")
    fleet_p.add_argument("--stale-days", type=int, default=14)
    fleet_p.add_argument("--rescue", action="store_true",
                         help="Rescue stranded worktrees: commit->branch, write manifest, unlock+prune")
    fleet_p.add_argument("--out-dir", default=None)
    fleet_p.add_argument("--json", action="store_true")

    spoke_p = sub.add_parser("spoke", help="Single-spoke session triage")
    spoke_p.add_argument("--spoke", default=".",
                         help="Spoke root path")
    spoke_p.add_argument("--apply", action="store_true",
                         help="Archive husks (default: dry-run)")
    spoke_p.add_argument("--grace-hours", type=int, default=24)
    spoke_p.add_argument("--json", action="store_true")

    lugs_p = sub.add_parser(
        "lugs", help="Per-lug-per-state staleness sweep (report-only, impl-cert-sweeper-readonly-v1)")
    lugs_p.add_argument("--spoke", default=".",
                        help="Spoke root path")
    lugs_p.add_argument("--json", action="store_true")

    # Back-compat: old flat CLI (--spoke / --registry as flags) routes to correct subcommand
    if argv and argv[0] not in ("fleet", "spoke", "lugs", "-h", "--help"):
        if "--registry" in argv or "--fleet" in argv:
            argv = ["fleet"] + [a for a in argv if a != "--fleet"]
        else:
            argv = ["spoke"] + argv

    a = ap.parse_args(argv)
    if a.mode == "fleet":
        return _main_fleet(a)
    if a.mode == "lugs":
        return _main_lugs(a)
    return _main_spoke(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
