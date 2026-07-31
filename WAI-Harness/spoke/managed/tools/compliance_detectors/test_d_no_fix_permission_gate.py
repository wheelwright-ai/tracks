"""Tests for d_no_fix_permission_gate.

EVERY fixture below is VERBATIM assistant text from this repo's own transcripts
under ~/.claude/projects/-home-mario-projects-wheelwright-mywheel/. Each is
cited by transcript filename at its definition. Synthetic text is used only
where the point is a mechanical guard (negation, fences) that no real message
happened to exercise, and it is labelled as such.

The negative fixtures matter more than the positive one. This detector's failure
mode is not missing a violation -- it is suppressing a question the operator
actually wants asked. So each negative pairs with a CONTROL: a one-clause
mutation of the same real text that MUST fire. Without the control, a negative
test passes just as happily when the detector is broken and never fires at all.
"""
import os
import sys

import pytest

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from compliance_detectors.d_no_fix_permission_gate import (  # noqa: E402
    PREF_ID, CLOSING_ONLY, detect)


# --- real corpus fixtures ----------------------------------------------------

# VIOLATION. 660db407-1b9e-401b-80be-d93935abb3c7.jsonl -- the agent found the
# corruption itself, called it "a genuine bug in the canonical master, trivial
# to fix", then spent the operator's turn asking whether to repair it.
REAL_VIOLATION = """**My recommendation:** knock out **#1 (tender_helpers)** right now \
— it's a genuine bug in the canonical master, trivial to fix, and it unblocks 4 \
test suites, which directly serves the v4 "self-certifying" goal. Then **#3** \
(teaching reconcile) as the next substantive item.

Want me to fix tender_helpers and run the loop?"""

# VIOLATION, coordinated form. 7c26b037-3148-4802-b973-c89dddf3705b.jsonl -- the
# repair verb is not adjacent to the lead, it is conjoined onto it.
#
# Kept at full length on purpose. An earlier abridgement pulled "the de-dup key
# should drop the count suffix" to within the destructive window, where "drop"
# suppressed the finding -- an artefact of the fixture, not of the corpus. Real
# text, real distances, or the test measures the editing.
REAL_VIOLATION_COORDINATED = """**3. A Conductor bug I caught:** minder's \
readiness shows **18 near-duplicate `review-canon-adherence` injections** (cycle \
counts 42→59) — the injection de-dup keys on the *incrementing count*, so each \
new count reads as "new." That's exactly the noise you asked to eliminate. The \
de-dup key should drop the count suffix.

---

Savepoint `sp-session-20260616-0207-conductor-orchestrator` is **claimed** \
(status=active, committed+pushed `8137dc6`), and the resume note (run Conductor; \
show waves+gaps) is done.

The highest-value next move is **#1 — route the foundation-hook refresh to \
Basher** (it's the one gap that degrades the fleet right now). Want me to open \
that lug, and fix the Conductor de-dup bug (#3) while I'm at it?"""

# LEGITIMATE ASK. 571381c1-9b3d-4f2f-992a-e25ac4b39d8d.jsonl -- the agent found
# the phantom directories itself and the repair is a bulk cross-repo `rm -rf`.
# Irreversible, so pausing is CORRECT and the detector must stay silent, even
# though every other surface feature (self-found defect, repair on offer, an ask)
# matches the violated shape. This is the near-miss the detector exists to spare.
REAL_LEGITIMATE_DESTRUCTIVE = """- **Phantom garbage** \
`WAI-Harness/spoke/[local/]WAI-Spoke/` on minder, solutions-by-mv, ezorg, \
track-prompt-lab, mywheel — dead expediter runtime written by the bug I just \
hardened
- Historian now reads the v4 tree + internal archive automatically.

## Two things I need from you (both consequential, both your call)

1. **Delete the phantom garbage dirs?** The safety system blocked my bulk \
cross-repo `rm -rf` (correctly — I shouldn't nuke dirs in 5 other repos on \
inferred targets). They contain only regenerable expediter runtime, no real \
work.

   Say the word and I'll remove them (you may need to approve the `rm` once)."""

