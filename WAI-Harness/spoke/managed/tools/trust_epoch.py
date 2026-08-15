#!/usr/bin/env python3
"""trust_epoch.py -- nothing that predates the approach is trusted.

W1 of the LOW TRUST tenet (spec-low-trust-tenet-v1).

THE FAILURE BEING REMOVED. A spoke adopting an assurance regime inherits its own
history as if that history had passed the regime. Measured on mywheel 2026-08-02,
BEFORE any of this existed: 1423 lugs sat in completed/, 239 of them (17%) carried
both verify steps and file_targets so anyone could re-check them, and 443 (31%)
carried NEITHER -- nothing on disk could ever prove or disprove those 443. They
were nonetheless counted, by every instrument that counted anything, as done work.

That is the ghost. A number computed over 1423 completions, 443 of which are
unfalsifiable by construction, is not a measurement -- it is a mood.

THE RULE. A spoke has a TRUST EPOCH: the instant it adopted the approach.

  * Work completed AFTER the epoch may earn trust, because the gates were live
    when it landed.
  * Work completed BEFORE the epoch earns NOTHING by default. It is not deleted,
    not reopened, not blessed. It is QUARANTINED -- carried in the record, excluded
    from every trust number, and visible as a debt with a name.
  * A quarantined lug leaves quarantine one way only: an independent re-check
    (recertification_sweep / completion_certifier) rules on it. Age does not
    release it. Volume does not release it. The author's word never releases it.

WHY THE EPOCH RATHER THAN "JUST RE-CHECK EVERYTHING". Because 443 of them CANNOT
be re-checked at any price -- there is no verify step and no file target to check
against. A regime that promises to re-verify its whole history is making a claim it
cannot keep, on turn one, about honesty. The epoch is the honest version: we say
plainly which work is proven, which is provable-but-unproven, and which can never
be proven, and we never add the third pile to the first.

FOUR CLASSES, and the whole point is that they are never summed:

  proven         post-epoch, checkable, and an independent check has passed
  provisional    checkable, but no independent check has ruled on it yet
  quarantined    pre-epoch -- excluded from trust numbers until re-checked
  unfalsifiable  no verify steps AND no file_targets: no check is possible, ever

TRUST RATIO = proven / (proven + provisional), computed over POST-EPOCH work only,
and reported as UNKNOWN -- never as a number, never as zero -- when the denominator
is empty or no epoch is stamped. A spoke that has done nothing since adopting the
regime has an unknown floor, not a perfect one and not a failing one. Rounding
"I have not measured" to any number in either direction is the failure this file
exists to remove.

CLI:
    trust_epoch.py --root DIR stamp [--force]     set/confirm this spoke's epoch
    trust_epoch.py --root DIR status [--json]     the four classes + trust ratio
    trust_epoch.py --root DIR classify [--apply]  stamp `trust` onto completed lugs

Exit codes: 0 clean, 1 findings present (quarantine or unfalsifiable non-zero),
2 no epoch stamped (UNKNOWN -- deliberately NOT 0, so a caller that treats exit-0
as green cannot read an unstamped spoke as a passing one).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from wai_paths import resolve_wai_root
except Exception:  # pragma: no cover - wai_paths is always present in a real tree
    resolve_wai_root = None


TRUST_DIR = "trust"
STATE_FILE = "trust-state.json"

CLASS_PROVEN = "proven"
CLASS_PROVISIONAL = "provisional"
CLASS_QUARANTINED = "quarantined"
CLASS_UNFALSIFIABLE = "unfalsifiable"

# Fields whose presence means an independent party has ruled. The worker's own
# narrative fields are deliberately absent from this list -- see completion_certifier.
INDEPENDENT_VERDICT_FIELDS = (
    "certification",
    "certified_by",
    "recertified_at",
    "certifier_verdict",
)


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


def _parse_ts(value):
    """Parse an ISO-8601 timestamp leniently. Returns None when unparseable.

    Unparseable is NOT treated as recent. Callers class a lug with no usable
    timestamp as pre-epoch, because a completion that cannot say when it happened
    cannot claim to have happened under the regime.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def base_dir(root, mode=None):
    if resolve_wai_root is not None:
        base, _ = resolve_wai_root(root, mode)
        if base:
            return base
    return os.path.join(root, "WAI-Harness", "spoke", "local")


def state_path(root, mode=None):
    return os.path.join(base_dir(root, mode), TRUST_DIR, STATE_FILE)


def read_state(root, mode=None):
    path = state_path(root, mode)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(root, state, mode=None):
    path = state_path(root, mode)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def epoch_of(root, mode=None):
    """The spoke's trust epoch as a datetime, or None when unstamped."""
    return _parse_ts(read_state(root, mode).get("trust_epoch"))


