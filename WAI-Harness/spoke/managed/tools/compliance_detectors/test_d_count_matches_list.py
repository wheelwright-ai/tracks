"""Tests for the taste-user-012 count-matches-list detector.

WHERE THE FIXTURES COME FROM. Almost every string below is REAL text lifted from
this repo's own transcripts under
``~/.claude/projects/-home-mario-projects-wheelwright-mywheel/*.jsonl``. Each such
fixture names its source file in a comment.

That is not decoration. This detector's whole risk is false positives on a corpus
saturated with version stamps, test tallies and impact scores, and a suite made of
strings the author invented would only prove the author's imagination. The
non-violation cases here are the exact sentences that made earlier drafts of this
detector fire — eleven of them — so the suite is a regression ledger for mistakes
already made, not a hypothetical.
"""
import os
import sys

import pytest

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from compliance_detectors import load                       # noqa: E402
from compliance_detectors import d_count_matches_list as D  # noqa: E402


def fired(text):
    return D.detect(text, {})


# ---- plugin contract --------------------------------------------------------

def test_exports_the_plugin_contract():
    assert D.PREF_ID == "taste-user-012"
    assert D.CLOSING_ONLY is False
    assert callable(D.detect)


def test_discoverable_by_the_oracle_loader():
    """The oracle finds it by walking the package, so registration must be real."""
    found = load()
    assert "taste-user-012" in found
    fn, closing_only = found["taste-user-012"]
    assert fn is D.detect and closing_only is False


# ---- the true violation -----------------------------------------------------

# REAL, verbatim from d5f2dd37-5ec1-4ca1-b794-31b1601c04db.jsonl. The message
# promises "Three failures", numbers two, and then closes with "Let me fix both" —
# the agent's own words confirm only two existed. This is exactly the mismatch the
# operator says he will call out, and it is the only fire in a 4,702-block sweep of
# the entire transcript corpus.
REAL_VIOLATION = (
    "Three failures, all real bugs the tests correctly caught:\n"
    "\n"
    "1. **`_porcelain_paths` misses untracked files in new dirs** — `git status "
    "--short` collapses untracked directories to `dir/`, so individual advisor "
    "snapshots/lug files wouldn't be seen. Need `--untracked-files=all`.\n"
    "2. **`_converge_lock_live` ignores `root`** — it resolves the lock path "
    "relative to CWD, not the repo root, so the CSRP lock check would silently "
    "never fire under `--root`.\n"
    "\n"
    "Good catches. Let me fix both."
)


def test_real_under_listing_fires():
    hits = fired(REAL_VIOLATION)
    assert len(hits) == 1
    assert "promised 3, listed 2" in hits[0]["note"]
    assert "Three failures" in hits[0]["evidence"]


def test_the_same_text_with_the_missing_item_restored_is_clean():
    """Control for the fixture above: add item 3 and the violation disappears."""
    fixed = REAL_VIOLATION.replace(
        "\n\nGood catches.",
        "\n3. **`_session_lane` collides under concurrency** — two sessions "
        "stamped the same lane id.\n\nGood catches.")
    assert fired(fixed) == []


# ---- real compliant text ----------------------------------------------------

# REAL, from the same corpus (session that produced the "advisor crew" slate).
# Note the fenced confidence bars sitting BETWEEN the header and the list:
# strip_structured() removes them, leaving three blank lines the detector must
# tolerate without losing the list underneath.
REAL_COMPLIANT_THREE = (
    "That leaves three things that genuinely need you:\n"
    "\n"
    "```\n"
    "\U0001F7E9\U0001F7E9\U0001F7E9⬜ 85%  (1) basher's advisor crew\n"
    "\U0001F7E9\U0001F7E9⬜⬜ 55%  (2) the master-managed distribution gate\n"
    "\U0001F7E9⬜⬜⬜ 30%  (3) let it run and review in the morning\n"
    "```\n"
    "\n"
    "**1. Which advisors should basher carry?** It is the only spoke that "
    "structurally cannot improve itself.\n"
    "\n"
    "**2. The distribution gate.** Twice today the whole fleet stopped taking "
    "upgrades.\n"
    "\n"
    "**3. Capacity.** Your window reset at 18:02Z.\n"
)


