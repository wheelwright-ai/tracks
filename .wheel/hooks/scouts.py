#!/usr/bin/env python3
"""Scout checks: small re-runnable checks of a project's posture, cheap to run without a model (kit part P-019).

An advisor that evaluates a project turns what it learns into scouts, so the next look costs nothing. A scout is a folder
.wheel/scouts/NAME/ with
  scout.json   {name, advisor, purpose, severity, checks: [...], created, updated}
  README.md    what it protects, how to re-run it, each check and the outcome it expects (written from scout.json)
  status.json  {last_run, last_ok, runs, fails, catches, lug, last_why}   (the record of re-runs)
A check is either a command (a list, never a shell string) or a file test, plus the outcome it expects:
  {"id": "c1", "what": "no lockfile of the old package manager", "file": "package-lock.json", "expect": {"exists": false}}
  {"id": "c2", "what": "the pack stays small", "cmd": ["git", "count-objects", "-vH"],
   "expect": {"exit": 0, "number": {"regex": "size-pack: ([0-9.]+)", "max": 500}}}
expect for a command: exit (default 0), stdout_contains, stdout_not_contains (a string or a list), stdout_regex,
number {regex, min, max, equals} (the first group), lines {min, max} (non-empty output lines).
expect for a file: exists (true|false), min_bytes, max_bytes, contains.
Only read-only commands run: ls cat head tail wc grep stat du find test diff echo, read-only git (log status diff rev-list
rev-parse ls-files count-objects show branch worktree list describe shortlog for-each-ref tag --list), and the project's own
test runners (bun test, pytest, python3 -m pytest|unittest). No absolute paths, no .., no env or key files, no shell.
A result never stores command output, only whether the expected outcome held and a short plain reason.

Usage (python3 .wheel/hooks/scouts.py ...):
  scouts.py [--root P] list                            the scouts with their last result
  scouts.py [--root P] run [NAME] [--record] [--open-lugs --by WHO] [--json]
                                                       run one scout or all; --record keeps status.json; --open-lugs opens a
                                                       maintenance lug (class maintain, in the keep-healthy initiative) for a
                                                       scout that fails and has none open. Exit 1 when any scout fails.
  scouts.py [--root P] write FILE.json --advisor NAME  write or update a scout from a spec file (validated first)
Stdlib only."""
import argparse, importlib.util, json, os, re, subprocess, sys, time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
SCOUTS = os.path.join(".wheel", "scouts")
MAX_SCOUTS, MAX_CHECKS = 30, 8
PLAIN = ("ls", "cat", "head", "tail", "wc", "grep", "stat", "du", "find", "test", "diff", "echo")
GIT_OK = ("log", "status", "diff", "rev-list", "rev-parse", "ls-files", "count-objects", "show", "branch", "worktree", "describe",
          "shortlog", "for-each-ref", "tag")
FIND_BAD = ("-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls")
GIT_BAD = ("--output", "--ext-diff", "--textconv", "--exec-path", "-c", "-C", "--git-dir", "--work-tree", "--no-index")
RUNNERS = (("bun", "test"), ("bun", "run", "test"), ("pytest",), ("python3", "-m", "pytest"), ("python3", "-m", "unittest"))
SECRETISH = re.compile(r"(^|/)\.env|id_rsa|id_ed25519|\.pem$|\.key$|credential|\.netrc|\.npmrc", re.I)
BAD_CHARS = re.compile(r"[;|&<>`$]|\.\./|^\.\.$|^~|^/")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")


def now_iso(t=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t if t is not None else time.time()))


