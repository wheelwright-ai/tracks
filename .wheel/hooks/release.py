#!/usr/bin/env python3
"""Release advice for one project (kit part P-021): when is it worth asking the owner to release? Stdlib only; reads git
and the lug log, never writes except `record` and `applied`, never pushes, deploys or runs a gate.

  release.py advise [--root PATH] [--json]   the recommendation (first line: ASK NOW / BATCH MORE / HOLD / NOTHING TO RELEASE)
  release.py tier   [--root PATH]            the project's tier (income | content | personal | unset)
  release.py lint   [--root PATH]            exit 1 when the project declares no tier (live projects only)
  release.py record [--root PATH] [--commit SHA]   note that main (or SHA) is now in production (.wheel/last-release.json)
  release.py applied [--root PATH] NAME...         note that these migrations are applied in production
  release.py test

Tier: "tier" in .wheel/config.json, one of income | content | personal (plans/release-policy.md in the hub).
  income    makes or will make money: gates are the full tests, a preview deploy, smoke checks after, a second-opinion check.
  content   public, no income yet: tests, a preview, a smoke check.
  personal  serves only the owner: tests and a quick smoke check.
A missing tier is reported by lint and by the Spotter; advice then uses the content gates.

What is waiting: the commits on main that production does not have. "Released" is, in order, the commit in
.wheel/last-release.json, else origin/main (or origin/master), else unknown (the last 20 commits are counted and the
advice says so). Work still on a branch the owner has not accepted is not on main, so it is not counted. Wake and
housekeeping commits (kit, turn save, cycle summaries) carry no value. Lug ids (B-###) in commit messages tie commits to
done lugs; a lug scores its value (1-5) as owner-visible when its urgency is next_session, as plumbing otherwise
(plans/backlog-rubric.md).

THE WEIGHING RULE (the same words are in RULES.md)
  Never ship work still in checking, a pending migration, or past a red smoke check: that is HOLD.
  A fix for something broken is worth a release at any tier.
  Otherwise weigh value waiting against the cost of the gates. The owner-visible value waiting (done next_session lugs,
  summed) must reach the tier's bar: personal 3, content 5, income 8. A cheap gate (personal) clears with one solid
  lug the owner will use; income needs a bigger batch because every release carries four gates.
  Small plumbing waits for a batch: it counts only when it adds up to three times the bar.
  Below the bar the advice is BATCH MORE and says what would tip it. Nothing waiting is silent.
Ozi asks the owner only when the advice is ASK NOW, once, in one line; otherwise it says nothing."""
import json, os, re, subprocess, sys, tempfile, time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
TIERS = ("income", "content", "personal")
BAR = {"personal": 3, "content": 5, "income": 8}
GATES = {"personal": ["tests green", "quick smoke check"],
         "content": ["tests green", "preview deploy", "smoke check"],
         "income": ["full test suite", "preview deploy", "smoke checks after the deploy", "a second-opinion check"]}
HOUSEKEEPING = re.compile(r"^(Wheel: kit|Turn save|Spoke wake|Wake |Merge |Checkpoint)", re.I)
FIX = re.compile(r"^(hot)?fix(es|ed)?\b", re.I)
MIGRATION = re.compile(r"(^|/)(migrations?|db/migrate|prisma/migrations|supabase/migrations)/[^/]+")
RECORD = os.path.join(".wheel", "last-release.json")


