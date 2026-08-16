#!/usr/bin/env python3
"""ap_review: what an autopilot round actually did, read back from its own record.

WHY THIS FILE EXISTS. ap_review.py shipped in the 4.14.55 cut and was the 83rd managed
tool named by no test, which is what pushed the untested estate one over its ratchet
(kernel/tests/test_estate_coverage.py, CEILING 82) and BLOCKED every push until covered.

That is the ratchet working exactly as designed, so the fix is a real test rather than a
raised ceiling. These execute the summariser and the registry reader; none of them merely
mention a name -- the ratchet's own docstring warns that naming is not executing, and a
test written to satisfy a counter is the Goodhart failure it exists to avoid.

The behaviours pinned here are the ones a reader of the report would be misled by if they
broke: UNRECORDED must not read as a clean zero, and a torn line must not hide the good
rounds around it.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("ap_review", _HERE / "ap_review.py")
ap_review = importlib.util.module_from_spec(_SPEC)
sys.modules["ap_review"] = ap_review
_SPEC.loader.exec_module(ap_review)


def _spoke_with(rounds):
    root = Path(tempfile.mkdtemp())
    record = root / ap_review.RECORD_REL
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text("\n".join(json.dumps(r) for r in rounds) + "\n", encoding="utf-8")
    return root


ROUND_A = {"dispatched": 4, "productive": 3, "tokens_used": 21000,
           "verdicts": [{"lug_id": "L1", "model": "haiku", "productive": False,
                         "why": "touched nothing"}]}
ROUND_B = {"dispatched": 2, "productive": 2, "tokens_used": 9000, "verdicts": []}


class AnUnrecordedSpokeIsNotACleanZero(unittest.TestCase):
    """The distinction the whole report rests on. A spoke that never wrote a round and a
    spoke that ran a round doing nothing produce the same zeros -- so the STATE field is
    what separates them, and collapsing it would read as health over an absence."""

    def test_a_spoke_with_no_record_reports_UNRECORDED(self):
        summary = ap_review._summarise("nowhere", Path(tempfile.mkdtemp()), 5)
        self.assertEqual(summary["state"], "UNRECORDED")
        self.assertEqual(summary["rounds"], 0)

    def test_a_spoke_with_a_record_reports_RECORDED(self):
        summary = ap_review._summarise("here", _spoke_with([ROUND_A]), 5)
        self.assertEqual(summary["state"], "RECORDED")
        self.assertEqual(summary["rounds"], 1)


class TheNumbersAddUp(unittest.TestCase):

    def test_dispatched_productive_and_tokens_sum_across_rounds(self):
        summary = ap_review._summarise("s", _spoke_with([ROUND_A, ROUND_B]), 5)
        self.assertEqual(summary["dispatched"], 6)
        self.assertEqual(summary["productive"], 5)
        self.assertEqual(summary["tokens"], 30000)

    def test_unproductive_is_derived_not_trusted_from_the_record(self):
        summary = ap_review._summarise("s", _spoke_with([ROUND_A, ROUND_B]), 5)
        self.assertEqual(summary["unproductive"], 1)

    def test_every_unproductive_verdict_carries_its_reason_forward(self):
        summary = ap_review._summarise("s", _spoke_with([ROUND_A]), 5)
        self.assertEqual(len(summary["unproductive_reasons"]), 1)
        self.assertEqual(summary["unproductive_reasons"][0]["why"], "touched nothing")

    def test_a_productive_verdict_is_not_listed_as_a_reason(self):
        good = {"dispatched": 1, "productive": 1,
                "verdicts": [{"lug_id": "OK", "productive": True, "why": ""}]}
        self.assertEqual(
            ap_review._summarise("s", _spoke_with([good]), 5)["unproductive_reasons"], [])

    def test_the_limit_keeps_the_MOST_RECENT_rounds(self):
        rounds = [dict(ROUND_B, tokens_used=n) for n in (1, 2, 3, 4, 5)]
        summary = ap_review._summarise("s", _spoke_with(rounds), 2)
        self.assertEqual(summary["rounds"], 2)
        self.assertEqual(summary["tokens"], 9)          # 4 + 5, not 1 + 2


class ATornLineMustNotHideTheGoodRounds(unittest.TestCase):

    def test_a_corrupt_line_is_skipped_and_the_rest_still_count(self):
        root = Path(tempfile.mkdtemp())
        record = root / ap_review.RECORD_REL
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(ROUND_A) + "\n{ torn\n" + json.dumps(ROUND_B) + "\n")
        summary = ap_review._summarise("s", root, 10)
        self.assertEqual(summary["rounds"], 2)
        self.assertEqual(summary["dispatched"], 6)

    def test_blank_lines_are_not_rounds(self):
        root = Path(tempfile.mkdtemp())
        record = root / ap_review.RECORD_REL
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text("\n\n" + json.dumps(ROUND_A) + "\n\n")
        self.assertEqual(ap_review._summarise("s", root, 10)["rounds"], 1)


class TheRegistryReaderIsHonestAboutBadInput(unittest.TestCase):

    def _registry(self, payload):
        path = Path(tempfile.mkdtemp()) / "hub-registry.json"
        path.write_text(payload, encoding="utf-8")
        return path

    def test_only_ACTIVE_spokes_are_returned(self):
        wheels = {"wheels": [
            {"wheel_id": "live", "path": "/tmp/live", "status": "active"},
            {"wheel_id": "gone", "path": "/tmp/gone", "status": "archived"}]}
        names = [s["name"] for s in ap_review._registry_spokes(
            self._registry(json.dumps(wheels)))]
        self.assertEqual(names, ["live"])

    def test_a_wheel_with_no_path_is_skipped_rather_than_crashing(self):
        wheels = {"wheels": [{"wheel_id": "pathless", "status": "active"}]}
        self.assertEqual(
            ap_review._registry_spokes(self._registry(json.dumps(wheels))), [])

    def test_a_corrupt_registry_yields_no_spokes_rather_than_raising(self):
        self.assertEqual(ap_review._registry_spokes(self._registry("{ not json")), [])

    def test_an_absent_registry_yields_no_spokes_rather_than_raising(self):
        self.assertEqual(
            ap_review._registry_spokes(Path("/tmp/definitely-not-here-wai.json")), [])


class RateIsSafeOnAnEmptyDenominator(unittest.TestCase):

    def test_no_rounds_renders_a_dash_not_a_division_error(self):
        self.assertEqual(ap_review._rate(0, 0), "--")

    def test_a_real_rate_renders_as_a_percentage(self):
        self.assertEqual(ap_review._rate(3, 4), "75%")


if __name__ == "__main__":
    unittest.main()
