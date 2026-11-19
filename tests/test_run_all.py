"""Pytest entry for the one-runner test suite (B-022).

The hub's overwatch finds a project's tests by discovery: with no package.json
it runs `python -m pytest -q` when a tests/ folder exists. Our checks are shell
scripts and viewer_drop.py, which pytest does not collect, so the overwatch
saw "no tests" and reported 'tests none'. These tests run tests/run_all.sh
(B-012) and each of its checks, so `pytest -q` runs them and reports a count.

Usage: python3 -B -m pytest -q -p no:cacheprovider tests/test_run_all.py
       bash tests/run_all.sh        (the runner itself, unchanged)
"""
import os
import subprocess
import sys

sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
CHECKS = ["validate_rules.sh", "validate_samples.sh", "stranded_ideas.sh",
          "wake_from_track.sh", "viewer_drop.py"]


def _run(*argv):
    return subprocess.run(argv, cwd=ROOT, env=ENV, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=240)


def _check(name):
    cmd = ["python3", "-B"] if name.endswith(".py") else ["bash"]
    r = _run(*cmd, os.path.join("tests", name))
    assert r.returncode == 0, "%s exit %d\n%s%s" % (name, r.returncode, r.stdout[-800:], r.stderr[-800:])


def test_validate_rules():
    _check("validate_rules.sh")


def test_validate_samples():
    _check("validate_samples.sh")


def test_stranded_ideas():
    _check("stranded_ideas.sh")


def test_wake_from_track():
    _check("wake_from_track.sh")


def test_viewer_drop():
    _check("viewer_drop.py")


def test_run_all_lists_every_check():
    """The runner and this file cover the same five checks."""
    text = open(os.path.join(ROOT, "tests", "run_all.sh")).read()
    for name in CHECKS:
        assert name in text, "run_all.sh no longer lists %s" % name


def test_run_all_exits_zero():
    r = _run("bash", "tests/run_all.sh")
    assert r.returncode == 0, "run_all.sh exit %d\n%s%s" % (r.returncode, r.stdout[-800:], r.stderr[-800:])
    assert "ALL PASS" in r.stdout
