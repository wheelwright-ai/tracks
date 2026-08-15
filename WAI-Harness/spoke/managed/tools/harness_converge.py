#!/usr/bin/env python3
"""harness_converge.py — P7 master-side cross-spoke convergence (CSRP).

Master (mywheel) is the canonical convergence lead. Spokes accumulate managed/
edits as LOCAL proposals. This tool reconciles those proposals into the master
managed tree, re-cuts the MANIFEST, and bumps the version — giving spokes a
clean path back via harness_upgrade pull.

Symmetry with P6: P6 converges lanes within a spoke; P7 converges spokes back
into the master. Same guarantee: no effort lost, conflicts return as notice lugs
(never silent overwrite), master tree is never corrupted.

Path conventions (consistent with harness_upgrade.py):
  master_harness = WAI-Harness dir of the master (e.g. /mywheel/WAI-Harness)
  spoke_root     = repo root of a contributing spoke (e.g. /basher)
  master_managed = master_harness / spoke / managed
  spoke_managed  = spoke_root / WAI-Harness / spoke / managed

Commands:
  list-contributions  [--spoke-roots R ...] [--master M]
      Diff each spoke's managed/ vs master. Reports: additions, conflicts, same.

  reconcile  --spoke-root R [--master M] [--dry-run] [--base-sha SHA]
      Adopt additions, 3-way merge conflicts, emit notice lug on unresolvable
      conflict, re-cut MANIFEST, bump minor version.

  contribute  --master M [--spoke-root R] [--base-sha SHA]
      Spoke-side: record base sha + deliver contribution lug to master incoming.

  absorb-contributions  [--master M]
      Master reads all pending harness-contribution lugs from its incoming/,
      reconciles each, marks lugs processed.

  classify-live  --spoke-root R [--master M]
      READ-ONLY. Classifies every file in managed/.claude/** vs the spoke's own
      live .claude/** as IDENTICAL / BEHIND / AHEAD / CONFLICT / DECLARED_OVERRIDE.
      See converge_preflight.py for the operator-facing "what would converge
      take from me?" wrapper.

  absorb-live  --spoke-root R [--master M] [--dry-run]
      The actual managed(.claude) -> live(.claude) redeploy. IDENTICAL/BEHIND
      absorb cleanly; DECLARED_OVERRIDE is skipped and recorded; AHEAD/CONFLICT
      HALT that file, preserve its current content to a refs/recovery/ git ref,
      and never overwrite it silently. Always emits a converge receipt under
      hub/local/maintenance/receipts/.

  pull-exposure  --spoke-root R [--master M]
      READ-ONLY. The OTHER exposure direction (bug-converge-silently-reverts-
      locally-authored-behavior-v1): what would `harness_upgrade pull` take
      from THIS spoke's own managed/ tree, i.e. which files diverge from
      master's canon undeclared and would be silently overwritten today.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import harness_upgrade as hu  # noqa: E402 — resolves after sys.path insert

CONTRIBUTION_LUG_PREFIX = "harness-contribution-"
BASE_SHA_FILE = "spoke/local/runtime/harness-base.json"


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _iter_managed_files(root):
    root = Path(root)
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != hu.MANIFEST_NAME:
            rel = p.relative_to(root).as_posix()
            if not hu._excluded(rel):
                yield rel


def _md5file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _diff_trees(master_managed, spoke_managed):
    """Compare two managed/ trees. Returns:
      same      — identical content in both
      additions — only in spoke (spoke contributes to master)
      conflicts — in both but different content
      orphans   — only in master (spoke will receive on pull; not actionable here)
    """
    mw = {r: _md5file(Path(master_managed) / r) for r in _iter_managed_files(master_managed)}
    sp = {r: _md5file(Path(spoke_managed) / r) for r in _iter_managed_files(spoke_managed)}

    same, additions, conflicts, orphans = [], [], [], []
    for r, h in sp.items():
        if r not in mw:
            additions.append(r)
        elif mw[r] == h:
            same.append(r)
        else:
            conflicts.append(r)
    for r in mw:
        if r not in sp:
            orphans.append(r)
    return {
        "same": sorted(same),
        "additions": sorted(additions),
        "conflicts": sorted(conflicts),
        "orphans": sorted(orphans),
    }


def _resolve_master_harness(master=None):
    """Resolve to the WAI-Harness dir of the master (matches harness_upgrade DEFAULT_MASTER)."""
    if master:
        return str(Path(master).resolve())
    env = os.environ.get("WAI_HARNESS_MASTER")
    if env:
        return env
    return hu.DEFAULT_MASTER


def _master_managed(master_harness):
    return str(Path(master_harness) / "spoke" / "managed")


def _master_local(master_harness):
    return str(Path(master_harness) / "spoke" / "local")


def _spoke_managed(spoke_root):
    return str(Path(spoke_root) / "WAI-Harness" / "spoke" / "managed")


def _bump_minor(version):
    """Bump minor, reset patch: 4.3.4 → 4.4.0."""
    parts = str(version).split(".")
    if len(parts) >= 3:
        try:
            return f"{parts[0]}.{int(parts[1])+1}.0"
        except ValueError:
            pass
    return version


def _read_harness_base(spoke_root):
    """Read the recorded base SHA from a spoke's local runtime (written by harness_upgrade pull)."""
    p = Path(spoke_root) / "WAI-Harness" / BASE_SHA_FILE
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return None


