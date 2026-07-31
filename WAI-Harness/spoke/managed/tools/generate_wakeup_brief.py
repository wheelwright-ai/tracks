#!/usr/bin/env python3
"""Generate WAI-Spoke/wakeup-brief.json.

Run before launching an AI tool to guarantee the wakeup fast path.
The wakeup protocol (wai.md Step 7) checks git_sha_at_generation against
HEAD — if they match, it skips all tool calls and displays the brief in seconds.

Usage:
    python3 tools/generate_wakeup_brief.py [--spoke-path /absolute/path/to/spoke_root]
"""

import datetime
import glob
import json
import os
import subprocess
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spoke_integrity_score import hook_freshness_check

# Lug leasing (optional — graceful fallback if module absent)
try:
    import lug_lease
    _LEASE_AVAILABLE = True
except ImportError:
    _LEASE_AVAILABLE = False

# Initiative leasing (optional — graceful fallback if module absent)
try:
    import initiative_lease
    _INITIATIVE_LEASE_AVAILABLE = True
except ImportError:
    _INITIATIVE_LEASE_AVAILABLE = False

# Pattern Health (AC8) — optional; graceful fallback if the miner is absent
try:
    from historian_gate_mine import pattern_health as _pattern_health
    _PATTERN_HEALTH_AVAILABLE = True
except ImportError:
    _PATTERN_HEALTH_AVAILABLE = False

# Quality Health (AC30) — optional; coverage/certification over v4 lugs
try:
    from compute_coverage import read_coverage as _read_coverage
    _QUALITY_HEALTH_AVAILABLE = True
except ImportError:
    _QUALITY_HEALTH_AVAILABLE = False

# AC Drift (impl-derive-epic-ac-status-v1) — optional; epic AC checkbox vs lug
# evidence drift per open epic. Surfaced so under/over/mis-partial reporting is
# visible at session open instead of discovered by hand mid-session.
try:
    from reconcile_epic_acs import read_ac_drift as _read_ac_drift
    _AC_DRIFT_AVAILABLE = True
except ImportError:
    _AC_DRIFT_AVAILABLE = False

# QA suite health (impl-qa-stale-test-detection-v1) — optional; stale-test detection
# + the test-null/stale/failing gap taxonomy over v4 lugs (the freshness half the
# coverage compute does not surface).
try:
    from qa_suite_health import read_qa_health as _read_qa_health
    _QA_HEALTH_AVAILABLE = True
except ImportError:
    _QA_HEALTH_AVAILABLE = False


def collect_active_leases(spoke: "Path") -> list:
    """Return live lug leases for the wakeup brief (sweeps expired first)."""
    if not _LEASE_AVAILABLE:
        return []
    store = spoke / "runtime" / "claims-local.json"
    try:
        leases = lug_lease.active_leases(store_path=str(store))
    except Exception:
        return []
    return [
        {
            "lug_id": l["lug_id"],
            "held_by": l["held_by"],
            "expires_at": l["expires_at"],
        }
        for l in leases
    ]

def scan_session_goals(spoke: "Path") -> dict:
    """Scan session tracks for unresolved goal_set events.

    Returns {'user_required': [...], 'ozi_eligible': [...]} where each entry is:
    {session_id, initiative_id, goals: [{goal_id, description, requires_user_input}],
     last_active, ozi_eligible}
    """
    import time as _time
    from datetime import datetime as _dt, timezone as _tz
    sessions_dir = spoke / "sessions"
    result: dict = {"user_required": [], "ozi_eligible": []}
    if not sessions_dir.exists():
        return result
    cutoff_days = 30
    for track_file in sorted(sessions_dir.glob("session-*/track.jsonl"), reverse=True):
        try:
            lines = track_file.read_text().splitlines()
        except OSError:
            continue
        goals_set: dict = {}
        goals_done: set = set()
        last_ts: str = ""
        initiative_id: str = ""
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
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
            elif ev in ("savepoint", "session_start") and entry.get("initiative_id"):
                initiative_id = entry["initiative_id"]
        outstanding = [goals_set[g] for g in goals_set if g not in goals_done]
        if not outstanding:
            continue
        if last_ts:
            try:
                ts_dt = _dt.fromisoformat(last_ts.replace("Z", "+00:00"))
                age_days = (_dt.now(_tz.utc) - ts_dt).days
                if age_days > cutoff_days:
                    continue
            except Exception:
                pass
        session_id = track_file.parent.name
        needs_user = any(g.get("requires_user_input", False) for g in outstanding)
        entry_out = {
            "session_id": session_id,
            "initiative_id": initiative_id or None,
            "goals": [
                {
                    "goal_id": g["goal_id"],
                    "description": g.get("description", ""),
                    "requires_user_input": g.get("requires_user_input", False),
                }
                for g in outstanding
            ],
            "last_active": last_ts,
            "ozi_eligible": not needs_user,
        }
        if needs_user:
            result["user_required"].append(entry_out)
        else:
            result["ozi_eligible"].append(entry_out)
    return result


def generate_session_resume_brief(session_dir: "Path") -> str:
    """5-8 line rewarm brief for a session. Returns plain text."""
    session_dir = Path(session_dir)
    track_path = session_dir / "track.jsonl"
    if not track_path.exists():
        return f"Session {session_dir.name}: no track found."
    goals_set: dict = {}
    goals_done: set = set()
    turns: list = []
    initiative_id: str = ""
    open_items: list = []
    for raw in track_path.read_text().splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        ev = entry.get("event", "")
        if ev == "goal_set":
            gid = entry.get("goal_id", "")
            if gid:
                goals_set[gid] = entry
        elif ev == "goal_completed":
            gid = entry.get("goal_id", "")
            if gid:
                goals_done.add(gid)
        elif entry.get("turn"):
            turns.append(entry)
            open_items = entry.get("open", []) or []
        elif ev in ("savepoint", "session_start") and entry.get("initiative_id"):
            initiative_id = entry["initiative_id"]
    session_name = session_dir.name
    last_turns = turns[-3:] if turns else []
    outstanding = [(g, goals_set[g]) for g in goals_set if g not in goals_done]
    lines_out = [
        f"Session {session_name}"
        + (f" (initiative: {initiative_id})" if initiative_id else "")
    ]
    if outstanding:
        lines_out.append("Outstanding goals:")
        for _gid, grec in outstanding:
            ri = "  [needs you]" if grec.get("requires_user_input") else ""
            lines_out.append(f"  [ ] {grec.get('description', _gid)}{ri}")
    else:
        lines_out.append("Goals: all complete (or none set)")
    if last_turns:
        last = last_turns[-1]
        action_str = str(last.get("action", ""))[:120]
        lines_out.append(f"Last action (turn {last.get('turn', '?')}): {action_str}")
    if open_items:
        lines_out.append("Open items from last turn:")
        for item in open_items[:3]:
            lines_out.append(f"  - {item}")
    return "\n".join(lines_out)


