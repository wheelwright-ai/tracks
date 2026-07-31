"""Tests for d_definitive_exit_report.

EVERY corpus fixture below is VERBATIM assistant text from this repo's own
transcripts under ~/.claude/projects/-home-mario-projects-wheelwright-mywheel/,
cited by transcript filename at its definition. Nothing is paraphrased and
nothing is abridged inside its own boundaries -- the gate patterns measure
distance between words, so an edited fixture would test the editing.

THE FAILURE MODE THIS FILE IS BUILT AROUND. This detector reports an ABSENCE,
and it reports it against a SCOPE it has to prove first. That makes a silent
detector and an over-eager one look identical from the outside: both produce a
tidy number. So every negative here is paired with a CONTROL -- the same real
text with one clause changed -- that MUST fire. A negative that passes without
its control is evidence of nothing, because `return []` passes it too.

The scope pairs matter most. Wire this preference to every closing message and
every ordinary reply in every transcript becomes a wishy-washy closeout; the
gate exists to stop that, so the gate is what the controls interrogate.
"""
import os
import sys

import pytest

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from compliance_detectors.d_definitive_exit_report import (  # noqa: E402
    PREF_ID, CLOSING_ONLY, detect, is_ceremony_report)


# --- real corpus fixtures ----------------------------------------------------

# VIOLATION. b86ae229-91d9-430a-80cf-7dcddf4605da.jsonl -- a genuine savepoint
# ceremony that stops short. The savepoint is announced, committed and pushed;
# the track is never mentioned at all, and "Good place to stop" is a sentiment,
# not a verdict. Both absences are unarguable, which is why this is the primary
# violation fixture: nothing here turns on how generously a heading is read.
#
# It also carries the module's stated asymmetry in one message. Its accomplishments
# live as `Work done:` INSIDE the fence, and they count -- an absence detector must
# let every place an element could appear count, or it lies about a report that did
# the right thing. Its savepoint id lives inside that same fence, and it does NOT
# gate -- an id in a pasted block is evidence about what the message QUOTES.
REAL_CEREMONY_VIOLATION = """\
✅ **Savepoint committed (`803f45d`) and pushed.**

```
Savepoint:  sp-session-20260616-0207-conductor-orchestrator
Initiative: Harness Fleet Migration (harness-fleet-migration)
Work done:  v4 engine reconciled + distributed; phantom WAI-Spoke graveyard'd;
            Conductor built \
(throttle/warm-up/health-injection/signal-delivery/
            foundation-verify; subsumed Gardener+Tender; on 5h cron); 9/9 core
            initiatives seeded; verify_foundation built; KOL launch fixed.
Next:       Run the Conductor (conductor.py); show waves + gaps
```

Your resume intent is locked in — the next `/wai` will surface this savepoint,\
 and the agent's first move is to **run the Conductor and show you the waves +\
 gaps**. To watch it live yourself: `python3 \
WAI-Harness/hub/local/scripts/conductor.py --ceiling 800000 --wave-size 4` (it\
 self-throttles while you're active).

Two small heads-ups for next session:
- **OPERATOR-ASKS.md** has your pending decisions queued (KOL anon-key, RESEND\
 key, the 2 basher approvals, foundation refreshes) — the Conductor refreshes \
it each run.
- A stack of `*-autoeject` savepoints accumulated this session (auto-eject \
fired repeatedly); next `/wai` will flag the count — fine to prune them, the \
`conductor-orchestrator` one is the real resume point.

Good place to stop. Everything's committed, pushed, and the wheel's set up to \
roll forward on the 5-hour cadence."""

