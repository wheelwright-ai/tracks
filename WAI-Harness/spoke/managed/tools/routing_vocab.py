#!/usr/bin/env python3
"""routing_vocab — the canonical vocabulary for a lug's `routed_to`, and a resolver for it.

WHY THIS EXISTS
---------------
`routed_to` answers one question: where does this work go? Until now nothing defined the
legal answers, so one destination acquired five spellings and the dispatchers matched them
as exact literals. Measured on 2026-07-26 across 638 open/in_progress lugs:

    LOCAL 367 | FRAMEWORK 51 | mywheel 28 | SPOKE/mywheel 20 | BASHER 17 | MYWHEEL 10
    basher 8 | SPOKE/wheelwright-hub 6 | local 5 | hub 3 | HUB 2 | (absent) 117
    + CHANGE, SIGNAL, operator, crew, track-collector as singletons

ozi_headless dispatched on the exact-match set {LOCAL, FRAMEWORK, WHEELWRIGHT_FRAMEWORK},
so 221 of those 638 lugs — 35% of the live backlog — were invisible to it. Not blocked,
not rejected: invisible, because of how a word was cased. This module is the fix, and it
is why the FRAMEWORK rename could not simply be finished: renaming FRAMEWORK to mywheel
would have moved 51 lugs OUT of the dispatchable set.

THE CANONICAL VOCABULARY (exactly three shapes, nothing else is valid)
---------------------------------------------------------------------
    LOCAL              this wheel does the work
    SPOKE/<wheel_id>    a named sibling does the work; wheel_id comes from hub-registry
    SIGNAL             goes to the hub signals inbox, for every spoke

DESIGN RULES
------------
1. Resolution is by MEANING, not by string. "FRAMEWORK" on mywheel means LOCAL, because
   mywheel absorbed that role. The same value on basher means SPOKE/mywheel.
2. Unresolvable is LOUD. A value this module does not understand returns None and is
   reported by name. Silently defaulting an unknown destination to LOCAL would convert a
   routing mistake into local work — a worse failure than refusing.
3. Sibling identity comes from hub-registry.json, never a hardcoded list.
4. Deprecated repos resolve, with a deprecation note attached. wheelwright-framework and
   wheelwright-hub were both superseded by mywheel; a lug addressed to either is
   unreachable, which is how one sat untouched for 991 hours.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

LOCAL = "LOCAL"
SIGNAL = "SIGNAL"
SPOKE_PREFIX = "SPOKE/"

# Repos that were superseded by mywheel. A lug routed at one of these has no session that
# can ever pick it up, so these resolve to mywheel and carry a deprecation note.
DEPRECATED_WHEELS = {"wheelwright-framework", "wheelwright-hub", "framework", "hub"}

# Legacy spellings that all mean "the master/hub wheel", i.e. mywheel. FRAMEWORK is here
# rather than being renamed precisely because renaming it in place would un-dispatch it.
MASTER_ALIASES = {
    "framework", "wheelwright_framework", "wheelwright-framework",
    "mywheel", "wheelwright-hub", "hub", "master",
}

# Values that were never destinations — they are lug types, actors or artefacts that ended
# up in the routing field. They resolve to nothing and must be reported, not guessed.
NON_DESTINATIONS = {"change", "operator", "crew", "signal_type", "none", "null"}


def _registry_path(root="."):
    return os.path.join(root, "WAI-Harness", "hub", "local", "hub-registry.json")


def load_registry(root="."):
    """{wheel_id: status} from the registry of record. {} if unreadable."""
    try:
        with open(_registry_path(root)) as fh:
            return {w["wheel_id"]: w.get("status", "unknown")
                    for w in json.load(fh).get("wheels", []) if w.get("wheel_id")}
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return {}


def this_wheel_id(root="."):
    """This wheel's canonical id, resolved from the most trustworthy source available.

    The nested/top-level split is real: ozi_autopilot reads state['wheel_id'] while
    emit_activity_event reads state['wheel']['wheel_id'], and on mywheel NEITHER is set —
    which is exactly how a challenge report shipped with spoke_id 'unknown'. The registry
    path match is the reliable answer, so it sits ahead of the basename guess.
    """
    env = os.environ.get("WHEEL_ID")
    if env:
        return env
    state = {}
    for rel in ("WAI-Harness/spoke/local/WAI-State.json", "WAI-Spoke/WAI-State.json"):
        try:
            with open(os.path.join(root, rel)) as fh:
                state = json.load(fh)
            break
        except (OSError, json.JSONDecodeError):
            continue
    wheel = state.get("wheel", {}) if isinstance(state, dict) else {}
    for cand in (state.get("wheel_id"), wheel.get("wheel_id"), wheel.get("spoke_id")):
        if cand:
            return cand
    here = os.path.abspath(root)
    try:
        with open(_registry_path(root)) as fh:
            for w in json.load(fh).get("wheels", []):
                if w.get("path") and os.path.abspath(w["path"]) == here:
                    return w["wheel_id"]
    except (OSError, json.JSONDecodeError):
        pass
    return os.path.basename(here)


def resolve(routed_to, wheel_id=None, root="."):
    """Map any routed_to value onto the canonical vocabulary.

    Returns {value, dispatchable, deprecated, note}. `value` is None when the input cannot
    be understood — the caller must surface that, never substitute a default.
    """
    if wheel_id is None:
        wheel_id = this_wheel_id(root)

    def out(value, note=None, deprecated=False):
        return {"value": value, "dispatchable": value == LOCAL,
                "deprecated": deprecated, "note": note}

    # Absent is not ambiguous in practice: authors omit routed_to when the work is theirs.
    # Made explicit here so the default stops being invisible.
    if routed_to is None or (isinstance(routed_to, str) and not routed_to.strip()):
        return out(LOCAL, "routed_to absent — treated as LOCAL (the authoring wheel)")

    if not isinstance(routed_to, str):
        return out(None, f"routed_to is {type(routed_to).__name__}, expected a string")

    raw = routed_to.strip()
    low = raw.lower()

    if low == "local":
        return out(LOCAL)
    if low == "signal":
        return out(SIGNAL, "hub signals inbox — every spoke")

    target = raw[len(SPOKE_PREFIX):].strip() if low.startswith("spoke/") else raw
    tlow = target.lower()

    if tlow in NON_DESTINATIONS:
        return out(None, f"'{raw}' is not a destination — it names a lug type or an actor")

    if tlow in MASTER_ALIASES:
        deprecated = tlow in DEPRECATED_WHEELS
        note = (f"'{raw}' names a deprecated repo superseded by mywheel — unreachable as routed"
                if deprecated else None)
        if wheel_id == "mywheel":
            return out(LOCAL, note or f"'{raw}' means this wheel", deprecated)
        return out(SPOKE_PREFIX + "mywheel", note, deprecated)

    registry = load_registry(root)
    match = next((w for w in registry if w.lower() == tlow), None)
    if match:
        if match == wheel_id:
            return out(LOCAL, f"'{raw}' names this wheel")
        status = registry[match]
        note = (f"sibling '{match}' is {status} — it has no session to work this lug"
                if status != "active" else None)
        return out(SPOKE_PREFIX + match, note)

    return out(None, f"'{raw}' matches no registered wheel_id and no known alias")


# ------------------------------------------------------------------------ audit

# LIVE states — a lug in any of these can still be worked, so its routing must be correct.
# Enumerated rather than assumed: the first version of this list named only open/,
# in_progress/ and incoming/, so the audit reported "0 invisible" while 20 lugs in active/
# and 17 in needs_attention/ were never looked at. An oracle with an unexamined scope
# reports on the part it happens to cover and sounds exactly like full coverage.
LIVE_STATES = ("open", "in_progress", "active", "needs_attention", "flagged",
               "draft", "deferred", "parked", "acknowledged", "undelivered")

# TERMINAL states — historical provenance, deliberately left alone.
TERMINAL_STATES = ("completed", "closed", "retired", "resolved", "delivered")


# ====================================================================== CANON
#
# OPERATOR RULING (2026-07-31): "Wheelwright must be canonical so no disagreement
# over status values or expected locations and behaviors."
#
# THE PROBLEM THIS FIXES. Measured the same day on one spoke: 30 DISTINCT status
# values across 2,400+ lugs, and TERMINAL_STATES defined in three modules with
# different contents — so work_split counted a lug in state "done" as finished
# while routing_vocab counted it as live. The same lug, two answers.
#
# THE CUT, which is the operator's: "Done doesn't infer implemented — perhaps a
# sub-status or resolution is needed." One field was carrying two questions.
#
#   CANONICAL_STATUS      WHERE a lug is. Matches the directories exactly, so the
#                         filesystem and the field can never disagree.
#   CANONICAL_RESOLUTION  HOW a completed lug ended. Required when completed,
#                         meaningless otherwise. Stored in `resolution_class`.
#
# WHY resolution_class AND NOT resolution. The obvious field name was already
# taken, and finding that out is the whole reason the operator said "not assume it
# — a simple validation is worth it considering the importance of this spoke being
# our harness." Measured 2026-07-31: 126 lugs already store FREE-TEXT narrative in
# `resolution`, one of them 1,592 characters of reasoning about why something was
# closed, plus 18 storing structured dicts. Backfilling `resolution = implemented`
# would have overwritten 144 operator-written explanations with a single word.
# The controlled vocabulary therefore lives in its own field and the prose is left
# exactly where it is.
#
# "done" is deliberately ABSENT from both. It is the word that started this: it
# says a lug stopped without saying whether it was built, decided or abandoned.
# LEGACY_STATUS_MAP records where each historical value goes; a value mapping to a
# resolution of None needs a human, and the migration must PARK it rather than
# guess — mapping done -> implemented is a guess about work someone else did.
#
# Everything else in the wheel IMPORTS these. A second copy is a defect on sight,
# whether or not it currently agrees, because nothing keeps copies in step.
# Detector: contract_duplication_scan.py --fail-on-disagree.

CANONICAL_STATUS = ("open", "in_progress", "needs_attention", "completed")

CANONICAL_RESOLUTION = ("implemented", "delivered", "decided", "superseded",
                        "duplicate", "wont_do", "retired")

# historical value -> (canonical status, canonical resolution or None if a human
# must decide). None NEVER means "pick something sensible"; it means park it.
LEGACY_STATUS_MAP = {
    "completed":       ("completed", None),          # already canonical; resolution unknown
    "open":            ("open", None),
    "in_progress":     ("in_progress", None),
    "needs_attention": ("needs_attention", None),
    "resolved":        ("completed", "implemented"),
    "delivered":       ("completed", "delivered"),
    "published":       ("completed", "delivered"),
    "implemented":     ("completed", "implemented"),
    "archived":        ("completed", "retired"),
    "retired":         ("completed", "retired"),
    "decided":         ("completed", "decided"),
    "accepted":        ("completed", "decided"),
    "superseded":      ("completed", "superseded"),
    "duplicate":       ("completed", "duplicate"),
    "wont_do":         ("completed", "wont_do"),
    "closed":          ("completed", None),          # ambiguous: built or abandoned?
    "done":            ("completed", None),          # THE ambiguous one — never guess
    "active":          ("in_progress", None),
    "draft":           ("open", None),
    "pending":         ("open", None),
    "deferred":        ("open", None),
    "parked":          ("open", None),
    "flagged":         ("needs_attention", None),
    "needs_review":    ("needs_attention", None),
    "undelivered":     ("open", None),
    "acknowledged":    ("in_progress", None),
}


def canonicalise(status):
    """Map any historical status onto (canonical_status, resolution_or_None).

    Returns (None, None) for a value with no mapping — reported, never guessed.
    A caller that turns an unmapped value into a plausible one rewrites history
    silently, which is the failure this whole canon exists to remove.
    """
    if not status:
        return (None, None)
    return LEGACY_STATUS_MAP.get(str(status).strip().lower(), (None, None))

LUG_GLOBS = tuple(
    f"WAI-Harness/spoke/local/lugs/bytype/*/{s}/*.json" for s in LIVE_STATES
) + ("WAI-Harness/spoke/local/lugs/incoming/*.json",)


def audit(root="."):
    """The initiative's oracle: how many live lugs are invisible for spelling reasons."""
    wheel_id = this_wheel_id(root)
    rows, unresolvable, by_raw = [], [], {}
    for pattern in LUG_GLOBS:
        for path in sorted(glob.glob(os.path.join(root, pattern))):
            try:
                with open(path) as fh:
                    lug = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            raw = lug.get("routed_to")
            r = resolve(raw, wheel_id, root)
            key = "(absent)" if raw in (None, "") else str(raw)
            by_raw.setdefault(key, {"count": 0, "resolved": r["value"]})
            by_raw[key]["count"] += 1
            row = {"lug": lug.get("id") or lug.get("i") or os.path.basename(path),
                   "path": os.path.relpath(path, root), "raw": raw, **r}
            rows.append(row)
            if r["value"] is None:
                unresolvable.append(row)

    # "Invisible for spelling" = would dispatch once resolved, but the stored literal is
    # not one the legacy exact-match set recognised. This is the number that must reach 0.
    LEGACY_EXACT = {"LOCAL", "FRAMEWORK", "WHEELWRIGHT_FRAMEWORK"}
    invisible = [r for r in rows if r["dispatchable"] and str(r["raw"]) not in LEGACY_EXACT]

    return {
        "wheel_id": wheel_id,
        "lugs": len(rows),
        "dispatchable": sum(1 for r in rows if r["dispatchable"]),
        "invisible_for_spelling": len(invisible),
        "unresolvable": len(unresolvable),
        "deprecated_targets": sum(1 for r in rows if r["deprecated"]),
        "by_raw_value": dict(sorted(by_raw.items(), key=lambda kv: -kv[1]["count"])),
        "unresolvable_detail": unresolvable,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="routing_vocab — canonical routed_to vocabulary")
    ap.add_argument("--audit", action="store_true", help="audit live lugs")
    ap.add_argument("--resolve", metavar="VALUE", help="resolve a single value")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.resolve is not None:
        r = resolve(a.resolve, root=a.root)
        print(json.dumps(r, indent=2) if a.json
              else f"{a.resolve!r} -> {r['value']}  dispatchable={r['dispatchable']}"
                   + (f"  [{r['note']}]" if r["note"] else ""))
        return 0 if r["value"] else 1

    if a.audit:
        rep = audit(a.root)
        if a.json:
            print(json.dumps(rep, indent=2))
        else:
            print(f"routing_vocab --audit   (wheel: {rep['wheel_id']})")
            print(f"  live lugs                : {rep['lugs']}")
            print(f"  dispatchable (resolved)  : {rep['dispatchable']}")
            print(f"  invisible for spelling   : {rep['invisible_for_spelling']}   <- target 0")
            print(f"  unresolvable             : {rep['unresolvable']}")
            print(f"  deprecated targets       : {rep['deprecated_targets']}")
            print("  raw values in use:")
            for raw, info in rep["by_raw_value"].items():
                print(f"    {info['count']:>4}  {raw:<28} -> {info['resolved']}")
            for row in rep["unresolvable_detail"]:
                print(f"    UNRESOLVABLE {row['lug']}: {row['note']}")
        return 0 if rep["unresolvable"] == 0 else 1

    ap.error("need --audit or --resolve")


if __name__ == "__main__":
    sys.exit(main())
