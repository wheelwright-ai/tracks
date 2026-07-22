#!/usr/bin/env python3
"""Does this spoke still WORK after the upgrade? — the check md5 cannot make.

THE HOLE THIS FILLS. harness_upgrade.py is a verify-apply-verify engine and both
verifies are md5 comparisons against the master. They answer "did the bytes copy
correctly" and never "does this spoke still function". A cut that copies
perfectly and breaks every tool passes every check the engine has. That is not
hypothetical: a cut this week rolled 28 command files back two months on a live
spoke, and the md5 verify would have passed it happily, because the bytes it
copied were exactly the bytes it meant to copy.

OPERATOR MODEL (2026-07-22, correcting the Gardener reading): the Gardener was
deprecated deliberately. Its replacement is not a scheduled sweep — it is
validation that RUNS AT UPGRADE TIME and is validated BY THE SPOKE THAT TOOK THE
UPGRADE. Validation belongs at the moment of change, run by the party that took
it, because that is the only point where cause and effect are still adjacent.

WHY NOT "JUST RUN THE TEST SUITE". The 1600-test managed suite is deliberately
NOT distributed (operator decision 2026-07-14; the retire mechanism exists to
pull the 172 orphaned copies back out of the fleet). Those tests also resolve
their repo root from their own file location, so running master's copies would
test master, not the spoke that took the upgrade — the answer would be
confidently about the wrong wheel.

So validation is built from checks that travel WITH the harness and run AGAINST
the receiving spoke:

    syntax      every distributed tool compiles — catches the whole class of
                "copied perfectly, imports broken", which is what actually
                breaks a spoke after a bad cut, and what md5 structurally cannot see
    paths       no distributed tool reaches for a v3 path on a v4-only spoke —
                the specific way this fleet has broken before, twice
    entrypoints the tools a ceremony calls on the next wakeup actually import
    health      spoke_health_check's own structural verdict
    selftest    the spoke-side test_*.py that ARE distributed, when pytest exists

A check that cannot run reports SKIPPED and says why. It never reports PASS.
That distinction is the whole point: this module exists because something was
reporting success on evidence that could not support it.
"""

import argparse
import json
import os
import py_compile
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS, FAIL, SKIP = "pass", "fail", "skip"

# The tools a ceremony calls on the very next wakeup. If one of these cannot be
# imported, the spoke is broken in a way its operator meets immediately.
ENTRYPOINTS = ("wai_paths.py", "lug_utils.py", "spoke_health_check.py",
               "generate_wakeup_brief.py", "harness_upgrade.py")

# v3 shapes that must not appear in a distributed tool running on a v4-only spoke.
V3_MARKERS = ('"WAI-Spoke/', "'WAI-Spoke/", "/WAI-Spoke/")


def _managed(spoke_root):
    return Path(spoke_root) / "WAI-Harness" / "spoke" / "managed"


def _is_v4_only(spoke_root):
    return not (Path(spoke_root) / "WAI-Spoke").is_dir()


def _result(name, status, detail, evidence=None):
    return {"check": name, "status": status, "detail": detail, "evidence": evidence or []}


def check_syntax(spoke_root):
    """Every distributed .py compiles. The cheapest check that md5 cannot make."""
    tools = _managed(spoke_root) / "tools"
    if not tools.is_dir():
        return _result("syntax", SKIP, f"no managed tools dir at {tools}")
    broken = []
    count = 0
    # A real temp file, not /dev/null: py_compile refuses to write a .pyc onto a
    # non-regular file and raises for EVERY input, which reads as "216 of 216 tools
    # are broken" — a validator's own false positive, caught by running it.
    with tempfile.TemporaryDirectory() as tmp:
        cfile = os.path.join(tmp, "out.pyc")
        for path in sorted(tools.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            count += 1
            try:
                py_compile.compile(str(path), cfile=cfile, doraise=True)
            except py_compile.PyCompileError as exc:
                broken.append(f"{path.name}: {str(exc).splitlines()[0][:160]}")
            except (OSError, ValueError) as exc:
                broken.append(f"{path.name}: unreadable ({exc})")
    if broken:
        return _result("syntax", FAIL, f"{len(broken)} of {count} tool(s) do not compile", broken[:20])
    return _result("syntax", PASS, f"{count} tool(s) compile")


def check_paths(spoke_root):
    """No distributed tool reaches for a v3 path on a v4-only spoke.

    Delegates to v3_path_lint.py, which already owns this question along with the
    allowlist of accepted debt. A second, competing definition of "v3 violation"
    living here would drift from the cut gate's and start failing upgrades the
    gate itself allows — the same one-question-two-answers problem the retire
    mechanism was built to end.
    """
    if not _is_v4_only(spoke_root):
        return _result("paths", SKIP,
                       "spoke has a WAI-Spoke tree (v3 coexist) — v3 paths are legitimate here")
    managed = _managed(spoke_root)
    lint = managed / "tools" / "v3_path_lint.py"
    if not lint.is_file():
        return _result("paths", SKIP, "v3_path_lint.py not distributed here")
    proc = subprocess.run([sys.executable, str(lint), "--managed", str(managed), "--json"],
                          capture_output=True, text=True, timeout=300)
    try:
        report = json.loads(proc.stdout or "{}")
    except ValueError:
        return _result("paths", FAIL, "v3 lint produced no parseable verdict",
                       [(proc.stderr or proc.stdout or "")[-300:]])
    violations = report.get("violations") or {}
    if violations:
        evidence = [f"{f}:{hits[0][0]}" for f, hits in list(violations.items())[:20] if hits]
        return _result("paths", FAIL,
                       f"{len(violations)} tool(s) hardcode a v3 path on a v4-only spoke",
                       evidence)
    debt = len(report.get("allowlisted_debt") or {})
    return _result("paths", PASS,
                   f"no v3 violations{f' ({debt} file(s) of allowlisted debt)' if debt else ''}")


def check_entrypoints(spoke_root):
    """The tools the next wakeup will call actually import, in a clean interpreter."""
    tools = _managed(spoke_root) / "tools"
    present = [name for name in ENTRYPOINTS if (tools / name).is_file()]
    if not present:
        return _result("entrypoints", SKIP, "none of the known entrypoints are present")
    failures = []
    for name in present:
        module = name[:-3]
        proc = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            capture_output=True, text=True, timeout=120,
            env=dict(os.environ, PYTHONPATH=str(tools)), cwd=str(spoke_root))
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip().splitlines()[-1:] or ["import failed"]
            failures.append(f"{name}: {tail[0][:160]}")
    if failures:
        return _result("entrypoints", FAIL,
                       f"{len(failures)} of {len(present)} entrypoint(s) fail to import", failures)
    return _result("entrypoints", PASS, f"{len(present)} entrypoint(s) import cleanly")