def test_real_compliant_three_over_three_does_not_fire():
    assert fired(REAL_COMPLIANT_THREE) == []


def test_multi_line_items_with_unindented_body_are_not_undercounted():
    """REAL shape from c1353731: `**1.` and `**2.` split by a column-0 body line.

    A line-by-line item counter saw ONE item here and reported a compliant message
    as a violation. The consecutive-numeral scan is what fixes it.
    """
    text = (
        "Here's what I'll build on basher, using the two advisor slots it "
        "already reserved:\n"
        "\n"
        "**1. `integrator` — version currency + harness integration**\n"
        "Watches: the apps basher distributes for version drift and lost "
        "integration.\n"
        "\n"
        "**2. `proofer` — implementation quality + completeness**\n"
        "Watches: lugs marked complete that lack real acceptance evidence.\n"
    )
    assert fired(text) == []


# ---- version numbers: REAL lines, must never fire ---------------------------

# Every string here is a real transcript line ending in a colon and carrying a
# cardinal. None is a promise to enumerate. These are the corpus's most common
# shape and the detector's single biggest false-positive risk.
VERSION_LINES = [
    # both verbatim from the mywheel transcript corpus
    "Now distributing 4.14.11 so the fix actually reaches the fleet:",
    "6 files changed cleanly. Bumping VERSION to 4.14.1 and recutting the "
    "MANIFEST:",
    "On master the 6 tests still run (guard only fires where the hub is absent). "
    "Cutting 4.14.12 and shipping:",
    "Gate green (4/4). Committing the recut + the 4 stranded hooks together:",
]


@pytest.mark.parametrize("line", VERSION_LINES)
def test_version_numbers_never_fire(line):
    """A version stamp above a numbered list must not read as a count promise."""
    text = line + "\n\n1. first thing\n2. second thing\n"
    assert fired(text) == [], line


def test_version_number_alone_is_not_a_promise():
    """Guard the parser directly, not just end-to-end.

    Both halves matter. Without the lookarounds on _CARDINAL, the `11` inside
    `4.14.11` is a well-formed \\b-delimited two-digit number and the first line
    becomes an eleven-item promise.
    """
    assert D._promise("Now distributing 4.14.11 so the fix reaches the fleet:") is None
    assert D._promise("Cutting 4.14.12 and shipping the recut MANIFEST:") is None
    # The digits of a version must not survive as cardinals at all.
    assert D._cardinals("Now distributing 4.14.11 to the fleet") == []
    assert D._cardinals("Gate green (4/4), 80% done, 3x faster") == []


def test_referential_cardinals_abstain():
    """'the 4 stranded hooks' points BACK at a known set; it promises nothing."""
    assert D._promise("Committing the recut + the 4 stranded hooks together:") is None
    assert D._promise("All 9 spokes reporting clean, so now the real work:") is None
    # But the same noun phrase without a determiner still reads as a promise.
    assert D._promise("Committing 4 stranded hooks:") == 4


# ---- test counts and other statistics: REAL lines, must never fire ----------

# All verbatim from the corpus. Test tallies are the second-largest source of
# cardinals in this repo's transcripts.
STAT_LINES = [
    "6/6 green. Confirming the CLI flag works and no regression in existing "
    "upgrade tests, then recut + commit:",
    "32/32 green. Now the live proof — the same commands from the start of this "
    "session:",
    "**Verified:** 1514 passed / 9 skipped · MANIFEST `ok: true`. Next steps:",
    "Wave 1 complete — 32 tests green, oracle live. Now wave 2, the dispatchers:",
    "**Result:** all five spokes `outcome=pass`, selftest `71 passed / 6 skipped`. "
    "Distributing:",
    "Everything is committed and pushed. 1272 tests pass. The same two "
    "pre-existing failures remain:",
    "The spoke HAS `tests/critical_paths.sh`, so RED is a hard block per WHEEL "
    "RULE. Reproducing to find the 1 failure:",
]


