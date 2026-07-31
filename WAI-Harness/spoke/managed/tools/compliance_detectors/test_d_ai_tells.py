"""Test-at-birth for d_ai_tells.py — taste-user-013.

Every fixture marked REAL is verbatim assistant output from this repo's own
transcripts under ~/.claude/projects/-home-mario-projects-wheelwright-mywheel/,
with the source file id in the comment above it. Synthetic fixtures prove the
plumbing; only real ones prove the detector survives contact with the prose it
will actually be pointed at.

The properties pinned here, in the order that matters:

  - the FALSE POSITIVES first. A detector that fires on the operator's own
    quoted words, on a library name, on a file path, or on "make it robust" is
    worse than no detector, because it teaches the reader to skip the tool. Six
    of these tests exist only to prove it stays quiet.
  - then the real violations: an acknowledgment-loop opener, the
    "it's not X, it's Y" construction, and a scaffolding preamble, each lifted
    from a session where the agent actually wrote it.
  - then the contract: PREF_ID / CLOSING_ONLY / detect(), and that the oracle's
    plugin loader really picks the module up.
  - and the honest gap: `robust` and hollow intensifiers are NOT scored, and a
    test asserts that silence so nobody "fixes" it back into a false positive
    without reading the docstring first.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compliance_detectors import d_ai_tells as d  # noqa: E402


def notes(text):
    return [v["note"] for v in d.detect(text)]


# --------------------------------------------------------------------------
# contract
# --------------------------------------------------------------------------

def test_exports_the_plugin_contract():
    assert d.PREF_ID == "taste-user-013"
    assert d.CLOSING_ONLY is False
    assert callable(d.detect)


def test_oracle_plugin_loader_finds_it():
    """A detector the loader silently drops lowers coverage with no error."""
    from compliance_detectors import load
    found = load()
    assert "taste-user-013" in found, load.errors
    fn, closing_only = found["taste-user-013"]
    assert closing_only is False
    assert fn("plain sentence with nothing wrong.", {}) == []


def test_every_violation_points_at_characters_in_the_input():
    """Evidence must be provable — a quotation from the text, never a summary."""
    text = ("You're absolutely right about the queue. It's not a cache problem, "
            "it's a source-of-truth problem, and we should leverage the expediter.")
    vs = d.detect(text)
    assert vs
    for v in vs:
        assert v["evidence"]
        assert v["evidence"].lower() in text.lower()
        assert v["note"]


# --------------------------------------------------------------------------
# false positives — the tests that matter most
# --------------------------------------------------------------------------

# REAL, verbatim from transcript b5163b74-*.jsonl. Contains "robust" in its
# load-bearing engineering sense ("tolerant of bad input"), which is exactly the
# usage the detector must not punish.
REAL_CLEAN_ROBUST = (
    "One rule makes this robust: **ready-queue.json is never authoritative.** "
    "Missing or stale → regenerate, never read. That single discipline is "
    "what would have prevented the stale-zero bug — a cache that's stale is a "
    "non-event; a *source* that's stale reports \"0 items need you\" on a "
    "517-lug backlog."
)

# REAL, verbatim from transcript b5163b74-*.jsonl. "unblock leverage" is a
# defined metric in this repo, not a hollow word.
REAL_CLEAN_LEVERAGE = (
    "Ranked by **unblock leverage**, not age or ROI — top of your list is "
    "whatever frees the most work per decision. Both new sections sit above "
    "TASTEGRAPH."
)


def test_real_clean_block_with_robust_is_silent():
    assert d.detect(REAL_CLEAN_ROBUST) == []


def test_real_clean_block_with_leverage_as_a_noun_is_silent():
    assert d.detect(REAL_CLEAN_LEVERAGE) == []


def test_robust_is_deliberately_unscored():
    """Documented gap, asserted so it is not silently 'fixed' into noise.

    Measured on this repo: 3 of 3 non-quoted uses of `robust` were the real
    engineering sense. See the module docstring.
    """
    assert d.detect("A robust pipeline with robust error handling.") == []


def test_hollow_intensifiers_are_unmeasured():
    """Declared UNMEASURABLE in the docstring — no fake check stands in for it."""
    assert d.detect("This is very broken and really quite incredibly stale.") == []


def test_quoted_operator_paragraph_is_exempt():
    """The preference text itself enumerates every banned string.

    Grading the agent for quoting the operator back to him is the false positive
    that would discredit the oracle, and the only way to 'comply' would be to
    paraphrase him — which the taste harvester promises never to do.
    """
    quoted = (
        '"Voice: subtract the AI tells rather than performing humanity. Cut '
        "hollow words (leverage, robust, seamless, utilize, foster), "
        "acknowledgment loops ('great question', 'you're absolutely right', "
        "'to answer your question'), the 'it's not X, it's Y' construction, "
        'hollow intensifiers, and scaffolding preambles."'
    )
    assert d.detect(quoted) == []


def test_blockquote_is_exempt():
    assert d.detect("> You're absolutely right, we should leverage the cache.") == []


def test_enumerating_the_rule_in_prose_is_exempt():
    """Mention, not use — the words appear because they are being banned."""
    text = ("Cut the hollow words: leverage, seamless, utilize, foster. "
            "Avoid the 'great question' acknowledgment loop entirely.")
    assert d.detect(text) == []


def test_fenced_code_and_inline_code_are_exempt():
    """A symbol named after a banned word is a name, not a voice choice."""
    text = ("The scorer reads `leverage_score` from the graph.\n\n"
            "```python\ndef leverage(x):\n    return utilize(x)\n```\n")
    assert d.detect(text) == []


def test_file_paths_are_exempt():
    assert d.detect("Patched tools/foster_lug.py and lib/seamless-sync.js today.") == []


def test_mid_sentence_agreement_is_not_a_loop():
    """REAL shape from transcript e07dffe9-*.jsonl.

    'You're right that the old framework and hub repos are unnecessary' arrives
    mid-paragraph attached to a specific factual claim. Flagging that would push
    the agent toward never conceding a point, which is the opposite of the
    preference. Only the block-opening form is the loop.
    """
    text = ("The audit compares the spec to what the code actually does. You're "
            "right that the old framework and hub repos are unnecessary; both "
            "are deprecated and superseded by mywheel.")
    assert notes(text) == []


def test_ordinary_negation_is_not_the_construction():
    """'not X, it's Y' needs the frame TWICE — one negation is just a sentence."""
    assert d.detect("This is not going to work on WSL2 today.") == []
    assert d.detect("The lug is not ready, and the queue is stale.") == []


