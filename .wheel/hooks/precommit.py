#!/usr/bin/env python3
"""Commit-time gate (W-160): refuse the mistakes that keep recurring, at the moment they are made.

  precommit.py [--hub]           run as a git pre-commit hook on the staged files (exit 1 = commit refused)
  precommit.py selftest          prove the gate in a scratch repository (the kit canary runs this)
  precommit.py install [--hub] [ROOT]   put the hook in ROOT's git hooks (chains to any existing pre-commit hook)

What it checks, on the staged files only (added lines, so it stays fast):
  F-004  secret-shaped text, with the reviewed allowlist (hub: audits/secrets-allowlist.json, project:
         .wheel/secrets-allowlist.json; entries are path + type + sha256 of the line text, same as the hub's push gate)
  F-002  residue: __pycache__, .pytest_cache, bytecode and other cache folders
  F-009  folders or files whose name is a command-line flag (a tool treated --help as a folder name)
  F-003  (--hub only) personal detail (identity term, email, absolute home path) in staged files under seed/ or tools/kit/
The refusal names the file, the failure kind and the fix. It never prints a matched value. Stdlib only; no hub path is
needed in a project (the hub's fuller scanner is used when WHEEL_HUB or ~/.config/wheel/hub-path points at one).
A bug in the gate itself fails open (prints a warning, lets the commit through) so it can never lock a project."""
import hashlib, importlib.util, json, os, re, subprocess, sys, tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))

RESIDUE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis", ".ipynb_checkpoints"}
RESIDUE_EXT = (".pyc", ".pyo")

# Written with character classes so this file does not match its own scan.
BUILTIN = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("anthropic-key", re.compile(r"sk[-]ant[-]")),
    ("openai-style-key", re.compile(r"sk[-][A-Za-z0-9]{20,}")),
    ("github-token", re.compile(r"\b(gh[pous]_[A-Za-z0-9]{20,}|github[_]pat[_])")),
    ("slack-token", re.compile(r"xox[bpas][-]")),
    ("aws-key-id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("google-api-key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}")),
    ("stripe-key", re.compile(r"\b[sr]k_(live|test)_[0-9A-Za-z]{20,}")),
]
ASSIGN = re.compile(r"""(password|passwd|secret|api_key|apikey|token)\s*[:=]\s*(['"])([^\s'"]{8,})\2""", re.I)
PLACEHOLDER = re.compile(r"(^test[-_]|[-_]test$|your|example|placeholder|changeme|invalid|fake|mock|xxxx|dummy|sample|todo|redacted|<|\$\{|\{\{)", re.I)
SKIP_SCAN = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "uv.lock", "go.sum", "bun.lock"}
EMPTY_SHA = hashlib.sha256(b"").hexdigest()


def run(args, cwd=None, inp=None):
    r = subprocess.run(args, cwd=cwd, input=inp, capture_output=True, text=True, errors="replace")
    return r.returncode, r.stdout, r.stderr


def toplevel(cwd=None):
    rc, out, _ = run(["git", "rev-parse", "--show-toplevel"], cwd)
    return out.strip() if rc == 0 else None


# ---------------------------------------------------------------- staged content

def staged_paths(cwd):
    rc, out, _ = run(["git", "-c", "core.quotepath=off", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], cwd)
    return [p for p in out.split("\0") if p] if rc == 0 else []


def added_lines(cwd):
    """{path: [(new line number, text)]} for the lines the commit adds."""
    rc, out, _ = run(["git", "-c", "core.quotepath=off", "diff", "--cached", "-U0", "--no-color", "--no-ext-diff",
                      "--diff-filter=ACMR"], cwd)
    res, path, header, n = {}, None, False, 0
    if rc != 0:
        return res
    for l in out.split("\n"):
        if l.startswith("diff --git "):
            header, path = True, None
        elif header and l.startswith("+++ "):
            p = l[4:].rstrip("\t")
            path = p[2:] if p.startswith("b/") else None
        elif l.startswith("@@"):
            header = False
            m = re.match(r"@@ -\S+ \+(\d+)", l)
            n = int(m.group(1)) if m else 0
        elif not header and path and l.startswith("+"):
            res.setdefault(path, []).append((n, l[1:]))
            n += 1
    return res