def jload(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def jdump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def backlog_mod():
    spec = importlib.util.spec_from_file_location("wheel_kit_backlog_scouts", os.path.join(HERE, "backlog.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------- what may run ----------
def command_problem(cmd):
    """Why this command may not run as a scout, or None when it may."""
    if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) and x for x in cmd):
        return "cmd must be a non-empty list of strings (no shell)"
    pattern = None
    if cmd[0] == "grep":   # the pattern may hold regex characters; every other argument is a path or an option
        args = cmd[1:]
        for i, a in enumerate(args):
            if a in ("-e", "--regexp") and i + 1 < len(args):
                pattern = i + 1
                break
        if pattern is None:
            pattern = next((i for i, a in enumerate(args) if not a.startswith("-")), None)
    for i, a in enumerate(cmd[1:]):
        if i == pattern:
            continue
        if BAD_CHARS.search(a) or SECRETISH.search(a):
            return "argument %r is not allowed (absolute path, .., shell characters or an env/key file)" % a[:40]
    for r in RUNNERS:
        if tuple(cmd[:len(r)]) == r:
            return None
    if cmd[0] == "git":
        if len(cmd) < 2 or cmd[1].startswith("-") or cmd[1] not in GIT_OK:
            return "git %s is not a read-only scout command" % (cmd[1] if len(cmd) > 1 else "")
        if any(a in GIT_BAD or a.startswith("--output") for a in cmd[2:]):
            return "git option not allowed"
        if cmd[1] == "worktree" and cmd[2:3] != ["list"]:
            return "only git worktree list is allowed"
        if cmd[1] == "branch":  # listing only: every argument must be a listing flag or the ref a listing filter names
            ok_flags = {"-a", "--all", "-r", "--remotes", "-l", "--list", "-v", "-vv", "--verbose", "--show-current",
                        "--merged", "--no-merged", "--contains", "--no-contains"}
            args = cmd[2:]
            for i, a in enumerate(args):
                takes_ref = i > 0 and args[i - 1] in ("--merged", "--no-merged", "--contains", "--no-contains")
                if a in ok_flags or (takes_ref and re.match(r"^[A-Za-z0-9._/-]{1,80}$", a) and not a.startswith("-")):
                    continue
                return "git branch only lists (%r is not a listing flag)" % a[:20]
        if cmd[1] == "tag" and cmd[2:3] not in (["-l"], ["--list"]):
            return "git tag only lists (-l)"
        return None
    if cmd[0] in PLAIN:
        if cmd[0] == "find" and any(a in FIND_BAD or a.startswith("-fprint") for a in cmd[1:]):
            return "find may not execute or write"
        return None
    return "%s is not a scout command (read-only commands and the project's test runners only)" % cmd[0]


def check_problem(c):
    if not isinstance(c, dict):
        return "a check is an object"
    if not re.match(r"^[a-z0-9_-]{1,20}$", str(c.get("id") or "")):
        return "check id must be 1-20 of a-z 0-9 _ -"
    if not str(c.get("what") or "").strip():
        return "check %s needs a plain 'what'" % c["id"]
    exp = c.get("expect")
    if not isinstance(exp, dict) or not exp:
        return "check %s needs an expect" % c["id"]
    if ("cmd" in c) == ("file" in c):
        return "check %s needs exactly one of cmd or file" % c["id"]
    if "file" in c:
        f = str(c["file"])
        if BAD_CHARS.search(f) or SECRETISH.search(f):
            return "check %s: file path not allowed" % c["id"]
        if not set(exp) <= {"exists", "min_bytes", "max_bytes", "contains"}:
            return "check %s: unknown expect for a file" % c["id"]
        return None
    p = command_problem(c["cmd"])
    if p:
        return "check %s: %s" % (c["id"], p)
    if not set(exp) <= {"exit", "stdout_contains", "stdout_not_contains", "stdout_regex", "number", "lines"}:
        return "check %s: unknown expect for a command" % c["id"]
    n = exp.get("number")
    if n is not None:
        try:
            re.compile(n["regex"])
        except Exception:  # noqa: BLE001
            return "check %s: number needs a valid regex with one group" % c["id"]
        if not any(k in n for k in ("min", "max", "equals")):
            return "check %s: number needs min, max or equals" % c["id"]
    if exp.get("stdout_regex"):
        try:
            re.compile(exp["stdout_regex"])
        except re.error:
            return "check %s: stdout_regex is not valid" % c["id"]
    return None


def validate(spec):
    """(clean spec, problems). The clean spec keeps only the known fields."""
    probs = []
    if not isinstance(spec, dict):
        return None, ["a scout is an object"]
    name = str(spec.get("name") or "")
    if not NAME_RE.match(name):
        probs.append("name must be 3-40 of a-z 0-9 -")
    if not str(spec.get("purpose") or "").strip():
        probs.append("purpose is required: what this scout protects")
    checks = spec.get("checks")
    if not isinstance(checks, list) or not checks:
        probs.append("a scout needs at least one check")
        checks = []
    if len(checks) > MAX_CHECKS:
        probs.append("at most %d checks per scout" % MAX_CHECKS)
    ids = set()
    for c in checks:
        p = check_problem(c)
        if p:
            probs.append(p)
        elif c["id"] in ids:
            probs.append("check id %s is used twice" % c["id"])
        else:
            ids.add(c["id"])
    if probs:
        return None, probs
    clean = {"name": name, "purpose": spec["purpose"].strip()[:300],
             "severity": "blocker" if spec.get("severity") == "blocker" else "normal",
             "checks": [{k: c[k] for k in ("id", "what", "cmd", "file", "expect") if k in c} for c in checks]}
    return clean, []


# ---------- running ----------
def _env():
    keep = {k: os.environ[k] for k in ("PATH", "HOME", "LANG") if k in os.environ}
    keep.update(LC_ALL="C", GIT_OPTIONAL_LOCKS="0", GIT_PAGER="cat", PYTHONDONTWRITEBYTECODE="1",
                PYTEST_ADDOPTS="-p no:cacheprovider")  # F-002: a pytest scout leaves no .pytest_cache
    return keep


def _within(root, rel):
    p = os.path.realpath(os.path.join(root, rel))
    r = os.path.realpath(root)
    return p == r or p.startswith(r + os.sep)


def run_check(root, c):
    """(ok, plain reason). Never raises; never keeps command output."""
    exp = c["expect"]
    if "file" in c:
        p = os.path.join(root, c["file"])
        if not _within(root, c["file"]):
            return False, "file path leaves the project"
        exists = os.path.exists(p)
        if "exists" in exp and bool(exp["exists"]) != exists:
            return False, "%s %s, expected %s" % (c["file"], "exists" if exists else "is missing", "present" if exp["exists"] else "absent")
        if exists and os.path.isfile(p):
            size = os.path.getsize(p)
            if "max_bytes" in exp and size > exp["max_bytes"]:
                return False, "%s is %d bytes, more than %d" % (c["file"], size, exp["max_bytes"])
            if "min_bytes" in exp and size < exp["min_bytes"]:
                return False, "%s is %d bytes, less than %d" % (c["file"], size, exp["min_bytes"])
            if "contains" in exp:
                try:
                    with open(p, encoding="utf-8", errors="replace") as f:
                        if exp["contains"] not in f.read(2_000_000):
                            return False, "%s lacks the expected text" % c["file"]
                except OSError:
                    return False, "%s cannot be read" % c["file"]
        elif exists is False and any(k in exp for k in ("max_bytes", "min_bytes", "contains")) and "exists" not in exp:
            return False, "%s is missing" % c["file"]
        return True, "ok"
    long_ = any(tuple(c["cmd"][:len(r)]) == r for r in RUNNERS)
    try:
        r = subprocess.run(c["cmd"], cwd=root, capture_output=True, text=True, timeout=600 if long_ else 60, stdin=subprocess.DEVNULL, env=_env())
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except OSError as e:
        return False, "could not run (%s)" % str(e)[:60]
    out = r.stdout or ""
    if r.returncode != int(exp.get("exit", 0)):
        return False, "exit %d, expected %d" % (r.returncode, int(exp.get("exit", 0)))
    for key, want in (("stdout_contains", True), ("stdout_not_contains", False)):
        vals = exp.get(key)
        for v in ([vals] if isinstance(vals, str) else vals or []):
            if (v in out) != want:
                return False, "output %s the expected text" % ("lacks" if want else "has")
    if exp.get("stdout_regex") and not re.search(exp["stdout_regex"], out, re.M):
        return False, "output does not match the expected pattern"
    n = exp.get("number")
    if n:
        m = re.search(n["regex"], out, re.M)
        try:
            val = float(m.group(1)) if m else None
        except (ValueError, IndexError):
            val = None
        if val is None:
            return False, "the number was not found in the output"
        if "max" in n and val > n["max"]:
            return False, "number %g is above %g" % (val, n["max"])
        if "min" in n and val < n["min"]:
            return False, "number %g is below %g" % (val, n["min"])
        if "equals" in n and val != n["equals"]:
            return False, "number %g is not %g" % (val, n["equals"])
    ln = exp.get("lines")
    if ln:
        k = len([x for x in out.splitlines() if x.strip()])
        if "max" in ln and k > ln["max"]:
            return False, "%d line(s), more than %d" % (k, ln["max"])
        if "min" in ln and k < ln["min"]:
            return False, "%d line(s), fewer than %d" % (k, ln["min"])
    return True, "ok"


def scout_dir(root, name):
    return os.path.join(root, SCOUTS, name)


def names(root):
    d = os.path.join(root, SCOUTS)
    return sorted(n for n in (os.listdir(d) if os.path.isdir(d) else []) if os.path.exists(os.path.join(d, n, "scout.json")))


def load_scout(root, name):
    return jload(os.path.join(scout_dir(root, name), "scout.json"))


def status_of(root, name):
    return jload(os.path.join(scout_dir(root, name), "status.json"), {}) or {}


def run_scout(root, name, record=False, at=None):
    """Run one scout. Returns {name, advisor, ok, checks: [{id, what, ok, why}], was_ok, caught}. 'caught' is true when it
    fails now and either passed last time or never ran (a new break, or a baseline that already fails). With record the
    status.json is updated."""
    sc = load_scout(root, name) or {}
    spec, probs = validate(sc)
    st = status_of(root, name)
    if spec is None:
        res = {"name": name, "advisor": sc.get("advisor"), "ok": False, "checks": [{"id": "-", "what": "scout.json", "ok": False,
               "why": "invalid scout: " + "; ".join(probs)[:200]}]}
    else:
        rows = []
        for c in spec["checks"]:
            ok, why = run_check(root, c)
            rows.append({"id": c["id"], "what": c["what"], "ok": ok, "why": why})
        res = {"name": name, "advisor": sc.get("advisor"), "ok": all(r["ok"] for r in rows), "checks": rows}
    res["severity"] = (spec or {}).get("severity", "normal")
    res["was_ok"] = st.get("last_ok")
    res["caught"] = (not res["ok"]) and st.get("last_ok") is not False
    if record:
        st.update(last_run=now_iso(at), last_ok=res["ok"], runs=int(st.get("runs") or 0) + 1,
                  fails=0 if res["ok"] else int(st.get("fails") or 0) + 1,
                  catches=int(st.get("catches") or 0) + (1 if res["caught"] else 0),
                  last_why=[r["why"] for r in res["checks"] if not r["ok"]][:4])
        st.setdefault("lug", None)
        jdump(os.path.join(scout_dir(root, name), "status.json"), st)
    return res


def run_all(root, record=False, at=None, only=None):
    return [run_scout(root, n, record, at) for n in names(root) if not only or n == only]


# ---------- writing ----------
def readme_text(spec, advisor, created):
    L = ["# Scout: %s" % spec["name"], "",
         "Written by the %s advisor on %s. %s" % (advisor, created[:10], spec["purpose"]), "",
         "Re-run it with no model: `python3 .wheel/hooks/scouts.py run %s --record`. A break opens a maintenance lug in the "
         "project's keep-healthy initiative when the wake re-runs it." % spec["name"], "", "## Checks and the outcome each expects", ""]
    for c in spec["checks"]:
        what = ("`%s`" % " ".join(c["cmd"])) if "cmd" in c else "file `%s`" % c["file"]
        L.append("- **%s** (%s): %s. Expects %s." % (c["id"], what, c["what"], json.dumps(c["expect"], sort_keys=True)))
    L += ["", "Severity: %s. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the "
          "expectation is out of date) have an advisor update this scout." % spec["severity"], ""]
    return "\n".join(L)


def write_scout(root, spec, advisor, at=None):
    """Validate and write scout.json and README.md. Returns (name, 'created'|'updated'|'unchanged', problems)."""
    clean, probs = validate(spec)
    if clean is None:
        return None, "refused", probs
    if len(names(root)) >= MAX_SCOUTS and clean["name"] not in names(root):
        return None, "refused", ["this project already has %d scouts" % MAX_SCOUTS]
    d = scout_dir(root, clean["name"])
    old = load_scout(root, clean["name"])
    stamp = now_iso(at)
    if old and all(old.get(k) == clean.get(k) for k in ("purpose", "severity", "checks")):
        return clean["name"], "unchanged", []
    full = dict(clean, advisor=advisor, created=(old or {}).get("created") or stamp, updated=stamp)
    jdump(os.path.join(d, "scout.json"), full)
    with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme_text(clean, advisor, full["created"]))
    return clean["name"], "updated" if old else "created", []