# CLEAN. d668fd91-5f09-4549-b524-23b05ccf7239.jsonl -- the report the preference
# was written to describe, and the session that produced the preference. All four
# parts are named as sections: accomplishments with a net-net, the track closed
# with a row count, the savepoint verified by pointer read-back, and one
# unambiguous verdict line at the bottom.
REAL_DEFINITIVE_CLOSE_REPORT = """\
# SESSION 137 — DEFINITIVE CLOSE REPORT

## What we accomplished (net-net)

| Domain | Delivered |
|---|---|
| **Diagnosis** | 6-dimension wheel review, every finding file:line-evidenced;\
 one thesis proven: *state advanced without reality* |
| **Verification** | Adversarial pass corrected 17/24 of my own plan — \
writer≠checker proven, then legislated |
| **Certification** | Mandate landed: **22 lugs now carry full signature \
chains** (43 filed/validated; 21 verified end-to-end + exit-clarity validated \
tonight); Gate-4 is tool-assisted (`wai_assurance --lug`) |
| **Fleet** | 4 cuts (4.6.1→4.6.4), 3 verified distributions, **15 active \
spokes converged and byte-audited**, registry truthful *and* enforced, 7 \
spokes frozen on a verified baseline per your directive |
| **Resume** | Your "we lose our place" — closed at every layer and \
live-proven: pointer auto-updates, wakeup scans, both ceremonies fixed, menu \
shows real savepoints, launcher Resume-on-Enter fed truthful data |
| **Self-healing** | First full oracle loop closed same-day (ts_source: found \
→ lugged → fixed → re-proven) |
| **Hygiene** | 186 stale savepoints archived (live pointer intact), 4 zombie \
branches retired with ancestor proofs, secrets gitignored, journals \
disciplined |

## Track closed ✅
**74 rows flushed** to `sessions/session-20260709-1751/track.jsonl`, committed\
 to git. Final event: `turn`. *(This message's own row flushes at Stop — the \
mechanism was live-verified repeatedly today.)*

## Savepoint verified ✅
Pointer read-back: **`sp-session-20260709-1751-wheel-review-execution`** · \
status `pending` · ts `04:29Z` · file exists · headline: *"s137 CLOSED CLEAN: \
batch-4 fully VERIFIED (21 lugs), 4.6.4 cut… ready to distribute."* First \
actions: distribute 4.6.4 → cron decision → final round.

## Git verified ✅ (fresh, this minute)
Dirty: **0** *(sole exception: the live track file, which grows by design \
until Stop)* · Unpushed: **0** on branch, **0** on main · **branch = main = \
origin/main**. Your complaint even caught real dirt — two runtime files had \
crept in since my last claim; both sealed (log gitignored, track committed) \
before this report.

## The permanent fix ✅
**`impl-ceremony-exit-clarity-report-v1`** — filed, Gate-1 VALIDATED, pushed, \
carrying your words. Every future closeout ends with this exact report \
assembled by a deterministic tool (`exit_report.py`) and **one unambiguous \
verdict line**, never prose. Preference also saved to durable memory.

---

# ✅ **WE ARE CLEAR TO EXIT.**

Nothing undone. Nothing unpushed. Nothing unverified. See you at "Resume."

Turn 68 | Thu, Jul 9, 2026 | 9:29 PM PDT | claude-fable-5 | Gold: +1"""

# NOT A CEREMONY. c1e083fb-f9bb-439c-b8ee-b0156115574f.jsonl -- the regression the
# detector's own docstring names. A three-gap work report that closed its session,
# so `evaluate` would hand it to a closing-only detector; it says "closeout" twice
# and edits `wai-closeout.md`, and it is emphatically not a closeout. Nothing was
# saved, nothing was closed, no verdict was rendered. This is the whole
# false-positive class in one block: the ceremony as a NOUN IN PASSING.
REAL_WORK_REPORT_CLOSING = """\
Done. Here's what was executed:

**Gap-2 (validate_canonical.py — stale path):** Fixed in \
`WAI-Harness/spoke/managed/tools/validate_canonical.py`. The tool now tries \
`managed/knowledge/spec/active/` first (the canonical Basher distribution \
location) before falling back to `local/lugs/bytype/spec/`. Also adds \
`"status": "unverified"` to JSON output when `checked == 0` so a misconfigured\
 verifier can't silently impersonate a clean pass. Verified: `checked=1630 \
errors=1221` on mywheel (contract found, real validation ran).

**Gap-3 (wai-closeout.md Step 0a bootstrap ambiguity):** Added an explicit \
**Bootstrap obligation** note to all three copies of wai-closeout.md \
(template, managed/.claude/commands/, .claude/commands/). The note makes \
clear: "Do not block" at Step 0a is a per-step exemption only — a RED stub is \
not exempt from Step 10i's convergence re-verification, which re-runs the test\
 gate on the merged HEAD and blocks there just as hard. Real tests must be \
added before the closeout can complete.

**Gap-1 (git race — AP pushes to origin during live sessions):** Routed to \
Basher as `impl-ap-commit-session-guard-v1` in \
`/home/mario/projects/basher/WAI-Harness/spoke/local/lugs/incoming/`. The lug \
specifies three implementation options (recommend: (c) strip all `git push \
origin` from background scripts immediately + (b) AP commits to its own branch\
 long-term) with concrete file targets.

Commit `a688156` on `session/herald-navcap-20260701-2239`, pushed. Completion \
notice delivered to ezorg-email-website incoming. Notice lug moved to \
`bytype/notice/completed/`."""

