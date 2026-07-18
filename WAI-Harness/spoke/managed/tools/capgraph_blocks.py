#!/usr/bin/env python3
"""capgraph_blocks — turn AP block events into durable, machine-read CapabilitiesGraph antipatterns.

This is the P0 keystone of initiative-goal-driven-autopilot-v1. Every time
ozi_autopilot blocks a lug (execute_when skip, verify-gate fail, stall, dispatch
failure) it calls record_block(); consult() reads those antipatterns back at
dispatch so the same block is remembered, not silently re-hit.

Design (see ~/.claude/plans/cached-purring-taco.md + impl-capgraph-blocks-keystone-v1):
  - A block is a NEGATIVE CAPABILITY: situation -> what-to-do-instead, the mirror
    of a positive capability's situation -> solution. It lives in the spoke-local
    CapabilitiesGraph addenda layer (capabilities-graph-local.json, kind=antipattern),
    resolved by resolve_capabilities_graph.py. NOT a new graph.
  - CONCURRENCY: blocks.jsonl (append-only) is the source-of-truth event log; the
    capabilities-graph-local.json projection is written atomically (temp + rename).
  - ROBUSTNESS: every public call is wrapped so it can NEVER raise into AP. On any
    error it logs to stderr and returns a safe default (None / []).

Signature (dedup key): "ap-block:<block_class>:<lug_id>" — a recurring block on the
same lug increments occurrences rather than duplicating. `target` + `sources` are
retained so a later phase can generalize across lugs with the same signature.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

LOCAL_GRAPH = "capabilities-graph-local.json"
BLOCKS_LOG = "capabilitygraph/blocks.jsonl"
# Effective graph (resolved hub+spoke+local) — relative to spoke root (WAI-Harness/spoke/)
EFFECTIVE_GRAPH_REL = Path("managed") / "runtime" / "capabilities-effective.json"

VALID_CLASSES = {
    "precondition_unmet",
    "qc_error",
    "execute_when",
    "dispatch_failure",
    "stall",
    "blocked_by",  # P2: dependency block caught at the expediter layer (pre-phase-3)
}

# B2: typed event ledger — record_block() is now a thin wrapper over record_event()
# for kind="block". No migration: any BLOCKS_LOG line (or graph entry) missing the
# 'kind' key is legacy history and reads as kind=block via _kind_of().
# C9: "reason_code" added for silent state-clear ledger entries (dispatch unlink,
# incoming/signal clear, teaching archival + savepoint migrate, lug retire). The
# fixed enum vocabulary for payload["reason_code"] values lives in
# managed/config/contract-routing.yaml's reason_codes: section (data, not code) —
# this kind does not itself validate against the enum; callers bind reason_code
# from that fixed list.
VALID_KINDS = {"block", "contract_event", "heartbeat", "resolution", "reason_code", "verification-finding"}

# P2: only STRUCTURAL/DETERMINISTIC block classes are promoted fleet-wide.
# Transient classes (dispatch_failure, stall, blocked_by) are intentionally excluded
# to avoid spamming Basher with flaky/network noise.
STRUCTURAL_CLASSES = {"precondition_unmet", "execute_when", "qc_error"}
PROMOTE_THRESHOLD = 3  # occurrences on a single spoke before promoting to hub


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_spoke_local(start: Optional[str] = None) -> Optional[Path]:
    """Resolve WAI-Harness/spoke/local from an explicit path, env, or by walking up."""
    if start:
        p = Path(start)
        # accept either spoke/local itself or a spoke root containing it
        if p.name == "local" and p.parent.name == "spoke":
            return p
        cand = p / "WAI-Harness" / "spoke" / "local"
        if cand.exists():
            return cand
        cand = p / "spoke" / "local"
        if cand.exists():
            return cand
    env = os.environ.get("WAI_SPOKE_LOCAL")
    if env and Path(env).exists():
        return Path(env)
    here = Path(__file__).resolve()
    for anc in here.parents:
        cand = anc / "WAI-Harness" / "spoke" / "local"
        if cand.exists():
            return cand
        if anc.name == "local" and anc.parent.name == "spoke":
            return anc
    return None


def _load_graph(graph_path: Path) -> Dict[str, Any]:
    if graph_path.exists():
        try:
            d = json.loads(graph_path.read_text())
            if isinstance(d, dict) and isinstance(d.get("entries"), list):
                return d
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "schema_version": "1.0",
        "id": "capabilities-graph-local",
        "purpose": "Spoke-local CapabilityGraph addenda (incl. antipattern block-memory).",
        "generated_by": "capgraph_blocks",
        "generated_at": _now(),
        "entries": [],
    }


def _atomic_write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(tmp, path)  # atomic on POSIX


def _signature(block_class: str, lug_id: str) -> str:
    return f"ap-block:{block_class}:{lug_id}"


def _kind_of(entry: Dict[str, Any]) -> str:
    """Back-compat reader for raw BLOCKS_LOG lines: missing 'kind' == legacy == block.

    Used anywhere raw BLOCKS_LOG lines are re-read (never touches/rewrites history).
    """
    return entry.get("kind", "block")


def _event_signature(kind: str, subject: str, payload: Dict[str, Any]) -> str:
    """Dedup signature per kind. 'block' keeps the exact pre-existing format so
    goal_planner.py and existing blocks.jsonl history are unaffected. New kinds get
    new prefixes so no collision with 'ap-block:' is possible. 'resolution' has no
    signature of its own -- it operates against an existing sig (subject IS the sig)."""
    if kind == "block":
        return _signature(payload.get("block_class", ""), subject)
    if kind == "contract_event":
        return f"contract-event:{payload.get('component')}:{payload.get('clause')}"
    if kind == "heartbeat":
        return f"heartbeat:{payload.get('component')}:{payload.get('behavior')}"
    if kind == "resolution":
        return subject
    if kind == "reason_code":
        return f"reason-code:{subject}:{payload.get('reason_code')}"
    if kind == "verification-finding":
        return f"verification-finding:{subject}:{payload.get('error_class')}"
    raise ValueError(f"unknown event kind: {kind}")


def _new_projection_entry(kind: str, sig: str, subject: str, payload: Dict[str, Any], ts: str) -> Dict[str, Any]:
    """Initial shape for a brand-new dedup'd projection entry, keyed by event kind.

    'block' keeps its existing 'antipattern' entry-kind + situation shape so consult(),
    summarize(), and _maybe_promote() (all block_class/situation aware) need no changes.
    """
    entry: Dict[str, Any] = {
        "id": sig,
        "kind": "antipattern" if kind == "block" else kind,
        "status": "open",
        "resolution": None,
        "occurrences": 0,
        "sources": [],
        "first_seen": ts,
        "last_seen": ts,
    }
    if kind == "block":
        block_class = payload.get("block_class")
        lug_type = payload.get("lug_type")
        target = (payload.get("error_code") or payload.get("reason") or "")[:160]
        entry.update({
            "name": f"AP block [{block_class}] on {subject}",
            "tier": "recommended",
            "block_class": block_class,
            "situation": {
                "lug_type": lug_type, "target": target,
                "error_code": payload.get("error_code"),
                "precondition_expr": (payload.get("reason") or "")[:160] or None,
            },
            "solution": None,
            "source": "runtime-block",
            "goal_id": payload.get("goal_id"),
            "initiative": payload.get("initiative"),
        })
    elif kind == "contract_event":
        entry.update({
            "name": f"contract event on {payload.get('component')}:{payload.get('clause')}",
            "component": payload.get("component"),
            "contract_version": payload.get("contract_version"),
            "clause": payload.get("clause"),
            "severity": payload.get("severity"),
            "evidence_ref": payload.get("evidence_ref"),
            "tier": payload.get("tier"),
            "resolution_ref": payload.get("resolution_ref"),
            "source": "runtime-contract-event",
        })
    elif kind == "heartbeat":
        entry.update({
            "name": f"heartbeat on {payload.get('component')}:{payload.get('behavior')}",
            "component": payload.get("component"),
            "behavior": payload.get("behavior"),
            "fired_at": payload.get("fired_at"),
            "work_units": payload.get("work_units"),
            "source": "runtime-heartbeat",
        })
    elif kind == "reason_code":
        entry.update({
            "name": f"reason_code [{payload.get('reason_code')}] on {subject}",
            "reason_code": payload.get("reason_code"),
            "detail": payload.get("detail"),
            "component": payload.get("component"),
            "source": "runtime-reason-code",
        })
    elif kind == "verification-finding":
        entry.update({
            "name": f"verification-finding [{payload.get('error_class')}] on {subject}",
            "error_class": payload.get("error_class"),
            "caught_by": payload.get("caught_by"),
            "author_context": payload.get("author_context"),
            "artifact": payload.get("artifact"),
            "tier": payload.get("tier"),
            "source": "creation-gate",
        })
    return entry


# ---------------------------------------------------------------------------
# P2: Hub promotion helpers
# ---------------------------------------------------------------------------

def _find_basher_incoming(local: Path) -> Optional[Path]:
    """Locate Basher's lugs/incoming/ by reading WAI-State.json -> hub_path -> hub-registry.json."""
    try:
        state = json.loads((local / "WAI-State.json").read_text())
        hub_path = state.get("wheel", {}).get("hub_path")
        if not hub_path:
            return None
        registry_path = Path(hub_path) / "local" / "hub-registry.json"
        if not registry_path.exists():
            return None
        registry = json.loads(registry_path.read_text())
        for wheel in registry.get("wheels", []):
            if wheel.get("wheel_id") == "basher":
                spoke_path = Path(wheel["path"])
                incoming = spoke_path / "WAI-Harness" / "spoke" / "local" / "lugs" / "incoming"
                if incoming.exists():
                    return incoming
    except Exception:
        pass
    return None