def _git_head(repo_root):
    """Return HEAD SHA for a git repo, or None."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def _git_file_at_sha(repo_root, sha, relpath):
    """Return file bytes at a specific commit, or None if absent."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{sha}:{relpath}"],
            capture_output=True, timeout=30,
        )
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def _three_way_merge(base_content, ours_content, theirs_content):
    """3-way merge using git merge-file in a temp dir.
    Returns (merged_content, had_conflict)."""
    with tempfile.TemporaryDirectory() as tmp:
        base_f = Path(tmp) / "base"
        ours_f = Path(tmp) / "ours"
        theirs_f = Path(tmp) / "theirs"
        base_f.write_bytes(base_content)
        ours_f.write_bytes(ours_content)
        theirs_f.write_bytes(theirs_content)
        r = subprocess.run(
            ["git", "merge-file", "-q", "--stdout",
             str(ours_f), str(base_f), str(theirs_f)],
            capture_output=True, timeout=30,
        )
        merged = r.stdout
        had_conflict = r.returncode != 0
        return merged, had_conflict


def _emit_conflict_lug(master_harness, spoke_name, conflicted_files):
    """Write a notice lug to the spoke's incoming/ (delivered back to that spoke)
    and to master's own local/ as a record."""
    # Try to find the spoke's incoming/ via hub registry
    spoke_incoming = None
    try:
        repo_root = Path(master_harness).parent
        hub_registry = repo_root / "WAI-Harness" / "hub" / "local" / "hub-registry.json"
        reg = json.loads(hub_registry.read_text())
        spoke_entry = next(
            (w for w in reg.get("wheels", [])
             if w.get("name") == spoke_name or w.get("wheel_id") == spoke_name),
            None,
        )
        if spoke_entry:
            sp_path = spoke_entry.get("path", "")
            if sp_path:
                spoke_incoming = Path(sp_path) / "WAI-Harness" / "spoke" / "local" / "lugs" / "incoming"
    except Exception:
        pass

    slug = f"notice-harness-converge-conflict-{spoke_name}-v1"
    lug = {
        "id": slug,
        "type": "notice",
        "status": "open",
        "from_spoke": "mywheel",
        "to_spoke": spoke_name,
        "title": (f"harness-converge: {len(conflicted_files)} managed/ file(s) conflict "
                  f"with master — review needed"),
        "body": (
            "The master ran harness_converge reconcile and found files that diverged in BOTH "
            "the master and your spoke since the last sync. These were NOT auto-merged "
            "to avoid silent data loss. Master version kept. Review the diff and re-contribute "
            "if your version should win."
        ),
        "conflicted_files": conflicted_files,
        "resolution": "review each file; confirm master version is correct or re-contribute via harness_converge contribute",
        "created_at": _utcnow(),
    }

    master_local_incoming = Path(master_harness) / "spoke" / "local" / "lugs" / "incoming"
    for dest in [p for p in [spoke_incoming, master_local_incoming] if p]:
        try:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"{slug}.json").write_text(json.dumps(lug, indent=2) + "\n")
        except Exception:
            pass
    return lug


def _recut_manifest(master_harness, new_version):
    """Re-cut the master MANIFEST with a bumped version. Returns the new manifest."""
    managed = Path(master_harness) / "spoke" / "managed"
    m = hu.build_manifest(str(managed), version=new_version, generated_at=_utcnow())
    mpath = managed / hu.MANIFEST_NAME
    mpath.write_text(json.dumps(m, indent=2) + "\n")
    return m


