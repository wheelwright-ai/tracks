#!/usr/bin/env python3
"""Message lugs between projects (kit part P-022, W-181). The one way a project talks to another: no loose files.

The owner (2026-11-11): "each spoke knows how to find active sessions and essentially drop a message lug in its inbox
for review on its next wake". A message lug is one JSON file in the recipient's inbox, `.wheel/inbox/<id>.json` in
the recipient's MAIN checkout (git-ignored: messages may name machines and addresses; never pushed). The recipient
reviews its inbox at its next wake or session start; a reply is a message lug back, with reply_to.

  msg.py who                                  every project, where it lives, whether a session is active there now,
                                              its unread count (the directory: the hub's spokes/active.json and
                                              spokes/remote.json, found through ~/.config/wheel/hub-path)
  msg.py send TO --subject S --body B [--ask A ...] [--item-file F.json] [--reply-to ID] [--responsible] [--from NAME]
                                              drop a message lug in TO's inbox (a local path, or ssh for a project on
                                              another machine); prints its id
  msg.py inbox [--all] [--json]               this project's messages, unread first
  msg.py read ID                              print one and mark it read
  msg.py done ID --note WHY                   mark it handled (what was done: a lug added, a reply sent, nothing needed)

No local hub checkout (e.g. a project on another machine)? Set "remote_hub": {"ssh": HOST, "path": "~/projects/hub"} in
.wheel/config.json: who and send then read the hub's spoke lists and deliver over ssh.

A message lug: {kind: "message", schema: 1, id, at, from, to, subject, body, asks: [str], items: [work items with
checks], reply_to, refs: [str], responsibility: responsible|informed}. State (unread, read, done) lives beside it in .wheel/inbox/.state.json, never in the
message, so a message is never rewritten. TO and FROM are project names; "hub" is the hub. Stdlib only."""
import argparse, datetime, json, os, re, shlex, subprocess, sys, uuid