def stamp(root, mode=None, force=False, when=None):
    """Set this spoke's trust epoch. Idempotent; refuses to move without --force.

    Re-stamping is a trust-destroying act -- moving the epoch forward silently
    re-quarantines work that had already earned its place, and moving it backward
    silently grants trust to work that never met a gate. Both require --force and
    both are recorded in `epoch_history`.
    """
    state = read_state(root, mode)
    existing = state.get("trust_epoch")
    new = _iso(when or _now())
    if existing and not force:
        return {"changed": False, "trust_epoch": existing, "reason": "already stamped"}
    if existing:
        history = state.setdefault("epoch_history", [])
        history.append({"was": existing, "now": new, "moved_at": _iso(_now())})
    state["trust_epoch"] = new
    state["stamped_at"] = _iso(_now())
    write_state(root, state, mode)
    return {"changed": True, "trust_epoch": new, "reason": "restamped" if existing else "stamped"}


def is_checkable(lug):
    """A lug is checkable when an independent party could decide pass/fail on it.

    That requires a VERIFY statement and nothing else. A verify step is a claim
    someone can re-run; file_targets are a locator, useful but not decisive. This
    matches completion_certifier, which also rules on verify[] alone.

    CORRECTED 2026-08-02, first live run: the initial version required verify AND
    file_targets, which reported 83% of mywheel's history as unfalsifiable when the
    true figure -- lugs with NEITHER, where no check is possible at any price -- is
    31%. Overstating the debt is the same defect as hiding it, and it is a worse one
    in a tool whose whole purpose is honest numbers. `has_targets` is now reported
    beside the classes as a locatability signal, never folded into the verdict.
    """
    return bool(lug.get("verify") or lug.get("acceptance_criteria"))


def has_targets(lug):
    """Locatability: can a re-checker find what this lug touched without guessing?"""
    return bool(lug.get("file_targets"))


def has_independent_verdict(lug):
    for field in INDEPENDENT_VERDICT_FIELDS:
        value = lug.get(field)
        if not value:
            continue
        if isinstance(value, dict):
            verdict = str(value.get("verdict", "")).lower()
            if verdict in ("approved", "certified", "pass", "passed"):
                return True
            continue
        if str(value).lower() in ("approved", "certified", "pass", "passed"):
            return True
        # A bare certifier name/id counts as a ruling having been recorded.
        if field in ("certified_by", "recertified_at"):
            return True
    return False


def completion_time(lug):
    for field in ("completed_at", "certified_at", "closed_at", "updated_at", "created_at"):
        parsed = _parse_ts(lug.get(field))
        if parsed:
            return parsed
    return None


def classify_lug(lug, epoch):
    """Return (class, reason). Order matters -- unfalsifiable outranks everything.

    A pre-epoch lug that is ALSO unfalsifiable is reported as unfalsifiable, not
    quarantined, because quarantine implies a path out and this one has none.
    """
    if not is_checkable(lug):
        return CLASS_UNFALSIFIABLE, "no verify steps -- nothing states what would prove this"
    when = completion_time(lug)
    if epoch is None:
        return CLASS_QUARANTINED, "no trust epoch stamped on this spoke"
    if when is None:
        return CLASS_QUARANTINED, "completion carries no parseable timestamp"
    if when < epoch:
        return CLASS_QUARANTINED, "completed before the trust epoch"
    if has_independent_verdict(lug):
        return CLASS_PROVEN, "post-epoch and independently certified"
    return CLASS_PROVISIONAL, "post-epoch and checkable, but no independent verdict recorded"


def completed_lug_paths(root, mode=None):
    pattern = os.path.join(base_dir(root, mode), "lugs", "bytype", "*", "completed", "*.json")
    return sorted(glob.glob(pattern))