# ── live-vs-managed classify + absorb (bug-converge-silently-reverts-locally-
#    authored-behavior-v1) ───────────────────────────────────────────────────
#
# THE BUG THIS CLOSES. A fix lands in the LIVE copy of a file (e.g.
# .claude/hooks/wakeup-canonical.sh). The canonical source is the copy under
# managed/. Redeploy/converge restores live from managed and the fix is gone —
# no error, no log, success reported while behavior regresses. Endemic on
# basher, which holds a standing population of locally-authored files under
# managed/ itself; caught once in mywheel (s140) by hand-diffing live vs
# managed, which is not a strategy.
#
# OPERATOR RULING (s140, verbatim, sharpening the original ask): "On converging
# they should absolutely do a diff and evaluate the change its absorbing dont
# blindly overwright files." The floor is detect-and-halt; the actual ask is
# detect-and-CLASSIFY: converge must say what the difference IS, not only that
# one exists.
#
# SCOPE: this covers the 1:1 mirrored subtree managed/.claude/** <->
# <spoke_root>/.claude/** (hooks, commands, agents, skills, workflows) — the
# exact subtree the operator's incident and this bug's file_targets concern.
# The wider managed/ tree (tools/, templates/, etc.) has no live mirror; its
# spoke<->master convergence is handled by reconcile()/list_contributions()
# below, using a parallel but distinct base (master's managed tree, not git
# HEAD) — see classify_pull_exposure().
#
# CLASSIFICATION, not arbitration. This code reports which side changed and by
# how much. It never decides whether a change is GOOD — that judgment call
# belongs to the operator. A tool that pretended to arbitrate quality would
# make a confident wrong choice at exactly the wrong moment.

LIVE_MIRROR_SUBTREE = ".claude"
AHEAD_LEDGER_NAME = getattr(hu, "AHEAD_LEDGER", "harness-ahead.json")


def _read_bytes_or_none(path):
    try:
        return Path(path).read_bytes()
    except (OSError, FileNotFoundError):
        return None


def _git_hash_object_write(repo_root, content_bytes):
    """Write CONTENT (working-tree bytes, possibly uncommitted/untracked) to the
    git object database as a blob and return its SHA. Pure content-addressed
    storage — does not touch the working tree, the index, or any ref by itself.
    Returns None on any failure (never raises)."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "hash-object", "-w", "--stdin"],
            input=content_bytes, capture_output=True, timeout=30,
        )
        sha = r.stdout.decode().strip()
        return sha if r.returncode == 0 and sha else None
    except Exception:
        return None


def _git_update_ref(repo_root, ref, sha):
    """Point REF at SHA (git update-ref). This is the ONE sanctioned git write
    this tool performs — the recovery-ref preservation mechanism itself (same
    pattern as managed_retire.py's refs/recovery/retire-*). Returns True/False."""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo_root), "update-ref", ref, sha],
            capture_output=True, timeout=30,
        )
        return r.returncode == 0
    except Exception:
        return False


def _diff_stat(managed_bytes, live_bytes, max_sample=6):
    """Line-level summary of what converge would ABSORB: lines it would remove
    from live (present in live, not in managed) and lines it would add (present
    in managed, not in live), plus a short human-readable sample so a halt can be
    read without opening two files."""
    m_lines = (managed_bytes or b"").decode("utf-8", "replace").splitlines()
    l_lines = (live_bytes or b"").decode("utf-8", "replace").splitlines()
    diff = list(difflib.unified_diff(m_lines, l_lines, fromfile="managed", tofile="live",
                                      lineterm="", n=0))
    added = sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---"))
    sample = [ln for ln in diff if ln[:1] in "+-" and ln[:3] not in ("+++", "---")][:max_sample]
    return {
        "managed_line_count": len(m_lines),
        "live_line_count": len(l_lines),
        "added_in_live_vs_managed": added,
        "removed_from_live_vs_managed": removed,
        "sample": sample,
    }


def _iter_live_mirrored(spoke_managed):
    """Files under managed/.claude/** — the subtree mirrored 1:1 (identical
    relpath) into the spoke's live .claude/**. Yields relpaths like
    '.claude/hooks/x.sh', rooted at the spoke root (git-relative)."""
    base = Path(spoke_managed) / LIVE_MIRROR_SUBTREE
    if not base.is_dir():
        return
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(spoke_managed).as_posix()
        if "__pycache__" in rel:
            continue
        yield rel