# NOT A CEREMONY, quoted-verdict form.
# bfdf3656-e9b9-45a1-8f8f-d74a53adc1aa.jsonl -- section 3 of a three-item work
# report that ends by asking the operator two questions. It is 737 characters, so
# it clears the 400-char bar `evaluate` uses to pick a closing block.
#
# THIS FIXTURE FOUND A LIVE BUG. Before the inline-quote guard, the detector
# graded this a wishy-washy closeout on the strength of one clause: `the savepoint
# honestly says "safe to exit"` -- a sentence DESCRIBING what a tool prints, in a
# message where nothing was saved and nothing was closed. The `>` blockquote guard
# already covered the operator's words read back; only the inline form was open,
# and this repo talks about its own exit ceremony constantly because it builds it.
REAL_QUOTED_VERDICT = """\
## 3. "Active shells" on exit — found it

Not mysterious, and connected to #2. Session hooks **background long-lived \
daemons** that Claude Code counts as live shells when you go to exit:
- `session-start.sh:228` → backgrounds **`herald_poll.py`** (cross-spoke comms\
 daemon)
- `wakeup-canonical.sh:590` → backgrounds a **context-refresh** job
- (plus `wake_proxy.mjs`, the dev proxy)

So the savepoint honestly says "safe to exit" (state *is* saved), but these \
detached-but-not-fully-disowned processes trip CC's guard — confusing, though \
harmless. **Fix:** fully detach them (`setsid`/`nohup` + `disown` + redirect \
all FDs) so CC no longer counts them, or have the savepoint's exit line name \
them as expected background daemons.

---

**"""


# --- the two required cases --------------------------------------------------

def test_real_ceremony_violation_fires():
    """A real savepoint ceremony that omits two of the four named parts."""
    hits = detect(REAL_CEREMONY_VIOLATION, {})
    assert len(hits) == 1
    assert "Savepoint committed" in hits[0]["evidence"]
    assert "track closed with net-net" in hits[0]["note"]
    assert "explicit clear-to-exit verdict" in hits[0]["note"]


def test_real_definitive_close_report_is_clean():
    """All four parts named and evidenced. The detector must stay silent."""
    assert detect(REAL_DEFINITIVE_CLOSE_REPORT, {}) == []


# --- controls: every silence above must be provably EARNED -------------------

def test_control_clean_report_without_its_verdict_line_fires():
    """Proves the four-element check -- not a dead detector -- kept #2 silent.

    One line changed, everything else byte-identical. The gate still holds via
    the savepoint id in prose, so this isolates the element check exactly: the
    finding must name the verdict and nothing else.
    """
    stripped = REAL_DEFINITIVE_CLOSE_REPORT.replace(
        "# ✅ **WE ARE CLEAR TO EXIT.**", "# ✅ **Session 137 ends here.**")
    assert "CLEAR TO EXIT" not in stripped
    hits = detect(stripped, {})
    assert len(hits) == 1
    assert hits[0]["note"].count("missing explicit clear-to-exit verdict") == 1
    assert "track closed" not in hits[0]["note"]


