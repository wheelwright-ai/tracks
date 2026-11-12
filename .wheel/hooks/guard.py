#!/usr/bin/env python3
"""PreToolUse guard. Reads the hook JSON on stdin. For Bash commands it denies four kinds:
  1. discarding uncommitted work (git checkout -- / ., git restore without --staged, git clean -f),
  2. DROP DATABASE / DROP TABLE anywhere in the command (a quoted mention is blocked too, on purpose),
  3. plain rm of anything under the projects folder (WHEEL_GUARD_ROOT, default ~/projects); move it to the
     trash folder (WHEEL_TRASH, default ~/trash_bin) instead. Paths under /tmp are fine.
  4. switching branches (git checkout <branch>, git switch) in a project's main checkout.
  5. second spellings of the same losses (W-177): git reset --hard, checkout -f, switch --discard-changes, stash
     drop/clear, branch -D, find -delete / -exec rm, and history rewrites on the remote: push --force/-f/
     --force-with-lease/+refspec/--mirror/--delete; and --no-verify on commit or push (never skip hooks).
  6. writes to the guard's own files (W-177): .wheel/hooks/, .claude/settings*.json, .wheel/config.json and the secrets
     allowlists, by Edit/Write or by a shell write (cp, mv, tee, sed -i, redirect ...). The kit installs them; the
     owner can set WHEEL_KIT_OK=1 to lift this.
Wrappers are unwrapped before the rules run (W-177): bash/sh -c STRING, eval, env, timeout, nice, nohup, time, sudo,
command, exec, xargs, subshells ( ) and $( ) or backticks; before, only the first word of a segment was looked at.
For Edit/Write/MultiEdit/NotebookEdit it denies any file inside a project's main checkout outside .wheel/: the main
checkout stays on main, and sessions work in their own worktree (start one with wcl). A linked worktree is allowed.
The owner can set WHEEL_MAIN_OK=1 to lift rules 4 and the edit rule.
Everything else, and any malformed input, is allowed silently (exit 0, no output).
  guard.py test      run the fixtures (fixtures/guard_cases.jsonl and the main-checkout cases)"""
import json, os, re, shlex, subprocess, sys

sys.dont_write_bytecode = True
SPLIT = re.compile(r"&&|\|\||;|\||\n")
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
MAIN_REASON = ("this is the main checkout, which stays on main: start a session with wcl to get a worktree "
               "(or the owner sets WHEEL_MAIN_OK=1)")
PROTECTED = re.compile(r"(^|/)(\.wheel/hooks/|\.claude/settings(\.local)?\.json$|\.wheel/config\.json$|"
                       r"\.wheel/secrets-allowlist\.json$|audits/secrets-allowlist\.json$)")
PROTECTED_ANY = re.compile(r"\.wheel/hooks/|\.claude/settings(\.local)?\.json|\.wheel/config\.json|secrets-allowlist\.json")
PROTECT_REASON = ("this is one of the guard's own files (kit hooks, Claude settings, the project config or the secrets "
                  "allowlist): the kit installs them from the hub (tools/kit/sync.py); the owner can set WHEEL_KIT_OK=1")
WRITERS = {"cp", "mv", "tee", "truncate", "dd", "install", "ln", "chmod", "chown", "rm", "touch", "rsync", "patch"}
WRAP_SIMPLE = {"sudo", "command", "exec", "nohup", "time", "builtin", "unbuffer", "stdbuf"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))
    sys.exit(0)