# ---------------------------------------------------------------- the checks

def residue(paths):
    out = []
    for p in paths:
        parts = p.split("/")
        if set(parts[:-1]) & RESIDUE_DIRS or parts[-1] in RESIDUE_DIRS or p.endswith(RESIDUE_EXT):
            out.append((p, 0, "F-002", "cache residue (%s)" % next((x for x in parts if x in RESIDUE_DIRS), "bytecode"),
                        "unstage it (git rm --cached -r PATH), delete it, and run with PYTHONDONTWRITEBYTECODE=1 or python3 -B; add it to .gitignore"))
        elif any(x.startswith("-") for x in parts):
            out.append((p, 0, "F-009", "a name that is a command-line flag",
                        "a tool took a flag as a folder name: delete it (git rm --cached -r PATH), and check a tool prints usage before you run it with a flag"))
    return out


def load_scanner(top, hub):
    cands = [os.path.join(top, "tools", "secrets_scan.py")] if hub else []
    h = os.environ.get("WHEEL_HUB")
    if not h and not hub:
        try:
            h = open(os.path.expanduser("~/.config/wheel/hub-path")).read().strip()
        except OSError:
            h = ""
    if h:
        cands.append(os.path.join(h, "tools", "secrets_scan.py"))
    for p in cands:
        if os.path.isfile(p):
            try:
                spec = importlib.util.spec_from_file_location("wheel_precommit_scan", p)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "scan_text") and hasattr(mod, "name_flags"):
                    return mod
            except Exception:  # noqa: BLE001
                pass
    return None


def builtin_scan(text):
    found = set()
    for n, line in enumerate(text.splitlines(), 1):
        line = line[:5000]
        hit = False
        for typ, rx in BUILTIN:
            if rx.search(line):
                found.add((n, typ))
                hit = True
        if not hit:
            for m in ASSIGN.finditer(line):
                if not PLACEHOLDER.search(m.group(3)):
                    found.add((n, "assigned-secret"))
                    break
    return sorted(found)


def builtin_name_flag(path):
    b = os.path.basename(path).lower()
    if b in (".env.example", ".env.template", ".env.sample") or ".template" in b:
        return None
    if b == ".env" or b.startswith(".env."):
        return "env-file"
    if b.endswith((".pem", ".key")) or b.startswith("id_rsa"):
        return "key-file"
    return None


def read_allow(path):
    try:
        return {(e["path"], e["type"], e["line_sha256"]) for e in json.load(open(path))["entries"]}
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def secrets(top, paths, lines, hub, allow_path):
    mod = load_scanner(top, hub)
    allow = read_allow(allow_path)
    out = []
    for p in paths:
        if os.path.basename(p) in SKIP_SCAN or "node_modules/" in "/" + p:
            continue
        nf = mod.name_flags(p) if mod else builtin_name_flag(p)
        if nf and (p, nf, EMPTY_SHA) not in allow:
            out.append((p, 0, "F-004", "a file name that looks like a secret (%s)" % nf,
                        "do not commit it; keep it outside the repository or in .gitignore"))
        got = lines.get(p) or []
        if not got:
            continue
        text = "\n".join(t for _, t in got)
        if mod:
            session = hasattr(mod, "is_session_name") and mod.is_session_name(p)
            hits = mod.scan_text(text, bool(session))
        else:
            hits = builtin_scan(text)
        for idx, typ in hits:
            line_text = got[idx - 1][1] if 0 < idx <= len(got) else ""
            sha = hashlib.sha256(line_text.encode()).hexdigest()
            if (p, typ, sha) in allow:
                continue
            ln = got[idx - 1][0] if 0 < idx <= len(got) else 0
            out.append((p, ln, "F-004", "secret-shaped text (%s)" % typ,
                        "remove it; build test values at runtime (prefix + repeated filler) and never quote a real prefix. If it is a reviewed mention, "
                        "add {path, type: %s, line_sha256: %s, reason} to %s" % (typ, sha, os.path.relpath(allow_path, top))))
    return out