# ---------- a break becomes maintenance ----------
def open_break_lug(root, res, by=None, log=None):
    """Open a maintenance lug for a failing scout that has none open. Returns (lug id or None, plain note)."""
    bl = backlog_mod()
    name = res["name"]
    st = status_of(root, name)
    state = bl.load(root)
    cur = st.get("lug")
    if cur and cur in state["items"] and state["items"][cur]["status"] not in bl.CLOSED:
        return None, "lug %s already open for scout %s" % (cur, name)
    ini = bl.keep_healthy(state)
    if ini is None:
        return None, "no keep-healthy initiative in this project, so scout %s opened no lug" % name
    bad = [c for c in res["checks"] if not c["ok"]]
    first = bad[0] if bad else {"what": "it failed", "why": ""}
    title = ("Scout %s broke: %s" % (name, first["what"]))[:110]
    by = by or "scout:%s" % name
    signed = ini["owner_signoff"].get("status") == "yes"
    args = [sys.executable, os.path.join(HERE, "backlog.py"), "--root", root, "add", title, "--value", "4" if res.get("severity") == "blocker" else "3",
            "--effort", "2", "--kind", "autopilot", "--source", "scout:%s (%s advisor)" % (name, res.get("advisor") or "an"),
            "--initiative", ini["id"], "--class", "maintain", "--urgency", "whenever", "--status", "ready" if signed else "proposed",
            "--check", "Running `python3 .wheel/hooks/scouts.py run %s` prints PASS for every check of the scout and exits 0" % name,
            "--reason", "scout %s failed: %s" % (name, "; ".join("%s: %s" % (c["id"], c["why"]) for c in bad)[:300]), "--by", by]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        return None, "could not open a lug for scout %s: %s" % (name, (r.stderr or r.stdout).strip()[:160])
    lug = r.stdout.split()[0]
    st.update(lug=lug)
    jdump(os.path.join(scout_dir(root, name), "status.json"), st)
    return lug, "scout %s broke: opened %s%s" % (name, lug, "" if signed else " (proposed: the keep-healthy initiative has no sign-off)")


