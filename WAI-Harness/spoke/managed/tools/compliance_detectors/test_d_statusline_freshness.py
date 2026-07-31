"""Tests for the cross-turn statusline staleness detector.

THE TEST THAT MATTERS is `test_real_session_20260728_0016`. The preference was
written after s138 to stop exactly this failure, a detector shipped, and it
happened again anyway — four consecutive turns stamped with turn 1's rendering —
because the shipped detector judged each line alone. So the acceptance bar here is
not "the regexes work on invented strings": it is that the detector fires on the
actual transcript where the actual regression occurred. Everything else in this
file exists to prove it does not fire on things that are fine.
"""

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.dirname(_HERE)
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from compliance_detectors import d_statusline_freshness as D  # noqa: E402

REAL_TRANSCRIPT = os.path.expanduser(
    "~/.claude/projects/-home-mario-projects-wheelwright-mywheel/"
    "e07dffe9-69ec-4660-998a-f787d85da6fc.jsonl")


def run(blocks):
    """Evaluate a whole transcript the way the oracle does: block by block.

    A fresh `pref` object per call is what scopes the detector's cross-block
    state to this run — the same contract `evaluate()` satisfies by re-reading
    the graph into new dicts on every invocation.
    """
    pref = {"id": "wai-track-statusline-fidelity"}
    out = []
    for i, text in enumerate(blocks):
        for v in D.detect(text, pref):
            out.append({**v, "block": i})
    return out


def line(turn, time, model="claude-opus-5", version="v4.14.18", date="Mon, Jul 27, 2026"):
    return f"Turn {turn} | {date} | {time} | {model} | {version} | Gold: +0"


# ---- the acceptance test ----------------------------------------------------

def test_real_session_20260728_0016():
    """The detector must catch the real four-turn copy-forward."""
    if not os.path.isfile(REAL_TRANSCRIPT):
        pytest.skip(f"real transcript not present on this machine: {REAL_TRANSCRIPT}")

    from tastegraph_compliance import load_transcript
    blocks = load_transcript(REAL_TRANSCRIPT)
    assert blocks, "transcript produced no assistant text blocks"

    violations = run(blocks)
    assert violations, "detector found nothing in a session known to be stale"

    # The staleness is the repeated 5:17 PM PDT rendering, so the evidence must
    # point at 5:17 lines carrying turn numbers past the first.
    stale_time = [v for v in violations if "5:17 PM PDT" in v["evidence"]]
    assert stale_time, f"5:17 PM PDT staleness not reported; got {violations}"

    # It is proven by the clock-stall rule, naming the earlier turns it collides
    # with — not by anything that could have been decided from one line alone.
    assert any("identical across turns" in v["note"] for v in stale_time)

    # Turns 3 and 4 are the provable ones (turn 2 is a legitimate same-minute
    # possibility and is deliberately not claimed).
    caught = {v["evidence"].split(" |")[0] for v in stale_time}
    assert {"Turn 3", "Turn 4"} <= caught, caught

    # Turn 1 is never blamed: there is nothing before it to have copied.
    assert not any(v["evidence"].startswith("Turn 1 |") for v in violations)


def test_real_session_also_catches_the_repeated_turn_number():
    """Turn 4 is emitted twice in that session — the counter did not advance."""
    if not os.path.isfile(REAL_TRANSCRIPT):
        pytest.skip("real transcript not present on this machine")

    from tastegraph_compliance import load_transcript
    violations = run(load_transcript(REAL_TRANSCRIPT))
    assert any("did not advance" in v["note"] for v in violations), violations


def test_real_session_through_the_oracle():
    """End to end: the extension is wired onto the operator's real preference."""
    if not os.path.isfile(REAL_TRANSCRIPT):
        pytest.skip("real transcript not present on this machine")

    import tastegraph_compliance as TC
    assert D.detect in TC.EXTRA_DETECTORS.get("wai-track-statusline-fidelity", []), \
        "extension not routed onto the base preference"

    pref = {"id": "wai-track-statusline-fidelity", "category": "output_format"}
    results = TC.evaluate(TC.load_transcript(REAL_TRANSCRIPT), [pref])
    r = results["wai-track-statusline-fidelity"]
    assert r["verdict"] == "violated"
    assert any("identical across turns" in v["note"] for v in r["violations"])


# ---- must not fire ----------------------------------------------------------