def identity_terms(top):
    """Names and hostname from .local/identity.json of the main checkout (a worktree has no .local of its own)."""
    rc, common, _ = run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], top)
    roots = [top] + ([os.path.dirname(common.strip())] if rc == 0 and common.strip() else [])
    for r in roots:
        try:
            idn = json.load(open(os.path.join(r, ".local", "identity.json")))
            return [t for t in list(idn.get("names", [])) + [idn.get("hostname", "")] if t]
        except (OSError, ValueError, AttributeError):
            continue
    return []


def personal(top, paths, lines):
    shared = [p for p in paths if p.startswith(("seed/", "tools/kit/"))]
    if not shared:
        return []
    sys.path.insert(0, os.path.join(top, "tools"))
    try:
        import wheel  # the hub's own definition of personal detail
    except Exception:  # noqa: BLE001
        return []
    finally:
        sys.path.pop(0)
    terms = identity_terms(top)
    out = []
    for p in shared:
        for ln, t in lines.get(p) or []:
            kinds = []
            if any(re.search(r"\b%s\b" % re.escape(x), t, re.I) for x in terms):
                kinds.append("identity term")
            if wheel.ABS_RE.search(t):
                kinds.append("absolute path")
            if wheel.EMAIL_RE.search(t):
                kinds.append("email")
            for k in kinds:
                out.append((p, ln, "F-003", "personal detail in a shared file (%s)" % k,
                            "shared files (seed/, tools/kit/) hold no name, email, hostname or home path: use a non-email test identity, a relative path, or build it at runtime"))
    return out


def check(cwd=None, hub=False):
    top = toplevel(cwd)
    if not top:
        return []
    paths = staged_paths(top)
    if not paths:
        return []
    lines = added_lines(top)
    allow_path = os.path.join(top, "audits", "secrets-allowlist.json") if hub else os.path.join(top, ".wheel", "secrets-allowlist.json")
    probs = residue(paths)
    probs += secrets(top, paths, lines, hub, allow_path)
    if hub:
        probs += personal(top, paths, lines)
    return probs


def report(probs):
    n = len(probs)
    msg = ["pre-commit refused: %d problem%s (nothing was committed)" % (n, "" if n == 1 else "s")]
    for p, ln, fid, what, fix in probs[:20]:
        msg.append("  %s%s [%s] %s" % (p, ":%d" % ln if ln else "", fid, what))
        msg.append("    fix: " + fix)
    if n > 20:
        msg.append("  ... and %d more" % (n - 20))
    return "\n".join(msg)


# ---------------------------------------------------------------- installing the hook

BEGIN = "# >>> wheel pre-commit (managed block) >>>"
END = "# <<< wheel pre-commit <<<"
CHAIN = "pre-commit.wheel-chain"


def block(script_rel, args=""):
    return "\n".join([
        BEGIN,
        '_wheel_top="$(git rev-parse --show-toplevel 2>/dev/null)"',
        'if [ -n "$_wheel_top" ] && [ -f "$_wheel_top/%s" ] && command -v python3 >/dev/null 2>&1; then' % script_rel,
        '  python3 -B "$_wheel_top/%s"%s || exit 1' % (script_rel, args),
        "fi",
        END]) + "\n"


def hook_dir(root):
    top = toplevel(root) or root
    rc, hp, _ = run(["git", "config", "--get", "core.hooksPath"], top)
    hp = hp.strip()
    if rc == 0 and hp:
        p = os.path.normpath(os.path.join(top, os.path.expanduser(hp)))
        if os.path.basename(p) == "_" and os.path.basename(os.path.dirname(p)) == ".husky":
            return os.path.dirname(p)  # husky 9: the generated stubs in .husky/_ run .husky/<hook>
        return p
    rc, out, _ = run(["git", "rev-parse", "--path-format=absolute", "--git-path", "hooks"], top)
    return out.strip() if rc == 0 and out.strip() else os.path.join(top, ".git", "hooks")


def hook_paths(root):
    """[pre-commit, its chained copy]: relative to the work tree when they are tracked-file locations, else absolute."""
    top = os.path.realpath(toplevel(root) or root)
    d = hook_dir(root)
    out = []
    for name in ("pre-commit", CHAIN):
        p = os.path.join(d, name)
        rel = os.path.relpath(os.path.realpath(d), top)
        inside = not rel.startswith("..") and not rel.split(os.sep)[0] == ".git"
        out.append(os.path.join(rel, name) if inside else p)
    return out


