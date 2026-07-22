#!/usr/bin/env python3
"""hygiene_run.py — the hygiene advisor's INNATE runner.

Called with ZERO manual invocation, backgrounded + best-effort, from
`.claude/hooks/session-start.sh` right after the pull block. This is what makes
the hygiene advisor innate per the parent lug's mission bar: "the advisor keeps
the spoke healthy WITHOUT anyone invoking it ... if it only works when called, it
FAILS." Every session start writes a fresh, current signal — nobody has to
remember to run anything.

This runner is READ-ONLY / SIGNAL-ONLY: it never reaps sessions or prunes
savepoints itself (session_reaper.py and savepoint_prune.py are separate,
dry-run-default, explicitly-invoked arms). It runs three checks:
  1. deprecation scan  — v3_path_lint.lint() over managed/ (existing v3-noop
     soft-feature gate, wrapped not reimplemented).
  2. phantom check      — wai_paths.detect(): a `WAI-Spoke/` tree coexisting
     alongside `WAI-Harness/` on a spoke that should be v4-only is a phantom
     that forces coexist-mode reads (see project memory:
     reference-deployed-hooks-must-be-tracked).
  3. health --quick     — spoke_health_check.py --quick --json (subprocess; the
     existing tool, wrapped not reimplemented).

...then a fast, in-process DRY-RUN scan of the two arms (session_reaper.scan /
savepoint_prune.scan) for backlog counts only — this runner never archives
anything, it just reports how much backlog exists so the scorecard/operator can
decide whether to run the arms.

Writes spoke/local/maintenance/hygiene-latest.json:
    {ts, spoke, v3_violations, phantom_present, health {passed, failed},
     reaper_pending, prune_pending, verdict: CLEAN|DRIFT}

verdict = DRIFT iff v3_violations > 0 OR phantom_present OR health.failed > 0.
Reap/prune backlog is reported but does NOT by itself flip the verdict to DRIFT —
routine housekeeping backlog is a separate concern from installation correctness.

Designed to fail SILENTLY-BUT-VISIBLY from the caller's perspective: any internal
exception is caught, and a best-effort degraded hygiene-latest.json is still
written (verdict UNKNOWN) so the file is never simply missing. The exit code is
always 0 from the session-start hook's point of view (it is backgrounded there
regardless), but running this script directly returns 1 on internal failure.

CLI:
    python3 hygiene_run.py --spoke-root DIR [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import wai_paths  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _spoke_name(spoke_root: str, base: str) -> str:
    try:
        state = json.loads((Path(base) / "WAI-State.json").read_text())
        wheel = state.get("wheel", {})
        return wheel.get("abbrev") or wheel.get("name") or os.path.basename(os.path.abspath(spoke_root))
    except Exception:
        return os.path.basename(os.path.abspath(spoke_root))


def _v3_violations(managed_dir: Path) -> int:
    try:
        import v3_path_lint
        rep = v3_path_lint.lint(str(managed_dir))
        return len(rep.get("violations", {}))
    except Exception:
        return -1  # sentinel: check itself failed to run (not the same as 0 clean)


def _phantom_present(spoke_root: str) -> bool:
    try:
        info = wai_paths.detect(spoke_root)
        return bool(info.get("has_v3") and info.get("has_v4"))
    except Exception:
        return False


def _health_quick(spoke_root: str) -> dict:
    tool = Path(__file__).parent / "spoke_health_check.py"
    try:
        out = subprocess.run(
            [sys.executable, str(tool), spoke_root, "--quick", "--json"],
            capture_output=True, text=True, timeout=20,
        )
        d = json.loads(out.stdout)
        return {"passed": d.get("passed", 0), "failed": d.get("failed", 0)}
    except Exception:
        return {"passed": 0, "failed": -1}  # -1 sentinel: check itself failed to run


def _reap_pending(spoke_root: str) -> int:
    try:
        import session_reaper
        m = session_reaper.scan(spoke_root)
        return m.get("count_reapable", 0) if m.get("ok") else -1
    except Exception:
        return -1


def _prune_pending(spoke_root: str) -> int:
    try:
        import savepoint_prune
        m = savepoint_prune.scan(spoke_root)
        return m.get("total_archived_planned", 0) if m.get("ok") else -1
    except Exception:
        return -1


def _circle_quick(spoke_root: str) -> dict:
    """Cheap-tier circle audit (epic-circle-audit-open-loops-and-orphans-v1).
    Best-effort import of circle_audit; signal-only — never raises, never writes.
    Includes the version-staleness signal that makes a version bump demand a deep audit."""
    try:
        import circle_audit
        bindings = circle_audit.collect_bindings(spoke_root)
        circles = circle_audit.audit_circles(spoke_root, bindings)
        findings = circle_audit.enforcement_findings(spoke_root, bindings)
        ver = circle_audit.version_staleness(spoke_root)
        return {
            "phantom": sum(1 for c in circles if c["verdict"] == "PHANTOM"),
            "open": sum(1 for c in circles if c["verdict"] == "OPEN"),
            "closed": sum(1 for c in circles if c["verdict"] == "CLOSED"),
            "enforcement_findings": len(findings),
            "audit_stale": ver.get("stale", True),
        }
    except Exception:
        return {"phantom": -1, "open": -1, "closed": -1, "enforcement_findings": -1, "audit_stale": True}


def run(spoke_root: str) -> dict:
    base, mode = wai_paths.resolve_wai_root(spoke_root)
    ts = _now_iso()
    if base is None:
        return {
            "ts": ts, "spoke": os.path.basename(os.path.abspath(spoke_root)),
            "v3_violations": -1, "phantom_present": False,
            "health": {"passed": 0, "failed": -1},
            "reaper_pending": -1, "prune_pending": -1,
            "verdict": "UNKNOWN", "_error": "no WAI working base found",
        }

    managed_dir = Path(spoke_root) / "WAI-Harness" / "spoke" / "managed"
    v3v = _v3_violations(managed_dir)
    phantom = _phantom_present(spoke_root)
    health = _health_quick(spoke_root)
    reap_pending = _reap_pending(spoke_root)
    prune_pending = _prune_pending(spoke_root)
    circles = _circle_quick(spoke_root)

    drift = (v3v > 0) or phantom or (health.get("failed", 0) > 0) \
        or (circles.get("phantom", 0) > 0) or (circles.get("open", 0) > 0)
    verdict = "DRIFT" if drift else "CLEAN"
    if v3v < 0 or health.get("failed", 0) < 0:
        verdict = "UNKNOWN"

    return {
        "ts": ts,
        "spoke": _spoke_name(spoke_root, base),
        "harness_mode": mode,
        "v3_violations": v3v,
        "phantom_present": phantom,
        "health": health,
        "reaper_pending": reap_pending,
        "prune_pending": prune_pending,
        "circles": circles,
        "verdict": verdict,
    }


def write_latest(spoke_root: str, report: dict) -> str:
    base, _ = wai_paths.resolve_wai_root(spoke_root)
    maint_dir = Path(base) / "maintenance" if base else Path(spoke_root) / "WAI-Harness" / "spoke" / "local" / "maintenance"
    maint_dir.mkdir(parents=True, exist_ok=True)
    p = maint_dir / "hygiene-latest.json"
    p.write_text(json.dumps(report, indent=2))
    return str(p)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Hygiene advisor's innate runner — writes hygiene-latest.json.")
    ap.add_argument("--spoke-root", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    try:
        report = run(args.spoke_root)
        path = write_latest(args.spoke_root, report)
        report["_written"] = path
    except Exception as e:
        report = {
            "ts": _now_iso(), "spoke": os.path.basename(os.path.abspath(args.spoke_root)),
            "v3_violations": -1, "phantom_present": False,
            "health": {"passed": 0, "failed": -1},
            "reaper_pending": -1, "prune_pending": -1,
            "verdict": "UNKNOWN", "_error": str(e),
        }
        try:
            path = write_latest(args.spoke_root, report)
            report["_written"] = path
        except Exception:
            pass
        print(json.dumps(report, indent=2))
        return 1

    if args.json or True:  # always print — this is a signal file writer, not a gate
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