def classify_live_file(spoke_root, rel, spoke_managed, pins=None):
    """Classify ONE mirrored file. READ-ONLY — makes no writes of any kind.

    rel is relative to both spoke_root (the live path) and spoke_managed (the
    managed path) — e.g. '.claude/hooks/wakeup-canonical.sh'.

    Returns a dict: {rel, status, ...}. status is one of:
      IDENTICAL         — live == managed byte-for-byte. Proceed, no noise.
      LIVE_MISSING       — only in managed (new distribution). Proceed, install.
      BEHIND             — managed changed since HEAD, live did not. Proceed,
                            absorbing is an upgrade.
      AHEAD               — live changed since HEAD (uncommitted or untracked),
                            managed did not. Undeclared local authorship about
                            to be destroyed. HALT.
      CONFLICT            — both changed since HEAD and disagree. Genuine
                            conflict; HALT and show both sides.
      DECLARED_OVERRIDE   — differs, but declared in harness-ahead.json (pins).
                            Proceed WITHOUT copying; record the override.
    """
    spoke_root = Path(spoke_root)
    spoke_managed = Path(spoke_managed)
    live_path = spoke_root / rel
    managed_path = spoke_managed / rel

    live_bytes = _read_bytes_or_none(live_path)
    managed_bytes = _read_bytes_or_none(managed_path)

    if live_bytes is None:
        return {"rel": rel, "status": "LIVE_MISSING"}
    if managed_bytes is None:
        return {"rel": rel, "status": "MANAGED_MISSING"}  # not actionable here
    if live_bytes == managed_bytes:
        return {"rel": rel, "status": "IDENTICAL"}

    # Differ. Classify direction using each side's own git-committed HEAD content
    # as its base — no stored "last sync" state needed, and it directly answers
    # the real-world shape of this bug: an edit landed on disk without a commit.
    managed_git_rel = f"WAI-Harness/spoke/managed/{rel}"
    live_head = _git_file_at_sha(str(spoke_root), "HEAD", rel)
    managed_head = _git_file_at_sha(str(spoke_root), "HEAD", managed_git_rel)

    live_dirty = (live_head is None) or (live_bytes != live_head)
    managed_dirty = (managed_head is None) or (managed_bytes != managed_head)

    if live_dirty and not managed_dirty:
        status = "AHEAD"
    elif managed_dirty and not live_dirty:
        status = "BEHIND"
    else:
        # both dirty, or both settled-but-disagreeing-in-history: either way this
        # is two sides that moved independently — a real conflict, not a clean
        # direction. Never guess; halt and let a human read the diff.
        status = "CONFLICT"

    result = {"rel": rel, "status": status, "diff": _diff_stat(managed_bytes, live_bytes)}

    if status in ("AHEAD", "CONFLICT") and pins is not None and rel in pins:
        result["status"] = "DECLARED_OVERRIDE"
        result["pin"] = {"change_lug": pins[rel].get("change_lug"),
                         "reason": pins[rel].get("reason")}
        result["underlying_status"] = status
    return result


def classify_live_tree(spoke_root, master=None):
    """Classify EVERY file in the live-mirrored subtree. Pure read — no writes.
    This is what converge_preflight.py calls to answer 'what would converge
    take from me?' for the redeploy (managed -> live) direction."""
    spoke_root = Path(spoke_root).resolve()
    spoke_managed = spoke_root / "WAI-Harness" / "spoke" / "managed"
    if not spoke_managed.is_dir():
        return {"ok": False, "error": f"no managed/ at {spoke_managed}"}
    pins, pin_error = hu.load_ahead_ledger(str(spoke_managed))
    files = []
    for rel in _iter_live_mirrored(spoke_managed):
        files.append(classify_live_file(spoke_root, rel, spoke_managed, pins=pins))
    by_status = {}
    for f in files:
        by_status.setdefault(f["status"], []).append(f["rel"])
    return {
        "ok": True,
        "spoke_root": str(spoke_root),
        "checked": len(files),
        "by_status": {k: sorted(v) for k, v in by_status.items()},
        "files": files,
        "ahead_ledger_error": pin_error,
    }


def _converge_receipt_dir(spoke_root):
    d = Path(spoke_root) / "WAI-Harness" / "hub" / "local" / "maintenance" / "receipts"
    return d


