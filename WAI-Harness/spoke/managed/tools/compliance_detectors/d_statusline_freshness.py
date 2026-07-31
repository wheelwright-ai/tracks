"""Statusline staleness, proved by comparing turns against each other.

WHICH PREFERENCE THIS SERVES. `wai-track-statusline-fidelity` — "the mandatory
per-turn statusline is re-read from the hook's template EVERY turn and rendered
with the values the hook actually supplied, never copied forward from an earlier
turn's rendering". This module carries PREF_ID
`wai-track-statusline-freshness` only because the loader refuses to let a plugin
shadow a built-in, and `d_statusline_model_resolved` already claims the real id.
It is not a second preference; `EXTENDS` routes its findings back onto the
operator's one preference so the score keeps meaning what it says.

WHY A SECOND DETECTOR WAS NEEDED. The built-in judges each statusline ALONE, and
the only thing a lone line can prove is that the model field reads "unknown". So
it caught exactly one field. In session-20260728-0016 the hook supplied, per
turn:

    Turn 1 | ... | 5:17 PM PDT | unknown       | v4.14.18
    Turn 2 | ... | 5:59 PM PDT | claude-opus-5 | v4.14.18
    Turn 3 | ... | 6:47 PM PDT | claude-opus-5 | v4.14.20
    Turn 4 | ... | 8:34 PM PDT | claude-opus-5 | v4.14.21

and turn 1's rendering was emitted verbatim four times. A per-line detector sees
four separate lines that each look plausible; the staleness only exists in the
RELATION between them. Hence: compare across the transcript, not within a line.

WHAT IS ACTUALLY PROVABLE, and nothing beyond it:

  R1  turn regression — the turn number did not strictly advance. Turns are a
      counter; a counter that stalls or goes backwards was not re-read.
  R2  clock regression — a later statusline carries an EARLIER wall time than one
      already emitted. Time does not run backwards, so that line is a copy.
  R3  clock stall — one timestamp emitted under three or more distinct turn
      numbers. Two turns inside one minute is ordinary (a one-word reply); three
      replies, each separated by operator input, inside the same minute is not.

DELIBERATE ABSTENTIONS. A stale harness VERSION is not reported on its own:
`git checkout` of an older cut mid-session legitimately lowers it, so a version
regression is not proof. A stale MODEL field is likewise left to the built-in.
And the SECOND emission of a repeated timestamp is never flagged — only the
third — which means the earliest catchable turn here is turn 3, not turn 2. Each
of these is a knowingly-accepted miss: this toolchain's rule is that a wrong
finding costs more than an admitted gap, because it teaches the reader to
discount the real ones.

STATE, AND WHY IT IS EXPLICIT. The detector contract hands over one block at a
time with no run identity and no index, so a cross-block comparison has nowhere
to live but module scope. Rather than a bare global — which would let one run's
statuslines contaminate the next inside a long-lived process — state is keyed on
the identity of the `pref` object the oracle passes. `evaluate()` passes one
`pref` dict for every block of a run and every run re-reads the graph into fresh
dicts, so that object IS the run. A strong reference is retained alongside the
key so the id cannot be recycled underneath us, the map is capped at a few runs,
and `reset()` exists for callers that reuse a pref object across runs.
"""

import re
from collections import OrderedDict
from datetime import datetime

PREF_ID = "wai-track-statusline-freshness"
EXTENDS = "wai-track-statusline-fidelity"
CLOSING_ONLY = False

# Fenced blocks are structured output, not an emitted statusline. A transcript
# that quotes its own statusline inside ``` is documenting, not stamping.
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

# The anchor does most of the quotation guarding on its own: an emitted
# statusline starts a line. A quoted one is prefixed ("> Turn 3 |"), wrapped
# (`Turn 3 |`, "Turn 3 |"), or indented into a code sample — none of which match.
_STATUS_RE = re.compile(r"^ {0,3}(Turn (\d+)\s*\|[^\n]*)$", re.MULTILINE)

_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\s*(AM|PM)\b(?:\s+([A-Z]{2,5}))?")
_DATE_RE = re.compile(r"\b([A-Z][a-z]{2}, [A-Z][a-z]{2} \d{1,2}, \d{4})\b")

# A run of statuslines introduced as evidence ("the hook supplied:") is a
# transcript OF renderings, not renderings. Narrow and cue-based on purpose.
_QUOTE_LEAD = re.compile(
    r"(quot\w*|verbatim|you (wrote|said|typed)|operator (wrote|said)|"
    r"hook (supplied|emitted|rendered|gave)|per turn|for reference|"
    r"e\.?g\.?|example|emitted)[^\n]{0,60}:\s*$", re.IGNORECASE)

