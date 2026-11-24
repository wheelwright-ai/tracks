#!/usr/bin/env python3
"""Scout checks: small re-runnable checks of a project's posture, cheap to run without a model (kit part P-019).

An advisor that evaluates a project turns what it learns into scouts, so the next look costs nothing. A scout is a folder
.wheel/scouts/NAME/ with
  scout.json   {name, advisor, purpose, severity, checks: [...], created, updated}
  README.md    what it protects, how to re-run it, each check and the outcome it expects (written from scout.json)
  status.json  {last_run, last_ok, runs, fails, catches, lug, notice, folded, held, last_why}   (the record of re-runs)
A check is a command (a list, never a shell string), a file test, a freshness test, a row count or a probe, plus the
outcome it expects:
  {"id": "c1", "what": "no lockfile of the old package manager", "file": "package-lock.json", "expect": {"exists": false}}
  {"id": "c2", "what": "the pack stays small", "cmd": ["git", "count-objects", "-vH"],
   "expect": {"exit": 0, "number": {"regex": "size-pack: ([0-9.]+)", "max": 500}}}
expect for a command: exit (default 0), stdout_contains, stdout_not_contains (a string or a list), stdout_regex,
number {regex, min, max, equals} (the first group), lines {min, max} (non-empty output lines).
expect for a file: exists (true|false), min_bytes, max_bytes, contains.
Evidence that something keeps happening (B-346):
  {"id": "f1", "what": "the nightly backup ran", "fresh": "backups/*.tar.gz", "expect": {"max_age_hours": 26}}
      the newest matching file is younger than max_age_hours and holds at least min_bytes (default 1); with
      "row_time": "at" the age is read from the last row of a JSONL file (that field: an ISO time or epoch seconds).
  {"id": "r1", "what": "the cron job wrote rows", "rows_since": "logs/job.jsonl", "expect": {"min": 1, "hours": 24}}
      at least min (default 1) new non-empty lines across the matching files since the baseline kept in status.json.
      With hours the baseline moves only once that window has passed, so a fast re-run cadence cannot fail a daily job.
  {"id": "p1", "what": "the TVs run main", "probe": "tv-version", "reach": "lan", "expect": {"ok": true}}
      runs the project's own committed .wheel/probes/NAME.py (no arguments, stripped environment, a timeout), which
      prints one JSON line {"ok": true|false, "reading": "plain words"}. reach is local (default), lan or net; a lan or
      net probe runs only after the owner signs it off (scouts.py signoff), and a sign-off covers that exact probe file.
Every check may also carry level (light, the default: a cheap evidence read; deep: tests, probes, the network) and fix
(a command or a lug template, shown with every failure).
Only read-only commands run: ls cat head tail wc grep stat du find test diff echo, read-only git (log status diff rev-list
rev-parse ls-files count-objects show branch worktree list describe shortlog for-each-ref tag --list), and the project's own
test runners (bun test, pytest, python3 -m pytest|unittest). No absolute paths, no .., no env or key files, no shell.
A result never stores command output, only whether the expected outcome held and a short plain reason.

Usage (python3 .wheel/hooks/scouts.py ...):
  scouts.py [--root P] list                            the scouts with their last result
  scouts.py [--root P] run [NAME] [--record] [--open-lugs [--lug-all] --by WHO] [--json] [--level light|deep]
                                                       run one scout or all; --record keeps status.json; --open-lugs reports
                                                       each break once (B-347): a blocker scout opens a maintenance lug (class
                                                       maintain, in the keep-healthy initiative), a normal one sends one notice
                                                       from watchman to this project's inbox per outage and a cleared reply when
                                                       it passes again; --lug-all opens a lug for every break instead.
                                                       Backpressure (B-358): while a watchman notice sits unread a further
                                                       normal break folds into it, and while 3 scout lugs sit unclaimed a
                                                       further normal break waits for a lug; a blocker always breaks through.
                                                       Exit 1 when any scout fails.
                                                       --level light runs only the light checks (deep, the default: all).
  scouts.py [--root P] write FILE.json --advisor NAME  write or update a scout from a spec file (validated first)
  scouts.py [--root P] signoff NAME --who WHO          the owner lets this scout's lan/net probes run, as their files are now
Stdlib only."""
import argparse, datetime, glob, hashlib, importlib.util, json, os, re, subprocess, sys, time

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
PROBE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")
PROBES = os.path.join(".wheel", "probes")
KINDS = ("cmd", "file", "fresh", "rows_since", "probe")
REACH = ("local", "lan", "net")
LEVELS = ("light", "deep")
EXPECT_KEYS = {"file": {"exists", "min_bytes", "max_bytes", "contains"},
               "cmd": {"exit", "stdout_contains", "stdout_not_contains", "stdout_regex", "number", "lines"},
               "fresh": {"max_age_hours", "min_bytes", "row_time"},
               "rows_since": {"min", "hours"},
               "probe": {"ok"}}
