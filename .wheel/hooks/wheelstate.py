#!/usr/bin/env python3
"""The wheel-state policy (B-049): no uncommitted work left lying around.

Every path the harness writes in a project is listed in wheelstate.json as `ignore` (runtime state) or `commit` (a
record, committed by the step that writes it). install.py puts the ignore list in the project's .gitignore.

  wheelstate.py check ROOT          list harness files left uncommitted (exit 1 when any)
  wheelstate.py land ROOT [-m MSG]  commit the dirty `commit` paths, by explicit path, in the checkout's current branch;
                                    untrack any file that is tracked but now ignored
  wheelstate.py unlisted PATH...    print the paths no entry covers

land never pushes, never switches a branch, refuses during a merge or rebase, and skips (and names) a file a
secret scan flags when a scanner is given. Stdlib only."""
import json, os, subprocess, sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))


def policy(path=None):
    with open(path or os.path.join(HERE, "wheelstate.json")) as f:
        return json.load(f)


def _match(rel, entry):
    return rel == entry or (entry.endswith("/") and rel.startswith(entry))


def classify(rel, pol=None):
    """'ignore', 'commit' or None (not a listed harness path)."""
    pol = pol or policy()
    for kind in ("ignore", "commit"):
        if any(_match(rel, e) for e in pol[kind]):
            return kind
    return None


def is_hub(root):
    """The hub carries the kit's source (tools/kit/MANIFEST.json). Only there are records/, plans/, lugs/, ledger.jsonl and
    runtime/ the harness's own; in any other project those names may be the project's own data."""
    return os.path.isfile(os.path.join(root, "tools", "kit", "MANIFEST.json"))


def owned(rel, root, pol=None):
    """classify() scoped to a checkout: in a project (not the hub) only what the harness itself puts under .wheel/ (and
    its hook wiring in .claude/settings.json) is the policy's business."""
    kind = classify(rel, pol)
    if kind and not is_hub(root) and not (rel.startswith(".wheel/") or rel == ".claude/settings.json"):
        return None
    return kind


def ignore_lines(pol=None):
    return list((pol or policy())["ignore"])


def apply_ignores(root, pol=None):
    """Add the ignore list to the project's .gitignore (never duplicating a line); returns the lines added."""
    gi = os.path.join(root, ".gitignore")
    have = open(gi).read().splitlines() if os.path.exists(gi) else []
    added = []
    with open(gi, "a") as f:
        for line in ignore_lines(pol):
            if line not in have:
                f.write(("\n" if have and have[-1] != "" else "") + line + "\n")
                have.append(line)
                added.append(line)
    return added


def _git(root, *a):
    return subprocess.run(["git", "-C", root, *a], capture_output=True, text=True, stdin=subprocess.DEVNULL)


def dirty(root):
    """Dirty paths (relative), untracked files listed one by one."""
    r = _git(root, "status", "--porcelain", "-z", "--untracked-files=all")
    out = []
    parts = r.stdout.split("\0")
    i = 0
    while i < len(parts):
        e = parts[i]
        if len(e) > 3:
            out.append(e[3:])
            if e[0] in "RC":
                i += 1   # the rename's source follows
        i += 1
    return out


def uncommitted(root, pol=None):
    """Harness files left uncommitted: dirty paths the policy says to commit (ignored ones never show in git status)."""
    pol = pol or policy()
    return [p for p in dirty(root) if owned(p, root, pol) == "commit"]


def tracked_ignored(root, pol=None):
    """Tracked files the policy now ignores; only in the hub. A project's tracked files are never untracked."""
    pol = pol or policy()
    if not is_hub(root):
        return []
    r = _git(root, "ls-files", "-z")
    return [p for p in r.stdout.split("\0") if p and classify(p, pol) == "ignore"]


def land(root, message="wheel state", scan=None, pol=None):
    """Commit what the harness wrote. scan(path_abs, rel) -> truthy means 'looks like a secret': that file is left out.
    Returns a one-line result."""
    pol = pol or policy()
    gd = _git(root, "rev-parse", "--absolute-git-dir").stdout.strip()
    if not gd:
        return "not committed: not a git repository"
    if any(os.path.exists(os.path.join(gd, x)) for x in ("MERGE_HEAD", "REBASE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD")):
        return "not committed: a merge or rebase is in progress"
    paths = uncommitted(root, pol)
    skipped = [p for p in paths if scan and scan(os.path.join(root, p), p)]
    paths = [p for p in paths if p not in skipped]
    untrack = tracked_ignored(root, pol)
    if not paths and not untrack:
        return "not committed: nothing changed" + (" (left out, looks like a secret: %s)" % ", ".join(skipped) if skipped else "")
    staged = set(_git(root, "diff", "--cached", "--name-only").stdout.split("\n")) - {""}
    if staged - set(paths) - set(untrack):
        return "not committed: other files are staged (%s)" % ", ".join(sorted(staged - set(paths) - set(untrack)))[:200]
    r = _commit(root, message, paths, untrack)
    refused = []
    if r.returncode != 0:
        # One flagged file used to block every state commit for good (cut 66: 61 files left dirty on main for a day).
        # Leave out the files the commit gate names, commit the rest, and name what was left out.
        named = set(GATE_LINE.findall((r.stderr or "") + (r.stdout or "")))
        refused = sorted(named & set(paths))
        rest = [p for p in paths if p not in named]
        if refused and (rest or untrack):
            r = _commit(root, message, rest, untrack)
        if r.returncode != 0:
            return "not committed: %s" % (r.stderr.strip() or r.stdout.strip())[:200]
    left = ["looks like a secret: %s" % ", ".join(skipped)] if skipped else []
    left += ["refused by the commit gate: %s" % ", ".join(refused)] if refused else []
    return "committed %s%s" % (_git(root, "rev-parse", "--short", "HEAD").stdout.strip(),
                               " (left out, %s)" % "; ".join(left) if left else "")


GATE_LINE = __import__("re").compile(r"(?m)^\s+(\S+?)(?::\d+)? \[F-\d+\]")


def _commit(root, message, paths, untrack):
    """Stage exactly these paths and commit. When the commit fails, the index is put back: a refused commit used to leave
    every file staged, so the next unrelated commit would have swept them in."""
    if untrack:   # stops tracking, keeps the file on disk
        _git(root, "rm", "--cached", "-q", "--ignore-unmatch", "--", *untrack)
    if paths:
        _git(root, "add", "-f", "--", *paths)
    r = _git(root, "commit", "-q", "-m", "%s\n\nFiles: %s" % (message, ", ".join(paths + ["(untracked) " + u for u in untrack])))
    if r.returncode != 0 and (paths or untrack):
        _git(root, "reset", "-q", "--", *(paths + untrack))
    return r


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "check" and os.path.isdir(a[1]):
        left = uncommitted(a[1])
        for p in left:
            print(p)
        print("%d harness file(s) uncommitted" % len(left))
        sys.exit(1 if left else 0)
    if len(a) >= 2 and a[0] == "land" and os.path.isdir(a[1]):
        msg = a[a.index("-m") + 1] if "-m" in a and a.index("-m") + 1 < len(a) else "wheel state"
        print(land(a[1], msg))
        sys.exit(0)
    if a[:1] == ["unlisted"]:
        miss = [p for p in a[1:] if classify(p) is None]
        print("\n".join(miss))
        sys.exit(1 if miss else 0)
    print(__doc__)
    sys.exit(0 if a[:1] in (["-h"], ["--help"]) else 2)