_SAME_STAMP_LIMIT = 3   # distinct turns sharing one timestamp before it is proof


class _RunState:
    """One transcript's worth of statusline history."""

    __slots__ = ("pref", "count", "max_turn", "max_stamp", "stamp_turns")

    def __init__(self, pref):
        self.pref = pref          # strong ref: keeps id(pref) from being recycled
        self.count = 0
        self.max_turn = None
        self.max_stamp = None     # (datetime, tz_label)
        self.stamp_turns = {}     # timestamp key -> set of distinct turn numbers


_RUNS = OrderedDict()
_MAX_RUNS = 4


def reset():
    """Drop all cross-block history. For callers that reuse a `pref` object."""
    _RUNS.clear()


def _state_for(pref):
    key = id(pref)
    st = _RUNS.get(key)
    if st is None or st.pref is not pref:
        st = _RunState(pref)
        _RUNS[key] = st
        while len(_RUNS) > _MAX_RUNS:
            _RUNS.popitem(last=False)
    _RUNS.move_to_end(key)
    return st


def _hhmm(dt):
    """12-hour clock without a leading zero, portably (no %-I)."""
    return dt.strftime("%I:%M %p").lstrip("0")


def _timestamp(line):
    """Return (equality_key, (datetime|None, tz_label)) for a statusline."""
    tm = _TIME_RE.search(line)
    if not tm:
        return None, (None, "")
    dm = _DATE_RE.search(line)
    tz = tm.group(3) or ""
    key = f"{dm.group(1) if dm else ''}|{tm.group(1)} {tm.group(2)}|{tz}"
    stamp = None
    if dm:
        try:
            stamp = datetime.strptime(
                f"{dm.group(1)} {tm.group(1)} {tm.group(2)}", "%a, %b %d, %Y %I:%M %p")
        except ValueError:
            stamp = None
    return key, (stamp, tz)


def _introduced_as_a_quote(text, start):
    """Is the nearest preceding non-empty line an 'here is what was emitted:' cue?"""
    head = text[:start].rstrip("\n")
    for line in reversed(head.splitlines()):
        s = line.strip()
        if not s:
            continue
        if _STATUS_RE.match(line):
            # A run of statuslines inherits the cue that introduced the run.
            continue
        return bool(_QUOTE_LEAD.search(s))
    return False


def detect(text, pref=None):
    """Prove statusline staleness by comparing this block's lines to earlier ones.

    Never fires on the first statusline of a transcript — there is nothing to
    compare it against, and turn 1's "unknown" model is legitimately correct.
    """
    st = _state_for(pref)
    clean = _FENCE_RE.sub("", text)
    out = []

    for m in _STATUS_RE.finditer(clean):
        line = m.group(1).strip()
        if _introduced_as_a_quote(clean, m.start()):
            continue
        turn = int(m.group(2))
        key, (stamp, tz) = _timestamp(line)
        st.count += 1
        first = st.count == 1

        if not first:
            # R1 — the counter must advance.
            if st.max_turn is not None and turn <= st.max_turn:
                out.append({
                    "evidence": line[:120],
                    "note": f"turn number did not advance (turn {turn} after turn "
                            f"{st.max_turn}) — the statusline was carried forward, "
                            "not re-read from the hook",
                })
            # R2 — the clock must not run backwards.
            if (stamp is not None and st.max_stamp is not None
                    and st.max_stamp[0] is not None and tz == st.max_stamp[1]
                    and stamp < st.max_stamp[0]):
                out.append({
                    "evidence": line[:120],
                    "note": f"statusline time runs backwards "
                            f"({_hhmm(stamp)} after {_hhmm(st.max_stamp[0])}) "
                            "— this is an earlier turn's rendering re-emitted",
                })
            # R3 — one wall-clock minute cannot hold three operator turns.
            if key:
                seen = st.stamp_turns.get(key, set())
                if turn not in seen and len(seen) + 1 >= _SAME_STAMP_LIMIT:
                    earlier = ", ".join(str(t) for t in sorted(seen))
                    out.append({
                        "evidence": line[:120],
                        "note": f"timestamp identical across turns {earlier}, {turn} "
                                "— at least one is a copy of an earlier render; "
                                "re-read the hook's line every turn",
                    })

        st.max_turn = turn if st.max_turn is None else max(st.max_turn, turn)
        if key:
            st.stamp_turns.setdefault(key, set()).add(turn)
        if stamp is not None and (st.max_stamp is None or st.max_stamp[0] is None
                                  or stamp > st.max_stamp[0]):
            st.max_stamp = (stamp, tz)

    return out
