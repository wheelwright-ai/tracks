#!/usr/bin/env python3
"""spoke_position_map.py — the standard orienting instrument (spec-spoke-position-map-v1).

FUSES five existing deterministic scorers into ONE legible map. It adds NO new scoring
logic — every number comes from the tool that already owns it:

  position  spoke_integrity_score.compute_score   0-100 composite  = where the spoke IS
  bar+gaps  compute_capability_gaps               CG resolved bar minus a survey
                                                  = where it needs to GO (roadmap)
  oracle    grounded_oracle_map.coverage          deterministic proof-of-movement
  priority  lathe_score (subprocess)              strategic weight = gap ordering
  narrative generate_knowme artifact (KnowMe.md)  self-portrait pointer

Best-effort + presence-guarded: any missing/unavailable source yields
{"value": null, "reason": ...} so the map runs cheaply every session and NEVER fails
closed (the exhaustive brownfield I/O-vector audit is the reserved deep variant, not this).
Read-only; writes one signal seat — spoke/local/maintenance/position-map.json — mirroring
the hygiene / lug-staleness seat pattern so consumers (wakeup brief, autopilot) find it
uniformly. `lathe_score` parse_args at import time, so it is invoked by subprocess, never
imported.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _local_base(spoke_root: Path) -> Path:
    """Resolve the v4 spoke-local base (holds maintenance/, lugs/, WAI-State.json)."""
    if spoke_root.name == "local" and (spoke_root / "WAI-State.json").exists():
        return spoke_root
    cand = spoke_root / "WAI-Harness" / "spoke" / "local"
    return cand if cand.exists() else spoke_root


def _null(reason: str) -> dict:
    return {"value": None, "reason": reason}


# ── the five sections (each presence-guarded, best-effort) ──────────────────

def section_position(spoke_root: Path) -> dict:
    """POSITION — 0-100 composite integrity score (where the spoke IS)."""
    try:
        import spoke_integrity_score as sis
        r = sis.compute_score(str(spoke_root))
        return {"value": r["score"], "max": r.get("max", 100), "grade": r.get("grade"),
                "dims": {k: v.get("score") for k, v in (r.get("dimensions") or {}).items()}}
    except Exception as e:  # noqa: BLE001 — best-effort by contract
        return _null(f"spoke_integrity_score unavailable: {e}")


def _read_cg_effective(spoke_root: Path):
    """The resolved CapabilitiesGraph bar (resolver output). Generated runtime state —
    absent until resolve_capabilities_graph.py / materialize_cg.py has run.

    The tool-relative fallback applies ONLY when spoke_root IS this tool's own repo:
    consulting it for a foreign/tmp spoke_root leaks canon state into that root's
    map (test-pollution class — surfaced at s260710-235336 convergence when the
    real runtime file materialized and a tmp-rooted test started seeing it)."""
    candidates = [spoke_root / "WAI-Harness" / "spoke" / "managed" / "runtime"
                  / "capabilities-effective.json"]
    fallback = _HERE.parent / "runtime" / "capabilities-effective.json"
    try:
        own_repo = _HERE.parents[3] == Path(spoke_root).resolve()
    except (IndexError, OSError):
        own_repo = False
    if own_repo:
        candidates.append(fallback)
    for p in candidates:
        if p.exists():
            try:
                d = json.loads(p.read_text())
                return d.get("entries", d) if isinstance(d, dict) else d, str(p)
            except Exception:  # noqa: BLE001
                return None, str(p)
    return None, None


def _read_survey(base: Path):
    """The capability survey {cap_id: {present, certified}} the gap diff needs. No canonical
    per-spoke producer is wired yet on every spoke, so this is commonly absent -> gaps null."""
    p = base / "maintenance" / "capability-survey.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return None
    return None


def section_bar_and_gaps(spoke_root: Path, base: Path) -> tuple[dict, dict]:
    """BAR — the CG mandated/recommended target; GAPS — bar minus survey, priority-ordered.

    Uses compute_capability_gaps directly so the fused gap set is byte-identical to the
    standalone scorer (no drift — an acceptance guarantee)."""
    effective, eff_path = _read_cg_effective(spoke_root)
    if not effective:
        reason = "no capabilities-effective.json (run resolve_capabilities_graph.py to materialize the bar)"
        return _null(reason), _null(reason)
    mandated = sum(1 for e in effective if e.get("tier") == "mandated")
    recommended = sum(1 for e in effective if e.get("tier") == "recommended")
    bar = {"value": {"cg_mandated": mandated, "cg_recommended": recommended},
           "source": eff_path}
    survey = _read_survey(base)
    if survey is None:
        return bar, _null("no capability-survey.json (survey of what is actually present is absent)")
    try:
        import compute_capability_gaps as ccg
        g = ccg.compute_capability_gaps(effective, survey)
        gaps = {"value": {"blocking": g["blocking"], "soft": g["soft"],
                          "declined": g["declined"], "roadmap": g["roadmap"]},
                "blocking_count": len(g["blocking"]), "soft_count": len(g["soft"])}
        return bar, gaps
    except Exception as e:  # noqa: BLE001
        return bar, _null(f"compute_capability_gaps failed: {e}")


def section_oracle(spoke_root: Path) -> dict:
    """ORACLE — deterministic proof-of-movement: grounded-loop coverage over impl lugs."""
    try:
        import grounded_oracle_map as gom
        c = gom.coverage(str(spoke_root))
        sec = {"value": c.get("ratio"), "grounded": c.get("grounded"),
               "total": c.get("total"), "hard": True,
               "loop": "grounded-loop-coverage",
               "reading": f"{c.get('grounded')}/{c.get('total')} impl lugs carry a metric_target"}
        if c.get("ratio") is None:  # no impl lugs to ground yet — a valid null, stated plainly
            sec["reason"] = "no impl lugs present to ground (coverage ratio undefined at 0 lugs)"
        return sec
    except Exception as e:  # noqa: BLE001
        return _null(f"grounded_oracle_map unavailable: {e}")


def section_priority(spoke_root: Path, hub_path: str | None) -> dict:
    """PRIORITY — lathe strategic weight (orders the gap roadmap). Subprocess-isolated
    because lathe_score.py parse_args at import time; requires the hub registry."""
    hub = hub_path or os.environ.get("WAI_HUB_PATH", "")
    if not hub:
        return _null("no hub path (lathe portfolio weight needs the hub registry); pass --hub-path")
    try:
        r = subprocess.run([sys.executable, str(_HERE / "lathe_score.py"), "--hub-path", hub],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return _null(f"lathe_score exited {r.returncode}: {(r.stderr or '').strip()[:120]}")
        return {"value": "available", "detail": "lathe portfolio computed; order gaps by strategic weight",
                "note": "per-spoke weight in lathe_score.py stdout table"}
    except Exception as e:  # noqa: BLE001
        return _null(f"lathe_score unavailable: {e}")


def section_narrative(spoke_root: Path) -> dict:
    """NARRATIVE — pointer to the KnowMe self-portrait (not regenerated; that costs an API call)."""
    for p in (spoke_root / "KnowMe.md",
              spoke_root / "WAI-Harness" / "dev" / "root-docs" / "KnowMe.md"):
        if p.exists():
            return {"value": str(p.relative_to(spoke_root)) if p.is_relative_to(spoke_root) else str(p)}
    return _null("no KnowMe.md (run generate_knowme.py to build the self-portrait)")


# ── fusion + render ─────────────────────────────────────────────────────────

def compose(spoke_root: str = ".", hub_path: str | None = None) -> dict:
    root = Path(spoke_root).resolve()
    base = _local_base(root)
    bar, gaps = section_bar_and_gaps(root, base)
    return {
        "schema": "spoke-position-map/v1",
        "ts": _now_iso(),
        "spoke_root": str(root),
        "position": section_position(root),
        "bar": bar,
        "gaps": gaps,
        "oracles": section_oracle(root),
        "priority": section_priority(root, hub_path),
        "narrative_ref": section_narrative(root),
    }


def _top_gaps(gaps: dict, n: int = 3) -> list:
    v = (gaps or {}).get("value") or {}
    return (v.get("roadmap") or [])[:n]


def render(m: dict) -> str:
    """One-screen human view — labels each part plainly (position / bar / gaps / oracle)
    so it reads as a MAP, not a score dump."""
    L = []
    pos = m.get("position", {})
    if pos.get("value") is not None:
        dims = pos.get("dims") or {}
        dim_s = " ".join(f"{k}:{v}" for k, v in dims.items())
        L.append(f"POSITION (where it is): {pos['value']}/{pos.get('max', 100)} "
                 f"[{pos.get('grade')}]  {dim_s}")
    else:
        L.append(f"POSITION: n/a — {pos.get('reason')}")

    bar = m.get("bar", {})
    if bar.get("value") is not None:
        b = bar["value"]
        L.append(f"THE BAR (where to go): CG {b['cg_mandated']} mandated / "
                 f"{b['cg_recommended']} recommended")
    else:
        L.append(f"THE BAR: n/a — {bar.get('reason')}")

    gaps = m.get("gaps", {})
    if gaps.get("value") is not None:
        L.append(f"GAPS (roadmap): {gaps.get('blocking_count', 0)} blocking / "
                 f"{gaps.get('soft_count', 0)} soft — top {min(3, len(_top_gaps(gaps)))}:")
        for g in _top_gaps(gaps, 3):
            L.append(f"    [{g.get('priority')}] {g.get('action')}")
    else:
        L.append(f"GAPS: n/a — {gaps.get('reason')}")

    orc = m.get("oracles", {})
    if orc.get("value") is not None:
        L.append(f"ORACLE (proof of movement): {orc.get('reading')} "
                 f"(ratio {orc.get('value')}, deterministic)")
    else:
        L.append(f"ORACLE: n/a — {orc.get('reason')}")

    nar = m.get("narrative_ref", {})
    L.append(f"NARRATIVE: {nar.get('value') or ('n/a — ' + str(nar.get('reason')))}")
    return "\n".join(L)


def write_seat(m: dict, base: Path) -> Path:
    seat = base / "maintenance" / "position-map.json"
    seat.parent.mkdir(parents=True, exist_ok=True)
    tmp = seat.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=2) + "\n")
    os.replace(tmp, seat)
    return seat


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Spoke Position Map — one fused where-it-is / "
                                 "where-to-go / oracle-proof instrument (spec-spoke-position-map-v1).")
    ap.add_argument("--spoke-root", default=".")
    ap.add_argument("--hub-path", default=None)
    ap.add_argument("--json", action="store_true", help="print the full map JSON")
    ap.add_argument("--render", action="store_true", help="print the one-screen human view")
    ap.add_argument("--no-write", action="store_true", help="do not write the maintenance seat")
    args = ap.parse_args(argv)

    m = compose(args.spoke_root, args.hub_path)
    if not args.no_write:
        seat = write_seat(m, _local_base(Path(args.spoke_root).resolve()))
        m["_seat"] = str(seat)
    if args.render:
        print(render(m))
    if args.json or not args.render:
        print(json.dumps(m, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