def test_control_ceremony_violation_goes_quiet_when_the_parts_are_added():
    """The mirror of the control above, on the violation fixture.

    Proves the finding is about the two NAMED absences and not about the message
    being a ceremony at all -- otherwise a detector that fired on any proven
    ceremony would pass `test_real_ceremony_violation_fires` just as happily.
    """
    completed = REAL_CEREMONY_VIOLATION + (
        "\n\nTrack closed — 41 rows flushed to `track.jsonl`, committed. "
        "**CLEAR TO EXIT.**")
    assert detect(completed, {}) == []


# --- the scope gate: ordinary closings are not ceremony reports --------------

def test_ordinary_work_report_closing_is_not_a_ceremony():
    """The docstring's named regression, now actually pinned by a test."""
    assert is_ceremony_report(REAL_WORK_REPORT_CLOSING) is False
    assert detect(REAL_WORK_REPORT_CLOSING, {}) == []


def test_control_same_work_report_announcing_a_closeout_fires():
    """Proves the GATE -- not the element check -- kept the work report silent.

    Four words changed at the head of real text whose body is untouched. The
    body still contains no track, no savepoint and no verdict, so a live gate
    must now classify it and name all four absences.
    """
    announced = REAL_WORK_REPORT_CLOSING.replace(
        "Done. Here's what was executed:",
        "Closeout complete. Here's what was executed:")
    hits = detect(announced, {})
    assert len(hits) == 1
    assert hits[0]["note"].count(",") == 3


def test_quoted_verdict_does_not_prove_a_ceremony():
    """Describing what the savepoint prints is not rendering a verdict."""
    assert is_ceremony_report(REAL_QUOTED_VERDICT) is False
    assert detect(REAL_QUOTED_VERDICT, {}) == []


def test_control_same_block_with_the_quotation_marks_removed_fires():
    """Proves the inline-quote guard -- not a dead gate -- earned that silence.

    Two characters removed from real text. With the verdict asserted rather than
    quoted, the same block is a (bad) ceremony report and must be graded.
    """
    asserted = REAL_QUOTED_VERDICT.replace(
        'says "safe to exit" (state', 'says safe to exit (state')
    assert len(detect(asserted, {})) == 1


def test_blockquoted_verdict_is_ignored():
    """The `>` form of the same act -- the operator's words read back.

    Built from the real verdict line so the only variable is the quoting.
    """
    quoted = ("Your ruling on how a close should end, on the record before I "
              "wire it:\n\n> WE ARE CLEAR TO EXIT.\n\nI have filed it as a lug "
              "and the ceremony will assemble it deterministically.\n")
    assert detect(quoted, {}) == []


# --- the fence asymmetry, both directions, from one real message -------------

def test_savepoint_id_inside_a_fence_does_not_gate():
    """Sliced from the real ceremony fixture, so the text is not invented.

    The gate reads stripped prose: an id in a pasted block is evidence about
    what the message QUOTES, not proof the message IS the report.
    """
    fence = REAL_CEREMONY_VIOLATION[
        REAL_CEREMONY_VIOLATION.index("```"):
        REAL_CEREMONY_VIOLATION.rindex("```") + 3]
    assert "sp-session-20260616-0207" in fence
    assert is_ceremony_report(fence) is False
    assert detect(fence, {}) == []


def test_elements_inside_a_fence_still_count():
    """The opposite direction, and deliberately so.

    `Work done:` appears only inside that fence. Grading this report as missing
    its accomplishments would be a false finding about a message that did the
    right thing, so element presence reads the FULL text.
    """
    assert "Work done:" not in REAL_CEREMONY_VIOLATION.replace(
        REAL_CEREMONY_VIOLATION[
            REAL_CEREMONY_VIOLATION.index("```"):
            REAL_CEREMONY_VIOLATION.rindex("```") + 3], "")
    assert "what was accomplished" not in detect(
        REAL_CEREMONY_VIOLATION, {})[0]["note"]


# --- dead-detector guard -----------------------------------------------------

