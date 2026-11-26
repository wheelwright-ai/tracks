#!/usr/bin/env python3
"""Workspace groups (B-604): policy shared by a named set of projects, kept in one manifest at the hub.

  HUB/spokes/groups/<name>.json   {"schema": 1, "name": N, "purpose": TEXT, "members": [project names],
                                   "since": DATE, "source": TEXT,
                                   "policy": [{"id": ID, "title": TEXT, "owner_words": TEXT, "lines": [TEXT, ...]}]}

A group's policy belongs to the group, not to each member's rules file: one edit at the hub reaches every member
at its next session start (checkpoint.py sessionstart prints the lines), with no kit release and no per-project copy.
Members are named as the hub's directory names them (spokes/active.json); any name the directory gives this
checkout counts, so the hub matches as "hub" or "wheelwright-hub".

  groups.py show [--project NAME]   the groups this project (or NAME) belongs to, and their policy lines
  groups.py lint                    every manifest: valid JSON, name matches the file, members known, policy lines present
                                    (run inside a hub checkout or worktree, it lints that checkout's manifests, not main's)

Stdlib only. A missing hub, a missing folder or a broken manifest never breaks a session start: it is skipped."""
import importlib.util, json, os, subprocess, sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))


def _msg():
    spec = importlib.util.spec_from_file_location("wheel_msg_groups", os.path.join(HERE, "msg.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def groups_dir(hub=None):
    hub = hub or _msg().hub_path()
    return os.path.join(hub, "spokes", "groups") if hub else None


def load_all(hub=None):
    """[(file, manifest or None, error or None)] for every *.json in the hub's groups folder."""
    d = groups_dir(hub)
    out = []
    if not d or not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, f)) as fh:
                g = json.load(fh)
            out.append((f, g, None) if isinstance(g, dict) else (f, None, "not a JSON object"))
        except (OSError, ValueError) as e:
            out.append((f, None, str(e)[:120]))
    return out


def names_of(root):
    """Every name the hub's directory gives the checkout holding root (worktrees count as their main checkout)."""
    m = _msg()
    top = os.path.realpath(m.git_top(root))
    names = {n for n, e in m.directory().items() if not e["machine"] and os.path.realpath(os.path.expanduser(e["path"])) == top}
    return names or {os.path.basename(top)}


def groups_for(root=None, project=None, hub=None):
    names = {project} if project else names_of(root or os.getcwd())
    return [g for _, g, err in load_all(hub) if not err and names & set(g.get("members") or [])]


def session_lines(root):
    """The lines a member's session start shows: one heading per group, then its policy lines. [] for a non-member."""
    try:
        out = []
        for g in groups_for(root):
            others = [x for x in g.get("members") or [] if x not in names_of(root)]
            out.append("Group %s policy (shared with %s; kept at the hub in spokes/groups/%s.json):"
                       % (g.get("name"), ", ".join(others) or "no other project", g.get("name")))
            for p in g.get("policy") or []:
                out.append("- %s:" % (p.get("title") or p.get("id")))
                out.extend("  - " + str(line) for line in p.get("lines") or [])
        return out
    except Exception:  # noqa: BLE001  (a session start never fails on a group manifest)
        return []


def lint(hub=None):
    """[problem] across every manifest; [] when all are sound."""
    known = set(_msg().directory(hub=hub))
    probs = []
    for f, g, err in load_all(hub):
        if err:
            probs.append("%s: %s" % (f, err))
            continue
        if g.get("schema") != 1:
            probs.append("%s: schema must be 1" % f)
        if g.get("name") != f[:-5]:
            probs.append("%s: name %r does not match the file name" % (f, g.get("name")))
        mem = g.get("members")
        if not isinstance(mem, list) or not mem:
            probs.append("%s: members must be a non-empty list" % f)
        else:
            probs.extend("%s: member %r is not in the hub's directory" % (f, x) for x in mem if x not in known)
        pol = g.get("policy")
        if not isinstance(pol, list) or not pol:
            probs.append("%s: policy must be a non-empty list" % f)
        else:
            for i, p in enumerate(pol):
                if not isinstance(p, dict) or not p.get("id") or not p.get("lines"):
                    probs.append("%s: policy %d needs an id and lines" % (f, i))
    return probs


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show")
    s.add_argument("--project")
    sub.add_parser("lint")
    a = ap.parse_args(argv)
    if a.cmd == "lint":
        here = os.path.realpath(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or os.getcwd())
        hub = here if os.path.isdir(os.path.join(here, "spokes", "groups")) else None
        probs = lint(hub)
        print("\n".join(probs) if probs else "groups: %d manifest(s) in %s, all sound" % (len(load_all(hub)), groups_dir(hub)))
        return 1 if probs else 0
    if a.project:
        gs = groups_for(project=a.project)
        print("\n".join("%s: %s" % (g["name"], ", ".join(g.get("members") or [])) for g in gs) or "no groups")
    else:
        print("\n".join(session_lines(os.getcwd())) or "no groups")
    return 0


if __name__ == "__main__":
    sys.exit(main())
