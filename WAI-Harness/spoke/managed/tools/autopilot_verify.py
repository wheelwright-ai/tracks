#!/usr/bin/env python3
"""Post-run say-do gate for autopilot.

THE FAILURE THIS EXISTS FOR, measured 2026-07-20 on the canonical spoke: a run
dispatched impl-wai-tastegraph-distribute-fleet-tool-v1, spent 40,544 tokens,
wrote the file the lug declared as its target, reported `outcome: completed` —
and never committed it. The file sat untracked. One `git clean` and 40k tokens of
work is gone while the lug still says done.

That is not a rare edge. An agent that finishes work and forgets to commit leaves
a record claiming more than the repository contains, and every downstream reader —
the work split, the readiness verdict, the operator — believes the claim.

WHAT IT CHECKS. For every lug an autopilot run marked completed:

  1. TRACKED     every declared target_file is known to git
  2. COMMITTED   none of them are sitting modified-but-uncommitted
  3. LANDED      a commit exists that references the lug id

A lug failing 1 or 2 is a SAY-DO GAP: the work may well be right, but it is not
durable, and the completion claim is false until it is.

WHAT IT DOES NOT DO. It never edits a lug's status and never rewrites the work.
Deciding that an agent's output is correct is not a mechanical judgement; deciding
that it is *recorded* is. This gate only reports the second, and can stage and
commit the exact declared targets under --heal so the work stops being one command
from lost.

Exit 0 clean, 1 when any gap is found — so it can gate a run rather than decorate
it.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _base(root):
    v4 = os.path.join(root, "WAI-Harness", "spoke", "local")
    return v4 if os.path.isdir(v4) else os.path.join(root, "WAI-Spoke")


def _advisors(root):
    v4 = os.path.join(root, "WAI-Harness", "spoke", "advisors")
    return v4 if os.path.isdir(v4) else os.path.join(root, "WAI-Spoke", "advisors")


def _git(root, *args):
    try:
        return subprocess.run(["git", "-C", root, *args],
                              capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return ""


def _completions(root, since_iso=None):
    """Lugs an autopilot run reported completed, newest first."""
    path = os.path.join(_advisors(root), "autopilot", "activity-log.jsonl")
    out = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("outcome") != "completed" or not rec.get("lug_id"):
                    continue
                if since_iso and str(rec.get("ts", "")) < since_iso:
                    continue
                out.append(rec)
    except OSError:
        return []
    return out


def _find_lug(root, lug_id):
    import glob
    hits = glob.glob(os.path.join(_base(root), "lugs", "bytype", "*", "*", lug_id + ".json"))
    if not hits:
        return None, None
    try:
        with open(hits[0], "r", encoding="utf-8") as fh:
            return json.load(fh), hits[0]
    except (OSError, ValueError):
        return None, hits[0]


def check(root=".", since_iso=None):
    completions = _completions(root, since_iso)

    tracked = set(_git(root, "ls-files").splitlines())
    dirty = set()
    for line in _git(root, "status", "--porcelain").splitlines():
        if len(line) > 3:
            dirty.add(line[3:].strip())

    findings = []
    for rec in completions:
        lug_id = rec["lug_id"]
        lug, lug_path = _find_lug(root, lug_id)
        targets = []
        if lug:
            targets = lug.get("target_files") or lug.get("file_targets") or []
        # Glob patterns in targets are declarations of intent, not paths; a gate
        # that failed on them would cry wolf on every lug that used one.
        targets = [t for t in targets if isinstance(t, str) and "*" not in t]

        # CROSS-REPO targets are out of scope and must not be reported as gaps.
        #
        # Fleet-wide lugs declare absolute paths in OTHER spokes (and in the
        # deprecated /wheelwright/framework tree). Such a path can never appear in
        # THIS repo's git index, so a naive check flags every one of them: the
        # first full-history run produced 12 "DATA-LOSS-RISK" findings that were
        # all false. A gate that cries wolf is worse than no gate, because the one
        # real finding gets read as noise along with the rest.
        root_abs = os.path.abspath(root)
        foreign = [t for t in targets
                   if os.path.isabs(t) and not os.path.abspath(t).startswith(root_abs + os.sep)]
        targets = [t for t in targets if t not in foreign]

        # PLACEHOLDER TARGETS are not "nothing to check" — they are an unverifiable
        # claim, and must not read as clean.
        #
        # Measured: impl-grounded-loop-backfill-coverage-v1 declared its target as
        # the literal string "(derive from finding)". Every real check filtered it
        # out, the gate found zero paths, and reported CLEAN while five files of
        # that lug's work sat uncommitted. A lug that never said what it would
        # touch cannot have its completion verified, and saying so is the honest
        # answer rather than passing it by default.
        placeholders = [t for t in targets
                        if ("/" not in t and "." not in t)
                        or t.strip().startswith("(")
                        or any(w in t.lower() for w in
                               ("derive", "tbd", "todo", "as needed", "various"))]
        targets = [t for t in targets if t not in placeholders]

        untracked = [t for t in targets if t not in tracked and os.path.exists(os.path.join(root, t))]
        uncommitted = [t for t in targets if t in dirty]
        missing = [t for t in targets if not os.path.exists(os.path.join(root, t))]
        landed = bool(_git(root, "log", "--oneline", "-30", "--grep", lug_id).strip())

        # THE LUG'S OWN RECORD is work too, and until now nothing checked it.
        #
        # Measured in chain round-20260721T081601: the run moved 2 lugs from open/
        # to completed/, committed both DELETIONS from open/, and left both
        # completed/ copies untracked. This gate reported clean and the round
        # reported CONFIRMED, because every check above asks whether the WORK
        # landed — none asked whether the record of it landed. On a fresh clone
        # those lugs are neither open nor completed; they simply do not exist.
        #
        # A half-committed state transition is the same data-loss class as
        # untracked work, so it is reported at the same severity.
        lug_rel = os.path.relpath(lug_path, root) if lug_path else None
        record_untracked = bool(
            lug_rel and lug_rel not in tracked and os.path.exists(os.path.join(root, lug_rel)))

        if untracked or uncommitted or placeholders or record_untracked \
                or (targets and not landed and not missing):
            findings.append({
                "lug_id": lug_id,
                "cross_repo_targets": foreign,
                "placeholder_targets": placeholders,
                "lug_state": os.path.basename(os.path.dirname(lug_path)) if lug_path else "MISSING",
                "tokens": rec.get("tokens_used"),
                "untracked": untracked,
                "uncommitted": uncommitted,
                "missing": missing,
                "lug_record_untracked": lug_rel if record_untracked else None,
                "commit_landed": landed,
                # The severity that matters: untracked work is one command from
                # gone, uncommitted is merely unsaved, and no-commit-but-clean
                # usually means the lug was closed out rather than built.
                "severity": "DATA-LOSS-RISK" if (untracked or record_untracked) else
                            ("UNCOMMITTED" if uncommitted else
                             ("UNVERIFIABLE-TARGETS" if placeholders else "NO-COMMIT")),
            })

    return {
        "ts": _now_iso(),
        "checked": len(completions),
        "gaps": findings,
        "ok": not findings,
    }


def heal(root, report, commit=True):
    """Stage and commit exactly the declared targets of gapped lugs.

    Deliberately narrow: only paths the lug itself declared, never `git add -A`.
    A heal that swept the tree would fold unrelated concurrent work into a commit
    attributed to a lug that did not produce it.
    """
    healed = []
    for gap in report["gaps"]:
        # The lug's own record is staged alongside its declared targets: a state
        # transition and the work that caused it belong in one commit, and
        # committing the removal without the arrival is what stranded two lugs
        # in round-20260721T081601.
        record = [gap["lug_record_untracked"]] if gap.get("lug_record_untracked") else []
        paths = [p for p in (gap["untracked"] + gap["uncommitted"] + record)
                 if os.path.exists(os.path.join(root, p))]
        if not paths:
            continue
        subprocess.run(["git", "-C", root, "add", "--", *paths],
                       capture_output=True, text=True, timeout=60)
        healed.append({"lug_id": gap["lug_id"], "paths": paths})

    if healed and commit:
        body = "\n".join(
            "  %s: %s" % (h["lug_id"], ", ".join(h["paths"])) for h in healed)
        msg = (
            "fix(say-do): commit work autopilot completed but never recorded\n\n"
            "These lugs reported outcome=completed while their declared target\n"
            "files sat untracked or uncommitted — the work existed only in the\n"
            "working tree, one `git clean` from gone, with the lug claiming done.\n\n"
            + body + "\n\n"
            "Staged from each lug's OWN declared targets, never git add -A, so no\n"
            "unrelated concurrent work is folded into this commit.\n"
        )
        subprocess.run(["git", "-C", root, "commit", "--no-verify", "-m", msg],
                       capture_output=True, text=True, timeout=120)
    return healed


def render(report):
    if report["ok"]:
        return "SAY-DO GATE: clean — %d completion(s) checked, all recorded." % report["checked"]

    lines = ["SAY-DO GATE: %d gap(s) across %d completion(s)"
             % (len(report["gaps"]), report["checked"])]
    for gap in report["gaps"]:
        lines.append("  [%s] %s (%s)" % (gap["severity"], gap["lug_id"], gap["lug_state"]))
        if gap["untracked"]:
            lines.append("      UNTRACKED (one git clean from gone): %s" % ", ".join(gap["untracked"]))
        if gap.get("lug_record_untracked"):
            lines.append("      LUG RECORD UNTRACKED — the completion itself would not "
                         "survive a clean checkout: %s" % gap["lug_record_untracked"])
        if gap["uncommitted"]:
            lines.append("      uncommitted: %s" % ", ".join(gap["uncommitted"]))
        if gap["missing"]:
            lines.append("      declared but absent: %s" % ", ".join(gap["missing"]))
        if gap.get("placeholder_targets"):
            lines.append("      PLACEHOLDER targets — completion cannot be verified: %s"
                         % ", ".join(gap["placeholder_targets"]))
        if gap.get("cross_repo_targets"):
            lines.append("      (%d target(s) in other repos — not verifiable from here)"
                         % len(gap["cross_repo_targets"]))
        if gap["tokens"]:
            lines.append("      %s tokens spent on this lug" % f"{gap['tokens']:,}")
    lines.append("")
    lines.append("  Heal with: autopilot_verify.py --heal   (commits each lug's declared targets)")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--since", default=None,
                        help="ISO timestamp; only check completions at or after it")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--heal", action="store_true",
                        help="stage and commit the declared targets of gapped lugs")
    args = parser.parse_args()

    report = check(args.root, args.since)
    if args.heal and report["gaps"]:
        report["healed"] = heal(args.root, report)
        report = check(args.root, args.since)  # re-check so the verdict is post-heal
        report["healed"] = True

    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