@pytest.mark.parametrize("line", STAT_LINES)
def test_test_counts_and_scores_never_fire(line):
    text = line + "\n\n1. first thing\n2. second thing\n"
    assert fired(text) == [], line


def test_impact_score_in_a_prior_sentence_is_not_a_promise():
    """REAL from 7c26b037: '(impact 10)' above a six-item list."""
    text = (
        "`release-basher-cut-distribute-csrp-bundle-v1` → Basher (impact 10), "
        "operator-stamped. It tells Basher to:\n"
        "\n"
        "1. **Bundle** the mywheel-canonical CSRP work.\n"
        "2. **Reconcile Basher's own CSRP tool files up** into the master.\n"
        "3. **Bump the version** and re-cut the MANIFEST.\n"
    )
    assert fired(text) == []


# ---- bullet lists group, so they are abstained on -------------------------

# All three are REAL headers whose bullet lists legitimately pack several promised
# items into fewer bullets. Earlier drafts fired on all of them.
GROUPED_BULLETS = [
    ("**3 files deliberately left uncommitted** (not noise — each has a reason):\n"
     "\n"
     "- `WAI-Spoke/` — the root phantom is back, recreated on session auto-eject.\n"
     "- `wai-enter.sh` / `wai-exit.sh` — Basher-owned launch wrappers with "
     "machine-specific absolute paths.\n"),
    ("Critical safety finding. The 12 drifted managed files are:\n"
     "\n"
     "- **9 are my edits this session** (the 4 ceremony commands + 4 templates).\n"
     "- **3 are NOT mine** — other sessions' in-flight edits.\n"),
    ("**mywheel repo** — 7 items:\n"
     "\n"
     "- `M WAI-Harness/hub/local/scripts/ap_status.sh`\n"
     "- `?? ap_progress.py`, `?? ap_dashboard.py`, `?? wheel_activity.py`\n"
     "- 2 signals — gitignored, on disk only\n"),
]


@pytest.mark.parametrize("text", GROUPED_BULLETS)
def test_bullet_lists_are_abstained_on(text):
    """Bullets group. There is no deterministic grouped-vs-missing test."""
    assert fired(text) == [], text.splitlines()[0]


# ---- compound and incidental cardinals --------------------------------------

def test_compound_promise_abstains():
    """REAL header: 'three things moved, one is holding' is a 4-item promise."""
    text = (
        "Status — three things moved, one is holding on purpose:\n"
        "\n"
        "**1. Teachings — killed.**\n"
        "**2. Policy — captured.**\n"
        "**3. B — was broken, now fixed and running.**\n"
        "**4. basher — I stopped, and I'm glad I looked.**\n"
    )
    assert fired(text) == []


def test_cardinal_in_an_earlier_sentence_abstains():
    """REAL from c03278e7 — '17 open lugs' then a deliberate subset."""
    text = (
        "**Work:** 17 open lugs. Headliners:\n"
        "\n"
        "1. `epic-hub-kb-system` — Expediter + Gardener advisors\n"
        "2. `epic-assessor-v2` — model recs driven by observed performance\n"
    )
    assert fired(text) == []


@pytest.mark.parametrize("line", [
    "Here are the top 5 offenders:",
    "A few of the 8 spokes worth naming:",
    "3 of the 12 failures are new:",
    "The biggest 4 regressions, for example:",
])
def test_explicit_subset_language_abstains(line):
    assert fired(line + "\n\n1. one\n2. two\n") == []


@pytest.mark.parametrize("line", [
    "That took 3 hours of budget:",
    "Ran it 4 times before it stuck:",
    "The injection costs 5 tokens per turn:",
])
def test_units_of_measure_are_not_enumerable(line):
    assert fired(line + "\n\n1. one\n2. two\n") == []


# ---- structural abstentions -------------------------------------------------

