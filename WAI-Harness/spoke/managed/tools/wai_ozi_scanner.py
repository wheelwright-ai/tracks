#!/usr/bin/env python3
"""OziScanner — bytype filesystem scanning and work queue assembly."""

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from wai_ozi_config import OziConfig

# Lug leasing (optional -- graceful fallback if module absent). Same pattern as
# ozi_autopilot.py: a lug held under a live lease is being actively worked and
# must never be treated as unclaimed backlog by the scanner.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import lug_lease  # noqa: E402
    _LEASE_AVAILABLE = True
except ImportError:
    _LEASE_AVAILABLE = False


@dataclass
class AbandonedSession:
    """A session that exited with outstanding Ozi-eligible goals."""

    session_id: str
    goals: List[Dict[str, Any]]   # [{goal_id, description, requires_user_input}]
    ozi_eligible: bool
    stale_hours: float
    rewarm_hint: str
    initiative_id: str = ""
    track_path: str = ""


class OziScanner:
    """Scans bytype/ folders and assembles the work queue."""

    def __init__(self, config: OziConfig):
        self._config = config

    def _scan_bytype_folders(self, statuses: List[str]) -> List[Dict[str, Any]]:
        """Scan bytype/ folders for lugs matching given statuses."""
        results: List[Dict[str, Any]] = []
        bytype_dir = self._config.bytype_dir
        if not bytype_dir.exists():
            return results
        for type_dir in sorted(bytype_dir.iterdir()):
            if not type_dir.is_dir():
                continue
            for status_name in statuses:
                status_path = type_dir / status_name
                if not status_path.exists():
                    continue
                for lug_file in sorted(status_path.glob("*.json")):
                    try:
                        lug = json.loads(lug_file.read_text())
                        lug.setdefault("id", lug_file.stem)
                        lug.setdefault("type", type_dir.name)
                        lug["_file_path"] = str(lug_file)
                        lug["_fs_status"] = status_name
                        lug["_fs_type"] = type_dir.name
                        results.append(lug)
                    except (json.JSONDecodeError, OSError):
                        continue
        return results

    def _age_string(self, value: str) -> str:
        try:
            dt_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            delta = datetime.now(timezone.utc) - dt_value
        except ValueError:
            return "recently"
        minutes = max(0, int(delta.total_seconds() // 60))
        if minutes < 60:
            return f"{minutes}min ago"
        return f"{minutes // 60}hr ago"

    @staticmethod
    def _is_completion_marked(lug: Dict[str, Any]) -> bool:
        """True if the lug carries direct evidence of committed, completed work
        (commit_sha or completed_at) OR the ghost-lug audit_outcome/s marker.

        spec-lug-lifecycle-ownership-v1 RULE 3: a lug found ANYWHERE (open/ or
        in_progress/, any status field value) with a commit_sha but not in
        completed/ is a RECONCILE case, never a REWORK case -- the exact
        failure mode of the basher incident this closes (work committed, the
        lug artifact left claiming status:open)."""
        if lug.get("commit_sha") or lug.get("completed_at"):
            return True
        audit_outcome = lug.get("audit_outcome", "")
        lug_s = str(lug.get("s", lug.get("status", "")))
        return audit_outcome in ("shipped", "completed") or lug_s in ("c", "completed")

    def reconcile_completed_lug(self, lug: Dict[str, Any], reason: str = "") -> bool:
        """Stamp status:completed (+completed_at if missing) and move a
        mis-filed-but-done lug to completed/. Idempotent no-op if the source
        file is already gone (raced with another reconcile pass). Returns
        True iff the lug was moved."""
        file_path = lug.get("_file_path")
        if not file_path:
            return False
        src = Path(file_path)
        if not src.exists():
            return False

        type_dir = src.parent.parent
        completed_dir = type_dir / "completed"
        completed_dir.mkdir(parents=True, exist_ok=True)

        clean_lug = {k: v for k, v in lug.items() if not k.startswith("_")}
        clean_lug["status"] = "completed"
        clean_lug["s"] = "completed"
        clean_lug.setdefault(
            "completed_at", datetime.now(timezone.utc).isoformat()
        )
        clean_lug["close_reason"] = reason or "reconciled: completion marker present, lug was mis-filed"
        clean_lug["reconciled_at"] = datetime.now(timezone.utc).isoformat()

        dest = completed_dir / src.name
        dest.write_text(json.dumps(clean_lug, indent=2) + "\n")
        src.unlink()

        lug_id = lug.get("id", src.stem)
        print(f"[scanner] reconciled {lug_id} to completed/ ({clean_lug['close_reason']})")
        return True

    def _is_leased_elsewhere(self, lug_id: str) -> bool:
        """True iff a live lease exists for this lug (held by ANY session).

        RULE 1/3: a lug under a live lease is being actively worked -- the
        scanner must never surface it as fresh ready-backlog just because it
        is still sitting in open/ (e.g. a claim that hasn't yet moved the
        file). Fails open (False) if the lease module is unavailable."""
        if not _LEASE_AVAILABLE or not lug_id:
            return False
        try:
            return bool(lug_lease.held_by(lug_id))
        except Exception:
            return False

    def scan_work_queue(self) -> Dict[str, List[Dict[str, Any]]]:
        queue: Dict[str, List[Dict[str, Any]]] = {
            "ready": [],
            "claimed_by_me": [],
            "in_progress": [],
            "ready_for_recheck": [],
            "accepted": [],
            "needs_clarification": [],
            "stale": [],
            "completed_recently": [],
        }

        now = datetime.now(timezone.utc)
        owner_name = self._config.current_owner_name()
        all_lugs = self._scan_bytype_folders(["open", "in_progress"])

        for lug in all_lugs:
            # --- Completion-aware reconcile: a lug carrying completion evidence
            # (commit_sha/completed_at, or the ghost audit_outcome/s marker) is
            # DONE regardless of which status folder it's sitting in -- reconcile
            # it to completed/ instead of ever scoring/dispatching it as
            # backlog (spec-lug-lifecycle-ownership-v1 RULE 3). ---
            if lug.get("_fs_status") != "completed" and self._is_completion_marked(lug):
                self.reconcile_completed_lug(lug)
                continue  # skip — file moved to completed/

            status = lug.get("status", lug.get("s", lug.get("_fs_status", "open")))
            if status in ("o", "open"):
                status = "open"
            elif status in ("p", "in-progress", "in_progress"):
                status = "in_progress"

            workflow = lug.get("workflow", {})
            owner = workflow.get("current_owner")

            if status == "open":
                # RULE 1: a lug already under a live lease is being actively
                # worked (claim taken but the in_progress/ move hasn't landed
                # yet, or a status write raced this scan) -- never surface it
                # as fresh ready-backlog.
                if self._is_leased_elsewhere(lug.get("id", "")):
                    queue["in_progress"].append(lug)
                    continue
                queue["ready"].append(lug)
                continue

            if status == "in_progress":
                if owner == owner_name:
                    queue["claimed_by_me"].append(lug)
                updated_at = workflow.get("updated_at")
                if updated_at:
                    try:
                        updated_dt = datetime.fromisoformat(
                            updated_at.replace("Z", "+00:00")
                        )
                        if (now - updated_dt) > timedelta(hours=4):
                            queue["stale"].append(lug)
                        else:
                            queue["in_progress"].append(lug)
                    except ValueError:
                        queue["in_progress"].append(lug)
                else:
                    queue["in_progress"].append(lug)
                continue

            if status == "ready_for_recheck":
                queue["ready_for_recheck"].append(lug)
                continue

            if status == "needs_clarification":
                queue["needs_clarification"].append(lug)

        return queue

    def scan_abandoned_sessions(self) -> List[AbandonedSession]:
        """Return sessions that exited with Ozi-eligible outstanding goals.

        Eligible: session has session_exit_with_goals event OR last_ts > 4h ago
        AND at least one goal with requires_user_input=False still unresolved.
        """
        spoke_wai = Path(self._config.spoke_path)
        spoke_path = spoke_wai.parent
        sessions_dir = spoke_wai / "sessions"
        if not sessions_dir.exists():
            return []

        stale_threshold_hours = 4.0
        now = datetime.now(timezone.utc)
        results: List[AbandonedSession] = []

        for track_file in sorted(sessions_dir.glob("session-*/track.jsonl")):
            try:
                lines = track_file.read_text().splitlines()
            except OSError:
                continue

            goals_set: Dict[str, Any] = {}
            goals_done: set = set()
            has_exit_event = False
            initiative_id = ""
            last_ts: Optional[str] = None

            for raw in lines:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue

                ts = entry.get("ts", "")
                if ts:
                    last_ts = ts

                ev = entry.get("event", "")
                if ev == "goal_set":
                    gid = entry.get("goal_id", "")
                    if gid:
                        goals_set[gid] = entry
                elif ev == "goal_completed":
                    gid = entry.get("goal_id", "")
                    if gid:
                        goals_done.add(gid)
                elif ev == "session_exit_with_goals":
                    has_exit_event = True
                elif ev in ("savepoint", "session_start") and entry.get("initiative_id"):
                    initiative_id = entry["initiative_id"]

            outstanding = [goals_set[g] for g in goals_set if g not in goals_done]
            if not outstanding:
                continue

            stale_hours = 0.0
            if last_ts:
                try:
                    ts_dt = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                    stale_hours = (now - ts_dt).total_seconds() / 3600
                except Exception:
                    pass

            if not has_exit_event and stale_hours < stale_threshold_hours:
                continue

            # Only include sessions where ALL outstanding goals are Ozi-eligible
            needs_user = any(g.get("requires_user_input", False) for g in outstanding)
            if needs_user:
                continue

            # Generate rewarm hint
            rewarm = ""
            try:
                import sys as _sys
                _tools = str(spoke_path / "tools")
                if _tools not in _sys.path:
                    _sys.path.insert(0, _tools)
                from generate_wakeup_brief import generate_session_resume_brief  # type: ignore
                rewarm = generate_session_resume_brief(str(track_file.parent))
            except Exception:
                rewarm = f"Session {track_file.parent.name}: {len(outstanding)} goal(s) outstanding"

            results.append(
                AbandonedSession(
                    session_id=track_file.parent.name,
                    goals=[
                        {
                            "goal_id": g["goal_id"],
                            "description": g.get("description", ""),
                            "requires_user_input": g.get("requires_user_input", False),
                        }
                        for g in outstanding
                    ],
                    ozi_eligible=True,
                    stale_hours=stale_hours,
                    rewarm_hint=rewarm,
                    initiative_id=initiative_id,
                    track_path=str(track_file),
                )
            )

        results.sort(key=lambda s: -s.stale_hours)
        return results
