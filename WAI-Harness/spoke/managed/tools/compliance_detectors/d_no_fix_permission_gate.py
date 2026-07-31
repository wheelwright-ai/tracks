"""work-style-never-ask-to-fix-what-you-built — the repair-permission gate.

OPERATOR RULING (2026-07-27, stated with frustration): "why wouldn't I affirm
the action?" Surfacing a defect and then GATING its repair on his approval is a
slow-down with no upside -- he has to spend a turn saying yes to a thing he was
always going to say yes to, and the fix waits for a human round-trip it never
needed. If the agent found it, reported it, and the repair is inside its own
authority, it must FIX it and report the fix. Decision points are reserved for
genuinely destructive/irreversible actions and for mutually-exclusive choices
between approaches.

WHY THIS IS NOT `d_no_permission_ask_for_safe_ops`. That detector measures
communication-register: asking permission for a READ-ONLY verb (check, look,
grep). It is about deference where none is warranted, and it deliberately
abstains the moment the sentence turns write-shaped. This preference lives on
the other side of that line: the action IS a write -- a repair -- and the ask is
still wrong, because the agent itself just named the thing that needs repairing.
Overlap is zero by construction: the two verb sets are disjoint (read verbs vs
repair verbs), so a sentence can satisfy at most one of them.

THE PROVABLE SHAPE, and the only one this fires on:

    <ask lead> [filler] <repair verb> ... ?
    "Want me to fix tender_helpers and run the loop?"
     ^^^^^^^^^^ ^^^                              ^

Three conditions, all required, all mechanical:

  1. ASK LEAD in question position -- "want me to", "should I", "shall I",
     "would you like me to". The sentence must terminate in '?'.
  2. REPAIR VERB in BARE/INFINITIVE POSITION -- directly after the lead (past a
     closed set of adverbial filler), or coordinated onto it with "and"/"then".
     Position is what makes this safe. Anchoring on the verb SLOT rather than on
     the word anywhere in the sentence is the single guard that kills the
     corpus's most common near-miss: "Want me to run the one-round confirmation,
     or commit the fix?" and "Want me to run one post-fix round on minder?" both
     contain "fix", neither is an offer to repair -- one is a noun behind a
     determiner, one is a hyphenated adjective. A word-anywhere match reports
     both. A slot match reports neither.
  3. DEFECT CUE in the preceding prose of the same block (or in the ask itself).
     This is the "what you built / what you reported" half of the preference. An
     offer to repair something the operator raised is a different act from an
     offer to repair something the AGENT surfaced two paragraphs earlier, and
     only the second is what he ruled on. Without this the detector would grade
     the mere existence of the word "fix" near a question mark.

THREE EXEMPTIONS, each one a case where the ask is CORRECT and firing would
suppress a question he actually wants:

  * DESTRUCTIVE/IRREVERSIBLE. Deleting, discarding, force-pushing, overwriting,
    resetting, purging. Scanned over a generous window around the ask rather
    than the ask alone, because the destructive word often sits in the clause
    that justifies the pause ("the safety system blocked my bulk rm -rf").
    Deliberately over-wide: a missed violation costs a metric point, a
    suppressed legitimate pause costs the operator real work. Known cost of
    that width: polysemous members like "drop" and "reset" occasionally
    suppress an innocent neighbour ("the de-dup key should drop the count
    suffix"), which loses a finding. Accepted, and left in -- narrowing them
    trades a silent miss for a confident wrong accusation, and the accusation
    is the more expensive error.
  * MUTUALLY-EXCLUSIVE CHOICE. Any alternative connector in the ask -- "or",
    "either", "(a)/(b)", "rather than". "Want me to dig into the grooming gap
    and fix it, or let the run ride?" is a genuine fork with a real tradeoff
    (a heavy run was in flight), and the ruling explicitly protects it.
  * NEGATION. Reuses the oracle's `_negated` window, so text that mentions the
    banned shape in order to warn against it -- which this very docstring's
    subject matter invites -- does not report itself as a violation.

Verbatim operator quotations and fenced blocks are removed before matching, via
the oracle's `strip_structured` plus a blockquote and paired-quote scrub. When
he quotes his own ask back at the agent, or the agent quotes his ruling to
confirm it, grading that text measures HIS sentence, not the agent's conduct.
The scrub replaces quoted spans with spaces rather than deleting them, so
reported offsets and evidence still line up with the original block.

DELIBERATELY NOT MEASURED, because no deterministic rule separates them from
legitimate asks:

  * BARE IMPERATIVE-QUESTION DECISION HEADINGS -- "**Fix the dead registry
    path?**" as a numbered item under "## Open decisions". Real, and a real
    violation when the repair was in-authority. But the identical construction
    is how the operator's own sanctioned decision blocks render DESTRUCTIVE
    choices ("**Discard the 3 forks?**", "**Delete the phantom garbage dirs?**"
    -- both live in this repo's transcripts), and with no ask-lead to anchor on,
    telling the two apart needs the surrounding argument, not a pattern.
  * ROUTING A REPAIR ELSEWHERE -- "Want me to route a lug to Basher to fix
    this?" The lead is followed by "route", so the slot rule already abstains.
    Whether that ask is a violation turns on whether the fix was in the agent's
    authority at all, which is a judgement about ownership boundaries. Left
    unmeasured on purpose rather than guessed at.
  * IMPLICIT GATING -- reporting a defect and simply stopping, with no ask at
    all. Identical harm, zero textual signature. Unmeasurable, and saying so
    beats inventing a proxy.
"""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tastegraph_compliance import strip_structured, _negated  # noqa: E402

