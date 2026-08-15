#!/usr/bin/env python3
"""savepoint_claim.py — claim a pending savepoint, atomically, and prove it was claimed.

WHY THIS TOOL EXISTS (measured failure, session 140, 2026-08-06):
A savepoint sat at `_savepoint.status == "pending"` through an entire wakeup. The briefing
DISPLAYED it and even recommended continuing it — and then left the status untouched. The
operator had to ask "did you pick it up or not?", which is the question this tool exists to
make unaskable. Surfacing a savepoint is not claiming it, and until this tool there was no
mechanical difference between the two: both left identical bytes on disk.

The failure path was in the ceremony, not the launcher. `wai-enter.sh` legitimately writes
`intent: "raw"` when the operator declines the opening prompt (choice `r`). The wai.md intent
router had no `raw` row, and step 2c (the savepoint intercept) was gated on
"only when SESSION_INTENT is absent". So a PRESENT-but-unrouted intent suppressed the
intercept: the one code path that would have claimed the savepoint was skipped precisely
because an intent existed. The hole opened only for intent values the table did not list,
which is why it survived so long.

THREE SUBCOMMANDS, one job each:
  status         — report whether a savepoint is pending. Read-only. Always exit 0.
  claim          — pending -> resumed, in one atomic write. Idempotent. Exit 0.
  assert-claimed — exit 1 if a savepoint is STILL pending. This is the oracle: it is what
                   makes "the ceremony forgot" a detectable event rather than a silent one.

WHAT `claim` WRITES (all-or-nothing; a crash mid-claim leaves the ORIGINAL file):
  WAI-State.json
    _savepoint.status              -> "resumed"
    _savepoint.resumed_at          -> UTC ISO-8601
    _savepoint.resumed_by_session  -> the claiming session id
    _session_state.active_initiative_id -> the savepoint's initiative_id (when it has one)
    _session_state.focus_directive      -> the savepoint's focus_directive (when it has one)
  the canonical savepoint file (when `canonical_path` resolves)
    status -> "resumed"

The two are kept in agreement deliberately. They drifted before: state said one thing, the
savepoint file another, and neither could be trusted to settle it.

Usage:
    python3 savepoint_claim.py --base <spoke_local_base> status [--json]
    python3 savepoint_claim.py --base <spoke_local_base> claim [--session-id ID] [--json]
    python3 savepoint_claim.py --base <spoke_local_base> assert-claimed
Exit: 0 ok | 1 assert-claimed found a pending savepoint | 2 error
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import tempfile

# Statuses that mean "somebody already dealt with this savepoint". Anything NOT in this set
# and not empty is treated as pending, so a novel status fails loud instead of silently
# counting as handled — the exact failure mode this tool was built to end.
HANDLED = {"resumed", "completed", "cleared", "abandoned", "discarded"}


def _state_path(base: str) -> str:
    return os.path.join(base, "WAI-State.json")


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json_atomic(path: str, data: dict) -> None:
    """Write via a same-directory temp file + os.replace.

    Same directory matters: os.replace is only atomic within a filesystem, and /tmp is
    routinely a different one. A torn WAI-State.json costs the whole session's continuity,
    which is more than this tool is trying to save.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".savepoint_claim.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _resolve_savepoint_file(base: str, savepoint: dict) -> str:
    """Resolve the canonical savepoint file, or '' when there isn't a readable one.

    `canonical_path` is recorded relative to the spoke local base. It is absent on older
    savepoints, so absence is normal and never an error.
    """
    rel = savepoint.get("canonical_path") or ""
    if not rel:
        return ""
    candidate = rel if os.path.isabs(rel) else os.path.join(base, rel)
    return candidate if os.path.isfile(candidate) else ""


def read_status(base: str) -> dict:
    """Report the savepoint situation. Never writes, never raises on a missing state file."""
    path = _state_path(base)
    if not os.path.isfile(path):
        return {"ok": False, "pending": False, "reason": f"no WAI-State.json at {path}"}
    try:
        state = _read_json(path)
    except Exception as exc:
        return {"ok": False, "pending": False, "reason": f"unreadable WAI-State.json: {exc}"}

    savepoint = state.get("_savepoint") or {}
    status = (savepoint.get("status") or "").strip()
    # An empty _savepoint is the normal "nothing to resume" state, not a pending one.
    pending = bool(savepoint) and status not in HANDLED

    return {
        "ok": True,
        "pending": pending,
        "status": status or None,
        "lug_id": savepoint.get("lug_id"),
        "savepoint_id": savepoint.get("savepoint_id"),
        "initiative_id": savepoint.get("initiative_id"),
        "resume_note": savepoint.get("resume_note"),
        "focus_directive": savepoint.get("focus_directive"),
        "savepoint_file": _resolve_savepoint_file(base, savepoint),
    }


