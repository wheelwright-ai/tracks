"""taste-user-013 — subtract the AI tells. Deterministic sub-detectors only.

WHAT THE PREFERENCE ASKS FOR, and how much of it a regex can honestly hold.

    "Voice: subtract the AI tells rather than performing humanity. Cut hollow
     words (leverage, robust, seamless, utilize, foster), acknowledgment loops
     ('great question', 'you're absolutely right', 'to answer your question'),
     the 'it's not X, it's Y' construction, hollow intensifiers, and scaffolding
     preambles. Vary sentence rhythm. Sound like one sharp colleague..."

That is six rules wearing one id. Four of them name LITERAL STRINGS, which is
the only kind of rule this oracle is allowed to score. Two of them name a
quality of prose, and those are declared unmeasured below rather than given a
plausible-looking check — a fabricated number here would be worse than the gap,
because the whole tool exists to replace exactly that kind of number.

MEASURED
  1. acknowledgment loops      literal openers, positional
  2. "it's not X, it's Y"      a fixed syntactic shape
  3. hollow words              utilize / seamless / foster / leverage-as-verb
  4. scaffolding preambles     literal block openers

DELIBERATELY NOT MEASURED — each of these is a real part of the preference that
this detector refuses to score, with the reason:

  * "hollow intensifiers". Whether an intensifier is hollow is a judgement about
    whether it carries information, not a property of the word. In this repo
    "really broken", "very stale", "absolutely no callers" are all load-bearing:
    they name a degree the reader needs. A `\b(very|really|truly|incredibly)\b`
    check would fire on all three and be wrong every time. There is no
    text-local fact that separates the hollow use from the loaded one, so this
    sub-rule is UNMEASURABLE and is left unscored.

  * "Vary sentence rhythm" / "sound like one sharp colleague". Sentence-length
    variance is computable, but every threshold on it would be invented — no
    value of stddev is the operator's preference, and picking one would launder
    an arbitrary constant into a compliance verdict. UNMEASURABLE.

  * "robust", though the preference lists it as a hollow word. Measured against
    this repo's own transcripts, four occurrences of `robust`: one was the rule
    being quoted, and THREE were the load-bearing engineering sense — "fix the
    autopilot bug robustly (all three sort keys can hit bad data)", "One rule
    makes this robust: ready-queue.json is never authoritative", "requires a
    Path but any caller might pass a string. Let's make it robust." Those mean
    "tolerant of bad input". Scoring them as violations would be 3 false
    positives out of 3, and a detector that is wrong every time it fires trains
    the reader to discount the ones that are right. Excluded on the evidence.

    `leverage` survives only in its VERB form for the same measured reason: in
    this repo the noun is a defined metric ("unblock leverage", "the
    highest-leverage change") and is real, while "leverage the existing X" is
    always just "use". The detector splits on that, rather than banning a word
    the operator's own vocabulary depends on.

WHAT IS EXEMPT, in every sub-detector. Fenced code, box-drawn and table lines
(via the oracle's own `strip_structured`), indented code, inline-code spans,
bare file paths, and any paragraph that opens with a quote character. The last
one matters most: the operator's ratified preference text ITSELF enumerates
these words, and several transcript hits are the agent quoting the rule back to
him. Grading an agent for repeating the operator's sentence is the false
positive that would discredit the whole oracle.
"""
import os
import re
import sys

# Prefer the oracle's own stripper so the two never drift apart. The fallback
# exists because `compliance_detectors.load()` SWALLOWS import errors by design
# — without it, one missing sibling module would make this detector silently
# vanish and quietly lower coverage with no error anywhere. A detector that
# disappears without saying so is the failure this package was built to avoid.
_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
try:
    from tastegraph_compliance import strip_structured
except Exception:  # pragma: no cover - last resort, keeps measurement alive
    _FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
    _BOX_RE = re.compile(r"^[│┌└├─╭╰|].*$", re.MULTILINE)

    def strip_structured(text):
        return _BOX_RE.sub("", _FENCE_RE.sub("", text))


PREF_ID = "taste-user-013"
CLOSING_ONLY = False

# ---- what counts as prose ---------------------------------------------------
# `strip_structured` handles fences and box/table lines. Three more classes of
# text have to go before any word-level rule runs, because in each of them the
# banned word is a NAME, not a voice choice:
#   - inline code spans: `leverage_score`, `foster_child_lug` are identifiers
#   - bare paths: tools/seamless_migrate.py is a file, not marketing
#   - indented blocks: pasted output, same argument as a fence
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_PATH = re.compile(r"(?:[\w.~@-]*/)+[\w.~@-]+|\b[\w-]+\.(?:py|js|ts|jsonl?|md|sh|ya?ml|toml|cfg|txt)\b")
_INDENTED = re.compile(r"^(?: {4,}|\t).*$", re.MULTILINE)

# A paragraph that opens with a quote character is the operator's own words, or
# a rule being cited. Both are quotation, not authorship. Same reasoning as the
# oracle's `_QUOTED`, extended to closing/typographic quotes and markdown
# blockquotes because a quote pasted from a transcript often arrives curled.
_QUOTED_PARA = re.compile(r'^\s*(?:[>"“”‘’«\']|\*\*?["“])')