PREF_ID = "work-style-never-ask-to-fix-what-you-built"
CLOSING_ONLY = False

# Ask leads. Only first-person offers -- "can you", "is it worth" and friends are
# not the agent gating its own action, which is the whole subject here.
_LEAD = (r"(?:want me to|do you want me to|would you like me to|"
         r"shall i|should i|ok(?:ay)? for me to)")

# Adverbial filler that may sit between the lead and the verb without changing
# the shape. Closed set: anything outside it means the verb is not in the slot.
_FILL = (r"(?:\s+(?:just|also|now|first|quickly|please|then|go ahead and|"
         r"actually|simply))*")

# Repair verbs. Bare forms only -- an inflected form ("fixed", "fixing",
# "repairs") cannot occupy an infinitive slot, so excluding them costs nothing
# and removes a whole class of noun/participle collisions.
#
# "resolve" and "address" are deliberately ABSENT. Both are heavily overloaded in
# this codebase ("resolve the transcript path", "address the operator"), and a
# repair verb that is only sometimes a repair verb is exactly the kind of
# almost-right rule that produces confident wrong findings.
_REPAIR = (r"(?:fix|repair|patch|correct|rectify|remediate|mend|unbreak|un-break|"
           r"clean up|cleanup|re-?point|straighten out|sort out|"
           r"close (?:the )?gaps?)")

# The verb directly in the slot: "Want me to fix ...".
_SLOT_RE = re.compile(_LEAD + _FILL + r"\s+" + _REPAIR + r"\b", re.IGNORECASE)

# The verb coordinated onto the lead: "Want me to open that lug, and fix ...".
# Bounded at 80 chars and forbidden from crossing '?' or a newline, so it cannot
# reach into the next sentence and borrow a verb that belongs to another ask.
_COORD_RE = re.compile(_LEAD + r"[^?\n]{0,80}?\b(?:and|then)\s+(?:also\s+)?"
                       + _REPAIR + r"\b", re.IGNORECASE)

# Alternative connectors -> a fork, not a gate. "or" is checked as a whole word
# so "for"/"editor" cannot trip it.
_ALTERNATIVE_RE = re.compile(
    r"\bor\b|\beither\b|\brather than\b|\binstead of\b|\bversus\b|\bvs\.?\b"
    r"|\(a\)|\(b\)|\bA or B\b", re.IGNORECASE)

# Destructive / irreversible. A pause here is CORRECT and must survive.
_DESTRUCTIVE_RE = re.compile(
    r"\b(delet|remov|discard|purge|wipe|destroy|overwrit|force[- ]?push|"
    r"reset|revert|rollback|roll back|nuke|rm -rf|drop|prune|truncate|"
    r"retire|decommission|blow away|throw away|rewrite histor|"
    r"unrecoverable|irreversible|destructive)", re.IGNORECASE)