def _write_converge_receipt(spoke_root, kind, entries, extra=None):
    """Persist a converge receipt naming every file whose live content differed,
    what was done with it, and where any preserved copy lives. A converge that
    changed behavior and reported nothing IS the bug this closes — so this is
    never optional and never silent, even when every file was IDENTICAL (an
    empty differs-list is itself the receipt's content in that case)."""
    ts = _utcnow()
    receipt = {
        "receipt_id": f"converge-{kind}-{Path(spoke_root).name}-{ts.replace(':', '').replace('+00:00', 'Z')}",
        "kind": kind,
        "ts": ts,
        "spoke_root": str(spoke_root),
        "entries": entries,
        "summary": {
            "differed": len(entries),
            "halted": sum(1 for e in entries if e.get("disposition") == "halted_preserved"),
            "absorbed": sum(1 for e in entries if e.get("disposition") == "absorbed"),
            "overridden": sum(1 for e in entries if e.get("disposition") == "overridden"),
        },
    }
    if extra:
        receipt.update(extra)
    try:
        rdir = _converge_receipt_dir(spoke_root)
        rdir.mkdir(parents=True, exist_ok=True)
        path = rdir / f"{receipt['receipt_id']}.json"
        path.write_text(json.dumps(receipt, indent=2) + "\n")
        receipt["receipt_path"] = str(path)
    except Exception as e:  # noqa: BLE001 — a receipt-write failure must still SURFACE
        receipt["receipt_write_error"] = str(e)
    return receipt


def absorb_live(spoke_root, master=None, dry_run=False):
    """The actual converge action for the managed(.claude) -> live(.claude)
    direction. For every mirrored file:
      IDENTICAL          -> no-op.
      LIVE_MISSING/BEHIND -> copy managed -> live (an upgrade). Recorded 'absorbed'.
      DECLARED_OVERRIDE   -> skip the copy; live keeps its declared local content.
                             Recorded 'overridden'.
      AHEAD/CONFLICT      -> HALT: live is NOT touched. The live file's CURRENT
                             on-disk content (which may be uncommitted) is
                             snapshotted to a git blob and a refs/recovery/ ref
                             is created pointing at it — the same preservation
                             pattern managed_retire.py uses for retirement.
                             Recorded 'halted_preserved' with the ref name.
    Always emits a converge receipt, even when nothing differed. Never raises;
    a per-file failure is recorded in that file's entry, not fatal to the run.
    """
    spoke_root = Path(spoke_root).resolve()
    classified = classify_live_tree(str(spoke_root), master=master)
    if not classified.get("ok"):
        return classified

    ts_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    entries = []
    for f in classified["files"]:
        rel = f["rel"]
        status = f["status"]
        entry = dict(f)
        live_path = spoke_root / rel
        managed_path = spoke_root / "WAI-Harness" / "spoke" / "managed" / rel

        if status in ("IDENTICAL", "MANAGED_MISSING"):
            entry["disposition"] = "no_action"
        elif status in ("LIVE_MISSING", "BEHIND"):
            entry["disposition"] = "absorbed"
            if not dry_run:
                try:
                    live_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(managed_path, live_path)
                except Exception as e:  # noqa: BLE001
                    entry["disposition"] = "absorb_failed"
                    entry["error"] = str(e)
        elif status == "DECLARED_OVERRIDE":
            entry["disposition"] = "overridden"
        elif status in ("AHEAD", "CONFLICT"):
            entry["disposition"] = "halted_preserved"
            if not dry_run:
                live_bytes = _read_bytes_or_none(live_path)
                blob = _git_hash_object_write(str(spoke_root), live_bytes or b"")
                if blob:
                    ref = f"refs/recovery/converge-live-{rel.replace('/', '-').lstrip('.')}-{ts_tag}"
                    if _git_update_ref(str(spoke_root), ref, blob):
                        entry["recovery_ref"] = ref
                        entry["recovery_blob"] = blob
                    else:
                        entry["preservation_error"] = f"update-ref failed for blob {blob}"
                else:
                    entry["preservation_error"] = "hash-object failed"
        entries.append(entry)

    # The receipt names every file whose live content DIFFERED — not the whole
    # tree. A receipt that repeats 160 unchanged files to report on 1 halted one
    # is noise, and noise is how a check earns being disabled within a week
    # (operator ruling, s140). `checked` still carries the full scan count so
    # "nothing differed" is provably distinct from "nothing was checked".
    differed_entries = [e for e in entries if e["status"] != "IDENTICAL"]
    receipt = _write_converge_receipt(
        spoke_root, "live", differed_entries,
        extra={"dry_run": dry_run, "checked": classified["checked"]},
    )
    return {
        "ok": all(e.get("disposition") not in ("absorb_failed",) and "preservation_error" not in e
                  for e in entries),
        "dry_run": dry_run,
        "spoke_root": str(spoke_root),
        "entries": entries,
        "receipt": receipt,
    }


