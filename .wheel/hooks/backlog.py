#!/usr/bin/env python3
"""Lugs and initiatives for one project: a force-ranked plan and roadmap (kit part P-019). Stdlib only; never touches git.

Lugs are the work items; initiatives group the lugs that deliver one agreed goal. Every write names who made it (--by).
  lug add TITLE --value 1-5 --effort 1-5 --kind owner|autopilot --source WHO --by WHO [--goal G] [--initiative I-###]
          [--check HOW] [--reason WHY] [--above ID | --below ID] [--status proposed|ready]
  lug status ID proposed|ready|doing|checking|done|dropped|blocked --reason WHY --by WHO
  lug rank ID N --reason WHY [--pin|--unpin] --by WHO      lug move ID --above|--below OTHER --reason WHY [--pin] --by WHO
  lug edit ID [--title T] [--goal G] [--value V] [--effort E] [--kind K] [--check C] --reason WHY --by WHO
  lug link ID I-### --by WHO [--reason WHY]                 (each lug belongs to exactly one initiative)
  lug claim ID --by WORKER --lease MINUTES                  lug release ID --by WORKER [--reason WHY]
  lug initiative add TITLE --goal N --outcome .. --why-now .. --scope-in .. --scope-out .. --done-when .. --by WHO
  lug initiative edit I-### [--title|--goal|--outcome|--why-now|--scope-in|--scope-out|--done-when ..] --reason WHY --by WHO
  lug initiative signoff I-### --who "the owner (source)" --by WHO      lug initiative close I-### --reason WHY --by WHO
  lug initiative show [I-###] [--json]
  lug show [--all] [--json]   lug top [--kind K] [--pickable] [-n N] [--json]   lug history ID
  lug roadmap [--json]        lug render     lug lint [--json]     lug verify     lug test
("lug" is lug.py or backlog.py; the same program.)

The log is .wheel/backlog.jsonl in the project root (found by walking up from the current folder, or --root PATH):
append-only, one JSON event per line {at, event, id, by, ...}. The current state is the fold of the events. Every open
lug (not done/dropped) holds a unique rank 1..N; ranks stay contiguous after any change. Lug ids are B-###, initiative
ids I-###. Rendered views (never edit by hand): .wheel/BACKLOG.md (the ranked lugs) and .wheel/ROADMAP.md
(goal -> initiative -> lugs -> completed history).
kind owner = needs the owner (a decision, a walkthrough, a login, anything outward-facing or hard to undo);
kind autopilot = a builder can do it and an independent checker can prove it (a check is required). An autopilot lug
gets no autopilot budget (claim, top --pickable) until its initiative has the owner's sign-off."""
import argparse, calendar, json, os, re, sys, time

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
WRITES = ("add", "status", "rank", "move", "edit", "link", "claim", "release", "initiative")
INIT_FIELDS = ("title", "goal", "outcome", "why_now", "scope_in", "scope_out", "done_when")
INIT_LABELS = {"title": "title", "goal": "goal", "outcome": "outcome", "why_now": "why now", "scope_in": "scope (in)",
               "scope_out": "scope (out)", "done_when": "done when"}
# the text an owner signs off; changing any of these puts the sign-off back to pending
SIGNED_FIELDS = ("goal", "outcome", "scope_in", "scope_out", "done_when")
EVENTS = ("add", "status", "rank", "edit", "link", "claim", "release",
          "init_add", "init_edit", "init_signoff", "init_close")


class Refused(Exception):
    pass


# ---------- paths and time ----------
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


def now():
    # BACKLOG_NOW (an ISO time) lets the fixtures test lease expiry without waiting
    return os.environ.get("BACKLOG_NOW") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def secs(iso):
    try:
        return calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return 0


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


# ---------- fold ----------
def score(it):
    return it["value"] * 2 - it["effort"]


def repin(order, pinned):
    """Owner-pinned lugs return to their pinned rank; everything else keeps its relative order."""
    res = [i for i in order if i not in pinned]
    for pid, r in sorted(pinned.items(), key=lambda kv: (kv[1], kv[0])):
        if pid in order:
            res.insert(min(max(r, 1) - 1, len(res)), pid)
    return res


def new_state():
    return {"items": {}, "order": [], "pinned": {}, "inits": {}}


def apply(st, ev):
    kind, iid = ev.get("event"), ev.get("id")
    items, order, pinned, inits = st["items"], st["order"], st["pinned"], st["inits"]
    if kind == "init_add":
        if iid in inits:
            return
        inits[iid] = {k: ev.get(k) for k in INIT_FIELDS}
        inits[iid].update(id=iid, added=ev.get("at"), updated=ev.get("at"), closed=None, by=ev.get("by"),
                          owner_signoff={"status": "pending"}, history=[ev])
        return
    if kind in ("init_edit", "init_signoff", "init_close"):
        ini = inits.get(iid)
        if ini is None:
            return
        ini["history"].append(ev)
        ini["updated"] = ev.get("at")
        if kind == "init_edit":
            ch = ev.get("changes") or {}
            for k, v in ch.items():
                ini[k] = v
            if any(k in SIGNED_FIELDS for k in ch) and ini["owner_signoff"].get("status") == "yes":
                ini["owner_signoff"] = {"status": "pending", "reset": ev.get("at"), "was": ini["owner_signoff"]}
        elif kind == "init_signoff":
            ini["owner_signoff"] = {"status": "yes", "who": ev.get("who"), "at": ev.get("at"), "by": ev.get("by")}
        else:
            ini["closed"] = ev.get("at")
            ini["close_reason"] = ev.get("reason")
        return
    if kind == "add":
        if iid in items:  # a duplicate id (say, from a bad merge): the first add stands; verify reports it
            return
        items[iid] = {k: ev.get(k) for k in ("id", "title", "goal", "value", "effort", "kind", "source", "check", "reason")}
        items[iid].update(status=ev.get("status", "proposed"), added=ev.get("at"), updated=ev.get("at"), closed=None,
                          initiative=ev.get("initiative"), claim=None, history=[ev])
        order.insert(min(max(int(ev.get("rank") or len(order) + 1), 1) - 1, len(order)), iid)
        st["order"] = repin(order, pinned)
        return
    it = items.get(iid)
    if it is None:
        return
    it["history"].append(ev)
    it["updated"] = ev.get("at")
    if kind == "status":
        it["status"] = ev["status"]
        it["status_by"], it["status_reason"] = ev.get("by"), ev.get("reason")
        if ev["status"] in CLOSED:
            it["closed"] = ev.get("at")
            it["claim"] = None
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
    elif kind == "link":
        it["initiative"] = ev.get("initiative")
    elif kind == "claim":
        it["claim"] = {"by": ev.get("by"), "at": ev.get("at"), "until": ev.get("until")}
    elif kind == "release":
        it["claim"] = None


