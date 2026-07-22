#!/usr/bin/env python3
"""Advisor panel — one line per advisor: when it last ran, its net-net call to
action, and when it is next due.

Answers the operator question "what is my advisor bench actually doing?" without
opening a single advisor directory. Rendered in the wakeup briefing ahead of the
TASTEGRAPH block so the panel is structurally recognisable in the same screen
position every session.

Truth precedence, strongest first. The registry is authored metadata and its
`last_run_at` is largely unmaintained (1 of 14 populated on the canonical spoke),
so run evidence always wins over it:

    runs.jsonl (last line)      actual execution, with net-net counts
    scan_state.json             last_run_at / last_scan_at
    schedule-index.json         cadence, next_recommended_run, actionable count
    registry.json               title, cadence, status  (metadata only)

Advisors are discovered from the filesystem, not the registry: the canonical
spoke carries 33 advisor directories against 14 registry entries, so trusting the
registry alone would hide two thirds of the bench.

v4 note: advisors live at WAI-Harness/spoke/advisors — a SIBLING of local/, not
under it. Resolution goes through wai_paths.advisors_dir() so v3 spokes still
work; never hand-join the path.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import wai_paths
except ImportError:  # pragma: no cover - only when run outside the harness
    wai_paths = None

# Files that are advisor plumbing rather than advisors.
_NOT_ADVISORS = {"__pycache__", "schema", "registry.json", "schedule-index.json"}

# Cadence -> expected interval in hours. Anything absent is treated as unscheduled.
_CADENCE_HOURS = {
    "continuous": 1,
    "hourly": 1,
    "per_session": 24,
    "session": 24,
    "daily": 24,
    "nightly": 24,
    "weekly": 168,
    "biweekly": 336,
    "monthly": 720,
    "quarterly": 2160,
}

# Statuses that mean "declared but never wired up" — reported, never called overdue.
_DORMANT = {"stub", "planned", "draft", "retired", "disabled"}


def _now():
    return datetime.now(timezone.utc)


def _parse_ts(value):
    """Parse an ISO timestamp to an aware datetime, or None.

    Advisor artifacts are inconsistent: some stamps carry an offset, some end in
    Z, some are naive. Naive stamps are assumed UTC — mixing naive and aware is
    what produced the "can't subtract offset-naive and offset-aware datetimes"
    error already sitting in the expediter's own verification_debt block.
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
    return dt


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _last_jsonl(path, max_bytes=65536):
    """Return the last parseable JSON object in a .jsonl file.

    Reads the tail only — findings logs grow without bound and the panel runs on
    every session start. Scans upward from the end so a torn final write (common
    if a session was killed mid-append) falls back to the last intact record.
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            if size > max_bytes:
                fh.seek(-max_bytes, os.SEEK_END)
            chunk = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    for line in reversed(chunk.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except ValueError:
            continue
    return None


def _advisors_root(spoke_root):
    # wai_paths returns None when it cannot determine a harness mode (an
    # un-activated or freshly bootstrapped spoke). The panel runs on every session
    # start, so that case must resolve to a path that simply holds no advisors —
    # never propagate None into os.path.join and take the briefing down with it.
    if wai_paths is not None:
        resolved = wai_paths.advisors_dir(spoke_root)
        if resolved:
            return resolved
    # Fallback mirrors wai_paths: v4 sibling location, else v3 nested.
    v4 = os.path.join(spoke_root, "WAI-Harness", "spoke", "advisors")
    return v4 if os.path.isdir(v4) else os.path.join(spoke_root, "WAI-Spoke", "advisors")


def _index_by_id(blob, key="advisor_id"):
    """Normalise registry/schedule payloads to {advisor_id: record}."""
    out = {}
    if isinstance(blob, dict):
        blob = blob.get("advisors", blob)
    if isinstance(blob, dict):
        for name, record in blob.items():
            if isinstance(record, dict):
                out[record.get(key, name)] = record
    elif isinstance(blob, list):
        for record in blob:
            if isinstance(record, dict) and record.get(key):
                out[record[key]] = record
    return out


def _humanise_age(delta_hours):
    if delta_hours is None:
        return "never run"
    if delta_hours < 1:
        return "ran <1h ago"
    if delta_hours < 48:
        return "ran %dh ago" % int(delta_hours)
    return "ran %dd ago" % int(delta_hours / 24)


def _net_net(advisor_dir, run_record):
    """The advisor's own call to action, in its own words where it has one.

    Prefers structured counts from runs.jsonl (what the run concluded) over the
    latest individual finding (one symptom among many).
    """
    if run_record:
        parts = []
        findings = run_record.get("findings")
        if isinstance(findings, int):
            parts.append("%d findings" % findings)
        for field, label in (
            ("needs_judgment", "need judgment"),
            ("actionable_findings", "actionable"),
            ("auto_groomable", "auto-groomable"),
        ):
            value = run_record.get(field)
            if isinstance(value, int) and value:
                parts.append("%d %s" % (value, label))
        if parts:
            return " · ".join(parts)

    finding = _last_jsonl(os.path.join(advisor_dir, "findings-log.jsonl"))
    if finding:
        text = finding.get("recommendation") or finding.get("finding")
        if text:
            severity = finding.get("severity")
            text = str(text).strip()
            if len(text) > 68:
                text = text[:65] + "..."
            return "%s (%s)" % (text, severity) if severity else text
    return "no findings recorded"


def collect(spoke_root="."):
    """Build the panel model. Pure data — rendering is separate and testable."""
    root = _advisors_root(spoke_root)
    registry = _index_by_id(_read_json(os.path.join(root, "registry.json")))
    schedule = _index_by_id(_read_json(os.path.join(root, "schedule-index.json")))

    # Operator kill switch. A deliberately paused advisor must never be reported
    # as overdue — otherwise the panel nags about a decision the operator already
    # made, and the real overdue signal gets buried.
    disabled = (_read_json(os.path.join(root, "disabled.json")) or {}).get("disabled", {})

    names = set()
    if os.path.isdir(root):
        for entry in os.listdir(root):
            if entry in _NOT_ADVISORS or entry.startswith("."):
                continue
            if os.path.isdir(os.path.join(root, entry)):
                names.add(entry)
    # Registered-but-absent advisors still matter: a declared advisor with no
    # directory has never run even once, which is exactly what the panel exists
    # to surface.
    names.update(registry)

    now = _now()
    rows = []
    for name in sorted(names):
        advisor_dir = os.path.join(root, name)
        reg = registry.get(name, {})
        sched = schedule.get(name, {})

        run_record = _last_jsonl(os.path.join(advisor_dir, "runs.jsonl"))
        activity = _last_jsonl(os.path.join(advisor_dir, "activity-log.jsonl"))
        scan_state = _read_json(os.path.join(advisor_dir, "scan_state.json")) or {}

        # NEWEST evidence wins, not first-found. A fixed precedence order silently
        # reports the stale source whenever an advisor writes more than one kind of
        # run artifact: autopilot logs to activity-log.jsonl while its scan_state
        # lags a day, and tool-advisor records last_audit_at with 108 audits behind
        # it while carrying no last_run_at at all — under first-non-null it printed
        # as "never run".
        stamps = [
            _parse_ts((run_record or {}).get("ts")),
            _parse_ts((activity or {}).get("ts")),
            _parse_ts((activity or {}).get("timestamp")),
            _parse_ts(scan_state.get("last_run_at")),
            _parse_ts(scan_state.get("last_scan_at")),
            _parse_ts(scan_state.get("last_audit_at")),
            _parse_ts(sched.get("last_run_at")),
            _parse_ts(reg.get("last_run_at")),
        ]
        stamps = [s for s in stamps if s is not None]
        last_run = max(stamps) if stamps else None
        age_hours = (now - last_run).total_seconds() / 3600.0 if last_run else None

        cadence = (
            sched.get("run_cadence")
            or reg.get("run_schedule")
            or reg.get("run_cadence")
            or ""
        )
        cadence = str(cadence).strip().lower()
        status = str(reg.get("status") or sched.get("status") or "").strip().lower()
        interval = _CADENCE_HOURS.get(cadence)

        # An advisor on an interval cadence that has NEVER run is maximally overdue,
        # not exempt. Requiring a last-run stamp to qualify let navigator (weekly)
        # and proofer (daily) sit permanently outside the overdue tally — the exact
        # advisors most worth surfacing, hidden by the metric meant to surface them.
        off = name in disabled
        overdue_hours = None
        never_run_overdue = False
        if interval and not (status in _DORMANT) and not off:
            if age_hours is None:
                never_run_overdue = True
            elif age_hours > interval:
                overdue_hours = age_hours - interval

        rows.append(
            {
                "advisor_id": name,
                "title": reg.get("title") or name,
                "status": status,
                "disabled": off,
                "disabled_reason": (disabled.get(name) or {}).get("reason", ""),
                "dormant": status in _DORMANT,
                "exists": os.path.isdir(advisor_dir),
                "cadence": cadence,
                "last_run_at": last_run.isoformat() if last_run else None,
                "age_hours": age_hours,
                "overdue_hours": overdue_hours,
                "never_run_overdue": never_run_overdue,
                "next_due": sched.get("next_recommended_run")
                or sched.get("next_scheduled_run"),
                "net_net": _net_net(advisor_dir, run_record),
            }
        )
    return {"advisors_root": root, "generated_at": now.isoformat(), "advisors": rows}


def _due_text(row):
    cadence = row["cadence"] or "unscheduled"

    # Paused by the operator. Stays visible so a pause is never forgotten, but
    # carries no due date — an advisor you switched off is not late.
    if row.get("disabled"):
        return "%s — DISABLED by operator" % cadence

    # A stub that has nonetheless produced run artifacts is not "never wired" —
    # saying so contradicts the age column standing right next to it.
    if row["dormant"]:
        return "%s — stub" % cadence

    # Scheduled but never run: the strongest overdue signal there is.
    if row.get("never_run_overdue"):
        return "%s, OVERDUE — never run" % cadence

    # The age column already reads "never run"; repeating it here just doubles
    # the width of the noisiest rows on the panel.
    if row["age_hours"] is None:
        return cadence

    if row["overdue_hours"] is not None:
        over = row["overdue_hours"]
        unit = "%dh" % int(over) if over < 48 else "%dd" % int(over / 24)
        return "%s, OVERDUE %s" % (cadence, unit)

    # Only interval cadences can be "on time". Event-driven and on-demand
    # advisors have no due date, so claiming they are on time is a false green —
    # the same class of lie as the Hub: OK banner.
    if row["cadence"] in _CADENCE_HOURS:
        return "%s, on time" % cadence
    return cadence if row["cadence"] else "unscheduled"


def render(model, limit=0):
    """Render the panel. Silent when there is no advisor bench at all.

    Ordering puts what needs attention on top: overdue first (worst first), then
    healthy advisors, then dormant stubs — so the panel reads as a call sheet
    rather than an alphabetical inventory.
    """
    rows = model["advisors"]
    if not rows:
        return ""

    def sort_key(row):
        if row.get("disabled"):
            return (3, 0, row["advisor_id"])
        if row["dormant"]:
            return (2, 0, row["advisor_id"])
        # Never-run-but-scheduled sorts above merely-late: no run at all is worse
        # than a late run, however late.
        if row.get("never_run_overdue"):
            return (0, float("-inf"), row["advisor_id"])
        if row["overdue_hours"] is not None:
            return (0, -row["overdue_hours"], row["advisor_id"])
        return (1, -(row["age_hours"] or 0), row["advisor_id"])

    def _is_overdue(row):
        return not row["dormant"] and not row.get("disabled") and (
            row["overdue_hours"] is not None or row.get("never_run_overdue")
        )

    rows = sorted(rows, key=sort_key)
    overdue = sum(1 for r in rows if _is_overdue(r))
    dormant = sum(1 for r in rows if r["dormant"])

    never = sum(1 for r in rows if r["age_hours"] is None)
    off = sum(1 for r in rows if r.get("disabled"))
    lines = [
        "ADVISORS — last run · call to action · next due",
        "  %d on the bench | %d overdue | %d never run | %d stubs%s"
        % (len(rows), overdue, never, dormant,
           (" | %d DISABLED" % off) if off else ""),
    ]

    width = max(len(r["advisor_id"]) for r in rows)
    shown = rows[:limit] if limit else rows
    for row in shown:
        if row.get("disabled"):
            glyph = "x"
        elif row["dormant"]:
            glyph = "·"
        elif _is_overdue(row):
            glyph = "!"
        else:
            glyph = "*"
        lines.append(
            "  %s %-*s  %-14s %s"
            % (glyph, width, row["advisor_id"], _humanise_age(row["age_hours"]), _due_text(row))
        )
        # The net-net line earns its space only when there is something to say.
        # An advisor that has never run has no call to action, and printing
        # "no findings recorded" under 19 of them buries the three that matter.
        if not row["dormant"] and not row.get("disabled") and row["age_hours"] is not None:
            if row["net_net"] != "no findings recorded":
                lines.append("      %s" % row["net_net"])

    if limit and len(rows) > limit:
        lines.append("  ... %d more (advisor_panel.py --all)" % (len(rows) - limit))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spoke-root", default=".", help="spoke root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="emit the model as JSON")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="max advisors to render (0 = all; wakeup uses a cap)",
    )
    parser.add_argument("--all", action="store_true", help="render every advisor")
    args = parser.parse_args()

    model = collect(args.spoke_root)
    if args.json:
        print(json.dumps(model, indent=2))
        return 0

    text = render(model, limit=0 if args.all else args.limit)
    if text:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