def classify_pull_exposure(spoke_root, master=None):
    """What would a `harness_upgrade pull` (master managed/ -> this spoke's
    managed/) currently take from this spoke? Pure read — delegates to
    harness_upgrade.compute_home_map, which already carries direction-aware
    'ahead' pins (declared overrides). The 'change' bucket it returns is exactly
    the undeclared-local-authorship-at-risk set: apply() copies master's bytes
    over every one of those files with no halt today.

    This is the OTHER exposure surface named in the bug report ('basher holds
    locally-authored files under managed/ itself') — distinct from the
    managed-vs-live direction above, and it is why basher is measured here on
    ITS OWN managed/ tree against master's, not on live files at all."""
    master_harness = Path(_resolve_master_harness(master)).resolve()
    mm = _master_managed(str(master_harness))
    spoke_root = Path(spoke_root).resolve()
    sm = spoke_root / "WAI-Harness" / "spoke" / "managed"
    if not sm.is_dir():
        return {"ok": False, "error": f"no managed/ at {sm}"}
    try:
        home_map = hu.compute_home_map(mm, str(sm))
    except Exception as e:
        return {"ok": False, "error": f"compute_home_map failed: {e}"}
    return {
        "ok": True,
        "spoke_root": str(spoke_root),
        "master_managed": mm,
        "identical": sorted(home_map.get("unchanged", [])),
        "behind": sorted(home_map.get("add", [])),                 # spoke lacks it -> safe pull
        "ahead_undeclared": sorted(home_map.get("change", [])),    # AT RISK: pull would overwrite silently today
        "ahead_declared": sorted(home_map.get("ahead", [])),       # pinned in harness-ahead.json
        "ahead_declared_detail": home_map.get("ahead_detail", {}),
        "ahead_ledger_error": home_map.get("ahead_error"),
        "orphans": sorted(home_map.get("orphan", [])),
    }


# ── list-contributions ────────────────────────────────────────────────────────

def list_contributions(spoke_roots, master=None):
    """Diff each spoke's managed/ vs master. Pure read — no writes."""
    master_harness = _resolve_master_harness(master)
    mm = _master_managed(master_harness)
    results = []
    for sr in spoke_roots:
        sr = str(Path(sr).resolve())
        sm = _spoke_managed(sr)
        if not Path(sm).is_dir():
            results.append({"spoke": sr, "error": "no WAI-Harness/spoke/managed/ found"})
            continue
        diff = _diff_trees(mm, sm)
        base_info = _read_harness_base(sr)
        results.append({
            "spoke": sr,
            "base": base_info,
            "additions": len(diff["additions"]),
            "conflicts": len(diff["conflicts"]),
            "same": len(diff["same"]),
            "orphans": len(diff["orphans"]),
            "detail": diff,
        })
    return results


# ── reconcile ─────────────────────────────────────────────────────────────────

def reconcile(spoke_root, master=None, dry_run=False, base_sha=None):
    """Apply a spoke's managed/ contributions onto master.

    1. Copy additions (spoke-only files) to master — always clean.
    2. For conflicts (same file, different content):
       - With base_sha: 3-way merge. Clean → apply. Conflict → notice lug, keep master.
       - Without base_sha: keep master, emit notice lug.
    3. Re-cut MANIFEST, bump minor version (only when changes were adopted).
    """
    master_harness = Path(_resolve_master_harness(master)).resolve()
    spoke_root = Path(spoke_root).resolve()
    spoke_name = spoke_root.name

    mm = master_harness / "spoke" / "managed"
    sm = spoke_root / "WAI-Harness" / "spoke" / "managed"

    if not sm.is_dir():
        return {"ok": False, "error": f"no managed/ at {sm}"}

    diff = _diff_trees(str(mm), str(sm))

    # Resolve base SHA
    if not base_sha:
        base_info = _read_harness_base(str(spoke_root))
        if base_info:
            base_sha = base_info.get("master_sha")

    try:
        current_manifest = hu.load_manifest(str(mm))
        current_version = current_manifest.get("harness_version", "4.0.0")
    except Exception:
        current_version = "4.0.0"
    new_version = _bump_minor(current_version)

    report = {
        "ok": False,
        "dry_run": dry_run,
        "spoke": str(spoke_root),
        "master": str(master_harness),
        "base_sha": base_sha,
        "version_before": current_version,
        "version_after": None,
        "adopted": [],
        "merged": [],
        "kept_master": [],
        "conflicts_emitted": [],
    }

    # Step 1: adopt additions (spoke-only files)
    for rel in diff["additions"]:
        src = sm / rel
        dst = mm / rel
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        report["adopted"].append(rel)

    # Step 2: resolve conflicts
    conflicted_files = []
    for rel in diff["conflicts"]:
        master_bytes = (mm / rel).read_bytes()
        spoke_bytes = (sm / rel).read_bytes()
        resolved = False

        if base_sha:
            git_rel = f"WAI-Harness/spoke/managed/{rel}"
            base_bytes = _git_file_at_sha(str(spoke_root), base_sha, git_rel)
            if base_bytes is None:
                base_bytes = _git_file_at_sha(str(master_harness.parent), base_sha, f"WAI-Harness/spoke/managed/{rel}")

            if base_bytes is not None:
                if spoke_bytes == base_bytes:
                    # Spoke unchanged from base → master is newer → keep master
                    report["kept_master"].append(rel)
                    resolved = True
                elif master_bytes == base_bytes:
                    # Master unchanged from base → spoke has clean contribution → adopt
                    if not dry_run:
                        shutil.copy2(sm / rel, mm / rel)
                    report["merged"].append(rel)
                    resolved = True
                else:
                    # Both changed since base → attempt 3-way merge
                    merged_content, had_conflict = _three_way_merge(base_bytes, master_bytes, spoke_bytes)
                    if not had_conflict:
                        if not dry_run:
                            (mm / rel).write_bytes(merged_content)
                        report["merged"].append(rel)
                        resolved = True

        if not resolved:
            report["conflicts_emitted"].append(rel)
            conflicted_files.append(rel)

    if conflicted_files and not dry_run:
        _emit_conflict_lug(str(master_harness), spoke_name, conflicted_files)

    # Step 3: re-cut MANIFEST and bump version when anything changed
    changes_made = len(report["adopted"]) + len(report["merged"])
    if not dry_run and changes_made > 0:
        new_manifest = _recut_manifest(str(master_harness), new_version)
        verify_result = hu.verify(str(mm), new_manifest)
        report["verify_post"] = verify_result
        report["ok"] = verify_result["ok"]
        report["version_after"] = new_version
    else:
        report["ok"] = True
        report["version_after"] = new_version if dry_run else current_version
        if not dry_run:
            report["note"] = "no changes made; MANIFEST version unchanged"

    return report


