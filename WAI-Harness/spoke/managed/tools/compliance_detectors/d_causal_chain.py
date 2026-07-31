"""communication-explicit-causal-chain — a report must end by closing the loop.

THE PREFERENCE, verbatim: "Every report ends with an explicit causal chain: what
happens AUTOMATICALLY (and when), what is WAITING and on WHOM, and THE single
next action for the operator — one, unambiguous, no inference required. If a
claim implies a chain of events (e.g. 'routed to X'), state what triggers it and
what does NOT happen until then. Leaving the operator to deduce the next step is
a defect."

The operator's words behind it: "notice how Im left confused about the actionable
next step by your responses. Improve upon this."

WHAT MAKES THIS MEASURABLE AT ALL. The preference does not ask for a good next
step -- no regex judges that -- it asks for three NAMED ELEMENTS to be present.
Presence is lexical, so presence is provable. The detector measures exactly that
and nothing more: it can prove a report never used the vocabulary of automation,
never named an owner, and never pointed at an action. It cannot prove the chain
it found is correct. That gap is stated here rather than papered over.

The canonical failure is in this repo's own history: transcript c1e083fb closes a
three-gap work report with "Routed to Basher as impl-ap-commit-session-guard-v1
in .../incoming/" and stops. That is the preference's OWN example -- a claim
implying a chain, with nothing said about what triggers it. Nothing automatic is
named, no owner is named, no next action is named. It is the violating fixture.

THE SCOPE GATE. "Every report" is not "every message". A block that narrates
thinking, asks a question, or explains a concept is not a report, and grading it
against a reporting rule manufactures findings. So the detector first requires
the block to ASSERT WORK STATE -- three or more distinct delivery markers
(verified, pushed, shipped, fixed, tests passed, …). Below that bar it abstains.
The bar is a floor on evidence, not a measure of quality; a genuinely terse
report that slips under it is a miss, and a miss is the cheaper error.

Structured output is stripped for the GATE (a fenced tool dump is quoted
evidence, not the agent asserting work) and kept for ELEMENT PRESENCE (this
detector reports an absence, so every place an element may count is a place a
false finding cannot come from). Both choices push toward abstention.

DELIBERATELY UNMEASURED, each with its reason:
  * "(and when)" -- the preference wants a TIME for the automatic thing. Real
    closings say "on next wakeup", "at 06:30 UTC", "the moment the turn ends",
    "tonight" and a dozen other shapes; a pattern loose enough to catch them all
    catches prose that is not a schedule. Presence of the automatic ELEMENT is
    measured, its timing is not.
  * "THE SINGLE next action" -- singularity. A closing offering three ranked
    next actions matches the same markers as one offering exactly one. Counting
    them would require deciding which list items are actions, which is judgement.
  * whether the stated chain is TRUE. Out of reach by construction.
"""
import re


def strip_structured(text):
    """Borrow the oracle's definition of "structured output", LAZILY.

    This used to be a module-scope `from tastegraph_compliance import ...`, which
    made this file's REGISTRATION depend on who imported first. The oracle calls
    `load()` at the bottom of its own import, so importing this module FIRST
    re-enters the oracle, the oracle re-enters this half-built module, and
    `getattr(m, "PREF_ID")` finds nothing yet. The loader skips it into
    PLUGIN_ERRORS and the preference is then reported UNMEASURABLE while the run
    still reports success -- the exact false-green this toolchain exists to
    catch. Reproduced by this file's own tests: `evaluate()` returned
    "unmeasurable" for a transcript it should have graded. `d_count_matches_list`
    and `d_definitive_exit_report` already resolve it this way.
    """
    import os
    import sys
    tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from tastegraph_compliance import strip_structured as _fn
    return _fn(text)


PREF_ID = "communication-explicit-causal-chain"
CLOSING_ONLY = True

