#!/usr/bin/env python3
"""Scan a spoke's resume surfaces (savepoints + interrupted sessions) and emit
shell-eval lines for the wai-enter wakeup menu.

Why a standalone tool: the menu rendering lives in wai-enter.sh (interactive bash,
hard to test). The DATA — clean one-line titles, the initiative `silo_label`, and
recommended actions for interrupted sessions — is pure transformation, so it lives
here where it can be unit-tested (tests/test_wai_enter_resume_scan.py).

Contract (per spec-savepoint-resume-contract-v1, harness master):
  - savepoints carry `initiative_id` + `silo_label`; `silo_label` is the human
    initiative name shown in the resume menu (blank for legacy v2 savepoints).
  - a savepoint is a resume CONTRACT — the menu enumerates each one by IDENTITY
    (slug + a short note), NOT by dumping its work_done contents.

Two savepoint sources are unified here (the spoke fleet uses both during v3/v4
coexistence):
  - v4 on-disk store: initiatives/savepoints/<initiative_id>/sp-*.json — the file
    IS the savepoint (symlinks back to the authoritative file). This REPLACES the
    old flat savepoints/ scan.
  - legacy: a single `._savepoint` object embedded in WAI-State.json.
Each row carries `_SP_EMBEDDED[i]` so the resume prompt reads the right shape:
'1' = claim the `._savepoint` object inside that WAI-State.json; '' = the file
IS the savepoint.

Usage:  wai_enter_resume_scan.py --wai-local <dir> [--state <WAI-State.json> ...]
Emits (stdout, safe for `eval`):
  _SP_COUNT=N
  _SP_IDS[i]='…'  _SP_TITLES[i]='…'  _SP_SILOS[i]='…'  _SP_NOTES[i]='…'
  _SP_FILES[i]='…'  _SP_EMBEDDED[i]='1'|''
  _SP_STATUS='…'  _SP_LUG='…'  _SP_NOTE='…'                 # [0] convenience for single-resume
  _INT_COUNT=N
  _INT_IDS[i]='…'  _INT_TITLES[i]='…'  _INT_ACTIONS[i]='…'  _INT_FILES[i]='…'
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

STALE_ACTIVE_HOURS = 8        # an 'active' savepoint older than this reads as resumable
INTERRUPTED_MAX_AGE_DAYS = 7  # older interrupted sessions have no actionable context (anti-pattern)
TITLE_CAP = 64
NOTE_CAP = 52


def _shq(s):
    """Single-quote a value for safe shell eval."""
    return "'" + str(s).replace("'", "'\\''") + "'"


def _one_line(s, cap):
    s = " ".join(str(s or "").split())
    return (s[: cap - 1].rstrip() + "…") if len(s) > cap else s


def _first_sentence(s):
    s = " ".join(str(s or "").split())
    for sep in (". ", "! ", "? "):
        if sep in s:
            return s.split(sep)[0]
    return s


def _savepoint_title(d):
    """A concise IDENTITY line for the savepoint — slug-first, never the raw
    work_done dump. Falls back through the fields real savepoints actually carry
    (v2 string `work_done` and v4 `where_we_are`/`first_actions` both handled)."""
    slug = d.get("slug") or ""
    if slug:
        return _one_line(slug, TITLE_CAP)
    wwa = d.get("where_we_are")
    if wwa:
        return _one_line(_first_sentence(wwa), TITLE_CAP)
    fa = d.get("first_actions")
    if isinstance(fa, list) and fa and isinstance(fa[0], dict) and fa[0].get("action"):
        return _one_line(fa[0]["action"], TITLE_CAP)
    wd = d.get("work_done")
    if isinstance(wd, list) and wd and isinstance(wd[0], dict) and wd[0].get("what"):
        return _one_line(wd[0]["what"], TITLE_CAP)
    if isinstance(wd, str) and wd:
        return _one_line(_first_sentence(wd), TITLE_CAP)
    return _one_line(d.get("id") or "savepoint", TITLE_CAP)


def _savepoint_note(d):
    """A short descriptor shown after the title — the resume intent, not contents."""
    note = d.get("resume_note") or d.get("user_next_step") or ""
    return _one_line(note, NOTE_CAP)


def _resolve_status(d):
    """pending/active for display; a stale-active (claimed >8h ago) reads as
    resumable -> pending. Returns '' for any non-resumable status."""
    status = d.get("status", "")
    if status == "active":
        claimed = d.get("claimed_at", "")
        if claimed:
            try:
                cdt = datetime.fromisoformat(claimed.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - cdt > timedelta(hours=STALE_ACTIVE_HOURS):
                    return "pending"
            except Exception:
                return "pending"
    return status if status in ("pending", "active") else ""


def _row(d, file, embedded):
    return {
        "id": d.get("id") or d.get("lug_id") or d.get("session_id") or Path(file).stem,
        "status": _resolve_status(d),
        "title": _savepoint_title(d),
        "silo": _one_line(d.get("silo_label") or "", 24),   # initiative context (blank = legacy)
        "note": _savepoint_note(d),
        "file": str(file),
        "embedded": "1" if embedded else "",
        # which initiative owns this savepoint (the v4 store sets this from the
        # parent dir name; embedded/legacy rows fall back to the JSON field).
        "initiative_id": d.get("initiative_id") or "",
    }


def _safe_mtime(p):
    try:
        return p.stat().st_mtime   # follows symlinks; the v4 store is symlinks
    except OSError:
        return 0.0                 # dangling symlink — keep, sort last, don't abort


def _scan_dir(directory):
    """Scan one directory of standalone savepoint *.json files (the file IS the
    savepoint). Symlinks are followed — the v4 initiative store holds symlinks
    back to the authoritative file. Newest-first; non-resumable rows skipped."""
    d = Path(directory)
    out = []
    if not d.exists():
        return out
    for f in sorted(d.glob("*.json"), key=_safe_mtime, reverse=True):
        if f.name == ".gitkeep":
            continue
        try:
            data = json.loads(f.read_text())
        except Exception:
            continue
        if not _resolve_status(data):
            continue
        out.append(_row(data, f, embedded=False))
    return out


def scan_initiative_savepoints(wai_local):
    """v4 savepoint source: savepoints owned by an initiative live under
    initiatives/savepoints/<initiative_id>/sp-*.json (symlinks back to the
    authoritative file, written by initiative_nav.py). This REPLACES the legacy
    flat savepoints/ scan as the on-disk savepoint source for the resume menu."""
    base = Path(wai_local) / "initiatives" / "savepoints"
    if not base.is_dir():
        return []
    out = []
    for iid_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        for row in _scan_dir(iid_dir):
            row["initiative_id"] = iid_dir.name   # dir name is authoritative ownership
            out.append(row)
    return out


def scan_embedded(state_files):
    """The single `._savepoint` object inside one or more WAI-State.json candidates
    (v3/v4). The savepoint lives nested under ._savepoint; resume claims it there."""
    out = []
    seen_real = set()
    for sf in state_files:
        rp = os.path.realpath(sf)
        if rp in seen_real:
            continue
        seen_real.add(rp)
        try:
            sp = (json.load(open(sf)) or {}).get("_savepoint") or {}
        except Exception:
            continue
        if not sp or not _resolve_status(sp):
            continue
        out.append(_row(sp, sf, embedded=True))
    return out


def scan_all_savepoints(wai_local, state_files=()):
    """Unified savepoint list, deduped by id, from the two live sources:
      - v4 on-disk store: initiatives/savepoints/<iid>/*.json (scan_initiative_savepoints)
      - legacy embedded ._savepoint object inside WAI-State.json (scan_embedded)
    The flat savepoints/ dir is no longer scanned — the v4 initiative store replaces it."""
    rows = scan_initiative_savepoints(wai_local) + scan_embedded(state_files)
    seen, uniq = set(), []
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        uniq.append(r)
    return uniq


# states a live initiative can be in (terminal states are not surfaced at wakeup)
LIVE_INITIATIVE_STATES = ("active", "measuring", "approved", "proposed", "dormant")
_STATE_RANK = {s: i for i, s in enumerate(LIVE_INITIATIVE_STATES)}


def scan_initiatives(wai_local):
    """Live initiatives for the wakeup menu, focus-pinned first. Read from the
    per-file store initiatives/bytype/initiative/<state>/*.json, with the focus
    pin from initiatives/current.json (._initiative_id). Terminal states
    (complete/abandoned) are excluded. Each row: id, label, state, focus."""
    base = Path(wai_local) / "initiatives"
    focus = ""
    cur = base / "current.json"
    if cur.exists():
        try:
            focus = (json.loads(cur.read_text()) or {}).get("initiative_id") or ""
        except Exception:
            focus = ""
    out = []
    bty = base / "bytype" / "initiative"
    if bty.is_dir():
        for state_dir in bty.iterdir():
            if not state_dir.is_dir() or state_dir.name not in _STATE_RANK:
                continue
            for f in sorted(state_dir.glob("*.json")):
                if f.name == ".gitkeep":
                    continue
                try:
                    d = json.loads(f.read_text())
                except Exception:
                    continue
                iid = d.get("id") or f.stem
                label = d.get("label") or d.get("silo_label") or d.get("title") or iid
                out.append({
                    "id": iid,
                    "label": _one_line(label, 32),
                    "state": d.get("lifecycle_state") or state_dir.name,
                    "focus": "1" if iid and iid == focus else "",
                })
    # focus pin first, then by lifecycle priority, then id — stable for the menu.
    out.sort(key=lambda r: (r["focus"] != "1",
                            _STATE_RANK.get(r["state"], len(_STATE_RANK)),
                            r["id"]))
    return out


def _track_last_record(track_path):
    last = None
    try:
        with open(track_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line)
                except Exception:
                    continue
    except Exception:
        return None
    return last


def _is_closed(rec):
    if not isinstance(rec, dict):
        return False
    # Closeout entries use event+summary schema (no `completed` field); resumable
    # turns may set completed=true. Either marks the session as cleanly ended.
    #
    # A SAVEPOINT ALSO ENDS A SESSION. Canon (taste work-style-savepoint-must-stand-
    # alone): "The operator OFTEN leaves a session having done only a savepoint and no
    # closeout. A savepoint must therefore leave the wheel fully durable on its own."
    # This function did not honour that, so a savepoint-closed session stayed
    # "interrupted" forever. Measured on basher 2026-08-01: 10 of the 11 sessions on
    # the interrupted list had a savepoint. The list was not detecting interruption —
    # it was detecting that the operator does not run /wai-closeout, which canon says
    # he does not have to.
    #
    # An `exit` record (written by wai-exit) is only terminal when it says the
    # session was actually made durable. wai-exit stamps durable=false when the
    # session left neither a closeout nor a deliberate savepoint — that session
    # must keep surfacing. Quieting the list by accepting every exit would trade a
    # noisy signal for a lying one, which is the failure this whole change is about.
    if rec.get("event") == "exit":
        return rec.get("durable") is True
    return (rec.get("event") in ("closeout", "savepoint_created", "savepoint_updated")
            or rec.get("completed") is True)


def _track_has_closeout(track_path):
    """True if ANY record in the track marks the session closed.

    Deliberately scans the whole file rather than the tail: the caller only ever sees
    the LAST record, and a trailing turn written after the closeout hides it. Reuses
    _is_closed per record so "what counts as closed" has exactly one definition.
    (Ported from the basher fork 2026-08-14 — see epic-launcher-reconciliation-v1.
    Three copies of this scanner had diverged; this rule and _is_operator_session
    below existed only in the forks, and their absence here made the two copies
    disagree by 47 sessions on the same tree.)"""
    try:
        with open(track_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if _is_closed(rec):
                    return True
    except Exception:
        pass
    return False


# Agent-session tells in a track's first real user message. MIRRORED from
# scripts/claude-resume-picker.sh (_scan) and bin/claude-resume — that picker is the
# canonical list. An autonomous run (Ozi/autopilot, Herald responder, chain worker) is a
# single-shot `claude -p`, never an operator chat worth offering to resume.
_AGENT_MARKERS = re.compile(
    r"^\[HERALD RESPONDER"
    r"|^HERALD RESPONDER"
    r"|^\[(OZI|AUTOPILOT|AUTONOMOUS|CHAIN)\b"
    r"|single-shot\.?\s+Do NOT run full wakeup"
    r"|Do NOT run full wakeup; do NOT claim chains"
    r"|SCHEDULED Autopilot"
    r"|servicing this spoke.?s backlog"
    r"|Autopilot \(Ozi\)"
    r"|^reply with exactly:",
    re.IGNORECASE)


def _is_operator_session(track):
    """True iff this track could be an operator's session worth resuming.

    Operator, s117 2026-07-24: "Interrupted sessions shown only if it was a user
    session." The interrupted list is a RESUME OFFER, so a machine run does not belong
    in it — there is no operator intent to pick up. Deliberately narrow:
      * first real user_msg is agent-marked -> EXCLUDE (single-shot `claude -p` worker)
      * otherwise -> INCLUDE
    Everything ambiguous or unreadable fails OPEN: over-offering one session is
    recoverable, silently hiding the operator's interrupted work is not. (The
    no-records case is already handled upstream by _turn_count.)"""
    try:
        with track.open(encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                try:
                    rec = json.loads(ln)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                msg = rec.get("user_msg")
                if not msg or not str(msg).strip():
                    continue
                return not _AGENT_MARKERS.search(" ".join(str(msg).split()))
    except OSError:
        return True          # unreadable -> do not hide it
    return True              # no user_msg anywhere -> not proof of a machine run


def _turn_count(track_path):
    """Real turns on this track — `turn` events only, not session_start/autoeject."""
    n = 0
    try:
        with open(track_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict) and (rec.get("event") == "turn" or rec.get("turn")):
                    n += 1
    except Exception:
        return 0
    return n


def _has_savepoint(wai_local, session_id):
    """Did this session leave a savepoint? An AUTO-EJECT does not count.

    An auto-eject is the harness catching a session that ran out of room — it is a
    crash cushion, not a deliberate close, so a session whose only savepoint is an
    auto-eject IS genuinely interrupted and must stay on the list.
    """
    sp_root = Path(wai_local) / "initiatives" / "savepoints"
    if not sp_root.exists():
        return False
    for f in sp_root.glob("*/*.json"):
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                d = json.load(fh)
        except Exception:
            continue
        if not isinstance(d, dict) or d.get("session_id") != session_id:
            continue
        if d.get("status") == "auto-eject" or "autoeject" in f.name:
            continue
        return True
    return False


