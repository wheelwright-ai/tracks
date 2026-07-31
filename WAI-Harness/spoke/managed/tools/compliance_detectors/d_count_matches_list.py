"""taste-user-012 rule (3): "if I say N items, show all N."

THE ACCOMMODATION, not a style rule. The operator has ADHD and dyslexia. When a
message promises "three things that need you" and then lists two, he cannot tell
whether the third was dropped, merged, or is further down the page — so he has to
re-read the whole block to find out. That re-read is the cost the accommodation
exists to remove, and he names the mismatch a hard failure he will call out.

WHY THIS DETECTOR IS MOSTLY ABSTENTION. Numbers saturate this corpus for reasons
that have nothing to do with enumeration, and every one of them was observed in
real transcripts under ~/.claude/projects/-home-mario-projects-wheelwright-mywheel:

    "Now distributing 4.14.11 so the fix actually reaches the fleet:"
    "Bumping VERSION to 4.14.1 and recutting the MANIFEST:"
    "Gate green (4/4). Committing the recut + the 4 stranded hooks together:"
    "The spoke HAS tests/critical_paths.sh ... Reproducing to find the 1 failure:"

Each of those ends in a colon and contains a cardinal. None is a promise to
enumerate. A detector that reads "a number near a colon" as a count promise would
fire on all four, and a compliance oracle that cries wolf on version stamps is
worth less than no oracle at all — a wrong finding trains the reader to discount
the real ones. So this detector is built to abstain by default and to fire only on
a shape that cannot plausibly mean anything else.

WHAT IT PROVES, the whole measurable sub-case:

    a single cardinal (2..20), followed by a plural noun, ending a line with ':'
    then a contiguous top-level list of one consistent marker family
    whose item count is strictly FEWER than the cardinal promised

Everything else is reported by silence. See UNMEASURED at the bottom of this file
for what was deliberately left out and why — those are honest gaps, not oversights,
and the oracle's contract is that an admitted gap beats an invented number.
"""
import re

PREF_ID = "taste-user-012"
CLOSING_ONLY = False

# ---- the count promise ------------------------------------------------------

_NUMWORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
             "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}

# Cardinal, guarded against version numbers, ratios and percentages. The lookarounds
# are the load-bearing part: without `(?<![\d./])` the "11" inside "4.14.11" is a
# perfectly good \b-delimited two-digit number, and "4.14.11 so the fix reaches the
# fleet:" becomes an eleven-item promise. Observed verbatim in the corpus, which is
# why the guard is here and not left to a noun check downstream.
#   (?<![\d./%-])  no digit/dot/slash before  -> kills 4.14.11, 4/4, 90-95
#   (?![\d./%x])   no digit/dot/slash/%/x after -> kills 4.14, 4/4, 80%, 3x
_CARDINAL = re.compile(
    r"(?<![\d./%\-])\b(\d{1,2}|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve)\b(?![\d./%]|x\b)", re.IGNORECASE)

# Nouns that are units of measure, not enumerable things. "3 times faster:",
# "2 hours of budget:" and "12 minutes:" all carry a cardinal and a plural noun but
# promise nothing to enumerate. Kept small on purpose — every entry here is a case
# the detector will never see again, and a long speculative list is just a second
# place for the detector to be wrong.
_UNIT_NOUNS = {
    "times", "days", "hours", "minutes", "seconds", "weeks", "months", "years",
    "mins", "secs", "msecs", "tokens", "bytes", "chars", "characters",
    "dollars", "cents", "percent", "degrees", "pixels",
}

# Words that end in -s but are not nouns. The morphology test below already drops
# -ss/-us/-is and anything under four letters (was, has, its, as), so this only has
# to cover the survivors seen in practice.
_NON_NOUNS = {"does", "goes", "always", "perhaps", "whereas", "hence", "else"}