CHECK_KEYS = ("id", "what") + KINDS + ("reach", "expect", "level", "fix")


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


def _num(v, low=0, allow_zero=False):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and (v >= low if allow_zero else v > low)


def check_problem(c):
    if not isinstance(c, dict):
        return "a check is an object"
    if not re.match(r"^[a-z0-9_-]{1,20}$", str(c.get("id") or "")):
        return "check id must be 1-20 of a-z 0-9 _ -"
    cid = c["id"]
    if not str(c.get("what") or "").strip():
        return "check %s needs a plain 'what'" % cid
    exp = c.get("expect")
    if not isinstance(exp, dict) or not exp:
        return "check %s needs an expect" % cid
    kinds = [k for k in KINDS if k in c]
    if len(kinds) != 1:
        return "check %s needs exactly one of %s" % (cid, ", ".join(KINDS))
    kind = kinds[0]
    if not set(exp) <= EXPECT_KEYS[kind]:
        return "check %s: unknown expect for a %s check" % (cid, kind)
    if c.get("level", "light") not in LEVELS:
        return "check %s: level is light or deep" % cid
    if "fix" in c and (not isinstance(c["fix"], str) or not c["fix"].strip() or len(c["fix"]) > 300):
        return "check %s: fix is a command or lug template of at most 300 characters" % cid
    if "reach" in c and kind != "probe":
        return "check %s: only a probe has a reach" % cid
    if kind in ("file", "fresh", "rows_since"):
        f = c[kind]
        if not isinstance(f, str) or not f.strip() or BAD_CHARS.search(f) or SECRETISH.search(f):
            return "check %s: path not allowed" % cid
        if kind == "fresh":
            if not _num(exp.get("max_age_hours")):
                return "check %s: fresh needs max_age_hours above 0" % cid
            if "min_bytes" in exp and not _num(exp["min_bytes"], allow_zero=True):
                return "check %s: min_bytes is a number" % cid
            if "row_time" in exp and not re.match(r"^[A-Za-z0-9_]{1,40}$", str(exp["row_time"])):
                return "check %s: row_time names one field of the last row" % cid
        if kind == "rows_since":
            if "min" in exp and not (isinstance(exp["min"], int) and not isinstance(exp["min"], bool) and exp["min"] >= 1):
                return "check %s: min is a whole number of at least 1" % cid
            if "hours" in exp and not _num(exp["hours"]):
                return "check %s: hours is a number above 0" % cid
        return None
    if kind == "probe":
        if not PROBE_RE.match(str(c["probe"])):
            return "check %s: probe names a file .wheel/probes/NAME.py (NAME: 2-40 of a-z 0-9 _ -)" % cid
        if c.get("reach", "local") not in REACH:
            return "check %s: reach is local, lan or net" % cid
        if not isinstance(exp["ok"], bool):
            return "check %s: a probe expects ok true or false" % cid
        return None
    p = command_problem(c["cmd"])
    if p:
        return "check %s: %s" % (cid, p)
    n = exp.get("number")
    if n is not None:
        try:
            re.compile(n["regex"])
        except Exception:  # noqa: BLE001
            return "check %s: number needs a valid regex with one group" % cid
        if not any(k in n for k in ("min", "max", "equals")):
            return "check %s: number needs min, max or equals" % cid
    if exp.get("stdout_regex"):
        try:
            re.compile(exp["stdout_regex"])
        except re.error:
            return "check %s: stdout_regex is not valid" % cid
    return None


