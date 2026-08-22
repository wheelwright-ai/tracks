"""Tests for thread_landing.py command-condition execution.

One test per VERIFY criterion of impl-thread-landing-conditions-never-execute-v1:

  1. A thread whose command condition passes is absent from the digest after
     one closeout-style clear.
  2. A thread on the deny-list reports DENIED with a reason and stays open.
  3. A hung condition is killed at the timeout and the run still completes.
  4. The wakeup path runs zero command conditions.

Plus the load-bearing asymmetry these guards must never break: absence of
evidence is UNCHECKABLE, never landed.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import thread_landing as tl  # noqa: E402


def _spoke(tmp, threads):
    """Build a minimal spoke tree with a resident digest holding `threads`."""
    local = os.path.join(tmp, "WAI-Harness", "spoke", "local")
    os.makedirs(os.path.join(local, "resident"), exist_ok=True)
    os.makedirs(os.path.join(local, "lugs", "bytype"), exist_ok=True)
    os.makedirs(os.path.join(local, "runtime"), exist_ok=True)
    digest = os.path.join(local, "resident", "digest.json")
    with open(digest, "w") as fh:
        json.dump({"open_threads": threads}, fh)
    return tl.paths(tmp)


class Args:
    def __init__(self, **kw):
        self.run_commands = kw.get("run_commands", False)
        self.command_timeout = kw.get("command_timeout", tl.DEFAULT_COMMAND_TIMEOUT)
        self.dry_run = kw.get("dry_run", False)
        self.format = kw.get("format", "text")


class TestCommandExecution(unittest.TestCase):

    def test_passing_command_lands_and_is_cleared(self):
        """VERIFY 1 — a passing condition leaves the digest after one clear."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _spoke(tmp, [
                {"text": "done thing", "landing": {"kind": "command", "cmd": "true"}},
                {"text": "not done", "landing": {"kind": "command", "cmd": "false"}},
            ])
            rc = tl.cmd_clear(Args(run_commands=True), p)
            self.assertEqual(rc, 0)
            with open(p["digest"]) as fh:
                remaining = json.load(fh)["open_threads"]
            self.assertEqual([t["text"] for t in remaining], ["not done"])

    def test_denied_command_reports_reason_and_stays_open(self):
        """VERIFY 2 — deny-listed conditions are refused, named, and stay open."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _spoke(tmp, [])
            cond = {"kind": "command", "cmd": "bash tests/run.sh"}
            state, why = tl.evaluate(p, {"text": "x", "landing": cond},
                                     run_commands=True)
            self.assertEqual(state, "open")
            self.assertTrue(why.startswith("DENIED"), why)
            self.assertIn("tests/run.sh", why)
            self.assertIn("fixture escape", why)

    def test_deny_list_applies_even_without_run_commands(self):
        """A refusal is visible on the read-only path too, never a silent skip."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _spoke(tmp, [])
            cond = {"kind": "command", "cmd": "git reset --hard origin/main"}
            _state, why = tl.evaluate(p, {"text": "x", "landing": cond},
                                      run_commands=False)
            self.assertTrue(why.startswith("DENIED"), why)

    def test_every_deny_entry_carries_a_reason(self):
        """A denial without a stated reason is an unexplained skip."""
        for needle, reason in tl.COMMAND_DENY_LIST:
            self.assertTrue(needle.strip(), "deny-list needle must be non-empty")
            self.assertGreater(len(reason.strip()), 20,
                               f"deny entry {needle!r} needs a real reason")

    def test_destructive_commands_are_denied(self):
        for cmd in ("git clean -fd", "rm -rf build", "git push --force",
                    "git checkout -- .", "sudo systemctl restart x"):
            denied, reason = tl.screen_command(cmd)
            self.assertTrue(denied, f"{cmd!r} should be denied")
            self.assertTrue(reason.startswith("DENIED"))

    def test_ordinary_command_is_not_denied(self):
        denied, _ = tl.screen_command("python3 -m pytest -q tools/test_x.py")
        self.assertFalse(denied)

    def test_hung_command_is_killed_at_timeout(self):
        """VERIFY 3 — a hung condition is killed and the run still completes."""
        with tempfile.TemporaryDirectory() as tmp:
            p = _spoke(tmp, [{"text": "hangs",
                              "landing": {"kind": "command", "cmd": "sleep 30"}}])
            state, why = tl.evaluate(p, {"text": "hangs",
                                         "landing": {"kind": "command",
                                                     "cmd": "sleep 30"}},
                                     run_commands=True, timeout=1)
            self.assertEqual(state, "open")
            self.assertTrue(why.startswith("TIMEOUT"), why)
            # and the clear path survives it
            rc = tl.cmd_clear(Args(run_commands=True, command_timeout=1), p)
            self.assertEqual(rc, 0)
            with open(p["digest"]) as fh:
                self.assertEqual(len(json.load(fh)["open_threads"]), 1)

    def test_wakeup_path_runs_no_commands(self):
        """VERIFY 4 — without --run-commands nothing is executed."""
        with tempfile.TemporaryDirectory() as tmp:
            marker = os.path.join(tmp, "SHOULD_NOT_EXIST")
            p = _spoke(tmp, [])
            cond = {"kind": "command", "cmd": f"touch {marker}"}
            state, why = tl.evaluate(p, {"text": "x", "landing": cond},
                                     run_commands=False)
            self.assertEqual(state, "open")
            self.assertIn("command not run", why)
            self.assertFalse(os.path.exists(marker),
                             "wakeup posture executed a command condition")

    def test_wakeup_caller_does_not_pass_run_commands(self):
        """The wakeup hook must not be able to reach the executing path."""
        here = os.path.dirname(os.path.abspath(__file__))
        root = tl.find_spoke_root(here)
        hooks = [
            os.path.join(root, ".claude", "hooks", "wakeup-canonical.sh"),
            os.path.join(here, "..", ".claude", "hooks", "wakeup-canonical.sh"),
        ]
        hooks = [h for h in hooks if os.path.isfile(h)]
        if not hooks:
            self.skipTest("wakeup hook not present in this tree")
        for hook in hooks:
            with open(hook) as fh:
                body = fh.read()
            for line in body.splitlines():
                if "thread_landing" in line:
                    self.assertNotIn("--run-commands", line,
                                     f"{hook}: wakeup must never execute "
                                     f"conditions: {line.strip()}")

    def test_absence_is_uncheckable_never_landed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _spoke(tmp, [])
            state, _ = tl.evaluate(p, {"text": "no condition"}, run_commands=True)
            self.assertEqual(state, "uncheckable")

    def test_unknown_kind_is_uncheckable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _spoke(tmp, [])
            state, _ = tl.evaluate(p, {"text": "x", "landing": {"kind": "vibes"}},
                                   run_commands=True)
            self.assertEqual(state, "uncheckable")

    def test_manual_never_lands_even_with_run_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _spoke(tmp, [])
            state, _ = tl.evaluate(p, {"text": "x",
                                       "landing": {"kind": "manual",
                                                   "note": "operator call"}},
                                   run_commands=True)
            self.assertEqual(state, "open")


if __name__ == "__main__":
    unittest.main()
