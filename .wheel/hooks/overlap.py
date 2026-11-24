#!/usr/bin/env python3
"""overlap: on a session's first edit of a file, name any other unmerged work that changed the same file (B-381).

    python3 overlap.py hook      PreToolUse hook: reads the hook JSON on stdin, prints a notice as additionalContext
    python3 overlap.py check FILE [--cwd DIR] [--session ID]   the same check from the command line
    python3 overlap.py test      prove it on fixture repositories (replays B-377 vs B-379 on basher/src/wcl.py)

It WARNS and never blocks (owner, 2026-11-23: plans/threads.md, decision 2): the hook always exits 0. A notice names the
thread (branch), its lug, its pane when a thread record gives one, whether it is live (checked out in a worktree) or
parked, how long ago it touched the file, and the git diff to read. Each (session, file) is noticed once; the notices
are logged to overlap.jsonl so the B-383 watch can count them. State lives in $BASHER_STATE or ~/.local/state/basher.
Wiring (kit part P-025, matcher Edit|Write|MultiEdit|NotebookEdit; installed as .wheel/hooks/overlap.py):
    python3 "$CLAUDE_PROJECT_DIR/.wheel/hooks/overlap.py" hook
"""
import json, os, re, subprocess, sys, time

sys.dont_write_bytecode = True
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def state_dir():
    return os.environ.get("BASHER_STATE") or os.path.expanduser("~/.local/state/basher")


def git(cwd, *args):
    try:
        r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def main_branch(top):
    for b in ("main", "master"):
        if git(top, "rev-parse", "--verify", "-q", b) is not None:
            return b
    return None


def worktrees(top):
    """{branch: path} of every worktree, from git worktree list --porcelain."""
    out, path = {}, None
    for line in (git(top, "worktree", "list", "--porcelain") or "").splitlines():
        if line.startswith("worktree "):
            path = line[9:]
        elif line.startswith("branch refs/heads/") and path:
            out[line[18:]] = path
    return out


def thread_info(branch):
    """B-378: the ticket under <state>/threads/<project>/<name>.json whose branch is this one gives thread and pane."""
    d = os.path.join(state_dir(), "threads")
    try:
        for proj in sorted(os.listdir(d)):
            pd = os.path.join(d, proj)
            for n in sorted(os.listdir(pd)) if os.path.isdir(pd) else []:
                if not n.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(pd, n), encoding="utf-8") as f:
                        t = json.load(f)
                except (OSError, ValueError):
                    continue
                if isinstance(t, dict) and t.get("branch") == branch and t.get("state") in ("live", "parked"):
                    return t.get("name") or n[:-5], t.get("pane")
    except OSError:
        pass
    return None, None