# --------------------------------------------------------------------------
# real violations
# --------------------------------------------------------------------------

# REAL, verbatim from transcript 46c0d087-*.jsonl.
REAL_ACK_LOOP = (
    "Good question, and the honest answer depends on whether the pull-check is "
    "actually *wired* into a lifecycle or just exists. Let me check rather than "
    "describe the design as intended."
)

# REAL, verbatim from transcript d8313da6-*.jsonl.
REAL_NOT_X_IT_Y = (
    "Diagnosed precisely, and it's not a bug in the sync — it's "
    "**contradictory inputs**. Those two files are on the RETIRED list *and* "
    "still present in the tree."
)

# REAL, verbatim from transcript 4e20773c-*.jsonl.
REAL_SCAFFOLD = (
    "I'll start by surveying the actual state — savepoints and incoming queues."
)


def test_real_acknowledgment_loop_opener_fires():
    vs = d.detect(REAL_ACK_LOOP)
    assert len(vs) == 1
    assert "acknowledgment loop" in vs[0]["note"]
    assert vs[0]["evidence"].startswith("Good question")


def test_real_not_x_it_y_construction_fires():
    vs = d.detect(REAL_NOT_X_IT_Y)
    assert len(vs) == 1
    assert "it's not X, it's Y" in vs[0]["note"]
    assert "not a bug in the sync" in vs[0]["evidence"]


def test_real_scaffolding_preamble_fires():
    vs = d.detect(REAL_SCAFFOLD)
    assert len(vs) == 1
    assert "scaffolding preamble" in vs[0]["note"]


def test_intensified_agreement_fires_anywhere():
    """'absolutely right' adds nothing 'right' did not, in any position."""
    text = ("The queue regenerates on demand, so you're absolutely right that "
            "the cache can go.")
    vs = d.detect(text)
    assert len(vs) == 1
    assert vs[0]["evidence"].lower() == "you're absolutely right"


def test_hollow_words_fire_when_actually_used():
    for word, sentence in [
        ("utilize", "We utilize the expediter to groom the backlog."),
        ("seamless", "The handoff between spokes is seamless."),
        ("foster", "This will foster better collaboration across the fleet."),
    ]:
        vs = d.detect(sentence)
        assert len(vs) == 1, (word, vs)
        assert vs[0]["evidence"].lower() == word


def test_leverage_fires_as_a_verb_only():
    verb = d.detect("We should leverage the existing expediter for this.")
    assert len(verb) == 1
    assert "verb" in verb[0]["note"]
    assert d.detect("The highest leverage change is fixing the path scoping.") == []


def test_scaffolding_only_at_the_head_of_a_block():
    """A preamble defers the answer; mid-work narration defers nothing."""
    assert d.detect("The queue is stale.\n\nLet me start by regenerating it.") == []


def test_multiple_tells_in_one_block_are_reported_separately():
    text = ("Great question. It's not a cache problem, it's a source problem, "
            "and we can leverage the expediter to fix it.")
    assert len(d.detect(text)) == 3