# Blockquoted operator words are not the agent's report. Grading a quotation is a
# false positive with no honest fix.
#
# `.*$` and not just `>`. Deleting the MARKER and keeping the sentence left the
# quoted words in the gate's prose, so the guard removed the only evidence that a
# quotation was happening and none of the text being quoted -- it read as a guard
# and behaved as an amplifier. Identical defect to the one `d_definitive_exit_
# report` documents; this file carried the un-fixed copy. `$` with MULTILINE
# stops before the newline, so the line empties rather than closing up.
_QUOTE_LINE = re.compile(r"^\s*>.*$", re.MULTILINE)

# ---- the scope gate ---------------------------------------------------------

# Delivery markers. A report asserts that work reached a state; conversation does
# not. Distinct markers are counted rather than total hits so one repeated word
# ("pushed … pushed … pushed") cannot promote a chatty block into a report.
_DELIVERY = [
    re.compile(r"\bverified\b|\bverif(y|ies|ication)\b", re.IGNORECASE),
    re.compile(r"\bvalidat(ed|es|ion)\b", re.IGNORECASE),
    re.compile(r"\bcommitted\b|\bcommit\b", re.IGNORECASE),
    re.compile(r"\bpushed\b", re.IGNORECASE),
    re.compile(r"\bshipped\b|\bdistributed\b", re.IGNORECASE),
    re.compile(r"\bdelivered\b|\brouted\b", re.IGNORECASE),
    re.compile(r"\bfixed\b|\brepaired\b", re.IGNORECASE),
    re.compile(r"\blanded\b|\bmerged\b", re.IGNORECASE),
    re.compile(r"\bcomplete[d]?\b|\bdone\b", re.IGNORECASE),
    re.compile(r"\btests? (pass|passed)\b|\b\d+ (tests?|passed)\b|\bgreen\b",
               re.IGNORECASE),
    re.compile(r"\bbuilt\b|\bimplemented\b", re.IGNORECASE),
    re.compile(r"\bclosed\b|\bcleared\b", re.IGNORECASE),
]
_REPORT_FLOOR = 3


def is_report(text):
    """Does the block assert work state? Abstain unless it clearly does."""
    prose = _QUOTE_LINE.sub("", strip_structured(text))
    return sum(1 for pat in _DELIVERY if pat.search(prose)) >= _REPORT_FLOOR


# ---- the three elements -----------------------------------------------------

# 1. WHAT HAPPENS AUTOMATICALLY. An explicit denial ("nothing runs automatically")
#    satisfies the preference exactly as well as an assertion -- the operator's
#    complaint is being left to deduce, and "nothing fires" ends the deduction.
_AUTOMATIC = re.compile(
    r"\bautomatic(ally)?\b|\bauto-(commits?|heals?|closes?|reconcile|updates?)\b"
    r"|\bon its own\b|\bby itself\b|\bresumes? itself\b|\bruns? itself\b"
    r"|\bself-(heal|clos|correct|commit)\w*"
    r"|\bunattended\b|\bwithout you\b|\bnothing (runs|fires|happens)\b"
    r"|\b(will |won't |does not |doesn't )?fires?\b|\bwill fire\b"
    r"|\bcron\b|\bscheduled\b|\bnightly\b"
    r"|\bnext (wakeup|session|wake)\b|\bsession[- ]start\b|\bon wakeup\b"
    r"|\bstop hook\b|\bthe hook (flushes|fires|runs)\b",
    re.IGNORECASE)

