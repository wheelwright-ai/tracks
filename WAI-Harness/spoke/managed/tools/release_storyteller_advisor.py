#!/usr/bin/env python3
"""
release_storyteller_advisor.py -- translate the delta between the last two
audited circle-continuity states into (a) a story-delta lug for the website
and (b) a mesh-check review lug per NEW mismatch, on every minor release.

The release event IS the circle-audit version-stamp advancing: circle_audit.py
stamps circle-audit-latest.json.harness_version each time it runs. This advisor
fires only when that stamp (a) matches the live WAI-Harness/VERSION (the audit
is fresh, not itself stale) and (b) differs from the version this advisor last
processed (so it never fires twice for the same release, and never fires on
audit data that hasn't caught up to the live version yet).

Usage:
    python3 tools/release_storyteller_advisor.py [--json] [--submit-lugs] [--dry-run]
    python3 tools/release_storyteller_advisor.py --simulate-delta --baseline OLD.json --current NEW.json [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wai_paths  # noqa: E402  harness-mode root resolver

SPOKE_ROOT = "."
ADVISOR_ID = "release-storyteller"
WEBSITE_SPOKE_ROOT = "/home/mario/projects/wheelwright/website"

# circle_audit.py's own HARD_KINDS (main()) -- a new one appearing is a
# new-evolution callout candidate, not just background noise.
HARD_FINDING_KINDS = {
    "BOUND_MISSING", "UNKNOWN_OWNERSHIP", "MANAGED_DRIFT",
    "DECLARED_NOT_INSTALLED", "INSTALLED_UNBOUND", "UNMERGED_LANE",
}
LONG_RUNNING_DAYS = 90

# Circle ids the marketing story publishes as "verified CLOSED, 8/8" -- the
# mesh-check fires when audited reality no longer matches what the story claims.
STORY_CLAIMED_CLOSED_CIRCLES = {
    "track-per-turn", "savepoint-floor", "compact-resume", "lane-csrp",
    "hygiene-innate", "edit-feedback", "test-gate", "worktree-hygiene",
}


def _advisors_base(spoke_root: str = SPOKE_ROOT) -> str:
    return wai_paths.advisors_dir(spoke_root) or str(Path(spoke_root) / "WAI-Spoke" / "advisors")


def _own_dir(spoke_root: str = SPOKE_ROOT) -> Path:
    return Path(_advisors_base(spoke_root)) / ADVISOR_ID


def _state_file(spoke_root: str = SPOKE_ROOT) -> Path:
    return _own_dir(spoke_root) / "scan_state.json"


def _runs_file(spoke_root: str = SPOKE_ROOT) -> Path:
    return _own_dir(spoke_root) / "runs.jsonl"


def _local_base(spoke_root: str = SPOKE_ROOT) -> Path:
    base, _ = wai_paths.resolve_wai_root(spoke_root)
    return Path(base) if base else Path(spoke_root) / "WAI-Spoke"


def _audit_latest_file(spoke_root: str = SPOKE_ROOT) -> Path:
    return _local_base(spoke_root) / "maintenance" / "circle-audit-latest.json"


def _story_doc_file(spoke_root: str = SPOKE_ROOT) -> Path:
    return _local_base(spoke_root) / "reference" / "marketing-circles-story-v1.md"


def _version_file(spoke_root: str = SPOKE_ROOT) -> Path:
    return Path(spoke_root) / "WAI-Harness" / "VERSION"


def _own_lugs_incoming(spoke_root: str = SPOKE_ROOT) -> Path:
    base = wai_paths.category(spoke_root, "lugs") or str(Path(spoke_root) / "WAI-Spoke" / "lugs")
    return Path(base) / "incoming"


def _own_lugs_outgoing(spoke_root: str = SPOKE_ROOT) -> Path:
    base = wai_paths.category(spoke_root, "lugs") or str(Path(spoke_root) / "WAI-Spoke" / "lugs")
    return Path(base) / "outgoing"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _circles_by_id(audit: dict) -> dict:
    return {c["id"]: c for c in (audit.get("circles") or []) if c.get("id")}


def _finding_kinds(audit: dict) -> set:
    return {f["kind"] for f in (audit.get("enforcement_findings") or []) if f.get("kind")}


def compute_deltas(baseline: dict, current: dict, own_state: dict, now: datetime) -> dict:
    """Diff two circle-audit snapshots into the categories the story-delta and
    mesh-check lugs need. Pure function of (baseline, current, own_state) so it
    can be exercised identically in real runs and --simulate-delta dry-runs."""
    base_circles = _circles_by_id(baseline)
    cur_circles = _circles_by_id(current)
    closed_since = dict(own_state.get("closed_since") or {})
    announced_long_running = set(own_state.get("long_running_announced") or [])

    new_evolution_circles = []
    long_running_circles = []
    mesh_mismatches = []
    all_ids = sorted(set(base_circles) | set(cur_circles))

    for cid in all_ids:
        prev = base_circles.get(cid, {}).get("verdict")
        cur = cur_circles.get(cid, {}).get("verdict")
        name = (cur_circles.get(cid) or base_circles.get(cid) or {}).get("name", cid)

        if cur == "CLOSED" and (prev in ("OPEN", "PHANTOM", "BROKEN") or prev is None):
            new_evolution_circles.append({"id": cid, "name": name, "was": prev or "NEW"})

        if cur == "CLOSED":
            closed_since.setdefault(cid, now.isoformat())
            first_closed = closed_since[cid]
            try:
                d0 = datetime.fromisoformat(first_closed.replace("Z", "+00:00"))
                if d0.tzinfo is None:
                    d0 = d0.replace(tzinfo=timezone.utc)
                age_days = (now - d0).days
            except ValueError:
                age_days = 0
            if age_days >= LONG_RUNNING_DAYS and cid not in announced_long_running:
                long_running_circles.append({"id": cid, "name": name, "closed_days": age_days})
        else:
            closed_since.pop(cid, None)

        if cid in STORY_CLAIMED_CLOSED_CIRCLES and cur is not None and cur != "CLOSED":
            mesh_mismatches.append({
                "id": cid, "name": name, "claimed": "CLOSED", "actual": cur,
            })

    base_kinds = _finding_kinds(baseline)
    cur_kinds = _finding_kinds(current)
    new_hard_kinds = sorted((cur_kinds - base_kinds) & HARD_FINDING_KINDS)
    new_soft_kinds = sorted((cur_kinds - base_kinds) - HARD_FINDING_KINDS)

    return {
        "new_evolution_circles": new_evolution_circles,
        "new_hard_finding_kinds": new_hard_kinds,
        "new_soft_finding_kinds": new_soft_kinds,
        "long_running_circles": long_running_circles,
        "mesh_mismatches": mesh_mismatches,
        "closed_since": closed_since,
        "long_running_announced": sorted(announced_long_running | {c["id"] for c in long_running_circles}),
    }


def build_website_delta_lug(deltas: dict, baseline_version: str, current_version: str, now_iso: str) -> dict:
    changed_sections = []
    if deltas["new_evolution_circles"] or deltas["new_hard_finding_kinds"]:
        changed_sections.append("Differentiator callouts")
    if deltas["long_running_circles"]:
        changed_sections.append("Differentiator callouts (long-running)")
    if deltas["mesh_mismatches"]:
        changed_sections.append("Circles inside a SPOKE (verified CLOSED table)")

    callouts = []
    for c in deltas["new_evolution_circles"]:
        callouts.append(f"NEW EVOLUTION: '{c['name']}' ({c['id']}) closed (was {c['was']}).")
    for k in deltas["new_hard_finding_kinds"]:
        callouts.append(f"NEW EVOLUTION: new hard-finding class '{k}' now instrumented.")
    for c in deltas["long_running_circles"]:
        callouts.append(f"LONG-RUNNING: '{c['name']}' ({c['id']}) closed for {c['closed_days']}d with live evidence.")

    ts = now_iso.replace(":", "").replace("-", "").split(".")[0].replace("Z", "")
    lug_id = f"story-delta-{current_version}-{ts}"
    return {
        "id": lug_id,
        "type": "task",
        "status": "open",
        "title": f"Circles story delta: harness {baseline_version} -> {current_version}",
        "created_at": now_iso,
        "from": "mywheel",
        "routed_to": "wheelwright-ai-website",
        "va": "build",
        "effort": "S",
        "impact": 6,
        "source_advisor": ADVISOR_ID,
        "perceive": [
            f"release-storyteller advisor detected a fresh circle-audit stamp for harness "
            f"{current_version} (previously processed: {baseline_version}). This delta is "
            f"regenerated from audited state per impl-release-storyteller-advisor-v1.",
            "Canonical doc: WAI-Harness/spoke/local/reference/marketing-circles-story-v1.md "
            "(mywheel). Adapt into site voice per the original implementation lug "
            "(feature-circles-story-marketing-page-v1) -- do not publish the mesh-check table.",
        ],
        "execute": [
            f"1. Sections to review/update: {', '.join(changed_sections) or 'none (no story-visible delta this release)'}.",
            "2. New differentiator callouts this release:\n   - " + "\n   - ".join(callouts)
            if callouts else "2. No new differentiator callouts this release.",
            "3. Apply only VERIFIED claims; if a mismatch section is listed above, do NOT "
            "publish the affected claim until mywheel resolves the paired review lug.",
        ],
        "verify": [
            "Live page reflects the listed section changes and differentiator callouts.",
            "No claim published for a circle currently listed under mesh_mismatches.",
        ],
        "acceptance_criteria": [
            "Site content updated for every listed changed section.",
            "New differentiator callouts (if any) rendered with distinct visual treatment.",
        ],
        "file_targets": ["site content/pages per website's own structure"],
        "discovered_in": f"release-storyteller advisor run ({current_version})",
        "notes": f"Automated delta. new_evolution={len(deltas['new_evolution_circles'])}, "
                 f"new_hard_kinds={len(deltas['new_hard_finding_kinds'])}, "
                 f"long_running={len(deltas['long_running_circles'])}, "
                 f"mesh_mismatches={len(deltas['mesh_mismatches'])}.",
        "_deltas": deltas,
    }


def build_mesh_review_lug(mismatch: dict, current_version: str, now_iso: str, idx: int) -> dict:
    ts = now_iso.replace(":", "").replace("-", "").split(".")[0].replace("Z", "")
    return {
        "id": f"mesh-check-{mismatch['id']}-{ts}-{idx}",
        "type": "bug",
        "status": "open",
        "title": f"Mesh-check: story claims '{mismatch['name']}' CLOSED, audit now shows {mismatch['actual']}",
        "created_at": now_iso,
        "routed_to": "LOCAL",
        "va": "fix",
        "effort": "S",
        "impact": 6,
        "source_advisor": ADVISOR_ID,
        "perceive": [
            f"marketing-circles-story-v1.md lists '{mismatch['id']}' ({mismatch['name']}) under "
            f"the 'verified CLOSED, 8/8' table. Harness {current_version}'s circle-audit now "
            f"shows verdict={mismatch['actual']} for this circle.",
            "This is a mesh-check mismatch: the published story no longer meshes with audited "
            "state, so it is a defect report on the story, not a copy-editing task.",
        ],
        "execute": [
            f"1. Investigate why circle '{mismatch['id']}' regressed to {mismatch['actual']}.",
            "2. Either fix the underlying circle so it re-closes, or if the regression is "
            "expected/intentional, update marketing-circles-story-v1.md's claimed-closed table "
            "and STORY_CLAIMED_CLOSED_CIRCLES in release_storyteller_advisor.py to match reality.",
            "3. Do not let the website publish this claim until resolved (the paired story-delta "
            "lug already excludes it).",
        ],
        "verify": [
            f"circle-audit-latest.json shows '{mismatch['id']}' verdict=CLOSED again, OR "
            "marketing-circles-story-v1.md's table is updated to reflect the new verdict.",
        ],
        "acceptance_criteria": [
            f"Circle '{mismatch['id']}' verdict and the published story claim agree.",
        ],
        "file_targets": [
            "WAI-Harness/spoke/local/reference/marketing-circles-story-v1.md",
            "WAI-Harness/spoke/managed/tools/circle_audit.py",
        ],
        "discovered_in": f"release-storyteller advisor run ({current_version})",
    }


def detect_and_run(spoke_root: str, force_process: bool = False) -> dict:
    """Real-cadence entry point: reads live state, applies the freshness +
    novelty gate, and returns {'fired': bool, 'reason': str, ...}."""
    audit = _load_json(_audit_latest_file(spoke_root))
    if not audit:
        return {"fired": False, "reason": "no circle-audit-latest.json present"}

    live_version = (_version_file(spoke_root).read_text().strip()
                    if _version_file(spoke_root).exists() else None)
    stamped_version = audit.get("harness_version")

    if not live_version or not stamped_version:
        return {"fired": False, "reason": "missing live VERSION or stamped harness_version"}

    if not force_process and stamped_version != live_version:
        return {"fired": False, "reason": f"audit is stale (stamped={stamped_version}, live={live_version}); "
                                           "waiting for a fresh deep audit before storytelling"}

    own_state = _load_json(_state_file(spoke_root))
    last_processed_version = own_state.get("last_processed_version")

    if not force_process and stamped_version == last_processed_version:
        return {"fired": False, "reason": f"already processed version {stamped_version}"}

    baseline = own_state.get("last_processed_audit") or audit  # first-ever run: seed from self, no-op delta
    now = datetime.now(timezone.utc)
    deltas = compute_deltas(baseline, audit, own_state, now)

    return {
        "fired": True,
        "baseline_version": baseline.get("harness_version", stamped_version),
        "current_version": stamped_version,
        "deltas": deltas,
        "current_audit": audit,
    }


def submit(result: dict, spoke_root: str, dry_run: bool) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    deltas = result["deltas"]
    website_lug = build_website_delta_lug(deltas, result["baseline_version"], result["current_version"], now_iso)
    mesh_lugs = [
        build_mesh_review_lug(m, result["current_version"], now_iso, i)
        for i, m in enumerate(deltas["mesh_mismatches"], start=1)
    ]

    if dry_run:
        return {"website_lug": website_lug, "mesh_lugs": mesh_lugs, "written": False}

    website_incoming = Path(WEBSITE_SPOKE_ROOT) / "WAI-Harness" / "spoke" / "local" / "lugs" / "incoming"
    website_incoming.mkdir(parents=True, exist_ok=True)
    (website_incoming / f"{website_lug['id']}.json").write_text(json.dumps(website_lug, indent=2))

    outgoing = _own_lugs_outgoing(spoke_root)
    outgoing.mkdir(parents=True, exist_ok=True)
    (outgoing / f"{website_lug['id']}.json").write_text(json.dumps(website_lug, indent=2))

    incoming = _own_lugs_incoming(spoke_root)
    incoming.mkdir(parents=True, exist_ok=True)
    for lug in mesh_lugs:
        (incoming / f"{lug['id']}.json").write_text(json.dumps(lug, indent=2))

    return {"website_lug": website_lug, "mesh_lugs": mesh_lugs, "written": True}


def update_state(spoke_root: str, result: dict, submitted: dict, run_id: str, duration_s: float, dry_run: bool) -> None:
    if dry_run:
        return
    deltas = result["deltas"]
    state_path = _state_file(spoke_root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()
    state = _load_json(state_path)
    state.update({
        "advisor_id": ADVISOR_ID,
        "last_processed_version": result["current_version"],
        "last_processed_audit": result["current_audit"],
        "closed_since": deltas["closed_since"],
        "long_running_announced": deltas["long_running_announced"],
        "last_run_at": now_iso,
        "last_run_id": run_id,
        "status": "active",
    })
    state_path.write_text(json.dumps(state, indent=2))

    runs_path = _runs_file(spoke_root)
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    with open(runs_path, "a") as f:
        f.write(json.dumps({
            "run_id": run_id,
            "run_at": now_iso,
            "duration_s": round(duration_s, 2),
            "baseline_version": result["baseline_version"],
            "current_version": result["current_version"],
            "website_lug_id": submitted["website_lug"]["id"],
            "mesh_lugs_count": len(submitted["mesh_lugs"]),
        }) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Release-storyteller advisor")
    parser.add_argument("--json", dest="json_output", action="store_true")
    parser.add_argument("--submit-lugs", action="store_true",
                         help="Write the story-delta lug to the website + mesh-check lugs locally")
    parser.add_argument("--dry-run", action="store_true", help="Compute and print without writing anything")
    parser.add_argument("--force", action="store_true",
                         help="Bypass the freshness/novelty gate (testing only)")
    parser.add_argument("--simulate-delta", action="store_true",
                         help="Diff two explicit audit snapshots instead of live state")
    parser.add_argument("--baseline", help="Path to the baseline circle-audit json (--simulate-delta)")
    parser.add_argument("--current", help="Path to the current circle-audit json (--simulate-delta)")
    args = parser.parse_args()

    run_id = f"{ADVISOR_ID}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    t0 = time.time()

    if args.simulate_delta:
        if not args.baseline or not args.current:
            print("--simulate-delta requires --baseline and --current", file=sys.stderr)
            sys.exit(2)
        baseline = _load_json(Path(args.baseline))
        current = _load_json(Path(args.current))
        own_state = _load_json(_state_file(SPOKE_ROOT)) if not args.force else {}
        now = datetime.now(timezone.utc)
        deltas = compute_deltas(baseline, current, own_state, now)
        result = {
            "fired": True,
            "baseline_version": baseline.get("harness_version", "unknown"),
            "current_version": current.get("harness_version", "unknown"),
            "deltas": deltas,
            "current_audit": current,
        }
    else:
        result = detect_and_run(SPOKE_ROOT, force_process=args.force)

    if not result["fired"]:
        if args.json_output:
            print(json.dumps(result, indent=2))
        else:
            print(f"release-storyteller: no run ({result['reason']})")
        return

    dry_run = args.dry_run or not args.submit_lugs
    submitted = submit(result, SPOKE_ROOT, dry_run=dry_run)
    update_state(SPOKE_ROOT, result, submitted, run_id, time.time() - t0, dry_run=dry_run)

    if args.json_output:
        print(json.dumps({
            "run_id": run_id,
            "fired": True,
            "baseline_version": result["baseline_version"],
            "current_version": result["current_version"],
            "deltas": result["deltas"],
            "website_lug": submitted["website_lug"],
            "mesh_lugs": submitted["mesh_lugs"],
            "written": submitted["written"],
        }, indent=2))
    else:
        d = result["deltas"]
        print(f"release-storyteller run: {run_id}")
        print(f"{result['baseline_version']} -> {result['current_version']}")
        print(f"new_evolution_circles={len(d['new_evolution_circles'])} "
              f"new_hard_finding_kinds={len(d['new_hard_finding_kinds'])} "
              f"long_running_circles={len(d['long_running_circles'])} "
              f"mesh_mismatches={len(d['mesh_mismatches'])}")
        print(f"written={submitted['written']}")


if __name__ == "__main__":
    main()