def read_events(root, problems=None):
    """The events in log order. Unreadable lines are skipped (and reported in problems with their line number)."""
    p = log_path(root)
    evs = []
    if os.path.exists(p):
        for n, line in enumerate(open(p, encoding="utf-8"), 1):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
                if not isinstance(ev, dict):
                    raise ValueError("not an object")
            except ValueError:
                if problems is not None:
                    problems.append((n, "not valid JSON"))
                else:
                    sys.stderr.write("lug: skipped unreadable line %d of %s\n" % (n, p))
                continue
            ev["_line"] = n
            evs.append(ev)
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
    for ini in st["inits"].values():
        ini.update(progress(st, ini["id"]))
    return st


def load(root):
    return fold(read_events(root))


def lugs_of(st, init_id):
    return [it for it in st["items"].values() if it.get("initiative") == init_id]


def progress(st, init_id):
    """Derived from the initiative's lugs: dropped lugs never count, as done or as total."""
    lugs = lugs_of(st, init_id)
    counted = [l for l in lugs if l["status"] != "dropped"]
    done = [l for l in counted if l["status"] == "done"]
    if counted and len(done) == len(counted):
        status = "done"
    elif lugs and not counted:
        status = "dropped"
    elif any(l["status"] in ("doing", "checking", "done") for l in counted):
        status = "active"
    else:
        status = "proposed"
    return {"lugs": len(lugs), "counted": len(counted), "done": len(done), "dropped": len(lugs) - len(counted),
            "open": len([l for l in lugs if l["status"] not in CLOSED]), "status": status}


def live_claim(it, at=None):
    c = it.get("claim")
    if c and secs(c.get("until")) > secs(at or now()):
        return c
    return None


# ---------- writing ----------
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


def next_id(events, prefix="B-", kinds=("add",)):
    n = 0
    for e in events:
        if e.get("event") in kinds and str(e.get("id", "")).startswith(prefix):
            try:
                n = max(n, int(e["id"][len(prefix):]))
            except ValueError:
                pass
    return "%s%03d" % (prefix, n + 1)


def open_item(st, iid):
    it = st["items"].get(iid)
    need(it is not None, "no lug %s" % iid)
    return it


def get_init(st, init_id):
    ini = st["inits"].get(init_id)
    need(ini is not None, "no initiative %s" % init_id)
    return ini


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
    return "score %d (value %d x2 - effort %d)%s" % (score(it), it["value"], it["effort"], ", " + " and ".join(bits) if bits else ", the only open lug")


def do_add(root, a):
    need(a.title and a.title.strip(), "a title is required")
    intrange(a.value, "value")
    intrange(a.effort, "effort")
    need(a.kind in KINDS, "kind must be owner or autopilot")
    need(a.source and a.source.strip(), "source is required (who or what created this lug)")
    need(a.kind != "autopilot" or (a.check and a.check.strip()), "an autopilot lug needs --check: how done will be proven")
    need(not (a.above and a.below), "use --above or --below, not both")
    need((a.status or "proposed") in ("proposed", "ready"), "a new lug starts proposed or ready")
    need(not (a.above or a.below) or (a.reason and a.reason.strip()), "placing by judgment (--above/--below) needs --reason: why it sits there")
    with Locked(root) as lk:
        events = read_events(root)
        st = fold(events)
        goal = a.goal
        if a.initiative:
            ini = get_init(st, a.initiative)
            need(not ini["closed"], "%s is closed; a new lug cannot join it" % a.initiative)
            need(goal is None or str(goal) == str(ini["goal"]), "%s serves goal %s, not goal %s" % (a.initiative, ini["goal"], goal))
            goal = ini["goal"]
        iid = next_id(events)
        anchor = a.above or a.below
        if anchor:
            need(anchor in st["order"], "%s is not an open lug" % anchor)
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
        ev = {"event": "add", "id": iid, "title": a.title.strip(), "goal": goal, "value": a.value, "effort": a.effort,
              "kind": a.kind, "source": a.source.strip(), "check": (a.check or "").strip() or None,
              "status": a.status or "proposed", "rank": rank, "placed": placed, "by": a.by, "reason": (a.reason or "").strip()}
        if a.initiative:
            ev["initiative"] = a.initiative
        if anchor:
            ev["anchor"] = anchor
            ev["position"] = "above" if a.above else "below"
        # an owner-pinned rank may sit in the way: fold first, record the rank the lug really gets
        st2 = fold(events + [dict(ev, at=now())])
        ev["rank"] = st2["items"][iid]["rank"]
        if not ev["reason"]:
            ev["reason"] = describe(st2, iid)
        lk.append(ev)
        return "%s rank %d of %d: %s" % (iid, ev["rank"], len(st2["order"]), ev["reason"])


def allowed_moves(it):
    ok = FLOW[it["status"]]
    if it["kind"] == "owner" and it["status"] == "doing":
        ok = ok + ["done"]
    return ok


def do_status(root, a):
    need(a.status in STATUSES, "status must be one of: " + ", ".join(STATUSES))
    need(a.reason and a.reason.strip(), "every status change needs --reason")
    with Locked(root) as lk:
        st = load(root)
        it = open_item(st, a.id)
        cur = it["status"]
        ok = allowed_moves(it)
        need(a.status in ok, "cannot move %s from %s to %s (allowed: %s)" % (a.id, cur, a.status, ", ".join(ok) or "nothing, it is closed"))
        c = live_claim(it)
        need(not (c and a.status == "doing" and c["by"] != a.by), "%s is claimed by %s until %s" % (a.id, c and c["by"], c and c["until"]))
        if a.status == "done" and it["kind"] == "autopilot":
            last = [e for e in it["history"] if e.get("event") == "status" and e["status"] in ("doing", "checking")]
            need(all(e.get("by") != a.by for e in last), "%s cannot be marked done by %s: a different checker must close an autopilot lug" % (a.id, a.by))
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
            need(anchor and anchor in st["order"], "%s is not an open lug" % anchor)
            need(anchor != a.id, "cannot move a lug relative to itself")
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
        need(kind != "autopilot" or (chk and chk.strip()), "an autopilot lug needs a check")
        if "goal" in ch and it.get("initiative") in st["inits"]:
            g = st["inits"][it["initiative"]]["goal"]
            need(str(ch["goal"]) == str(g), "%s belongs to %s, which serves goal %s; link it elsewhere first" % (a.id, it["initiative"], g))
        lk.append({"event": "edit", "id": a.id, "changes": ch, "by": a.by, "reason": a.reason.strip()})
        return "%s edited: %s" % (a.id, ", ".join(sorted(ch)))