# 2. WHAT IS WAITING, AND ON WHOM. The owner is the load-bearing half: "pending"
#    with no owner is the exact ambiguity the preference was written against, so
#    a bare "pending" does not count.
_WAITING = re.compile(
    r"\bwait(s|ing)? (on|for)\b|\bawait(s|ing)\b"
    r"|\bblocked (on|by)\b|\bpending (on|with|at)\b"
    r"|\bneeds? (you|your)\b|\brequires? your\b|\byour (call|decision|approval|"
    r"input|sign-?off|ruling|go)\b"
    r"|\bnothing is waiting\b|\bnothing waits\b|\bwaiting on you\b"
    # An explicit denial closes the deduction as well as an assertion does.
    # "Nothing undone. Nothing unpushed." leaves nothing for the operator to
    # work out, which is the whole point of the preference.
    r"|\bnothing (undone|outstanding|is left|left to do|pending|blocking)\b"
    r"|\b(waits?|waiting|blocked|pending)\b[^.\n]{0,40}?\bon (you|me|basher|"
    r"the operator|the spoke)\b"
    r"|\bon you\b[^.\n]{0,30}?\b(decision|call|approval)\b"
    r"|\bunactioned\b"
    # Naming the operator as the owner of a list. The earlier pattern required
    # the literal word "open" in front, so transcript 073d8ac3 -- which says
    # "Decisions for you, in order: 1. Nothing needed — this is a good stopping
    # point." -- was reported as ending WITHOUT what is waiting and on whom.
    # That is the clearest possible statement of the element, graded as its
    # absence. Corrected s139 with the corpus sweep that found it.
    r"|\b(decisions?|questions?|asks?|calls?|items?) for you(r attention)?\b"
    r"|\bfor your (approval|review|sign-?off|ruling|decision|steer)\b"
    r"|\bnothing (needed|required)\b"
    # A message that IS the ask. Transcript ffc05a94 lays out a 10-lug plan
    # "so you can approve the batch" and ends "Shall I proceed?" — nothing in
    # that report is ambiguous about what waits or on whom, and reporting it as
    # unstated was this detector's worst finding on the whole corpus.
    r"|\bshall i proceed\b|\byou can approve\b|\bapprove the (batch|writes?|plan)\b",
    re.IGNORECASE)

# 3. THE NEXT ACTION. Named as an action the operator can take, not implied.
_NEXT_ACTION = re.compile(
    r"\bnext (action|step|actions|steps)\b|\bfirst action(s)?\b"
    r"|\bnext session (opens|picks up|resumes|begins|starts)\b"
    r"|\brecommended (first )?(action|next)\b|\bresume note\b"
    r"|\bpicks? up (here|on|with)\b|\bresumes? here\b"
    r"|\bwhen you (start|restart|open|come back)\b"
    r"|\bsay (\"|\*\*|`)|\brun (`|\*\*|the |this|it|these)|\bstart with\b"
    r"|\bnext up\b|\bto proceed\b|\bto execute\b|\bnext, \b"
    # The permission-blocked closings in this repo end with "the drain commands
    # to run:" or "approve the write prompts" and a script. That IS a named
    # action; missing it would be a false finding against a message that told
    # the operator exactly what to do.
    r"|\bcommands? to run\b|\bapprove the\b|\byou can (run|say|approve|do)\b"
    # A named recommendation IS a named action. The pattern above only admitted
    # the exact phrases "recommended action" / "recommended next", so the house
    # closing form -- "Recommended session-closing action: **savepoint**"
    # (d8313da6, twice) and "My recommendation is **savepoint and close out**"
    # -- was reported as ending with no next action named. Corrected s139.
    r"|\brecommend(ed|ation|s)?\b[^.\n]{0,40}?\b(action|move|step|next)\b"
    r"|\bmy recommendation is\b|\bi(\'d| would)? recommend\b",
    re.IGNORECASE)

_ELEMENTS = [
    ("what happens AUTOMATICALLY", _AUTOMATIC),
    ("what is WAITING and on WHOM", _WAITING),
    ("THE single next action", _NEXT_ACTION),
]


def detect(text, _pref):
    """Fire only on a proven report that omits a named element of the chain.

    One finding per report listing everything missing. Three findings for one
    loop-open closing would treble the ledger's violation count while adding no
    fact the reader did not already have from the first.
    """
    if not is_report(text):
        return []

    missing = [label for label, pat in _ELEMENTS if not pat.search(text)]
    if not missing:
        return []

    tail = " ".join(_QUOTE_LINE.sub("", strip_structured(text)).split())[-110:]
    return [{
        "evidence": tail,
        "note": ("report ends without " + ", ".join(missing)
                 + " — the operator is left to deduce the next step"),
    }]
