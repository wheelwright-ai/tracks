#!/usr/bin/env python3
"""debt_rotation — last-touched-per-(surface, dimension) query layer over the typed
event ledger (capgraph_blocks.py / B2's block|contract_event|heartbeat|resolution
kinds), feeding THREE consumers named in initiative-mandates-spine-v1:

  (i)   ozi_autopilot's dispatch loop — reserves 1-in-5 dispatch slots for the
        oldest below-gate/low-score lug per rotate_candidates(), tagged
        exploration: true so its outcome stays separately attributable.
  (ii)  Conductor's starvation-age counter-metric (feeds C5's Goodhart pairing).
  (iii) Prism's lens-rotation feed (E5, wired later) — lens_rotation_candidates()
        only needs to exist and return correct data against a fixture ledger now.

Design (impl-spine-c11-debt-rotation-exploration-v1):
  - Single shared module. Each consumer calls INTO this module rather than
    reimplementing "what's the oldest stale thing" logic three times.
  - A 'surface' is a component/spoke identity extracted from a ledger entry:
      * block/antipattern entries -> the lug_id in entry['sources'][0]
        (the finest-grained surface available for block events; there is no
        separate 'component' field on a block entry).
      * contract_event / heartbeat entries -> entry['component'].
  - A 'dimension' is the ledger KIND (block | contract_event | heartbeat) --
    WHAT KIND of check/event last touched that surface. Finer detail
    (block_class / clause / behavior) stays on the raw entry for callers that
    want it; it is not folded into the dimension key so oldest-first ranking
    stays comparable across kinds.
  - resolution events do not create their own ledger entries (they mutate an
    existing one in place, per capgraph_blocks.record_event) so they are not a
    distinct dimension here; a resolved entry's last_seen still moves forward
    and is picked up naturally.

Ratio ownership: the 1-in-5 exploration ratio is human-owned (C10,
hub/local/config/weights.yaml). If weights.yaml doesn't exist yet (C10 not
landed), DEFAULT_EXPLORATION_RATIO below is used as a clearly-marked fallback.
TODO(C10): once weights.yaml lands fleet-wide, this inline default becomes
pure fallback-of-last-resort; no code change needed here beyond confirming the
key path (debt_rotation.exploration_ratio) matches what C10 actually ships.

Reads capgraph_blocks.py's ledger accessors (_find_spoke_local / _load_graph /
LOCAL_GRAPH) directly -- capgraph_blocks.py itself is READ-ONLY for this
packet (perceive[] / target_files mark it read-only; consult() is lug-scoped
and unsuited to a "give me every surface x dimension pair" scan, so this
module reads the same on-disk projection consult() reads, via the same
private loader capgraph_blocks already uses internally).

Every public call is guarded so it can NEVER raise into a caller (AP, Conductor,
or Prism) -- on any error it logs to stderr and returns a safe default,
matching capgraph_blocks.py's own robustness contract.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capgraph_blocks as _cb  # noqa: E402

# 1-in-5 exploration slot. TODO(C10): migrate to hub/local/config/weights.yaml
# under key debt_rotation.exploration_ratio; this inline value is the fallback
# used whenever that file/key doesn't exist yet.
DEFAULT_EXPLORATION_RATIO = 0.2

# A pair not touched within this many days is eligible as a rotation candidate.
# ("below a freshness threshold" per the lug's acceptance criteria.)
DEFAULT_FRESHNESS_THRESHOLD_DAYS = 1.0

_ANTIPATTERN_DIMENSION = "block"  # capgraph_blocks projects block events as kind="antipattern"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _entry_dimension(entry: Dict[str, Any]) -> str:
    kind = entry.get("kind")
    if kind == "antipattern":
        return _ANTIPATTERN_DIMENSION
    return str(kind or "unknown")


def _entry_surface(entry: Dict[str, Any]) -> str:
    kind = entry.get("kind")
    if kind == "antipattern":
        sources = entry.get("sources") or []
        if sources:
            return str(sources[0])
        return str((entry.get("situation") or {}).get("lug_type") or "unknown")
    if kind in ("contract_event", "heartbeat"):
        return str(entry.get("component") or "unknown")
    return "unknown"


def load_ledger(spoke_local: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read the typed-event ledger projection (capabilities-graph-local.json entries)
    via capgraph_blocks's own loader. Returns [] on any error or if no ledger exists
    yet (fresh spoke) -- NEVER raises."""
    try:
        local = _cb._find_spoke_local(spoke_local)
        if local is None:
            return []
        graph_path = local / _cb.LOCAL_GRAPH
        if not graph_path.exists():
            return []
        graph = _cb._load_graph(graph_path)
        return list(graph.get("entries", []))
    except Exception as e:  # never raise into a caller
        print(f"[debt_rotation] load_ledger degraded to []: {e}", file=sys.stderr)
        return []


def _pairs(ledger: List[Dict[str, Any]]) -> Dict[tuple, str]:
    """Reduce raw ledger entries to {(surface, dimension): latest last_seen}."""
    out: Dict[tuple, str] = {}
    for entry in ledger:
        if not isinstance(entry, dict):
            continue
        surface = _entry_surface(entry)
        dimension = _entry_dimension(entry)
        ts = entry.get("last_seen") or entry.get("first_seen")
        if not ts:
            continue
        key = (surface, dimension)
        prev = out.get(key)
        if prev is None or (_parse_ts(ts) or datetime.min.replace(tzinfo=timezone.utc)) > (
            _parse_ts(prev) or datetime.min.replace(tzinfo=timezone.utc)
        ):
            out[key] = ts
    return out