def do_link(root, a):
    with Locked(root) as lk:
        st = load(root)
        it = open_item(st, a.id)
        ini = get_init(st, a.initiative)
        need(not ini["closed"], "%s is closed; no lug can join it" % a.initiative)
        need(it.get("initiative") != a.initiative, "%s already belongs to %s" % (a.id, a.initiative))
        need(not it.get("initiative") or (a.reason and a.reason.strip()), "%s belongs to %s; moving it needs --reason" % (a.id, it.get("initiative")))
        need(not it.get("goal") or str(it["goal"]) == str(ini["goal"]),
             "%s serves goal %s but %s serves goal %s; edit the lug's goal first" % (a.id, it["goal"], a.initiative, ini["goal"]))
        ev = {"event": "link", "id": a.id, "initiative": a.initiative, "from": it.get("initiative"), "by": a.by,
              "reason": (a.reason or "").strip() or "grouped under %s" % a.initiative}
        lk.append(ev)
        if not it.get("goal"):
            lk.append({"event": "edit", "id": a.id, "changes": {"goal": ini["goal"]}, "by": a.by, "reason": "goal taken from %s" % a.initiative})
        return "%s -> %s %s" % (a.id, a.initiative, ini["title"])


def do_claim(root, a):
    need(a.lease and a.lease > 0, "--lease must be a positive number of minutes")
    with Locked(root) as lk:
        st = load(root)
        it = open_item(st, a.id)
        need(it["status"] not in CLOSED, "%s is %s and cannot be claimed" % (a.id, it["status"]))
        need(it["status"] != "blocked", "%s is blocked" % a.id)
        c = live_claim(it)
        need(not c or c["by"] == a.by, "%s is claimed by %s until %s" % (a.id, c and c["by"], c and c["until"]))
        if it["kind"] == "autopilot":
            ini = st["inits"].get(it.get("initiative"))
            need(ini is not None, "%s is in no initiative, so it has no autopilot budget" % a.id)
            need(ini["owner_signoff"].get("status") == "yes", "%s has no owner sign-off yet, so %s has no autopilot budget" % (ini["id"], a.id))
        t = now()
        until = iso(secs(t) + int(round(a.lease * 60)))
        lk.append({"event": "claim", "id": a.id, "by": a.by, "lease": a.lease, "until": until, "renew": bool(c)})
        return "%s %s by %s until %s" % (a.id, "renewed" if c else "claimed", a.by, until)


def do_release(root, a):
    with Locked(root) as lk:
        st = load(root)
        it = open_item(st, a.id)
        c = it.get("claim")
        need(c, "%s is not claimed" % a.id)
        need(c["by"] == a.by or not live_claim(it), "%s is claimed by %s until %s; only they can release it" % (a.id, c["by"], c["until"]))
        lk.append({"event": "release", "id": a.id, "by": a.by, "reason": (a.reason or "").strip() or "released"})
        return "%s released" % a.id


# ---------- writing check ----------
PLACEHOLDERS = {"tbd", "tba", "todo", "to do", "n/a", "na", "none", "x", "xx", "xxx", "misc", "-", "--", "?", "??", "...",
                "placeholder", "fill in", "fill me in", "later", "etc", "same", "see above", "lorem ipsum"}
PLACEHOLDER_RE = re.compile(r"(\btbd\b|\btba\b|\btodo\s*:|\bn/a\b|\.\.\.|…|\blorem\b|\bipsum\b|\bxxx+\b|\bfill (me )?in\b|\bplaceholder\b)", re.I)
# "TODO" in capitals is a marker left to fill in; a lower-case "todo" can be the product's own word (a todo list)
TODO_RE = re.compile(r"\bTODO\b")
MIN_WORDS = {"title": 4, "outcome": 8, "why_now": 6, "scope_in": 3, "scope_out": 2, "done_when": 8}
VAGUE_RE = re.compile(r"\b(better|improved?|improves|nicer|good|great|easier|faster|robust|properly|appropriate(ly)?|as needed|somehow|"
                      r"more or less|ideally|hopefully|reasonabl[ey]|polished|optimi[sz]ed|enhanced?|streamlined?)\b", re.I)
CHECK_RE = re.compile(r"(\d|\b(pass(es|ed)?|test(s|ed)?|prints?|shows?|returns?|lists?|renders?|live|deployed|merged|exists?|"
                      r"written( down)?|recorded|claimed|signed|confirmed|sent|published|counts?|measured|logged|answers?|"
                      r"opens?|loads?|every|all|each|at least|at or above|or more|no more than|zero|none of|one|two|three|"
                      r"four|five|ten|first)\b)", re.I)


def words(s):
    return len(re.findall(r"[A-Za-z0-9][\w'/-]*", s or ""))


def text_problem(field, text):
    """Why this text is not a written section, or None when it is."""
    s = (text or "").strip()
    if not s:
        return "%s is empty" % INIT_LABELS.get(field, field)
    low = re.sub(r"[\s.!]+$", "", s.lower())
    if low in PLACEHOLDERS or PLACEHOLDER_RE.search(s) or TODO_RE.search(s):
        return "%s is placeholder text (%r)" % (INIT_LABELS.get(field, field), s[:40])
    n = MIN_WORDS.get(field)
    if n and words(s) < n:
        return "%s is too short to stand on its own (%d words, at least %d)" % (INIT_LABELS.get(field, field), words(s), n)
    return None


def checkable_problem(text):
    """A done_when must say what someone can look at and confirm: a number, or a concrete observable result,
    and no vague comparative ("better", "improved") unless a number pins it down."""
    s = text or ""
    if not CHECK_RE.search(s):
        return "done when is not checkable: name a result someone can look at (a count, a test that passes, a page that is live, something written down)"
    v = VAGUE_RE.search(s)
    if v and not re.search(r"\d", s):
        return "done when is not checkable: %r is a judgment, not a check; pin it to a number or an observable result" % v.group(0)
    return None