def test_detector_is_not_dead():
    """Fails if `detect` were replaced by `return []`.

    Named and standalone rather than left implicit in the cases above, because
    the majority of this file asserts SILENCE. A stubbed detector satisfies
    every one of those assertions; this is the single test that cannot be
    satisfied by doing nothing, and the controls tie each silence back to it.
    """
    firing = [t for t in (REAL_CEREMONY_VIOLATION,
                          REAL_DEFINITIVE_CLOSE_REPORT,
                          REAL_WORK_REPORT_CLOSING,
                          REAL_QUOTED_VERDICT) if detect(t, {})]
    assert firing == [REAL_CEREMONY_VIOLATION]


# --- the CLOSING_ONLY contract, through the oracle that consumes it ----------

def test_closing_only_is_declared():
    assert CLOSING_ONLY is True


def test_closing_only_is_honoured_by_evaluate():
    """The flag is worth nothing unless `evaluate` acts on it.

    Same real violation, same block list, two positions. Mid-turn it must not be
    graded at all: a savepoint announced in the middle of a session is a
    progress note, and grading it would manufacture violations out of when the
    tool happened to run.
    """
    from tastegraph_compliance import evaluate
    prefs = [{"id": PREF_ID}]
    filler = "Running the suite now. " * 30

    mid = evaluate([REAL_CEREMONY_VIOLATION, filler], prefs)[PREF_ID]
    end = evaluate([filler, REAL_CEREMONY_VIOLATION], prefs)[PREF_ID]

    assert mid["verdict"] == "compliant" and mid["violation_count"] == 0
    assert end["verdict"] == "violated" and end["violation_count"] == 1


def test_short_trailing_narration_never_becomes_the_closing():
    """A savepoint line too short to be a report is not graded as one.

    Real shape from bfdf3656: "Savepoint written. Now validate the contract,
    commit scoped (no churn sweep), and push." -- mid-ceremony narration that is
    the LAST block whenever a transcript is read live.
    """
    from tastegraph_compliance import evaluate
    narration = ("Savepoint written. Now validate the contract, commit scoped "
                 "(no churn sweep), and push.")
    assert len(narration) < 400
    res = evaluate([REAL_DEFINITIVE_CLOSE_REPORT, narration], [{"id": PREF_ID}])
    assert res[PREF_ID]["verdict"] == "compliant"


# --- contract + registry -----------------------------------------------------

def test_plugin_contract():
    assert PREF_ID == "output-format-definitive-exit-report"
    assert detect("", {}) == []
    assert detect("Done — the parser now handles the empty case.", {}) == []


def test_registered_with_the_oracle():
    """The detector is worthless if `load()` cannot see it."""
    from compliance_detectors import load
    found = load()
    assert PREF_ID in found, load.errors
    fn, closing_only = found[PREF_ID]
    assert fn is detect and closing_only is True


def test_registered_even_when_imported_before_the_oracle():
    """Import order must not decide whether this preference is measured.

    `tastegraph_compliance` calls `load()` at the bottom of its own import. A
    top-level `from tastegraph_compliance import ...` here meant that importing
    this module FIRST -- which running this file's tests alone does -- re-entered
    the oracle, which re-entered this half-built module, found no `PREF_ID`, and
    dropped it into `PLUGIN_ERRORS`. The preference then reported UNMEASURABLE
    while the run still reported success. Silent false-green, and invisible.
    """
    import tastegraph_compliance
    assert PREF_ID in tastegraph_compliance.DETECTORS, \
        tastegraph_compliance.PLUGIN_ERRORS
    assert tastegraph_compliance.DETECTORS[PREF_ID] == (detect, True)


@pytest.mark.parametrize("text", [
    REAL_CEREMONY_VIOLATION,
    REAL_DEFINITIVE_CLOSE_REPORT,
    REAL_WORK_REPORT_CLOSING,
    REAL_QUOTED_VERDICT,
])
def test_determinism(text):
    """Same input, same output, twice. No hidden state, no model, no clock."""
    assert detect(text, {}) == detect(text, {})