sys.dont_write_bytecode = True


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_top(path):
    """The main checkout of the repository holding path (worktrees share it), or path itself outside git."""
    r = subprocess.run(["git", "-C", path, "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip().endswith("/.git"):
        return os.path.dirname(r.stdout.strip())
    r = subprocess.run(["git", "-C", path, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else path


def hub_path():
    h = os.environ.get("WHEEL_HUB")
    if not h:
        try:
            with open(os.path.expanduser("~/.config/wheel/hub-path")) as f:
                h = f.read().strip()
        except OSError:
            h = ""
    return h or None


def remote_hub(root=None):
    """(ssh host, path) of a hub on another machine, from remote_hub in this project's .wheel/config.json, or None.
    Accepts {"ssh": H, "path": P} or "H:P". Used only when there is no local hub checkout."""
    try:
        with open(os.path.join(git_top(root or os.getcwd()), ".wheel", "config.json")) as f:
            r = json.load(f).get("remote_hub")
    except (OSError, ValueError, AttributeError):
        return None
    if isinstance(r, str) and ":" in r:
        r = dict(zip(("ssh", "path"), r.split(":", 1)))
    if isinstance(r, dict) and r.get("ssh") and r.get("path"):
        return r["ssh"], r["path"]
    return None


def remote_directory(host, path, runner=subprocess.run):
    """The hub's directory read over ssh: its spoke lists, every path marked as on that machine."""
    rel = path[2:] if path.startswith("~/") else path
    base = ("$HOME/" + rel if path.startswith("~/") else rel).rstrip("/")
    out = {"hub": {"path": path, "machine": host, "ssh": host}}
    for fn in ("active", "remote"):
        try:
            r = runner(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, 'cat "%s/spokes/%s.json" 2>/dev/null; true' % (base, fn)],
                       capture_output=True, text=True, timeout=30)
            rows = (json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}).get(fn) or []
        except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
            continue
        for s in rows:
            if fn == "active":
                out[s["name"]] = {"path": s["path"], "machine": host, "ssh": host}
            else:
                out[s["name"]] = {"path": s["path"], "machine": s.get("machine"), "ssh": s.get("ssh_host") or s.get("machine")}
    return out


def directory(hub=None, root=None, runner=subprocess.run):
    """{name: {"path", "machine" (None = this one), "ssh"}} for the hub and every project it knows."""
    hub = hub or hub_path()
    out = {}
    if not hub:
        rh = remote_hub(root)
        return remote_directory(rh[0], rh[1], runner) if rh else out
    out["hub"] = {"path": hub, "machine": None, "ssh": None}
    try:
        with open(os.path.join(hub, "spokes", "active.json")) as f:
            for s in json.load(f).get("active") or []:
                out[s["name"]] = {"path": s["path"], "machine": None, "ssh": None}
    except (OSError, ValueError):
        pass
    try:
        with open(os.path.join(hub, "spokes", "remote.json")) as f:
            for s in json.load(f).get("remote") or []:
                out[s["name"]] = {"path": s["path"], "machine": s.get("machine"), "ssh": s.get("ssh_host") or s.get("machine")}
    except (OSError, ValueError):
        pass
    return out


def inbox_dir(root):
    return os.path.join(git_top(root), ".wheel", "inbox")


def this_project(root):
    """The name the directory gives this checkout, or its folder name."""
    top = os.path.realpath(git_top(root))
    for name, e in directory().items():
        if not e["machine"] and os.path.realpath(os.path.expanduser(e["path"])) == top:
            return name
    return os.path.basename(top)


def make(sender, to, subject, body, asks=None, items=None, reply_to=None, refs=None, responsibility=None):
    need_text(subject, "subject")
    need_text(body, "body")
    return {"kind": "message", "schema": 1, "id": "m-%s-%s" % (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"), uuid.uuid4().hex[:6]),
            "at": now(), "from": sender, "to": to, "subject": subject.strip(), "body": body.strip(),
            "asks": [a.strip() for a in (asks or []) if a.strip()], "items": items or [], "reply_to": reply_to, "refs": refs or [],
            "responsibility": "responsible" if responsibility == "responsible" else "informed"}


def need_text(v, what):
    if not (isinstance(v, str) and v.strip()):
        raise SystemExit("msg.py: a message needs a %s" % what)


def deliver(m, entry, runner=subprocess.run):
    """Write the message lug into the recipient's inbox: a local file, or over ssh for another machine."""
    data = json.dumps(m, indent=1, ensure_ascii=False) + "\n"
    name = m["id"] + ".json"
    if entry.get("machine"):
        path = entry["path"]
        rel = path[2:] if path.startswith("~/") else path
        target = ("$HOME/" + rel if path.startswith("~/") else rel).rstrip("/") + "/.wheel/inbox"
        proj = target[: -len("/.wheel/inbox")]
        script = ('mkdir -p "%s" && cat > "%s/%s.tmp" && mv "%s/%s.tmp" "%s/%s"; '
                  'x="%s/.git/info/exclude"; [ -d "%s/.git/info" ] && { grep -qx ".wheel/inbox/" "$x" 2>/dev/null || echo ".wheel/inbox/" >> "$x"; }; true'
                  % (target, target, name, target, name, target, name, proj, proj))
        r = runner(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", entry["ssh"], script], input=data, capture_output=True,
                   text=True, timeout=60)
        if r.returncode:
            raise SystemExit("msg.py: could not deliver to %s over ssh: %s" % (entry["ssh"], (r.stderr or "").strip()[:200]))
        return "%s:%s/%s" % (entry["ssh"], target, name)
    d = inbox_dir(os.path.expanduser(entry["path"]))
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, name + ".tmp")
    with open(tmp, "w") as f:
        f.write(data)
    os.replace(tmp, os.path.join(d, name))
    ensure_ignored(git_top(os.path.expanduser(entry["path"])))
    return os.path.join(d, name)


def ensure_ignored(top):
    """.wheel/inbox/ stays out of git (through .git/info/exclude: no tracked change)."""
    ex = os.path.join(top, ".git", "info", "exclude")
    if not os.path.isdir(os.path.dirname(ex)):
        return
    try:
        have = open(ex).read() if os.path.exists(ex) else ""
        if ".wheel/inbox/" not in have:
            with open(ex, "a") as f:
                f.write(("" if have.endswith("\n") or not have else "\n") + ".wheel/inbox/\n")
    except OSError:
        pass


def keep_sent(root, m):
    """The sender keeps a copy in its own .wheel/outbox/ (git-ignored like the inbox), so what was asked is on record."""
    try:
        top = git_top(root)
        d = os.path.join(top, ".wheel", "outbox")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, m["id"] + ".json"), "w") as f:
            json.dump(m, f, indent=1, ensure_ascii=False)
        ex = os.path.join(top, ".git", "info", "exclude")
        if os.path.isdir(os.path.dirname(ex)):
            have = open(ex).read() if os.path.exists(ex) else ""
            if ".wheel/outbox/" not in have:
                with open(ex, "a") as f:
                    f.write(("" if have.endswith("\n") or not have else "\n") + ".wheel/outbox/\n")
    except OSError:
        pass