# Phrases that legitimately introduce a SUBSET. "the top 3 offenders:",
# "3 of the 12 failures:", "a few of the 5 spokes:" — showing fewer than the set
# size is correct there, so the promise is not a promise and the detector abstains.
_SUBSET_CUES = re.compile(
    r"\b(e\.?g\.?|for example|for instance|such as|including|includes|among|"
    r"top|first|last|best|worst|biggest|highest|lowest|largest|a few|some of|"
    r"one of|couple of|out of|of the|of these|of those|so far|sample|examples?|"
    r"headliners?|highlights?|notably|breaks? down|break down as)\b",
    re.IGNORECASE)

# A sentence boundary between the cardinal and the colon means the number belongs
# to an EARLIER sentence and the list belongs to a later one. This single guard
# removed seven of the fifteen candidate fires in a full-corpus sweep, every one of
# them a case where the number was incidental:
#
#   "...(impact 10), operator-stamped. It tells Basher to:"        -> a score
#   "**Work:** 17 open lugs. Headliners:"                          -> a total
#   "All 9 spokes: **v4.1.0, mode v4, config ok** ... readiness:"   -> a fleet size
#
# Matching only a period/!/? that is followed by whitespace keeps `4.14.11`,
# `wai-enter.sh` and `CLAUDE.md` from reading as sentence ends.
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")

# A determiner in front of the cardinal makes it REFERENTIAL — it points back at a
# set already established — rather than a promise to lay one out now. Compare:
#
#   "Three failures, all real bugs the tests caught:"   introduces  -> measurable
#   "Committing the recut + the 4 stranded hooks:"      refers back -> abstain
#   "All 9 spokes: v4.1.0, mode v4, config ok ...:"     refers back -> abstain
#
# The second and third are real corpus lines, and the colon after them introduces
# an ACTION, not an enumeration. Losing the occasional genuine "the three things
# you must decide:" is the cheap error here; firing on every backward reference to
# a known set is the expensive one.
_DETERMINER = re.compile(
    r"\b(the|these|those|both|all|its|his|her|their|our|my|your|same|other|"
    r"remaining|above|below)\s+$", re.IGNORECASE)

# Verbatim operator quotation. Grading the agent on the shape of the operator's own
# sentences is the false positive the oracle already learned once (see _QUOTED in
# tastegraph_compliance.py, added after both dyslexia violations in
# session-20260728-0016 turned out to be his words quoted back for ratification).
# The oracle exposes strip_structured but no span helper, so the quote test lives
# here: a line that opens with a quote mark or a blockquote marker is his, and a
# promise sitting inside a "..." span on any line is his too.
_QUOTE_OPEN = re.compile(r'^\s*(?:>|["“‘«])')
_QUOTED_SPAN = re.compile(r'"[^"\n]{1,400}"|“[^”\n]{1,400}”')


def _cardinals(line):
    """Every countable cardinal in `line`, version stamps and ratios excluded.

    Split out from _promise so the version guard is directly testable — it is the
    guard most likely to be loosened by a future edit and the one whose failure is
    least visible, because a version number reads as a perfectly ordinary integer
    once it is out of context.
    """
    return list(_CARDINAL.finditer(line))


def _plural_noun(word):
    """Morphological plural test. Deliberately crude, deliberately strict."""
    w = word.lower()
    if len(w) < 4 or not w.endswith("s"):
        return False
    if w.endswith(("ss", "us", "is", "ous")):
        return False
    return w not in _UNIT_NOUNS and w not in _NON_NOUNS