def read_ask_landing(spoke, project_root):
    """W4, epic-close-the-presumption-gap-v1: did the thing he asked for land?

    Surfaces ONLY when an ask has STALLED. A wakeup line that appears every
    session stops being read within a week, so a clean audit is silent by
    design and `stalled` is 0 with no line.

    Producer failure must never break the brief -- an absent tool yields an
    empty dict, exactly like the other optional feeds here.
    """
    try:
        import ask_landing_audit
        rep = ask_landing_audit.audit(str(spoke), str(project_root))
        return {
            "counts": rep["counts"],
            "total": rep["total"],
            "stalled": rep["counts"].get("STALLED", 0),
            "line": ask_landing_audit.wakeup_line(rep),
            "stalled_asks": [
                {"id": e["id"], "verbatim": e.get("verbatim", "")[:200],
                 "age_days": e.get("age_days"), "why": e.get("why", "")}
                for e in rep.get("surface_at_wakeup", [])
            ],
        }
    except Exception:
        return {}


def build_continuation_menu(spoke: "Path") -> dict:
    """Populate continuation_menu for the wakeup brief.

    Returns {initiatives: [...], pending_savepoints: [...]} for finish-before-start prioritization.
    """
    try:
        initiatives_full: list = []
        initiatives_index = spoke / "initiatives" / "WAI-InitiativeIndex.jsonl"
        if initiatives_index.exists():
            try:
                for line in initiatives_index.read_text().strip().split('\n'):
                    if not line:
                        continue
                    ini = json.loads(line)
                    if ini.get("lifecycle_state") not in ("approved", "measuring"):
                        continue
                    initiatives_full.append(ini)
            except Exception:
                pass

        initiatives_full.sort(key=lambda x: (-int(x.get("focus_lock", False)), x.get("impact_rank", 99)))
        initiatives = [
            {
                "id": ini.get("id", ""),
                "label": ini.get("label", ini.get("id", "")),
                "lifecycle_state": ini.get("lifecycle_state", ""),
                "focus_lock": ini.get("focus_lock", False),
            }
            for ini in initiatives_full[:3]
        ]

        pending_savepoints: list = []
        sp_files = [
            f for f in glob.glob(str(spoke / "initiatives" / "savepoints" / "**" / "*.json"), recursive=True)
            if "completed" not in Path(f).parts
        ]
        sp_candidates = []
        for f in sp_files:
            try:
                savepoint_data = json.loads(Path(f).read_text())
                if savepoint_data.get("status") in ("pending", "active"):
                    sp_candidates.append((os.path.getmtime(f), savepoint_data))
            except Exception:
                continue
        sp_candidates.sort(key=lambda x: x[0], reverse=True)
        pending_savepoints = [data for _, data in sp_candidates[:3]]

        return {"initiatives": initiatives, "pending_savepoints": pending_savepoints}
    except Exception:
        return {"initiatives": [], "pending_savepoints": []}


PROJECT_DIR = Path(__file__).parent.parent
# Default to CWD if it's a WAI spoke

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wai_paths  # noqa: E402  harness-mode root resolver (single source of truth)

try:
    import compile_tastegraph  # noqa: E402  TasteGraph producer (best-effort; brief must never break on it)
except Exception:
    compile_tastegraph = None

# These are now determined after parsing args.
# SPOKE is the working BASE (v3: <root>/WAI-Spoke ; v4-only: <root>/WAI-Harness/spoke/local).
# PROJECT_ROOT is the spoke project dir that CONTAINS that base — it is NOT SPOKE.parent
# in v4 (where SPOKE.parent is .../WAI-Harness/spoke), so it is tracked explicitly.
SPOKE = None
PROJECT_ROOT = None
BYTYPE = None
STATE_FILE = None
BRIEF_FILE = None


def _project_root_for(spoke) -> Path:
    """Map a working BASE back to its spoke project root, layout-aware, so the
    coverage/drift/qa helpers stay self-contained (callable without main()):
      v3 base  <root>/WAI-Spoke               -> <root>
      v4 base  <root>/WAI-Harness/spoke/local -> <root>
    Falls back to the base itself if the layout is unrecognised."""
    sp = Path(spoke)
    if sp.name == "WAI-Spoke":
        return sp.parent
    if sp.parts[-3:] == ("WAI-Harness", "spoke", "local"):
        return sp.parents[2]
    return sp


_NON_WORK_TYPES = {"signal", "spec", "phone-home"}  # non-executable, excluded from "work" bucket

def count_open_lugs() -> dict:
    """Return lug counts broken down by bucket: total, epics, work_open, work_ip."""
    counts = {"total": 0, "epics": 0, "work_open": 0, "work_ip": 0}
    if not BYTYPE.exists():
        return counts
    for type_dir in BYTYPE.iterdir():
        if not type_dir.is_dir():
            continue
        t = type_dir.name.lower()
        for status in ("open", "in_progress"):
            status_dir = type_dir / status
            try:
                n = len(list(status_dir.glob("*.json")))
                if n == 0:
                    continue
                counts["total"] += n
                if t == "epic":
                    counts["epics"] += n
                elif t not in _NON_WORK_TYPES:
                    counts["work_open" if status == "open" else "work_ip"] += n
            except (FileNotFoundError, PermissionError):
                pass
    return counts