def scan_interrupted(wai_local, now=None):
    """Interrupted sessions = a session whose track.jsonl does not end in a
    closeout/completed record AND is <= 7 days old (older = no actionable context,
    skip silently per the anti-pattern rule). Presented like savepoints so the
    user can OPEN one and take the recommended action, not just see a count."""
    now = now if now is not None else time.time()
    sess_dir = Path(wai_local) / "sessions"
    out = []
    if not sess_dir.exists():
        return out
    cutoff = now - INTERRUPTED_MAX_AGE_DAYS * 86400
    dirs = [d for d in sess_dir.glob("session-*") if d.is_dir()]
    for d in sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True):
        track = d / "track.jsonl"
        if not track.exists():
            continue
        if track.stat().st_mtime < cutoff:
            continue
        last = _track_last_record(track)
        # Whole-file scan, not just the tail: a turn appended after the closeout
        # would otherwise hide it and keep the session "interrupted" forever.
        if _is_closed(last) or _track_has_closeout(track):
            continue
        # A machine run (Ozi/autopilot, Herald, chain worker) is not resumable work.
        if not _is_operator_session(track):
            continue
        # A session with NO TURNS was never interrupted — nothing happened in it.
        # These are launcher spawns: basher measured four on 2026-07-29 inside a
        # 12-minute window, each one line of session_start and nothing else. They
        # carry no actionable context at all, which is the same reason the >7d rule
        # already skips old ones (the "stale interrupted sessions" anti-pattern).
        # Surfacing them costs wakeup attention and produces retroactive closeouts
        # on empty shells.
        if _turn_count(track) == 0:
            continue
        # A session closed by SAVEPOINT is durably closed even if its last track
        # record is an ordinary turn — the savepoint, not the track, is the contract.
        # Checked on disk rather than trusting the track's tail, because the Stop
        # hook can append a turn AFTER the savepoint is written.
        if _has_savepoint(wai_local, d.name):
            continue
        # Title: the last meaningful summary/note from the track, else the id.
        title = ""
        if isinstance(last, dict):
            title = last.get("summary") or last.get("note") or last.get("title") or ""
        out.append({
            "id": d.name,
            "title": _one_line(title or d.name, TITLE_CAP),
            "action": "resume & closeout",   # recommended action when opened
            "file": str(track),
        })
    return out


