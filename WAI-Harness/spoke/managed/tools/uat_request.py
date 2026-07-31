#!/usr/bin/env python3
"""uat_request.py -- UAT-needed lug on autopilot completion (impl-exitclarity-5).

Operator directive (2026-07-08): "on completion a lug returned to the user that
UAT is needed is a good closeout action." uat_status was written 'pending' at
completion and never flipped -- this module is the populator.

Two entry points, both fully fail-safe (never raise into the caller's completion
path -- a UAT-emission bug must never brick a lug completion):

  emit_uat_request(lug, bytype_dir, ...) -> dict
      Called from the single completion choke-point (wai_ozi_dispatch.py
      update_lug_status(), status == "completed"). Default is EMIT; skips only
      on an explicit contract-routing.yaml `uat_request` skip-list match, and
      every skip is reason-coded (never silent). On emit, writes a companion
      review-type lug bytype/review/open/uat-<id>.json and mutates the passed
      `lug` dict in place (uat_status="awaiting_user") so the caller's own
      write of `lug` to disk persists both changes in one I/O op.

  apply_verdict(lug_id, verdict, reason, bytype_dir, ...) -> dict
      The uat-verdict verb (see uat_verdict.py). Flips uat_status to
      accepted/rejected on the original completed lug, closes the review lug,
      and on reject authors a fix lug carrying the rejection reason + the
      original evidence.

Query used by the wakeup ATTENTION section (impl-exitclarity-4, not yet built --
this is the data source it will call):

  list_awaiting_user(bytype_dir) -> list[dict]
"""
from __future__ import annotations

import fnmatch
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

_THIS_DIR = Path(__file__).resolve().parent
CONTRACT_ROUTING_YAML = _THIS_DIR.parent / "config" / "contract-routing.yaml"

REVIEW_ID_PREFIX = "uat-"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_skip_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """Read the `uat_request` skip-list section of contract-routing.yaml (DATA,
    human-editable, never a Python literal). Missing file/section -> {} (default
    EMIT everything)."""
    p = Path(path) if path else CONTRACT_ROUTING_YAML
    try:
        with open(p) as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data.get("uat_request", {}) or {}