def _is_shell(text):
    if not text.startswith("#!"):
        return True  # git runs a hook without a shebang through sh
    first = text.split("\n", 1)[0]
    return bool(re.search(r"(^|[ /])(ba|da|z|k)?sh(\s|$)", first))


def install_hook(root, script_rel, args=""):
    """Add the gate to root's pre-commit hook. Never overwrites: an existing hook keeps running (the block goes first in a
    shell hook; any other kind of hook is renamed beside it and run by a small wrapper). Idempotent. Returns a note."""
    d = hook_dir(root)
    os.makedirs(d, exist_ok=True)
    target, chain = os.path.join(d, "pre-commit"), os.path.join(d, CHAIN)
    blk = block(script_rel, args)
    if not os.path.exists(target):
        text = "#!/bin/sh\n" + blk
        note = "created"
    else:
        old = open(target, errors="replace").read()
        if BEGIN in old and END in old:
            a, b = old.index(BEGIN), old.index(END) + len(END)
            text = old[:a] + blk.rstrip("\n") + old[b:]
            note = "updated"
        elif _is_shell(old):
            if old.startswith("#!"):
                first, _, rest = old.partition("\n")
                text = first + "\n" + blk + rest
            else:
                text = blk + old
            note = "chained (shell hook kept)"
        else:
            if not os.path.exists(chain):
                os.rename(target, chain)
            text = "#!/bin/sh\n" + blk + 'exec "$(dirname "$0")/%s" "$@"\n' % CHAIN
            note = "chained (existing hook kept as %s)" % CHAIN
    if not os.path.exists(target) or open(target, errors="replace").read() != text:
        with open(target, "w") as f:
            f.write(text)
    if not os.access(target, os.X_OK):
        os.chmod(target, os.stat(target).st_mode | 0o111)
    return note


# ---------------------------------------------------------------- selftest

def selftest():
    """Returns a list of failure strings; empty = the gate works here."""
    fails = []
    me = os.path.abspath(__file__)
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t",
                   PYTHONDONTWRITEBYTECODE="1")

        def g(*a):
            return subprocess.run(["git"] + list(a), cwd=d, capture_output=True, text=True, env=env)
        g("init", "-q")
        os.makedirs(os.path.join(d, "x", "__pycache__"))
        with open(os.path.join(d, "x", "__pycache__", "a.pyc"), "w") as f:
            f.write("z")
        with open(os.path.join(d, "ok.txt"), "w") as f:
            f.write("fine\n")
        g("add", "ok.txt")
        if subprocess.run([sys.executable, me], cwd=d, capture_output=True, text=True, env=env).returncode != 0:
            fails.append("a clean commit was refused")
        g("add", "-f", "x/__pycache__/a.pyc")
        r = subprocess.run([sys.executable, me], cwd=d, capture_output=True, text=True, env=env)
        if r.returncode != 1 or "F-002" not in r.stderr:
            fails.append("a staged __pycache__ was not refused")
    return fails


def main(argv):
    hub = "--hub" in argv
    args = [a for a in argv if not a.startswith("--")]
    if args[:1] == ["selftest"]:
        fails = selftest()
        for f in fails:
            print("precommit selftest: " + f)
        return 1 if fails else 0
    if args[:1] == ["install"]:
        root = os.path.abspath(args[1]) if len(args) > 1 else os.getcwd()
        rel = "tools/kit/precommit.py" if hub else ".wheel/hooks/precommit.py"
        print("pre-commit hook %s in %s" % (install_hook(root, rel, " --hub" if hub else ""), hook_dir(root)))
        return 0
    if args:
        print("usage: precommit.py [--hub] | selftest | install [--hub] [ROOT]", file=sys.stderr)
        return 2
    try:
        probs = check(None, hub)
    except Exception as e:  # noqa: BLE001  (the gate must never lock a project)
        print("pre-commit gate skipped, it failed itself: %s: %s" % (type(e).__name__, str(e)[:120]), file=sys.stderr)
        return 0
    if probs:
        print(report(probs), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
