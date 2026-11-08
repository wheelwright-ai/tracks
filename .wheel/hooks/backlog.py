#!/usr/bin/env python3
"""Force-ranked backlog for one project (kit part P-019). Stdlib only; never touches git.

  backlog.py add TITLE --value 1-5 --effort 1-5 --kind owner|autopilot --source WHO [--goal G] [--check HOW]
             [--reason WHY] [--above ID | --below ID] [--status proposed|ready] [--by WHO]
  backlog.py status ID proposed|ready|doing|checking|done|dropped|blocked --reason WHY [--by WHO]
  backlog.py rank ID N --reason WHY [--pin|--unpin] [--by WHO]
  backlog.py move ID --above|--below OTHER --reason WHY [--pin] [--by WHO]
  backlog.py edit ID [--title T] [--goal G] [--value V] [--effort E] [--kind K] [--check C] --reason WHY [--by WHO]
  backlog.py show [--all] [--json]     backlog.py top [--kind K] [-n N] [--json]
  backlog.py render                    backlog.py history ID                backlog.py test

The log is .wheel/backlog.jsonl in the project root (found by walking up from the current folder, or --root PATH):
append-only, one JSON event per line {at, event: add|rank|status|edit, id, ...}. The current state is the fold of the
events. Every open item (not done/dropped) holds a unique rank 1..N; ranks stay contiguous after any change.
kind owner = needs the owner (a decision, a walkthrough, a login, anything outward-facing or hard to undo);
kind autopilot = a builder can do it and an independent checker can prove it (a check is required)."""
import argparse, json, os, sys, time

sys.dont_write_bytecode = True
try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

STATUSES = ["proposed", "ready", "doing", "checking", "done", "dropped", "blocked"]
CLOSED = ("done", "dropped")
FLOW = {
    "proposed": ["ready", "blocked", "dropped"],
    "ready": ["doing", "proposed", "blocked", "dropped"],
    "doing": ["checking", "ready", "blocked", "dropped"],
    "checking": ["done", "doing", "blocked", "dropped"],
    "blocked": ["proposed", "ready", "doing", "dropped"],
    "done": [],
    "dropped": [],
}
KINDS = ("owner", "autopilot")


class Refused(Exception):
    pass


# ---------- paths ----------
def find_root(start=None, explicit=None):
    if explicit:
        return os.path.abspath(explicit)
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(d, ".wheel")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return os.path.abspath(start or os.getcwd())
        d = up


def log_path(root):
    return os.path.join(root, ".wheel", "backlog.jsonl")


# ---------- fold ----------
def score(it):
    return it["value"] * 2 - it["effort"]


def repin(order, pinned):
    """Owner-pinned items return to their pinned rank; everything else keeps its relative order."""
    res = [i for i in order if i not in pinned]
    for pid, r in sorted(pinned.items(), key=lambda kv: (kv[1], kv[0])):
        if pid in order:
            res.insert(min(max(r, 1) - 1, len(res)), pid)
    return res


def new_state():
    return {"items": {}, "order": [], "pinned": {}}


def apply(st, ev):
    kind, iid = ev.get("event"), ev.get("id")
    items, order, pinned = st["items"], st["order"], st["pinned"]
    if kind == "add":
        items[iid] = {k: ev.get(k) for k in ("id", "title", "goal", "value", "effort", "kind", "source", "check", "reason")}
        items[iid].update(status=ev.get("status", "proposed"), added=ev["at"], updated=ev["at"], closed=None, history=[ev])
        order.insert(min(ev["rank"] - 1, len(order)), iid)
        st["order"] = repin(order, pinned)
        return
    it = items.get(iid)
    if it is None:
        return
    it["history"].append(ev)
    it["updated"] = ev["at"]
    if kind == "status":
        it["status"] = ev["status"]
        it["status_by"], it["status_reason"] = ev.get("by"), ev.get("reason")
        if ev["status"] in CLOSED:
            it["closed"] = ev["at"]
            if iid in order:
                order.remove(iid)
            pinned.pop(iid, None)
    elif kind == "rank" and iid in order:
        order.remove(iid)
        order.insert(min(max(ev["rank"], 1) - 1, len(order)), iid)
        if ev.get("pinned"):
            pinned[iid] = ev["rank"]
        else:
            pinned.pop(iid, None)
        st["order"] = repin(order, pinned)
        it["reason"] = ev.get("reason", it["reason"])
    elif kind == "edit":
        for k, v in (ev.get("changes") or {}).items():
            it[k] = v


def read_events(root):
    p = log_path(root)
    evs = []
    if os.path.exists(p):
        for n, line in enumerate(open(p, encoding="utf-8"), 1):
            line = line.strip()
            if not line:
                continue
            try:
                evs.append(json.loads(line))
            except ValueError:
                sys.stderr.write("backlog: skipped unreadable line %d of %s\n" % (n, p))
    return evs