def _promise(line):
    """Return N if `line` is a header promising to enumerate N things, else None.

    A header qualifies only when it ends in a colon and contains EXACTLY ONE
    cardinal. The single-cardinal rule is not fussiness — it is the fix for the two
    real headers that would otherwise be scored as under-listing when they are
    correct:

        "Status - three things moved, one is holding on purpose:"   -> 4 items
        "I have what I need. Two things fire now, one waits:"       -> 2 items

    Both promise a compound set ("three ... plus one more"), and no deterministic
    reading resolves the arithmetic. Two cardinals means abstain.
    """
    if not line.rstrip().endswith(":"):
        return None
    if _QUOTE_OPEN.match(line):
        return None

    nums = _cardinals(line)
    if len(nums) != 1:
        return None
    m = nums[0]

    # Inside a quoted span -> operator's words, not the agent's structure.
    for q in _QUOTED_SPAN.finditer(line):
        if q.start() <= m.start() < q.end():
            return None

    # Referential, not introductory. See _DETERMINER.
    if _DETERMINER.search(line[:m.start()]):
        return None

    raw = m.group(1).lower()
    n = _NUMWORDS.get(raw) or (int(raw) if raw.isdigit() else 0)
    # N=1 is trivially satisfied and N>20 is statistics, not a list a human writes
    # out. Both ends are cut so the detector only speaks where it has something.
    if not 2 <= n <= 20:
        return None

    # The plural noun must be the cardinal's own head, so allow at most two
    # intervening adjectives: "3 stranded hooks", "two open threads". Any further
    # and the number is describing something else in the sentence.
    tail = line[m.end():]
    words = re.findall(r"[A-Za-z][\w\-]*", tail)[:3]
    if not any(_plural_noun(w) for w in words):
        return None

    # The promise must reach the colon unbroken. See _SENTENCE_END.
    if _SENTENCE_END.search(tail):
        return None
    if _SUBSET_CUES.search(line):
        return None
    return n


# ---- the list that follows --------------------------------------------------

# NUMBERED LISTS ONLY, and this is the single most important decision in the file.
#
# A full-corpus sweep produced fifteen candidate fires. Eleven sat over BULLET
# lists, and all eleven were wrong for the same reason: bullets GROUP. The author
# promises a true count and then packs it into fewer bullets, which is good writing
# and not a violation:
#
#   "**3 files deliberately left uncommitted**:"   -> 2 bullets, one covering
#                                                     `wai-enter.sh`/`wai-exit.sh`
#   "The 12 drifted managed files break down as:"  -> 2 bullets, "9 are mine" +
#                                                     "3 are NOT mine"
#   "**mywheel repo** — 7 items:"                  -> 5 bullets, one holding three
#                                                     `??` paths
#
# There is no deterministic way to tell a grouped bullet from a missing item, so
# bullets are abstained on entirely. A numbered list is different in kind: the
# author who writes `1.` `2.` `3.` has committed to one number per item, and the
# numerals themselves are the oracle. This also lands squarely on the operator's
# own rule (5) — "number things so I can point at them" — so the measurable case
# is the case he actually asks for.
_NUMBERED = re.compile(r"^\*{0,2}(\d{1,2})[.)]\s+\S")
_BULLET = re.compile(r"^[-*•]\s+\S")

# An item that trails off is an admitted partial list, not a broken promise.
_TRUNCATED = re.compile(r"(…|\.\.\.|\(truncated|and \d+ more|etc\.)\s*$",
                        re.IGNORECASE)

# Section breaks. A rule or heading ends the list no matter what follows.
_SECTION_BREAK = re.compile(r"^(#{1,6}\s|-{3,}\s*$|\*{3,}\s*$|={3,}\s*$)")

# How much blank space may sit between the header and its list. Three lines is
# generous for markdown and still tight enough that a list belonging to a LATER
# paragraph cannot be dragged up here. It matters more than it looks: the oracle's
# strip_structured() blanks out tables and box-drawing, so a header whose
# enumeration was a table arrives at this function as a run of empty lines.
_MAX_GAP = 3

# How far to look for the NEXT numeral. Items in this corpus run long — a numbered
# item is regularly a bold title followed by unindented explanatory lines — so the
# scan cannot stop at the first line that is not itself a numeral.
_ITEM_SPAN = 40