def classify_skip(lug: Dict[str, Any], skip_cfg: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Return (skip, reason_code). Default is EMIT -- only an explicit skip-list
    match (type / lug id / tag / category / id glob) causes a skip, and the
    reason_code always names which rule matched."""
    lug_type = lug.get("type") or lug.get("_fs_type") or ""
    lug_id = lug.get("id") or ""
    tags = set(lug.get("tags") or [])
    category = lug.get("category")

    skip_types = set(skip_cfg.get("skip_types") or [])
    skip_ids = set(skip_cfg.get("skip_lug_ids") or [])
    skip_tags = set(skip_cfg.get("skip_tags") or [])
    skip_categories = set(skip_cfg.get("skip_categories") or [])
    skip_id_globs = skip_cfg.get("skip_id_globs") or []

    if lug_type in skip_types:
        return True, f"skip_list_type:{lug_type}"
    if lug_id in skip_ids:
        return True, f"skip_list_id:{lug_id}"
    matched_tags = tags & skip_tags
    if matched_tags:
        return True, f"skip_list_tag:{sorted(matched_tags)[0]}"
    if category and category in skip_categories:
        return True, f"skip_list_category:{category}"
    for g in skip_id_globs:
        if fnmatch.fnmatch(lug_id, g):
            return True, f"skip_list_id_glob:{g}"
    return False, None


def _find_lug_file(bytype_dir: Path, lug_id: str, lug_type: Optional[str] = None) -> Optional[Path]:
    bytype_dir = Path(bytype_dir)
    if lug_type:
        for status in ("completed", "in_progress", "open", "needs_attention"):
            cand = bytype_dir / lug_type / status / f"{lug_id}.json"
            if cand.exists():
                return cand
    if not bytype_dir.exists():
        return None
    for type_dir in bytype_dir.iterdir():
        if not type_dir.is_dir():
            continue
        for status_dir in type_dir.iterdir():
            if not status_dir.is_dir():
                continue
            cand = status_dir / f"{lug_id}.json"
            if cand.exists():
                return cand
    return None


def _how_to_test(lug: Dict[str, Any]) -> List[str]:
    verify = lug.get("verify") or []
    if isinstance(verify, list) and verify:
        return [str(v) for v in verify]
    if isinstance(verify, str) and verify.strip():
        return [verify.strip()]
    return [
        "No explicit verify[] steps on the source lug -- exercise the "
        "acceptance_criteria below directly."
    ]


def build_review_lug(
    lug: Dict[str, Any], evidence: Dict[str, Any], now_iso: Optional[str] = None
) -> Dict[str, Any]:
    """Fixed-template generated artifact -- improvement lenses are NOT required
    (per this lug's execute[] contract: it is generated, not authored)."""
    now_iso = now_iso or _now_iso()
    lug_id = lug.get("id", "unknown")
    review_id = f"{REVIEW_ID_PREFIX}{lug_id}"
    lug_type = lug.get("type") or lug.get("_fs_type") or "unknown"
    title = lug.get("title") or lug.get("t") or lug_id
    what_changed = (
        lug.get("one_liner") or lug.get("summary") or lug.get("description") or title
    ).strip()

    return {
        "id": review_id,
        "type": "review",
        "status": "open",
        "routed_to": "LOCAL",
        "owner": "operator",
        "scope": lug.get("scope", "SPOKE"),
        "initiative_id": lug.get("initiative_id"),
        "created_at": now_iso,
        "authored_by": "ozi-autopilot (impl-exitclarity-5-uat-request-on-completion-v1, generated)",
        "title": f"UAT NEEDED: {title}",
        "one_liner": (
            f"Autopilot completed {lug_type} {lug_id} -- operator verdict "
            "needed before it counts as delivered."
        ),
        "uat_request": {
            "completed_lug_id": lug_id,
            "completed_lug_type": lug_type,
            "what_changed": what_changed,
            "evidence": evidence,
            "how_to_test": _how_to_test(lug),
            "verdict_contract": {
                "accept": f"uat_verdict.py {lug_id} accept   -> uat_status=accepted",
                "reject": (
                    f"uat_verdict.py {lug_id} reject '<reason>'   -> "
                    "uat_status=rejected + a fix lug is authored from <reason>"
                ),
            },
        },
        "urgency": 2,
        "impact": lug.get("impact", 5),
        "effort": "XS",
        "effort_score": 1,
        "model_fit": "operator",
        "execute_when": "operator attention (wakeup ATTENTION once impl-exitclarity-4 lands)",
        "acceptance_criteria": ["operator has run uat_verdict.py with accept or reject"],
        "execution_mode": "operator",
        "disposition": "review",
        "disposition_reason": "generated UAT request -- operator verdict needed (impl-exitclarity-5)",
    }


def _append_activity_transition(activity_log: Optional[Path], entry: Dict[str, Any]) -> None:
    if not activity_log:
        return
    try:
        activity_log = Path(activity_log)
        activity_log.parent.mkdir(parents=True, exist_ok=True)
        with open(activity_log, "a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # activity-log write failures must never break the completion path


def emit_uat_request(
    lug: Dict[str, Any],
    bytype_dir: Path,
    evidence: Optional[Dict[str, Any]] = None,
    skip_config_path: Optional[Path] = None,
    activity_log: Optional[Path] = None,
    now_iso: Optional[str] = None,
) -> Dict[str, Any]:
    """Called at the autopilot completion choke-point. Mutates `lug` in place
    (uat_status + uat_review_lug_id) when emitted, so the caller's own write of
    `lug` to disk persists the transition in the same I/O op it was already
    doing.

    Returns {"emitted": bool, "skipped": bool, "reason_code": str|None,
             "review_lug_id": str|None, "review_lug_path": str|None}.
    """
    bytype_dir = Path(bytype_dir)
    now_iso = now_iso or _now_iso()
    lug_id = lug.get("id", "unknown")

    skip_cfg = _load_skip_config(skip_config_path)
    skip, reason_code = classify_skip(lug, skip_cfg)

    if skip:
        _append_activity_transition(
            activity_log,
            {
                "event": "uat_emission_skipped",
                "ts": now_iso,
                "lug_id": lug_id,
                "reason_code": reason_code,
            },
        )
        return {
            "emitted": False,
            "skipped": True,
            "reason_code": reason_code,
            "review_lug_id": None,
            "review_lug_path": None,
        }

    review_lug = build_review_lug(lug, dict(evidence or {}), now_iso)
    review_dir = bytype_dir / "review" / "open"
    review_dir.mkdir(parents=True, exist_ok=True)
    review_path = review_dir / f"{review_lug['id']}.json"
    review_path.write_text(json.dumps(review_lug, indent=2) + "\n")

    lug["uat_status"] = "awaiting_user"
    lug["uat_review_lug_id"] = review_lug["id"]

    _append_activity_transition(
        activity_log,
        {
            "event": "uat_status_transition",
            "ts": now_iso,
            "lug_id": lug_id,
            "from": "pending",
            "to": "awaiting_user",
            "review_lug_id": review_lug["id"],
        },
    )

    return {
        "emitted": True,
        "skipped": False,
        "reason_code": None,
        "review_lug_id": review_lug["id"],
        "review_lug_path": str(review_path),
    }


def list_awaiting_user(bytype_dir: Path) -> List[Dict[str, Any]]:
    """Query consumed by the wakeup ATTENTION section (impl-exitclarity-4): every
    open review-type lug generated by emit_uat_request is, by construction, an
    awaiting_user item -- no separate index to keep in sync."""
    bytype_dir = Path(bytype_dir)
    review_open = bytype_dir / "review" / "open"
    if not review_open.exists():
        return []
    items = []
    for f in sorted(review_open.glob(f"{REVIEW_ID_PREFIX}*.json")):
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        req = data.get("uat_request", {}) or {}
        items.append(
            {
                "review_lug_id": data.get("id"),
                "completed_lug_id": req.get("completed_lug_id"),
                "title": data.get("title"),
                "created_at": data.get("created_at"),
                "verdict_contract": req.get("verdict_contract"),
            }
        )
    return items


def apply_verdict(
    lug_id: str,
    verdict: str,
    reason: str,
    bytype_dir: Path,
    activity_log: Optional[Path] = None,
    now_iso: Optional[str] = None,
) -> Dict[str, Any]:
    """The uat-verdict verb: uat_verdict.py <lug-id> accept|reject '<reason>'."""
    if verdict not in ("accept", "reject"):
        return {"ok": False, "error": f"verdict must be accept|reject, got {verdict!r}"}

    bytype_dir = Path(bytype_dir)
    now_iso = now_iso or _now_iso()
    review_id = f"{REVIEW_ID_PREFIX}{lug_id}"

    review_path = None
    for status in ("open", "in_progress"):
        cand = bytype_dir / "review" / status / f"{review_id}.json"
        if cand.exists():
            review_path = cand
            break
    if review_path is None:
        return {"ok": False, "error": f"no open UAT review lug found for {lug_id} ({review_id})"}

    try:
        review_lug = json.loads(review_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "error": f"could not read {review_path}: {exc}"}

    req = review_lug.setdefault("uat_request", {})
    completed_lug_type = req.get("completed_lug_type")
    completed_path = _find_lug_file(bytype_dir, lug_id, completed_lug_type)

    new_uat_status = "accepted" if verdict == "accept" else "rejected"
    completed_updated = False
    if completed_path is not None:
        try:
            completed_lug = json.loads(completed_path.read_text())
            completed_lug["uat_status"] = new_uat_status
            completed_lug["uat_verdict_at"] = now_iso
            if reason:
                completed_lug["uat_verdict_reason"] = reason
            completed_path.write_text(json.dumps(completed_lug, indent=2) + "\n")
            completed_updated = True
        except (json.JSONDecodeError, OSError):
            completed_updated = False

    fix_lug_id = None
    if verdict == "reject":
        fix_lug_id = f"fix-{lug_id}-uat-reject-v1"
        fix_dir = bytype_dir / "fix" / "open"
        fix_dir.mkdir(parents=True, exist_ok=True)
        fix_path = fix_dir / f"{fix_lug_id}.json"
        suffix = 2
        while fix_path.exists():
            fix_lug_id = f"fix-{lug_id}-uat-reject-v{suffix}"
            fix_path = fix_dir / f"{fix_lug_id}.json"
            suffix += 1
        fix_lug = {
            "id": fix_lug_id,
            "type": "fix",
            "status": "open",
            "routed_to": "LOCAL",
            "owner": "mywheel-master",
            "scope": review_lug.get("scope", "SPOKE"),
            "initiative_id": review_lug.get("initiative_id"),
            "created_at": now_iso,
            "authored_by": "uat_verdict.py (impl-exitclarity-5, operator rejection)",
            "title": f"UAT rejected: {req.get('completed_lug_id', lug_id)} -- {reason or 'no reason given'}"[:200],
            "one_liner": f"Operator rejected {lug_id} at UAT: {reason or 'no reason given'}",
            "summary": (
                f"Autopilot completion {lug_id} was rejected at UAT.\n"
                f"Rejection reason: {reason or '(none given)'}\n"
                f"Original what-changed: {req.get('what_changed', '')}\n"
                f"Original evidence: {json.dumps(req.get('evidence', {}))}\n"
                f"How it was meant to be tested: {req.get('how_to_test', [])}"
            ),
            "urgency": 3,
            "impact": review_lug.get("impact", 5),
            "effort": "S",
            "effort_score": 2,
            "model_fit": "sonnet",
            "execute_when": "blocked_by cleared",
            "blocked_by": [],
            "perceive": [f"Re-read the original lug/commits for {lug_id} and the operator's rejection reason above."],
            "execute": [f"Address the rejection reason for {lug_id}."],
            "verify": ["Re-run the original lug's verify[] steps; re-submit for UAT."],
            "acceptance_criteria": [f"Rejection reason for {lug_id} addressed."],
            "target_files": [],
            "file_targets": [],
            "reopens": lug_id,
            "uat_reject_reason": reason,
        }
        fix_path.write_text(json.dumps(fix_lug, indent=2) + "\n")

    review_lug["status"] = "completed"
    req["verdict"] = verdict
    req["verdict_reason"] = reason
    req["verdict_at"] = now_iso
    if fix_lug_id:
        req["fix_lug_id"] = fix_lug_id

    completed_review_dir = bytype_dir / "review" / "completed"
    completed_review_dir.mkdir(parents=True, exist_ok=True)
    (completed_review_dir / review_path.name).write_text(json.dumps(review_lug, indent=2) + "\n")
    try:
        review_path.unlink()
    except OSError:
        pass

    _append_activity_transition(
        activity_log,
        {
            "event": "uat_verdict",
            "ts": now_iso,
            "lug_id": lug_id,
            "verdict": verdict,
            "uat_status": new_uat_status,
            "reason": reason,
            "fix_lug_id": fix_lug_id,
            "completed_lug_updated": completed_updated,
        },
    )

    return {
        "ok": True,
        "lug_id": lug_id,
        "uat_status": new_uat_status,
        "completed_lug_updated": completed_updated,
        "fix_lug_id": fix_lug_id,
    }