def run_score_backlog() -> tuple[dict, list, list]:
    """Run score_backlog.py --update-state, then read updated _work_queue from state.

    Returns (queue_snapshot, top_ready_lugs, stalled_lugs).
    """
    score_script = PROJECT_DIR / "tools" / "score_backlog.py"
    if not score_script.exists():
        return {"ready_count": 0, "needs_refinement_count": 0, "blocked_count": 0, "stalled_count": 0}, [], []

    # Ensure score_backlog uses the correct spoke_path if provided
    score_cmd = [sys.executable, str(score_script), "--update-state"]
    if PROJECT_ROOT:  # the project dir containing the active harness base
        score_cmd.extend(["--spoke-path", str(PROJECT_ROOT)])

    subprocess.run(
        score_cmd,
        cwd=str(PROJECT_DIR),
        capture_output=True,
        timeout=30,
    )

    # Reload state to get updated _work_queue
    try:
        state = json.loads(STATE_FILE.read_text())
        wq = state.get("_work_queue", {})
        queue_snapshot = wq.get(
            "queue_state",
            {"ready_count": 0, "needs_refinement_count": 0, "blocked_count": 0, "stalled_count": 0},
        )
        top_lugs = [
            {k: item[k] for k in ("id", "title", "roi") if k in item}
            for item in wq.get("items", [])[:5]
            if item.get("readiness") == "ready"
        ]
        stalled_lugs = [
            {
                "id": item["id"],
                "title": item.get("title", ""),
                "roi": item.get("roi"),
                "annotation": (
                    "no estimated_seconds — consider setting based on effort+model"
                    if not item.get("has_estimated_seconds")
                    else None
                ),
            }
            for item in wq.get("items", [])
            if item.get("readiness") == "stalled"
        ]
        return queue_snapshot, top_lugs, stalled_lugs
    except Exception:
        return {"ready_count": 0, "needs_refinement_count": 0, "blocked_count": 0, "stalled_count": 0}, [], []


def count_teachings_pending(hub_path: str, spoke: "Optional[Path]" = None) -> int:
    """Count unprocessed teachings from hub.

    Scans the same paths as session-start.sh (node-type-aware) PLUS the legacy
    framework/current/ directory, deduplicating by filename so neither source is missed.
    """
    if not hub_path:
        return 0
    hub = Path(hub_path).expanduser()
    processed_dir = (spoke if spoke else SPOKE) / "seed" / "ingest" / "processed"
    # Node-type-aware paths (mirrors session-start.sh logic)
    try:
        _state_file = (spoke if spoke else SPOKE) / "WAI-State.json"
        _node_type = json.loads(_state_file.read_text()).get("wheel", {}).get("node_type", "spoke")
    except Exception:
        _node_type = "spoke"
    if _node_type == "hub":
        scan_dirs = [hub / "teachings_repo" / "hub-only" / "current",
                     hub / "teachings_repo" / "cross_spoke" / "current"]
    else:
        scan_dirs = [hub / "teachings_repo" / "spoke" / "current",
                     hub / "teachings_repo" / "cross_spoke" / "current"]
    # Legacy path — keep scanning until hub is fully migrated
    scan_dirs.append(hub / "teachings_repo" / "framework" / "current")
    seen: set = set()
    count = 0
    for teach_dir in scan_dirs:
        if not teach_dir.exists():
            continue
        for f in teach_dir.glob("*.teaching"):
            if f.name in seen:
                continue
            seen.add(f.name)
            if not (processed_dir / f.name).exists():
                count += 1
    return count


def count_incoming_lugs(spoke: "Optional[Path]" = None) -> int:
    """Count unprocessed lugs in the spoke's lugs/incoming/ (excludes processed/ and completed/).

    `spoke` is the already-resolved working base (v3: <root>/WAI-Spoke, v4: <root>/WAI-Harness/spoke/local),
    so lugs/incoming below it is harness-mode-correct."""
    incoming = (spoke if spoke else SPOKE) / "lugs" / "incoming"
    if not incoming.exists():
        return 0
    skip_dirs = {incoming / "processed", incoming / "completed"}
    return sum(
        1 for f in incoming.glob("*.json")
        if f.is_file() and f.parent not in skip_dirs
    )


def count_hub_signals(hub_path: str) -> int:
    if not hub_path:
        return 0
    base = Path(hub_path).expanduser() / "WAI-Hub" / "signals" / "incoming"
    total = 0
    for subfolder in ("framework", "spokes"):
        sig_dir = base / subfolder
        if sig_dir.exists():
            total += len([f for f in sig_dir.glob("*.json") if f.name != ".gitkeep"])
    return total


def read_work_queue_matrix_counts(spoke: "Optional[Path]") -> dict:
    """Read work-queue.json from Expediter and return autopilot-ready vs needs-you totals."""
    if not spoke:
        return {}
    wq_path = spoke / "advisors" / "expediter" / "work-queue.json"
    if not wq_path.exists():
        return {}
    try:
        wq = json.loads(wq_path.read_text())
        totals = wq.get("totals", {})
        return {
            "autopilot_ready": totals.get("autonomous", 0),
            "needs_you": totals.get("attended", 0),
            "schema_version": wq.get("schema_version", ""),
        }
    except (OSError, json.JSONDecodeError):
        return {}


def read_pattern_health(spoke: "Optional[Path]") -> "Optional[dict]":
    """AC8: the wakeup Pattern Health section — first-attempt approval rate per
    flow, halt frequency per step, open-candidate count. Reads the gate-log +
    historian candidates and computes via historian_gate_mine.pattern_health().

    Degrades gracefully (returns None) if the miner is unavailable or there is no
    gate-log yet — never blocks brief generation. Carries a freshness marker so a
    stale/empty section self-flags rather than appearing authoritative."""
    if not spoke or not _PATTERN_HEALTH_AVAILABLE:
        return None
    gate_log = spoke / "patterns" / "gate-log.jsonl"
    if not gate_log.exists():
        return {"status": "no-gate-log-yet", "first_attempt_approval_rate": {},
                "halt_frequency_per_step": {}, "open_candidates": 0,
                "source": str(gate_log.relative_to(spoke.parent)) if spoke else ""}
    try:
        events = []
        for line in gate_log.read_text().splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
        cand_dir = spoke / "advisors" / "historian" / "patterns" / "candidates"
        candidates = sorted(cand_dir.glob("*.json")) if cand_dir.exists() else []
        health = _pattern_health(events, candidates, trigger_fired=False)
        health["status"] = "ok"
        health["event_count"] = len(events)
        return health
    except (OSError, json.JSONDecodeError, ValueError):
        return {"status": "unreadable", "first_attempt_approval_rate": {},
                "halt_frequency_per_step": {}, "open_candidates": 0}