def scan(root, mode=None):
    """Classify every completed lug. Pure read -- writes nothing."""
    epoch = epoch_of(root, mode)
    counts = {
        CLASS_PROVEN: 0,
        CLASS_PROVISIONAL: 0,
        CLASS_QUARANTINED: 0,
        CLASS_UNFALSIFIABLE: 0,
    }
    items = []
    unreadable = []
    unlocatable = 0
    for path in completed_lug_paths(root, mode):
        try:
            with open(path) as handle:
                lug = json.load(handle)
        except (OSError, ValueError) as exc:
            unreadable.append({"path": path, "error": str(exc)})
            continue
        if not isinstance(lug, dict):
            unreadable.append({"path": path, "error": "not a JSON object"})
            continue
        klass, reason = classify_lug(lug, epoch)
        counts[klass] += 1
        if klass != CLASS_UNFALSIFIABLE and not has_targets(lug):
            unlocatable += 1
        items.append({
            "id": lug.get("id") or os.path.basename(path)[:-5],
            "path": path,
            "class": klass,
            "reason": reason,
        })

    total = sum(counts.values())
    denom = counts[CLASS_PROVEN] + counts[CLASS_PROVISIONAL]
    # UNKNOWN, never 0.0 -- an unmeasured floor is not a failing floor.
    trust_ratio = (counts[CLASS_PROVEN] / denom) if denom else None

    return {
        "trust_epoch": _iso(epoch) if epoch else None,
        "epoch_stamped": epoch is not None,
        "total_completed": total,
        "counts": counts,
        "trust_ratio": trust_ratio,
        "trust_ratio_display": (
            "UNKNOWN" if trust_ratio is None else f"{trust_ratio:.0%}"
        ),
        "post_epoch_population": denom,
        "unlocatable": unlocatable,
        "unreadable": unreadable,
        "items": items,
    }


def classify(root, mode=None, apply=False):
    """Stamp a `trust` block onto each completed lug. Dry-run unless apply=True."""
    result = scan(root, mode)
    written = 0
    for item in result["items"]:
        if not apply:
            continue
        try:
            with open(item["path"]) as handle:
                lug = json.load(handle)
        except (OSError, ValueError):
            continue
        block = {
            "class": item["class"],
            "reason": item["reason"],
            "epoch": result["trust_epoch"],
            "classified_at": _iso(_now()),
        }
        if lug.get("trust") == block:
            continue
        lug["trust"] = block
        with open(item["path"], "w") as handle:
            json.dump(lug, handle, indent=2)
            handle.write("\n")
        written += 1
    result["written"] = written
    result["applied"] = bool(apply)
    return result


def render(result):
    lines = []
    epoch = result["trust_epoch"] or "NOT STAMPED"
    lines.append(f"trust epoch: {epoch}")
    counts = result["counts"]
    total = result["total_completed"] or 1
    lines.append(f"completed lugs: {result['total_completed']}")
    for klass in (CLASS_PROVEN, CLASS_PROVISIONAL, CLASS_QUARANTINED, CLASS_UNFALSIFIABLE):
        n = counts[klass]
        lines.append(f"  {klass:<14} {n:>6}  ({n / total:.0%})")
    if result.get("unlocatable"):
        lines.append(f"  (of the checkable, {result['unlocatable']} carry no file_targets"
                     f" -- re-checkable in principle, hard to locate)")
    lines.append(f"trust ratio (post-epoch only): {result['trust_ratio_display']}")
    if result["trust_ratio"] is None:
        lines.append("  UNKNOWN is not a pass and not a failure -- nothing post-epoch to measure yet.")
    if result["unreadable"]:
        lines.append(f"  ! {len(result['unreadable'])} unreadable lug file(s)")
    return "\n".join(lines)


def _main(argv=None):
    # Global flags accepted before OR after the subcommand. The sub-level copy uses
    # SUPPRESS so it cannot re-default --root back to "." over an explicit value.
    top = argparse.ArgumentParser(add_help=False)
    top.add_argument("--root", default=".")
    top.add_argument("--mode", default=None)
    top.add_argument("--json", action="store_true")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS)
    common.add_argument("--mode", default=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0], parents=[top])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_stamp = sub.add_parser("stamp", parents=[common])
    p_stamp.add_argument("--force", action="store_true")

    sub.add_parser("status", parents=[common])

    p_classify = sub.add_parser("classify", parents=[common])
    p_classify.add_argument("--apply", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "stamp":
        out = stamp(args.root, args.mode, force=args.force)
        print(json.dumps(out, indent=2) if args.json else
              f"trust epoch: {out['trust_epoch']} ({out['reason']})")
        return 0

    if args.cmd == "status":
        result = scan(args.root, args.mode)
    else:
        result = classify(args.root, args.mode, apply=args.apply)

    if args.json:
        payload = dict(result)
        payload.pop("items", None)
        print(json.dumps(payload, indent=2))
    else:
        print(render(result))
        if args.cmd == "classify":
            verb = "written" if result["applied"] else "would write (dry-run)"
            print(f"{verb}: {result['written'] if result['applied'] else result['total_completed']}")

    if not result["epoch_stamped"]:
        return 2
    findings = result["counts"][CLASS_QUARANTINED] + result["counts"][CLASS_UNFALSIFIABLE]
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(_main())