def agreed_goals(root):
    """Goal numbers agreed with the owner, read from .wheel/spoke.md ("## Owner's goals" or "## Goals"), with their
    short labels. Empty when the project has no spoke file (then any whole number is accepted)."""
    p = os.path.join(root, ".wheel", "spoke.md")
    goals, on = {}, False
    if not os.path.exists(p):
        return goals
    for line in open(p, encoding="utf-8"):
        if line.startswith("## "):
            on = bool(re.match(r"##\s+(owner'?s\s+)?(agreed\s+)?goals\b", line.strip(), re.I))
            continue
        m = re.match(r"\s*(\d+)\.\s+(.*)", line) if on else None
        if m:
            body = m.group(2).strip()
            b = re.match(r"\*\*(.+?)\*\*\s*(.*)", body)
            label = b.group(1).rstrip(":") if b else body.split(":")[0]
            text = re.sub(r"\s*\*?\(later\)\*?\s*$", "", (b.group(2) if b else body)).strip()
            goals[m.group(1)] = {"label": label.strip(), "text": text[:1].upper() + text[1:], "later": "(later)" in body}
    return goals


def init_problems(ini, goals):
    out = []
    for f in INIT_FIELDS:
        if f == "goal":
            g = str(ini.get("goal") or "").strip()
            if not g:
                out.append("goal is missing")
            elif not g.isdigit():
                out.append("goal must be an agreed goal number, not %r" % g)
            elif goals and g not in goals:
                out.append("goal %s is not one of the agreed goals (%s)" % (g, ", ".join(sorted(goals))))
            continue
        p = text_problem(f, ini.get(f))
        if p:
            out.append(p)
    if not any(p.startswith("done when") for p in out):
        p = checkable_problem(ini.get("done_when"))
        if p:
            out.append(p)
    return out


# production and deploy work is the owner's: an autopilot lug must not apply a migration to production, deploy to
# production, change production data or settings, or need credentials (trial 1 of the spoke wake)
OWNER_WORK = [
    (re.compile(r"\bmigrat\w*\b[^.;]{0,60}\bprod(uction)?\b|\bprod(uction)?\b[^.;]{0,60}\bmigrat\w*\b", re.I),
     "applies a migration to production"),
    (re.compile(r"\bdeploy\w*\b[^.;]{0,60}\bprod(uction)?\b|\bprod(uction)?\b[^.;]{0,40}\bdeploy\w*\b|\bpromote\w*\b[^.;]{0,30}\bprod(uction)?\b", re.I),
     "deploys to production"),
    (re.compile(r"\bprod(uction)?\s+(data|database|db|settings?|config\w*|secrets?|env\w*)\b", re.I),
     "changes production data or settings"),
    (re.compile(r"\bcredentials?\b|\bapi[ -]?keys?\b|\bpasswords?\b", re.I), "needs credentials"),
]
NEGATION = re.compile(r"\b(no|not|without|never|nor|doesn'?t|don'?t)\b[^.;]{0,25}$", re.I)


def owner_work_reason(*texts):
    """Why an autopilot lug's title or check looks like owner work, or None."""
    for text in texts:
        for rx, why in OWNER_WORK:
            for m in rx.finditer(text or ""):
                if not NEGATION.search(text[: m.start()]):
                    return why
    return None


def lint(root, st):
    goals = agreed_goals(root)
    errors, pending = [], []
    for iid in sorted(st["inits"]):
        ini = st["inits"][iid]
        for p in init_problems(ini, goals):
            errors.append((iid, p))
        if ini["closed"] and ini["open"]:
            errors.append((iid, "closed with %d open lug(s)" % ini["open"]))
        if not ini["closed"] and ini["lugs"] == 0:
            errors.append((iid, "holds no lugs: link the lugs that deliver it, or close it"))
        if ini["owner_signoff"].get("status") != "yes" and not ini["closed"]:
            pending.append((iid, "owner sign-off pending: its lugs get no autopilot budget until the owner says yes"))
    for it in open_items(st):
        lid = it["id"]
        if not str(it.get("goal") or "").strip():
            errors.append((lid, "lug has no goal"))
        elif goals and str(it["goal"]) not in goals:
            errors.append((lid, "lug's goal %s is not one of the agreed goals" % it["goal"]))
        ini = st["inits"].get(it.get("initiative"))
        if not it.get("initiative"):
            errors.append((lid, "lug is in no initiative (lug link %s I-###)" % lid))
        elif ini is None:
            errors.append((lid, "lug points at %s, which does not exist" % it["initiative"]))
        elif str(ini["goal"]) != str(it.get("goal")):
            errors.append((lid, "lug serves goal %s but its initiative %s serves goal %s" % (it.get("goal"), ini["id"], ini["goal"])))
        if it["kind"] == "autopilot":
            c = (it.get("check") or "").strip()
            if not c:
                errors.append((lid, "autopilot lug has no check"))
            elif text_problem("check", c) or words(c) < 3:
                errors.append((lid, "autopilot lug's check is not a real check (%r)" % c[:40]))
            why = owner_work_reason(it.get("title"), c)
            if why:
                errors.append((lid, "autopilot lug looks like owner work: %s" % why))
        t = (it.get("title") or "").strip()
        if not t or re.sub(r"[\s.!]+$", "", t.lower()) in PLACEHOLDERS or PLACEHOLDER_RE.search(t) or TODO_RE.search(t):
            errors.append((lid, "lug title is empty or placeholder"))
    return errors, pending


def do_lint(root, a):
    st = load(root)
    errors, pending = lint(root, st)
    if a.json:
        return json.dumps({"errors": [{"id": i, "problem": p} for i, p in errors],
                           "pending": [{"id": i, "problem": p} for i, p in pending]}, ensure_ascii=False, indent=1), (1 if errors else 0)
    lines = ["%s: %s" % e for e in errors] + ["%s: %s" % p for p in pending]
    lines.append("lint: %d problem(s), %d sign-off(s) pending (%d initiatives, %d open lugs)" % (len(errors), len(pending), len(st["inits"]), len(st["order"])))
    return "\n".join(lines), (1 if errors else 0)