def git_check(tok):
    """tok: tokens starting at 'git'. Return a reason or None."""
    i, n = 1, len(tok)
    while i < n and tok[i].startswith("-"):  # git -C dir / -c k=v / --no-pager
        i += 2 if tok[i] in ("-C", "-c") else 1
    if i >= n:
        return None
    sub, args = tok[i], tok[i + 1:]
    if sub == "checkout" and ("--" in args or "." in args):
        return "git checkout -- / . would discard uncommitted changes in the working tree. Run `git stash` first (it keeps them recoverable)."
    if sub == "restore":
        if "--staged" in args and "--worktree" not in args:
            return None
        return "git restore would discard uncommitted changes in the working tree. Run `git stash` first (it keeps them recoverable)."
    if sub == "clean":
        if any(a == "--force" or (re.match(r"-[A-Za-z]+$", a) and "f" in a) for a in args):
            return "git clean -f would delete untracked files for good. Run `git stash -u` first, or preview with `git clean -n`."
    if sub == "reset" and "--hard" in args:
        return "git reset --hard discards uncommitted changes. Commit or `git stash` first; to move a branch, ask the owner."
    if sub == "checkout" and ("-f" in args or "--force" in args):
        return "git checkout -f discards uncommitted changes. Run `git stash` first."
    if sub == "switch" and any(a in ("-f", "--force", "--discard-changes") for a in args):
        return "git switch --discard-changes / -f discards uncommitted changes. Run `git stash` first."
    if sub == "stash" and args[:1] and args[0] in ("drop", "clear"):
        return "git stash %s deletes stashed work. Ask the owner first." % args[0]
    if sub == "branch" and any(a in ("-D",) or (re.match(r"-[A-Za-z]+$", a) and "D" in a) for a in args):
        return "git branch -D deletes a branch even when its commits are not merged. Use `git branch -d` (it refuses unmerged work) or ask the owner."
    if sub in ("commit", "push", "merge", "rebase", "am", "cherry-pick") and "--no-verify" in args:
        return "--no-verify skips the project's hooks (the secret and trap checks). Never skip hooks: fix what they report."
    if sub == "commit" and "-n" in args:
        return "git commit -n skips the project's hooks (the secret and trap checks). Never skip hooks."
    if sub == "push":
        if any(a in ("-f", "--force", "--mirror", "--delete", "-d", "--prune") or a.startswith("--force-with-lease")
               or a.startswith("--force-if-includes") or (re.match(r"-[A-Za-z]+$", a) and "f" in a) for a in args):
            return "git push --force / --mirror / --delete rewrites or deletes history on the remote. Never force-push; ask the owner."
        if any(a.startswith("+") or (a.startswith(":") and len(a) > 1) for a in args):
            return "a +refspec forces the push and a :refspec deletes a remote branch. Never force-push; ask the owner."
    return None


def rm_check(tok, cwd):
    """tok: tokens starting at 'rm'. Return a reason or None."""
    root = os.path.realpath(os.path.expanduser(os.environ.get("WHEEL_GUARD_ROOT") or "~/projects"))
    trash = os.path.expanduser(os.environ.get("WHEEL_TRASH") or "~/trash_bin")
    moves, end_opts = [], False
    for a in tok[1:]:
        if not end_opts and a == "--":
            end_opts = True
            continue
        if not end_opts and a.startswith("-"):
            continue
        p = os.path.expandvars(os.path.expanduser(a))
        p = os.path.realpath(p if os.path.isabs(p) else os.path.join(cwd, p))
        if p == "/tmp" or p.startswith("/tmp/"):
            continue
        if p == root or p.startswith(root + os.sep):
            dest = os.path.join(trash, os.path.relpath(p, root))
            moves.append('mkdir -p "%s" && mv "%s" "%s"' % (os.path.dirname(dest), p, dest))
    if moves:
        return "rm inside the projects folder deletes for good. Move it to the trash folder instead:\n" + "\n".join(moves)
    return None


def find_check(tok, cwd):
    """find ... -delete or -exec rm under the projects folder deletes for good, like rm."""
    if "-delete" not in tok and not any(t in ("-exec", "-execdir", "-ok", "-okdir") and i + 1 < len(tok) and
                                         os.path.basename(tok[i + 1]) in ("rm", "shred", "unlink")
                                         for i, t in enumerate(tok)):
        return None
    starts = []
    for a in tok[1:]:
        if a.startswith("-") or a in ("(", "!", ")"):
            break
        starts.append(a)
    return rm_check(["rm"] + (starts or ["."]), cwd) and "find -delete / -exec rm inside the projects folder deletes for good. Move files to the trash folder instead."