def check_health(spoke_root):
    """The spoke's own structural verdict, in its own words."""
    tool = _managed(spoke_root) / "tools" / "spoke_health_check.py"
    if not tool.is_file():
        return _result("health", SKIP, "spoke_health_check.py not distributed here")
    proc = subprocess.run([sys.executable, str(tool), str(spoke_root), "--quick"],
                          capture_output=True, text=True, timeout=300)
    out = (proc.stdout or "") + (proc.stderr or "")
    verdict = next((ln.strip() for ln in out.splitlines() if "Health:" in ln), None)
    # RED fails the upgrade; YELLOW does not. Gating on the exit code instead would
    # fail every upgrade on every spoke — the tool exits non-zero for YELLOW, and a
    # gate that always fires is one people learn to route around.
    if "Health: RED" in out:
        tail = [ln.strip() for ln in out.splitlines() if "FAIL" in ln or "Health:" in ln]
        return _result("health", FAIL, "spoke health check reports RED", tail[:10])
    if verdict is None:
        return _result("health", SKIP, "health check produced no verdict line",
                       [(out or "")[-200:]])
    return _result("health", PASS, verdict)


def check_selftest(spoke_root):
    """The spoke-side test_*.py that ARE distributed. Absent pytest is a SKIP."""
    tools = _managed(spoke_root) / "tools"
    tests = sorted(str(p) for p in tools.glob("test_*.py")) if tools.is_dir() else []
    if not tests:
        return _result("selftest", SKIP, "no distributed spoke-side tests present")
    try:
        import pytest  # noqa: F401
    except ImportError:
        return _result("selftest", SKIP, "pytest not installed on this spoke — cannot run, so not claiming pass")
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", *tests],
                          capture_output=True, text=True, timeout=900, cwd=str(spoke_root))
    summary = [ln for ln in (proc.stdout or "").splitlines() if "passed" in ln or "failed" in ln]
    if proc.returncode != 0:
        return _result("selftest", FAIL, "distributed spoke tests failed",
                       summary[-3:] or [(proc.stdout or "")[-400:]])
    return _result("selftest", PASS, summary[-1] if summary else "spoke tests passed")


CHECKS = (check_syntax, check_paths, check_entrypoints, check_health, check_selftest)


def validate(spoke_root, checks=CHECKS):
    """Run the validation suite against a spoke. Never raises.

    outcome is `pass` only when at least one check RAN and none failed. An
    all-skipped run is `skip`, never `pass` — the case this whole module exists
    to stop being reported as success.
    """
    results = []
    for check in checks:
        try:
            results.append(check(spoke_root))
        except subprocess.TimeoutExpired:
            results.append(_result(check.__name__.replace("check_", ""), FAIL, "check timed out"))
        except Exception as exc:  # a broken check is a failed check, not a silent one
            results.append(_result(check.__name__.replace("check_", ""), FAIL,
                                   f"check raised: {type(exc).__name__}: {exc}"))
    failed = [r for r in results if r["status"] == FAIL]
    ran = [r for r in results if r["status"] != SKIP]
    outcome = FAIL if failed else (PASS if ran else SKIP)
    return {
        "outcome": outcome,
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "spoke_root": str(Path(spoke_root).resolve()),
        "checks": results,
        "failed": [r["check"] for r in failed],
        "skipped": [r["check"] for r in results if r["status"] == SKIP],
        "summary": (f"{len(ran) - len(failed)}/{len(ran)} check(s) passed"
                    + (f", {len(failed)} FAILED: {', '.join(r['check'] for r in failed)}" if failed else "")
                    + (f" ({len(results) - len(ran)} skipped)" if len(results) != len(ran) else "")),
    }


def main():
    ap = argparse.ArgumentParser(description="validate that a spoke still works")
    ap.add_argument("spoke_root", nargs="?", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    report = validate(args.spoke_root)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        icon = {PASS: "PASS", FAIL: "FAIL", SKIP: "SKIP"}
        print(f"VALIDATION — {report['spoke_root']}")
        for r in report["checks"]:
            print(f"  [{icon[r['status']]}] {r['check']:<12} {r['detail']}")
            for line in r["evidence"][:5]:
                print(f"        {line}")
        print(f"  => {report['outcome'].upper()}: {report['summary']}")
    return 1 if report["outcome"] == FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
