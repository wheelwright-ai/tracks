#!/usr/bin/env python3
"""anthropic_usage_read: the parser, and the browser route that turned out to be blocked.

WHY THIS FILE EXISTS. The tool was the 83rd managed tool named by no test, which is one
over the ratchet in kernel/tests/test_estate_coverage.py and blocks every push. Covering
it is the fix; raising the ceiling would loosen a guard whose whole value is that it only
moves one way.

WHAT IS ACTUALLY WORTH PINNING. The browser route is BLOCKED -- claude.ai serves a human
verification challenge to a Playwright profile, correctly -- and the supported path is now
statusline_limits_poll.sh reading Claude Code's own payload. So the live behaviour to
protect is the PARSER's honesty, not the scraping: it must convert used to remaining, and
it must return NOTHING rather than a zero when it cannot read the page.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "anthropic_usage_read", Path(__file__).resolve().parent / "anthropic_usage_read.py")
aur = importlib.util.module_from_spec(_SPEC)
sys.modules["anthropic_usage_read"] = aur
_SPEC.loader.exec_module(aur)


class ThePageReportsUsedTheGateStoresRemaining(unittest.TestCase):
    """Confusing these does not round the gate. It inverts it."""

    def test_a_five_hour_window_is_converted_to_remaining(self):
        got = aur._extract("Current 5-hour session\n32% used\nResets at 7:00 PM")
        self.assertEqual(got["five_hour"]["pct_left"], 68)
        self.assertEqual(got["five_hour"]["pct_used_on_page"], 32)

    def test_the_reset_hint_is_carried(self):
        got = aur._extract("Current 5-hour session\n32% used\nResets at 7:00 PM")
        self.assertEqual(got["five_hour"]["resets_at"], "7:00 PM")

    def test_all_three_windows_parse_independently(self):
        got = aur._extract(
            "Current 5-hour session\n10% used\n"
            "Weekly all-model usage\n61% used\n"
            "Weekly Opus usage\n78% used\n")
        self.assertEqual(got["five_hour"]["pct_left"], 90)
        self.assertEqual(got["weekly"]["pct_left"], 39)
        self.assertEqual(got["opus"]["pct_left"], 22)

    def test_a_window_with_no_reset_hint_still_parses(self):
        got = aur._extract("Weekly Opus usage\n78% used")
        self.assertEqual(got["opus"]["pct_left"], 22)
        self.assertEqual(got["opus"]["resets_at"], "")


class AnUnreadablePageYieldsNothingNotZero(unittest.TestCase):
    """A parser that writes on a failed read is worse than one that stops: it manufactures
    a confident number out of a page it never understood."""

    def test_unrecognised_text_yields_no_windows(self):
        self.assertEqual(aur._extract("some unrelated page"), {})

    def test_empty_text_yields_no_windows(self):
        self.assertEqual(aur._extract(""), {})

    def test_a_label_with_no_percentage_is_not_a_reading(self):
        self.assertEqual(aur._extract("Current 5-hour session\nplenty left"), {})

    def test_a_percentage_with_no_label_is_not_a_reading(self):
        self.assertEqual(aur._extract("42% used"), {})


class TheBlockedRouteIsRecordedInTheSource(unittest.TestCase):
    """The file's value is now the finding it carries. If someone strips that paragraph,
    the next session re-tries the browser or reaches for an anti-detect tool."""

    def test_the_source_states_the_route_is_blocked(self):
        text = (Path(__file__).resolve().parent / "anthropic_usage_read.py").read_text()
        self.assertIn("BLOCKED IN PRACTICE", text)

    def test_the_source_names_the_supported_alternative(self):
        text = (Path(__file__).resolve().parent / "anthropic_usage_read.py").read_text()
        self.assertIn("wai budget --record", text)


if __name__ == "__main__":
    unittest.main()
