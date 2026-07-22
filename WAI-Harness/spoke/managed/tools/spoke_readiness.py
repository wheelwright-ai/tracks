#!/usr/bin/env python3
"""Spoke readiness — two questions, deliberately kept apart.

  Q1  OPERATIONAL   After this upgrade, will the spoke behave as expected?
  Q2  HEALTH        What is the next action that gets this spoke to a good place?

These have different owners, and merging them is what made the old green light
meaningless. Q1 is the HARNESS's responsibility: hooks wired, tools present,
paths resolving, migrations clean, version honest. The harness controls all of
it, so a Q1 failure is a harness defect and must block.

Q2 is the SPOKE's own condition — backlog quality, dispatchable work, drift. Most
spokes are a mess here because the harness never governed the behaviour that built
them. A Q2 finding is therefore NOT an upgrade failure and must never fail the
upgrade; it is the next piece of work, named.

Reporting them together as one status is how "ok: true" came to sit above a spoke
with one runnable lug out of fifty-one.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import work_split
except Exception:  # pragma: no cover
    work_split = None

_TOOLS = os.path.dirname(os.path.abspath(__file__))

# Q1 checks. Each returns (ok, detail). Anything the harness ships and controls.
_REQUIRED_TOOLS = ("work_split.py", "advisor_panel.py", "disposition_migrate.py",
                   "spoke_expediter.py", "wai_paths.py")
_REQUIRED_HOOKS = ("session-start.sh", "wakeup-canonical.sh", "user-prompt-submit.sh")


def _spoke_paths(root):
    v4 = os.path.join(root, "WAI-Harness", "spoke")
    if os.path.isdir(os.path.join(v4, "local")):
        return {"base": os.path.join(v4, "local"), "advisors": os.path.join(v4, "advisors"),
                "tools": os.path.join(v4, "managed", "tools"), "mode": "v4"}
    return {"base": os.path.join(root, "WAI-Spoke"),
            "advisors": os.path.join(root, "WAI-Spoke", "advisors"),
            "tools": os.path.join(root, "WAI-Spoke", "tools"), "mode": "v3"}


def check_operational(root="."):
    """Q1 — will it operate? Harness-owned, and a failure here blocks."""
    paths = _spoke_paths(root)
    checks = []

    missing_tools = [t for t in _REQUIRED_TOOLS
                     if not os.path.isfile(os.path.join(paths["tools"], t))]
    checks.append(("tools deployed", not missing_tools,
                   "missing: %s" % ", ".join(missing_tools) if missing_tools else "all present"))

    hooks_dir = os.path.join(root, ".claude", "hooks")
    missing_hooks = [h for h in _REQUIRED_HOOKS
                     if not os.path.isfile(os.path.join(hooks_dir, h))]
    checks.append(("hooks wired", not missing_hooks,
                   "missing: %s" % ", ".join(missing_hooks) if missing_hooks else "all present"))

    # Version honesty: VERSION and WAI-State must agree. They drift silently, and a
    # spoke advertising the wrong version pulls the wrong migrations.
    version_file = os.path.join(root, "WAI-Harness", "VERSION")
    declared = stamped = None
    try:
        with open(version_file, "r", encoding="utf-8") as fh:
            declared = fh.read().strip()
    except OSError:
        pass
    try:
        with open(os.path.join(paths["base"], "WAI-State.json"), "r", encoding="utf-8") as fh:
            stamped = (json.load(fh).get("wheel") or {}).get("harness_version")
    except (OSError, ValueError):
        pass
    checks.append(("version honest", bool(declared) and declared == str(stamped),
                   "VERSION=%s WAI-State=%s" % (declared, stamped)))

    # Migration state — the correction pass must report clean, not merely have run.
    migrate = os.path.join(paths["tools"], "disposition_migrate.py")
    if os.path.isfile(migrate):
        try:
            result = subprocess.run(
                [sys.executable, migrate, "--root", root, "--verify", "--json"],
                capture_output=True, text=True, timeout=120)
            blob = json.loads(result.stdout) if result.stdout.strip() else {}
            checks.append(("migrations clean", bool(blob.get("clean")),
                           "unstamped=%s cache_bad=%s" % (blob.get("unstamped_remaining"),
                                                          blob.get("cache_missing_or_zero"))))
        except Exception as exc:
            checks.append(("migrations clean", False, "verify failed: %s" % exc))
    else:
        checks.append(("migrations clean", False, "disposition_migrate.py absent"))

    # The split must actually answer. A spoke that upgraded but cannot report who is
    # blocking what has not become operational in the sense that matters.
    if work_split is not None:
        try:
            model = work_split.collect(root)
            checks.append(("work split answers", model["total_lugs"] >= 0,
                           "%d lugs readable" % model["total_lugs"]))
        except Exception as exc:
            checks.append(("work split answers", False, str(exc)))
    else:
        checks.append(("work split answers", False, "work_split unavailable"))

    return {"ok": all(ok for _, ok, _ in checks), "mode": paths["mode"],
            "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks]}


def assess_health(root="."):
    """Q2 — what is the next action? Spoke-owned, and never blocks the upgrade."""
    if work_split is None:
        return {"available": False, "next_action": "install work_split.py to assess health"}

    model = work_split.collect(root)
    runnable = model["runnable_now"]
    repairable = len(model["repairable"])
    needs_you = len(model["needs_you"])
    total = model["total_lugs"]

    # One next action, chosen by what unlocks the most. Ordering matters more than
    # completeness here: a list of six things is a backlog, not a directive.
    if total == 0:
        action = "no lugs yet — author the first piece of work"
    elif repairable > runnable:
        action = ("groom %d repairable lug(s) — they are blocked on fillable gaps "
                  "(targets/PEV/AC), not on judgment; each one promoted becomes "
                  "autonomous work" % repairable)
    elif runnable == 0 and needs_you:
        action = ("decide %d operator-gated item(s) — nothing is dispatchable until "
                  "one clears" % needs_you)
    elif runnable:
        action = "run autopilot --not-blocking-me — %d lug(s) dispatchable now" % runnable
    else:
        action = "backlog is empty of actionable work — scout for new work"

    top = model["needs_you"][0] if model["needs_you"] else None
    return {
        "available": True,
        "total_lugs": total,
        "runnable_now": runnable,
        "repairable": repairable,
        "needs_you": needs_you,
        # The ratio is the honest headline: a spoke can be perfectly upgraded and
        # still unable to do any autonomous work.
        "autonomy_ratio": round(runnable / total, 2) if total else 0.0,
        "next_action": action,
        "top_blocker": ({"id": top["id"], "unblocks": top["gates"]} if top else None),
    }


def render(operational, health):
    lines = []
    verdict = "OPERATIONAL" if operational["ok"] else "NOT OPERATIONAL"
    lines.append("SPOKE READINESS")
    lines.append("  Q1 will it operate as expected?   %s (%s)" % (verdict, operational["mode"]))
    for check in operational["checks"]:
        if not check["ok"]:
            lines.append("       FAIL %s — %s" % (check["name"], check["detail"]))

    if health.get("available"):
        lines.append("  Q2 next action to health?         %d/%d dispatchable (%.0f%%)"
                     % (health["runnable_now"], health["total_lugs"],
                        health["autonomy_ratio"] * 100))
        lines.append("       -> %s" % health["next_action"])
        if health.get("top_blocker") and health["top_blocker"]["unblocks"]:
            lines.append("       top blocker: %s (unblocks %d)"
                         % (health["top_blocker"]["id"], health["top_blocker"]["unblocks"]))
    else:
        lines.append("  Q2 next action to health?         UNKNOWN — %s" % health["next_action"])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    operational = check_operational(args.root)
    health = assess_health(args.root)

    if args.json:
        print(json.dumps({"operational": operational, "health": health}, indent=2))
    else:
        print(render(operational, health))
    # Exit code reflects Q1 ONLY. Spoke-side mess is the next piece of work, not an
    # upgrade failure, and must never turn a healthy harness red.
    return 0 if operational["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
