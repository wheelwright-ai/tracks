#!/usr/bin/env python3
"""Materialise open threads into durable lugs.

The resume problem this solves: open threads live in the resident digest, which is
derived from CONVERSATION. Lose the session and the thread text survives, but the
work it represents has no lug, no owner, and no place in the backlog — so the next
session reconstructs intent by reading a transcript instead of picking up work.

After this runs, every open thread has a lug in `bytype/`. Resume reads the
backlog, not the conversation.

CORRESPONDENCE. Thread and lug point at each other and stay in step:

    thread.lug_id      -> the lug carrying this thread
    lug._thread_id     -> the thread that produced it
    lug.verify         <- the thread's landing condition, verbatim

The landing condition becoming `verify` is the point: a thread already carries a
machine-checkable definition of done, which is exactly what a lug needs and what
hand-authored lugs most often lack.

IDEMPOTENT. Lug ids derive from thread ids, so re-running updates rather than
duplicating. Threads whose lug already exists are left alone.

GATE-COMPLIANT BY CONSTRUCTION. Generated lugs satisfy lug_gate (PEV,
acceptance_criteria, file_targets, model_fit_reason, _improvement_lenses) because
a materialiser that emits blocked lugs would wedge the next commit for everyone.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_LUG_TYPE = "task"
# Every state a materialised lug might have MOVED to. Narrower than this and the
# tool re-creates a lug that already exists further along its lifecycle: three
# lugs moved to flagged/ during an autopilot run and would have been duplicated.
try:
    from work_split import LIVE_STATES, TERMINAL_STATES
    _STATES = tuple(LIVE_STATES) + tuple(TERMINAL_STATES)
except Exception:  # pragma: no cover
    _STATES = ("open", "in_progress", "completed", "flagged", "active",
               "needs_attention", "parked", "deferred", "draft", "closed", "done")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _base(root):
    v4 = os.path.join(root, "WAI-Harness", "spoke", "local")
    return v4 if os.path.isdir(v4) else os.path.join(root, "WAI-Spoke")


def _digest_path(root):
    return os.path.join(_base(root), "resident", "digest.json")


def _lug_dir(root, state="open"):
    return os.path.join(_base(root), "lugs", "bytype", _LUG_TYPE, state)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _slug(text, limit=48):
    out = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (out[:limit].rstrip("-")) or "thread"


def lug_id_for(thread):
    """Deterministic id so re-running updates instead of duplicating."""
    return "thread-%s-%s-v1" % (_slug(thread.get("text"), 40), thread.get("id", "unknown"))


def _existing_lug_path(root, lug_id):
    for state in _STATES:
        candidate = os.path.join(_lug_dir(root, state), lug_id + ".json")
        if os.path.isfile(candidate):
            return candidate
    return None


def _landing_prose(landing):
    """Render a landing condition as a verify criterion a human can act on."""
    if not isinstance(landing, dict):
        return "Landing condition unrecorded — define one before closing."
    kind = landing.get("kind")
    if kind == "file_exists":
        return "File exists: %s" % landing.get("path")
    if kind == "file_contains":
        return "%s contains %r" % (landing.get("path"), landing.get("needle"))
    if kind == "lug_completed":
        return "Lug %s has reached completed/" % landing.get("id")
    if kind == "commit":
        return "Commit %s is an ancestor of HEAD" % landing.get("sha")
    if kind == "command":
        return "Command exits 0: %s" % landing.get("cmd")
    if kind == "manual":
        return "Manual check — %s" % landing.get("note", "human judgement required")
    return "Landing kind %r is not machine-checkable; needs a real condition." % kind


_DIGEST_REL = "WAI-Harness/spoke/local/resident/digest.json"


def _targets_from_landing(landing):
    """Derive file_targets from the landing condition where it names a path.

    Better than a placeholder: the landing condition usually points at the very
    file the work must change, so the target is real rather than invented.

    When the condition names no path (manual and command kinds), fall back to the
    digest — the thread record genuinely lives there, so the target is truthful
    rather than fabricated. lug_gate blocks on empty file_targets, and a
    materialiser that emits blocked lugs would wedge the next commit for everyone;
    inventing a plausible-looking source path to satisfy it would be worse, because
    a wrong target sends an autonomous run at the wrong file.
    """
    if isinstance(landing, dict):
        path = landing.get("path")
        if path:
            return [path]
    return [_DIGEST_REL]


def build_lug(thread, spoke_id="unknown"):
    landing = thread.get("landing") or {}
    text = (thread.get("text") or "").strip()
    targets = _targets_from_landing(landing)
    manual = landing.get("kind") == "manual"

    return {
        "id": lug_id_for(thread),
        "type": _LUG_TYPE,
        "title": text[:120] or "Open thread",
        "status": "open",
        "initiative": "thread-continuity",
        "created_at": _now_iso(),
        "created_by": "thread_materialize",
        "origin_spoke": spoke_id,
        "_thread_id": thread.get("id"),
        "_thread_session": thread.get("session"),
        "_thread_turn": thread.get("turn"),
        # PEV fields are LISTS, not strings: lug_gate normalises string -> [string]
        # anyway, and emitting the canonical shape keeps generated lugs from
        # tripping a gate they were built to satisfy.
        "perceive": [(
            "Open thread carried forward from %s turn %s: %s\n\n"
            "Materialised into a lug so the work survives losing the session. Before "
            "this existed the thread lived only in the resident digest, which is "
            "derived from conversation — the next session would have had to "
            "reconstruct intent from a transcript instead of picking up a backlog item."
            % (thread.get("session", "an earlier session"), thread.get("turn", "?"), text)
        )],
        "execute": [(
            "1. Read the thread statement above and confirm it is still the work worth "
            "doing — a thread can outlive its reason.\n"
            "2. Do the work.\n"
            "3. Satisfy the landing condition in `verify`; it is the same condition "
            "thread_landing.py checks, so meeting it clears the thread automatically.\n"
            "4. If the landing condition is wrong or unreachable, fix the CONDITION "
            "deliberately rather than closing the thread around it."
            + ("\n\nNOTE: file_targets points at the digest because this thread's "
               "landing condition names no file. Scope the real targets before "
               "dispatching this to an autonomous run."
               if targets == [_DIGEST_REL] else "")
        )],
        "verify": [_landing_prose(landing)],
        "acceptance_criteria": [
            _landing_prose(landing),
            "thread_landing.py check reports this thread as landed",
        ],
        "target_files": targets,
        "file_targets": targets,
        "model_fit": "sonnet" if not manual else "opus",
        "model_fit_reason": (
            "Manual landing condition implies operator judgement, so the model must be "
            "able to reason about intent rather than execute a mechanical check."
            if manual else
            "Landing condition is machine-checkable and scoped to named files, so a "
            "mid-tier model can execute and verify it without judgement calls."
        ),
        "_improvement_lenses": {
            "skeptic": (
                "Is this thread still real work, or an artefact of a conversation that "
                "moved on? A thread with no landing condition met and no recent mention "
                "may be stale rather than blocked."
            ),
            "architect": (
                "The landing condition is the contract. If it names no file, the work is "
                "under-scoped and the lug should be refined before dispatch rather than "
                "run against a guess."
            ),
            "naive_reader": (
                "Someone joining cold should be able to read `perceive` and know what was "
                "being attempted and why, without opening the session transcript."
            ),
        },
        # Stamp disposition at creation. A lug born without one is invisible to
        # BOTH work-split buckets and trips the readiness check's migrations-clean
        # gate — measured: materialising 17 threads took this spoke from
        # OPERATIONAL to NOT OPERATIONAL until a migration ran. A tool that creates
        # lugs owns their disposition; leaving it for a later pass means every
        # materialisation run breaks readiness in the window between.
        "disposition": "auto_build" if targets and targets != [_DIGEST_REL] and not manual else "needs_you",
        "disposition_reason": (
            "thread landing condition names a concrete file target and is machine-checkable"
            if targets and targets != [_DIGEST_REL] and not manual
            else "thread landing condition names no file target -- needs human scoping before dispatch"
        ),
        "disposition_at": _now_iso(),
        "tags": ["thread-continuity", "materialised", "session-resume"],
        "execution_mode": "manual" if manual else "auto",
    }


def materialize(root=".", dry_run=False):
    digest_path = _digest_path(root)
    digest = _read_json(digest_path)
    if digest is None:
        # Same key set as the success return below. These two returns drifted:
        # this one omitted `already`/`dry_run`/`details`, and main()'s non-JSON
        # print reads report["already"] unconditionally — so the no-digest path
        # died with `KeyError: 'already'` instead of printing the actionable
        # message it had ready. The traceback fired exactly where the operator
        # most needed the message: on a spoke whose digest was never bootstrapped.
        return {"ok": False,
                "errors": ["no resident digest at %s — run: "
                           "python3 resident_digest.py bootstrap" % digest_path],
                "created": 0, "already": 0, "linked": 0,
                "details": [], "ts": _now_iso(), "dry_run": bool(dry_run)}

    threads = digest.get("open_threads") or digest.get("threads") or []
    spoke_id = os.path.basename(os.path.abspath(root))

    report = {"ok": True, "created": 0, "already": 0, "linked": 0,
              "errors": [], "details": [], "ts": _now_iso(), "dry_run": bool(dry_run)}

    changed_digest = False
    for thread in threads:
        if not isinstance(thread, dict) or not thread.get("text"):
            continue
        lug_id = lug_id_for(thread)
        existing = _existing_lug_path(root, lug_id)

        if existing:
            report["already"] += 1
        else:
            report["created"] += 1
            report["details"].append({"thread": thread.get("id"), "lug": lug_id})
            if not dry_run:
                target_dir = _lug_dir(root, "open")
                os.makedirs(target_dir, exist_ok=True)
                try:
                    with open(os.path.join(target_dir, lug_id + ".json"), "w",
                              encoding="utf-8") as fh:
                        json.dump(build_lug(thread, spoke_id), fh, indent=2)
                        fh.write("\n")
                except OSError as exc:
                    report["errors"].append("write %s: %s" % (lug_id, exc))

        # Back-reference on the thread, so the digest points AT the durable record
        # rather than being the record.
        if thread.get("lug_id") != lug_id:
            thread["lug_id"] = lug_id
            changed_digest = True
            report["linked"] += 1

    if changed_digest and not dry_run:
        try:
            with open(digest_path, "w", encoding="utf-8") as fh:
                json.dump(digest, fh, indent=2)
                fh.write("\n")
        except OSError as exc:
            report["errors"].append("digest write: %s" % exc)

    report["ok"] = not report["errors"]
    return report


def verify_all_threads_have_lugs(root="."):
    """Post-check: is every open thread backed by a lug on disk?

    FAILS CLOSED when the digest is absent. "No digest" means the thread corpus
    is UNKNOWN, not empty, and those two must never share an exit code — the
    savepoint ceremony treats a CLEAN here as a hard precondition for ejecting.

    Measured on sound-sails-website (2026-07-25): the digest had never been
    bootstrapped, so this returned clean=True over zero threads and the eject
    gate passed by knowing nothing. Bootstrapping the digest then surfaced 9
    genuinely open threads, one of them a month-old unanswered question. The
    gate would have certified a spoke that was losing every thread it had.
    """
    digest = _read_json(_digest_path(root))
    if digest is None:
        return {"clean": False, "status": "unknown", "threads": None, "orphans": [],
                "reason": "no resident digest at %s — thread corpus is UNKNOWN, not "
                          "empty. Run: python3 resident_digest.py bootstrap"
                          % _digest_path(root)}
    threads = digest.get("open_threads") or digest.get("threads") or []
    orphans = [t.get("id") for t in threads
               if isinstance(t, dict) and t.get("text")
               and not _existing_lug_path(root, lug_id_for(t))]
    return {"clean": not orphans, "threads": len(threads), "orphans": orphans,
            "ts": _now_iso()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    if args.verify:
        result = verify_all_threads_have_lugs(args.root)
        if args.json:
            print(json.dumps(result, indent=2))
        elif result.get("status") == "unknown":
            # Distinct from both CLEAN and ORPHAN: we did not fail to find a lug,
            # we failed to find the corpus. Saying "ORPHAN THREADS: " with an empty
            # list here would be as misleading as the CLEAN this replaced.
            print("UNKNOWN — %s" % result.get("reason", "thread corpus unreadable"))
        elif result["clean"]:
            print("CLEAN — every open thread has a lug")
        else:
            print("ORPHAN THREADS (no lug): %s" % ", ".join(result["orphans"]))
        return 0 if result["clean"] else 1

    report = materialize(args.root, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("threads materialised: %d created, %d already had lugs, %d linked%s"
              % (report["created"], report["already"], report["linked"],
                 " (dry-run)" if report["dry_run"] else ""))
        for err in report["errors"][:5]:
            print("  ERROR: %s" % err)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
