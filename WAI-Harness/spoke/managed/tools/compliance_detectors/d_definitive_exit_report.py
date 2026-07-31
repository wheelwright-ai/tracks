"""output-format-definitive-exit-report — the ceremony report names its four parts.

THE PREFERENCE, verbatim: "Every savepoint/closeout ends with a definitive report:
what was accomplished, track closed with net-net, savepoint verified, and an
explicit clear-to-exit verdict." Operator's own words behind it: "I find it very
wishy washy experience after savepoint/closeout."

THE SCOPE TRAP, and the reason this file is mostly gate. The rule governs
SAVEPOINT AND CLOSEOUT REPORTS, not every closing message. Wire it to fire on any
final block and every ordinary reply in every transcript becomes a violation --
a detector that reports a hundred findings reports nothing, and it would be
wrong in the one way this toolchain cannot afford: confidently. So the detector
FIRST proves the block is a ceremony report and abstains when it cannot.

Proving it is harder than grepping for "savepoint", because the word turns up
constantly in work that is not a ceremony: lug ids (`impl-mywheel-savepoint-
skill-validator-reconcile-v1`), file names (`wai-closeout.md`), wakeup banners
(`Savepoint: spec-p12-purposeful-objects`). A real transcript closing in this
repo -- c1e083fb, a three-gap work report -- contains the literal word "closeout"
and is emphatically not a closeout. It is a regression fixture for exactly that.

So the gate wants the ceremony as the SUBJECT of a completion statement, not as a
noun in passing, and it takes one of three forms:

    ANNOUNCEMENT   the opening lines say the ceremony happened
                   ("Savepoint written, validated, committed, pushed.")
    IDENTITY       a savepoint id is named in prose (`sp-session-YYYYMMDD-HHMM-…`)
    VERDICT        an explicit exit verdict is rendered ("CLEAR TO EXIT")

TWO DIRECTIONS, BOTH TOWARD ABSTENTION -- the asymmetry is deliberate and is the
whole precision argument:

  * the GATE reads strip_structured() text only. A savepoint id inside a pasted
    fence or an operator quote is evidence about something the message QUOTES,
    not proof the message IS the report. Stripping makes the gate stricter.
  * ELEMENT PRESENCE reads the FULL text, fences included. This detector reports
    an ABSENCE, so every place an element is allowed to count is a place a false
    violation cannot come from. Several real ceremony reports put their exit
    matrix inside a fenced block; grading them as missing it would be a lie about
    a message that did the right thing.

Stripping for the gate and not for the elements looks inconsistent until you note
both choices push the same way: fewer findings, each one harder to argue with.

WHAT IS NOT MEASURED, said plainly rather than faked:
  * whether the accomplishments listed are COMPLETE or TRUE. This checks that the
    report has an accomplishments section, not that it is honest. No regex reads
    a session.
  * whether "net-net" is genuinely net-net rather than a heading. Same reason.
  * ordering of the four parts. The preference does not require an order.
Those need judgement, and a detector that needs judgement is a preference this
tool should report unmeasurable instead.
"""
import re


def _strip_structured():
    """Borrow the oracle's definition of "structured output", LAZILY.

    Borrowed rather than reimplemented on purpose: if what counts as structure
    ever changes there, this detector must change with it, and a private copy
    would silently drift into scoring text the rest of the suite ignores.

    Lazy because importing it at module scope makes this file's REGISTRATION
    depend on who imports first. `tastegraph_compliance` calls `load()` at the
    bottom of its own import; a top-level import here means that whenever this
    module is imported FIRST, it re-enters the oracle, the oracle re-enters this
    half-built module, and `getattr(m, "PREF_ID")` finds nothing yet. The loader
    then skips it -- not loudly, but into `PLUGIN_ERRORS`, from which the
    preference is reported UNMEASURABLE. A detector that silently stops
    measuring while the run still reports success is the exact false-green this
    toolchain exists to catch, and it was reachable by running this file's own
    tests alone. `d_count_matches_list` already resolves it this way.
    """
    import os
    import sys
    tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    from tastegraph_compliance import strip_structured
    return strip_structured