def read_quality_health(spoke: "Optional[Path]") -> "Optional[dict]":
    """AC30: the wakeup Quality Health section — lug coverage %, null rate,
    certification_score, uncertified lugs — computed over v4 lugs. Degrades
    gracefully (None) if the computer is unavailable; never blocks brief generation."""
    if not spoke or not _QUALITY_HEALTH_AVAILABLE:
        return None
    try:
        return _read_coverage(str(_project_root_for(spoke)))
    except Exception:
        return {"status": "unreadable", "certification_score": None,
                "ac_coverage_pct": None, "null_rate": None, "uncertified_lugs": []}


def read_ac_drift(spoke: "Optional[Path]", now=None) -> "Optional[dict]":
    """impl-derive-epic-ac-status-v1: per-open-epic AC drift vs lug evidence
    {epic_id: {under_report, over_report, mis_partial, total_drift}}. Degrades
    gracefully (None) if the reconciler is unavailable; never blocks brief gen.

    now is passed straight through to reconcile_epic_acs.read_ac_drift, which
    defaults it to time.time() when None (real-time freshness classification
    for actual brief generation). Exposed here so callers/tests can pin it --
    the underlying evidence_for()/_test_fresh() freshness window is genuinely
    time-dependent (drift/mis_partial classification changes as evidence ages
    out of freshness_days), so without this passthrough this wrapper could
    never be called deterministically."""
    if not spoke or not _AC_DRIFT_AVAILABLE:
        return None
    try:
        return _read_ac_drift(str(_project_root_for(spoke)), now=now)
    except Exception:
        return {}


def read_qa_health(spoke: "Optional[Path]") -> "Optional[dict]":
    """impl-qa-stale-test-detection-v1: stale-test detection + gap taxonomy
    (test_null/stale/failing) over v4 lugs. Additive to quality_health (which
    carries coverage/cert). Degrades gracefully (None) if the module is absent."""
    if not spoke or not _QA_HEALTH_AVAILABLE:
        return None
    try:
        return _read_qa_health(str(_project_root_for(spoke)))
    except Exception:
        return {"gap_summary": {"test_null": 0, "stale": 0, "failing": 0},
                "stale_tests": [], "status": "unreadable"}



def read_assurance_health(spoke: "Optional[Path]") -> "Optional[dict]":
    """The wheel's own measurements, surfaced at wakeup instead of on request.

    THE PROBLEM THIS CLOSES (s138). The oracle, the trail walker and the canon
    checker all became real this session, and all three were invisible unless
    somebody thought to run them. An instrument nobody sees is on exactly the
    same path as the mandatory plan-review gate found dead this session: present,
    correct, and quietly not participating.

    Cheap and read-only. Reads the artefacts the tools already leave behind
    rather than executing them — a wakeup must not pay for a test run. Every
    field is independently optional, so a spoke that has not adopted a given
    instrument shows nothing rather than an error.
    """
    if spoke is None:
        return None
    out = {}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import savepoint_walk as _sw  # noqa: PLC0415

        rep = _sw.walk(str(_project_root_for(spoke)), run_commands=False)
        if rep.get("entries"):
            out["trail"] = {
                "checkable_ratio": rep.get("checkable_ratio", 0.0),
                "drifted": rep["counts"].get("drifted", 0),
                "unevidenced_claims": rep.get("claimed_verified_but_uncheckable", 0),
                "entries": rep.get("entries", 0),
            }
    except Exception:  # noqa: BLE001 — a brief must never fail on an optional read
        pass

    try:
        import canon_adherence as _ca  # noqa: PLC0415

        rep = _ca.check(str(_project_root_for(spoke)))
        out["canon"] = {"ok": bool(rep.get("ok")),
                        "drift_count": rep.get("drift_count", 0),
                        "undeployed_count": rep.get("undeployed_count", 0)}
    except Exception:  # noqa: BLE001
        pass

    try:
        d = _project_root_for(spoke) / "WAI-Harness/spoke/local/lugs/bytype/task/open"
        if d.is_dir():
            out["open_assurance_lugs"] = len([f for f in os.listdir(d)
                                              if f.startswith("assurance-")])
    except OSError:
        pass
    return out or None


def read_integrity_probe(project_root: "Optional[Path]") -> "Optional[dict]":
    """Standing silent-failure oracles, surfaced at wakeup instead of on request.

    Operator, 2026-07-26: "too basic problems are not getting seen — that learning has to
    get caught sooner than by the user." Every finding these probes cover was previously
    found by a human happening to ask on the right day: hooks that never deployed while
    restore said "current", a master that refused to distribute for four days in silence,
    lugs the dispatcher ignored rather than rejected.

    Deliberately excludes the slow fleet-wide probes (pending-deploys walks every spoke's
    git remote) so wakeup stays fast — those run under the full `integrity_probe` command.
    Failure to run yields None and the banner simply omits the line; it must never block
    or slow a wakeup.
    """
    if project_root is None:
        return None
    tool = Path(project_root) / "WAI-Harness/spoke/managed/tools/integrity_probe.py"
    if not tool.is_file():
        return None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("integrity_probe", tool)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fast = [mod.probe_master_selfverify, mod.probe_routing, mod.probe_terminal_dirs]
        results = []
        for fn in fast:
            try:
                results.append(fn(str(project_root)))
            except Exception as e:
                results.append(mod._result(fn.__name__, mod.UNKNOWN,
                                           f"probe crashed: {type(e).__name__}"))
        results.sort(key=lambda r: mod.RANK.get(r["status"], 1))
        return {
            "verdict": results[0]["status"] if results else mod.UNKNOWN,
            "lines": mod.render({"verdict": results[0]["status"], "probes": results,
                                 "counts": {}}, brief=True),
            "probes": results,
            "note": "fast probes only — run integrity_probe for the fleet-wide checks",
        }
    except Exception:
        return None