# LEGITIMATE ASK, mutually-exclusive fork.
# 6a774c94-38d0-46e7-b785-3fce8d75988a.jsonl -- a real tradeoff (a heavy 8-round
# run was in flight), so the two branches are not interchangeable.
REAL_LEGITIMATE_FORK = """So the residual isn't a spin in the cadence — it's a \
**grooming gap**: the expediter reports fixable lugs every round, but nothing \
fixes them, so it reports them again.

Want me to dig into the grooming gap and fix it (so the expediter churn \
resolves), or let the run ride and look at it after? Either way the heavy run \
keeps going — your call on where I point next."""

# NOT AN OFFER TO REPAIR. cac7494b-6082-4e62-9829-0e877105bdef.jsonl -- "post-fix"
# is a hyphenated adjective and "the fuel-gate fix" is a noun behind a
# determiner. A word-anywhere matcher reports this; the slot rule must not.
REAL_FIX_AS_NOUN = """- Minor rough edge: a few spokes (ezorg/pathfinder/website) \
show idle cells but a STARVED footer — the verdict function flags `ready=0` even \
when there's no actual backlog. The cell glyphs are the more accurate read \
there; I can tighten the verdict if it bugs you.

Want me to run one post-fix round on **minder** so you can watch its newest \
cells flip in the dashboard — the live proof the fuel-gate fix actually rolls?"""

# NOT AN OFFER TO REPAIR, second shape.
# cac7494b-6082-4e62-9829-0e877105bdef.jsonl -- the verb after the lead is "run";
# "the fix" is the object of a coordinated alternative.
REAL_FIX_AS_NOUN_2 = """Files changed: `ap_progress.py` (new), `ap_status.sh` \
(verdict section), `framework/tools/spoke_expediter.py` (uncommitted fix). The \
routing bug is diagnosed and saved to memory.

Want me to run the one-round confirmation, or commit the fix?"""


# --- the two required cases --------------------------------------------------

def test_real_violation_fires():
    """The shape the operator ruled on, taken verbatim from the corpus."""
    hits = detect(REAL_VIOLATION, {})
    assert len(hits) == 1
    assert "Want me to fix tender_helpers" in hits[0]["evidence"]
    assert "report the fix" in hits[0]["note"]


def test_real_legitimate_destructive_ask_is_silent():
    """A pause before an irreversible bulk `rm -rf` is CORRECT. Must not fire."""
    assert detect(REAL_LEGITIMATE_DESTRUCTIVE, {}) == []


# --- guard-by-guard, each negative paired with a control ---------------------

def test_coordinated_repair_verb_fires():
    hits = detect(REAL_VIOLATION_COORDINATED, {})
    assert len(hits) == 1
    assert "fix the Conductor de-dup bug" in hits[0]["evidence"]


def test_mutually_exclusive_fork_is_silent():
    assert detect(REAL_LEGITIMATE_FORK, {}) == []


def test_control_same_text_without_the_fork_fires():
    """Proves the fork exemption -- not the defect gate -- silenced the fixture.

    Same real block, alternative clause removed. Everything else is identical,
    so a detector that fires here and abstains above is discriminating on the
    one feature that distinguishes a decision point from a permission gate.
    """
    forkless = REAL_LEGITIMATE_FORK.replace(
        ", or let the run ride and look at it after? Either way the heavy run "
        "keeps going — your call on where I point next.", "?")
    assert "or let the run ride" not in forkless
    assert len(detect(forkless, {})) == 1


def test_fix_as_noun_or_adjective_is_silent():
    """'post-fix round' and 'commit the fix' are not offers to repair."""
    assert detect(REAL_FIX_AS_NOUN, {}) == []
    assert detect(REAL_FIX_AS_NOUN_2, {}) == []


def test_control_same_context_with_verb_in_slot_fires():
    """Proves the SLOT rule silenced the two fixtures above.

    The surrounding real prose is untouched -- same self-reported defect, same
    ask lead -- and only the verb position changes.
    """
    mutated = REAL_FIX_AS_NOUN_2.replace(
        "Want me to run the one-round confirmation, or commit the fix?",
        "Want me to fix the routing bug now?")
    assert len(detect(mutated, {})) == 1


