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
    return rec.get("event") == "closeout" or rec.get("completed") is True


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
        if _is_closed(last):
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