def test_enumeration_rendered_as_a_table_abstains():
    """REAL header 'Of the 12 diverged files:' — the list was a table.

    strip_structured() deletes box-drawing before the detector sees the text, so
    the enumeration arrives as blank space. Firing here would report a violation
    against every table the operator asked for.
    """
    text = (
        "I have a precise, decision-ready picture. Of the 12 diverged files:\n"
        "\n"
        "| file | owner |\n"
        "|---|---|\n"
        "| a.py | basher |\n"
        "\n"
        "A blind `harness_upgrade` would destroy those 2 basher-authored files.\n"
    )
    assert fired(text) == []


def test_no_list_at_all_abstains():
    text = ("Three failures, all real bugs the tests correctly caught:\n"
            "\n"
            "I will write them up after the suite finishes running.\n")
    assert fired(text) == []


def test_a_run_that_does_not_start_at_one_abstains():
    """Counting from the middle of somebody else's list proves nothing."""
    text = "Three failures worth naming:\n\n2. second thing\n3. third thing\n"
    assert fired(text) == []


def test_over_listing_is_not_scored():
    """Deliberate. See the UNMEASURED note in the detector."""
    text = ("Two defects surfaced:\n"
            "\n1. one\n2. two\n3. three\n")
    assert fired(text) == []


def test_truncated_list_abstains():
    text = ("Six regressions landed:\n"
            "\n1. first\n2. second, and 4 more\n")
    assert fired(text) == []


def test_n_of_one_abstains():
    """'the 1 failure:' is trivially satisfied and out of range."""
    assert D._promise("Reproducing to find the 1 failure:") is None


def test_large_counts_abstain():
    """Above 20 a cardinal is statistics, not a list a human writes out."""
    text = "There were 43 regressions:\n\n1. one\n2. two\n"
    assert fired(text) == []


# ---- containment: code blocks and operator quotations -----------------------

def test_does_not_fire_inside_a_fenced_code_block():
    text = ("Here is the sample output:\n"
            "\n```\n" + REAL_VIOLATION + "\n```\n")
    assert fired(text) == []


def test_does_not_fire_on_a_verbatim_operator_quotation():
    """The accommodation governs how the AGENT writes, not what the operator said.

    The oracle already learned this once: both dyslexia violations reported in
    session-20260728-0016 were the operator's own words quoted back to him for
    ratification.
    """
    quoted = '"Three failures, all real bugs the tests correctly caught:"\n'
    text = quoted + "\n1. first thing\n2. second thing\n"
    assert fired(text) == []


def test_does_not_fire_inside_a_blockquote():
    text = ("> Three failures, all real bugs the tests correctly caught:\n"
            "\n1. first thing\n2. second thing\n")
    assert fired(text) == []


def test_does_not_fire_on_a_quoted_span_mid_line():
    text = ('You wrote "three defects, all real:" and I want to confirm:\n'
            "\n1. first thing\n2. second thing\n")
    assert fired(text) == []


# ---- corpus regression ------------------------------------------------------

def _corpus_blocks(limit_files=12):
    import glob
    from tastegraph_compliance import load_transcript
    home = os.path.expanduser(
        "~/.claude/projects/-home-mario-projects-wheelwright-mywheel")
    files = sorted(glob.glob(os.path.join(home, "*.jsonl")),
                   key=os.path.getmtime, reverse=True)[:limit_files]
    blocks = []
    for f in files:
        try:
            blocks += load_transcript(f)
        except Exception:  # noqa: BLE001 - a malformed transcript is not this test
            continue
    return blocks


def test_corpus_fire_rate_stays_near_zero():
    """The real guard on this detector: it must stay quiet on real traffic.

    A precision claim from hand-picked strings is worth nothing. This runs the
    detector over the actual transcripts and asserts the fire rate stays in the
    range measured at authoring time — 1 fire in 4,702 blocks across the full
    corpus, and that one a genuine violation. A change that makes this detector
    chatty fails here before it ever reaches a ledger entry.
    """
    blocks = _corpus_blocks()
    if len(blocks) < 200:
        pytest.skip("transcript corpus not available in this environment")
    hits = sum(len(fired(b)) for b in blocks)
    assert hits <= max(3, len(blocks) // 500), (
        f"{hits} fires over {len(blocks)} blocks — too chatty for a detector "
        "whose value is precision")