def _safe_filename(s: str) -> str:
    """Strip non-filename-safe chars for use in a lug filename."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", s)[:48]


def _emit_promotion_change_lug(entry: Dict[str, Any], local: Path) -> bool:
    """Emit a change-lug to Basher requesting the antipattern be added to hub CapabilitiesGraph.

    Also writes an audit copy to local/lugs/outgoing/.
    Returns True on success, False on any failure (never raises).
    """
    try:
        import re as _re
        basher_incoming = _find_basher_incoming(local)
        if basher_incoming is None:
            print("[capgraph_blocks] cannot locate Basher incoming — promotion skipped", file=sys.stderr)
            return False

        block_class = entry.get("block_class", "unknown")
        safe_id = _safe_filename(entry.get("id", "unknown"))
        lug_id = f"change-capgraph-promote-{block_class}-{safe_id}"
        ts = _now()

        change_lug = {
            "id": lug_id,
            "type": "change",
            "status": "open",
            "priority": "P3",
            "routed_to": "SPOKE/basher",
            "scope": "cross-spoke",
            "created_at": ts,
            "created_by": "capgraph_blocks/promote_antipattern",
            "title": f"Add fleet antipattern [{block_class}] to hub CapabilitiesGraph",
            "summary": (
                f"A structural antipattern (block_class={block_class}) reached "
                f"occurrences>={PROMOTE_THRESHOLD} on this spoke. Promoting to hub "
                f"WAI-Harness/hub/managed/capabilities-graph-hub.json so the fleet "
                f"consult() pre-empts this before wasting a dispatch."
            ),
            "action": "add_entry",
            "target_file": "WAI-Harness/hub/managed/capabilities-graph-hub.json",
            "antipattern_entry": {
                **entry,
                "tier": "recommended",  # non-hub entries are always recommended (superset rule)
                "source": "hub",        # will become hub-level after Basher merges
            },
            "basher_instructions": (
                "1. Open target_file. "
                "2. Append antipattern_entry to entries[] (skip if id already present). "
                "3. Commit + distribute via harness_distribute_fleet."
            ),
        }

        filename = f"{lug_id}.json"
        _atomic_write(basher_incoming / filename, change_lug)

        # Audit copy in local outgoing/
        outgoing = local / "lugs" / "outgoing"
        outgoing.mkdir(parents=True, exist_ok=True)
        _atomic_write(outgoing / filename, change_lug)
        return True
    except Exception as exc:
        print(f"[capgraph_blocks] _emit_promotion_change_lug failed: {exc}", file=sys.stderr)
        return False


def _maybe_promote(entry: Dict[str, Any], local: Path, graph: Dict[str, Any],
                   graph_path: Path, threshold: int = PROMOTE_THRESHOLD) -> None:
    """Promote an antipattern to the hub if it meets the structural threshold.

    Skipped silently (never raises) if any gate fails or promotion already done.
    """
    try:
        # Gate 1: structural class only
        if entry.get("block_class") not in STRUCTURAL_CLASSES:
            return
        # Gate 2: occurrences threshold
        if int(entry.get("occurrences", 0)) < threshold:
            return
        # Gate 3: not already promoted (idempotent)
        if entry.get("promoted_at"):
            return
        # Emit the change-lug to Basher
        ok = _emit_promotion_change_lug(entry, local)
        if ok:
            entry["promoted_at"] = _now()
            _atomic_write(graph_path, graph)
    except Exception as exc:
        print(f"[capgraph_blocks] _maybe_promote failed: {exc}", file=sys.stderr)


def record_event(
    kind: str,
    subject: str,
    payload: Dict[str, Any],
    spoke_local: Optional[str] = None,
) -> Optional[str]:
    """Generalized typed-event recorder: block | contract_event | heartbeat | resolution.

    Writes one JSON line to BLOCKS_LOG (append-only source of truth), then upserts a
    dedup'd projection entry in capabilities-graph-local.json, sharing the exact
    atomic-write + occurrence-increment machinery across all 4 kinds. 'resolution'
    operates against an existing sig (subject) and updates resolution/status only —
    it does not create a new entry or bump occurrences (mirrors set_resolution()).

    Returns the entry signature, or None if recording was skipped/failed.
    NEVER raises into the caller.
    """
    try:
        if kind not in VALID_KINDS:
            return None
        local = _find_spoke_local(spoke_local)
        if local is None:
            print("[capgraph_blocks] could not resolve spoke/local — skip", file=sys.stderr)
            return None
        sig = _event_signature(kind, subject, payload)
        ts = _now()

        # 1) append-only event log (source of truth) — never blocks on graph IO
        log_path = local / BLOCKS_LOG
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as fh:
            fh.write(json.dumps({"ts": ts, "kind": kind, "sig": sig, **payload}, ensure_ascii=False) + "\n")

        # 2) upsert the projection entry (atomic), shared across all kinds
        graph_path = local / LOCAL_GRAPH
        graph = _load_graph(graph_path)
        entry = next((e for e in graph["entries"] if e.get("id") == sig), None)

        if kind == "resolution":
            if entry is None:
                return sig  # log line written; no existing sig to resolve against
            resolution = payload.get("resolution")
            status = payload.get("status")
            if status is None:
                status = "resolved" if resolution and resolution != "escalated" else "open"
            entry["resolution"] = resolution
            entry["status"] = status
            entry["resolved_at"] = ts if resolution else None
            entry["last_seen"] = ts
            graph["generated_at"] = ts
            _atomic_write(graph_path, graph)
            return sig

        if entry is None:
            entry = _new_projection_entry(kind, sig, subject, payload, ts)
            graph["entries"].append(entry)
        entry["occurrences"] = int(entry.get("occurrences", 0)) + 1
        entry["last_seen"] = ts
        if subject and subject not in entry.get("sources", []):
            entry.setdefault("sources", []).append(subject)
        graph["generated_at"] = ts
        _atomic_write(graph_path, graph)

        # P2: promote if this structural antipattern has hit the fleet-sharing threshold
        if kind == "block":
            _maybe_promote(entry, local, graph, graph_path)

        return sig
    except Exception as e:  # never raise into AP
        print(f"[capgraph_blocks] record_event degraded to no-op: {e}", file=sys.stderr)
        return None


def record_block(
    lug: Dict[str, Any],
    block_class: str,
    reason: str = "",
    error_code: Optional[str] = None,
    spoke_local: Optional[str] = None,
) -> Optional[str]:
    """Record a block as a CapabilitiesGraph antipattern entry (upsert by signature).

    Thin wrapper over record_event(kind="block", ...). Preserves the exact existing
    signature format "ap-block:<block_class>:<lug_id>" and call surface unchanged —
    zero call-site changes anywhere in the repo.

    Returns the antipattern entry id, or None if recording was skipped/failed.
    NEVER raises into the caller.
    """
    try:
        if block_class not in VALID_CLASSES:
            return None
        lug_id = str(lug.get("id") or lug.get("lug_id") or lug.get("i") or "unknown")
        lug_type = str(lug.get("type") or lug.get("_fs_type") or "unknown")
        payload = {
            "lug_id": lug_id,
            "lug_type": lug_type,
            "block_class": block_class,
            "reason": (reason or "")[:280],
            "error_code": error_code,
            "goal_id": lug.get("goal_id"),
            "initiative": lug.get("initiative") or lug.get("initiative_id"),
        }
        return record_event("block", lug_id, payload, spoke_local)
    except Exception as e:  # never raise into AP
        print(f"[capgraph_blocks] record_block degraded to no-op: {e}", file=sys.stderr)
        return None


def consult(lug: Dict[str, Any], spoke_local: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return open antipattern entries known for this lug (machine-read at dispatch).

    Two-tier lookup:
      1. Local graph (capabilities-graph-local.json): exact match by lug_id in sources.
      2. Effective graph (capabilities-effective.json): fleet-distributed structural
         antipatterns matched by block_class + lug_type. These were promoted from another
         spoke and immunize the fleet against the same structural class.

    NEVER raises; returns [] on any error.
    """
    try:
        local = _find_spoke_local(spoke_local)
        if local is None:
            return []
        lug_id = str(lug.get("id") or lug.get("lug_id") or lug.get("i") or "unknown")
        lug_type = str(lug.get("type") or lug.get("_fs_type") or "unknown")

        hits: List[Dict[str, Any]] = []

        # 1. Local graph: exact match by lug_id in entry.sources
        graph_path = local / LOCAL_GRAPH
        if graph_path.exists():
            graph = _load_graph(graph_path)
            hits.extend(
                e for e in graph.get("entries", [])
                if e.get("kind") == "antipattern"
                and e.get("status") == "open"
                and lug_id in e.get("sources", [])
            )

        # 2. Effective graph: fleet-distributed structural antipatterns (broad match)
        # spoke root = local.parent; managed/runtime is a sibling of spoke/local
        eff_path = local.parent / EFFECTIVE_GRAPH_REL
        if eff_path.exists():
            try:
                eff = json.loads(eff_path.read_text())
                for e in eff.get("entries", []):
                    if (e.get("kind") == "antipattern"
                            and e.get("status") == "open"
                            and e.get("block_class") in STRUCTURAL_CLASSES
                            and e.get("situation", {}).get("lug_type") == lug_type
                            # skip if we already have this from the local graph
                            and e.get("id") not in {h["id"] for h in hits}):
                        hits.append(e)
            except Exception:
                pass

        return hits
    except Exception as e:
        print(f"[capgraph_blocks] consult degraded to []: {e}", file=sys.stderr)
        return []