# ---------- verify ----------
REQUIRED = {
    "add": ("id", "title", "value", "effort", "kind", "status", "rank"),
    "status": ("id", "status", "reason"),
    "rank": ("id", "rank", "reason"),
    "edit": ("id", "changes", "reason"),
    "link": ("id", "initiative"),
    "claim": ("id", "by", "until"),
    "release": ("id", "by"),
    "init_add": ("id",) + INIT_FIELDS,
    "init_edit": ("id", "changes", "reason"),
    "init_signoff": ("id", "who"),
    "init_close": ("id", "reason"),
}


def verify(root):
    """Replay the whole log and report every problem as (line, message)."""
    problems = []
    events = read_events(root, problems)
    st = new_state()
    for ev in events:
        n, kind, iid = ev.get("_line"), ev.get("event"), ev.get("id")
        if kind not in EVENTS:
            problems.append((n, "unknown event %r" % kind))
            continue
        miss = [k for k in REQUIRED[kind] if ev.get(k) in (None, "")]
        if not ev.get("at"):
            miss.append("at")
        if miss:
            problems.append((n, "%s %s is missing %s" % (kind, iid, ", ".join(miss))))
            if "id" in miss:
                continue
        if kind == "add":
            if iid in st["items"]:
                problems.append((n, "lug id %s is used twice" % iid))
                continue
            if not re.match(r"^B-\d+$", str(iid)):
                problems.append((n, "lug id %r is not B-###" % iid))
            if ev.get("status") not in ("proposed", "ready"):
                problems.append((n, "%s is added as %r (a new lug starts proposed or ready)" % (iid, ev.get("status"))))
            r = ev.get("rank")
            if not isinstance(r, int) or not 1 <= r <= len(st["order"]) + 1:
                problems.append((n, "%s is added at rank %r, outside 1..%d" % (iid, r, len(st["order"]) + 1)))
            if ev.get("kind") not in KINDS:
                problems.append((n, "%s has kind %r" % (iid, ev.get("kind"))))
            if ev.get("anchor") and ev["anchor"] not in st["order"]:
                problems.append((n, "%s is placed next to %s, which is not an open lug" % (iid, ev["anchor"])))
            if ev.get("initiative") and ev["initiative"] not in st["inits"]:
                problems.append((n, "%s joins %s, which does not exist yet" % (iid, ev["initiative"])))
        elif kind == "init_add":
            if iid in st["inits"]:
                problems.append((n, "initiative id %s is used twice" % iid))
                continue
            if not re.match(r"^I-\d+$", str(iid)):
                problems.append((n, "initiative id %r is not I-###" % iid))
        elif kind.startswith("init_"):
            ini = st["inits"].get(iid)
            if ini is None:
                problems.append((n, "%s refers to %s, which does not exist" % (kind, iid)))
                continue
            if kind == "init_close" and progress(st, iid)["open"]:
                problems.append((n, "%s closed while %d lug(s) were open" % (iid, progress(st, iid)["open"])))
            if ini["closed"] and kind != "init_signoff":
                problems.append((n, "%s on %s after it was closed" % (kind, iid)))
        else:
            it = st["items"].get(iid)
            if it is None:
                problems.append((n, "%s refers to %s, which does not exist" % (kind, iid)))
                continue
            if kind == "status":
                if ev.get("from") and ev["from"] != it["status"]:
                    problems.append((n, "%s says it moved from %s, but it was %s (events out of order?)" % (iid, ev["from"], it["status"])))
                if ev.get("status") not in allowed_moves(it):
                    problems.append((n, "%s moved %s -> %s, which the flow does not allow" % (iid, it["status"], ev.get("status"))))
                elif ev["status"] == "done" and it["kind"] == "autopilot":
                    builders = {e.get("by") for e in it["history"] if e.get("event") == "status" and e.get("status") in ("doing", "checking")}
                    if ev.get("by") in builders:
                        problems.append((n, "%s (autopilot) was closed by its builder %s" % (iid, ev.get("by"))))
            elif kind == "rank":
                if iid not in st["order"]:
                    problems.append((n, "%s is ranked while closed" % iid))
                elif not isinstance(ev.get("rank"), int) or not 1 <= ev["rank"] <= len(st["order"]):
                    problems.append((n, "%s ranked %r, outside 1..%d" % (iid, ev.get("rank"), len(st["order"]))))
            elif kind == "link":
                ini = st["inits"].get(ev.get("initiative"))
                if ini is None:
                    problems.append((n, "%s links to %s, which does not exist" % (iid, ev.get("initiative"))))
                elif ini["closed"]:
                    problems.append((n, "%s links to %s after it was closed" % (iid, ev.get("initiative"))))
            elif kind == "claim":
                c = live_claim(it, ev.get("at"))
                if c and c["by"] != ev.get("by"):
                    problems.append((n, "%s claimed by %s while %s held it until %s" % (iid, ev.get("by"), c["by"], c["until"])))
                if it["status"] in CLOSED:
                    problems.append((n, "%s claimed while %s" % (iid, it["status"])))
            elif kind == "release" and not it.get("claim"):
                problems.append((n, "%s released while not claimed" % iid))
        apply(st, ev)
        if kind in ("add", "status", "rank") and len(set(st["order"])) != len(st["order"]):
            problems.append((n, "two open lugs share a place in the order"))
    st = fold(events)
    ranks = [st["items"][i]["rank"] for i in st["order"]]
    if ranks != list(range(1, len(ranks) + 1)):
        problems.append((0, "open lug ranks are not 1..%d" % len(ranks)))
    for it in st["items"].values():
        if (it["status"] in CLOSED) == (it["id"] in st["order"]):
            problems.append((0, "%s is %s but %s the ranked order" % (it["id"], it["status"], "in" if it["id"] in st["order"] else "not in")))
        if it.get("initiative") and it["initiative"] not in st["inits"]:
            problems.append((0, "%s points at %s, which does not exist" % (it["id"], it["initiative"])))
    return problems, len(events)


def do_verify(root):
    problems, n = verify(root)
    out = ["line %d: %s" % (ln, msg) if ln else "state: %s" % msg for ln, msg in problems]
    out.append("verify: %d event(s) replayed, %s" % (n, "%d problem(s)" % len(problems) if problems else "clean"))
    return "\n".join(out), (1 if problems else 0)


# ---------- initiatives ----------
def init_args(a):
    return {f: getattr(a, f, None) for f in INIT_FIELDS}


