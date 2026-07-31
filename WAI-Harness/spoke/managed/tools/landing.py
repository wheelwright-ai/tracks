"""landing.py — the single definition of LANDED, cited rather than copied.

change-git-lifecycle-must-land-on-origin-main-v1.

THE DEFECT THIS EXISTS TO REMOVE. Each ceremony defined "safe" locally, so three
gates each answered a narrower question and their conjunction was mistaken for
the real one. Measured 2026-07-30: session-20260730-0121 committed 17 times,
pushed every one, ended with dead_end_scan clean:true and exit_safety_check
reporting no blockers -- and not one of those commits was on main. Every gate
passed while the work sat off canon.

That is not cosmetic. harness_upgrade distributes the master's WORKING TREE, so
work stranded off main is what the whole fleet receives: spokes were stamped
4.14.31 from a branch whose content predated main's 4.14.30, with the pull
reporting ok:true. "Pushed" read as safe while the fleet was served pre-canon
bytes.

BEHIND IS WORSE THAN AHEAD, and the two must not be collapsed into "unmerged":

  ahead   work of ours canon does not have yet. A debt -- owed, tracked, and
          legitimately outstanding while a session is still running. CSRP keeps
          concurrent lanes off main deliberately, so a gate that blocks on this
          would fail every concurrent session and be routed around within a week.
  behind  canon has work WE do not have. This is the one that ships: it is what
          harness_upgrade hands the fleet, and it is never a normal state to
          exit in.

REMEDIATION MUST RUN IN THE CASE IT FIRES ON. The previous gate printed
`git merge --ff-only` for every unmerged branch, which fails precisely when the
branch has diverged -- exactly when the operator needs it. A gate whose fix
cannot run in the failing case is advice, not a gate, so remediation() is
computed per case.
"""
import subprocess

# Cite this string; do not paraphrase it. Ceremonies that restate the definition
# in their own words are how the three gates drifted apart in the first place.
LANDED_DEFINITION = (
    "LANDED means present on canon: the commit is an ancestor of origin/main. "
    "Not committed, not pushed to a session lane -- present on canon.")

AHEAD = "ahead"          # canon lacks our work -- a tracked debt
BEHIND = "behind"        # we lack canon's work -- this is what the fleet gets
DIVERGED = "diverged"    # both, and ff-only cannot succeed
LANDED = "landed"
UNKNOWN = "unknown"      # no canon ref reachable; never report this as landed


def _git(args, repo):
    try:
        p = subprocess.run(["git", "-C", str(repo)] + args,
                           capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:  # noqa: BLE001 -- a broken probe must not crash a ceremony
        return None, "", str(e)


def canon_ref(repo):
    """origin/main, or local main when there is no remote, or None.

    Never invents a canon: with neither ref present the answer is UNKNOWN, and
    UNKNOWN must never be reported as landed."""
    for ref in ("origin/main", "main"):
        rc, _, _ = _git(["rev-parse", "--verify", ref], repo)
        if rc == 0:
            return ref
    return None


def landing_status(repo, fetch=False):
    """Where HEAD stands relative to canon. The one computation all gates share.

    fetch=False by default: ceremonies run this often and a network call per gate
    is its own failure mode. A caller that needs freshness fetches first.
    """
    ref = canon_ref(repo)
    rc, branch, _ = _git(["rev-parse", "--abbrev-ref", "HEAD"], repo)
    branch = branch.strip() if rc == 0 else ""

    status = {
        "definition": LANDED_DEFINITION,
        "branch": branch,
        "canon_ref": ref,
        "ahead": 0,
        "behind": 0,
        "landed": False,
        "state": UNKNOWN,
        "remediation": None,
        "severity_note": None,
    }
    if ref is None:
        status["severity_note"] = (
            "no origin/main or main to measure against -- landing cannot be "
            "confirmed, and unconfirmed is not landed")
        return status

    if fetch:
        _git(["fetch", "-q", "origin"], repo)

    rc, counts, _ = _git(["rev-list", "--left-right", "--count",
                          "%s...HEAD" % ref], repo)
    if rc != 0 or not counts.strip():
        status["severity_note"] = "could not compare HEAD against %s" % ref
        return status
    parts = counts.split()
    behind = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    ahead = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    status["ahead"], status["behind"] = ahead, behind

    if ahead == 0 and behind == 0:
        status["landed"] = True
        status["state"] = LANDED
        return status

    if ahead and behind:
        status["state"] = DIVERGED
        # ff-only CANNOT succeed here. Name the merge that can.
        status["remediation"] = (
            "cd %s && git fetch origin && git merge %s   "
            "# diverged: a real merge, ff-only cannot succeed here" % (repo, ref))
        status["severity_note"] = (
            "diverged from canon by %d behind / %d ahead -- BEHIND is the serious "
            "half: it is what harness_upgrade distributes to the fleet"
            % (behind, ahead))
    elif behind:
        status["state"] = BEHIND
        status["remediation"] = (
            "cd %s && git fetch origin && git merge --ff-only %s" % (repo, ref))
        status["severity_note"] = (
            "%d commit(s) behind canon -- this tree is what harness_upgrade "
            "distributes, so the fleet would be served pre-canon bytes" % behind)
    else:
        status["state"] = AHEAD
        status["remediation"] = (
            "cd %s && git push origin HEAD:main   "
            "# lands without touching another lane's working tree" % repo)
        status["severity_note"] = (
            "%d commit(s) not on canon -- a landing DEBT, legitimately owed while "
            "concurrent lanes are live, but it is not landed" % ahead)
    return status


def describe(status):
    """One operator-facing line. Ceremonies print this rather than inventing wording."""
    st = status.get("state")
    if st == LANDED:
        return "landed on %s" % status.get("canon_ref")
    if st == UNKNOWN:
        return "landing UNKNOWN — %s" % (status.get("severity_note") or "no canon ref")
    return "NOT LANDED (%s: %d behind / %d ahead of %s)" % (
        st, status.get("behind", 0), status.get("ahead", 0), status.get("canon_ref"))