# Mention-not-use guard. The preference text lists its own banned strings, and
# so does every lug, teaching and savepoint that discusses this detector. When
# the surrounding words are ABOUT the tell, the tell is evidence, not a
# violation. Deliberately a bounded window over neighbouring characters rather
# than a parser: it either abstains or it does not fire.
#
# The cue list is ONLY words that mark discussion of a rule, and pointedly NOT
# bare negations (not / no / never), for two reasons found by testing this
# against real prose:
#
#   1. The "it's not X, it's Y" pattern CONTAINS "not". A guard that treated
#      negation as a mention would see its own match and abstain on every real
#      instance — silently switching the detector off while still reporting
#      "compliant", which is worse than having no detector, because a fabricated
#      pass is exactly what this oracle exists to eliminate.
#   2. A negation near a hollow word does not make it a mention. "It's not a
#      cache problem, it's a source problem, and we can leverage the expediter"
#      is three tells in one sentence; a negation-sensitive guard suppressed all
#      three because the word "not" happened to appear first.
#
# Negation as a mention-signal is right for the oracle's built-in `_negated`
# (where "brew install is macOS-only, use apt" is correct advice about a banned
# thing). It is wrong here, where the banned thing is the agent's own voice.
_MENTION_CUE = re.compile(
    r"\b(cut|cuts|kill|kills|drop|drops|ban|banned|avoid|avoids|forbid|"
    r"forbidden|hollow|filler|ai tell|ai tells|acknowledgment loops?|"
    r"acknowledgement loops?|the phrase|the construction|so-called|"
    r"words like|e\.g\.|such as)\b", re.IGNORECASE)

# Quotation marks around the match are the other mention signal, and the one
# that survives when no cue word is nearby: `the 'great question' opener`.
# Paragraph-initial quotes are already dropped by `_prose`; this catches the
# inline case.
_OPEN_Q = "\"'“‘«"
_CLOSE_Q = "\"'”’»"


def _mentioned(clean, start, end=None, before=110, after=40):
    """Is this occurrence being TALKED ABOUT rather than committed?"""
    if end is not None and start > 0 and end < len(clean):
        if clean[start - 1] in _OPEN_Q and clean[end] in _CLOSE_Q:
            return True
    window = clean[max(0, start - before):start + after]
    return bool(_MENTION_CUE.search(window))


def _prose(text):
    """Text the operator reads as the agent's own voice — everything else out."""
    t = strip_structured(text)
    t = _INDENTED.sub("", t)
    t = _INLINE_CODE.sub(" ", t)
    t = _PATH.sub(" ", t)
    kept = [p for p in re.split(r"\n\s*\n", t) if not _QUOTED_PARA.match(p)]
    return "\n\n".join(kept)


# ---- 1. acknowledgment loops ------------------------------------------------
# Two tiers, because the same words are not equally hollow in every position.
#
# INTENSIFIED forms carry no information anywhere they appear: "you're
# absolutely right" adds nothing that "right" did not. Those fire on sight.
#
# BARE forms are position-sensitive. Opening a reply with "You're right —" is
# the loop the preference names: a turn spent agreeing before the work starts.
# Mid-paragraph, "you're right that the hub repos are deprecated" is a specific
# factual concession attached to a claim, and flagging it would push the agent
# toward never conceding a point, which is the opposite of what is wanted. So
# bare forms fire only at the head of a paragraph. Measured on real transcripts:
# 30 raw hits, and the positional split is what separates the "You're right — I
# owe the track entry" openers from the substantive mid-sentence agreements.
_ACK_INTENSIFIED = re.compile(
    r"\byou'?re (?:absolutely|completely|totally|entirely|100%|so) right\b",
    re.IGNORECASE)

_ACK_OPENER = re.compile(
    r"^\s*(?:\*\*|_)?\s*("
    r"great question|good question|excellent question|that'?s a (?:great|good|fair) (?:question|point)|"
    r"you'?re right|you'?re correct|you are right|"
    r"good catch|great catch|nice catch|fair point|"
    r"to answer your question|happy to help|i'?d be happy to|"
    r"i appreciate (?:you|your)|thanks for (?:the|your))\b",
    re.IGNORECASE)


def _ack_loops(clean):
    out = []
    for m in _ACK_INTENSIFIED.finditer(clean):
        if _mentioned(clean, m.start(), m.end()):
            continue
        out.append({"evidence": m.group(0),
                    "note": "acknowledgment loop — intensified agreement carries "
                            "no information the bare claim did not"})
    for para in re.split(r"\n\s*\n", clean):
        head = para.lstrip()
        if not head:
            continue
        m = _ACK_OPENER.match(head)
        # `head` starts at the paragraph, so there is no left context to read
        # and the only mention risk is the phrase being quoted — which `_prose`
        # has already handled by dropping quote-initial paragraphs. Reading the
        # text that FOLLOWS for cue words was tried and rejected: it suppressed
        # real openers whenever the rest of the sentence merely said "not".
        if m:
            out.append({"evidence": head.splitlines()[0][:100],
                        "note": "acknowledgment loop opens the block — the reply "
                                "spends its first line agreeing"})
    return out


