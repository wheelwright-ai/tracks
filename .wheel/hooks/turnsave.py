#!/usr/bin/env python3
"""Stop hook (kit P-018): every turn ends with a save.

Reads the hook's JSON on stdin (session_id, transcript_path, cwd). Finds the files this session wrote this turn
(Edit/Write/MultiEdit/NotebookEdit tool uses since the owner's last message), and commits exactly those files,
nothing else, on the project's current branch. In a project that publishes live from main (.wheel/config.json
{"publishes_live": true}) a session on main first moves to a wheel/<date>-<session> branch, so the live site is
never touched by a turn save.

Skips, with one JSON line in .wheel/turnsave.log saying why: no files, merge/rebase/cherry-pick in progress,
detached HEAD, a secrets scan hit, a refused pre-commit hook, or only ignored/generated files (those are dropped and
logged when other files can be saved).

  turnsave.py files TRANSCRIPT [--repo PATH]   (read-only: print what the last turn would save)
Never pushes, never prints, never blocks the turn: always exits 0.

  turnsave.py            (as a hook)
  turnsave.py test       (run the fixtures in tools/kit/fixtures/turnsave/)"""
import datetime, importlib.util, json, os, re, subprocess, sys

sys.dont_write_bytecode = True
KIT = os.path.dirname(os.path.abspath(__file__))
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
GENERATED_DIRS = {"node_modules", "dist", "build", ".next", "__pycache__"}
MAX_BYTES = 5 * 1024 * 1024
LOG_REL = ".wheel/turnsave.log"
SYSTEM_TAGS = ("<bash-", "<local-command", "<command-", "<system-reminder>", "<task-notification", "[Request interrupted")

# Used only when the hub's tools/secrets_scan.py is not reachable (WHEEL_HUB or ~/.config/wheel/hub-path).
BUILTIN = [re.compile(p) for p in (
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"s[k]-ant-", r"s[k]-[A-Za-z0-9]{20,}", r"\b(g[h]p_|g[h]o_|github_[p]at_)",
    r"x[o]x[bpas]-", r"A[K]IA[0-9A-Z]{16}", r"e[y]J[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}", r"AIza[0-9A-Za-z_-]{35}",
    r"\b[sr]k_(live|test)_[0-9A-Za-z]{20,}", r"glpat-[A-Za-z0-9_-]{20}", r"\bnpm_[A-Za-z0-9]{36}\b")]
BUILTIN_ASSIGN = re.compile(r"""(password|passwd|secret|api_key|apikey|token)\s*[:=]\s*(['"])([^\s'"]{8,})\2""", re.I)
BUILTIN_PLACEHOLDER = re.compile(r"(your|example|placeholder|changeme|fake|mock|xxxx|dummy|sample|todo|redacted|<|\$\{|\{\{)", re.I)


def git(root, *args, timeout=10, text=True):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    return subprocess.run(["git", "-C", root, *args], capture_output=True, timeout=timeout, env=env,
                          text=text, errors="replace" if text else None)


# ---- the transcript ----
def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def real_user_text(e):
    """The owner's own words for a transcript entry, or None for tool results, echoed output and meta entries."""
    if e.get("type") != "user" or e.get("isMeta") or e.get("isSidechain"):
        return None
    c = (e.get("message") or {}).get("content")
    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
        return None
    t = re.sub(r"<system-reminder>.*?</system-reminder>", "", _text_of(c), flags=re.S).strip()
    if not t or t.startswith(SYSTEM_TAGS):
        return None
    return t


