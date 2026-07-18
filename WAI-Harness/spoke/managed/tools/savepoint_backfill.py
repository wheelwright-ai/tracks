#!/usr/bin/env python3
"""savepoint_backfill.py — promote evidence that is ALREADY THERE. Invent nothing.

THE OPERATOR'S ASK (s138): retroactively build the progress records into the
legacy session history, so Ozi can walk the trail and check whether past work
still holds.

WHAT MEASUREMENT CHANGED ABOUT THAT PLAN. The obvious reading of "backfill" is to
reconstruct missing work_done from tracks and commits. But the trail is not short
of entries — 249 of 263 savepoints already have work_done. It is short of
EVIDENCE: 330 work entries, and before this ran, 8 with a re-runnable check
against 100 marked verified=true.

Reconstructing prose would therefore have made the record longer and no more
trustworthy. Worse, it would have manufactured hundreds of confident-looking
entries whose only source was an agent's later inference — the exact laundering
of assertion into fact that the compliance oracle, the consent gate and the
claim-is-not-evidence rule were all built to stop.

WHAT THIS TOOL ACTUALLY DOES, AND ITS ONE HARD RULE. It reads the text a session
ALREADY wrote and promotes evidence hiding in it: a repo path, or a commit sha,
mentioned in `what` or `evidence` but never recorded in `verification`. That is a
lossless move of information that was captured at the time by someone who was
there — not a reconstruction by someone who was not.

    IT NEVER INVENTS A VERIFICATION. If no path or sha is present in the
    original text, the entry stays uncheckable and is reported as such.

Measured before writing it: 56 of 330 entries carry recoverable evidence (17
paths, 39 shas). The remaining 274 are an honest gap, and printing that number
truthfully is worth more than closing it falsely.

Every promoted entry is marked `evidence_source: "backfilled-from-prose"` so the
distinction between what a session verified and what a later pass inferred stays
visible forever. A promoted claim is not upgraded to verified=true — promotion
makes it CHECKABLE, and the walk decides whether it holds.

Usage:
    savepoint_backfill.py run [--dry-run] [--json]
"""

import argparse
import glob
import json
import os
import re
import sys

SAVEPOINT_GLOB = "WAI-Harness/spoke/local/initiatives/savepoints/**/*.json"

# Deliberately the same shapes savepoint_walk.py can re-run. Promoting something
# the walker cannot check would just move an uncheckable claim into a field that
# implies it is checkable.
PATH_RE = re.compile(r"(?:WAI-Harness|tools|tests|scripts)/[\w./-]+\.\w+")
SHA_RE = re.compile(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")


def _recover(entry):
    """Find evidence ALREADY present in the entry's own words. Never fabricate.

    Order matters: a path is directly checkable by existence, while a sha needs
    git ancestry, so a path is preferred when both appear.
    """
    blob = " ".join(str(entry.get(k) or "") for k in ("what", "evidence", "verification"))
    m = PATH_RE.search(blob)
    if m:
        return m.group(0), "path"
    m = SHA_RE.search(blob)
    if m:
        return m.group(0), "sha"
    return None, None


def backfill(root, dry_run=False):
    promoted, already, unrecoverable = [], 0, 0

    for path in glob.glob(os.path.join(root, SAVEPOINT_GLOB), recursive=True):
        try:
            sp = json.load(open(path))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(sp, dict):
            continue
        entries = sp.get("work_done")
        if not isinstance(entries, list):
            continue

        changed = False
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            # Already checkable — leave it exactly as the session wrote it.
            cur = str(entry.get("verification") or "")
            if PATH_RE.search(cur) or SHA_RE.search(cur):
                already += 1
                continue

            found, kind = _recover(entry)
            if not found:
                unrecoverable += 1
                continue

            promoted.append({"savepoint": sp.get("id") or os.path.basename(path),
                             "what": (entry.get("what") or "")[:70],
                             "recovered": found, "kind": kind})
            if not dry_run:
                # Preserve the original note; a human wrote it and it carries
                # context the extracted token does not.
                note = cur.strip()
                entry["verification"] = f"{found}" + (f"  ({note})" if note else "")
                entry["evidence_source"] = "backfilled-from-prose"
                changed = True

        if changed and not dry_run:
            json.dump(sp, open(path, "w"), indent=2, ensure_ascii=False)

    total = len(promoted) + already + unrecoverable
    return {"ok": True, "dry_run": dry_run, "entries": total,
            "promoted": len(promoted), "already_checkable": already,
            "unrecoverable": unrecoverable,
            "detail": promoted[:40]}


def cmd_run(args, root):
    rep = backfill(root, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        return 0
    tag = "[dry-run] " if rep["dry_run"] else ""
    print(f"{tag}savepoint backfill — {rep['entries']} work entries scanned")
    print(f"  promoted        {rep['promoted']:4d}  (evidence recovered from the entry's own text)")
    print(f"  already checkable {rep['already_checkable']:2d}")
    print(f"  unrecoverable   {rep['unrecoverable']:4d}  (no path or sha in the original — HONEST GAP)")
    print("\nNothing was invented. An entry with no evidence in its own words stays")
    print("uncheckable; a fabricated verification would be worse than an admitted gap.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Promote evidence already present in savepoint prose")
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    return cmd_run(args, os.path.abspath(args.root))


if __name__ == "__main__":
    sys.exit(main())