# ---- 2. "it's not X, it's Y" ------------------------------------------------
# The construction the preference names by shape, so it can be matched by shape:
# pronoun-copula, negation, a short X, a separator, then the SAME frame again.
# Requiring the frame twice is what keeps this precise — "that's not spoke-local
# — that's a template gap" matches; "this is not going to work today" does not,
# because nothing repeats the frame. Six real instances in this repo's
# transcripts, e.g. "it's not a bug in the sync — it's contradictory inputs".
_NOT_X_IT_Y = re.compile(
    r"\b(?:it'?s|it is|this is|that'?s|that is|they'?re|these are)\s+not\s+"
    r"(?:just\s+|merely\s+|only\s+|simply\s+)?"
    r"(?P<x>[^.;:\n]{2,60}?)\s*[,—–-]+\s*"
    r"(?:it'?s|it is|this is|that'?s|that is|they'?re|these are)\s+\S",
    re.IGNORECASE)


def _not_x_it_y(clean):
    out = []
    for m in _NOT_X_IT_Y.finditer(clean):
        if _mentioned(clean, m.start(), after=0):
            continue
        out.append({"evidence": m.group(0)[:110],
                    "note": "'it's not X, it's Y' construction"})
    return out


# ---- 3. hollow words --------------------------------------------------------
# Only the words whose hollowness is a property of the word itself. `utilize`
# has an exact shorter synonym in every context ("use"); `seamless` is a claim
# no engineering sentence needs; `foster` in this repo's register is never
# literal. See the module docstring for why `robust` is excluded on measured
# evidence, and why `leverage` is admitted in its verb form only.
_HOLLOW = re.compile(
    r"\b(utiliz(?:e|es|ed|ing|ation)|seamless(?:ly)?|foster(?:s|ed|ing)?)\b",
    re.IGNORECASE)

# Verb-form leverage. The bare stem needs an auxiliary or subject in front of it
# to be a verb; without that guard `\bleverage\b` swallows "unblock leverage"
# and "the highest leverage thing on your desk", which are this repo's own
# metric and are correct usage.
_LEVERAGE_VERB = re.compile(
    r"(?:\b(?:to|can|could|should|would|will|must|we|you|they|i|and|then|"
    r"already|also)\s+(leverage)\b)|\b(leverages|leveraging|leveraged)\b",
    re.IGNORECASE)


def _hollow_words(clean):
    out = []
    for m in _HOLLOW.finditer(clean):
        # A hyphenated compound is a coined term, not the marketing adjective.
        if m.start() and clean[m.start() - 1] == "-":
            continue
        if _mentioned(clean, m.start(), m.end()):
            continue
        out.append({"evidence": m.group(0),
                    "note": f"hollow word '{m.group(0).lower()}' — say the plain thing"})
    for m in _LEVERAGE_VERB.finditer(clean):
        word = m.group(1) or m.group(2)
        at = m.start(1) if m.group(1) else m.start(2)
        if at and clean[at - 1] == "-":
            continue
        if _mentioned(clean, at, at + len(word)):
            continue
        out.append({"evidence": clean[m.start():m.end()],
                    "note": f"hollow word '{word.lower()}' used as a verb — 'use'"})
    return out


# ---- 4. scaffolding preambles ----------------------------------------------
# Only the FIRST line of a block, which is the only place a preamble can live: a
# preamble is defined by deferring the answer, and a sentence in the middle of
# the work defers nothing. A closed list of openers that announce the work
# instead of doing it. Real instance, repeated across four sessions: "I'll start
# by surveying the actual state — savepoints and incoming queues."
#
# This overlaps taste-user-001 (lead with the answer) on purpose. They are two
# preferences the operator stated separately, and a block that opens this way
# violates both; collapsing them would hide one of the two.
_SCAFFOLD = re.compile(
    r"^\s*(?:\*\*|_)?\s*("
    r"let me start by|let me begin by|let me first|"
    r"i'?ll start by|i'?ll begin by|i'?m going to start by|i will start by|"
    r"first,? let me|let'?s dive in|let'?s get started|let'?s begin|"
    r"before (?:we|i) (?:begin|dive|start)|to (?:begin|start) with,|"
    r"i'?ll go ahead and)\b",
    re.IGNORECASE)


def _scaffold(clean):
    lines = [ln for ln in clean.splitlines() if ln.strip()]
    if not lines:
        return []
    head = lines[0].strip()
    m = _SCAFFOLD.match(head)
    if not m or _MENTION_CUE.search(head[:m.start(1)]):
        return []
    return [{"evidence": head[:110],
             "note": "scaffolding preamble — the block announces the work "
                     "instead of leading with it"}]


def detect(text, _pref=None):
    """taste-user-013: subtract the AI tells (4 of 6 sub-rules measurable)."""
    clean = _prose(text)
    return _ack_loops(clean) + _not_x_it_y(clean) + _hollow_words(clean) + _scaffold(clean)