def read_lug_staleness(spoke: "Optional[Path]") -> "Optional[dict]":
    """impl-w4-lug-staleness-wakeup-reader-v1: top-line surface for
    maintenance/lug-staleness-latest.json (produced by fleet_hygiene_scan.py's
    write_lug_staleness_report() — that producer is untouched/out of scope here,
    this is a read-only consumer). Returns None if the report does not exist yet
    (closing cert L2's deferred reader gracefully rather than blocking on it).
    Degrades to a 'status: unreadable' shape on malformed JSON, mirroring
    read_qa_health's degradation convention. Never raises; never blocks brief
    generation."""
    if not spoke:
        return None
    report_path = spoke / "maintenance" / "lug-staleness-latest.json"
    if not report_path.exists():
        return None
    try:
        report = json.loads(report_path.read_text())
        violations = report.get("violations", []) or []
        oldest = None
        if violations:
            oldest_raw = max(violations, key=lambda v: v.get("age_hours", 0))
            oldest = {
                "id": oldest_raw.get("id"),
                "type": oldest_raw.get("type"),
                "status": oldest_raw.get("status"),
                "age_hours": oldest_raw.get("age_hours"),
                "slo_hours": oldest_raw.get("slo_hours"),
            }
        generated_at = report.get("generated_at")
        report_age_hours = None
        if generated_at:
            try:
                gen_dt = datetime.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                now_dt = datetime.datetime.now(datetime.timezone.utc)
                report_age_hours = round((now_dt - gen_dt).total_seconds() / 3600, 1)
            except Exception:
                report_age_hours = None
        # Freshness caveat: reuse this report's own tightest SLO tier (24h, the
        # in_progress/needs_attention slo_hours already codified in the report
        # itself) rather than inventing a new unconfigured threshold.
        stale_report = bool(report_age_hours is not None and report_age_hours > 24)
        return {
            "status": "ok",
            "violations_count": len(violations),
            "oldest_violation": oldest,
            "generated_at": generated_at,
            "report_age_hours": report_age_hours,
            "stale_report": stale_report,
        }
    except Exception:
        return {
            "status": "unreadable",
            "violations_count": 0,
            "oldest_violation": None,
            "generated_at": None,
            "report_age_hours": None,
            "stale_report": True,
        }