def _numbered_run(lines, start):
    """Length of the consecutive 1,2,3,... run directly under `lines[start]`.

    Returns (count, truncated) or None to abstain.

    Consecutive-from-1 is what makes this safe against the two ways a naive item
    count goes wrong. Long items whose continuation lines sit at column zero used
    to end the count early — caught in the corpus on "using the two advisor slots
    it already reserved:", where `**1.` and `**2.` were separated by an unindented
    "Watches: ..." line and a line-by-line counter saw one item and called a
    compliant message a violation. And a run that does not start at 1 is somebody
    else's list, so it is abstained on rather than counted from the middle.
    """
    i, gap = start + 1, 0
    while i < len(lines) and not lines[i].strip():
        gap += 1
        if gap > _MAX_GAP:
            return None
        i += 1
    if i >= len(lines):
        return None

    first = _NUMBERED.match(lines[i])
    # Bullets and prose are not countable here; see the note above _NUMBERED.
    if not first or int(first.group(1)) != 1:
        return None

    count, truncated, expect = 1, bool(_TRUNCATED.search(lines[i])), 2
    i += 1
    while i < len(lines):
        if _SECTION_BREAK.match(lines[i]):
            break
        m = _NUMBERED.match(lines[i])
        if m and int(m.group(1)) == expect:
            count, expect = expect, expect + 1
            truncated = truncated or bool(_TRUNCATED.search(lines[i]))
            i += 1
            continue
        if m and int(m.group(1)) != expect:
            break          # a different numbered list started
        # Not a numeral: body text, a nested bullet, a blank. Keep looking for the
        # next numeral, but only within one item's worth of lines.
        j, span = i, 0
        while (j < len(lines) and span < _ITEM_SPAN
               and not (_NUMBERED.match(lines[j])
                        and int(_NUMBERED.match(lines[j]).group(1)) == expect)
               and not _SECTION_BREAK.match(lines[j])):
            j += 1
            span += 1
        if j >= len(lines) or span >= _ITEM_SPAN or _SECTION_BREAK.match(lines[j]):
            break
        i = j
    return count, truncated


# ---- detector ---------------------------------------------------------------

def _strip_structured():
    """The oracle's own stripper, imported late.

    Deferred because the oracle imports this package at module scope, so a
    top-level import here would close a cycle. Resolved through the oracle rather
    than reimplemented locally on purpose: if the definition of "structured output"
    ever changes there, this detector must change with it, and a private copy would
    silently drift into scoring text the rest of the suite ignores.
    """
    import os
    import sys
    tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from tastegraph_compliance import strip_structured
    return strip_structured


def detect(text, _pref):
    """Fire only on a promised count strictly greater than the list beneath it."""
    lines = _strip_structured()(text).splitlines()
    out = []
    for i, line in enumerate(lines):
        n = _promise(line)
        if n is None:
            continue
        found = _numbered_run(lines, i)
        if found is None:
            continue
        count, truncated = found
        if truncated:
            continue
        # UNDER-listing only. Over-listing is not scored: the real corpus shows
        # headers that add items after the cardinal ("three things moved, one is
        # holding on purpose:" -> 4 items, which is correct), and the compound-
        # cardinal guard cannot catch every phrasing of that. Under-listing is the
        # failure the operator actually named, and it is the half that is provable.
        if count < n:
            out.append({
                "evidence": f"{line.strip()[:100]}  ->  {count} item(s) listed",
                "note": f"promised {n}, listed {count} — a count that does not "
                        f"match the list is a hard failure (taste-user-012 rule 3)",
            })
    return out


# ---- UNMEASURED, and why -----------------------------------------------------
#
# 1. Enumerations rendered as TABLES or boxes. strip_structured() removes
#    box-drawing before this detector sees the text, so "Of the 12 diverged files:"
#    arrives as a header over blank lines. Counting table rows would mean parsing
#    what the oracle deliberately discards, and the corpus shows the operator often
#    gets his sets as tables (he asks for them). Abstained.
#
# 2. Enumerations written as PROSE ("first ... second ... also ..."). No reliable
#    boundary between an enumerated item and a sentence that happens to start with
#    "also". This is judgement, and judgement is what this oracle refuses.
#
# 3. OVER-listing. Reported by silence, for the reason in detect() above.
#
# 4. COMPOUND promises ("three things moved, one is holding"). Two cardinals, no
#    deterministic arithmetic. Abstained by the single-cardinal rule.
#
# 5. Counts stated in a LATER sentence than the list, or in a heading two
#    paragraphs up. Only the line immediately above the list is considered.
#
# 6. The other five rules of taste-user-012 (magnitude-first, short lines,
#    no emoji, numbering, tables-over-paragraphs). Emoji is already covered by
#    taste-user-004; the rest are unmeasurable by regex and stay that way.
