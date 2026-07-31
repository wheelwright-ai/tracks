"""Test-at-birth for tastegraph_harvest.py — the producer the spoke TasteGraph never had.

The loop downstream of taste.spoke.yaml has worked for months and never received
input: measured on the master, `source_files.spoke: null`, `spoke_entries: 0`.

These pin the properties that make an imperfect miner SAFE, which matters more
here than recall. A harvester that quietly binds behaviour, or that silently
drops the operator's own words, would be worse than the nothing it replaces:

  - a standing instruction is captured, verbatim, with its evidence
  - ordinary task chatter is not captured
  - harvested entries land as `proposed` -> `inferred` -> filtered OUT of
    injection, so nothing this tool writes can act until ratified
  - the same message is never proposed twice (stable content id)
  - slash commands and background notifications are never mined
  - ratify accept/reject flips status and is what makes an entry bind
  - accepted entries compile to spoke_entries > 0 (the loop actually closes)
  - a near-verbatim restatement of existing canon is dropped
  - a merely-similar candidate is KEPT and annotated, never silently judged
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tastegraph_harvest as th  # noqa: E402

yaml = pytest.importorskip("yaml")


def _track(base, session, msgs):
    d = Path(base) / "sessions" / session
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "track.jsonl", "w", encoding="utf-8") as fh:
        for i, m in enumerate(msgs, 1):
            fh.write(json.dumps({"event": "turn", "turn": i, "user_msg": m}) + "\n")


@pytest.fixture
def base(tmp_path):
    b = tmp_path / "local"
    b.mkdir(parents=True)
    return b


STANDING = ("From now on you must always run the verify step before you claim "
            "anything is done, and never report a pass you did not observe.")
CHATTER = "Sounds good, go ahead with that approach and let me know how it goes."


def test_standing_instruction_is_captured_verbatim(base):
    _track(base, "session-1", [STANDING, CHATTER])
    out = th.scan(root=base.parent, base=base)
    assert out["candidates_total"] == 1
    c = out["candidates"][0]
    # Verbatim: a paraphrase is a second artifact that can drift from the first.
    assert c["statement"] == STANDING
    assert "standing" in c["markers"] and "obligation" in c["markers"]


def test_ordinary_chatter_is_not_captured(base):
    _track(base, "session-1", [CHATTER, "That looks right to me, thanks."])
    assert th.scan(root=base.parent, base=base)["candidates_total"] == 0


def test_proposed_entries_are_not_binding(base):
    _track(base, "session-1", [STANDING])
    th.propose(root=base.parent, base=base)
    doc = yaml.safe_load((base / "taste.spoke.yaml").read_text())
    entry = doc["entries"][0]
    assert entry["status"] == "proposed"

    # The whole safety argument rests on this mapping holding downstream.
    import compile_tastegraph as ct
    assert ct._confidence_from_status("proposed") == "inferred"
    assert ct._confidence_from_status("accepted") == "verified"


def test_same_message_is_never_proposed_twice(base):
    _track(base, "session-1", [STANDING])
    assert len(th.propose(root=base.parent, base=base)["proposed"]) == 1
    # Re-run over the same corpus: already-known, so nothing new.
    second = th.propose(root=base.parent, base=base)
    assert second["proposed"] == []
    assert second["already_known"] == 1
    doc = yaml.safe_load((base / "taste.spoke.yaml").read_text())
    assert len(doc["entries"]) == 1


def test_slash_commands_and_notifications_are_never_mined(base):
    _track(base, "session-1", [
        "/wai-closeout — never stop until it is done and always push",
        "[background notification: agent finished] you must always check this",
    ])
    assert th.scan(root=base.parent, base=base)["candidates_total"] == 0


def test_ratify_accept_is_what_makes_an_entry_bind(base):
    _track(base, "session-1", [STANDING])
    cid = th.propose(root=base.parent, base=base)["proposed"][0]

    res = th.ratify(cid, accept=True, root=base.parent, base=base, category="work_style")
    assert res["ok"] and res["status"] == "accepted"
    e = yaml.safe_load((base / "taste.spoke.yaml").read_text())["entries"][0]
    assert e["status"] == "accepted" and e["category"] == "work_style"
    assert e["accepted_at"]


def test_ratify_reject_marks_and_does_not_delete(base):
    _track(base, "session-1", [STANDING])
    cid = th.propose(root=base.parent, base=base)["proposed"][0]
    assert th.ratify(cid, accept=False, root=base.parent, base=base)["status"] == "rejected"
    e = yaml.safe_load((base / "taste.spoke.yaml").read_text())["entries"][0]
    # Kept, so the id stays known and the message is never re-proposed.
    assert e["status"] == "rejected" and e["rejected_at"]


def test_ratify_unknown_id_reports_rather_than_silently_passing(base):
    _track(base, "session-1", [STANDING])
    th.propose(root=base.parent, base=base)
    assert th.ratify("harvest-doesnotexist", accept=True,
                     root=base.parent, base=base)["ok"] is False


def test_accepted_entry_closes_the_loop_to_spoke_entries(tmp_path):
    """The whole point: `spoke_entries: 0` stops being 0.

    Runs the REAL compiler over a real v4 tree rather than asserting on the
    harvester's own output. Every other test here could pass while the loop stayed
    open — this is the one that proves an accepted entry reaches the graph the
    session actually reads.
    """
    import compile_tastegraph as ct

    root = tmp_path / "spoke"
    base = root / "WAI-Harness" / "spoke" / "local"
    base.mkdir(parents=True)
    (base / "WAI-State.json").write_text(json.dumps({"wheel": {"name": "testspoke"}}))

    _track(base, "session-1", [STANDING])
    before = ct.compile_tastegraph(root, mode="v4-only", write=True)
    assert before["counts"]["spoke_entries"] == 0, "fixture must start from the real defect"

    cid = th.propose(root=root, base=base)["proposed"][0]
    proposed = ct.compile_tastegraph(root, mode="v4-only", write=True)

    # spoke_entries counts entries SOURCED from the spoke, regardless of status --
    # so merely proposing moves it off 0. That makes it a Goodhart target for this
    # tool: a harvester graded on spoke_entries could "fix" the metric by proposing
    # noise and never ratifying anything. Pinned here so the trap stays visible,
    # and `status()` reports in_force separately as the number that actually binds.
    assert proposed["counts"]["spoke_entries"] == 1
    prop_pref = next(p for p in proposed["graph"]["preferences"] if p["id"] == cid)
    assert prop_pref["confidence"] == "inferred"   # NOT in force

    th.ratify(cid, accept=True, root=root, base=base)
    after = ct.compile_tastegraph(root, mode="v4-only", write=True)
    assert after["counts"]["spoke_entries"] >= 1
    assert any(p["confidence"] == "verified" and p["id"] == cid
               for p in after["graph"]["preferences"])

    # The number that means the loop actually closed.
    assert th.status(root=root, base=base)["in_force"] == 1


def test_near_verbatim_restatement_of_canon_is_dropped(base, monkeypatch):
    _track(base, "session-1", [STANDING])
    # Canon that IS the candidate -> similarity 1.0, above DROP_CEILING.
    monkeypatch.setattr(th, "user_canon_ids",
                        lambda root, b: [("existing-pref", th._canon_tokens(STANDING))])
    out = th.scan(root=base.parent, base=base)
    assert out["candidates_total"] == 0
    assert out["dropped_as_org_canon"] == 1


def test_merely_similar_candidate_is_kept_and_annotated(base, monkeypatch):
    monkeypatch.setattr(th, "user_canon_ids", lambda root, b: [
        ("unrelated-pref", th._canon_tokens(
            "Deployment rollbacks require an approved change window and a named owner.")),
        ("similar-pref", th._canon_tokens(
            "Always confirm the release window before scheduling downstream work.")),
    ])
    _track(base, "session-1", [STANDING])
    out = th.scan(root=base.parent, base=base)
    c = out["candidates"][0]
    # Kept — the tool annotates the overlap rather than pretending to adjudicate it,
    # because measured similarity could not separate duplicate from unrelated.
    assert out["dropped_as_org_canon"] == 0
    assert c["nearest_existing"] == "similar-pref"
    assert 0.0 < c["nearest_similarity"] < th.DROP_CEILING


def test_unrelated_candidate_reports_no_nearest_rather_than_a_fake_one(base, monkeypatch):
    monkeypatch.setattr(th, "user_canon_ids", lambda root, b: [
        ("unrelated-pref", th._canon_tokens(
            "Deployment rollbacks require an approved change window and a named owner.")),
    ])
    _track(base, "session-1", [STANDING])
    c = th.scan(root=base.parent, base=base)["candidates"][0]
    # An honest absence. Naming a nearest match at similarity 0 would invite the
    # ratifier to dismiss a genuinely new preference as a duplicate.
    assert c["nearest_existing"] is None
    assert c["nearest_similarity"] == 0.0


def test_cap_bounds_the_review_queue(base):
    _track(base, "session-1", [
        f"You must always do thing number {i} and never skip it going forward."
        for i in range(12)
    ])
    out = th.scan(root=base.parent, base=base, cap=3)
    assert out["candidates_total"] == 12
    assert len(out["candidates"]) == 3


def test_status_reports_loop_health(base):
    _track(base, "session-1", [STANDING])
    cid = th.propose(root=base.parent, base=base)["proposed"][0]
    assert th.status(root=base.parent, base=base)["by_status"] == {"proposed": 1}
    th.ratify(cid, accept=True, root=base.parent, base=base)
    assert th.status(root=base.parent, base=base)["by_status"] == {"accepted": 1}


def test_malformed_track_lines_do_not_stop_the_scan(base):
    d = base / "sessions" / "session-1"
    d.mkdir(parents=True)
    (d / "track.jsonl").write_text(
        "not json\n"
        + json.dumps("a bare string, not an object") + "\n"
        + json.dumps({"event": "turn", "turn": 1, "user_msg": STANDING}) + "\n",
        encoding="utf-8")
    assert th.scan(root=base.parent, base=base)["candidates_total"] == 1
