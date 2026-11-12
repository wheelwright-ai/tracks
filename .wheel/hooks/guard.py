#!/usr/bin/env python3
"""PreToolUse guard. Reads the hook JSON on stdin. For Bash commands it denies four kinds:
  1. discarding uncommitted work (git checkout -- / ., git restore without --staged, git clean -f),
  2. DROP DATABASE / DROP TABLE anywhere in the command (a quoted mention is blocked too, on purpose),
  3. plain rm of anything under the projects folder (WHEEL_GUARD_ROOT, default ~/projects); move it to the
     trash folder (WHEEL_TRASH, default ~/trash_bin) instead. Paths under /tmp are fine.
  4. switching branches (git checkout <branch>, git switch) in a project's main checkout.
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
    for seg in SPLIT.split(cmd):
        try:
            tok = shlex.split(seg)
        except ValueError:
            tok = seg.split()
        while tok and (re.match(r"\w+=", tok[0]) or tok[0] in ("sudo", "command")):
            tok = tok[1:]
        if tok and tok[0] == "\\rm":
            tok[0] = "rm"
        if not tok:
            continue
        name = os.path.basename(tok[0])
        reason = git_check(tok) if name == "git" else rm_check(tok, cwd) if name == "rm" else None
        if not reason and name == "git":
            reason = switch_check(tok, cwd)
        if reason:
            deny(reason)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures"))
        import guard_cases
        sys.exit(guard_cases.run_all(os.path.abspath(__file__)))
    main()