def state(d):
    try:
        with open(os.path.join(d, ".state.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def set_state(d, mid, st, note=None):
    s = state(d)
    s[mid] = {"state": st, "at": now(), **({"note": note} if note else {})}
    tmp = os.path.join(d, ".state.json.tmp")
    with open(tmp, "w") as f:
        json.dump(s, f, indent=1, sort_keys=True)
    os.replace(tmp, os.path.join(d, ".state.json"))


def messages(root, include_done=False):
    """[(message, state)] in this project's inbox, unread first then oldest first."""
    d = inbox_dir(root)
    st = state(d)
    out = []
    try:
        names = sorted(n for n in os.listdir(d) if n.endswith(".json") and not n.startswith("."))
    except OSError:
        return []
    for n in names:
        try:
            with open(os.path.join(d, n)) as f:
                m = json.load(f)
        except (OSError, ValueError):
            continue
        s = (st.get(m.get("id")) or {}).get("state", "unread")
        if s == "done" and not include_done:
            continue
        out.append((m, s))
    out.sort(key=lambda x: (x[1] != "unread", x[0].get("at", "")))
    return out


def unread_lines(root, limit=5):
    """Short lines for a wake or session start; [] when nothing is waiting."""
    waiting = [(m, s) for m, s in messages(root) if s != "done"]
    if not waiting:
        return []
    lines = ["Inbox: %d message lug(s) waiting for review (python3 .wheel/hooks/msg.py inbox):" % len(waiting)]
    for m, s in waiting[:limit]:
        lines.append("- %s from %s: %s%s [%s]" % (m.get("id"), m.get("from"), m.get("subject"),
                                                 " (%d asks, %d items)" % (len(m.get("asks") or []), len(m.get("items") or [])) if m.get("asks") or m.get("items") else "", s))
    return lines


def active_session(entry):
    """True when a claude session runs inside the project now (local: /proc; another machine: one short ssh)."""
    path = entry["path"]
    if entry.get("machine"):
        rel = path[2:] if path.startswith("~/") else path
        script = ('d="$HOME/%s"; for p in /proc/[0-9]*; do c=$(readlink "$p/cwd" 2>/dev/null) || continue; case "$c" in "$d"|"$d"/*) '
                  'grep -qa claude "$p/cmdline" 2>/dev/null && { echo yes; exit 0; };; esac; done; echo no' % rel)
        try:
            r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", entry["ssh"], script], capture_output=True, text=True, timeout=30)
            return r.stdout.strip() == "yes" if r.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None
    root = os.path.realpath(os.path.expanduser(path))
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            cwd = os.path.realpath(os.readlink("/proc/%s/cwd" % p))
            if cwd == root or cwd.startswith(root + os.sep):
                with open("/proc/%s/cmdline" % p, "rb") as f:
                    if b"claude" in f.read():
                        return True
        except OSError:
            continue
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(prog="msg.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=os.getcwd())
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("who")
    s = sub.add_parser("send")
    s.add_argument("to")
    s.add_argument("--subject", required=True)
    s.add_argument("--body", required=True)
    s.add_argument("--ask", action="append", default=[])
    s.add_argument("--item-file", help="a JSON file holding a list of work items (each with a check)")
    s.add_argument("--reply-to")
    s.add_argument("--responsible", action="store_true", help="the recipient is responsible: its wake turns this into a ready lug and replies when done (default: informed, only marked read)")
    s.add_argument("--ref", action="append", default=[])
    s.add_argument("--from", dest="sender")
    s = sub.add_parser("inbox")
    s.add_argument("--all", action="store_true")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("read")
    s.add_argument("id")
    s = sub.add_parser("done")
    s.add_argument("id")
    s.add_argument("--note", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "who":
        for name, e in sorted(directory(root=a.root).items()):
            act = active_session(e)
            n = len([1 for _, s in messages(os.path.expanduser(e["path"])) if s == "unread"]) if not e["machine"] else "?"
            print("%-22s %-9s %-44s session %-4s unread %s" % (name, e["machine"] or "here", e["path"][:44],
                                                              {True: "yes", False: "no", None: "?"}[act], n))
        return 0
    if a.cmd == "send":
        d = directory(root=a.root)
        if a.to not in d:
            raise SystemExit("msg.py: no project named %s in the hub's directory (msg.py who lists them)" % a.to)
        items = []
        if a.item_file:
            with open(a.item_file) as f:
                items = json.load(f)
            if not isinstance(items, list) or not all(isinstance(i, dict) and i.get("check") for i in items):
                raise SystemExit("msg.py: --item-file must hold a list of work items, each with a check")
        m = make(a.sender or this_project(a.root), a.to, a.subject, a.body, a.ask, items, a.reply_to, a.ref, "responsible" if a.responsible else None)
        where = deliver(m, d[a.to])
        keep_sent(a.root, m)
        print("%s delivered to %s" % (m["id"], where))
        return 0
    if a.cmd == "inbox":
        ms = messages(a.root, include_done=a.all)
        if a.json:
            print(json.dumps([dict(m, _state=s) for m, s in ms], indent=1))
        elif not ms:
            print("Inbox empty.")
        else:
            for m, s in ms:
                print("%-7s %s from %-16s %s" % (s, m.get("id"), m.get("from"), m.get("subject")))
        return 0
    d = inbox_dir(a.root)
    m = next((m for m, _ in messages(a.root, include_done=True) if m.get("id") == a.id), None)
    if not m:
        raise SystemExit("msg.py: no message %s in this inbox" % a.id)
    if a.cmd == "read":
        print(json.dumps(m, indent=1, ensure_ascii=False))
        if (state(d).get(a.id) or {}).get("state") != "done":
            set_state(d, a.id, "read")
        return 0
    set_state(d, a.id, "done", a.note.strip())
    print("%s done: %s" % (a.id, a.note.strip()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