def test_destructive_clause_suppresses_an_otherwise_firing_ask():
    """Proves the destructive window, using real text from both transcripts.

    The real violation is spliced with the real justifying clause from the
    phantom-dirs block (571381c1). The ask is unchanged and still fires on its
    own; adding an irreversible action to its neighbourhood must silence it.
    """
    assert len(detect(REAL_VIOLATION, {})) == 1
    spliced = REAL_VIOLATION.replace(
        "Want me to fix tender_helpers",
        "The safety system blocked my bulk cross-repo `rm -rf` (correctly). "
        "Want me to fix tender_helpers")
    assert detect(spliced, {}) == []


def test_no_defect_reported_is_silent():
    """No defect on the table means this preference is not what is in play.

    Synthetic: the corpus has no clean instance of an ask to 'fix' something the
    agent never described, precisely because agents describe first.
    """
    assert detect("Want me to fix the ordering of the summary sections?", {}) == []


def test_negated_mention_is_silent():
    """Text that names the banned shape in order to forbid it. Synthetic.

    This docstring's own subject matter guarantees such text exists -- the
    anti-pattern list, this file, the detector's own comments -- so the guard is
    load-bearing rather than hypothetical.
    """
    text = ("The anti-pattern is explicit: after reporting a bug, never say want "
            "me to fix it — apply the repair and report what changed.")
    assert detect(text, {}) == []


def test_fenced_block_is_ignored():
    """Fenced content is structured output, not the agent's prose. Synthetic."""
    text = ("The registry entry is stale and the path is dead.\n\n"
            "```\nWant me to fix the dead registry path?\n```\n")
    assert detect(text, {}) == []


def test_verbatim_quotation_is_ignored():
    """Grading a quoted ask measures the quoted sentence, not the agent.

    Both the blockquote form and the inline paired-quote form are covered, since
    ratification messages in this repo use both.
    """
    quoted_block = ("Your ruling, restated so it is on the record — the bug was "
                    "mine and the repair was in my authority.\n\n"
                    "> Want me to fix tender_helpers and run the loop?\n")
    assert detect(quoted_block, {}) == []

    inline = ('The offending sentence from that session was a real bug report '
              'followed by "Want me to fix tender_helpers and run the loop?" '
              'which is the shape now banned.')
    assert detect(inline, {}) == []


def test_narration_without_a_question_is_silent():
    """A lead that never reaches '?' is narration about an ask, not an ask."""
    text = ("The parser is broken. I already decided not to ask whether you "
            "want me to fix it, and shipped the repair instead.")
    assert detect(text, {}) == []


# --- contract + registry -----------------------------------------------------

def test_plugin_contract():
    assert PREF_ID == "work-style-never-ask-to-fix-what-you-built"
    assert CLOSING_ONLY is False
    assert detect("", {}) == []


def test_registered_with_the_oracle():
    """The detector is worthless if `load()` cannot see it."""
    from compliance_detectors import load
    found = load()
    assert PREF_ID in found, load.errors
    fn, closing_only = found[PREF_ID]
    assert fn is detect and closing_only is False


def test_disjoint_from_the_communication_register_detector():
    """No double-counting: the read-verb detector must stay out of this shape.

    The two preferences sit on opposite sides of the read/write line, so an
    overlap would mean one violation scoring twice against two different
    preferences and quietly inflating the violated count.
    """
    from tastegraph_compliance import d_no_permission_ask_for_safe_ops
    assert d_no_permission_ask_for_safe_ops(REAL_VIOLATION, {}) == []
    assert detect("Want me to check the registry for stale entries?", {}) == []


@pytest.mark.parametrize("text", [
    REAL_LEGITIMATE_DESTRUCTIVE,
    REAL_LEGITIMATE_FORK,
    REAL_FIX_AS_NOUN,
    REAL_FIX_AS_NOUN_2,
])
def test_determinism(text):
    """Same input, same output, twice. No hidden state, no model, no clock."""
    assert detect(text, {}) == detect(text, {})
