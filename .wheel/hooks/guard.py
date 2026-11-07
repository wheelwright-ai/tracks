#!/usr/bin/env python3
"""PreToolUse guard for Bash commands. Reads the hook JSON on stdin and denies three kinds of command:
  1. discarding uncommitted work (git checkout -- / ., git restore without --staged, git clean -f),
  2. DROP DATABASE / DROP TABLE anywhere in the command (a quoted mention is blocked too, on purpose),
  3. plain rm of anything under the projects folder (WHEEL_GUARD_ROOT, default ~/projects); move it to the
     trash folder (WHEEL_TRASH, default ~/trash_bin) instead. Paths under /tmp are fine.
Everything else, and any malformed input, is allowed silently (exit 0, no output)."""
import json, os, re, shlex, sys

sys.dont_write_bytecode = True
SPLIT = re.compile(r"&&|\|\||;|\||\n")


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


def main():
    try:
        data = json.loads(sys.stdin.read())
        if data.get("tool_name") != "Bash":
            return
        ti = data.get("tool_input") or {}
        cmd = ti.get("command")
        if not isinstance(cmd, str):
            return
        cwd = ti.get("cwd") or data.get("cwd") or os.getcwd()
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
        if reason:
            deny(reason)


if __name__ == "__main__":
    main()