# Evidence that the agent itself reported something wrong. Generous on purpose:
# this gate exists to establish "a defect was on the table", not to classify it.
_DEFECT_CUE_RE = re.compile(
    r"\b(bug|bugs|broke|broken|breaks|breaking|crash|crashed|corrupt\w*|"
    r"fail|fails|failed|failing|failure|defect|regression|stale|drift\w*|"
    r"wrong|incorrect|mismatch\w*|misdiagnos\w*|dead path|dead link|"
    r"phantom|hardcoded|hard-coded|typo|churn|hole|gap|gaps|missing|"
    r"doesn't (?:work|parse|run|fire)|won't (?:work|parse|run|fire)|"
    r"never (?:ran|fired|worked)|error|errors|stranded|orphan\w*|"
    r"v3-stale|not wired|unwired|silently)\b", re.IGNORECASE)

_BLOCKQUOTE_RE = re.compile(r"^\s*>.*$", re.MULTILINE)
# Paired quotes and backticked spans. Replaced with spaces, never deleted, so
# every downstream offset still indexes the same characters it did before.
_QUOTED_SPAN_RE = re.compile(r"[\"“][^\"”\n]{0,400}[\"”]|`[^`\n]{0,400}`")

# How far around the ask the destructive check looks. Wider than the ask itself
# because the justifying clause routinely sits in a neighbouring sentence.
_DESTRUCT_WINDOW = 220
# How far back a defect report may sit and still count as "the agent reported
# it". One or two paragraphs -- past that it is a different topic.
_DEFECT_WINDOW = 900


def _scrub(base):
    """Blank quotations in `base`, preserving every character offset.

    Spans become runs of spaces rather than disappearing, so `base` and the
    scrubbed text share one coordinate space and a window taken from one indexes
    the same characters in the other.
    """
    clean = _BLOCKQUOTE_RE.sub(lambda m: " " * len(m.group(0)), base)
    return _QUOTED_SPAN_RE.sub(lambda m: " " * len(m.group(0)), clean)


def _ask_sentence(text, start):
    """The question the match sits in: back to a boundary, forward to '?'.

    Returns None when no '?' follows on the same line -- a lead that never
    becomes a question is narration ("I'll ask whether you want me to fix it
    later"), not a gate, and narration is not what the operator ruled on.
    """
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start),
               text.rfind("!", 0, start), text.rfind("?", 0, start))
    qmark = text.find("?", start)
    if qmark < 0:
        return None
    nl = text.find("\n", start)
    if 0 <= nl < qmark:
        return None
    return text[left + 1:qmark + 1].strip()


def detect(text, _pref):
    """Offer to repair a self-reported defect, gated on operator approval."""
    # MATCHING runs on the quote-scrubbed text -- grading a sentence the operator
    # wrote is not grading the agent. The DESTRUCTIVE guard runs on the
    # unscrubbed text, because the irreversible thing is very often named inside
    # backticks ("blocked my bulk cross-repo `rm -rf`") and scrubbing it away
    # would turn the safest exemption into a silent no-op. Suppression may read
    # more; only accusation reads less.
    base = strip_structured(text)
    clean = _scrub(base)
    out = []
    seen = set()
    for rx in (_SLOT_RE, _COORD_RE):
        for m in rx.finditer(clean):
            sentence = _ask_sentence(clean, m.start())
            if sentence is None:
                continue
            if m.start() in seen:
                continue

            # A fork between approaches is a legitimate decision point.
            if _ALTERNATIVE_RE.search(sentence):
                continue

            # A pause before something irreversible is legitimate.
            window = base[max(0, m.start() - _DESTRUCT_WINDOW):
                          m.start() + _DESTRUCT_WINDOW]
            if _DESTRUCTIVE_RE.search(window):
                continue

            if _negated(clean, m.start()):
                continue

            # Was a defect actually on the table, put there by the agent?
            preceding = clean[max(0, m.start() - _DEFECT_WINDOW):m.start()]
            if not (_DEFECT_CUE_RE.search(preceding)
                    or _DEFECT_CUE_RE.search(sentence)):
                continue

            seen.add(m.start())
            out.append({
                "evidence": sentence[:140],
                "note": "gated a repair on approval after reporting the defect "
                        "— fix it and report the fix",
            })
    return out