def validate(spec):
    """(clean spec, problems). The clean spec keeps only the known fields (signed_off included: write_scout decides
    whether a sign-off may be kept)."""
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
             "checks": [{k: c[k] for k in CHECK_KEYS if k in c} for c in checks]}
    if isinstance(spec.get("signed_off"), dict):
        clean["signed_off"] = spec["signed_off"]
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


def _matches(root, pattern):
    """The regular files under root that the path or glob names (never outside the project)."""
    hits = glob.glob(os.path.join(root, pattern)) if glob.has_magic(pattern) else [os.path.join(root, pattern)]
    return [h for h in hits if os.path.isfile(h) and _within(root, os.path.relpath(h, root))]


def _parse_time(v):
    """Epoch seconds from an ISO time (Z or an offset; no zone means UTC) or a number, or None."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v / 1000 if v > 1e11 else v)
    if not isinstance(v, str) or not v.strip():
        return None
    t = v.strip().replace("Z", "+00:00")
    try:
        d = datetime.datetime.fromisoformat(t)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone.utc)
    return d.timestamp()


def _last_row(path, limit=1_000_000):
    """The last non-empty line of a file as a dict, or None (reads at most the last MB)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - limit))
            lines = [x for x in f.read().decode("utf-8", "replace").splitlines() if x.strip()]
    except OSError:
        return None
    try:
        row = json.loads(lines[-1]) if lines else None
    except ValueError:
        return None
    return row if isinstance(row, dict) else None


def _hours(sec):
    return "%.1f h" % (sec / 3600.0)


def check_fresh(root, c, now):
    exp, pat = c["expect"], c["fresh"]
    files = _matches(root, pat)
    if not files:
        return False, "%s has no file" % pat
    newest = max(files, key=os.path.getmtime)
    rel = os.path.relpath(newest, root)
    size = os.path.getsize(newest)
    least = exp.get("min_bytes", 1)       # not empty by default; 0 allows a touched marker file
    if size < least:
        return False, "%s is %d bytes, less than %d" % (rel, size, least)
    if exp.get("row_time"):
        row = _last_row(newest)
        if row is None:
            return False, "%s has no readable last row" % rel
        t = _parse_time(row.get(exp["row_time"]))
        if t is None:
            return False, "the last row of %s has no time in %s" % (rel, exp["row_time"])
        what = "the last row of %s" % rel
    else:
        t, what = os.path.getmtime(newest), rel
    age = now - t
    if age > exp["max_age_hours"] * 3600:
        return False, "%s is %s old, more than %g h" % (what, _hours(age), exp["max_age_hours"])
    return True, "ok"


def _count_rows(path):
    n = 0
    try:
        with open(path, "rb") as f:
            for line in f:
                if line.strip():
                    n += 1
    except OSError:
        pass
    return n


def check_rows_since(root, c, now, rows):
    """rows is this scout's {check id: {count, at}} baseline record (updated in place)."""
    exp, pat = c["expect"], c["rows_since"]
    files = _matches(root, pat)
    if not files:
        return False, "%s has no file" % pat
    count = sum(_count_rows(f) for f in files)
    base = rows.get(c["id"]) if isinstance(rows.get(c["id"]), dict) else None
    want = int(exp.get("min", 1))
    if base is None:
        rows[c["id"]] = {"count": count, "at": now_iso(now)}
        return True, "baseline set at %d row(s)" % count
    since = _parse_time(base.get("at")) or now
    if exp.get("hours") and now - since < exp["hours"] * 3600:
        return True, "window open: %d new row(s) after %s of %g h" % (max(0, count - int(base.get("count") or 0)), _hours(now - since), exp["hours"])
    prev = int(base.get("count") or 0)
    new = count - prev if count >= prev else count     # the file shrank (rotated): every row now counts as new
    rows[c["id"]] = {"count": count, "at": now_iso(now)}
    if new < want:
        return False, "%d new row(s) in %s since %s, fewer than %d" % (new, pat, base.get("at") or "the last run", want)
    return True, "ok"