def do_init_add(root, a):
    fields = {k: (v.strip() if isinstance(v, str) else v) for k, v in init_args(a).items()}
    probs = init_problems(fields, agreed_goals(root))
    need(not probs, "the initiative is not written well enough yet:\n  - " + "\n  - ".join(probs))
    with Locked(root) as lk:
        events = read_events(root)
        iid = next_id(events, "I-", ("init_add",))
        ev = dict({"event": "init_add", "id": iid}, **fields)
        ev.update(by=a.by, reason=(a.reason or "").strip() or "new initiative for goal %s" % fields["goal"])
        lk.append(ev)
        return "%s %s (goal %s; owner sign-off pending)" % (iid, fields["title"], fields["goal"])


def do_init_edit(root, a):
    need(a.reason and a.reason.strip(), "every edit needs --reason")
    with Locked(root) as lk:
        st = load(root)
        ini = get_init(st, a.id)
        need(not ini["closed"], "%s is closed" % a.id)
        ch = {k: v.strip() for k, v in init_args(a).items() if v is not None and v.strip() != (ini.get(k) or "")}
        need(ch, "nothing to change")
        probs = init_problems(dict(ini, **ch), agreed_goals(root))
        need(not probs, "the initiative would not be written well enough:\n  - " + "\n  - ".join(probs))
        if "goal" in ch:
            bad = [l["id"] for l in lugs_of(st, a.id) if l["status"] not in CLOSED and str(l.get("goal")) != str(ch["goal"])]
            need(not bad, "lugs %s serve goal %s; edit or move them first" % (", ".join(bad), ini["goal"]))
        lk.append({"event": "init_edit", "id": a.id, "changes": ch, "by": a.by, "reason": a.reason.strip()})
        reset = any(k in SIGNED_FIELDS for k in ch) and ini["owner_signoff"].get("status") == "yes"
        return "%s edited: %s%s" % (a.id, ", ".join(sorted(ch)), "; owner sign-off back to pending" if reset else "")


def do_init_signoff(root, a):
    need(a.who and a.who.strip(), "--who is required: the owner, and where they said yes")
    with Locked(root) as lk:
        st = load(root)
        ini = get_init(st, a.id)
        need(ini["owner_signoff"].get("status") != "yes", "%s is already signed off by %s" % (a.id, ini["owner_signoff"].get("who")))
        probs = init_problems(ini, agreed_goals(root))
        need(not probs, "%s cannot be signed off until it is written well enough:\n  - %s" % (a.id, "\n  - ".join(probs)))
        lk.append({"event": "init_signoff", "id": a.id, "who": a.who.strip(), "by": a.by, "reason": (a.reason or "").strip() or "owner said yes"})
        return "%s signed off by %s" % (a.id, a.who.strip())


def do_init_close(root, a):
    need(a.reason and a.reason.strip(), "closing an initiative needs --reason")
    with Locked(root) as lk:
        st = load(root)
        ini = get_init(st, a.id)
        need(not ini["closed"], "%s is already closed" % a.id)
        open_ids = [l["id"] for l in lugs_of(st, a.id) if l["status"] not in CLOSED]
        need(not open_ids, "%s cannot close while lugs are open: %s" % (a.id, ", ".join(open_ids)))
        lk.append({"event": "init_close", "id": a.id, "by": a.by, "reason": a.reason.strip(), "done": ini["done"], "counted": ini["counted"]})
        return "%s closed: %d of %d lugs done" % (a.id, ini["done"], ini["counted"])


def init_brief(ini):
    d = {k: ini.get(k) for k in ("id",) + INIT_FIELDS + ("owner_signoff", "closed", "status", "done", "counted", "dropped", "open")}
    return d


def do_init_show(root, a):
    st = load(root)
    inits = [get_init(st, a.id)] if a.id else [st["inits"][k] for k in sorted(st["inits"])]
    if a.json:
        return json.dumps([init_brief(i) for i in inits], ensure_ascii=False, indent=1)
    if not inits:
        return "No initiatives."
    return "\n\n".join(init_block(st, i, table=False) for i in inits)


# ---------- views ----------
def open_items(st):
    return [st["items"][i] for i in st["order"]]


def cell(s):
    return str(s if s is not None else "").replace("|", "/").replace("\n", " ")


def render_md(st):
    done = sorted([i for i in st["items"].values() if i["status"] == "done"], key=lambda i: i["closed"] or "", reverse=True)[:10]
    lines = ["# Lugs", "", "Force-ranked, one unique rank per open lug. Generated from .wheel/backlog.jsonl by backlog.py render; do not edit by hand. "
             "The roadmap (goal, initiative, lugs, history) is in .wheel/ROADMAP.md.", ""]
    if st["order"]:
        lines += ["| rank | id | title | kind | status | value/effort | initiative |", "|---:|---|---|---|---|---|---|"]
        for it in open_items(st):
            lines.append("| %s | %s | %s | %s | %s | %d/%d | %s |" % (it["rank"], it["id"], cell(it["title"]), it["kind"], it["status"], it["value"], it["effort"], it.get("initiative") or "-"))
    else:
        lines.append("Nothing open.")
    lines += ["", "## Recently done", ""]
    if done:
        lines += ["- %s %s (%s)" % (i["id"], i["title"], (i["closed"] or "")[:10]) for i in done]
    else:
        lines.append("Nothing done yet.")
    return "\n".join(lines) + "\n"


def signoff_text(ini):
    s = ini["owner_signoff"]
    if s.get("status") == "yes":
        return "signed off by %s on %s" % (s.get("who"), (s.get("at") or "")[:10])
    if s.get("reset"):
        return "pending (the text changed on %s after it was signed off)" % s["reset"][:10]
    return "pending"