def read_turn(transcript_path):
    """(owner's last ask or '', [raw paths written since that ask]). Unreadable transcript gives ('', [])."""
    entries = []
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        return "", []
    last, ask = -1, ""
    for i, e in enumerate(entries):
        t = real_user_text(e) if isinstance(e, dict) else None
        if t is not None:
            last, ask = i, t
    paths = []
    for e in entries[last + 1:]:
        if not isinstance(e, dict) or e.get("type") != "assistant":
            continue
        c = (e.get("message") or {}).get("content")
        for b in c if isinstance(c, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in EDIT_TOOLS:
                inp = b.get("input") or {}
                p = inp.get("file_path") or inp.get("notebook_path")
                if isinstance(p, str) and p and p not in paths:
                    paths.append(p)
    return ask, paths


def subject(ask):
    first = next((l.strip() for l in ask.splitlines() if l.strip()), "")
    first = re.sub(r"\s+", " ", first) or "work in progress"
    head = "Turn save: "
    room = 72 - len(head)
    if len(first) > room:
        first = first[:room - 3].rstrip() + "..."
    return head + first


# ---- repo checks ----
def in_progress(root):
    for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        r = git(root, "rev-parse", "--git-path", name)
        p = r.stdout.strip()
        if p:
            p = p if os.path.isabs(p) else os.path.join(root, p)
            if os.path.exists(p):
                return name
    return None


def is_generated(rel, full):
    if set(rel.split("/")) & GENERATED_DIRS:
        return True
    try:
        return os.path.isfile(full) and os.path.getsize(full) > MAX_BYTES
    except OSError:
        return False


def hub_scanner():
    hub = os.environ.get("WHEEL_HUB")
    if not hub:
        try:
            hub = open(os.path.expanduser("~/.config/wheel/hub-path")).read().strip()
        except Exception:
            hub = ""
    path = os.path.join(hub, "tools", "secrets_scan.py") if hub else ""
    if not path or not os.path.isfile(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("wheel_secrets_scan", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod if hasattr(mod, "scan_file") and hasattr(mod, "name_flags") else None
    except Exception:
        return None


def scan_hits(rel_files, root):
    """Names of the files whose content or name looks like a secret. Values are never kept or shown."""
    mod = hub_scanner()
    hits = []
    for rel in rel_files:
        full = os.path.join(root, rel)
        if not os.path.isfile(full):
            continue
        try:
            if mod is not None:
                if mod.name_flags(rel) or mod.scan_file(full, rel):
                    hits.append(rel)
                continue
            base = os.path.basename(rel).lower()
            if (base == ".env" or base.startswith(".env.")) and not base.endswith((".example", ".sample", ".template")):
                hits.append(rel)
                continue
            if os.path.getsize(full) > 2 * 1024 * 1024:
                continue
            data = open(full, "rb").read()
            if b"\0" in data[:8192]:
                continue
            text = data.decode("utf-8", "replace")
            if any(rx.search(text) for rx in BUILTIN) or any(
                    not BUILTIN_PLACEHOLDER.search(m.group(3)) for m in BUILTIN_ASSIGN.finditer(text)):
                hits.append(rel)
        except Exception:
            hits.append(rel)  # cannot scan: do not commit blind
    return hits


# ---- the log ----
def ensure_log_ignored(root):
    try:
        p = git(root, "rev-parse", "--git-path", "info/exclude").stdout.strip()
        p = p if os.path.isabs(p) else os.path.join(root, p)
        have = open(p).read().splitlines() if os.path.exists(p) else []
        if LOG_REL not in have:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "a") as f:
                f.write(("\n" if have and have[-1] != "" else "") + LOG_REL + "\n")
    except Exception:
        pass


def log(root, sid, status, reason="", **extra):
    try:
        ensure_log_ignored(root)
        os.makedirs(os.path.join(root, ".wheel"), exist_ok=True)
        row = {"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "session": sid,
               "status": status, "reason": reason}
        row.update(extra)
        with open(os.path.join(root, LOG_REL), "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


def env_id():
    v = os.environ.get("WHEEL_ENV_ID")
    if v:
        return v.strip()
    try:
        return open(os.path.expanduser("~/.config/wheel/environment-id")).read().strip()
    except Exception:
        return ""


def default_branch_names():
    return ("main", "master")


# ---- the save ----
def repo_rels(raw, root, cwd):
    """Raw tool-use paths -> repo-relative paths inside the repo (never inside .git), in order, no repeats."""
    rels = []
    for p in raw:
        full = os.path.realpath(p if os.path.isabs(p) else os.path.join(cwd, p))
        if full == root or not full.startswith(root + os.sep):
            continue
        rel = os.path.relpath(full, root).replace(os.sep, "/")
        if not rel.startswith(".git/") and rel not in rels:
            rels.append(rel)
    return rels


def plan(root, rels):
    """Read-only. (changed, untracked set, ignored paths dropped, generated paths dropped).
    Ignored files are intentionally untracked, so they are dropped, not a reason to skip the turn."""
    ignored = [f for f in rels if git(root, "check-ignore", "-q", "--", f).returncode == 0]
    rest = [f for f in rels if f not in ignored]
    changed, untracked = [], set()
    if rest:
        st = git(root, "status", "--porcelain", "-z", "--untracked-files=all", "--", *rest).stdout
        seen = {}
        for ent in [e for e in st.split("\0") if e]:
            seen[ent[3:]] = ent[:2]
        for f in rest:
            if f in seen:
                changed.append(f)
                if seen[f] == "??":
                    untracked.add(f)
    gen = [f for f in changed if is_generated(f, os.path.join(root, f))]
    changed = [f for f in changed if f not in gen]
    return changed, untracked, ignored, gen


def show_files(tpath, repo):
    """Read-only: print what the hook would save for the transcript's last turn."""
    root = os.path.realpath(repo or os.getcwd())
    top = git(root, "rev-parse", "--show-toplevel").stdout.strip()
    root = os.path.realpath(top) if top else root
    ask, raw = read_turn(tpath)
    rels = repo_rels(raw, root, root)
    changed, _u, ignored, gen = plan(root, rels)
    print("ask: " + subject(ask))
    print("tool-use paths in the last turn: %d (inside the repo: %d)" % (len(raw), len(rels)))
    for label, items in (("would save", changed), ("dropped, ignored", ignored), ("dropped, generated", gen)):
        for f in items:
            print("%s: %s" % (label, f))
    for f in rels:
        if f not in changed and f not in ignored and f not in gen:
            print("no change vs last commit: " + f)


def run(hook):
    cwd = hook.get("cwd") or os.getcwd()
    r = git(cwd, "rev-parse", "--show-toplevel")
    if r.returncode != 0 or not r.stdout.strip():
        return  # not a git repo: nothing to say, nowhere to log
    root = os.path.realpath(r.stdout.strip())
    sid = str(hook.get("session_id") or "unknown")
    tpath = hook.get("transcript_path") or ""

    ask, raw = read_turn(tpath)
    rels = repo_rels(raw, root, cwd)
    if not rels:
        return log(root, sid, "skipped", "no files written this turn")

    why = in_progress(root)
    if why:
        return log(root, sid, "skipped", "%s in progress" % why, files=rels)
    branch = git(root, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip()
    if not branch:
        return log(root, sid, "skipped", "detached HEAD", files=rels)

    changed, untracked, ignored, gen = plan(root, rels)
    dropped = {"ignored": ignored, "generated": gen}
    if not changed:
        if gen and not ignored and not any(f for f in rels if f not in gen):
            return log(root, sid, "skipped", "looks generated", files=gen)
        return log(root, sid, "skipped", "nothing to save (ignored, generated or unchanged)", files=rels, dropped=dropped)
    if any(git(root, "ls-files", "-u", "--", f).stdout.strip() for f in changed):
        return log(root, sid, "skipped", "unmerged paths", files=changed)

    hits = scan_hits(changed, root)
    if hits:
        return log(root, sid, "skipped", "secrets scan hit", files=hits)  # names only, never values

    live = False
    try:
        live = json.load(open(os.path.join(root, ".wheel", "config.json"))).get("publishes_live") is True
    except Exception:
        pass
    made_branch = None
    if live and branch in default_branch_names():
        made_branch = "wheel/%s-%s" % (datetime.date.today().isoformat(), re.sub(r"[^A-Za-z0-9]", "", sid)[:8] or "session")
        sw = git(root, "switch", "-c", made_branch)
        if sw.returncode != 0:
            return log(root, sid, "skipped", "could not create live-project branch", files=changed)

    def undo(note):
        new = [f for f in changed if f in untracked]
        if new:
            git(root, "reset", "-q", "--", *new)
        if made_branch:
            git(root, "switch", "-q", branch)
            git(root, "branch", "-q", "-D", made_branch)
        log(root, sid, "skipped", note, files=changed, dropped=dropped)

    new = [f for f in changed if f in untracked]
    if new:
        a = git(root, "add", "--", *new)
        if a.returncode != 0:
            return undo("git add failed")
    body = ["Files:"] + ["- " + f for f in changed] + ["", "session: " + sid]
    if env_id():
        body.append("env: " + env_id())
    if tpath:
        body.append("track: " + os.path.basename(tpath))
    msg = subject(ask) + "\n\n" + "\n".join(body) + "\n"
    c = git(root, "commit", "-q", "-m", msg, "--", *changed, timeout=60)
    if c.returncode != 0:
        return undo("commit refused (pre-commit hook or git error)")
    sha = git(root, "rev-parse", "--short", "HEAD").stdout.strip()
    log(root, sid, "saved", "", files=changed, branch=made_branch or branch, commit=sha, dropped=dropped)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        sys.path.insert(0, os.path.join(KIT, "fixtures", "turnsave"))
        import cases
        sys.exit(cases.run_all(os.path.abspath(__file__)))
    if len(sys.argv) > 2 and sys.argv[1] == "files":
        repo = sys.argv[sys.argv.index("--repo") + 1] if "--repo" in sys.argv else None
        show_files(sys.argv[2], repo)
        return
    try:
        hook = json.load(sys.stdin)
        if isinstance(hook, dict):
            run(hook)
    except BaseException:
        pass


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        sys.exit(e.code)
    except BaseException:
        pass
    sys.exit(0)