# ── contribute ────────────────────────────────────────────────────────────────

def contribute(master, spoke_root=None, base_sha=None):
    """Spoke-side: deliver a contribution lug to master's incoming/.

    Lists files this spoke would contribute and records the base SHA so the
    master's reconcile can compute the correct 3-way diff.
    """
    master_harness = Path(_resolve_master_harness(master)).resolve()
    if spoke_root is None:
        spoke_root = Path(".").resolve()
    else:
        spoke_root = Path(spoke_root).resolve()

    spoke_name = spoke_root.name
    mm = master_harness / "spoke" / "managed"
    sm = spoke_root / "WAI-Harness" / "spoke" / "managed"

    if not sm.is_dir():
        return {"ok": False, "error": f"no managed/ at {sm}"}

    if not base_sha:
        base_info = _read_harness_base(str(spoke_root))
        if base_info:
            base_sha = base_info.get("master_sha")
    if not base_sha:
        base_sha = _git_head(str(master_harness.parent))

    diff = _diff_trees(str(mm), str(sm))
    spoke_head = _git_head(str(spoke_root))

    lug_id = f"{CONTRIBUTION_LUG_PREFIX}{spoke_name}-v1"
    lug = {
        "id": lug_id,
        "type": "harness-contribution",
        "status": "open",
        "from_spoke": spoke_name,
        "to_spoke": "mywheel",
        "title": (f"Managed tree contribution from {spoke_name}: "
                  f"{len(diff['additions'])} additions, {len(diff['conflicts'])} conflicts"),
        "spoke_root": str(spoke_root),
        "spoke_head": spoke_head,
        "base_sha": base_sha,
        "files_to_adopt": diff["additions"],
        "files_conflicting": diff["conflicts"],
        "created_at": _utcnow(),
    }

    dest = master_harness / "spoke" / "local" / "lugs" / "incoming"
    dest.mkdir(parents=True, exist_ok=True)
    lug_path = dest / f"{lug_id}.json"
    lug_path.write_text(json.dumps(lug, indent=2) + "\n")

    # Record base sha on spoke for future reference
    base_rec_path = spoke_root / "WAI-Harness" / BASE_SHA_FILE
    base_rec_path.parent.mkdir(parents=True, exist_ok=True)
    base_rec_path.write_text(json.dumps({
        "master_sha": base_sha,
        "master_root": str(master_harness),
        "recorded_at": _utcnow(),
    }, indent=2) + "\n")

    return {
        "ok": True,
        "lug": str(lug_path),
        "additions": len(diff["additions"]),
        "conflicts": len(diff["conflicts"]),
    }


# ── absorb-contributions ──────────────────────────────────────────────────────

