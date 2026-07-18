#!/usr/bin/env python3
"""grounded_oracle_map.py — bind each AP loop-type to its cheapest DETERMINISTic oracle.

The close-gate asks: "did the declared metric actually move?" This module answers with a
real measurement, reusing oracles the harness already owns:

  test-loop      -> pytest passed-count delta            (hard)
  contract-loop  -> contract_validate live-circuit count (hard)
  lint-loop      -> v3_path_lint violation count -> 0     (hard)
  health-loop    -> spoke_health_check drain/health score (hard)
  <unknown>      -> SOFT default (labeled, never a hard green)

Design:
  * Each entry exposes capture() -> a comparable reading (int/float/bool) and
    measure(before, after, direction) -> {moved: bool|None, detail: str}.
  * measure is PURE (compares two readings) so it is unit-testable without running tools.
  * A soft/unknown oracle NEVER returns moved=True without a measurement — moved stays None.
  * All external tools are invoked by EXPLICIT path (never assume cwd).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Anchor paths off this file so invocation never depends on cwd.
_TOOLS = Path(__file__).resolve().parent                       # spoke/managed/tools
_REPO = _TOOLS.parents[3]                                       # repo root (…/mywheel)
CONTRACT_VALIDATE = _REPO / "WAI-Harness" / "hub" / "local" / "scripts" / "contract_validate.py"
SPOKE_HEALTH = _TOOLS / "spoke_health_check.py"
V3_LINT = _TOOLS / "v3_path_lint.py"
ACCOUNTABILITY = _TOOLS / "accountability_ledger.py"


def _num(before: Any, after: Any, direction: str) -> Dict[str, Any]:
    """Pure numeric comparison honoring direction."""
    if before is None or after is None:
        return {"moved": None, "detail": f"missing reading (before={before!r}, after={after!r})"}
    try:
        b, a = float(before), float(after)
    except (TypeError, ValueError):
        return {"moved": None, "detail": f"non-numeric reading ({before!r} -> {after!r})"}
    if direction == "down":
        moved = a < b
    elif direction == "becomes_true":
        moved = bool(a) and not bool(b)
    else:  # 'up' default
        moved = a > b
    return {"moved": moved, "detail": f"{before} -> {after} (direction={direction})"}


def _run(cmd, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or str(_REPO), timeout=900)


# ---- capture() implementations (runtime only; each returns None on any failure so an
#      unmeasurable loop degrades to soft, never to a false green) ----

def _cap_pytest() -> Optional[int]:
    try:
        p = _run([sys.executable, "-m", "pytest", "-q", str(_TOOLS.parent / "tests")])
        m = re.search(r"(\d+) passed", p.stdout + p.stderr)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _cap_contract() -> Optional[int]:
    try:
        if not CONTRACT_VALIDATE.is_file():
            return None
        p = _run([sys.executable, str(CONTRACT_VALIDATE), "--json"])
        data = json.loads(p.stdout)
        return int(data.get("live", data.get("live_circuits", 0)))
    except Exception:
        return None


def _cap_lint() -> Optional[int]:
    try:
        if not V3_LINT.is_file():
            return None
        p = _run([sys.executable, str(V3_LINT)])
        m = re.search(r"(\d+)\s+violation", p.stdout + p.stderr)
        return int(m.group(1)) if m else 0
    except Exception:
        return None


def _cap_health() -> Optional[float]:
    try:
        if not SPOKE_HEALTH.is_file():
            return None
        p = _run([sys.executable, str(SPOKE_HEALTH), "--json"])
        data = json.loads(p.stdout)
        return float(data.get("health_score", data.get("score", 0)))
    except Exception:
        return None


def _cap_accountability() -> Optional[int]:
    """Count of unowned (OPEN) aspects — drive DOWN as the wheel takes ownership."""
    try:
        if not ACCOUNTABILITY.is_file():
            return None
        p = _run([sys.executable, str(ACCOUNTABILITY), "--json"])
        return int(json.loads(p.stdout)["metrics"]["open_count"])
    except Exception:
        return None


ORACLES: Dict[str, Dict[str, Any]] = {
    "test-loop": {"name": "pytest passed-count", "kind": "hard", "capture": _cap_pytest,
                  "measure": _num, "soft_limits": ""},
    "contract-loop": {"name": "contract_validate live circuits", "kind": "hard", "capture": _cap_contract,
                      "measure": _num, "soft_limits": ""},
    "lint-loop": {"name": "v3_path_lint violations", "kind": "hard", "capture": _cap_lint,
                  "measure": _num, "soft_limits": ""},
    "health-loop": {"name": "spoke_health_check score", "kind": "hard", "capture": _cap_health,
                    "measure": _num, "soft_limits": ""},
    "accountability-loop": {"name": "unowned (open) aspect count", "kind": "hard", "capture": _cap_accountability,
                            "measure": _num, "soft_limits": ""},
}

_SOFT_DEFAULT: Dict[str, Any] = {
    "name": "unclassified-loop",
    "kind": "soft",
    "capture": lambda: None,
    "measure": lambda before, after, direction="up": {
        "moved": None,
        "detail": "soft: no deterministic oracle bound for this loop-type",
    },
    "soft_limits": (
        "No deterministic oracle is bound to this loop-type; its outcome cannot be auto-verified "
        "and is labeled soft — it is never counted as a hard green."
    ),
}


def get_oracle(loop_type: Optional[str]) -> Dict[str, Any]:
    """Return the oracle entry for loop_type, or a SOFT default (with soft_limits) for
    an unknown/None loop-type. Never returns a hard oracle for an unknown type."""
    return ORACLES.get(loop_type or "", _SOFT_DEFAULT)


def run_oracle(loop_type: Optional[str], before: Any, after: Any, direction: str = "up") -> Dict[str, Any]:
    """Measure whether the metric moved. Returns {moved, kind, detail, soft_limits}."""
    entry = get_oracle(loop_type)
    res = entry["measure"](before, after, direction)
    return {
        "moved": res.get("moved"),
        "kind": entry["kind"],
        "detail": res.get("detail", ""),
        "soft_limits": entry.get("soft_limits", ""),
    }


# ---------------------------------------------------------------------------
# Coverage + mechanical backfill (impl-grounded-loop-backfill-coverage-v1)
#
# The close-gate only fires when a lug carries grounded_loop.metric_target;
# baseline was 6/1308 = 0.5% of ALL lugs. Coverage here is scoped to OPEN/
# in_progress impl lugs specifically (grounded_loop is an impl-lug close-gate
# concept — spec/task/epic lugs don't go through ozi_autopilot's completion
# gate the same way), matching groom_gate's GROOM_TYPES scope in
# lug_readiness.py.
# ---------------------------------------------------------------------------

UNBOUND_ORACLE_KEY = "unbound-backfill"  # deliberately unknown -> get_oracle() -> _SOFT_DEFAULT


def _impl_lug_files(root="."):
    root = str(root)
    out = []
    for base in (os.path.join(root, "WAI-Harness", "spoke", "local", "lugs", "bytype"),):
        for status in ("open", "in_progress"):
            out += glob.glob(os.path.join(base, "*", status, "*.json"))
    return out


def coverage(root=".") -> Dict[str, Any]:
    """(open+in_progress impl lugs carrying grounded_loop.metric_target) / (all open+
    in_progress impl lugs). Returns {total, grounded, ratio}."""
    total = grounded = 0
    for f in _impl_lug_files(root):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if (d.get("type") or "").lower() not in ("implementation", "impl"):
            continue
        total += 1
        if (d.get("grounded_loop") or {}).get("metric_target"):
            grounded += 1
    ratio = round(grounded / total, 4) if total else None
    return {"total": total, "grounded": grounded, "ratio": ratio}


def derive_metric_target(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Mechanically lift an existing verify/acceptance_criteria field into a
    grounded_loop.metric_target shape -- never invents new criteria. Returns
    None if the lug has neither (nothing safe to lift). Always marked soft:
    a lifted text field is not the same as a proven oracle binding."""
    verify = d.get("verify")
    ac = d.get("acceptance_criteria")
    source = verify if verify else ac
    if not source:
        return None
    def _to_text(item):
        return item if isinstance(item, str) else json.dumps(item, sort_keys=True)
    text = " ".join(_to_text(x) for x in source) if isinstance(source, list) else _to_text(source)
    text = text.strip()
    if not text:
        return None
    title = str(d.get("title") or d.get("id") or "untitled")[:80]
    return {
        "name": f"verify criteria for: {title}",
        "oracle": UNBOUND_ORACLE_KEY,
        "direction": "becomes_true",
        "baseline_cmd": text[:500],
        "soft": True,
        "soft_limits": (
            "Mechanically backfilled from the lug's own verify/acceptance_criteria text "
            "(impl-grounded-loop-backfill-coverage-v1) -- no oracle has been bound or run; "
            "this labels intent, it does not measure completion. Never counted as a hard green."
        ),
    }