def last_touched(
    surface: str,
    dimension: str,
    ledger: Optional[List[Dict[str, Any]]] = None,
    spoke_local: Optional[str] = None,
) -> Optional[str]:
    """Latest ISO timestamp this (surface, dimension) pair was touched, or None if
    the pair has never appeared in the ledger. NEVER raises."""
    try:
        led = ledger if ledger is not None else load_ledger(spoke_local)
        return _pairs(led).get((surface, dimension))
    except Exception as e:
        print(f"[debt_rotation] last_touched degraded to None: {e}", file=sys.stderr)
        return None


def rotate_candidates(
    ledger: List[Dict[str, Any]],
    n: int,
    freshness_threshold_days: float = DEFAULT_FRESHNESS_THRESHOLD_DAYS,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """The n oldest (surface, dimension) pairs at/below the freshness threshold
    (i.e. stale enough to count as debt), oldest-first. Each result:
        {"surface", "dimension", "last_touched", "age_days"}
    NEVER raises; returns [] on any error."""
    try:
        ref = now or _now()
        pairs = _pairs(ledger)
        candidates = []
        for (surface, dimension), ts in pairs.items():
            dt = _parse_ts(ts)
            if dt is None:
                continue
            age_days = (ref - dt).total_seconds() / 86400.0
            if age_days >= freshness_threshold_days:
                candidates.append(
                    {
                        "surface": surface,
                        "dimension": dimension,
                        "last_touched": ts,
                        "age_days": age_days,
                    }
                )
        candidates.sort(key=lambda c: c["last_touched"])  # oldest ISO ts first
        return candidates[: max(0, n)]
    except Exception as e:
        print(f"[debt_rotation] rotate_candidates degraded to []: {e}", file=sys.stderr)
        return []


def starvation_age(
    spoke: Optional[str] = None,
    ledger: Optional[List[Dict[str, Any]]] = None,
    now: Optional[datetime] = None,
) -> Optional[float]:
    """Age (in days) of the single oldest (surface, dimension) pair in a spoke's
    ledger -- the starvation-age counter-metric Conductor's health-gate/dispatch
    cycle feeds into C5's Goodhart pairing. `spoke` is a spoke root path (same
    shape Conductor already passes to dispatchable_lugs()); `ledger` lets a
    caller (or test) pass a synthetic ledger directly instead of reading disk.
    Returns None if the ledger is empty (nothing to be starved of yet).
    NEVER raises."""
    try:
        led = ledger if ledger is not None else load_ledger(spoke)
        oldest = rotate_candidates(led, n=1, freshness_threshold_days=0.0, now=now)
        if not oldest:
            return None
        return oldest[0]["age_days"]
    except Exception as e:
        print(f"[debt_rotation] starvation_age degraded to None: {e}", file=sys.stderr)
        return None


def lens_rotation_candidates(
    ledger: Optional[List[Dict[str, Any]]] = None,
    spoke_local: Optional[str] = None,
    n: int = 5,
    freshness_threshold_days: float = DEFAULT_FRESHNESS_THRESHOLD_DAYS,
) -> List[Dict[str, Any]]:
    """Stub for Prism's E5 lens-rotation use: shaped exactly like rotate_candidates()
    (Prism wires selection-by-lens fully later; this packet only needs the query to
    exist and return correct data against a fixture ledger). NEVER raises."""
    try:
        led = ledger if ledger is not None else load_ledger(spoke_local)
        return rotate_candidates(led, n=n, freshness_threshold_days=freshness_threshold_days)
    except Exception as e:
        print(f"[debt_rotation] lens_rotation_candidates degraded to []: {e}", file=sys.stderr)
        return []


def _weights_path(hub_local: Optional[str] = None) -> Optional[Path]:
    if hub_local:
        p = Path(hub_local) / "config" / "weights.yaml"
        return p
    # Walk up from this file to find WAI-Harness/hub/local/config/weights.yaml
    here = Path(__file__).resolve()
    for anc in here.parents:
        cand = anc / "hub" / "local" / "config" / "weights.yaml"
        if cand.exists():
            return cand
        if anc.name == "WAI-Harness":
            return anc / "hub" / "local" / "config" / "weights.yaml"
    return None


def exploration_ratio(hub_local: Optional[str] = None) -> float:
    """1-in-5 exploration ratio, human-owned via hub/local/config/weights.yaml
    (C10). Falls back to DEFAULT_EXPLORATION_RATIO with a stderr note if C10
    hasn't landed yet or the key is absent/invalid. NEVER raises."""
    try:
        path = _weights_path(hub_local)
        if path is not None and path.exists():
            try:
                import yaml
                data = yaml.safe_load(path.read_text()) or {}
                val = (data.get("debt_rotation") or {}).get("exploration_ratio")
                if isinstance(val, (int, float)) and 0 < val <= 1:
                    return float(val)
            except Exception as e:
                print(f"[debt_rotation] weights.yaml read failed, using default: {e}", file=sys.stderr)
        return DEFAULT_EXPLORATION_RATIO
    except Exception as e:
        print(f"[debt_rotation] exploration_ratio degraded to default: {e}", file=sys.stderr)
        return DEFAULT_EXPLORATION_RATIO


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="debt_rotation — last-touched debt query")
    ap.add_argument("--root", help="spoke root or spoke/local path")
    ap.add_argument("--rotate", type=int, help="show N oldest rotation candidates")
    ap.add_argument("--starvation-age", action="store_true")
    args = ap.parse_args()
    ledger = load_ledger(args.root)
    if args.rotate:
        print(json.dumps(rotate_candidates(ledger, args.rotate), indent=2))
    elif args.starvation_age:
        print(json.dumps({"starvation_age_days": starvation_age(args.root, ledger=ledger)}, indent=2))
    else:
        print(json.dumps({"exploration_ratio": exploration_ratio(), "pair_count": len(_pairs(ledger))}, indent=2))