def probe_path(root, name):
    return os.path.join(root, PROBES, name + ".py")


def probe_sha(root, name):
    try:
        with open(probe_path(root, name), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def check_probe(root, c, signed_off):
    name, reach = c["probe"], c.get("reach", "local")
    path = probe_path(root, name)
    if not _within(root, os.path.join(PROBES, name + ".py")) or not os.path.isfile(path):
        return False, "probe file .wheel/probes/%s.py is missing" % name
    if reach != "local":
        signed = ((signed_off or {}).get("probes") or {}).get(name)
        if not signed:
            return False, "probe %s reaches the %s and the owner has not signed it off (scouts.py signoff)" % (name, reach)
        if signed != probe_sha(root, name):
            return False, "probe %s changed since the owner signed it off; it needs a new sign-off" % name
    try:
        r = subprocess.run([sys.executable, "-B", path], cwd=root, capture_output=True, text=True, timeout=120,
                           stdin=subprocess.DEVNULL, env=_env())
    except subprocess.TimeoutExpired:
        return False, "probe %s timed out" % name
    except OSError as e:
        return False, "probe %s could not run (%s)" % (name, str(e)[:60])
    lines = [x for x in (r.stdout or "").splitlines() if x.strip()]
    try:
        out = json.loads(lines[-1]) if lines else None
    except ValueError:
        out = None
    if not isinstance(out, dict) or not isinstance(out.get("ok"), bool):
        return False, "probe %s exited %d without a JSON line {ok, reading}" % (name, r.returncode)
    reading = " ".join(str(out.get("reading") or "").split())[:120]
    if out["ok"] != c["expect"]["ok"]:
        return False, "probe %s: %s" % (name, reading or ("not ok" if c["expect"]["ok"] else "ok, expected not ok"))
    return True, reading or "ok"


def run_check(root, c, ctx=None):
    """(ok, plain reason). Never raises; never keeps command output. ctx: {now (epoch), rows (this scout's rows_since
    baselines, updated in place), signed_off (the scout's owner sign-off)}."""
    ctx = ctx if ctx is not None else {}
    now = ctx.get("now") or time.time()
    exp = c["expect"]
    try:
        if "fresh" in c:
            return check_fresh(root, c, now)
        if "rows_since" in c:
            return check_rows_since(root, c, now, ctx.setdefault("rows", {}))
        if "probe" in c:
            return check_probe(root, c, ctx.get("signed_off"))
    except Exception as e:  # noqa: BLE001  (a check never breaks the run)
        return False, "the check could not run (%s)" % str(e)[:60]
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


def run_scout(root, name, record=False, at=None, level="deep"):
    """Run one scout. Returns {name, advisor, ok, checks: [{id, what, ok, why, level, fix?}], was_ok, caught, level}.
    'caught' is true when it fails now and either passed last time or never ran (a new break, or a baseline that already
    fails). With record the status.json is updated (rows_since baselines included). level light runs only light checks."""
    sc = load_scout(root, name) or {}
    spec, probs = validate(sc)
    st = status_of(root, name)
    if spec is None:
        res = {"name": name, "advisor": sc.get("advisor"), "ok": False, "checks": [{"id": "-", "what": "scout.json", "ok": False,
               "why": "invalid scout: " + "; ".join(probs)[:200]}]}
    else:
        rows = []
        ctx = {"now": at if at is not None else time.time(), "signed_off": spec.get("signed_off"),
               "rows": json.loads(json.dumps(st.get("rows") or {}))}
        for c in spec["checks"]:
            lvl = c.get("level", "light")
            if level == "light" and lvl != "light":
                continue
            ok, why = run_check(root, c, ctx)
            row = {"id": c["id"], "what": c["what"], "ok": ok, "why": why, "level": lvl}
            if c.get("fix"):
                row["fix"] = c["fix"]
            rows.append(row)
        res = {"name": name, "advisor": sc.get("advisor"), "ok": all(r["ok"] for r in rows), "checks": rows}
        if len(rows) < len(spec["checks"]):
            res["partial"] = True                 # a light run skipped deep checks: a pass here cannot clear a notice
        if ctx["rows"]:
            res["_rows"] = ctx["rows"]
    res["severity"] = (spec or {}).get("severity", "normal")
    res["level"] = level
    new_rows = res.pop("_rows", None)
    res["was_ok"] = st.get("last_ok")
    res["caught"] = (not res["ok"]) and st.get("last_ok") is not False
    if record:
        st.update(last_run=now_iso(at), last_ok=res["ok"], runs=int(st.get("runs") or 0) + 1,
                  fails=0 if res["ok"] else int(st.get("fails") or 0) + 1,
                  catches=int(st.get("catches") or 0) + (1 if res["caught"] else 0),
                  last_why=[r["why"] for r in res["checks"] if not r["ok"]][:4])
        if new_rows is not None:
            st["rows"] = new_rows
        st.setdefault("lug", None)
        jdump(os.path.join(scout_dir(root, name), "status.json"), st)
    return res


def run_all(root, record=False, at=None, only=None, level="deep"):
    return [run_scout(root, n, record, at, level) for n in names(root) if not only or n == only]


# ---------- writing ----------
def readme_text(spec, advisor, created):
    L = ["# Scout: %s" % spec["name"], "",
         "Written by the %s advisor on %s. %s" % (advisor, created[:10], spec["purpose"]), "",
         "Re-run it with no model: `python3 .wheel/hooks/scouts.py run %s --record`. When the wake re-runs it, a break "
         "sends one notice to the project's inbox (a blocker opens a maintenance lug in the keep-healthy initiative), and a "
         "cleared message follows when it passes again." % spec["name"], "", "## Checks and the outcome each expects", ""]
    for c in spec["checks"]:
        if "cmd" in c:
            what = "`%s`" % " ".join(c["cmd"])
        elif "probe" in c:
            what = "probe `.wheel/probes/%s.py`, reach %s" % (c["probe"], c.get("reach", "local"))
        else:
            kind = next(k for k in ("file", "fresh", "rows_since") if k in c)
            what = {"file": "file", "fresh": "freshness of", "rows_since": "new rows in"}[kind] + " `%s`" % c[kind]
        L.append("- **%s** (%s, %s): %s. Expects %s.%s" % (c["id"], what, c.get("level", "light"), c["what"],
                 json.dumps(c["expect"], sort_keys=True), " Fix: %s" % c["fix"] if c.get("fix") else ""))
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
    clean.pop("signed_off", None)                 # a spec cannot sign itself off: only `scouts.py signoff` (the owner) can
    if isinstance((old or {}).get("signed_off"), dict):
        clean["signed_off"] = old["signed_off"]   # the probe-file hashes keep it honest when a probe changes
    if old and all(old.get(k) == clean.get(k) for k in ("purpose", "severity", "checks")):
        return clean["name"], "unchanged", []
    full = dict(clean, advisor=advisor, created=(old or {}).get("created") or stamp, updated=stamp)
    jdump(os.path.join(d, "scout.json"), full)
    with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme_text(clean, advisor, full["created"]))
    return clean["name"], "updated" if old else "created", []