def test_clean_transcript_does_not_fire():
    blocks = [
        "Done.\n" + line(1, "5:17 PM PDT", model="unknown"),
        "Next.\n" + line(2, "5:59 PM PDT"),
        "Then.\n" + line(3, "6:47 PM PDT", version="v4.14.20"),
        "Last.\n" + line(4, "8:34 PM PDT", version="v4.14.21"),
    ]
    assert run(blocks) == []


def test_first_statusline_never_fires():
    """Turn 1's 'unknown' model is correct — no assistant message exists yet."""
    assert run([line(1, "5:17 PM PDT", model="unknown")]) == []


def test_two_turns_in_the_same_minute_are_allowed():
    """A one-word reply inside the same minute is ordinary, not proof."""
    blocks = [line(1, "5:17 PM PDT"), line(2, "5:17 PM PDT"), line(3, "5:18 PM PDT")]
    assert run(blocks) == []


def test_version_change_alone_does_not_fire():
    """Versions move, including backwards on a checkout — never proof by itself."""
    blocks = [line(1, "5:17 PM PDT", version="v4.14.21"),
              line(2, "5:59 PM PDT", version="v4.14.18")]
    assert run(blocks) == []


def test_code_block_is_exempt():
    blocks = [
        line(1, "5:17 PM PDT"),
        "Here is the template:\n```\n" + line(1, "5:17 PM PDT") + "\n"
        + line(1, "5:17 PM PDT") + "\n" + line(1, "5:17 PM PDT") + "\n```",
        line(2, "5:59 PM PDT"),
    ]
    assert run(blocks) == []


def test_verbatim_operator_quotation_is_exempt():
    """Quoting the hook's own renderings back is documentation, not stamping."""
    blocks = [
        line(1, "5:17 PM PDT"),
        "The hook supplied, per turn:\n\n"
        + line(1, "5:17 PM PDT") + "\n"
        + line(2, "5:17 PM PDT") + "\n"
        + line(3, "5:17 PM PDT") + "\n",
        "> " + line(1, "5:17 PM PDT"),
        "`" + line(1, "5:17 PM PDT") + "`",
        line(2, "5:59 PM PDT"),
    ]
    assert run(blocks) == []


# ---- must fire --------------------------------------------------------------

def test_clock_running_backwards_fires():
    blocks = [line(1, "5:17 PM PDT"), line(2, "5:59 PM PDT"), line(3, "5:17 PM PDT")]
    v = run(blocks)
    assert any("runs backwards" in x["note"] for x in v), v


def test_turn_number_stall_fires():
    blocks = [line(1, "5:17 PM PDT"), line(2, "5:59 PM PDT"), line(2, "6:47 PM PDT")]
    v = run(blocks)
    assert any("did not advance" in x["note"] for x in v), v


def test_wholesale_copy_of_the_whole_line_fires():
    same = line(1, "5:17 PM PDT", model="unknown")
    v = run([same, same, same])
    assert any("did not advance" in x["note"] for x in v), v


def test_three_turns_sharing_one_timestamp_fires_on_the_third_only():
    blocks = [line(1, "5:17 PM PDT"), line(2, "5:17 PM PDT"), line(3, "5:17 PM PDT")]
    v = [x for x in run(blocks) if "identical across turns" in x["note"]]
    assert len(v) == 1 and v[0]["block"] == 2, v


# ---- state hygiene ----------------------------------------------------------

def test_a_fresh_run_is_not_polluted_by_the_previous_one():
    dirty = [line(1, "5:17 PM PDT"), line(2, "5:17 PM PDT"), line(3, "5:17 PM PDT")]
    assert run(dirty), "setup: the dirty run should have fired"
    # A separate run means a separate pref object, exactly as evaluate() provides.
    assert run([line(1, "5:17 PM PDT")]) == []
    assert run([line(9, "5:17 PM PDT")]) == []


def test_reset_clears_history_for_a_reused_pref_object():
    pref = {"id": "wai-track-statusline-fidelity"}
    for blk in (line(1, "5:17 PM PDT"), line(2, "5:17 PM PDT"), line(3, "5:17 PM PDT")):
        last = D.detect(blk, pref)
    assert last, "setup: the third same-minute turn should have fired"
    D.reset()
    assert D.detect(line(1, "5:17 PM PDT"), pref) == []