def set_resolution(
    sig: str, resolution: Optional[str], spoke_local: Optional[str] = None
) -> bool:
    """Stamp an antipattern's resolution (P1 replan ladder records the rung taken).

    resolution None -> status stays open; a non-null resolution -> status resolved.
    NEVER raises; returns True on write, False otherwise.
    """
    try:
        local = _find_spoke_local(spoke_local)
        if local is None:
            return False
        graph_path = local / LOCAL_GRAPH
        graph = _load_graph(graph_path)
        entry = next((e for e in graph["entries"] if e.get("id") == sig), None)
        if entry is None:
            return False
        entry["resolution"] = resolution
        entry["status"] = "resolved" if resolution and resolution != "escalated" else "open"
        entry["resolved_at"] = _now() if resolution else None
        _atomic_write(graph_path, graph)
        return True
    except Exception as e:
        print(f"[capgraph_blocks] set_resolution degraded to no-op: {e}", file=sys.stderr)
        return False


def summarize(spoke_local: Optional[str] = None) -> Dict[str, Any]:
    """Monitoring helper: counts by block_class + totals."""
    local = _find_spoke_local(spoke_local)
    out: Dict[str, Any] = {"total_antipatterns": 0, "total_occurrences": 0, "by_class": {}, "open": 0, "resolved": 0}
    if local is None:
        return out
    graph = _load_graph(local / LOCAL_GRAPH)
    for e in graph.get("entries", []):
        if e.get("kind") != "antipattern":
            continue
        out["total_antipatterns"] += 1
        out["total_occurrences"] += int(e.get("occurrences", 0))
        bc = e.get("block_class", "?")
        out["by_class"][bc] = out["by_class"].get(bc, 0) + 1
        out["open" if e.get("status") == "open" else "resolved"] += 1
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="capgraph_blocks — AP block antipattern memory")
    ap.add_argument("--root", help="spoke root or spoke/local path")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()
    if args.summary:
        print(json.dumps(summarize(args.root), indent=2))