def claim(base: str, session_id: str) -> dict:
    """Claim a pending savepoint. Idempotent: an already-claimed savepoint is a no-op."""
    info = read_status(base)
    if not info["ok"]:
        return {**info, "claimed": False}
    if not info["pending"]:
        return {**info, "claimed": False, "reason": "nothing pending"}

    path = _state_path(base)
    state = _read_json(path)
    savepoint = state.get("_savepoint") or {}

    savepoint["status"] = "resumed"
    savepoint["resumed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    savepoint["resumed_by_session"] = session_id
    state["_savepoint"] = savepoint

    session_state = state.setdefault("_session_state", {})
    # Only overwrite when the savepoint actually carries the field. A savepoint with no
    # initiative must not blank an initiative the session already chose.
    if savepoint.get("initiative_id"):
        session_state["active_initiative_id"] = savepoint["initiative_id"]
    if savepoint.get("focus_directive"):
        session_state["focus_directive"] = savepoint["focus_directive"]

    _write_json_atomic(path, state)

    # Stamp the canonical file second. If this half fails, WAI-State.json is already
    # authoritative and the next `status` read still reports resumed — the safe direction.
    sp_file = info.get("savepoint_file") or ""
    file_stamped = False
    if sp_file:
        try:
            doc = _read_json(sp_file)
            doc["status"] = "resumed"
            _write_json_atomic(sp_file, doc)
            file_stamped = True
        except Exception:
            file_stamped = False

    result = read_status(base)
    result.update({
        "claimed": True,
        "resumed_by_session": session_id,
        "savepoint_file_stamped": file_stamped,
    })
    return result


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
        return
    if not payload.get("ok"):
        print(f"savepoint: ERROR — {payload.get('reason')}")
        return
    if not payload.get("pending") and not payload.get("claimed"):
        print("savepoint: none pending")
        return
    verb = "CLAIMED" if payload.get("claimed") else "PENDING"
    print(f"savepoint: {verb} {payload.get('savepoint_id') or payload.get('lug_id')}")
    if payload.get("lug_id"):
        print(f"  lug:        {payload['lug_id']}")
    if payload.get("initiative_id"):
        print(f"  initiative: {payload['initiative_id']}")
    if payload.get("focus_directive"):
        print(f"  focus:      {payload['focus_directive']}")
    if payload.get("resume_note"):
        print(f"  next:       {payload['resume_note'][:300]}")


def main(argv: list) -> int:
    # --json lives on a shared parent so it is accepted on EITHER side of the subcommand.
    # argparse otherwise rejects `... status --json`, which is the order every caller reaches
    # for first — a usage error there would read as "the tool is broken", not "wrong order".
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="emit JSON instead of prose")

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0], parents=[common])
    parser.add_argument("--base", required=True, help="spoke local base (the {BASE} the ceremony resolves)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", parents=[common], help="report whether a savepoint is pending (read-only)")
    p_claim = sub.add_parser("claim", parents=[common], help="claim a pending savepoint (idempotent)")
    p_claim.add_argument("--session-id", default=os.environ.get("WAI_SESSION_ID", "unknown"))
    sub.add_parser("assert-claimed", parents=[common], help="exit 1 if a savepoint is still pending")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "status":
            _emit(read_status(args.base), args.json)
            return 0
        if args.cmd == "claim":
            _emit(claim(args.base, args.session_id), args.json)
            return 0
        if args.cmd == "assert-claimed":
            info = read_status(args.base)
            if not info["ok"]:
                print(f"savepoint assert: ERROR — {info.get('reason')}", file=sys.stderr)
                return 2
            if info["pending"]:
                print(
                    "savepoint assert: FAIL — still pending: "
                    f"{info.get('savepoint_id') or info.get('lug_id')} "
                    "(wakeup surfaced it but never claimed it)",
                    file=sys.stderr,
                )
                return 1
            print("savepoint assert: OK — nothing left pending")
            return 0
    except Exception as exc:  # noqa: BLE001 — a tool crash must not be mistaken for a clean run
        print(f"savepoint_claim: ERROR — {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