def signoff(root, name, who, at=None):
    """The owner lets this scout's lan and net probes run, as their files are now. Returns (ok, plain note)."""
    sc = load_scout(root, name)
    spec, probs = validate(sc or {})
    if spec is None:
        return False, "scout %s is missing or invalid: %s" % (name, "; ".join(probs)[:160])
    if not str(who or "").strip():
        return False, "say who signs off (--who)"
    far = [c for c in spec["checks"] if "probe" in c and c.get("reach", "local") != "local"]
    if not far:
        return False, "scout %s has no lan or net probe to sign off" % name
    probes = {}
    for c in far:
        sha = probe_sha(root, c["probe"])
        if sha is None:
            return False, "probe file .wheel/probes/%s.py is missing" % c["probe"]
        probes[c["probe"]] = sha
    sc["signed_off"] = {"who": who.strip()[:80], "at": now_iso(at), "probes": probes}
    jdump(os.path.join(scout_dir(root, name), "scout.json"), sc)
    return True, "signed off %s: %s may reach beyond this machine" % (name, ", ".join(sorted(probes)))


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
            "--reason", ("scout %s failed: %s" % (name, "; ".join("%s: %s%s" % (c["id"], c["why"], " (fix: %s)" % c["fix"] if c.get("fix") else "")
                                                                 for c in bad)))[:400], "--by", by]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        return None, "could not open a lug for scout %s: %s" % (name, (r.stderr or r.stdout).strip()[:160])
    lug = r.stdout.split()[0]
    st.update(lug=lug)
    jdump(os.path.join(scout_dir(root, name), "status.json"), st)
    return lug, "scout %s broke: opened %s%s" % (name, lug, "" if signed else " (proposed: the keep-healthy initiative has no sign-off)")


