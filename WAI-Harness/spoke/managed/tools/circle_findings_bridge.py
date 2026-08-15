#!/usr/bin/env python3
"""circle_findings_bridge.py — turns circle_audit hard findings into AP-executable lugs.

circle_audit.py is a read-only oracle (detection). autopilot only ever walks
lugs/bytype/ (execution). Nothing connected the two: a hard finding sat in
circle-audit-latest.json until a live session noticed it. This bridge is that
connection — the last leg of detection -> work -> execution -> verification.

Contract (operator-ratified, epic-circle-audit / impl-circle-findings-to-lugs-bridge-v1):
  - Only HARD findings mint lugs (the same six kinds circle_audit.py counts toward
    its BROKEN verdict). Exempt findings never mint — an exemption is a recorded
    disposition, not noise to re-surface as work.
  - Idempotent: a stable key per (kind, normalized target) is stamped on the lug as
    `_finding_key`. A finding whose key already has an open/in_progress/completed
    lug mints nothing. A finding that disappears while its lug is still open gets
    `self_resolved: true` stamped on it instead of deletion — groom closes it.
  - Kinds that remediate by touching live `.claude/` or `~/.claude/` NEVER get a
    lug whose execute steps mutate that surface directly — the agent classifier
    correctly blocks that, and working around it would be wrong even if it didn't.
    Those lugs stage the fix and append to the apply-script pattern proven in s138
    (WAI-Harness/spoke/local/maintenance/circle-audit/apply-live-enforcement-reconcile.sh),
    and are stamped `blocked_by_operator_apply: true`.
  - UNMERGED_LANE is the one hard kind that resolves with a git operation, not a
    live-.claude edit, so it is NOT operator-gated — it mints a track-review-then-
    merge-if-safe lug per the safety triple: lane provably dead, worktree clean on
    main, MANIFEST conflicts resolved by rebuild. Any leg failing means the lug's
    own execute step is "send a cooperative converge signal and report", not force-merge.

Usage:
    circle_findings_bridge.py [--root PATH] [--report PATH] [--dry-run] [--json]
Exit: 0 always (informational tool); non-zero only on a genuine I/O/parse failure.
"""
import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

HARD_KINDS = {
    "BOUND_MISSING", "UNKNOWN_OWNERSHIP", "MANAGED_DRIFT",
    "DECLARED_NOT_INSTALLED", "INSTALLED_UNBOUND", "UNMERGED_LANE",
}

# Kinds whose remediation touches live .claude/ or ~/.claude/ enforcement surface —
# these NEVER get direct-mutation execute steps, only stage-and-apply-script ones.
LIVE_GATED_KINDS = {
    "BOUND_MISSING", "UNKNOWN_OWNERSHIP", "MANAGED_DRIFT",
    "DECLARED_NOT_INSTALLED", "INSTALLED_UNBOUND",
}

APPLY_SCRIPT = "WAI-Harness/spoke/local/maintenance/circle-audit/apply-live-enforcement-reconcile.sh"

_TARGET_PATTERNS = {
    "BOUND_MISSING": re.compile(r"->\s*(\S+)\s+does not exist"),
    "UNKNOWN_OWNERSHIP": re.compile(r"^(\S+)\s+live but absent"),
    "MANAGED_DRIFT": re.compile(r"^(\S+)\s+md5 differs"),
    "DECLARED_NOT_INSTALLED": re.compile(r"^(\S+)\s+in MANIFEST"),
    "INSTALLED_UNBOUND": re.compile(r"^(\S+)\s+—"),
    "UNMERGED_LANE": re.compile(r"^branch\s+(\S+)\s+unmerged"),
}


def _load_json(p):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return None


def normalize_target(kind, detail):
    """Extract the stable identifying token (path or branch) from a finding detail."""
    pat = _TARGET_PATTERNS.get(kind)
    if pat:
        m = pat.search(detail)
        if m:
            return m.group(1)
    return " ".join(detail.split())[:120]


def finding_key(kind, detail):
    target = normalize_target(kind, detail)
    return hashlib.sha1(f"{kind}:{target}".encode()).hexdigest()[:16]