def protected_write(seg, tok):
    """A shell write to one of the guard's own files (a redirect into one, or a writing command naming one)."""
    if os.environ.get("WHEEL_KIT_OK") == "1" or not PROTECTED_ANY.search(seg):
        return None
    if re.search(r">>?\s*['\"]?[^\s'\"]*(\.wheel/hooks/|\.claude/settings|\.wheel/config\.json|secrets-allowlist)", seg):
        return PROTECT_REASON
    name = os.path.basename(tok[0]) if tok else ""
    if name in WRITERS or (name in ("sed", "perl") and any(t == "-i" or t.startswith("-i") or t == "--in-place" for t in tok[1:])):
        targets = [t for t in tok[1:] if not t.startswith("-")]
        if any(PROTECTED_ANY.search(t) for t in (targets[-1:] if name in ("cp", "mv", "install", "ln", "rsync") else targets)):
            return PROTECT_REASON
    return None


def unwrap(tok):
    """Strip wrappers from a command's tokens. Returns (tokens, nested command strings to check as well)."""
    nested = []
    for _ in range(12):
        while tok and (re.match(r"^\w+=", tok[0]) or tok[0] in WRAP_SIMPLE):
            tok = tok[1:]
        if not tok:
            break
        name = os.path.basename(tok[0])
        if name == "\\rm" or tok[0] == "\\rm":
            tok = ["rm"] + tok[1:]
            break
        if name == "env":
            i = 1
            while i < len(tok) and (tok[i].startswith("-") or re.match(r"^\w+=", tok[i])):
                i += 2 if tok[i] in ("-u", "-C", "-S", "--unset", "--chdir") else 1
            tok = tok[i:]
        elif name in ("timeout", "nice", "ionice", "chrt", "taskset"):
            i = 1
            while i < len(tok) and tok[i].startswith("-"):
                i += 2 if tok[i] in ("-n", "-s", "-k", "--signal", "--kill-after", "-c", "-p") else 1
            if name in ("timeout", "chrt", "taskset") and i < len(tok):
                i += 1   # the duration, priority or mask
            tok = tok[i:]
        elif name == "xargs":
            i = 1
            while i < len(tok) and tok[i].startswith("-"):
                i += 2 if tok[i] in ("-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a") else 1
            tok = tok[i:]
        elif name in SHELLS and "-c" in tok[1:]:
            j = tok.index("-c")
            if j + 1 < len(tok):
                nested.append(tok[j + 1])
            return [], nested
        elif name == "eval":
            nested.append(" ".join(tok[1:]))
            return [], nested
        else:
            break
    return tok, nested


def split_unquoted(cmd):
    """Split on ; && || | and newlines outside quotes (cut 65 review: a commit message holding a separator and a
    destructive phrase was read as a second command)."""
    out, cur, q, i = [], [], None, 0
    while i < len(cmd):
        ch = cmd[i]
        if q:
            cur.append(ch)
            if ch == "\\" and q == '"' and i + 1 < len(cmd):
                cur.append(cmd[i + 1])
                i += 1
            elif ch == q:
                q = None
        elif ch in ("'", '"'):
            q = ch
            cur.append(ch)
        elif ch == "\\" and i + 1 < len(cmd):
            cur += [ch, cmd[i + 1]]
            i += 1
        elif cmd.startswith(("&&", "||"), i):
            out.append("".join(cur))
            cur = []
            i += 1
        elif ch in ";|\n":
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    out.append("".join(cur))
    return out


def segments(cmd):
    """The simple commands in a command line, including those inside $( ), backticks and ( ) subshells."""
    inner = re.findall(r"\$\(([^()]*)\)", cmd) + re.findall(r"`([^`]*)`", cmd)
    out = []
    for seg in split_unquoted(cmd) + [x for i in inner for x in split_unquoted(i)]:
        seg = seg.strip().lstrip("({").rstrip(")}").strip()
        if seg:
            out.append(seg)
    return out


def _git(cwd, *args):
    try:
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=10,
                           env=dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0"))
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def main_checkout(cwd):
    """The toplevel of cwd's repo when cwd is in a project's main checkout (git-dir equals git-common-dir), else None.
    A linked worktree, a non-repo and any git trouble give None."""
    if os.environ.get("WHEEL_MAIN_OK") == "1" or not os.path.isdir(cwd):
        return None
    top, gd, cd = _git(cwd, "rev-parse", "--show-toplevel"), _git(cwd, "rev-parse", "--git-dir"), _git(cwd, "rev-parse", "--git-common-dir")
    if not (top and gd and cd):
        return None
    gd = os.path.realpath(gd if os.path.isabs(gd) else os.path.join(cwd, gd))
    cd = os.path.realpath(cd if os.path.isabs(cd) else os.path.join(cwd, cd))
    return os.path.realpath(top) if gd == cd else None


