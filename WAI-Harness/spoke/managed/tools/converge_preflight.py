#!/usr/bin/env python3
"""converge_preflight.py — "what would converge take from me?" BEFORE anyone
runs it. ALWAYS READ-ONLY: this tool makes zero writes, in any repo, ever. It
is the tool a spoke runs when it is nervous, and it must be safe to run at any
time against any spoke, including one you do not own.

THE BUG THIS ANSWERS (bug-converge-silently-reverts-locally-authored-behavior-v1).
A fix lands in a spoke's LIVE copy of a file. The canonical source is managed/.
Converge/redeploy restores live from managed and the fix is gone, silently.
Basher suffers this repeatedly because it holds a standing population of
locally-authored files under managed/ itself. This tool measures BOTH exposure
surfaces before anything is absorbed:

  A) redeploy exposure — managed/.claude/** vs this spoke's own live .claude/**.
     (harness_converge.classify_live_file / classify_live_tree)
  B) pull exposure — master's canonical managed/ vs this spoke's OWN managed/
     tree. What a `harness_upgrade pull` would silently overwrite today.
     (harness_converge.classify_pull_exposure, delegating to
     harness_upgrade.compute_home_map's direction-aware ahead-ledger)

Operator ruling (s140): converge must CLASSIFY, not just flag — BEHIND (safe
upgrade), AHEAD (undeclared local authorship, at risk), CONFLICT (both sides
moved), or DECLARED_OVERRIDE (pinned in harness-ahead.json, safe). This tool
reports that classification, with line-count diff stats and a sample of the
first differing lines for anything AT RISK, so a human can read the report and
know what is at stake without opening two files. It never arbitrates whether a
change is good — only the operator makes that call.

CLI:
    python3 converge_preflight.py --spoke-root R [--master M] [--json]
Exit: 0 always when the check itself ran (mirrors converge_gate.py's contract:
a preflight must never fail to answer). Exit 2 only on a genuine tool error
(bad --spoke-root, missing managed/ tree).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import harness_converge as hc  # noqa: E402 — resolves after sys.path insert

AT_RISK_STATUSES = ("AHEAD", "CONFLICT")


def preflight(spoke_root, master=None):
    """Pure read. Runs both exposure checks and returns a combined report."""
    spoke_root = str(Path(spoke_root).resolve())

    redeploy = hc.classify_live_tree(spoke_root, master=master)
    pull = hc.classify_pull_exposure(spoke_root, master=master)

    at_risk_redeploy = []
    if redeploy.get("ok"):
        at_risk_redeploy = [f for f in redeploy.get("files", []) if f.get("status") in AT_RISK_STATUSES]

    at_risk_pull = pull.get("ahead_undeclared", []) if pull.get("ok") else []

    report = {
        "ok": bool(redeploy.get("ok")) and bool(pull.get("ok")),
        "spoke_root": spoke_root,
        "redeploy_exposure": {
            "ok": redeploy.get("ok"),
            "error": redeploy.get("error"),
            "checked": redeploy.get("checked"),
            "by_status": redeploy.get("by_status"),
            "at_risk": [
                {"rel": f["rel"], "status": f["status"], "diff": f.get("diff")}
                for f in at_risk_redeploy
            ],
        },
        "pull_exposure": {
            "ok": pull.get("ok"),
            "error": pull.get("error"),
            "identical": len(pull.get("identical", [])),
            "behind_safe_to_pull": len(pull.get("behind", [])),
            "ahead_declared_safe": len(pull.get("ahead_declared", [])),
            "at_risk_undeclared": pull.get("ahead_undeclared", []),
        },
        "summary": {
            "redeploy_at_risk_count": len(at_risk_redeploy),
            "pull_at_risk_count": len(at_risk_pull),
            "total_at_risk": len(at_risk_redeploy) + len(at_risk_pull),
        },
    }
    return report


def _human(report):
    lines = []
    lines.append(f"converge_preflight: {report['spoke_root']}")
    rd = report["redeploy_exposure"]
    if rd.get("ok") is False:
        lines.append(f"  redeploy exposure: ERROR — {rd.get('error')}")
    else:
        lines.append(f"  redeploy exposure (managed/.claude -> live): {rd.get('checked')} checked, "
                     f"{len(rd.get('at_risk', []))} AT RISK")
        for f in rd.get("at_risk", []):
            d = f.get("diff") or {}
            lines.append(f"    [{f['status']}] {f['rel']}  (+{d.get('added_in_live_vs_managed', 0)} "
                         f"-{d.get('removed_from_live_vs_managed', 0)} vs managed)")
    pe = report["pull_exposure"]
    if pe.get("ok") is False:
        lines.append(f"  pull exposure: ERROR — {pe.get('error')}")
    else:
        lines.append(f"  pull exposure (master managed -> this spoke's managed): "
                     f"{len(pe.get('at_risk_undeclared', []))} AT RISK "
                     f"undeclared, {pe.get('ahead_declared_safe')} declared-safe, "
                     f"{pe.get('behind_safe_to_pull')} safe additions")
        for rel in pe.get("at_risk_undeclared", []):
            lines.append(f"    [AHEAD_UNDECLARED] {rel}")
    lines.append(f"  TOTAL AT RISK: {report['summary']['total_at_risk']}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spoke-root", required=True)
    ap.add_argument("--master", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not Path(args.spoke_root).is_dir():
        print(f"converge_preflight: ERROR — no such directory {args.spoke_root}", file=sys.stderr)
        return 2

    report = preflight(args.spoke_root, args.master)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(_human(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