def init_block(st, ini, table=True):
    head = "### %s %s" % (ini["id"], ini["title"])
    state = "%s of %s lug%s done" % (ini["done"], ini["counted"], "" if ini["counted"] == 1 else "s")
    if ini["dropped"]:
        state += " (%d dropped, not counted)" % ini["dropped"]
    bits = [state, ini["status"] + (", closed %s" % ini["closed"][:10] if ini["closed"] else ""), "owner sign-off: " + signoff_text(ini)]
    out = [head, "", "*" + " · ".join(bits) + "*", "",
           "- **Outcome:** " + (ini["outcome"] or ""),
           "- **Why now:** " + (ini["why_now"] or ""),
           "- **In scope:** " + (ini["scope_in"] or ""),
           "- **Not in scope:** " + (ini["scope_out"] or ""),
           "- **Done when:** " + (ini["done_when"] or "")]
    if table:
        lugs = lugs_of(st, ini["id"])
        live = sorted([l for l in lugs if l["status"] not in CLOSED], key=lambda l: l["rank"])
        closed = sorted([l for l in lugs if l["status"] in CLOSED], key=lambda l: l["closed"] or "")
        out.append("")
        if live:
            out += ["| rank | lug | kind | status |", "|---:|---|---|---|"]
            for l in live:
                st_txt = l["status"] + (" (claimed by %s)" % live_claim(l)["by"] if live_claim(l) else "")
                out.append("| %s | %s %s | %s | %s |" % (l["rank"], l["id"], cell(l["title"]), "you" if l["kind"] == "owner" else "autopilot", st_txt))
        for l in closed:
            out.append("- %s %s %s, %s (%s)" % ("Done:" if l["status"] == "done" else "Dropped:", l["id"], l["title"], (l["closed"] or "")[:10], l.get("status_by") or "?"))
        if not lugs:
            out.append("No lugs yet.")
    return "\n".join(out)


def roadmap_data(root, st):
    goals = agreed_goals(root)
    keys = sorted(set(goals) | {str(i["goal"]) for i in st["inits"].values()}, key=lambda g: (not g.isdigit(), int(g) if g.isdigit() else 0, g))
    data = {"goals": [], "unlinked": [], "history": []}
    for g in keys:
        inits = sorted([i for i in st["inits"].values() if str(i["goal"]) == g], key=lambda i: i["id"])
        data["goals"].append({"goal": g, "label": goals.get(g, {}).get("label"), "text": goals.get(g, {}).get("text"),
                              "later": goals.get(g, {}).get("later", False),
                              "initiatives": [dict(init_brief(i), lugs=[brief(l) for l in sorted(lugs_of(st, i["id"]), key=lambda l: (l["rank"] is None, l["rank"] or 0, l["id"]))]) for i in inits]})
    data["unlinked"] = [brief(l) for l in open_items(st) if l.get("initiative") not in st["inits"]]
    for l in sorted([l for l in st["items"].values() if l["status"] in CLOSED], key=lambda l: l["closed"] or "", reverse=True):
        data["history"].append({"date": (l["closed"] or "")[:10], "id": l["id"], "title": l["title"], "status": l["status"],
                                "who": l.get("status_by"), "reason": l.get("status_reason"), "initiative": l.get("initiative")})
    for i in sorted([i for i in st["inits"].values() if i["closed"]], key=lambda i: i["closed"], reverse=True):
        data["history"].append({"date": i["closed"][:10], "id": i["id"], "title": i["title"], "status": "closed",
                                "who": i["history"][-1].get("by") if i["history"] else None, "reason": i.get("close_reason")})
    data["history"].sort(key=lambda h: h["date"], reverse=True)
    return data


def roadmap_md(root, st):
    data = roadmap_data(root, st)
    out = ["# Roadmap", "",
           "Goal, then the initiatives that serve it, then their lugs, then what is finished. Generated from .wheel/backlog.jsonl "
           "by backlog.py roadmap; do not edit by hand. Progress counts done lugs against lugs not dropped.", ""]
    for g in data["goals"]:
        name = "Goal %s" % g["goal"] + (": %s" % g["label"] if g["label"] else "") + (" (later)" if g["later"] else "")
        out += ["## " + name, ""]
        if g["text"]:
            out += [g["text"], ""]
        inits = [st["inits"][i["id"]] for i in g["initiatives"]]
        if not inits:
            out += ["No initiative yet.", ""]
        for ini in inits:
            out += [init_block(st, ini), ""]
    if data["unlinked"]:
        out += ["## Lugs not yet in an initiative", "", "| rank | lug | kind | status | goal |", "|---:|---|---|---|---|"]
        out += ["| %s | %s %s | %s | %s | %s |" % (l["rank"], l["id"], cell(l["title"]), l["kind"], l["status"], l.get("goal") or "-") for l in data["unlinked"]]
        out.append("")
    out += ["## Completed history", ""]
    if data["history"]:
        for h in data["history"]:
            verb = {"done": "done", "dropped": "dropped", "closed": "initiative closed"}[h["status"]]
            out.append("- %s · %s %s · %s by %s%s" % (h["date"], h["id"], h["title"], verb, h["who"] or "?",
                                                     " (%s)" % h["reason"] if h.get("reason") and h["status"] != "done" else ""))
    else:
        out.append("Nothing finished yet.")
    return "\n".join(out).rstrip() + "\n"


def write_views(root):
    st = load(root)
    os.makedirs(os.path.join(root, ".wheel"), exist_ok=True)
    for name, text in (("BACKLOG.md", render_md(st)), ("ROADMAP.md", roadmap_md(root, st))):
        with open(os.path.join(root, ".wheel", name), "w", encoding="utf-8") as f:
            f.write(text)
    return st


def do_render(root):
    st = write_views(root)
    return "wrote .wheel/BACKLOG.md and .wheel/ROADMAP.md in %s (%d open lugs, %d initiatives)" % (root, len(st["order"]), len(st["inits"]))


def do_roadmap(root, a):
    st = write_views(root)
    if a.json:
        return json.dumps(roadmap_data(root, st), ensure_ascii=False, indent=1)
    return roadmap_md(root, st)


def brief(it):
    d = {k: it.get(k) for k in ("rank", "id", "title", "kind", "status", "value", "effort", "goal", "initiative", "check", "source", "reason")}
    c = live_claim(it)
    d["claimed_by"] = c["by"] if c else None
    if it["status"] in CLOSED:
        d.update(closed=it.get("closed"), closed_by=it.get("status_by"))
    return d


def do_show(root, a):
    st = load(root)
    rows = open_items(st)
    if a.all:
        rows = rows + sorted([i for i in st["items"].values() if i["rank"] is None], key=lambda i: i["id"])
    if a.json:
        return json.dumps([brief(i) for i in rows], ensure_ascii=False, indent=1)
    if not rows:
        return "Nothing open."
    return "\n".join("%s %-6s %-9s %-10s v%d/e%d %-6s %s" % (("#%d" % i["rank"]) if i["rank"] else "-", i["id"], i["kind"], i["status"], i["value"], i["effort"], i.get("initiative") or "-", i["title"]) for i in rows)