PREF_ID = "output-format-definitive-exit-report"
CLOSING_ONLY = True

# ---- the gate ---------------------------------------------------------------

# A savepoint id. Ceremonies mint these; nothing else in the wheel writes one in
# prose, so it is the single most specific ceremony signal available.
_SAVEPOINT_ID = re.compile(r"\bsp-session-\d{8}-\d{4}\b", re.IGNORECASE)

# The ceremony as the subject of a completion statement. The verb list is closed
# on purpose: "savepoint drift", "savepoint validator", "savepoint skill" are all
# real strings in this repo's transcripts and none of them are a ceremony.
_ANNOUNCED = re.compile(
    r"\bsavepoint\b[^.\n]{0,70}?\b(taken|saved|written|complete|completed|"
    r"committed|pushed|sealed|validated|verified|updated|refreshed|ejected|"
    r"durable|stands)\b"
    r"|\b(taken|saved|written|completed|committed|pushed|sealed|validated|"
    r"verified|updated|refreshed|ejected)\b[^.\n]{0,40}?\bsavepoint\b"
    r"|\b(closed out|closing out|close(out)? report|closeout complete|"
    r"closeout done|session closed)\b",
    re.IGNORECASE)

# An explicit exit verdict. Rendering one is itself a ceremony act -- the
# preference that governs closings only permits "ready to exit session" once
# savepoint or closeout are already done.
_VERDICT = re.compile(
    r"\b(clear(ed)? to exit|clean to exit|ready to exit|safe to exit|"
    r"safe to eject|safe eject|safe to walk away|not (safe|clear) to exit|"
    r"we are clear to exit)\b",
    re.IGNORECASE)

# Blockquote lines are the operator's words being read back for ratification.
# Grading the agent on the shape of a quotation is the false positive that cost
# this toolchain two findings in session-20260728-0016.
#
# `.*$` and not just `>`. Deleting the MARKER and keeping the sentence left the
# quoted words in the gate's prose, so the guard removed the only evidence that
# a quotation was happening and none of the text being quoted -- it read as a
# guard and behaved as an amplifier. `$` with MULTILINE stops before the
# newline, so the line empties rather than closing up: a vanished line cannot
# pull the lines around it into each other's match window.
_QUOTE_LINE = re.compile(r"^\s*>.*$", re.MULTILINE)

# The same act, inline. A quoted verdict is the message TALKING ABOUT a verdict,
# and this repo talks about its own exit ceremony constantly -- it builds it.
#
# Found by the regression sweep for this file's tests: transcript bfdf3656, a
# three-item work report that reviews the savepoint ceremony and ENDS BY ASKING
# the operator two questions, was graded a wishy-washy closeout. Its only
# ceremony evidence was the clause `the savepoint honestly says "safe to exit"`
# -- a sentence describing what a tool prints, inside a message where nothing
# was closed and nothing was saved. Same class as the `>` guard above; only the
# quotation marks differ, and only the blockquote form had been closed.
#
# Substituted with " . " rather than "" on purpose. The gap clauses in the
# patterns below exclude `.`, so a sentence boundary can only ever REMOVE a
# match. Deleting outright would pull a `savepoint` and a completion verb across
# the vanished span into each other's window and MANUFACTURE an announcement --
# a scrubber that invents the thing it scrubs for.
_INLINE_QUOTE = re.compile(r"[\"“][^\"“”\n]{0,220}[\"”]")


def _gate_text(text):
    """Prose only: no fences, no box-drawing, no quoted words -- block or inline."""
    return _INLINE_QUOTE.sub(" . ", _QUOTE_LINE.sub("", _strip_structured()(text)))