def fold(events):
    st = new_state()
    for ev in events:
        apply(st, ev)
    for i, iid in enumerate(st["order"], 1):
        st["items"][iid]["rank"] = i
    for iid, it in st["items"].items():
        if iid not in st["order"]:
            it["rank"] = None
    return st


def load(root):
    return fold(read_events(root))


# ---------- writing ----------
def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Locked:
    """Hold an exclusive lock while reading the log and appending to it, so two sessions cannot interleave."""

    def __init__(self, root):
        self.root = root

    def __enter__(self):
        os.makedirs(os.path.join(self.root, ".wheel"), exist_ok=True)
        self.fh = open(log_path(self.root) + ".lock", "a")
        if fcntl:
            fcntl.flock(self.fh, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        self.fh.close()

    def append(self, ev):
        ev = dict(ev, at=now())
        fd = os.open(log_path(self.root), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        return ev


def need(cond, msg):
    if not cond:
        raise Refused(msg)


def intrange(v, name):
    need(isinstance(v, int) and 1 <= v <= 5, "%s must be a whole number 1-5" % name)


def next_id(events):
    n = 0
    for e in events:
        if e.get("event") == "add" and str(e.get("id", "")).startswith("B-"):
            try:
                n = max(n, int(e["id"][2:]))
            except ValueError:
                pass
    return "B-%03d" % (n + 1)


def open_item(st, iid):
    it = st["items"].get(iid)
    need(it is not None, "no item %s" % iid)
    return it


def describe(st, iid):
    """One line on why iid sits where it does, from its neighbours in the current order."""
    o, i = st["order"], st["order"].index(iid)
    it = st["items"][iid]
    bits = []
    if i > 0:
        p = st["items"][o[i - 1]]
        bits.append("below %s (score %d)" % (p["id"], score(p)))
    if i + 1 < len(o):
        n = st["items"][o[i + 1]]
        bits.append("above %s (score %d)" % (n["id"], score(n)))
    return "score %d (value %d x2 - effort %d)%s" % (score(it), it["value"], it["effort"], ", " + " and ".join(bits) if bits else ", the only open item")


def do_add(root, a):
    need(a.title and a.title.strip(), "a title is required")
    intrange(a.value, "value")
    intrange(a.effort, "effort")
    need(a.kind in KINDS, "kind must be owner or autopilot")
    need(a.source and a.source.strip(), "source is required (who or what created this item)")
    need(a.kind != "autopilot" or (a.check and a.check.strip()), "an autopilot item needs --check: how done will be proven")
    need(not (a.above and a.below), "use --above or --below, not both")
    need((a.status or "proposed") in ("proposed", "ready"), "a new item starts proposed or ready")
    need(not (a.above or a.below) or (a.reason and a.reason.strip()), "placing by judgment (--above/--below) needs --reason: why it sits there")
    with Locked(root) as lk:
        events = read_events(root)
        st = fold(events)
        iid = next_id(events)
        anchor = a.above or a.below
        if anchor:
            need(anchor in st["order"], "%s is not an open item" % anchor)
            idx = st["order"].index(anchor)
            rank = idx + 1 if a.above else idx + 2
            placed = "judgment"
        else:
            sc = a.value * 2 - a.effort
            rank = len(st["order"]) + 1
            for i, oid in enumerate(st["order"]):
                if oid not in st["pinned"] and score(st["items"][oid]) < sc:
                    rank = i + 1
                    break
            placed = "score"
        ev = {"event": "add", "id": iid, "title": a.title.strip(), "goal": a.goal, "value": a.value, "effort": a.effort,
              "kind": a.kind, "source": a.source.strip(), "check": (a.check or "").strip() or None,
              "status": a.status or "proposed", "rank": rank, "placed": placed, "by": a.by, "reason": (a.reason or "").strip()}
        if anchor:
            ev["anchor"] = anchor
            ev["position"] = "above" if a.above else "below"
        # an owner-pinned rank may sit in the way: fold first, record the rank the item really gets
        st2 = fold(events + [dict(ev, at=now())])
        ev["rank"] = st2["items"][iid]["rank"]
        if not ev["reason"]:
            ev["reason"] = describe(st2, iid)
        lk.append(ev)
        return "%s rank %d of %d: %s" % (iid, ev["rank"], len(st2["order"]), ev["reason"])


def do_status(root, a):
    need(a.status in STATUSES, "status must be one of: " + ", ".join(STATUSES))
    need(a.reason and a.reason.strip(), "every status change needs --reason")
    with Locked(root) as lk:
        st = load(root)
        it = open_item(st, a.id)
        cur = it["status"]
        ok = FLOW[cur]
        if it["kind"] == "owner" and cur == "doing":
            ok = ok + ["done"]
        need(a.status in ok, "cannot move %s from %s to %s (allowed: %s)" % (a.id, cur, a.status, ", ".join(ok) or "nothing, it is closed"))
        if a.status == "done" and it["kind"] == "autopilot":
            last = [e for e in it["history"] if e.get("event") == "status" and e["status"] in ("doing", "checking")]
            need(all(e.get("by") != a.by for e in last), "%s cannot be marked done by %s: a different checker must close an autopilot item" % (a.id, a.by))
        lk.append({"event": "status", "id": a.id, "status": a.status, "from": cur, "by": a.by, "reason": a.reason.strip()})
        return "%s %s -> %s" % (a.id, cur, a.status)


def do_rank(root, a, target=None):
    need(a.reason and a.reason.strip(), "every rank change needs --reason")
    with Locked(root) as lk:
        events = read_events(root)
        st = fold(events)
        open_item(st, a.id)
        need(a.id in st["order"], "%s is closed and has no rank" % a.id)
        old = st["order"].index(a.id) + 1
        n = len(st["order"])
        if target is None:
            anchor = a.above or a.below
            need(anchor and anchor in st["order"], "%s is not an open item" % anchor)
            need(anchor != a.id, "cannot move an item relative to itself")
            rest = [i for i in st["order"] if i != a.id]
            idx = rest.index(anchor)
            rank = idx + 1 if a.above else idx + 2
        else:
            need(1 <= target <= n, "rank must be between 1 and %d" % n)
            rank = target
        ev = {"event": "rank", "id": a.id, "rank": rank, "from": old, "pinned": bool(a.pin), "by": a.by, "reason": a.reason.strip()}
        if target is None:
            ev["anchor"] = a.above or a.below
        st2 = fold(events + [dict(ev, at=now())])
        ev["rank"] = st2["items"][a.id]["rank"]
        lk.append(ev)
        return "%s rank %d -> %d" % (a.id, old, ev["rank"])


def do_edit(root, a):
    need(a.reason and a.reason.strip(), "every edit needs --reason")
    with Locked(root) as lk:
        st = load(root)
        it = open_item(st, a.id)
        ch = {}
        for k in ("title", "goal", "check"):
            v = getattr(a, k)
            if v is not None and v != it.get(k):
                ch[k] = v
        for k in ("value", "effort"):
            v = getattr(a, k)
            if v is not None and v != it.get(k):
                intrange(v, k)
                ch[k] = v
        if a.kind is not None and a.kind != it["kind"]:
            need(a.kind in KINDS, "kind must be owner or autopilot")
            ch["kind"] = a.kind
        need(ch, "nothing to change")
        kind, chk = ch.get("kind", it["kind"]), ch.get("check", it.get("check"))
        need(kind != "autopilot" or (chk and chk.strip()), "an autopilot item needs a check")
        lk.append({"event": "edit", "id": a.id, "changes": ch, "by": a.by, "reason": a.reason.strip()})
        return "%s edited: %s" % (a.id, ", ".join(sorted(ch)))


# ---------- views ----------
def open_items(st):
    return [st["items"][i] for i in st["order"]]


def render_md(st):
    done = sorted([i for i in st["items"].values() if i["status"] == "done"], key=lambda i: i["closed"] or "", reverse=True)[:10]
    lines = ["# Backlog", "", "Force-ranked, one unique rank per open item. Generated from .wheel/backlog.jsonl by backlog.py render; do not edit by hand.", ""]
    if st["order"]:
        lines += ["| rank | id | title | kind | status | value/effort |", "|---:|---|---|---|---|---|"]
        for it in open_items(st):
            lines.append("| %s | %s | %s | %s | %s | %d/%d |" % (it["rank"], it["id"], it["title"].replace("|", "/"), it["kind"], it["status"], it["value"], it["effort"]))
    else:
        lines.append("Nothing open.")
    lines += ["", "## Recently done", ""]
    if done:
        lines += ["- %s %s (%s)" % (i["id"], i["title"], (i["closed"] or "")[:10]) for i in done]
    else:
        lines.append("Nothing done yet.")
    return "\n".join(lines) + "\n"


def do_render(root):
    st = load(root)
    p = os.path.join(root, ".wheel", "BACKLOG.md")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(render_md(st))
    return "wrote %s (%d open)" % (p, len(st["order"]))


def brief(it):
    return {k: it.get(k) for k in ("rank", "id", "title", "kind", "status", "value", "effort", "goal", "check", "source", "reason")}


def do_show(root, a):
    st = load(root)
    rows = open_items(st)
    if a.all:
        rows = rows + sorted([i for i in st["items"].values() if i["rank"] is None], key=lambda i: i["id"])
    if a.json:
        return json.dumps([brief(i) for i in rows], ensure_ascii=False, indent=1)
    if not rows:
        return "Nothing open."
    return "\n".join("%s %-6s %-9s %-10s v%d/e%d  %s" % (("#%d" % i["rank"]) if i["rank"] else "-", i["id"], i["kind"], i["status"], i["value"], i["effort"], i["title"]) for i in rows)


def do_top(root, a):
    st = load(root)
    rows = [i for i in open_items(st) if i["status"] != "blocked" and (not a.kind or i["kind"] == a.kind)][: a.n]
    if a.json:
        return json.dumps([brief(i) for i in rows], ensure_ascii=False, indent=1)
    return "\n".join("#%d %s [%s, %s] %s" % (i["rank"], i["id"], i["kind"], i["status"], i["title"]) for i in rows) or "Nothing open."


def do_history(root, iid):
    st = load(root)
    it = open_item(st, iid)
    out = ["%s %s" % (iid, it["title"])]
    for e in it["history"]:
        extra = {k: v for k, v in e.items() if k not in ("at", "event", "id", "title") and v not in (None, "")}
        out.append("%s %-6s %s" % (e["at"], e["event"], json.dumps(extra, ensure_ascii=False)))
    return "\n".join(out)


def do_test():
    here = os.path.dirname(os.path.abspath(__file__))
    cases = os.path.join(here, "fixtures", "backlog", "cases.py")
    if not os.path.exists(cases):
        return "no fixtures beside this copy; run the test from the wheel kit (tools/kit/backlog.py test)", 2
    import runpy
    mod = runpy.run_path(cases)
    return None, mod["run"](os.path.abspath(__file__))


def build_parser():
    p = argparse.ArgumentParser(prog="backlog.py", description=__doc__.split("\n")[0])
    p.add_argument("--root", help="project root (default: nearest folder above with .wheel/)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def by(s):
        s.add_argument("--by", default=os.environ.get("BACKLOG_BY", "session"), help="who is doing this")
        return s
    s = by(sub.add_parser("add"))
    s.add_argument("title")
    s.add_argument("--value", type=int, required=True)
    s.add_argument("--effort", type=int, required=True)
    s.add_argument("--kind", required=True)
    s.add_argument("--source", required=True)
    s.add_argument("--goal")
    s.add_argument("--check")
    s.add_argument("--reason")
    s.add_argument("--above")
    s.add_argument("--below")
    s.add_argument("--status")
    s = by(sub.add_parser("status"))
    s.add_argument("id")
    s.add_argument("status")
    s.add_argument("--reason", required=True)
    s = by(sub.add_parser("rank"))
    s.add_argument("id")
    s.add_argument("n", type=int)
    s.add_argument("--reason", required=True)
    s.add_argument("--pin", action="store_true")
    s.add_argument("--unpin", action="store_true")
    s = by(sub.add_parser("move"))
    s.add_argument("id")
    s.add_argument("--above")
    s.add_argument("--below")
    s.add_argument("--reason", required=True)
    s.add_argument("--pin", action="store_true")
    s = by(sub.add_parser("edit"))
    s.add_argument("id")
    for k in ("title", "goal", "check", "kind"):
        s.add_argument("--" + k)
    s.add_argument("--value", type=int)
    s.add_argument("--effort", type=int)
    s.add_argument("--reason", required=True)
    s = sub.add_parser("show")
    s.add_argument("--all", action="store_true")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("top")
    s.add_argument("--kind", choices=KINDS)
    s.add_argument("-n", type=int, default=3)
    s.add_argument("--json", action="store_true")
    sub.add_parser("render")
    s = sub.add_parser("history")
    s.add_argument("id")
    sub.add_parser("test")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.cmd == "test":
        msg, code = do_test()
        if msg:
            print(msg)
        return code
    root = find_root(explicit=a.root)
    try:
        if a.cmd == "add":
            out = do_add(root, a)
        elif a.cmd == "status":
            out = do_status(root, a)
        elif a.cmd == "rank":
            need(not (a.pin and a.unpin), "use --pin or --unpin, not both")
            out = do_rank(root, a, target=a.n)
        elif a.cmd == "move":
            need(bool(a.above) != bool(a.below), "give exactly one of --above or --below")
            out = do_rank(root, a)
        elif a.cmd == "edit":
            out = do_edit(root, a)
        elif a.cmd == "show":
            out = do_show(root, a)
        elif a.cmd == "top":
            out = do_top(root, a)
        elif a.cmd == "render":
            out = do_render(root)
        else:
            out = do_history(root, a.id)
    except Refused as e:
        sys.stderr.write("backlog: refused: %s\n" % e)
        return 1
    if a.cmd in ("add", "status", "rank", "move", "edit"):
        try:
            do_render(root)
        except OSError:
            pass
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