def pickable(st, it):
    ini = st["inits"].get(it.get("initiative"))
    return (it["kind"] == "autopilot" and it["status"] == "ready" and not live_claim(it)
            and ini is not None and ini["owner_signoff"].get("status") == "yes" and not ini["closed"])


def do_top(root, a):
    st = load(root)
    rows = [i for i in open_items(st) if i["status"] != "blocked" and (not a.kind or i["kind"] == a.kind) and (not a.pickable or pickable(st, i))][: a.n]
    if a.json:
        return json.dumps([brief(i) for i in rows], ensure_ascii=False, indent=1)
    return "\n".join("#%d %s [%s, %s] %s" % (i["rank"], i["id"], i["kind"], i["status"], i["title"]) for i in rows) or "Nothing open."


def do_history(root, iid):
    st = load(root)
    it = st["inits"].get(iid) or open_item(st, iid)
    out = ["%s %s" % (iid, it["title"])]
    for e in it["history"]:
        extra = {k: v for k, v in e.items() if k not in ("at", "event", "id", "title", "_line") and v not in (None, "")}
        out.append("%s %-12s %s" % (e.get("at"), e["event"], json.dumps(extra, ensure_ascii=False)))
    return "\n".join(out)


def do_test():
    here = os.path.dirname(os.path.abspath(__file__))
    cases = os.path.join(here, "fixtures", "backlog", "cases.py")
    if not os.path.exists(cases):
        return "no fixtures beside this copy; run the test from the wheel kit (tools/kit/backlog.py test)", 2
    import runpy
    mod = runpy.run_path(cases)
    return None, mod["run"](os.path.join(here, "backlog.py"))


def build_parser(prog="backlog.py"):
    p = argparse.ArgumentParser(prog=prog, description=__doc__.split("\n")[0])
    p.add_argument("--root", help="project root (default: nearest folder above with .wheel/)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def by(s, what="who is doing this (required on every write)"):
        s.add_argument("--by", required=True, help=what)
        return s
    s = by(sub.add_parser("add", help="add a lug"))
    s.add_argument("title")
    s.add_argument("--value", type=int, required=True)
    s.add_argument("--effort", type=int, required=True)
    s.add_argument("--kind", required=True)
    s.add_argument("--source", required=True)
    s.add_argument("--goal")
    s.add_argument("--initiative")
    s.add_argument("--check")
    s.add_argument("--reason")
    s.add_argument("--above")
    s.add_argument("--below")
    s.add_argument("--status")
    s = by(sub.add_parser("status", help="move a lug through the flow"))
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
    s = by(sub.add_parser("link", help="put a lug in an initiative"))
    s.add_argument("id")
    s.add_argument("initiative")
    s.add_argument("--reason")
    s = by(sub.add_parser("claim", help="claim a lug for a worker, with a lease"), "the worker claiming it")
    s.add_argument("id")
    s.add_argument("--lease", type=float, required=True, help="minutes")
    s = by(sub.add_parser("release"), "the worker releasing it")
    s.add_argument("id")
    s.add_argument("--reason")
    ini = sub.add_parser("initiative", help="initiatives: add, edit, signoff, close, show")
    isub = ini.add_subparsers(dest="icmd", required=True)
    for name in ("add", "edit"):
        s = by(isub.add_parser(name))
        if name == "add":
            s.add_argument("title")
        else:
            s.add_argument("id")
            s.add_argument("--title")
        s.add_argument("--goal", required=name == "add")
        for f in ("outcome", "why-now", "scope-in", "scope-out", "done-when"):
            s.add_argument("--" + f, dest=f.replace("-", "_"), required=name == "add")
        s.add_argument("--reason", required=name == "edit")
    s = by(isub.add_parser("signoff"))
    s.add_argument("id")
    s.add_argument("--who", required=True, help="the owner, and where they said yes")
    s.add_argument("--reason")
    s = by(isub.add_parser("close"))
    s.add_argument("id")
    s.add_argument("--reason", required=True)
    s = isub.add_parser("show")
    s.add_argument("id", nargs="?")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("show")
    s.add_argument("--all", action="store_true")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("top")
    s.add_argument("--kind", choices=KINDS)
    s.add_argument("--pickable", action="store_true", help="only ready autopilot lugs with budget (initiative signed off) and no live claim")
    s.add_argument("-n", type=int, default=3)
    s.add_argument("--json", action="store_true")
    sub.add_parser("render")
    s = sub.add_parser("roadmap")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("lint")
    s.add_argument("--json", action="store_true")
    sub.add_parser("verify")
    s = sub.add_parser("history")
    s.add_argument("id")
    sub.add_parser("test")
    return p


def main(argv=None, prog=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    i = 0
    while i < len(argv) and argv[i].startswith("--root"):
        i += 1 if "=" in argv[i] else 2
    if argv[i:i + 1] == ["lug"]:  # "backlog.py lug link ..." reads like "lug link ..."
        del argv[i]
    a = build_parser(prog or os.path.basename(sys.argv[0]) or "backlog.py").parse_args(argv)
    if a.cmd == "test":
        msg, code = do_test()
        if msg:
            print(msg)
        return code
    root = find_root(explicit=a.root)
    code = 0
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
        elif a.cmd == "link":
            out = do_link(root, a)
        elif a.cmd == "claim":
            out = do_claim(root, a)
        elif a.cmd == "release":
            out = do_release(root, a)
        elif a.cmd == "initiative":
            out = {"add": do_init_add, "edit": do_init_edit, "signoff": do_init_signoff, "close": do_init_close, "show": do_init_show}[a.icmd](root, a)
        elif a.cmd == "show":
            out = do_show(root, a)
        elif a.cmd == "top":
            out = do_top(root, a)
        elif a.cmd == "render":
            out = do_render(root)
        elif a.cmd == "roadmap":
            out = do_roadmap(root, a)
        elif a.cmd == "lint":
            out, code = do_lint(root, a)
        elif a.cmd == "verify":
            out, code = do_verify(root)
        else:
            out = do_history(root, a.id)
    except Refused as e:
        sys.stderr.write("lug: refused: %s\n" % e)
        return 1
    if a.cmd in WRITES and not (a.cmd == "initiative" and a.icmd == "show"):
        try:
            write_views(root)
        except OSError:
            pass
    print(out)
    return code


if __name__ == "__main__":
    sys.exit(main())