def _headline(prose, lines=2):
    """The opening lines, stripped of markdown chrome.

    Ceremony reports announce themselves at the top -- every one of the fourteen
    real ones sampled from this repo does, in its FIRST line. Requiring the
    announcement up here is what keeps a mid-report aside ("the savepoint
    validator was updated") from reclassifying a work report as a ceremony.

    Two lines, not four. At four this gate claimed transcript 6a774c94 -- an
    autopilot campaign report whose third paragraph happens to confirm a
    savepoint was saved. That message reports a CAMPAIGN; the savepoint line is
    an aside. Every line of slack here converts an aside into a verdict.
    """
    out = []
    for line in prose.splitlines():
        s = re.sub(r"[#*`_✅🟢🟡🔴]", "", line).strip()
        if s:
            out.append(s)
        if len(out) >= lines:
            break
    return " \n".join(out)


def is_ceremony_report(text):
    """Is this block a SAVEPOINT or CLOSEOUT report? Abstain unless proven."""
    prose = _gate_text(text)
    return bool(_SAVEPOINT_ID.search(prose)
                or _ANNOUNCED.search(_headline(prose))
                or _VERDICT.search(prose))


# ---- the four elements ------------------------------------------------------
# Presence is measured over the FULL text (see the module docstring). Each entry
# is (label, pattern); a missing label is named in the finding so the reader is
# told what to add rather than that something is wrong.

_ACCOMPLISHED = re.compile(
    r"what (we|this session|i|the session) (accomplished|shipped|delivered|"
    r"built|did|landed|leaves)"
    r"|what was accomplished|what (this )?session (shipped|delivered|leaves|"
    r"landed|built)"
    r"|\bwork done\b|\baccomplished\b|\bnet-net\b|what landed|"
    r"session'?s? (committed )?arc|this session (shipped|delivered|built|landed)|"
    r"what (this|the) (session|ceremony) leaves|holds:|work_done",
    re.IGNORECASE)

# The track, asserted CLOSED. `track` alone is not enough -- the word appears in
# any session that touched tracking. `net-net` counts on its own because the
# preference names it as the track assertion's content.
_TRACK_CLOSED = re.compile(
    r"\btracks?\b[^.\n]{0,80}?\b(closed|close|flushed|committed|complete|"
    r"completed|sealed|written|intact|rows|entries|pushed)\b"
    r"|\b(closed|flushed|committed|complete|sealed)\b[^.\n]{0,40}?\btracks?\b"
    r"|\bnet-net\b|\btrack\.jsonl\b",
    re.IGNORECASE)

_SAVEPOINT_VERIFIED = re.compile(
    r"\bsavepoint\b[^.\n]{0,90}?\b(verified|validated|validates|valid|"
    r"resume contract|committed|pushed|sealed|saved|written|ok\b)"
    r"|\b(verified|validated|resume contract|committed|pushed|sealed)\b"
    r"[^.\n]{0,60}?\bsavepoint\b"
    r"|savepoint (verified|validated)|resume contract (satisfied|validated|ok)",
    re.IGNORECASE)

_ELEMENTS = [
    ("what was accomplished", _ACCOMPLISHED),
    ("track closed with net-net", _TRACK_CLOSED),
    ("savepoint verified", _SAVEPOINT_VERIFIED),
    ("explicit clear-to-exit verdict", _VERDICT),
]


def detect(text, _pref):
    """Fire only on a proven ceremony report that omits a named element.

    One finding per report, listing every missing element. Emitting four separate
    findings for one wishy-washy closing would inflate the violation count without
    adding a single fact -- and the count is what the ledger trends.
    """
    if not is_ceremony_report(text):
        return []

    missing = [label for label, pat in _ELEMENTS if not pat.search(text)]
    if not missing:
        return []

    head = _headline(_gate_text(text))
    return [{
        "evidence": head[:110],
        "note": ("savepoint/closeout report is missing " + ", ".join(missing)
                 + " — the operator called this the 'wishy washy' closing"),
    }]