def age(secs):
    m = max(0, int(secs // 60))
    if m < 60:
        return "%d minutes" % max(m, 1)
    return "%d hours" % (m // 60) if m < 2880 else "%d days" % (m // 1440)


def others(top, rel, now=None):
    """Notice lines: other branches ahead of main (or other worktrees with uncommitted edits) that changed rel."""
    now = now or time.time()
    main = main_branch(top)
    me = (git(top, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
    wts = worktrees(top)
    mypath = os.path.realpath(top)
    hits = {}
    if main:
        for b in (git(top, "for-each-ref", "--format=%(refname:short)", "refs/heads") or "").split():
            if b in (main, me):
                continue
            if not (git(top, "diff", "--name-only", "%s...%s" % (main, b), "--", rel) or "").strip():
                continue
            log = (git(top, "log", "--format=%ct %s", "%s..%s" % (main, b), "--", rel) or "").splitlines()
            ts = int(log[0].split()[0]) if log else now
            lugs = sorted({m for ln in log for m in re.findall(r"\bB-\d+\b", ln)})
            hits[b] = {"branch": b, "ts": ts, "lugs": lugs, "live": b in wts, "dirty": False}
    for b, p in wts.items():
        if os.path.realpath(p) == mypath or b == main:
            continue
        if (git(p, "status", "--porcelain", "--", rel) or "").strip():
            try:
                ts = os.path.getmtime(os.path.join(p, rel))
            except OSError:
                ts = now
            h = hits.setdefault(b, {"branch": b, "ts": ts, "lugs": [], "live": True, "dirty": True})
            h["live"], h["dirty"], h["ts"] = True, True, max(h["ts"], ts)
    out = []
    for h in sorted(hits.values(), key=lambda h: -h["ts"]):
        name, pane = thread_info(h["branch"])
        who = "thread `%s`" % name if name else "branch `%s`" % h["branch"]
        extra = list(h["lugs"]) + (["pane %s" % pane] if pane else []) + ["live" if h["live"] else "parked"]
        out.append("%s (%s) changed this file %s ago%s: read `git diff %s...%s -- %s`, then build on that branch or "
                   "leave it to that thread" % (who, ", ".join(extra), age(now - h["ts"]),
                                                " (uncommitted)" if h["dirty"] else ", unmerged", main or "main",
                                                h["branch"], rel))
    return out


def seen_path():
    return os.path.join(state_dir(), "overlap-seen.json")


def first_time(session, key):
    """True the first time this session touches key; records it."""
    key = "%s|%s" % (session, key)
    try:
        with open(seen_path(), encoding="utf-8") as f:
            seen = json.load(f)
    except (OSError, ValueError):
        seen = {}
    if key in seen:
        return False
    seen[key] = int(time.time())
    if len(seen) > 4000:
        seen = dict(sorted(seen.items(), key=lambda kv: kv[1])[-2000:])
    try:
        os.makedirs(state_dir(), exist_ok=True)
        tmp = seen_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(seen, f)
        os.replace(tmp, seen_path())
    except OSError:
        pass
    return True


def notice(file_path, cwd, session):
    """The warning text for a first edit of file_path, or '' (not first, no overlap, or not a git file)."""
    cwd = cwd if os.path.isdir(cwd or "") else os.path.dirname(os.path.abspath(file_path))
    top = (git(cwd, "rev-parse", "--show-toplevel") or "").strip()
    if not top:
        return ""
    ap = os.path.realpath(file_path if os.path.isabs(file_path) else os.path.join(cwd, file_path))
    top = os.path.realpath(top)
    if not ap.startswith(top + os.sep):
        return ""
    rel = os.path.relpath(ap, top)
    if rel.startswith(".git" + os.sep) or not first_time(session or "none", rel + "@" + top):
        return ""
    lines = others(top, rel)
    if not lines:
        return ""
    try:
        with open(os.path.join(state_dir(), "overlap.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": int(time.time()), "session": session, "file": rel, "n": len(lines)}) + "\n")
    except OSError:
        pass
    return "Overlap notice for %s: " % rel + "; ".join(lines) + "."


def hook(raw):
    try:
        p = json.loads(raw)
        ti = p.get("tool_input") or {}
        fp = ti.get("file_path") or ti.get("notebook_path")
        if p.get("tool_name") not in EDIT_TOOLS or not fp:
            return ""
        msg = notice(fp, p.get("cwd") or os.getcwd(), p.get("session_id"))
    except Exception:  # a warning tool must never break an edit
        return ""
    if not msg:
        return ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": msg}})


def test():
    import shutil, tempfile, unittest

    class T(unittest.TestCase):
        def setUp(self):
            self.d = tempfile.mkdtemp()
            os.environ["BASHER_STATE"] = os.path.join(self.d, "state")
            self.repo = os.path.join(self.d, "repo")
            os.makedirs(os.path.join(self.repo, "basher", "src"))
            self.g(self.repo, "init", "-q", "-b", "main")
            self.w(self.repo, "basher/src/wcl.py", "base\n")
            self.w(self.repo, "other.py", "x\n")
            self.commit(self.repo, "base")

        def tearDown(self):
            shutil.rmtree(self.d, ignore_errors=True)

        def g(self, cwd, *a):
            subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@t"] + list(a), check=True,
                           capture_output=True)

        def w(self, root, rel, text):
            with open(os.path.join(root, rel), "w") as f:
                f.write(text)

        def commit(self, root, msg):
            self.g(root, "add", "-A")
            self.g(root, "commit", "-q", "-m", msg)

        def wt(self, branch):
            p = os.path.join(self.d, branch.replace("/", "_"))
            self.g(self.repo, "worktree", "add", "-q", "-b", branch, p, "main")
            return p

        def hj(self, wt, rel, session="s1", tool="Edit"):
            return json.dumps({"tool_name": tool, "session_id": session, "cwd": wt,
                               "tool_input": {"file_path": os.path.join(wt, rel)}})

        def ctx(self, out):
            return json.loads(out)["hookSpecificOutput"]["additionalContext"]

        def replay(self):
            a = self.wt("topic/b377")
            self.w(a, "basher/src/wcl.py", "harness resume\n")
            self.commit(a, "B-377 wcl harness resume")
            return a, self.wt("wheel/b379")

        def test_replay_b377_vs_b379_one_notice(self):
            a, b = self.replay()
            c = self.ctx(hook(self.hj(b, "basher/src/wcl.py")))
            self.assertIn("topic/b377", c)
            self.assertIn("B-377", c)
            self.assertIn("live", c)
            self.assertIn("git diff main...topic/b377 -- basher/src/wcl.py", c)
            self.assertEqual(c.count("Overlap notice"), 1)
            self.assertEqual(hook(self.hj(b, "basher/src/wcl.py")), "")  # warns once
            with open(os.path.join(os.environ["BASHER_STATE"], "overlap.jsonl")) as f:
                self.assertEqual(len(f.read().splitlines()), 1)

        def test_new_session_is_noticed_again(self):
            a, b = self.replay()
            self.assertTrue(hook(self.hj(b, "basher/src/wcl.py", "s1")))
            self.assertTrue(hook(self.hj(b, "basher/src/wcl.py", "s2")))

        def test_other_file_and_other_tools_silent(self):
            a, b = self.replay()
            self.assertEqual(hook(self.hj(b, "other.py")), "")
            self.assertEqual(hook(self.hj(b, "basher/src/wcl.py", tool="Read")), "")
            self.assertEqual(hook("not json"), "")

        def test_merged_branch_is_silent(self):
            a, b = self.replay()
            self.g(self.repo, "merge", "-q", "topic/b377")
            self.assertEqual(hook(self.hj(b, "basher/src/wcl.py")), "")

        def test_uncommitted_edit_in_live_worktree(self):
            a = self.wt("topic/b377")
            b = self.wt("wheel/b379")
            self.w(a, "basher/src/wcl.py", "wip\n")
            self.assertIn("uncommitted", self.ctx(hook(self.hj(b, "basher/src/wcl.py"))))

        def test_parked_branch_and_thread_record(self):
            a, b = self.replay()
            self.g(self.repo, "worktree", "remove", "--force", a)
            td = os.path.join(os.environ["BASHER_STATE"], "threads", "proj")
            os.makedirs(td)
            with open(os.path.join(td, "harness-resume.json"), "w") as f:
                json.dump({"name": "harness-resume", "state": "parked", "branch": "topic/b377", "pane": "w3:p1"}, f)
            c = self.ctx(hook(self.hj(b, "basher/src/wcl.py")))
            self.assertIn("thread `harness-resume`", c)
            self.assertIn("pane w3:p1", c)
            self.assertIn("parked", c)

        def test_cli_never_blocks(self):
            r = subprocess.run([sys.executable, "-B", os.path.abspath(__file__), "hook"], input="garbage", text=True,
                               capture_output=True)
            self.assertEqual(r.returncode, 0)

    res = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(T))
    return 0 if res.wasSuccessful() else 1


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "hook":
        out = hook(sys.stdin.read())
        if out:
            print(out)
        return 0
    if cmd == "check" and len(argv) > 2:
        cwd = argv[argv.index("--cwd") + 1] if "--cwd" in argv else os.getcwd()
        sess = argv[argv.index("--session") + 1] if "--session" in argv else "cli"
        print(notice(argv[2], cwd, sess) or "no overlap")
        return 0
    if cmd == "test":
        return test()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