def read_insight_memory(spoke: "Optional[Path]", project_root: "Optional[Path]" = None,
                         max_age_hours: float = 24.0) -> "Optional[dict]":
    """feature-insight-memory-from-tracks-v1: top-line surface for the rolling
    cross-session insight digest at <spoke>/memory/insight-memory.json (produced
    by scripts/insight_memory.py -- a read-only consumer here; that producer is
    currently basher-only, so a spoke that has not adopted it simply has no
    digest to show). Returns None if the digest has never been generated on
    this spoke. Best-effort fires a DETACHED background refresh when the digest
    is stale or missing AND the producer script exists on this spoke, so the
    digest self-warms across wakeups without ever blocking brief generation
    (mirrors refresh_position_map's fire-and-check-next-time shape, but
    detached since synthesis calls an LLM rather than a cheap local compute).
    Degrades to a 'status: unreadable' shape on malformed JSON, mirroring
    read_lug_staleness's convention. Never raises; never blocks brief
    generation."""
    if not spoke:
        return None
    digest_path = spoke / "memory" / "insight-memory.json"
    root = project_root or _project_root_for(spoke)
    script = root / "scripts" / "insight_memory.py"
    stale = True
    result = None
    if digest_path.exists():
        try:
            data = json.loads(digest_path.read_text())
            gen_at = data.get("generated_at")
            age_hours = None
            if gen_at:
                gen_dt = datetime.datetime.fromisoformat(gen_at.replace("Z", "+00:00"))
                now_dt = datetime.datetime.now(datetime.timezone.utc)
                age_hours = round((now_dt - gen_dt).total_seconds() / 3600, 1)
                stale = age_hours > max_age_hours
            digest = data.get("digest") or {}
            result = {
                "status": "ok",
                "generated_at": gen_at,
                "age_hours": age_hours,
                "stale": stale,
                "sessions_covered": data.get("sessions_covered", 0),
                "turns_covered": data.get("turns_covered", 0),
                "themes": (digest.get("themes") or [])[:6],
                "open_threads": (digest.get("open_threads") or [])[:6],
                "degraded": digest.get("degraded", False),
            }
        except Exception:
            result = {"status": "unreadable", "stale": True, "generated_at": None,
                       "age_hours": None, "sessions_covered": 0, "turns_covered": 0,
                       "themes": [], "open_threads": [], "degraded": True}
    if stale and script.exists():
        try:
            subprocess.Popen(
                [sys.executable, str(script), "refresh"],
                cwd=str(root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass
    return result


def refresh_position_map(spoke: "Optional[Path]", max_age_hours: float = 12.0) -> None:
    """spec-spoke-position-map-v1 (innate refresh): regenerate maintenance/position-map.json
    when it is absent or stale, so the map is never an orphaned output. spoke_position_map
    stays the SOLE producer — this only TRIGGERS it, best-effort, and never blocks/raises the
    brief if the instrument is missing or slow."""
    if not spoke:
        return
    seat = spoke / "maintenance" / "position-map.json"
    try:
        if seat.exists():
            ts = json.loads(seat.read_text()).get("ts")
            if ts:
                age = (datetime.datetime.now(datetime.timezone.utc)
                       - datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")))
                if age.total_seconds() < max_age_hours * 3600:
                    return  # fresh enough
        import spoke_position_map as spm
        spoke_root = spoke.parents[2] if len(spoke.parents) >= 3 else spoke  # local -> repo root
        m = spm.compose(str(spoke_root))
        spm.write_seat(m, spoke)
    except Exception:
        return  # never let map refresh break brief generation


def read_position_map(spoke: "Optional[Path]") -> "Optional[dict]":
    """spec-spoke-position-map-v1: top-line surface for maintenance/position-map.json
    (produced by spoke_position_map.py — a read-only consumer here, that producer is out
    of scope). Returns None if the map has not been emitted yet; degrades to a compact
    summary (position / bar / gap counts / oracle reading) so the wakeup brief carries the
    where-it-is -> where-to-go read without loading the full map. Never raises/blocks."""
    if not spoke:
        return None
    seat = spoke / "maintenance" / "position-map.json"
    if not seat.exists():
        return None
    try:
        m = json.loads(seat.read_text())
        pos = m.get("position") or {}
        bar = m.get("bar") or {}
        gaps = m.get("gaps") or {}
        orc = m.get("oracles") or {}
        return {
            "status": "ok",
            "position": pos.get("value"),
            "grade": pos.get("grade"),
            "bar": bar.get("value"),
            "blocking_gaps": gaps.get("blocking_count"),
            "soft_gaps": gaps.get("soft_count"),
            "oracle_reading": orc.get("reading"),
            "ts": m.get("ts"),
        }
    except Exception:
        return {"status": "unreadable"}


# --- TasteGraph (spec: WAI-Harness/spoke/managed/wilbur/docs/tastegraph-spec.md) ---
# Resolution order per spec §1: spoke-local overrides -> hub base -> agent defaults.
#
# CARDINAL RULE (spec §2): a preference with confidence 'inferred' may NEVER be
# silently applied. Only 'stated'/'verified' are actionable. Everything else —
# 'inferred', 'observed' (the hub verification_policy keeps observed's
# last_verified null until Mario explicitly confirms), and ANY tier this
# generator does not know about — is segregated into `unverified` and marked as
# needing confirmation. Unknown tiers fail SAFE (segregated, never actionable),
# so a confidence tier added later cannot silently become authoritative here.
_TASTEGRAPH_ACTIVE_CONFIDENCE = frozenset({"stated", "verified"})

# Category render order. communication LEADS: it governs how the agent talks to
# the operator, which is the reason this block is injected at all. Then the rest
# of the how-we-say-it tier, then how-we-decide, then ambient. Categories absent
# from this tuple sort alphabetically after it (never dropped for being unknown).
_TASTEGRAPH_CATEGORY_ORDER = (
    "communication", "accessibility", "output_format", "locale",
    "alignment_gates", "work_style", "engagement", "approach",
    "risk_tolerance", "trust_ladder", "workflow", "prioritization",
    "notification_preferences", "temporal", "cost_sensitivity",
    "aesthetic", "environment", "audience_profile", "meta",
)

# Line ceiling for the injected block, following ceremony_token_budget.py's
# convention: a deliberate ceiling, ratcheted DOWN as the render tightens, never
# up without cause. This block is read by EVERY session, so its size is a
# per-session token cost. Overflow is capped by category priority and ANNOUNCED
# inside the block itself — never silently truncated.
TASTEGRAPH_BLOCK_BUDGET_LINES = 80
_TASTEGRAPH_VALUE_CHARS = 220
_TASTEGRAPH_SUMMARY_CHARS = 110


def _tg_scalar(v) -> str:
    """Render a preference value leaf compactly (no JSON punctuation noise)."""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if v is None:
        return "none"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return ", ".join(_tg_scalar(x) for x in v)
    if isinstance(v, dict):
        return "; ".join(f"{k}={_tg_scalar(x)}" for k, x in v.items())
    return str(v)


def _tg_flatten_value(value, limit: int = _TASTEGRAPH_VALUE_CHARS) -> str:
    """Flatten a preference value to ONE compact line, truncated to `limit`."""
    if isinstance(value, dict):
        s = " | ".join(f"{k}: {_tg_scalar(v)}" for k, v in value.items())
    else:
        s = _tg_scalar(value)
    s = " ".join(s.split())  # collapse newlines/runs — one pref, one line
    if len(s) > limit:
        s = s[: max(0, limit - 3)].rstrip() + "..."
    return s


def _load_tastegraph_tier(path: "Path") -> tuple:
    """Load one tastegraph tier -> (prefs, error).

    prefs is None ONLY on error; a readable tier with an empty preferences list
    returns ([], None). Every failure returns a human reason rather than an empty
    list, so a missing/corrupt tier can never masquerade as "0 preferences"."""
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return None, "not found"
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, f"unreadable ({e.__class__.__name__}: {e})"
    if not isinstance(data, dict):
        return None, f"top level is {type(data).__name__}, expected object"
    prefs = data.get("preferences")
    if prefs is None:
        return None, "no 'preferences' key"
    if not isinstance(prefs, list):
        return None, f"'preferences' is {type(prefs).__name__}, expected list"
    return [p for p in prefs if isinstance(p, dict) and p.get("id")], None


def read_tastegraph_prefs(
    spoke: "Optional[Path]",
    hub_path: str,
    budget_lines: int = TASTEGRAPH_BLOCK_BUDGET_LINES,
) -> dict:
    """Resolve + render the operator's TasteGraph for injection into the brief.

    Merges hub base (<hub_path>/local/tastegraph-org.json — the same
    hub_path -> local/ pattern capgraph_blocks.py uses for hub-registry.json)
    under the OPTIONAL spoke-local tastegraph.json, which wins on id collision
    per spec §1. `spoke` is the already-resolved working base (v3
    <root>/WAI-Spoke, v4 <root>/WAI-Harness/spoke/local), so <base>/tastegraph.json
    is harness-mode-correct in both layouts with no second resolver.

    Unlike the other read_* helpers this NEVER degrades to silence: a missing or
    unparseable tier — or a zero-preference result from any cause — sets
    degraded=True with a reason, carried BOTH in the returned fields and in the
    first line of `block` (a session that reads only the block still sees it). A
    silent 0-preference injection is the exact bug that hid this wiring for
    months. `budget_lines` is exposed so callers/tests can pin the cap.
    """
    try:
        tiers: list = []
        merged: dict = {}       # id -> pref; hub first, spoke-local overwrites in place
        reasons: list = []
        full_set_ref = ""

        # Tier 1: hub base (fleet default).
        if not hub_path:
            reasons.append(
                "wheel.hub_path is not set in WAI-State — hub fleet-default preferences unavailable"
            )
        else:
            hub_file = Path(hub_path).expanduser() / "local" / "tastegraph-org.json"
            full_set_ref = str(hub_file)
            prefs, err = _load_tastegraph_tier(hub_file)
            if err:
                reasons.append(f"hub tastegraph {err}: {hub_file}")
            else:
                for p in prefs:
                    merged[p["id"]] = p
                tiers.append(f"hub-org:{hub_file} ({len(prefs)} prefs)")

        # Tier 2: spoke-local overrides (OPTIONAL — absence is normal, not degraded).
        if spoke:
            local_file = Path(spoke) / "tastegraph.json"
            if local_file.exists():
                prefs, err = _load_tastegraph_tier(local_file)
                if err:
                    reasons.append(
                        f"spoke-local tastegraph {err}: {local_file} — spoke overrides NOT applied"
                    )
                else:
                    overrides = sum(1 for p in prefs if p["id"] in merged)
                    for p in prefs:
                        merged[p["id"]] = p
                    tiers.append(
                        f"spoke-local:{local_file} ({len(prefs)} prefs, {overrides} overriding hub)"
                    )

        # Cardinal rule partition.
        active: list = []
        unverified: list = []
        for p in merged.values():
            if p.get("confidence") in _TASTEGRAPH_ACTIVE_CONFIDENCE:
                active.append(p)
            else:
                unverified.append(p)

        if not active and not reasons:
            reasons.append(
                f"resolved {len(merged)} preference(s) but 0 are actionable "
                f"(stated/verified) — nothing to apply"
            )

        # Render: header (always) + body by category priority, within the budget.
        header: list = []
        if reasons:
            header.append("TASTEGRAPH DEGRADED: " + "; ".join(reasons))
        header.append(
            f"TASTEGRAPH — operator preferences in force this session "
            f"({len(active)} active; stated/verified only)"
        )
        if unverified:
            header.append(
                f"Cardinal rule: {len(unverified)} inferred/observed preference(s) are NOT "
                f"applied — see `tastegraph_prefs.unverified`; confirm with the operator "
                f"before acting on any of them."
            )

        by_cat: dict = {}
        for p in active:
            by_cat.setdefault(p.get("category") or "uncategorized", []).append(p)

        def _cat_rank(c):
            try:
                return (0, _TASTEGRAPH_CATEGORY_ORDER.index(c), "")
            except ValueError:
                return (1, 0, c)

        def _render(p) -> str:
            return f"- {p['id']} ({p.get('key', '')}): {_tg_flatten_value(p.get('value'))}"

        body: list = []
        capped_cats: list = []
        capped_count = 0
        for cat in sorted(by_cat, key=_cat_rank):
            entries = sorted(by_cat[cat], key=lambda p: p["id"])  # deterministic render/truncation
            # Once the budget has forced ANY omission, stop: a smaller lower-priority
            # category must not leapfrog a higher-priority one that did not fit.
            if capped_cats:
                capped_cats.append(cat)
                capped_count += len(entries)
                continue
            # +1 reserves the cap-notice line so the notice itself can't bust the budget.
            avail = budget_lines - (len(header) + len(body) + 1)
            if avail < 2:  # no room for even a category header + one preference
                capped_cats.append(cat)
                capped_count += len(entries)
                continue
            fit = min(len(entries), avail - 1)
            if fit == len(entries):
                body.append(f"[{cat}]")
                body.extend(_render(p) for p in entries)
            else:
                # Fill this category PARTIALLY rather than dropping it whole — an
                # oversized high-priority category must never cost itself its slot.
                body.append(f"[{cat}] ({fit} of {len(entries)} shown — budget)")
                body.extend(_render(p) for p in entries[:fit])
                capped_count += len(entries) - fit
                capped_cats.append(f"{cat} (partial)")

        if capped_cats:
            body.append(
                f"[CAPPED: {capped_count} preference(s) omitted across {len(capped_cats)} "
                f"lower-priority categor{'y' if len(capped_cats) == 1 else 'ies'} to hold the "
                f"{budget_lines}-line block budget: {', '.join(capped_cats)}. "
                f"Full set: {full_set_ref or 'hub tastegraph-org.json'}]"
            )

        return {
            "block": "\n".join(header + body),
            "count": len(active),
            "source": tiers,
            "degraded": bool(reasons),
            "degraded_reason": "; ".join(reasons) if reasons else None,
            "unverified": [
                {
                    "id": p.get("id"),
                    "category": p.get("category"),
                    "key": p.get("key"),
                    "confidence": p.get("confidence"),
                    "summary": _tg_flatten_value(p.get("value"), _TASTEGRAPH_SUMMARY_CHARS),
                    "action": "confirm with operator before applying — never apply silently",
                }
                for p in unverified
            ],
            "unverified_count": len(unverified),
            "resolved_count": len(merged),
            "block_lines": len(header + body),
            "budget_lines": budget_lines,
            "capped": bool(capped_cats),
            "capped_categories": capped_cats,
        }
    except Exception as e:  # never block brief generation — but never go quiet either
        return {
            "block": f"TASTEGRAPH DEGRADED: resolution failed ({e.__class__.__name__}: {e}) "
                     f"— 0 preferences injected; operator preferences are NOT in force.",
            "count": 0,
            "source": [],
            "degraded": True,
            "degraded_reason": f"resolution failed ({e.__class__.__name__}: {e})",
            "unverified": [],
            "unverified_count": 0,
            "resolved_count": 0,
            "block_lines": 1,
            "budget_lines": budget_lines,
            "capped": False,
            "capped_categories": [],
        }


def get_git_sha(spoke_root_path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(spoke_root_path),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return ""


def main() -> None:
    global SPOKE, PROJECT_ROOT, BYTYPE, STATE_FILE, BRIEF_FILE

    parser = argparse.ArgumentParser(description="Generate the spoke wakeup-brief.json (harness-mode aware).")
    parser.add_argument(
        "--spoke-path",
        type=str,
        help="Absolute path to the spoke root directory (e.g., /home/user/projects/minder)",
        default=None,
    )
    parser.add_argument(
        "--mode",
        type=str,
        default=None,
        help="v4-only | v3-only (else $WAI_HARNESS_MODE / auto: prefer v4).",
    )
    args = parser.parse_args()

    # Determine the PROJECT ROOT (dir containing WAI-Spoke and/or WAI-Harness), then
    # resolve the working BASE via the single-source resolver so a v4-only session
    # briefs from WAI-Harness/spoke/local with zero WAI-Spoke access.
    if args.spoke_path:
        PROJECT_ROOT = Path(args.spoke_path)
        if not ((PROJECT_ROOT / "WAI-Spoke").exists() or (PROJECT_ROOT / "WAI-Harness").exists()):
            print(f"ERROR: --spoke-path {args.spoke_path} contains neither WAI-Spoke nor WAI-Harness.", file=sys.stderr)
            sys.exit(1)
    elif (Path.cwd() / "WAI-Spoke").exists() or (Path.cwd() / "WAI-Harness").exists():
        PROJECT_ROOT = Path.cwd()
    else:
        PROJECT_ROOT = PROJECT_DIR

    base, mode = wai_paths.resolve_wai_root(str(PROJECT_ROOT), args.mode)
    if not base:
        print(f"ERROR: no WAI harness tree (WAI-Spoke or WAI-Harness) under {PROJECT_ROOT}", file=sys.stderr)
        sys.exit(1)
    SPOKE = Path(base)

    if not SPOKE.exists():
        print(f"ERROR: resolved working base does not exist at {SPOKE} (mode={mode})", file=sys.stderr)
        sys.exit(1)

    # Update global path variables based on the determined SPOKE path
    BYTYPE = SPOKE / "lugs" / "bytype"
    STATE_FILE = SPOKE / "WAI-State.json"
    BRIEF_FILE = SPOKE / "wakeup-brief.json"

    if not STATE_FILE.exists():
        print(f"ERROR: WAI-State.json not found at {STATE_FILE} — not a WAI project", file=sys.stderr)
        sys.exit(1)

    state = json.loads(STATE_FILE.read_text())
    hub_path = state.get("wheel", {}).get("hub_path", "")
    spoke_version = state.get("wheel", {}).get("version", "unknown")
    last_session_id = state.get("_session_state", {}).get("last_session_id", "unknown")
    next_rec = state.get("_session_state", {}).get(
        "next_session_recommendation", "None"
    )

    intent_file = SPOKE / "runtime" / "session-intent.json"
    session_intent = None
    if intent_file.exists():
        try:
            session_intent = json.loads(intent_file.read_text())
        except Exception:
            pass
    savepoint = state.get("_savepoint", {})
    savepoint_data = savepoint if savepoint.get("status") == "pending" else None

    lug_counts = count_open_lugs()
    open_lug_count = lug_counts["total"]
    queue_snapshot, top_ready_lugs, stalled_lugs = run_score_backlog()
    work_queue_matrix = read_work_queue_matrix_counts(SPOKE)
    teachings_pending = count_teachings_pending(hub_path, SPOKE)
    incoming_lugs_pending = count_incoming_lugs(SPOKE)
    hub_signals_pending = count_hub_signals(hub_path)
    git_sha = get_git_sha(PROJECT_ROOT)  # the spoke project root (NOT SPOKE.parent in v4)
    hook_freshness = hook_freshness_check(PROJECT_ROOT, PROJECT_DIR)
    active_leases = collect_active_leases(SPOKE)
    continuation_menu = build_continuation_menu(SPOKE)
    pattern_health_data = read_pattern_health(SPOKE)
    quality_health_data = read_quality_health(SPOKE)
    ac_drift_data = read_ac_drift(SPOKE)
    qa_health_data = read_qa_health(SPOKE)
    lug_staleness_data = read_lug_staleness(SPOKE)
    assurance_health_data = read_assurance_health(SPOKE)
    integrity_probe_data = read_integrity_probe(PROJECT_ROOT)
    refresh_position_map(SPOKE)
    position_map_data = read_position_map(SPOKE)
    insight_memory_data = read_insight_memory(SPOKE, PROJECT_ROOT)
    if compile_tastegraph is not None:
        try:
            compile_tastegraph.compile_tastegraph(project_root=PROJECT_ROOT, mode=mode, hub_path=hub_path)
        except Exception:
            pass  # producer failure must never break the brief
    tastegraph_data = read_tastegraph_prefs(SPOKE, hub_path)
    ask_landing_data = read_ask_landing(SPOKE, PROJECT_ROOT)

    brief = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "session_id": last_session_id,
        "generation_mode": "standard",
        "chain_target_lug": None,
        "open_lug_count": open_lug_count,
        "queue_snapshot": queue_snapshot,
        "top_ready_lugs": top_ready_lugs,
        "stalled_lugs": stalled_lugs,
        "teachings_pending": teachings_pending,
        "incoming_lugs_pending": incoming_lugs_pending,
        "hub_signals_pending": hub_signals_pending,
        "intent": session_intent.get("intent") if session_intent else None,
        "intent_label": session_intent.get("intent_label") if session_intent else None,
        "savepoint": savepoint_data,
        "next_session_goal": next_rec,
        "next_actions": [next_rec],
        "spoke_version": spoke_version,
        "git_sha_at_generation": git_sha,
        "hook_freshness": hook_freshness,
        "active_leases": active_leases,
        "continuation_menu": continuation_menu,
        "work_queue_matrix": work_queue_matrix,
        "pattern_health": pattern_health_data,
        "quality_health": quality_health_data,
        "ac_drift": ac_drift_data,
        "qa_health": qa_health_data,
        "lug_staleness": lug_staleness_data,
        "position_map": position_map_data,
        "ask_landing": ask_landing_data,
        "insight_memory": insight_memory_data,
        "tastegraph_prefs": tastegraph_data,
        "assurance_health": assurance_health_data,
        "integrity_probe": integrity_probe_data,
    }

    # Atomic write
    tmp = BRIEF_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(brief, indent=2) + "\n")
    os.replace(tmp, BRIEF_FILE)

    sha8 = git_sha[:8] if git_sha else "unknown"
    _parts = []
    if lug_counts["epics"] > 0:
        _parts.append(f"{lug_counts['epics']} epics")
    _work = lug_counts["work_open"] + lug_counts["work_ip"]
    if _work > 0:
        _parts.append(f"{_work} work")
    _lug_summary = " | ".join(_parts) if _parts else "0 open"
    _stalled = queue_snapshot.get("stalled_count", 0)
    _stalled_suffix = f" | {_stalled} stalled" if _stalled > 0 else ""
    _tg_suffix = f" | taste {tastegraph_data.get('count', 0)}"
    if tastegraph_data.get("capped"):
        _tg_suffix += " (capped)"
    print(
        f"wakeup-brief.json updated | SHA {sha8} | "
        f"{_lug_summary} | queue {queue_snapshot.get('ready_count', 0)} ready{_stalled_suffix}"
        f"{_tg_suffix}"
    )
    # Loud on stderr: a degraded tastegraph must never pass as a normal run.
    if tastegraph_data.get("degraded"):
        print(
            f"WARNING: tastegraph degraded — {tastegraph_data.get('degraded_reason')}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