# ---------- a break becomes an inbox notice (B-347) ----------
def msg_mod():
    """The kit's msg.py beside this file, or None where the project has no message part (P-022) installed."""
    path = os.path.join(HERE, "msg.py")
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location("wheel_kit_msg_scouts", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _set_status(root, name, **kw):
    st = status_of(root, name)
    st.update(kw)
    jdump(os.path.join(scout_dir(root, name), "status.json"), st)


def _lug_open(root, lug):
    if not lug:
        return False
    try:
        bl = backlog_mod()
        it = bl.load(root)["items"].get(lug)
        return bool(it) and it["status"] not in bl.CLOSED
    except Exception:  # noqa: BLE001  (an unreadable backlog must not hide the break: treat the lug as gone)
        return False


def send_notice(root, res, at=None, M=None, held_since=None):
    """One message lug to this project's own inbox for a scout that started failing. Returns (message id or None, note).
    held_since names the earlier notice this break waited behind (B-358 backpressure), so the reader knows it is not new."""
    M = M or msg_mod()
    name = res["name"]
    bad = [c for c in res["checks"] if not c["ok"]]
    lines = ["The %s scout %s failed on %s (severity %s)." % (res.get("advisor") or "an advisor's", name, now_iso(at), res.get("severity", "normal")), ""]
    for c in bad:
        lines.append("- %s, %s: %s%s" % (c["id"], c["what"], c["why"], ". Fix: %s" % c["fix"] if c.get("fix") else ""))
    if held_since:
        lines += ["", "This break waited behind the notice %s while that one sat unread, so it may be older than this message." % held_since]
    lines += ["", "Re-run it with `python3 .wheel/hooks/scouts.py run %s`. This is the one notice for this outage: a cleared "
              "message follows when the scout passes again." % name]
    m = M.make("watchman", M.this_project(root), ("Scout %s is failing: %s" % (name, (bad[0]["what"] if bad else "it failed")))[:110],
               "\n".join(lines), asks=["Fix what broke, or have an advisor update the scout if its expectation is out of date"],
               items=[{"id": name, "title": "Make scout %s pass again" % name,
                       "check": "`python3 .wheel/hooks/scouts.py run %s` prints PASS for every check and exits 0" % name}],
               refs=["scout:%s" % name], responsibility="responsible")
    M.deliver(m, {"path": root, "machine": None, "ssh": None})
    _set_status(root, name, notice=m["id"])
    return m["id"], "scout %s broke: notice %s sent to the inbox" % (name, m["id"])


def send_cleared(root, res, at=None, M=None):
    """The follow-up once a noticed scout passes again: a reply to the notice, which (if still unread) is marked done so
    nobody works on a break that has healed. Returns (message id, note)."""
    M = M or msg_mod()
    name = res["name"]
    first = status_of(root, name).get("notice")
    m = M.make("watchman", M.this_project(root), "Scout %s passes again" % name,
               "The scout %s passes every check again on %s. The notice %s needs no more work." % (name, now_iso(at), first),
               reply_to=first, refs=["scout:%s" % name])
    M.deliver(m, {"path": root, "machine": None, "ssh": None})
    d = M.inbox_dir(root)
    if (M.state(d).get(first) or {}).get("state", "unread") == "unread":
        M.set_state(d, first, "done", "cleared by watchman: scout %s passes again (%s)" % (name, m["id"]))
    _set_status(root, name, notice=None)
    return m["id"], "scout %s passes again: cleared %s" % (name, m["id"])


# ---------- backpressure (B-358): no pile of reports while earlier ones wait ----------
LUG_CAP = 3          # unclaimed scout lugs at once; a further normal break waits (held) until one is taken or closed


def open_watch_notice(root, M):
    """The oldest unread watchman notice (a message with items, not a cleared reply) in this inbox, or None."""
    try:
        for m, st in M.messages(root):
            if st == "unread" and m.get("from") == "watchman" and m.get("items"):
                return m["id"]
    except Exception:  # noqa: BLE001  (an unreadable inbox applies no backpressure: the break is reported)
        return None
    return None


def unclaimed_scout_lugs(root):
    """Open scout lugs nobody has taken yet (proposed or ready, no live claim): the queue a further break would join."""
    try:
        bl = backlog_mod()
        items = bl.load(root)["items"].values()
        return [it["id"] for it in items if str(it.get("source") or "").startswith("scout:")
                and it["status"] in ("proposed", "ready") and not bl.live_claim(it)]
    except Exception:  # noqa: BLE001  (an unreadable backlog applies no cap)
        return []


def rerun(root, by=None, open_lugs=True, at=None, only=None, level="deep", lug_all=False):
    """Re-run every scout (no model), record the results and report each break once. Returns
    {ran, failed: [names], caught: [{scout, advisor}], lugs: [ids], notices: [ids], cleared: [ids], folded: [{scout, into}],
    held: [names], notes: [...], results: [...]}.
    With open_lugs a blocker scout opens a maintenance lug (open_break_lug); a normal one sends one inbox notice per outage
    (its id kept in status.json "notice") and a cleared reply when it passes again, so nothing is reported twice. lug_all
    keeps the old path (a lug for every break); so does a project without msg.py. A normal scout whose earlier lug is
    still open sends no notice.
    Backpressure (B-358): while a watchman notice sits unread, a further normal break sends nothing and is kept as folded
    into it (status.json "folded"); it sends its own notice once that one is read or cleared. While LUG_CAP scout lugs sit
    unclaimed, a further normal break opens no lug and is kept as held. A blocker always breaks through. Passes are handled
    before breaks, so a clear frees the queue in the same run."""
    out = {"ran": 0, "failed": [], "caught": [], "lugs": [], "notices": [], "cleared": [], "folded": [], "held": [], "notes": [], "results": []}
    M = msg_mod() if open_lugs and not lug_all else None
    results = run_all(root, record=True, at=at, only=only, level=level)
    out["results"] = results
    out["ran"] = len(results)
    for res in [r for r in results if r["ok"]]:
        st = status_of(root, res["name"])
        if open_lugs and (st.get("folded") or st.get("held")) and not res.get("partial"):
            _set_status(root, res["name"], folded=None, held=None)
            out["notes"].append("scout %s passes again before its break was reported" % res["name"])
        if open_lugs and st.get("notice") and not res.get("partial") and M:
            try:
                mid, note = send_cleared(root, res, at, M)
                out["cleared"].append(mid)
            except (SystemExit, OSError, ValueError) as e:
                note = "scout %s passes again, but the cleared message failed: %s" % (res["name"], str(e)[:120])
            out["notes"].append(note)
    for res in [r for r in results if not r["ok"]]:
        name = res["name"]
        st = status_of(root, name)
        out["failed"].append(name)
        if res["caught"]:
            out["caught"].append({"scout": name, "advisor": res.get("advisor")})
        if not open_lugs:
            continue
        blocker = res.get("severity") == "blocker"
        if M and not blocker:
            if st.get("notice"):
                continue                                            # one notice per outage
            if _lug_open(root, st.get("lug")):
                out["notes"].append("lug %s already open for scout %s" % (st["lug"], name))
                continue
            waiting = open_watch_notice(root, M)
            if waiting:
                if st.get("folded") != waiting:
                    _set_status(root, name, folded=waiting)
                    out["notes"].append("scout %s broke: folded into the unread notice %s (its own notice follows once that one is read)" % (name, waiting))
                out["folded"].append({"scout": name, "into": waiting})
                continue
            try:
                mid, note = send_notice(root, res, at, M, held_since=st.get("folded"))
                _set_status(root, name, folded=None)
                out["notices"].append(mid)
                out["notes"].append(note)
                continue
            except (SystemExit, OSError, ValueError) as e:
                out["notes"].append("scout %s: the inbox notice failed (%s), so a lug opens instead" % (name, str(e)[:120]))
        if not blocker and not _lug_open(root, st.get("lug")):
            queue = unclaimed_scout_lugs(root)
            if len(queue) >= LUG_CAP:
                _set_status(root, name, held="%s: %d scout lugs unclaimed (%s)" % (now_iso(at), len(queue), ", ".join(sorted(queue))))
                out["held"].append(name)
                out["notes"].append("scout %s broke: no lug yet, %d scout lugs sit unclaimed (%s); it opens once one is taken"
                                    % (name, len(queue), ", ".join(sorted(queue))))
                continue
        lug, note = open_break_lug(root, res, by)
        out["notes"].append(note)
        if lug:
            _set_status(root, name, held=None)
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
    r.add_argument("--lug-all", action="store_true")
    r.add_argument("--by")
    r.add_argument("--json", action="store_true")
    r.add_argument("--level", choices=LEVELS + ("all",), default="deep")
    w = sub.add_parser("write")
    w.add_argument("file")
    w.add_argument("--advisor", required=True)
    so = sub.add_parser("signoff")
    so.add_argument("name")
    so.add_argument("--who", required=True)
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
    if a.cmd == "signoff":
        ok, note = signoff(root, a.name, a.who)
        print(note)
        return 0 if ok else 1
    level = "light" if a.level == "light" else "deep"
    if a.name and a.name not in names(root):
        print("no scout named %s" % a.name)
        return 2
    if a.open_lugs:
        res = rerun(root, a.by, True, only=a.name, level=level, lug_all=a.lug_all)
        results = res["results"]
        for note in res["notes"]:
            print(note)
    else:
        results = run_all(root, a.record, only=a.name, level=level)
    if a.json:
        print(json.dumps(results, indent=1))
    else:
        for x in results:
            print("%s %s" % ("PASS" if x["ok"] else "FAIL", x["name"]))
            for c in x["checks"]:
                print("  %s %s: %s" % ("PASS" if c["ok"] else "FAIL", c["id"], c["what"] if c["ok"] else c["why"]))
                if not c["ok"] and c.get("fix"):
                    print("    fix: %s" % c["fix"])
    return 0 if all(x["ok"] for x in results) else 1


if __name__ == "__main__":
    sys.exit(main())