def rerun(root, by=None, open_lugs=True, at=None, only=None):
    """Re-run every scout (no model), record the results and open a lug for each new break. Returns
    {ran, failed: [names], caught: [{scout, advisor}], lugs: [ids], notes: [...], results: [...]}."""
    out = {"ran": 0, "failed": [], "caught": [], "lugs": [], "notes": [], "results": []}
    for res in run_all(root, record=True, at=at, only=only):
        out["ran"] += 1
        out["results"].append(res)
        if res["ok"]:
            continue
        out["failed"].append(res["name"])
        if res["caught"]:
            out["caught"].append({"scout": res["name"], "advisor": res.get("advisor")})
        if open_lugs:
            lug, note = open_break_lug(root, res, by)
            out["notes"].append(note)
            if lug:
                out["lugs"].append(lug)
    return out


# ---------- command line ----------
def main(argv=None):
    ap = argparse.ArgumentParser(prog="scouts.py", description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("name", nargs="?")
    r.add_argument("--record", action="store_true")
    r.add_argument("--open-lugs", action="store_true")
    r.add_argument("--by")
    r.add_argument("--json", action="store_true")
    w = sub.add_parser("write")
    w.add_argument("file")
    w.add_argument("--advisor", required=True)
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root or os.getcwd())
    if a.cmd == "list":
        for n in names(root):
            st = status_of(root, n)
            print("%-30s %s  last %s" % (n, {True: "pass", False: "FAIL", None: "never run"}[st.get("last_ok")], st.get("last_run") or "-"))
        return 0
    if a.cmd == "write":
        n, how, probs = write_scout(root, jload(a.file), a.advisor)
        print("%s %s" % (how, n) if n else "refused: " + "; ".join(probs))
        return 0 if n else 1
    if a.name and a.name not in names(root):
        print("no scout named %s" % a.name)
        return 2
    if a.open_lugs:
        res = rerun(root, a.by, True, only=a.name)
        results = res["results"]
        for note in res["notes"]:
            print(note)
    else:
        results = run_all(root, a.record, only=a.name)
    if a.json:
        print(json.dumps(results, indent=1))
    else:
        for x in results:
            print("%s %s" % ("PASS" if x["ok"] else "FAIL", x["name"]))
            for c in x["checks"]:
                print("  %s %s: %s" % ("PASS" if c["ok"] else "FAIL", c["id"], c["what"] if c["ok"] else c["why"]))
    return 0 if all(x["ok"] for x in results) else 1


if __name__ == "__main__":
    sys.exit(main())
