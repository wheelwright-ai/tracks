#!/usr/bin/env python3
"""realized_outcome_join.py -- the read-time join from predicted (C8) to realized outcome.

C8 (impl-spine-c8-predicted-vs-realized-join-v1, completed) persists predicted_roi,
urgency_tier, and sort_rank onto a dispatched lug's JSON + its activity-log.jsonl
entry at the moment ozi_autopilot.py's _sort_key computes them. This module does NOT
re-specify that persistence step -- it consumes it. It defines what "realized" means
per plan-conductor-roi-safety-v1.md section 1.2 and answers "did dispatching this lug
actually help," once its lag window has elapsed.

READ-ONLY against dispatch: this module never writes to a lug, activity-log.jsonl,
_sort_key, or any dispatch-order-affecting code. It produces a report/query only,
consumed later by impl-roi-safety-2 (retargeting).

realized_score per dispatched lug (plan-conductor-roi-safety-v1.md:96-98):
  1.0  completed, no rework detected (signals 1-2 both clean)
  0.5  completed but inside a churn-flagged window (signal 2 fired, unresolved)
  0.0  reworked (signal 1 fired) or never completed
  None a lug younger than the lag window -- "not yet measurable," never silently
       folded into 0.0 or 1.0 (plan-conductor-roi-safety-v1.md:116-118)

Signal 1 -- rework/reopen (NEW, defined here; no such metric existed anywhere in the
codebase before this packet): a lug is "reworked" if, within the lag window after its
completed activity-log entry, a NEW lug appears whose blocked_by/supersedes/summary/
one_liner references the original lug's id as something it fixes/reopens/redoes.

Signal 2 -- work_impact.py churn overlap (real, live, reused as-is): a corroborating,
range-level signal. It lowers confidence (1.0 -> 0.5) but never substitutes for
signal 1, and it never turns a reworked lug's 0.0 back up.

Cadence (plan-conductor-roi-safety-v1.md:109-118): the conductor cron fires every 5h.
This design reuses plan-mandates-spine-v1.md's D2 soak-window precedent verbatim:
minimum 3 conductor cycles (~15h) before a dispatched lug's realized_score is
considered trustworthy. Lugs younger than that are excluded, not defaulted.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

CYCLE_HOURS = 5
LAG_WINDOW_CYCLES = 3
LAG_WINDOW = timedelta(hours=CYCLE_HOURS * LAG_WINDOW_CYCLES)  # ~15h

# work_impact.py's own churn-signal shape (work_impact.py:216-221): reused as-is.
CHURN_WORK_TYPES = ("advisor", "session", "state")
CHURN_SHARE_PCT_THRESHOLD = 30.0

_SCAN_STATUSES = ("open", "completed")


def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def default_bytype_dir(spoke_root: str = ".") -> Path:
    """WAI-Harness/spoke/local/lugs/bytype under spoke_root. No fallback guessing --
    callers that need real-repo behavior pass this in explicitly; tests always pass
    their own tmp_path-rooted bytype_dir instead of relying on this default."""
    return Path(spoke_root).resolve() / "WAI-Harness" / "spoke" / "local" / "lugs" / "bytype"


def iter_lug_files(bytype_dir: Path, statuses: Iterable[str] = _SCAN_STATUSES) -> Iterable[Path]:
    """Yield every lug JSON under bytype_dir/*/{open,completed} (per this packet's
    execute[] step 1 -- deliberately not in_progress/needs_attention/etc.)."""
    bytype_dir = Path(bytype_dir)
    if not bytype_dir.is_dir():
        return
    for type_dir in sorted(bytype_dir.iterdir()):
        if not type_dir.is_dir():
            continue
        for status in statuses:
            status_dir = type_dir / status
            if not status_dir.is_dir():
                continue
            for f in sorted(status_dir.glob("*.json")):
                yield f


def _load_lug(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _references(candidate: Dict[str, Any], lug_id: str) -> bool:
    """True if candidate's blocked_by/supersedes/summary/one_liner references lug_id."""
    blocked_by = candidate.get("blocked_by") or []
    if isinstance(blocked_by, str):
        blocked_by = [blocked_by]
    if lug_id in blocked_by:
        return True

    supersedes = candidate.get("supersedes") or []
    if isinstance(supersedes, str):
        supersedes = [supersedes]
    if lug_id in supersedes:
        return True

    pattern = re.compile(re.escape(lug_id))
    for field in ("summary", "one_liner"):
        text = candidate.get(field)
        if isinstance(text, str) and pattern.search(text):
            return True
    return False


def rework_detected(
    lug_id: str,
    bytype_dir: Path,
    completed_at: datetime,
    lag_window_cycles: int = LAG_WINDOW_CYCLES,
) -> bool:
    """A lug is reworked if a NEW lug (created_at within the lag window after
    completed_at) references lug_id as something it fixes/reopens/redoes."""
    window = timedelta(hours=CYCLE_HOURS * lag_window_cycles)
    window_end = completed_at + window
    for path in iter_lug_files(bytype_dir):
        candidate = _load_lug(path)
        if not candidate or candidate.get("id") == lug_id:
            continue
        created_at = _parse_ts(candidate.get("created_at"))
        if created_at is None or not (completed_at < created_at <= window_end):
            continue
        if _references(candidate, lug_id):
            return True
    return False


def _churn_flagged(work_impact_report: Optional[Dict[str, Any]]) -> bool:
    """True if work_impact.py's own churn signal fired for this window
    (share_pct >= 30% in advisor/session/state work-types, work_impact.py:216-221).
    Reused as-is -- not redefined."""
    if not work_impact_report:
        return False
    by_type = work_impact_report.get("by_work_type") or {}
    for wt in CHURN_WORK_TYPES:
        bucket = by_type.get(wt) or {}
        if bucket.get("share_pct", 0) >= CHURN_SHARE_PCT_THRESHOLD:
            return True
    return False


def realized_score(
    entry: Dict[str, Any],
    bytype_dir: Path,
    work_impact_report: Optional[Dict[str, Any]] = None,
    lag_window_cycles: int = LAG_WINDOW_CYCLES,
    now: Optional[datetime] = None,
) -> Optional[float]:
    """realized_score for one dispatched lug's activity-log entry (needs lug_id, ts,
    outcome). Returns None ("not yet measurable") if younger than the lag window."""
    lug_id = entry.get("lug_id")
    ts = _parse_ts(entry.get("ts"))
    if not lug_id or ts is None:
        return None

    if entry.get("outcome") != "completed":
        return 0.0

    window = timedelta(hours=CYCLE_HOURS * lag_window_cycles)
    if _now(now) - ts < window:
        return None

    if rework_detected(lug_id, bytype_dir, ts, lag_window_cycles=lag_window_cycles):
        return 0.0
    if _churn_flagged(work_impact_report):
        return 0.5
    return 1.0


def _normalize_predicted_roi(value: Any) -> Optional[float]:
    """predicted_roi is observed on a 0-10-ish scale (occasional >10 outliers) with no
    codebase-defined normalization function to reuse. Judgment call (flagged, not
    silently assumed): clamp(roi / 10.0, 0.0, 1.0) so it's comparable to realized_score's
    0.0-1.0 range. A future packet that formalizes ROI scaling should update this."""
    if value is None:
        return None
    try:
        roi = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, roi / 10.0))


def load_activity_log(activity_log_path: Path) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    path = Path(activity_log_path)
    if not path.is_file():
        return entries
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def predicted_vs_realized_delta(
    entries: List[Dict[str, Any]],
    bytype_dir: Path,
    category_of,
    category: str,
    trailing_n_cycles: int,
    work_impact_report: Optional[Dict[str, Any]] = None,
    lag_window_cycles: int = LAG_WINDOW_CYCLES,
    now: Optional[datetime] = None,
) -> Optional[float]:
    """predicted-vs-realized delta for one (spoke-implicit-in-entries, category), over
    the trailing N cycles (plan-conductor-roi-safety-v1.md:100-107):
    mean(realized_score) - normalize(mean(predicted_roi)), excluding not-yet-measurable
    lugs from both means. `entries` is one spoke's activity-log.jsonl entries (already
    scoped to that spoke by the caller); `category_of(lug_id)` classifies each entry.
    Returns None if no entry in the window/category has a measurable realized_score."""
    now = _now(now)
    window = timedelta(hours=CYCLE_HOURS * trailing_n_cycles)
    cutoff = now - window

    realized_values: List[float] = []
    predicted_values: List[float] = []
    for entry in entries:
        lug_id = entry.get("lug_id")
        if not lug_id or category_of(lug_id) != category:
            continue
        ts = _parse_ts(entry.get("ts"))
        if ts is None or ts < cutoff:
            continue
        score = realized_score(
            entry, bytype_dir, work_impact_report=work_impact_report,
            lag_window_cycles=lag_window_cycles, now=now,
        )
        if score is None:
            continue  # not yet measurable -- excluded from both means, not defaulted
        predicted = _normalize_predicted_roi(entry.get("predicted_roi"))
        if predicted is None:
            continue
        realized_values.append(score)
        predicted_values.append(predicted)

    if not realized_values:
        return None

    mean_realized = sum(realized_values) / len(realized_values)
    mean_predicted = sum(predicted_values) / len(predicted_values)
    return mean_realized - mean_predicted


def category_from_lug_id(lug_id: str) -> str:
    """Category = the lug's type prefix (lug type or initiative), per
    plan-conductor-roi-safety-v1.md:101 ('category (lug type or initiative)')."""
    return lug_id.split("-", 1)[0] if lug_id else ""