def hard_findings(report):
    return [
        f for f in (report.get("enforcement_findings") or [])
        if f.get("kind") in HARD_KINDS and not f.get("exempt")
    ]


def _iter_lug_files(root):
    lugs_dir = Path(root) / "WAI-Harness" / "spoke" / "local" / "lugs" / "bytype"
    if not lugs_dir.is_dir():
        return
    for p in lugs_dir.glob("*/*/*.json"):
        yield p


MINTED_BY = "circle_findings_bridge"


def existing_finding_keys(root):
    """Map finding_key -> list of lug file paths carrying it (any status).

    `_finding_key` is a generic field reused by other unrelated lug-generation
    systems in this repo (TASTE_GAP:, SUITE_RED:, etc.) — scope strictly to lugs
    this bridge itself minted (`_minted_by` == MINTED_BY), or idempotency checks
    and self-resolve annotation would collide with foreign keys.
    """
    out = {}
    for p in _iter_lug_files(root):
        data = _load_json(p)
        if not data or data.get("_minted_by") != MINTED_BY:
            continue
        key = data.get("_finding_key")
        if key:
            out.setdefault(key, []).append(p)
    return out


def _open_lugs_with_finding_keys(root):
    """Map finding_key -> lug file path, restricted to open/in_progress (self-resolve targets)."""
    out = {}
    for p in _iter_lug_files(root):
        if p.parent.name not in ("open", "in_progress", "needs_attention"):
            continue
        data = _load_json(p)
        if not data or data.get("_minted_by") != MINTED_BY:
            continue
        key = data.get("_finding_key")
        if key and not data.get("self_resolved"):
            out[key] = p
    return out


def _staging_execute_steps(kind, target):
    return [
        f"1. STAGE the fix for {target} under WAI-Harness/spoke/local/maintenance/circle-audit/ "
        f"(do not edit live .claude/ or ~/.claude/ directly — the agent classifier blocks it, correctly).",
        f"2. Append a reconciliation step to {APPLY_SCRIPT} (create it from the s138 template if absent) "
        f"that applies the staged {kind} fix for {target}.",
        "3. Mark this lug blocked_by_operator_apply: true and leave status open — "
        "the operator lands it with one `!` invocation of the apply script.",
    ]


def _unmerged_lane_execute_steps(target):
    return [
        f"1. Run a track review of branch {target}: divine what was in flight, what completed, "
        "what still should, per the wai-track-review template.",
        "2. Check the safety triple: (a) lane provably dead — no live lane registered AND tip age "
        "> threshold AND track silent; (b) main worktree clean and on main; (c) MANIFEST conflicts "
        "resolvable by manifest_build rebuild + VERSION takes the higher.",
        "3. If all three legs pass: merge-if-safe, recut MANIFEST, verify.",
        "4. If any leg fails: send a cooperative converge signal to the lane and report — never force-merge.",
    ]


def _verify_steps(kind, target):
    return [
        f"Re-run circle_audit.py --root . --write-latest and assert no un-exempt finding "
        f"with kind={kind} and target={target} remains.",
    ]


_TITLE = {
    "BOUND_MISSING": lambda t: f"Circle-audit: bind or remove dead handler binding at {t}",
    "UNKNOWN_OWNERSHIP": lambda t: f"Circle-audit: absorb {t} into MANIFEST or record an exemption",
    "MANAGED_DRIFT": lambda t: f"Circle-audit: reconcile drift between live {t} and MANIFEST",
    "DECLARED_NOT_INSTALLED": lambda t: f"Circle-audit: deploy or prune MANIFEST-declared {t}",
    "INSTALLED_UNBOUND": lambda t: f"Circle-audit: bind or remove unbound installed handler {t}",
    "UNMERGED_LANE": lambda t: f"Circle-audit: track-review and converge unmerged lane {t}",
}

_FILE_TARGETS = {
    "UNMERGED_LANE": lambda t: [
        "WAI-Harness/spoke/local/maintenance/circle-audit-latest.json",
    ],
}