def emit(savepoints, interrupted, initiatives=()):
    lines = []
    lines.append(f"_SP_COUNT={len(savepoints)}")
    for i, sp in enumerate(savepoints):
        lines.append(f"_SP_IDS[{i}]={_shq(sp['id'])}")
        lines.append(f"_SP_TITLES[{i}]={_shq(sp['title'])}")
        lines.append(f"_SP_SILOS[{i}]={_shq(sp['silo'])}")
        lines.append(f"_SP_NOTES[{i}]={_shq(sp['note'])}")
        lines.append(f"_SP_FILES[{i}]={_shq(sp['file'])}")
        lines.append(f"_SP_EMBEDDED[{i}]={_shq(sp['embedded'])}")
        lines.append(f"_SP_INITS[{i}]={_shq(sp.get('initiative_id', ''))}")
    if savepoints:
        lines.append(f"_SP_STATUS={_shq(savepoints[0]['status'])}")
        lines.append(f"_SP_LUG={_shq(savepoints[0]['id'])}")
        lines.append(f"_SP_NOTE={_shq(savepoints[0]['note'])}")
    else:
        lines.append("_SP_STATUS=''")
        lines.append("_SP_LUG=''")
        lines.append("_SP_NOTE=''")

    # ── Initiatives + their child-savepoint membership ───────────────────────
    # The menu renders a flat tree: each initiative (digit-selectable) followed by
    # its child savepoints (the indices in _INIT_SP_IDX point into the _SP_* arrays
    # above). Savepoints owned by no live initiative go in _SP_UNGROUPED_IDX.
    init_ids = [it["id"] for it in initiatives]
    grouped = set()
    lines.append(f"_INIT_COUNT={len(initiatives)}")
    for j, it in enumerate(initiatives):
        members = [str(i) for i, sp in enumerate(savepoints)
                   if sp.get("initiative_id") == it["id"]]
        grouped.update(int(m) for m in members)
        lines.append(f"_INIT_IDS[{j}]={_shq(it['id'])}")
        lines.append(f"_INIT_LABELS[{j}]={_shq(it['label'])}")
        lines.append(f"_INIT_STATES[{j}]={_shq(it['state'])}")
        lines.append(f"_INIT_FOCUS[{j}]={_shq(it['focus'])}")
        lines.append(f"_INIT_SP_IDX[{j}]={_shq(' '.join(members))}")
    ungrouped = [str(i) for i in range(len(savepoints)) if i not in grouped]
    lines.append(f"_SP_UNGROUPED_IDX={_shq(' '.join(ungrouped))}")

    lines.append(f"_INT_COUNT={len(interrupted)}")
    for i, it in enumerate(interrupted):
        lines.append(f"_INT_IDS[{i}]={_shq(it['id'])}")
        lines.append(f"_INT_TITLES[{i}]={_shq(it['title'])}")
        lines.append(f"_INT_ACTIONS[{i}]={_shq(it['action'])}")
        lines.append(f"_INT_FILES[{i}]={_shq(it['file'])}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wai-local", required=True)
    ap.add_argument("--state", action="append", default=[],
                    help="WAI-State.json candidate(s) to scan for an embedded ._savepoint")
    args = ap.parse_args()
    savepoints = scan_all_savepoints(args.wai_local, args.state)
    interrupted = scan_interrupted(args.wai_local)
    initiatives = scan_initiatives(args.wai_local)
    sys.stdout.write(emit(savepoints, interrupted, initiatives) + "\n")


if __name__ == "__main__":
    main()