def git(root, *a):
    try:
        r = subprocess.run(["git", "-C", root] + list(a), capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def jread(path):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def tier(root):
    """The declared tier, or None."""
    t = jread(os.path.join(root, ".wheel", "config.json")).get("tier")
    return t if t in TIERS else None


def is_live(root):
    return bool(jread(os.path.join(root, ".wheel", "config.json")).get("publishes_live"))


def lint(root):
    """Problems with the tier declaration (a live project must declare one)."""
    cfg = jread(os.path.join(root, ".wheel", "config.json"))
    if "tier" in cfg and cfg["tier"] not in TIERS:
        return ["tier %r is not one of %s" % (cfg["tier"], ", ".join(TIERS))]
    if cfg.get("publishes_live") and "tier" not in cfg:
        return ["publishes live but declares no tier: set \"tier\" in .wheel/config.json (income | content | personal)"]
    return []


def load_backlog(root):
    import importlib.util
    for p in (os.path.join(HERE, "backlog.py"), os.path.join(root, ".wheel", "hooks", "backlog.py")):
        if os.path.exists(p):
            spec = importlib.util.spec_from_file_location("wheel_release_backlog", p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    return None


def main_branch(root):
    for b in ("main", "master"):
        if git(root, "rev-parse", "--verify", "-q", b)[0] == 0:
            return b
    return None


def reference(root, branch):
    """(sha or None, label)."""
    rec = jread(os.path.join(root, RECORD))
    sha = rec.get("commit")
    if sha and git(root, "cat-file", "-e", sha + "^{commit}")[0] == 0:
        return sha, "the last recorded release"
    for r in ("origin/main", "origin/master"):
        rc, out = git(root, "rev-parse", "--verify", "-q", r)
        if rc == 0:
            return out.strip(), r
    return None, None


def waiting(root, branch, ref):
    """[(sha, subject, body)] newest first, housekeeping left out; plus the changed file names."""
    rng = ["%s..%s" % (ref, branch)] if ref else ["-20", branch]
    rc, out = git(root, "log", "--format=%H%x1f%s%x1f%b%x1e", *rng)
    commits = []
    for rec in out.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) >= 2 and parts[0].strip():
            commits.append((parts[0].strip(), parts[1], parts[2] if len(parts) > 2 else ""))
    commits = [c for c in commits if not HOUSEKEEPING.match(c[1])]
    files = set()
    for sha, _, _ in commits:
        files.update(f for f in git(root, "show", "--no-renames", "--name-only", "--format=", sha)[1].split("\n") if f)
    return commits, sorted(files)


def smoke_red(root):
    try:
        line = open(os.path.join(root, ".wheel", "last-smoke.txt")).readline().strip()
    except OSError:
        return None
    if re.search(r"\b(fail|failed|failing|red|error)\b", line, re.I) and not re.search(r"\b0\s+(fail|failed|errors?)\b", line, re.I):
        return line[:120]
    return None


def advise(root):
    """The recommendation as a dict: action (ask | batch | hold | none), tier, line, reason, ships, tip, gates, value."""
    root = os.path.abspath(root)
    t = tier(root)
    use = t or "content"
    out = {"root": root, "tier": t, "gates": GATES[use], "bar": BAR[use], "action": "none", "line": "", "reason": "", "ships": [],
           "tip": "", "value": {"owner_visible": 0, "plumbing": 0}, "commits": 0, "reference": None, "holds": [], "notes": []}
    branch = main_branch(root)
    if not branch or git(root, "rev-parse", "--git-dir")[0] != 0:
        out["line"] = "NOTHING TO RELEASE: not a git project"
        return out
    ref, label = reference(root, branch)
    out["reference"] = label or "unknown"
    if not t:
        out["notes"].append("no tier declared: using the content gates")
    if not ref:
        out["notes"].append("no release reference (no origin and no .wheel/last-release.json): counted the last 20 commits")
    commits, files = waiting(root, branch, ref)
    out["commits"] = len(commits)
    if not commits:
        out["line"] = "NOTHING TO RELEASE: production has everything on %s" % branch
        return out
    bl = load_backlog(root)
    st = None
    if bl and os.path.exists(os.path.join(root, ".wheel", "backlog.jsonl")):
        try:
            st = bl.load(root)
        except Exception:
            st = None
    ids = []
    for _, subj, body in commits:
        for i in re.findall(r"\bB-\d+\b", subj + "\n" + body):
            if i not in ids:
                ids.append(i)
    visible = plumbing = 0
    shipped, checking, fixes = [], [], []
    for i in ids:
        it = (st or {}).get("items", {}).get(i)
        if not it:
            continue
        if it["status"] == "checking":
            checking.append(i)
        if it["status"] != "done":
            continue
        v = int(it.get("value") or 1)
        owner_visible = (it.get("urgency") or "whenever") == "next_session"
        if owner_visible:
            visible += v
        else:
            plumbing += v
        shipped.append((i, it.get("title") or i, v, owner_visible))
        if FIX.match(it.get("title") or ""):
            fixes.append(i)
    for _, subj, _ in commits:
        if FIX.match(subj):
            fixes.append(subj[:60])
    out["value"] = {"owner_visible": visible, "plumbing": plumbing}
    out["ships"] = ["%s %s" % (i, ti) for i, ti, _, _ in shipped] or ["%d commit(s): %s" % (len(commits), commits[0][1][:60])]
    # holds: a gate is red, a migration is missing, work is still in checking
    if checking:
        out["holds"].append("%s still in checking" % ", ".join(checking))
    rec = jread(os.path.join(root, RECORD))
    applied = {os.path.basename(x) for x in rec.get("migrations_applied") or []}
    pending = sorted({f for f in files if MIGRATION.search(f) and os.path.basename(f) not in applied})
    if pending:
        out["holds"].append("migration not recorded as applied: %s" % ", ".join(os.path.basename(p) for p in pending[:3]))
    red = smoke_red(root)
    if red:
        out["holds"].append("last smoke check is red (%s)" % red)
    gates = ", ".join(GATES[use])
    if out["holds"]:
        out["action"] = "hold"
        out["reason"] = "; ".join(out["holds"])
        out["line"] = "HOLD: %s (%d commit(s) wait)" % (out["reason"], len(commits))
        return out
    bar = BAR[use]
    if fixes:
        out["action"] = "ask"
        out["reason"] = "a fix is waiting (%s) and fixes ship at any tier" % fixes[0]
    elif visible >= bar:
        out["action"] = "ask"
        out["reason"] = "%d value points the owner will see (bar %d at %s, gates: %s)" % (visible, bar, use, gates)
    elif plumbing >= 3 * bar:
        out["action"] = "ask"
        out["reason"] = "a large batch of plumbing (%d value points) is waiting" % plumbing
    if out["action"] == "ask":
        out["line"] = "ASK NOW: release %s. Why: %s. Gates: %s." % ("; ".join(out["ships"][:3]), out["reason"], gates)
        return out
    out["action"] = "batch"
    need = bar - visible
    out["tip"] = ("%d more value point(s) of work the owner will see (bar %d at %s), or a fix" % (need, bar, use)) if visible or not plumbing \
        else "work the owner will see worth %d value points (bar %d at %s), or a fix; plumbing alone waits" % (bar, bar, use)
    out["reason"] = "%d owner-visible and %d plumbing value points waiting; releasing costs: %s" % (visible, plumbing, gates)
    out["line"] = "BATCH MORE: %s. Would tip it: %s." % (out["reason"], out["tip"])
    return out


def text(a):
    lines = [a["line"]]
    lines.append("tier %s; reference %s; %d commit(s) waiting" % (a["tier"] or "unset", a["reference"], a["commits"]))
    lines += ["note: " + n for n in a["notes"]]
    return "\n".join(lines)


def record(root, commit=None):
    b = main_branch(root)
    sha = commit or (git(root, "rev-parse", b)[1].strip() if b else "")
    if not sha:
        raise SystemExit("release.py: no commit to record")
    p = os.path.join(root, RECORD)
    d = jread(p)
    d.update(commit=sha, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    json.dump(d, open(p, "w"), indent=1)
    return sha


def applied(root, names):
    p = os.path.join(root, RECORD)
    d = jread(p)
    d["migrations_applied"] = sorted(set(d.get("migrations_applied") or []) | {os.path.basename(n) for n in names})
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(d, open(p, "w"), indent=1)


# ---------- tests ----------
def _sh(root, *a):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    return subprocess.run(a, cwd=root, check=True, capture_output=True, text=True, env=env).stdout.strip()


def _lug(i, value, urgency, status, title=None):
    t = "2026-11-01T00:00:00Z"
    return [{"event": "add", "id": i, "title": title or "Lug %s" % i, "goal": "1", "value": value, "effort": 2, "kind": "autopilot",
             "source": "t", "check": "the file exists", "status": "ready", "rank": 1, "urgency": urgency, "at": t, "by": "t", "reason": "t"}] + \
           ([{"event": "status", "id": i, "status": status, "reason": "t", "at": t, "by": "t"}] if status != "ready" else [])


def _project(tmp, name, tier_=None, lugs=(), commits=(), files=None):
    """A repo with one released commit, then the given waiting commits [(message, [files])]."""
    p = os.path.join(tmp, name)
    os.makedirs(os.path.join(p, ".wheel"))
    _sh(p, "git", "init", "-q", "-b", "main")
    cfg = {"publishes_live": True}
    if tier_:
        cfg["tier"] = tier_
    json.dump(cfg, open(os.path.join(p, ".wheel", "config.json"), "w"))
    evs = []
    for l in lugs:
        evs += _lug(*l)
    with open(os.path.join(p, ".wheel", "backlog.jsonl"), "w") as f:
        for e in evs:
            f.write(json.dumps(e) + "\n")
    open(os.path.join(p, "app.txt"), "w").write("0\n")
    _sh(p, "git", "add", "-A")
    _sh(p, "git", "commit", "-qm", "released")
    record(p)
    for n, (msg, fs) in enumerate(commits):
        for f in fs or ["f%d.txt" % n]:
            os.makedirs(os.path.dirname(os.path.join(p, f)) or p, exist_ok=True)
            open(os.path.join(p, f), "w").write("x%d\n" % n)
            _sh(p, "git", "add", f)
        _sh(p, "git", "commit", "-qm", msg)
    return p


def selftest():
    fails = []

    def check(name, ok, detail=""):
        print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  " + str(detail)))
        if not ok:
            fails.append(name)
    with tempfile.TemporaryDirectory() as t:
        p = _project(t, "a", "personal", [("B-001", 4, "next_session", "done", "Weekly page shows revenue")], [("B-001 revenue page", [])])
        a = advise(p)
        check("personal tier, value-heavy next_session work: ask now", a["action"] == "ask" and a["line"].startswith("ASK NOW") and "B-001" in a["line"], a["line"])
        p = _project(t, "b", "personal", [("B-002", 4, "whenever", "done", "Rotate logs")], [("B-002 rotate logs", [])])
        a = advise(p)
        check("plumbing only: batch more, says what would tip it", a["action"] == "batch" and "would tip" in a["line"].lower(), a["line"])
        p = _project(t, "c", "personal", [("B-003", 5, "next_session", "done", "Nice")], [("B-003 nice", ["db/migrations/001_x.sql"])])
        a = advise(p)
        check("a pending migration: hold", a["action"] == "hold" and "migration" in a["line"], a["line"])
        applied(p, ["001_x.sql"])
        check("recorded migration lifts the hold", advise(p)["action"] == "ask", advise(p)["line"])
        p = _project(t, "d", "personal", [("B-004", 5, "next_session", "checking", "Half done")], [("B-004 half done", [])])
        a = advise(p)
        check("a lug in checking: hold, never ship it", a["action"] == "hold" and "checking" in a["line"], a["line"])
        p = _project(t, "e", "income", [("B-005", 4, "next_session", "done", "Visible")], [("B-005 visible", [])])
        a = advise(p)
        check("income needs more: the same work batches", a["action"] == "batch" and a["bar"] == 8, a["line"])
        p = _project(t, "f", "income", [("B-006", 5, "next_session", "done", "One"), ("B-007", 4, "next_session", "done", "Two")],
                     [("B-006 one", []), ("B-007 two", [])])
        check("income releases once the batch reaches the bar", advise(p)["action"] == "ask", advise(p)["line"])
        p = _project(t, "g", "income", [], [("Fix login redirect loop in production", [])])
        check("a fix goes out even at income", advise(p)["action"] == "ask", advise(p)["line"])
        p = _project(t, "h", "personal", [("B-008", 5, "next_session", "done", "Nice")], [("B-008 nice", [])])
        open(os.path.join(p, ".wheel", "last-smoke.txt"), "w").write("smoke FAILED: 2 of 9 pages\n")
        check("a red smoke check: hold", advise(p)["action"] == "hold", advise(p)["line"])
        p = _project(t, "i", "personal", [], [])
        check("nothing waiting: silent", advise(p)["action"] == "none")
        p = _project(t, "j", None, [("B-009", 5, "next_session", "done", "Nice")], [("B-009 nice", [])])
        a = advise(p)
        check("no tier: content gates, noted; lint reports it", a["bar"] == 5 and any("no tier" in n for n in a["notes"]) and lint(p), str(a["notes"]))
        check("tier helper", tier(p) is None and tier(_project(t, "k", "content")) == "content")
        p = _project(t, "l", "personal", [("B-010", 3, "next_session", "done", "Housekeeping shows")],
                     [("Turn save: x", []), ("Wheel: kit 5", []), ("B-010 shows", [])])
        check("housekeeping commits carry no weight", advise(p)["commits"] == 1, advise(p)["commits"])
    print("release tests: %s" % ("all passed" if not fails else "%d failed" % len(fails)))
    return 1 if fails else 0


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__.split("THE WEIGHING RULE")[0])
        return 0 if args else 2
    cmd, rest = args[0], args[1:]
    if cmd == "test":
        return selftest()
    root, js, commit, names = os.getcwd(), False, None, []
    while rest:
        x = rest.pop(0)
        if x == "--root":
            root = rest.pop(0)
        elif x == "--json":
            js = True
        elif x == "--commit":
            commit = rest.pop(0)
        else:
            names.append(x)
    if cmd == "advise":
        a = advise(root)
        print(json.dumps(a, indent=1) if js else text(a))
        return 0
    if cmd == "tier":
        print(tier(root) or "unset")
        return 0
    if cmd == "lint":
        probs = lint(root)
        print("\n".join(probs) if probs else "tier ok")
        return 1 if probs else 0
    if cmd == "record":
        print("recorded " + record(root, commit))
        return 0
    if cmd == "applied":
        applied(root, names)
        return 0
    print("release.py: unknown command %s" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main())