def absorb_contributions(master=None):
    """Master-side: process all pending harness-contribution lugs from incoming/.

    Runs reconcile for each spoke, marks lugs processed.
    """
    master_harness = Path(_resolve_master_harness(master)).resolve()
    incoming = master_harness / "spoke" / "local" / "lugs" / "incoming"
    processed_dir = incoming / "processed"

    if not incoming.is_dir():
        return {"ok": True, "contributions": [], "note": "no incoming/ dir"}

    contribution_lugs = sorted(incoming.glob(f"{CONTRIBUTION_LUG_PREFIX}*.json"))
    if not contribution_lugs:
        return {"ok": True, "contributions": [], "note": "no pending contributions"}

    results = []
    all_ok = True
    for lug_path in contribution_lugs:
        try:
            lug = json.loads(lug_path.read_text())
        except Exception as e:
            results.append({"lug": lug_path.name, "ok": False, "error": str(e)})
            all_ok = False
            continue

        spoke_root_str = lug.get("spoke_root")
        base_sha = lug.get("base_sha")

        if not spoke_root_str or not Path(spoke_root_str).is_dir():
            results.append({
                "lug": lug_path.name, "ok": False,
                "error": f"spoke_root {spoke_root_str!r} not accessible",
            })
            all_ok = False
            continue

        rep = reconcile(spoke_root_str, str(master_harness), dry_run=False, base_sha=base_sha)
        rep["lug"] = lug_path.name
        results.append(rep)
        if not rep.get("ok"):
            all_ok = False

        # Move lug to processed/
        processed_dir.mkdir(parents=True, exist_ok=True)
        lug["status"] = "processed"
        lug["processed_at"] = _utcnow()
        lug["reconcile_summary"] = {
            "ok": rep.get("ok"),
            "adopted": len(rep.get("adopted", [])),
            "merged": len(rep.get("merged", [])),
            "conflicts_emitted": len(rep.get("conflicts_emitted", [])),
        }
        (processed_dir / lug_path.name).write_text(json.dumps(lug, indent=2) + "\n")
        lug_path.unlink()

    return {"ok": all_ok, "contributions": results}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd")

    lc = sub.add_parser("list-contributions", help="diff spoke managed/ trees vs master")
    lc.add_argument("--spoke-roots", nargs="+", default=[], metavar="R")
    lc.add_argument("--master", default=None, help="master WAI-Harness path (default from env/config)")

    rec = sub.add_parser("reconcile", help="apply a spoke's contributions onto master")
    rec.add_argument("--spoke-root", required=True)
    rec.add_argument("--master", default=None)
    rec.add_argument("--dry-run", action="store_true")
    rec.add_argument("--base-sha", default=None, help="last sync SHA (spoke or master git)")

    con = sub.add_parser("contribute", help="(spoke-side) deliver contribution lug to master")
    con.add_argument("--master", required=True, help="master WAI-Harness path")
    con.add_argument("--spoke-root", default=None)
    con.add_argument("--base-sha", default=None)

    ab = sub.add_parser("absorb-contributions", help="(master-side) process all pending contribution lugs")
    ab.add_argument("--master", default=None)

    cl = sub.add_parser("classify-live", help="READ-ONLY: classify managed(.claude)/live divergence")
    cl.add_argument("--spoke-root", required=True)
    cl.add_argument("--master", default=None)

    al = sub.add_parser("absorb-live", help="apply managed(.claude) -> live, halting+preserving undeclared local authorship")
    al.add_argument("--spoke-root", required=True)
    al.add_argument("--master", default=None)
    al.add_argument("--dry-run", action="store_true")

    pe = sub.add_parser("pull-exposure", help="READ-ONLY: what a pull would take from a spoke's own managed/ tree")
    pe.add_argument("--spoke-root", required=True)
    pe.add_argument("--master", default=None)

    args = ap.parse_args(argv)

    if args.cmd == "list-contributions":
        result = list_contributions(args.spoke_roots or [], args.master)
        print(json.dumps(result, indent=2))
        return 0

    if args.cmd == "reconcile":
        result = reconcile(args.spoke_root, args.master, dry_run=args.dry_run, base_sha=args.base_sha)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "contribute":
        result = contribute(args.master, args.spoke_root, args.base_sha)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "absorb-contributions":
        result = absorb_contributions(args.master)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "classify-live":
        result = classify_live_tree(args.spoke_root, args.master)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "absorb-live":
        result = absorb_live(args.spoke_root, args.master, dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if args.cmd == "pull-exposure":
        result = classify_pull_exposure(args.spoke_root, args.master)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