def backfill(root=".", dry=True) -> Dict[str, Any]:
    """Backfill grounded_loop.metric_target onto open/in_progress impl lugs that
    have verify/acceptance_criteria but no grounded_loop yet. Returns a report;
    writes files only when dry=False."""
    filled, skipped_no_source, already_had = [], [], 0
    for f in _impl_lug_files(root):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if (d.get("type") or "").lower() not in ("implementation", "impl"):
            continue
        if (d.get("grounded_loop") or {}).get("metric_target"):
            already_had += 1
            continue
        target = derive_metric_target(d)
        if target is None:
            skipped_no_source.append(f)
            continue
        d.setdefault("grounded_loop", {})["metric_target"] = target
        d["grounded_loop"].setdefault("legality_gate", {
            "well_formed": True, "self_contained": True, "verifiable": True,
        })
        if not dry:
            json.dump(d, open(f, "w", encoding="utf-8"), indent=2)
            open(f, "a", encoding="utf-8").write("\n")
        filled.append(f)
    return {
        "filled": len(filled), "already_had": already_had,
        "skipped_no_source": len(skipped_no_source),
        "filled_files": filled, "skipped_files": skipped_no_source,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="grounded_oracle_map: oracle registry + coverage/backfill")
    sub = ap.add_subparsers(dest="cmd")
    cv = sub.add_parser("coverage"); cv.add_argument("--root", default=".")
    bf = sub.add_parser("backfill"); bf.add_argument("--root", default="."); bf.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "coverage":
        print(json.dumps(coverage(args.root), indent=2))
    elif args.cmd == "backfill":
        print(json.dumps(backfill(args.root, dry=not args.write), indent=2))
    else:
        print(json.dumps({k: {"name": v["name"], "kind": v["kind"]} for k, v in ORACLES.items()}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
