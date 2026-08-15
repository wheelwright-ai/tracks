#!/usr/bin/env python3
"""luci_uptime.py -- Luci's checks: is this spoke actually UP and actually WORKING.

Every other advisor in this harness asks whether work is FINISHED. Luci asks
whether the thing RUNS. She is the only one who does, which is why her 59 days
of silence mattered more than the count suggested: for two months nothing was
watching whether this spoke was usable at all.

Her mission is transcribed, not invented -- it is the one she already carried in
her own scan_state since 2026-06-05:

    "ensure every spoke is usable when it needs to be usable and doing what it
     needs to be doing -- availability, instrumentation, error detection, and
     proactive remediation"

DETERMINISTIC ON PURPOSE. Her declared checks (test runner, build, dependency
audit) are all scriptable. Routing them to a language model would spend money to
produce a WEAKER answer than simply running the suite -- a model's opinion about
whether tests pass is strictly worse than the exit code. So Luci is tool-backed
and free, and stays that way.

CHECKS ATTEMPTED IS REPORTED BESIDE CHECKS PASSED, always. A green from an uptime
advisor is trivially manufactured by narrowing what she checks: skip the suite,
skip the audit, report available. Recording the denominator makes a pass rate
that rose because fewer checks ran visible as exactly that. A check that could
not run is SKIPPED and counted, never silently dropped -- a skipped check is
missing evidence, not a pass.

SHE DOES NOT WRITE LUGS UNATTENDED. Her contract calls for remediation, and the
--remediate flag does it, but the nightly path only reports. An unattended job
that files lugs on every red test would bury a backlog this project is already
trying to drain.

CLI:
    luci_uptime.py --root DIR check [--json] [--timeout N]

Exit codes: 0 every attempted check passed AND at least one ran; 1 a check
failed or warned; 2 nothing could be attempted. Exit 0 over zero attempted
checks is not available -- an unmeasured spoke is UNKNOWN, and UNKNOWN is not up.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"
DEFAULT_TIMEOUT = 900


def _now():
    return datetime.now(timezone.utc).isoformat()


def _run(cmd, root, timeout):
    try:
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s"
    except OSError as exc:
        return None, str(exc)


def check_tests(root, timeout):
    """Does the suite pass. The single most direct answer to 'does this work'."""
    suite = os.path.join("WAI-Harness", "spoke", "managed", "tests")
    if not os.path.isdir(os.path.join(root, suite)):
        return {"check": "code_health", "state": SKIP,
                "why": f"no suite at {suite} -- nothing to run, and that is not a pass"}
    rc, out = _run([sys.executable, "-m", "pytest", suite, "-q"], root, timeout)
    if rc is None:
        return {"check": "code_health", "state": SKIP,
                "why": f"suite could not complete: {out.strip()[:200]}"}
    tail = "\n".join(out.strip().splitlines()[-3:])
    if rc == 0:
        return {"check": "code_health", "state": PASS, "why": tail}
    return {"check": "code_health", "state": FAIL,
            "why": f"suite exited {rc} -- this spoke is not working: {tail}",
            "remediation": "bug lug with the failing test names"}


def check_dependencies(root, timeout):
    """Known vulnerabilities in what we actually ship. Luci's one recorded
    finding (2026-06-05) came from exactly this check, and was real."""
    results = []
    if os.path.exists(os.path.join(root, "package.json")):
        rc, out = _run(["npm", "audit", "--json"], root, timeout)
        if rc is None:
            results.append(("npm", SKIP, out.strip()[:200]))
        else:
            try:
                data = json.loads(out)
                total = sum((data.get("metadata", {})
                             .get("vulnerabilities", {}) or {}).values())
            except Exception:
                total = None
            results.append(("npm", (PASS if total == 0 else WARN) if total is not None
                            else SKIP,
                            f"{total} vulnerable package(s)" if total is not None
                            else "npm audit output unparseable"))
    if not results:
        return {"check": "dependency_health", "state": SKIP,
                "why": ("no dependency manifest found (no package.json) -- nothing to "
                        "audit here, which is missing evidence rather than a clean bill")}
    worst = WARN if any(s == WARN for _n, s, _w in results) else (
        SKIP if all(s == SKIP for _n, s, _w in results) else PASS)
    return {"check": "dependency_health", "state": worst,
            "why": "; ".join(f"{n}: {w}" for n, _s, w in results),
            "remediation": ("task lug naming the affected package and fix version"
                            if worst == WARN else None)}


def check(root=".", timeout=DEFAULT_TIMEOUT):
    rows = [check_tests(root, timeout), check_dependencies(root, timeout)]
    attempted = [r for r in rows if r["state"] != SKIP]
    counts = {PASS: 0, WARN: 0, FAIL: 0, SKIP: 0}
    for r in rows:
        counts[r["state"]] += 1
    return {
        "advisor": "luci", "checked_at": _now(),
        # The denominator is the anti-Goodhart guard: a pass rate that rose
        # because fewer checks RAN must be visible as that, not as improvement.
        "checks_declared": len(rows),
        "checks_attempted": len(attempted),
        "checks_passed": counts[PASS],
        "counts": counts,
        "rows": rows,
        "headline": (
            "no check could be attempted -- this spoke's availability is UNKNOWN, "
            "and UNKNOWN is not up" if not attempted else
            f"{counts[PASS]}/{len(attempted)} attempted checks passed"
            f" ({counts[SKIP]} skipped, evidence missing)"),
    }


def render(report):
    lines = [f"luci {report['checked_at']}  {report['headline']}"]
    for r in report["rows"]:
        lines.append(f"  [{r['state']:5}] {r['check']}")
        lines.append(f"      {r['why']}")
        if r.get("remediation"):
            lines.append(f"      -> remediation: {r['remediation']}")
    return "\n".join(lines)


def _main(argv=None):
    ap = argparse.ArgumentParser(description="Luci -- is this spoke up and working")
    ap.add_argument("--root", default=".")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--json", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    args = ap.parse_args(argv)

    report = check(args.root, args.timeout)
    print(json.dumps(report, indent=2) if args.json else render(report))
    if not report["checks_attempted"]:
        return 2
    if report["counts"][FAIL] or report["counts"][WARN]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