def build_lug(finding, now_iso):
    kind, detail = finding["kind"], finding["detail"]
    target = normalize_target(kind, detail)
    key = finding_key(kind, detail)
    live_gated = kind in LIVE_GATED_KINDS

    if kind == "UNMERGED_LANE":
        execute = _unmerged_lane_execute_steps(target)
        file_targets = _FILE_TARGETS["UNMERGED_LANE"](target)
    else:
        execute = _staging_execute_steps(kind, target)
        file_targets = [APPLY_SCRIPT, "WAI-Harness/spoke/local/maintenance/circle-audit-latest.json"]

    title = _TITLE.get(kind, lambda t: f"Circle-audit: remediate {kind} at {t}")(target)

    lug = {
        "id": f"impl-circle-audit-{kind.lower().replace('_', '-')}-{key}-v1",
        "type": "implementation",
        "status": "open",
        "title": title,
        "created_at": now_iso,
        "routed_to": "LOCAL",
        "va": "build",
        "model_fit": "sonnet",
        "model_fit_reason": "Mechanical remediation of a named enforcement/lane finding; template-shaped, minimal judgment.",
        "effort": "S",
        "effort_score": 2,
        "impact": 6,
        "roi": 3.0,
        "execute_when": "any session or AP round; no dependencies",
        "perceive": [
            f"circle_audit.py hard finding: kind={kind}, detail={detail}",
            "Minted by circle_findings_bridge.py — the detection->work bridge that closes the "
            "gap between circle_audit's read-only oracle and autopilot's bytype/ walk.",
        ],
        "execute": execute,
        "verify": _verify_steps(kind, target),
        "acceptance_criteria": [
            f"circle_audit.py no longer reports this finding (kind={kind}, target={target}), "
            "or it is recorded as an exemption with a reason.",
        ],
        "file_targets": file_targets,
        "notes": "Auto-minted from a circle-audit hard finding. Do not hand-edit _finding_key.",
        "_finding_key": key,
        "_finding_kind": kind,
        "_finding_target": target,
        "_minted_by": "circle_findings_bridge",
        "_minted_at": now_iso,
    }
    if live_gated:
        lug["blocked_by_operator_apply"] = True
    return lug


def run(root, report_path=None, dry_run=False):
    root = str(Path(root).resolve())
    report_path = report_path or (Path(root) / "WAI-Harness" / "spoke" / "local" / "maintenance" / "circle-audit-latest.json")
    report = _load_json(report_path)
    if report is None:
        return {"error": f"cannot read report at {report_path}", "minted": [], "self_resolved": [], "skipped": []}

    findings = hard_findings(report)
    current_keys = {finding_key(f["kind"], f["detail"]) for f in findings}
    existing = existing_finding_keys(root)

    minted, skipped = [], []
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out_dir = Path(root) / "WAI-Harness" / "spoke" / "local" / "lugs" / "bytype" / "implementation" / "open"

    for f in findings:
        key = finding_key(f["kind"], f["detail"])
        if key in existing:
            skipped.append({"kind": f["kind"], "_finding_key": key, "existing_lug": str(existing[key][0])})
            continue
        lug = build_lug(f, now_iso)
        minted.append(lug)
        if not dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{lug['id']}.json").write_text(json.dumps(lug, indent=2) + "\n")

    self_resolved = []
    for key, path in _open_lugs_with_finding_keys(root).items():
        if key in current_keys:
            continue
        data = _load_json(path)
        if not data or data.get("self_resolved"):
            continue
        self_resolved.append({"_finding_key": key, "lug": str(path)})
        if not dry_run:
            data["self_resolved"] = True
            data["self_resolved_at"] = now_iso
            path.write_text(json.dumps(data, indent=2) + "\n")

    return {"minted": minted, "self_resolved": self_resolved, "skipped": skipped}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Bridge circle_audit hard findings into AP-executable lugs.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--report")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    result = run(args.root, report_path=args.report, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        if result.get("error"):
            print(f"circle_findings_bridge: {result['error']}", file=sys.stderr)
            return 1
        print(f"circle_findings_bridge: minted={len(result['minted'])} "
              f"self_resolved={len(result['self_resolved'])} skipped={len(result['skipped'])}")
        for m in result["minted"]:
            print(f"  + {m['id']}" + ("  [operator-gated]" if m.get("blocked_by_operator_apply") else ""))
        for s in result["self_resolved"]:
            print(f"  ~ self-resolved: {s['lug']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