def edit_check(ti, cwd):
    p = ti.get("file_path") or ti.get("notebook_path")
    if not isinstance(p, str) or not p:
        return None
    full0 = os.path.realpath(p if os.path.isabs(p) else os.path.join(cwd, p))
    if os.environ.get("WHEEL_KIT_OK") != "1" and PROTECTED.search(full0.replace(os.sep, "/")):
        return PROTECT_REASON
    top = main_checkout(cwd)
    if not top:
        return None
    full = os.path.realpath(p if os.path.isabs(p) else os.path.join(cwd, p))
    if full != top and full.startswith(top + os.sep):
        rel = os.path.relpath(full, top).replace(os.sep, "/")
        if not rel.startswith(".wheel/"):
            return MAIN_REASON
    return None


def switch_check(tok, cwd):
    """tok: tokens starting at 'git'. A branch switch in a main checkout, or None."""
    i, n = 1, len(tok)
    while i < n and tok[i].startswith("-"):
        if tok[i] == "-C" and i + 1 < n:
            d = os.path.expanduser(tok[i + 1])
            cwd = d if os.path.isabs(d) else os.path.join(cwd, d)
        i += 2 if tok[i] in ("-C", "-c") else 1
    if i >= n or tok[i] not in ("checkout", "switch"):
        return None
    args = tok[i + 1:]
    if tok[i] == "checkout" and ("--" in args or "." in args):
        return None  # handled (denied) by the discard rule
    top = main_checkout(cwd)
    if not top:
        return None
    target = [a for a in args if not a.startswith("-")]
    making = any(a in ("-b", "-B", "-c", "-C", "--orphan", "--create", "--force-create", "--detach", "-d") for a in args)
    if tok[i] == "checkout" and not making:
        # a plain checkout of NAME is a branch switch only when NAME is a branch; otherwise it restores a path
        if not target or not any(_git(cwd, "rev-parse", "--verify", "-q", r + target[0]) for r in ("refs/heads/", "refs/remotes/origin/")):
            return None
    if target and target[0] == _git(cwd, "symbolic-ref", "--short", "-q", "HEAD"):
        return None  # already on it
    return MAIN_REASON


def main():
    try:
        data = json.loads(sys.stdin.read())
        tool = data.get("tool_name")
        ti = data.get("tool_input") or {}
        cwd = ti.get("cwd") or data.get("cwd") or os.getcwd()
        if tool in EDIT_TOOLS:
            reason = edit_check(ti, cwd)
            if reason:
                deny(reason)
            return
        if tool != "Bash":
            return
        cmd = ti.get("command")
        if not isinstance(cmd, str):
            return
    except Exception:
        return
    if re.search(r"drop\s+(database|table)\b", cmd, re.I):
        deny("DROP DATABASE / DROP TABLE is destructive. Ask the owner before running it.")
    reason = check_command(cmd, cwd)
    if reason:
        deny(reason)


def check_command(cmd, cwd, depth=0):
    """The first rule a command line breaks, or None. Nested shell strings (bash -c, eval) are checked too."""
    if depth > 4:
        return None
    for seg in segments(cmd):
        try:
            tok = shlex.split(seg)
        except ValueError:
            tok = seg.split()
        tok, nested = unwrap(tok)
        for n in nested:
            r = check_command(n, cwd, depth + 1)
            if r:
                return r
        if tok and tok[0] == "\\rm":
            tok[0] = "rm"
        if not tok:
            continue
        name = os.path.basename(tok[0])
        if name in ("cd", "pushd") and len(tok) > 1:   # later segments run there
            d = os.path.expanduser(tok[1])
            cwd = d if os.path.isabs(d) else os.path.join(cwd, d)
            continue
        reason = protected_write(seg, tok)
        if not reason:
            reason = git_check(tok) if name == "git" else rm_check(tok, cwd) if name == "rm" else \
                find_check(tok, cwd) if name == "find" else None
        if not reason and name == "git":
            reason = switch_check(tok, cwd)
        if reason:
            return reason
    return None


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures"))
        import guard_cases
        sys.exit(guard_cases.run_all(os.path.abspath(__file__)))
    main()
