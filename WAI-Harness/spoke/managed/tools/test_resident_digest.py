"""Tests for resident_digest.py fold semantics.

Traces to change-basher-resident-voice-pilot-v1 (the Resident pilot). The
pilot's verify list names roll idempotency explicitly; the retirement tests
cover the defect the pilot found live in session 119 — a thread the operator
had explicitly retired came back on the next fold, because the fold re-reads
the raw track and nothing recorded the ruling.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import resident_digest as rd


def _entry(session, turns, open_texts):
    return {
        "session": session,
        "turns": turns,
        "started": None,
        "ended": None,
        "focus": None,
        "phases": [],
        "decisions": [],
        "insights": [],
        "open": [
            {"turn": 1, "text": t, "id": rd.thread_id(t)} for t in open_texts
        ],
    }


class FoldTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.p = {
            "local": os.path.join(self.tmp, "local"),
            "resident": os.path.join(self.tmp, "resident"),
            "digest": os.path.join(self.tmp, "resident", "digest.json"),
            "droplog": os.path.join(self.tmp, "resident", "drops.jsonl"),
            "sessions": os.path.join(self.tmp, "sessions"),
        }
        os.makedirs(self.p["resident"], exist_ok=True)
        self.digest = rd.load_digest(self.p)

    def test_new_digest_carries_retired_threads(self):
        self.assertEqual(self.digest["retired_threads"], [])

    def test_fold_is_a_noop_when_session_did_not_grow(self):
        e = _entry("session-A", 3, ["alpha thread"])
        self.digest, did = rd.fold(self.digest, e, self.p)
        self.assertTrue(did)
        self.digest, did = rd.fold(self.digest, _entry("session-A", 3, ["alpha thread"]), self.p)
        self.assertFalse(did, "re-folding an unchanged session must be a no-op")

    def test_fold_refolds_when_session_grew(self):
        self.digest, _ = rd.fold(self.digest, _entry("session-A", 3, ["alpha"]), self.p)
        self.digest, did = rd.fold(self.digest, _entry("session-A", 5, ["alpha", "beta"]), self.p)
        self.assertTrue(did, "a grown session must re-fold so the digest is not stale")
        texts = {t["text"] for t in self.digest["open_threads"]}
        self.assertEqual(texts, {"alpha", "beta"})

    def test_retired_thread_is_not_resurrected_by_a_later_fold(self):
        """The session-119 defect: the raw track still carries the thread."""
        keep, gone = "keep me", "retire me"
        self.digest, _ = rd.fold(self.digest, _entry("session-A", 3, [keep, gone]), self.p)
        self.assertEqual(len(self.digest["open_threads"]), 2)

        self.digest["retired_threads"] = [{
            "id": rd.thread_id(gone), "text": gone, "session": "session-A",
            "reason": "operator ruling", "retired_at": "2026-08-01T00:00:00+00:00",
        }]
        # The track is unchanged and still carries BOTH threads.
        self.digest, did = rd.fold(self.digest, _entry("session-A", 6, [keep, gone]), self.p)
        self.assertTrue(did)
        texts = {t["text"] for t in self.digest["open_threads"]}
        self.assertEqual(texts, {keep}, "a retired thread must not come back on a re-fold")

    def test_retiring_logs_a_drop_with_a_reason(self):
        gone = "retire me"
        self.digest, _ = rd.fold(self.digest, _entry("session-A", 3, [gone]), self.p)
        self.digest["retired_threads"] = [{
            "id": rd.thread_id(gone), "text": gone, "session": "session-A",
            "reason": "operator ruling", "retired_at": "2026-08-01T00:00:00+00:00",
        }]
        self.digest, _ = rd.fold(self.digest, _entry("session-A", 6, [gone]), self.p)
        drops = [json.loads(l) for l in open(self.p["droplog"]) if l.strip()]
        reasons = {d["reason"] for d in drops}
        self.assertIn("operator-retired-thread", reasons)
        self.assertTrue(all(d.get("reason") for d in drops), "every drop carries a reason")

    def test_retirement_also_suppresses_other_sessions_copies(self):
        """The same thread is often re-stated by a LATER session."""
        gone = "retire me"
        self.digest, _ = rd.fold(self.digest, _entry("session-A", 3, [gone]), self.p)
        self.digest["retired_threads"] = [{
            "id": rd.thread_id(gone), "text": gone, "session": "session-A",
            "reason": "operator ruling", "retired_at": "2026-08-01T00:00:00+00:00",
        }]
        self.digest, _ = rd.fold(self.digest, _entry("session-B", 2, ["something else"]), self.p)
        texts = {t["text"] for t in self.digest["open_threads"]}
        self.assertNotIn(gone, texts, "folding ANY session must drop retired threads")

    def test_landing_conditions_survive_a_refold(self):
        t = "alpha thread"
        self.digest, _ = rd.fold(self.digest, _entry("session-A", 3, [t]), self.p)
        self.digest["open_threads"][0]["landing"] = {"kind": "command", "cmd": "true"}
        self.digest, _ = rd.fold(self.digest, _entry("session-A", 5, [t]), self.p)
        self.assertEqual(self.digest["open_threads"][0]["landing"],
                         {"kind": "command", "cmd": "true"})


if __name__ == "__main__":
    unittest.main()
