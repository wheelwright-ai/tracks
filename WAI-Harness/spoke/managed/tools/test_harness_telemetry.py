"""Tests for harness_telemetry.py — the enforcement half of the contract.

Canonical means enforceable (operator ruling, 2026-08-01). A schema that lives
only in a docstring is documentation; these tests are what make it a contract.

The load-bearing assertions:
  * REQUIRED_FIELDS matches what model_usage_logger actually emits. A schema
    that drifts from its writer is worse than none — it certifies a shape
    nobody produces.
  * Absence is never rendered as zero. An uninstrumented spoke must read as
    UNINSTRUMENTED, not as clean.
  * Version truth reports disagreement rather than picking a winner quietly.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness_telemetry as ht  # noqa: E402
import model_usage_logger as mul  # noqa: E402


def _row(**kw):
    base = {
        "event": "model_usage", "ts": "2026-08-01T12:00:00+00:00",
        "spoke_id": "test", "harness_version": "4.14.34",
        "provider": "anthropic", "model": "claude-sonnet-5",
        "task_type": "implementation", "tokens_in": 100, "tokens_out": 200,
        "cost_estimate": 0.5, "duration_ms": 1000,
    }
    base.update(kw)
    return base


class TestSchemaContract(unittest.TestCase):

    def test_logger_emits_every_required_field(self):
        """The writer and the schema must not drift apart."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "usage.jsonl")
            orig_file, orig_dir = mul.USAGE_FILE, mul.USAGE_DIR
            mul.USAGE_FILE = path
            mul.USAGE_DIR = type(orig_dir)(tmp)
            try:
                mul.log_usage(provider="anthropic", model="claude-sonnet-5",
                              task_type="implementation", tokens_in=1,
                              tokens_out=2, cost_estimate=0.1, duration_ms=5)
            finally:
                mul.USAGE_FILE, mul.USAGE_DIR = orig_file, orig_dir
            with open(path) as fh:
                row = json.loads(fh.readline())
        for field in ht.REQUIRED_FIELDS:
            self.assertIn(field, row, f"logger does not emit required field {field!r}")

    def test_logger_emits_error_fields(self):
        """Failure capture is part of the contract, not an optional extra."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "usage.jsonl")
            orig_file, orig_dir = mul.USAGE_FILE, mul.USAGE_DIR
            mul.USAGE_FILE = path
            mul.USAGE_DIR = type(orig_dir)(tmp)
            try:
                mul.log_usage(provider="anthropic", model="x", task_type="t",
                              error="rate limited", error_kind="429")
            finally:
                mul.USAGE_FILE, mul.USAGE_DIR = orig_file, orig_dir
            row = json.loads(open(path).readline())
        self.assertEqual(row["error"], "rate limited")
        self.assertEqual(row["error_kind"], "429")

    def test_harness_version_is_stamped_from_the_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            md = os.path.join(tmp, "WAI-Harness", "spoke", "managed")
            os.makedirs(md)
            json.dump({"harness_version": "9.9.9"},
                      open(os.path.join(md, "MANIFEST.json"), "w"))
            self.assertEqual(mul.running_harness_version(tmp), "9.9.9")

    def test_missing_manifest_reports_none_not_a_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(mul.running_harness_version(tmp))


class TestAbsenceIsNeverZero(unittest.TestCase):

    def test_empty_usage_reports_zero_rows_and_no_totals(self):
        rep = ht.analyze([])
        self.assertEqual(rep["rows"], 0)
        self.assertNotIn("cost_total", rep)

    def test_rows_without_error_field_are_unobservable_not_successes(self):
        rep = ht.analyze([_row(), _row()])
        self.assertEqual(rep["errors"]["observable_rows"], 0)
        self.assertEqual(rep["errors"]["unobservable_rows"], 2)
        self.assertIsNone(rep["errors"]["rate"],
                          "an error RATE over zero observable rows is a fabrication")

    def test_error_rate_computed_only_over_observable_rows(self):
        rows = [_row(error=None), _row(error="boom", error_kind="oom"), _row()]
        rep = ht.analyze(rows)
        self.assertEqual(rep["errors"]["observable_rows"], 2)
        self.assertEqual(rep["errors"]["failures"], 1)
        self.assertEqual(rep["errors"]["rate"], 0.5)
        self.assertEqual(rep["errors"]["unobservable_rows"], 1)

    def test_absent_log_is_distinguished_from_empty_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(ht._read_jsonl(os.path.join(tmp, "nope.jsonl")))
            p = os.path.join(tmp, "empty.jsonl")
            open(p, "w").close()
            self.assertEqual(ht._read_jsonl(p), [])

    def test_malformed_row_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "u.jsonl")
            with open(p, "w") as fh:
                fh.write(json.dumps(_row()) + "\n")
                fh.write("{not json\n")
                fh.write(json.dumps(_row()) + "\n")
            self.assertEqual(len(ht._read_jsonl(p)), 2)


class TestFindings(unittest.TestCase):

    def test_unpriced_tokens_are_flagged_as_a_cost_floor(self):
        rows = [_row(cost_estimate=1.0),
                _row(cost_estimate=0, tokens_out=50_000, source="track_backfill")]
        rep = ht.analyze(rows)
        self.assertEqual(rep["cost_coverage"]["unpriced_rows_with_tokens"], 1)
        self.assertEqual(rep["cost_coverage"]["unpriced_output_tokens"], 50_000)
        levers = [i["lever"] for i in rep["inefficiencies"]]
        self.assertIn("cost coverage", levers)

    def test_model_alias_is_flagged_and_raw_value_preserved(self):
        rep = ht.analyze([_row(model="opus"), _row(model="claude-opus-5")])
        self.assertIn("attribution", [i["lever"] for i in rep["inefficiencies"]])
        models = {m["model"] for m in rep["by_model"]}
        self.assertIn("claude-opus (unversioned)", models)
        self.assertIn("claude-opus-5", models)

    def test_unversioned_rows_report_as_unknown_not_folded_into_newest(self):
        rep = ht.analyze([_row(harness_version=None), _row()])
        vers = dict(rep["by_harness_version"])
        self.assertEqual(vers.get("unknown"), 1)
        self.assertEqual(rep["version_unattributed"], 1)

    def test_missing_quality_ratings_are_flagged(self):
        rep = ht.analyze([_row(), _row()])
        self.assertIn("quality signal", [i["lever"] for i in rep["inefficiencies"]])
        self.assertIsNone(rep["quality_coverage"]["mean"])

    def test_every_finding_states_a_reason(self):
        rows = [_row(model="opus", cost_estimate=0, tokens_out=9999,
                     source="x", rework_required=True)]
        for i in ht.analyze(rows)["inefficiencies"]:
            self.assertTrue(i.get("lever"))
            self.assertTrue(i.get("finding"))
            self.assertGreater(len(i.get("why", "")), 30,
                               f"finding {i['lever']!r} has no usable reason")


class TestVersionTruth(unittest.TestCase):

    def _tree(self, tmp, manifest=None, version=None, state=None):
        md = os.path.join(tmp, "WAI-Harness", "spoke", "managed")
        os.makedirs(md, exist_ok=True)
        if manifest:
            json.dump({"harness_version": manifest},
                      open(os.path.join(md, "MANIFEST.json"), "w"))
        if version:
            open(os.path.join(tmp, "WAI-Harness", "VERSION"), "w").write(version)
        local = os.path.join(tmp, "WAI-Harness", "spoke", "local")
        os.makedirs(local, exist_ok=True)
        if state:
            json.dump({"_harness": {"harness_version_v4": state}},
                      open(os.path.join(local, "WAI-State.json"), "w"))

    def test_disagreement_is_reported_not_silently_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._tree(tmp, manifest="4.14.34", version="4.14.32", state="4.1.0")
            vt = ht.version_truth(tmp)
            self.assertEqual(vt["authority"], "4.14.34")
            self.assertFalse(vt["agree"])
            self.assertEqual(set(vt["disagreements"]), {"version_file", "wai_state"})

    def test_agreement_reports_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._tree(tmp, manifest="4.14.34", version="4.14.34", state="4.14.34")
            vt = ht.version_truth(tmp)
            self.assertTrue(vt["agree"])
            self.assertEqual(vt["disagreements"], {})

    def test_manifest_is_the_authority_not_the_version_file(self):
        """VERSION is stamped only by a pull; content can advance without it."""
        with tempfile.TemporaryDirectory() as tmp:
            self._tree(tmp, manifest="5.0.0", version="1.0.0")
            self.assertEqual(ht.version_truth(tmp)["authority"], "5.0.0")


if __name__ == "__main__":
    unittest.main()
