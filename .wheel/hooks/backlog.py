#!/usr/bin/env python3
"""Lugs and initiatives for one project: a force-ranked plan and roadmap (kit part P-019). Stdlib only.
The one git write (B-297): after a write run from a session (no --root), the log and its rendered views are committed on the
live checkout's main branch at once, alone (a pathspec-only commit under the backlog lock), so no session sweeps another
session's lug rows into its own commit. WHEEL_LUG_NOCOMMIT=1 turns this off; a checkout off main or mid-merge is left as is.

Lugs are the work items; initiatives group the lugs that deliver one agreed goal. Every write names who made it (--by).
  lug add TITLE --value 1-5 --effort 1-5 --kind owner|autopilot --source WHO --by WHO [--goal G] [--initiative I-###]
          [--check HOW] [--reason WHY] [--above ID | --below ID] [--status proposed|ready]
          [--urgency next_session|whenever] [--class build|maintain]
  lug status ID proposed|ready|doing|checking|done|dropped|blocked --reason WHY --by WHO [--proof TOKEN] [--repo SPOKE]
  lug rank ID N --reason WHY [--pin|--unpin] --by WHO      lug move ID --above|--below OTHER --reason WHY [--pin] --by WHO
  lug edit ID [--title T] [--goal G] [--value V] [--effort E] [--kind K] [--check C] [--urgency U] [--class C] --reason WHY --by WHO
  lug edit ID --after B-117[,B-118] --reason WHY --by WHO   (a blocked lug waits on those lugs)
  lug release-deps --by WHO                                 (blocked lugs whose --after lugs are all done go back to ready)
  lug link ID I-### --by WHO [--reason WHY]                 (each lug belongs to exactly one initiative)
  lug claim ID --by WORKER --lease MINUTES                  lug release ID --by WORKER [--reason WHY]
  lug initiative add TITLE --goal N --outcome .. --why-now .. --scope-in .. --scope-out .. --done-when .. --by WHO
  lug initiative edit I-### [--title|--goal|--outcome|--why-now|--scope-in|--scope-out|--done-when ..] --reason WHY --by WHO
  lug initiative signoff I-### --who "the owner (source)" --by WHO      lug initiative close I-### --reason WHY --by WHO
  lug initiative show [I-###] [--json]
  lug show [--all] [--json]   lug top [--kind K] [--class build|maintain] [--pickable|--needs-check] [-n N] [--split] [--json]   lug history ID
  lug roadmap [--json]        lug render     lug lint [--json]     lug verify     lug test
  lug statement ID TEXT --by WHO   lug changelog [--json] [--since YYYY-MM-DD]   (status ... done --statement TEXT)
("lug" is lug.py or backlog.py; the same program.)

The log is .wheel/backlog.jsonl in the project root (found by walking up from the current folder, or --root PATH; from a
linked worktree, a session's checkout, it is the live checkout's log, so a session branch never carries a log diff, B-078):
append-only, one JSON event per line {at, event, id, by, ...}. The current state is the fold of the events. Every open
lug (not done/dropped) holds a unique rank 1..N; ranks stay contiguous after any change. Lug ids are B-###, initiative
ids I-###. Rendered views (never edit by hand): .wheel/CHANGELOG.md (what reached main, B-171), .wheel/BACKLOG.md (the ranked lugs) and .wheel/ROADMAP.md
(goal -> initiative -> lugs -> completed history).
kind owner = needs the owner (a decision, a walkthrough, a login, anything outward-facing or hard to undo);
kind autopilot = a builder can do it and an independent checker can prove it (a check is required). Closing an autopilot
lug done needs --proof: the token tools/verify.py prints on a pass it backed with a command that ran (W-175), made with
the machine's proof key (~/.config/wheel/proof.key, or $WHEEL_PROOF_KEY) for this lug and a commit of this repository.
Its check and kind cannot change while it is doing or checking. An autopilot lug
gets no autopilot budget (claim, top --pickable) until its initiative has the owner's sign-off.
urgency (optional) = when the work should be done: "next_session" = meaningful and owner-visible, so it should be done before
the owner's next session; "whenever" (the default) = no deadline. Rule for whoever proposes a lug: an improvement the owner
will see in something he uses, or anything he asked for by a time, is next_session; internal plumbing is whenever.
Done next_session lugs are what the brief calls Highlights; the rest are Change notes.
class (optional) = build or maintain. Maintain is work that keeps the project healthy and current: a lug declared --class maintain,
or any lug in the project's "Keep ... healthy" initiative (its title starts with "Keep" and names healthy or current). Everything
else is build. The class is derived when not declared; `top --json` and `show --json` carry it, and `top --split` lists the
prioritised backlog as a build part and a maintain part, which is what a session reads at startup.
lint requires an explicit urgency on every open lug and keeps value within the goal's ceiling (goal n holds at most 6-n,
a "(later)" goal at most 2), and warns when a lug's title or check says it needs (or comes after) a lug ranked below it;
initiative add and edit print three fresh-reader questions to ask before sign-off. The full scoring rubric is plans/backlog-rubric.md in the hub."""
import argparse, datetime, binascii, calendar, hashlib, hmac, json, os, re, subprocess, sys, time

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
URGENCIES = ("next_session", "whenever")
DEFAULT_URGENCY = "whenever"
CLASSES = ("build", "maintain")
KEEP_RE = re.compile(r"^\s*keep\b.*\b(healthy|current)\b", re.I)   # the project's standing "Keep X healthy and current" initiative


def keep_healthy(st):
    """The open initiative that holds the project's maintenance (title like "Keep X healthy and current"), signed-off
    ones first; None when there is none."""
    rows = [i for i in st["inits"].values() if not i["closed"] and KEEP_RE.search(i.get("title") or "")]
    rows.sort(key=lambda i: (i["owner_signoff"].get("status") != "yes", i["id"]))
    return rows[0] if rows else None


def class_of(st, it):
    """build or maintain: the declared class when there is one, else maintain for a lug in the keep-healthy initiative."""
    if it.get("class") in CLASSES:
        return it["class"]
    ini = (st or {}).get("inits", {}).get(it.get("initiative"))
    return "maintain" if ini and KEEP_RE.search(ini.get("title") or "") else "build"


def urgency_of(it):
    """A lug's urgency; whenever when unset (older lugs carry none)."""
    return it.get("urgency") or DEFAULT_URGENCY
WRITES = ("add", "status", "reopen", "rank", "move", "edit", "link", "claim", "release", "initiative", "release-deps", "statement")
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


def live_root(root):
    """B-078: the project's main checkout when root is a linked worktree of it (its .git is a file pointing into
    <main>/.git/worktrees/), else root. The work-item log lives in one place, the live checkout, where the turn save
    commits it; a session branch never carries a diff of it, so shipping the branch cannot collide with the log."""
    try:
        with open(os.path.join(root, ".git"), encoding="utf-8") as f:
            line = f.readline().strip()
    except OSError:  # a directory (the main checkout itself) or no git at all
        return root
    if not line.startswith("gitdir:"):
        return root
    gd = line[len("gitdir:"):].strip()
    gd = os.path.normpath(gd if os.path.isabs(gd) else os.path.join(root, gd))
    marker = os.sep + ".git" + os.sep + "worktrees" + os.sep
    if marker not in gd + os.sep:
        return root
    main = gd.split(marker)[0]
    return main if os.path.isfile(log_path(main)) else root


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
        items[iid]["urgency"] = ev.get("urgency") or DEFAULT_URGENCY
        items[iid]["class"] = ev.get("class") if ev.get("class") in CLASSES else None
        items[iid]["urgency_set"] = bool(ev.get("urgency"))  # lint wants an explicit tag on every open lug
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
        if ev.get("branch"):
            it["branch"] = ev["branch"]
        elif ev.get("superseded") or ev["status"] in CLOSED:
            it["branch"] = None
        if ev["status"] in CLOSED:
            it["closed"] = ev.get("at")
            it["claim"] = None
            if iid in order:
                order.remove(iid)
            pinned.pop(iid, None)
        elif it.get("closed"):   # B-124: a reopened lug (lug.py reopen) is open again, at the bottom of the plan
            it["closed"] = None
            if iid not in order:
                order.append(iid)
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
            if k == "urgency":
                it["urgency_set"] = True
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
    need(getattr(a, "urgency", None) is None or getattr(a, "urgency", None) in URGENCIES, "urgency must be next_session or whenever")
    need(getattr(a, "klass", None) is None or getattr(a, "klass", None) in CLASSES, "class must be build or maintain")
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
        if getattr(a, "urgency", None):
            ev["urgency"] = getattr(a, "urgency", None)
        if getattr(a, "klass", None):
            ev["class"] = a.klass
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


# ---------- proof tokens (W-175): only tools/verify.py makes one, on a pass backed by a command that ran ----------
def proof_key_path():
    return os.environ.get("WHEEL_PROOF_KEY") or os.path.expanduser("~/.config/wheel/proof.key")


def proof_key(create=False):
    path = proof_key_path()
    try:
        with open(path, "rb") as f:
            k = f.read().strip()
        if k:
            return k
    except OSError:
        pass
    if not create:
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    k = binascii.hexlify(os.urandom(32))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(k + b"\n")
    return k


def _mac(key, subject, sha):
    return hmac.new(key, ("pass|%s|%s" % (subject, sha)).encode(), hashlib.sha256).hexdigest()[:32]


def sign_proof(subject, sha, key=None):
    return "proof1.%s.%s.%s" % (subject, sha, _mac(key or proof_key(create=True), subject, sha))


def proof_problem(token, subject, root):
    """None when token is a pass proof for subject made with this machine's key on a commit of root's repository."""
    if not token:
        return "no proof token: run the check through tools/verify.py and pass the token it prints on a pass with --proof"
    parts = str(token).strip().split(".")
    if len(parts) != 4 or parts[0] != "proof1" or not re.match(r"^[0-9a-f]{40}$", parts[2]):
        return "the proof token is malformed"
    _, subj, sha, mac = parts
    if subj != subject:
        return "the proof token is for %s, not %s" % (subj, subject)
    key = proof_key()
    if not key:
        return "no proof key on this machine (%s)" % proof_key_path()
    if not hmac.compare_digest(_mac(key, subject, sha), mac):
        return "the proof token does not match: it was not made by tools/verify.py on this machine"
    r = subprocess.run(["git", "-C", root, "cat-file", "-e", sha + "^{commit}"], capture_output=True)
    if r.returncode:
        return "the proof names commit %s, which is not in this project" % sha[:12]
    return None


LUG_NAMED = re.compile(r"\bB-\d{3,}\b")


def landing_problem(root, iid, sha=None):
    """None when a commit reachable from sha (the proven commit; else HEAD) names the lug and changes something besides
    harness bookkeeping (tidy.landed_ids reads main the same way); else why not (B-124: done that never reached a commit
    is spend with no result). A closing with --no-code REASON skips this and is counted apart."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import wheelstate
        pol = wheelstate.policy()
    except Exception as e:  # noqa: BLE001
        return "cannot read the harness state policy (%s)" % str(e)[:80]
    ref = sha or "HEAD"
    git = lambda *x: subprocess.run(["git", "-C", root, "log", ref] + list(x), capture_output=True, text=True)
    r = git("--format=%x01%H%x00%s%n%b")
    if r.returncode:
        return "cannot read the commit history from %s: %s" % (ref[:12], r.stderr.strip()[:100])
    naming = set()
    for chunk in r.stdout.split("\x01")[1:]:
        h, _, msg = chunk.partition("\x00")
        if iid in LUG_NAMED.findall(msg):
            naming.add(h.strip())
    if naming:
        for chunk in git("--format=%x01%H", "--name-only").stdout.split("\x01")[1:]:
            lines = [l.strip() for l in chunk.splitlines() if l.strip()]
            if lines and lines[0] in naming and any(wheelstate.owned(f, root, pol) is None for f in lines[1:]):
                return None
    return ("no commit on %s names %s and changes project files; commit the work with %s in the message, or close it with "
            "--no-code REASON when it is a state, config or decision change with no code" % (ref[:12], iid, iid))


def spoke_repo(root, name):
    """B-292: (path, None) for the registered spoke a hub-held lug's work lives in, else (None, why). A hub keeps lugs for
    work done in a spoke's own repository; its proof, landing and on-main checks then run in that repository. Only a
    spoke listed in spokes/active.json (this checkout's or the live checkout's) counts, by name or by path."""
    want = str(name or "").strip()
    if not want:
        return None, "--repo needs a spoke name"
    seen = False
    for base in dict.fromkeys([root, live_root(root)]):
        try:
            with open(os.path.join(base, "spokes", "active.json"), encoding="utf-8") as f:
                reg = json.load(f).get("active") or []
        except (OSError, ValueError, AttributeError):
            continue
        seen = True
        for s in reg:
            path = os.path.abspath(os.path.expanduser(str(s.get("path") or ""))) if isinstance(s, dict) else ""
            if path and (s.get("name") == want or path == os.path.abspath(os.path.expanduser(want))):
                if subprocess.run(["git", "-C", path, "rev-parse", "--git-dir"], capture_output=True).returncode:
                    return None, "spoke %s at %s is not a git repository" % (want, path)
                return path, None
    if not seen:
        return None, "--repo needs a hub: no spokes/active.json here"
    return None, "%s is not a registered spoke (spokes/active.json)" % want


def unlanded_problem(root, sha):
    """B-227: None when sha is reachable from the project's main/master branch (or there is none to check); else why not.
    A commit that lives only on a side branch is not done work."""
    if not sha or not any(subprocess.run(["git", "-C", root, "rev-parse", "--verify", "-q", b], capture_output=True).returncode == 0
                          for b in ("main", "master")):
        return None
    ref = default_ref(root)
    if subprocess.run(["git", "-C", root, "merge-base", "--is-ancestor", sha, ref], capture_output=True).returncode == 0:
        return None
    return "the proven commit %s is not on %s yet; merge it first (done means on %s)" % (sha[:12], ref, ref)


def do_unlanded(root, a):
    """B-227 (report only): done lugs whose proven commit is still not on main after --days (default 1), with the wheel
    branch that holds it. Closed lugs are final in the store, so this names them for a person or a wake to act on."""
    st = load(root)
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = []
    for iid, it in st["items"].items():
        if it.get("status") != "done":
            continue
        done = [e for e in it["history"] if e.get("event") == "status" and e.get("status") == "done" and e.get("proof")]
        parts = str(done[-1]["proof"]).split(".") if done else []
        proot = (spoke_repo(root, done[-1]["repo"])[0] or root) if done and done[-1].get("repo") else root
        if len(parts) != 4 or not re.match(r"^[0-9a-f]{40}$", parts[2]) or unlanded_problem(proot, parts[2]) is None:
            continue
        if landing_problem(proot, iid, default_ref(proot)) is None:   # landed under another sha (a fold or a cherry-pick)
            continue
        try:
            age = (now - datetime.datetime.fromisoformat(str(it.get("closed")).replace("Z", "+00:00"))).total_seconds() / 86400
        except (ValueError, TypeError):
            age = 0
        if age < float(getattr(a, "days", 1)):
            continue
        br = subprocess.run(["git", "-C", proot, "branch", "--contains", parts[2], "--format=%(refname:short)", "--list", "wheel/*"],
                            capture_output=True, text=True).stdout.split()
        rows.append({"id": iid, "sha": parts[2][:12], "closed": it.get("closed"), "branch": br[0] if br else None})
    if getattr(a, "json", False):
        return json.dumps(rows)
    return "\n".join("%s done but %s is not on main (branch %s): lug.py reopen %s" % (r["id"], r["sha"], r["branch"] or "unknown", r["id"])
                     for r in rows) or "every done lug's proven commit is on main"


def do_reopen(root, a):
    """B-124: a done lug whose work never reached main goes back to ready. Done is otherwise final; this is the one way
    back, and only when main shows no landing: no commit on main names the lug and changes project files. A lug closed
    with --no-code, or one that landed (even by a fold or cherry-pick with a new sha), is refused."""
    need(a.reason and a.reason.strip(), "reopen needs --reason")
    with Locked(root) as lk:
        st = load(root)
        it = open_item(st, a.id)
        need(it["status"] == "done", "%s is %s; only a done lug can be reopened" % (a.id, it["status"]))
        last = [e for e in it["history"] if e.get("event") == "status" and e.get("status") == "done"][-1:]
        need(not (last and last[0].get("no_code")), "%s was closed with no code to land (%s)" % (a.id, last and last[0].get("no_code")))
        proot = (spoke_repo(root, last[0]["repo"])[0] or root) if last and last[0].get("repo") else root
        ref = default_ref(proot)
        need(ref != "HEAD", "%s has no main or master branch to judge the landing by" % a.id)
        need(landing_problem(proot, a.id, ref) is not None, "%s has landed: a commit on %s names it and changes project files" % (a.id, ref))
        ev = {"event": "status", "id": a.id, "status": "ready", "from": "done", "by": a.by, "reason": a.reason.strip(), "reopen": True}
        branch = (getattr(a, "branch", None) or "").strip()
        if branch:
            ev["branch"] = branch
        lk.append(ev)
        return "%s done -> ready (reopened: not on %s)" % (a.id, ref)


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
        ev = {"event": "status", "id": a.id, "status": a.status, "from": cur, "by": a.by, "reason": a.reason.strip()}
        branch, gone = (getattr(a, "branch", None) or "").strip(), (getattr(a, "superseded", None) or "").strip()
        if a.status == "ready" or (a.status == "doing" and cur in ("ready", "blocked")):
            # B-223: built work is never forgotten. A lug with an unchecked wheel branch goes back to ready, or starts a
            # build, only naming the branch to continue from, or saying why that work is superseded.
            built = built_branches(root, a.id).get(a.id) or []
            need(not built or branch in built or gone,
                 "%s has built work not yet checked on %s: send a checker there (status checking), continue from it "
                 "(--branch %s), or say why it is superseded (--superseded WHY)" % (a.id, ", ".join(built), built[0] if built else ""))
            if built and branch in built:
                ev["branch"] = branch
            elif built:
                ev["superseded"] = {"branches": built, "why": gone[:300]}
        elif branch:
            ev["branch"] = branch
        repo, proot = (getattr(a, "repo", None) or "").strip(), root
        if repo:
            need(a.status == "done", "--repo only applies when closing done")
            proot, bad = spoke_repo(root, repo)
            need(not bad, "%s cannot be marked done: %s" % (a.id, bad))
            ev["repo"] = repo
        if a.status == "done" and it["kind"] == "autopilot":
            last = [e for e in it["history"] if e.get("event") == "status" and e["status"] in ("doing", "checking")]
            need(all(e.get("by") != a.by for e in last), "%s cannot be marked done by %s: a different checker must close an autopilot lug" % (a.id, a.by))
            bad = proof_problem(getattr(a, "proof", None), a.id, proot)
            need(not bad, "%s cannot be marked done: %s" % (a.id, bad))
            ev["proof"] = a.proof.strip()
        if a.status == "done":
            nc = (getattr(a, "no_code", None) or "").strip()
            if nc:
                ev["no_code"] = nc
            else:
                sha = str(getattr(a, "proof", None) or "").split(".")
                bad = landing_problem(proot, a.id, sha[2] if len(sha) == 4 and re.match(r"^[0-9a-f]{40}$", sha[2]) else None)
                need(not bad, "%s cannot be marked done: %s" % (a.id, bad))
                if len(sha) == 4 and re.match(r"^[0-9a-f]{40}$", sha[2]):
                    bad = unlanded_problem(proot, sha[2])
                    need(not bad, "%s cannot be marked done: %s" % (a.id, bad))
        lk.append(ev)
        stm = " ".join((getattr(a, "statement", None) or "").split())
        if a.status == "done" and stm:
            lk.append({"event": "edit", "id": a.id, "changes": {"statement": stm[:200]}, "by": a.by, "reason": "changelog statement"})
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
        if getattr(a, "urgency", None) is not None and (getattr(a, "urgency", None) != urgency_of(it) or not it.get("urgency_set")):
            need(getattr(a, "urgency", None) in URGENCIES, "urgency must be next_session or whenever")
            ch["urgency"] = getattr(a, "urgency", None)
        if getattr(a, "klass", None) is not None and a.klass != it.get("class"):
            need(a.klass in CLASSES, "class must be build or maintain")
            ch["class"] = a.klass
        reach = getattr(a, "reach", None)
        if reach is not None and reach != it.get("reach"):   # B-222: work whose effect reaches every spoke weighs more in reorder
            need(reach in REACHES, "reach must be spokes or project")
            ch["reach"] = reach
        after = getattr(a, "after", None)
        if after is not None:   # B-132: the lugs this one waits on, kept as a list; an empty value clears it
            ids = [x for x in re.split(r"[\s,]+", after.strip()) if x]
            need(all(re.match(r"^B-\d+$", x) for x in ids), "--after takes lug ids like B-117, comma-separated")
            need(a.id not in ids, "%s cannot wait on itself" % a.id)
            need(all(x in st["items"] for x in ids), "--after names a lug that does not exist: %s" % ", ".join(x for x in ids if x not in st["items"]))
            if ids != list(it.get("after") or []):
                ch["after"] = ids
        need(ch, "nothing to change")
        for k in ("check", "kind"):
            need(not (k in ch and it["status"] in ("doing", "checking")),
                 "%s is %s: its %s cannot change while it is built or checked (move it to ready or blocked first)" % (a.id, it["status"], k))
        kind, chk = ch.get("kind", it["kind"]), ch.get("check", it.get("check"))
        need(kind != "autopilot" or (chk and chk.strip()), "an autopilot lug needs a check")
        if "goal" in ch and it.get("initiative") in st["inits"]:
            g = st["inits"][it["initiative"]]["goal"]
            need(str(ch["goal"]) == str(g), "%s belongs to %s, which serves goal %s; link it to an initiative of that goal (lug link ID I-### --reason ...) or edit the initiative's goal" % (a.id, it["initiative"], g))
        lk.append({"event": "edit", "id": a.id, "changes": ch, "by": a.by, "reason": a.reason.strip()})
        return "%s edited: %s" % (a.id, ", ".join(sorted(ch)))


def do_release_deps(root, a):
    """B-132: a blocked lug that waits on other lugs (its `after` list) returns to ready once every one of them is done.
    A dependency that is dropped never lifts the block: the lug stays blocked for someone to decide."""
    with Locked(root) as lk:
        st = load(root)
        freed = []
        for iid in list(st["items"]):
            it = st["items"][iid]
            deps = list(it.get("after") or [])
            if it["status"] != "blocked" or not deps:
                continue
            if all((st["items"].get(d) or {}).get("status") == "done" for d in deps):
                why = "%s done: the block lifts" % ", ".join(deps)
                ev = {"event": "status", "id": iid, "status": "ready", "from": "blocked", "by": a.by, "reason": why}
                built = built_branches(root, iid).get(iid) or []
                if built:   # B-223: the parked work travels with the lug
                    ev["branch"] = built[0]
                lk.append(ev)
                lk.append({"event": "edit", "id": iid, "changes": {"after": []}, "by": a.by, "reason": "its dependencies are done"})
                freed.append(iid)
        return ("released: " + ", ".join(freed)) if freed else "released: none"


# ---------- reorder (B-222): the backlog orders itself for return on effort ----------
TIER_WEIGHT = {"P0": 1.0, "P1": 0.75, "P2": 0.55, "P3": 0.4}
UNKNOWN_TIER = 0.6
SPREAD_RE = re.compile(r"\b(?:every|all|each|other)\s+(?:spoke|project)s?\b|\bspokes\b|\bthe kit\b|\bkit (?:part|install|rollout|release)\b", re.I)
IN_MOTION = ("doing", "checking")
KEEP_TOP = 3
REACHES = ("spokes", "project")


def built_branches(root, iid=None):
    """Unmerged built work: lug id -> its wheel branches (wheel/...-B-###) holding commits not on main, newest first.
    The work is paid for and only needs checking, so the store never lets it be forgotten (B-223)."""
    out = {}
    try:
        pat = "refs/heads/wheel/*-%s" % iid if iid else "refs/heads/wheel/"
        p = subprocess.run(["git", "-C", root, "for-each-ref", "--sort=-committerdate", "--format=%(refname:short)", pat],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return out
    if p.returncode != 0:
        return out
    base = None
    for name in p.stdout.split():
        m = re.search(r"-(B-\d+)$", name)
        if not m or (iid and m.group(1) != iid):
            continue
        base = base or default_ref(root)
        c = subprocess.run(["git", "-C", root, "rev-list", "--count", "%s..%s" % (base, name)], capture_output=True, text=True)
        if c.returncode == 0 and c.stdout.strip() not in ("", "0"):
            out.setdefault(m.group(1), []).append(name)
    return out


def built_lugs(root):
    """Lug ids with unmerged built work on a wheel branch (see built_branches)."""
    return set(built_branches(root))


def goal_weights(root, path=None, project=None):
    """Initiative id -> (weight, label) from the hub's computed priorities (plans/priorities.json): the tier's weight,
    easing by 4% per place within the tier so the computed order counts too. No file: every initiative weighs the same."""
    path = path or os.environ.get("WHEEL_PRIORITIES") or os.path.join(root, "plans", "priorities.json")
    project = project or os.path.basename(os.path.normpath(root))
    try:
        pri = json.load(open(path, encoding="utf-8")).get("priority") or {}
    except (OSError, ValueError):
        return {}
    out = {}
    for tier, keys in pri.items():
        for n, key in enumerate(keys or []):
            proj, _, ini = str(key).rpartition(":")
            if proj == project and ini:
                out[ini] = (TIER_WEIGHT.get(tier, UNKNOWN_TIER) * max(0.6, 1 - 0.04 * n), tier)
    return out


def focus_of(root):
    try:
        return (json.load(open(os.path.join(root, ".wheel", "config.json"), encoding="utf-8")) or {}).get("focus_initiative")
    except (OSError, ValueError):
        return None


def deps_of(it, open_ids):
    deps = [d for d in (it.get("after") or []) if d in open_ids]
    for text in (it.get("title"), it.get("check")):
        for m in NEEDS_RE.finditer(text or ""):
            deps += [d.upper() for d in re.findall(r"B-\d+", m.group(1), re.I) if d.upper() in open_ids]
    return [d for d in dict.fromkeys(deps) if d != it["id"]]


def plan_order(st, built=(), weights=None, focus=None, keep=KEEP_TOP):
    """The order the backlog should have, and one plain reason per lug. Bands, then return on effort:
    the promised top `keep` stay; then work already built or in motion; then the rest by
    value / effort x goal weight x lifts (spoke reach, wanted before the next session, a fix, the focus goal);
    unapproved and blocked work sinks. Outside the promised top (which holds as promised, its waits named in the reason),
    a lug never ranks above an open lug it waits for; a wait on an owner-pinned lug counts as met. Owner pins hold their place."""
    weights = weights or {}
    order = [i for i in st["order"] if i in st["items"]]
    pinned = st["pinned"]
    free = [i for i in order if i not in pinned]
    kept = [i for i in free if st["items"][i]["status"] != "blocked"][:max(keep, 0)]   # a blocked lug is no promise
    open_ids = set(order)
    why, key = {}, {}
    for iid in free:
        it = st["items"][iid]
        w, tier = weights.get(it.get("initiative"), (UNKNOWN_TIER if weights else 1.0, None))
        roi = (it.get("value") or 1) / float(max(it.get("effort") or 1, 1)) * w
        notes = ["value %s for effort %s" % (it.get("value"), it.get("effort"))]
        if tier:
            notes.append("%s goal %s" % (tier, it.get("initiative")))
        text = "%s %s" % (it.get("title") or "", it.get("check") or "")
        if it.get("reach") == "spokes" or (it.get("reach") != "project" and SPREAD_RE.search(text)):
            roi *= 1.5
            notes.append("reaches the spokes")
        if urgency_of(it) == "next_session":
            roi *= 1.4
            notes.append("wanted before the next session")
        if FIX_RE.search((it.get("title") or "").split(":")[0]):
            roi *= 1.2
            notes.append("a fix")
        if focus and it.get("initiative") == focus:
            roi *= 1.2
            notes.append("the focus goal")
        band = 2
        if iid in kept:
            band, notes = 0, ["kept in the promised top %d" % keep] + notes
        elif it["status"] == "blocked":
            band = 4
            notes.insert(0, "blocked" + (" (a built branch waits for the block to lift)" if iid in built else ""))
        elif it["status"] in IN_MOTION or iid in built:
            band = 1
            notes.insert(0, "already built, needs checking and merging" if iid in built else "in motion (%s)" % it["status"])
        elif it["status"] == "proposed":
            band = 3 if it["kind"] == "owner" else 2
            roi *= 0.7
            notes.insert(0, "not approved yet")
        key[iid] = (band, kept.index(iid) if band == 0 else -roi)
        why[iid] = notes
    ranked = sorted(free, key=lambda i: (key[i], free.index(i)))
    # dependencies: place each lug only after the open lugs it waits for (a cycle falls back to rank order)
    placed, out, pending = set(), [], list(ranked)
    while pending:
        free_now = [i for i in pending if all(d in placed or d not in open_ids or d in pinned for d in deps_of(st["items"][i], open_ids))]
        pick = next((i for i in pending if i in kept), None) or (free_now or pending)[0]   # the promised top holds even over a wait
        deps = deps_of(st["items"][pick], open_ids)
        if deps:
            why[pick].append("waits for " + ", ".join(deps))
        pending.remove(pick)
        placed.add(pick)
        out.append(pick)
    for iid in pinned:
        if iid in st["items"]:
            why[iid] = ["pinned by the owner"]
    return repin(out + [p for p in pinned if p in open_ids], pinned), why


def stale_lugs(st, days=14, now_t=None):
    now_t = now_t or time.time()
    return [it["id"] for it in open_items(st) if it.get("urgency") != "next_session" and secs(it.get("updated") or it.get("added") or "") and
            now_t - secs(it.get("updated") or it.get("added")) > days * 86400]


def do_reorder(root, a):
    need(os.path.isfile(log_path(root)), "%s holds no backlog (.wheel/backlog.jsonl): nothing to reorder" % root)
    project = a.project or os.path.basename(os.path.normpath(root))
    weights = goal_weights(root, a.priorities, project)
    built = built_lugs(root)
    focus = focus_of(root)
    with (Locked(root) if a.write else _NoLock()) as lk:
        events = read_events(root)
        st = fold(events)
        target, why = plan_order(st, built, weights, focus, a.keep)
        moves = []
        if a.write:
            cur = list(st["order"])
            for pos, iid in enumerate(target, 1):
                if iid in st["pinned"] or cur.index(iid) + 1 == pos:
                    continue
                ev = {"event": "rank", "id": iid, "rank": pos, "from": cur.index(iid) + 1, "pinned": False, "by": a.by,
                      "reason": "reorder: " + "; ".join(why.get(iid) or [])[:300]}
                events.append(dict(lk.append(ev)))
                st = fold(events)
                cur = list(st["order"])
                moves.append(iid)
        else:
            moves = [i for n, i in enumerate(target) if st["order"][n] != i]
    rows = ["%s order (%d lug%s %s):" % (project, len(moves), "" if len(moves) == 1 else "s", "moved" if a.write else "would move")]
    for n, iid in enumerate(target[: a.n], 1):
        it = st["items"][iid]
        rows.append("  #%d %s [%s, %s] %s" % (n, iid, it["kind"], it["status"], (it.get("title") or "")[:70]))
        rows.append("      why: %s" % "; ".join(why.get(iid) or []))
    stale = [i for i in stale_lugs(st) if i not in target[: a.n]]
    if stale:
        rows.append("Untouched for two weeks, bump or drop? %s" % ", ".join(stale[:12]))
    return "\n".join(rows)


class _NoLock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def do_link(root, a):
    with Locked(root) as lk:
        st = load(root)
        it = open_item(st, a.id)
        ini = get_init(st, a.initiative)
        need(not ini["closed"], "%s is closed; no lug can join it" % a.initiative)
        need(it.get("initiative") != a.initiative, "%s already belongs to %s" % (a.id, a.initiative))
        need(not it.get("initiative") or (a.reason and a.reason.strip()), "%s belongs to %s; moving it needs --reason" % (a.id, it.get("initiative")))
        need(not it.get("goal") or str(it["goal"]) == str(ini["goal"]) or (a.reason and a.reason.strip()),
             "%s serves goal %s but %s serves goal %s; give --reason to move it (its goal then becomes %s)" % (a.id, it["goal"], a.initiative, ini["goal"], ini["goal"]))
        ev = {"event": "link", "id": a.id, "initiative": a.initiative, "from": it.get("initiative"), "by": a.by,
              "reason": (a.reason or "").strip() or "grouped under %s" % a.initiative}
        lk.append(ev)
        if str(it.get("goal") or "") != str(ini["goal"]):
            lk.append({"event": "edit", "id": a.id, "changes": {"goal": ini["goal"]}, "by": a.by,
                       "reason": "goal taken from %s" % a.initiative})
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


COMMAND_RE = re.compile(r"`([^`\n]+)`")


def check_command(check):
    """The first backticked command in a check (a span whose first word looks like a program or path), or None.
    A check with none cannot be failed by a checker, so no wake may pick the lug (B-131)."""
    for m in COMMAND_RE.finditer(check or ""):
        span = m.group(1).strip()
        if re.match(r"[A-Za-z0-9_./~$-][^\s]*(\s|$)", span) and re.search(r"[A-Za-z]", span):
            return span
    return None


def value_cap(goals, goal):
    """Highest value a lug on this goal may hold: goal 1 up to 5, goal 2 up to 4, ... down to 1; a "(later)" goal up to 2.
    None when the goal is not a known number (lint reports that on its own)."""
    g = str(goal or "").strip()
    if not goals or not g.isdigit() or g not in goals:
        return None
    cap = max(1, 6 - int(g))
    return min(cap, 2) if goals[g].get("later") else cap


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
            elif not check_command(c):
                errors.append((lid, "autopilot lug's check holds no backticked command a checker can run and fail (B-131): write one, e.g. `python3 tools/x_test.py`"))
            why = owner_work_reason(it.get("title"), c)
            if why:
                errors.append((lid, "autopilot lug looks like owner work: %s" % why))
        if it.get("urgency") not in (None,) + URGENCIES:
            errors.append((lid, "urgency %r is not one of %s" % (it.get("urgency"), ", ".join(URGENCIES))))
        elif not it.get("urgency_set"):
            errors.append((lid, "lug has no urgency: set next_session or whenever (plans/backlog-rubric.md)"))
        cap = value_cap(goals, it.get("goal"))
        if cap and it["value"] > cap:
            errors.append((lid, "value %d is above %d, the most a goal-%s lug can hold (a later goal never outranks an earlier one; plans/backlog-rubric.md)" % (it["value"], cap, it.get("goal"))))
        t = (it.get("title") or "").strip()
        if not t or re.sub(r"[\s.!]+$", "", t.lower()) in PLACEHOLDERS or PLACEHOLDER_RE.search(t) or TODO_RE.search(t):
            errors.append((lid, "lug title is empty or placeholder"))
    return errors, pending


STORE_CHECK_RE = re.compile(r"backlog\.jsonl|\blug\.py\b|\bbacklog\.py\s+(?:status|edit|rank|link|claim|release|add)\b|\blug (?:status|edit|rank|link) ", re.I)


NEEDS_RE = re.compile(r"\b(?:needs?|requires?|depends?\s+on|blocked\s+by|waits?\s+(?:for|on)|builds?\s+on|after)\s+"
                      r"((?:B-\d+(?:\s*(?:,|&|and)\s*)?)+)", re.I)


def order_warnings(st):
    """A lug whose title or check says it needs another open lug that ranks below it will be picked first and cannot
    finish (W-147). Advice, not an error: the owner may have ranked it so on purpose."""
    out, rank = [], {iid: n for n, iid in enumerate(st["order"], 1)}
    for it in open_items(st):
        seen = []
        for text in (it.get("title"), it.get("check")):
            for m in NEEDS_RE.finditer(text or ""):
                for dep in re.findall(r"B-\d+", m.group(1), re.I):
                    dep = dep.upper()
                    if dep != it["id"] and dep in rank and dep not in seen and rank[dep] > rank[it["id"]]:
                        seen.append(dep)
        for dep in seen:
            out.append((it["id"], "warning: says it needs %s, but ranks above it (rank %d, %s is rank %d); move it below with "
                                  "lug move %s --below %s" % (dep, rank[it["id"]], dep, rank[dep], it["id"], dep)))
    return out


def warnings_of(st):
    """Advice that does not fail lint: an autopilot lug whose check reads or edits the lug store
    (.wheel/backlog.jsonl) draws a warning, because a builder may not touch the store (failure kind F-012);
    a lug that says it needs a lug ranked below it draws a warning too."""
    out = []
    for it in open_items(st):
        if it["kind"] == "autopilot" and STORE_CHECK_RE.search(it.get("check") or ""):
            out.append((it["id"], "warning: autopilot check names the lug store (.wheel/backlog.jsonl) or lug.py, which a builder cannot edit; "
                                  "reword the check to something the builder's own files can show"))
    return out + order_warnings(st)


def do_lint(root, a):
    st = load(root)
    errors, pending = lint(root, st)
    warns = warnings_of(st)
    if a.json:
        return json.dumps({"errors": [{"id": i, "problem": p} for i, p in errors],
                           "warnings": [{"id": i, "problem": p} for i, p in warns],
                           "pending": [{"id": i, "problem": p} for i, p in pending]}, ensure_ascii=False, indent=1), (1 if errors else 0)
    lines = ["%s: %s" % e for e in errors] + ["%s: %s" % p for p in pending] + ["%s: %s" % w for w in warns]
    lines.append("lint: %d problem(s), %d sign-off(s) pending, %d warning(s) (%d initiatives, %d open lugs)" % (len(errors), len(pending), len(warns), len(st["inits"]), len(st["order"])))
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
            if ev.get("class") not in (None,) + CLASSES:
                problems.append((n, "%s has class %r" % (iid, ev.get("class"))))
            if ev.get("urgency") not in (None,) + URGENCIES:
                problems.append((n, "%s has urgency %r" % (iid, ev.get("urgency"))))
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


def retier(root):
    """The hub (it carries tools/kit/MANIFEST.json and tools/priorities.py) tiers its initiatives as they are written;
    any other project skips silently, even one with a tools/priorities.py of its own."""
    import subprocess
    p = os.path.join(root, "tools", "priorities.py")
    if not os.path.isfile(os.path.join(root, "tools", "kit", "MANIFEST.json")) or not os.path.isfile(p):
        return ""
    try:
        r = subprocess.run([sys.executable, "-B", p, "--write"], cwd=root, capture_output=True, text=True, timeout=60)
    except Exception:
        return "; priorities not recomputed"
    return "; priorities recomputed" if r.returncode == 0 else "; priorities not recomputed"


INIT_PROMPTS = ("Before sign-off, read it as a fresh reader (W-147 took seven review passes):\n"
                "  1. Is each claim in the outcome proven by the done-when?\n"
                "  2. Is everything in scope-in covered by a lug?\n"
                "  3. Does any lug sit above a lug it needs? (lug lint warns on \"needs B-###\" ranked below)")


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
    return "%s %s (goal %s; owner sign-off pending)%s\n%s" % (iid, fields["title"], fields["goal"], retier(root), INIT_PROMPTS)


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
        lk.append({"event": "init_edit", "id": a.id, "changes": ch, "by": a.by, "reason": a.reason.strip()})
        moved = []
        if "goal" in ch:
            # an initiative serves one goal and so do its open lugs: they follow it, in the same locked write
            moved = [l["id"] for l in lugs_of(st, a.id) if l["status"] not in CLOSED and str(l.get("goal")) != str(ch["goal"])]
            for lid in moved:
                lk.append({"event": "edit", "id": lid, "changes": {"goal": ch["goal"]}, "by": a.by,
                           "reason": "goal follows %s (%s)" % (a.id, a.reason.strip())})
        reset = any(k in SIGNED_FIELDS for k in ch) and ini["owner_signoff"].get("status") == "yes"
        return "%s edited: %s%s%s" % (a.id, ", ".join(sorted(ch)),
                                      "; goal moved on %d open lug(s): %s" % (len(moved), ", ".join(moved)) if moved else "",
                                      "; owner sign-off back to pending" if reset else "") + "\n" + INIT_PROMPTS


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
                              "initiatives": [dict(init_brief(i), lugs=[brief(l, st) for l in sorted(lugs_of(st, i["id"]), key=lambda l: (l["rank"] is None, l["rank"] or 0, l["id"]))]) for i in inits]})
    data["unlinked"] = [brief(l, st) for l in open_items(st) if l.get("initiative") not in st["inits"]]
    for l in sorted([l for l in st["items"].values() if l["status"] in CLOSED], key=lambda l: l["closed"] or "", reverse=True):
        data["history"].append({"date": (l["closed"] or "")[:10], "id": l["id"], "title": l["title"], "status": l["status"],
                                "who": l.get("status_by"), "reason": l.get("status_reason"), "initiative": l.get("initiative"),
                                "urgency": urgency_of(l)})
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


# ---------- the changelog (B-171) ----------

FIX_RE = re.compile(r"\b(fix(es|ed)?|bug|broke|broken|crash(es|ed)?|regression|fail(s|ed|ing)?|wrong|error|secur(e|ity)|vulnerab\w*|unauthenticated|unauthori[sz]ed|signed-in caller|authenticated|leak(s|ed)?|exposed?|injection|xss|csrf|rls)\b", re.I)
LANDING_RE = re.compile(r"^\s*land\b", re.I)   # moving finished work onto main: upkeep, not a fix
FIX_COMMIT_RE = re.compile(r"^(fix|hotfix|bugfix)\b|^fix(\(|:)|\bfix(es|ed)? (a |the )?(bug|crash|regression)\b", re.I)
GLANCE_DAYS = 7


def default_ref(root):
    """The branch finished work lands on: main, else master, else HEAD."""
    for ref in ("main", "master"):
        if subprocess.run(["git", "-C", root, "rev-parse", "--verify", "-q", ref], capture_output=True).returncode == 0:
            return ref
    return "HEAD"


def _harness_file(rel, root, pol):
    """True for the harness's own bookkeeping (work-item logs, rendered views, saves), which says nothing about the
    project itself."""
    if rel.startswith(".wheel/") or rel == ".claude/settings.json":
        return True
    if pol is not None:
        try:
            import wheelstate
            return wheelstate.owned(rel, root, pol) is not None
        except Exception:  # noqa: BLE001
            pass
    return False


def main_commits(root, ref=None):
    """Non-merge commits on the project's main branch, oldest last: [{sha, at, subject, body, files}] with files limited
    to the project's own (harness bookkeeping left out). [] when there is no git history."""
    ref = ref or default_ref(root)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import wheelstate
        pol = wheelstate.policy()
    except Exception:  # noqa: BLE001
        pol = None
    r = subprocess.run(["git", "-C", root, "log", ref, "--no-merges", "--format=%x01%h%x00%cI%x00%s%x00%b%x02",
                        "--name-only"], capture_output=True, text=True, errors="replace")
    if r.returncode:
        return []
    rows = []
    for chunk in r.stdout.split("\x01")[1:]:
        head, _, names = chunk.partition("\x02")
        sha, at, subject, body = (head.split("\x00") + ["", "", "", ""])[:4]
        files = [f.strip() for f in names.splitlines() if f.strip()]
        rows.append({"sha": sha, "at": at, "subject": subject.strip(), "body": body.strip(),
                     "files": [f for f in files if not _harness_file(f, root, pol)]})
    return rows


def any_secs(iso_text):
    """Epoch seconds of an ISO timestamp with Z or an offset (git's %cI); 0 when unreadable."""
    import datetime
    try:
        return datetime.datetime.fromisoformat((iso_text or "").replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def local_day(iso_text):
    """The owner's local calendar date of a timestamp (ISO with Z or an offset)."""
    t = any_secs(iso_text)
    return time.strftime("%Y-%m-%d", time.localtime(t)) if t else (iso_text or "")[:10]


def change_kind(it, st):
    """Fix, Upkeep or New: what kind of change a finished lug is, from its words and class."""
    if LANDING_RE.search(it.get("title") or ""):
        return "Upkeep"
    if FIX_RE.search(" ".join([it.get("title") or "", it.get("reason") or ""])):
        return "Fix"
    return "Upkeep" if class_of(st, it) == "maintain" else "New"


def headline(title, limit=150):
    """A short headline and the rest as detail: the part before the first ': ' when it reads as a name of its own."""
    title = redact(" ".join((title or "").split()))
    head, sep, rest = title.partition(": ")
    if sep and 20 <= len(head) <= limit and rest:
        return head, rest
    if len(title) <= limit:
        return title, ""
    cut = title.rfind(" ", 0, limit)
    return title[:cut if cut > 40 else limit].rstrip(",;") + "...", title


def redact(text):
    """Secret-shaped text out of a changelog line (a lug's words may quote a leaked key): the pre-commit gate's own
    patterns, each match replaced; a line it still flags is withheld whole. The changelog is tracked, so it must never
    carry what the gate refuses."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import precommit
    except Exception:  # noqa: BLE001
        return text
    for _, rx in precommit.BUILTIN:
        text = rx.sub("[secret removed]", text)
    text = precommit.ASSIGN.sub(lambda m: m.group(0) if precommit.PLACEHOLDER.search(m.group(3))
                                else m.group(0).replace(m.group(3), "[secret removed]"), text)
    flagged = precommit.builtin_scan(text)
    if not flagged:
        global _SCANNER
        if _SCANNER is None:   # the hub's fuller scanner, the one the gate runs when it can find it
            try:
                _SCANNER = precommit.load_scanner(precommit.toplevel(os.getcwd()) or os.getcwd(), False) or False
            except Exception:  # noqa: BLE001
                _SCANNER = False
        if _SCANNER:
            try:
                flagged = _SCANNER.scan_text(text, True)
            except Exception:  # noqa: BLE001
                flagged = []
    if flagged:
        return "[withheld: this text quotes something shaped like a secret; see the lug's history]"
    return text


_SCANNER = None


def clip(text, n):
    text = redact(" ".join((text or "").split()))
    return text if len(text) <= n else text[:n - 3].rstrip() + "..."


def file_list(files, n=6):
    seen = []
    for f in files:
        if f not in seen:
            seen.append(f)
    shown = ", ".join("`%s`" % f for f in seen[:n])
    return shown + (" and %d more" % (len(seen) - n) if len(seen) > n else "")


def landing_time(root, sha, ref):
    """When a commit reached ref: the time of the first-parent commit that brought it in (its merge), or its own commit
    time when it was made on ref itself. None when it is not on ref."""
    r = subprocess.run(["git", "-C", root, "rev-list", "--first-parent", "--ancestry-path", "%s..%s" % (sha, ref)],
                       capture_output=True, text=True)
    if r.returncode:
        return None
    lines = r.stdout.split()
    target = lines[-1] if lines else sha
    t = subprocess.run(["git", "-C", root, "show", "-s", "--format=%cI", target], capture_output=True, text=True)
    return t.stdout.strip() or None


def lug_commits(commits):
    """{lug id: [commits on main that name it and touch the project's own files]}."""
    by_lug = {}
    for c in commits:
        if c["files"]:
            for iid in set(LUG_NAMED.findall(c["subject"] + "\n" + c["body"])):
                by_lug.setdefault(iid, []).append(c)
    return by_lug


def mark_landed(root, by="changelog", commits=None):
    """Record on each finished lug when its work reached main (an edit event: landed = {at, sha}), once, from the
    history: the lug holds its own cradle-to-grave record (B-171). Returns the ids marked."""
    ref = default_ref(root)
    commits = main_commits(root, ref) if commits is None else commits
    by_lug = lug_commits(commits)
    marked = []
    with Locked(root) as lk:
        st = load(root)
        for it in st["items"].values():
            if it["status"] != "done" or it.get("landed") or it["id"] not in by_lug:
                continue
            times = [(landing_time(root, c["sha"], ref), c["sha"]) for c in by_lug[it["id"]]]
            times = [t for t in times if t[0]]
            if not times:
                continue
            at, sha = min(times, key=lambda t: any_secs(t[0]))
            lk.append({"event": "edit", "id": it["id"], "changes": {"landed": {"at": at, "sha": sha}}, "by": by,
                       "reason": "its work reached %s" % ref})
            marked.append(it["id"])
    return marked


def statement_of(it):
    """The lug's changelog line: the statement its closer wrote, else a headline made from its title."""
    return clip(it.get("statement") or headline(it.get("title"))[0], 200)


def changelog_entries(root, st, commits=None):
    """Every finished lug and every fix commit that names no lug, newest first. Each lug entry is dated by when its work
    reached main (the lug's landed record), else by when it closed."""
    commits = main_commits(root) if commits is None else commits
    by_lug = lug_commits(commits)
    out = []
    for it in st["items"].values():
        if it["status"] != "done":
            continue
        ini = st["inits"].get(it.get("initiative")) or {}
        landed = it.get("landed") or {}
        at = landed.get("at") or it["closed"] or ""
        out.append({"day": local_day(at), "at": at, "kind": change_kind(it, st), "statement": statement_of(it),
                    "lug": it["id"], "initiative": ini.get("id") or it.get("initiative"),
                    "initiative_title": ini.get("title"), "landed": bool(landed) or it["id"] in by_lug or bool(LANDING_RE.search(it.get("title") or "")),
                    "sha": landed.get("sha") or (by_lug.get(it["id"]) or [{}])[0].get("sha")})
    named = {c["sha"] for cs in by_lug.values() for c in cs}
    for c in commits:
        if c["sha"] in named or not c["files"] or not FIX_COMMIT_RE.search(c["subject"]):
            continue
        out.append({"day": local_day(c["at"]), "at": c["at"], "kind": "Fix", "statement": clip(c["subject"], 200),
                    "lug": None, "initiative": None, "initiative_title": None, "landed": True, "sha": c["sha"]})
    out.sort(key=lambda e: (e["day"], any_secs(e["at"])), reverse=True)
    return out


def entry_line(e):
    where = ("lug %s" % e["lug"]) if e["lug"] else ("commit %s" % e["sha"])
    ini = ("%s %s" % (e["initiative"], e["initiative_title"] or "")).strip() if e["initiative"] else "no initiative"
    return "- **%s** · %s · %s · %s%s" % (e["statement"].rstrip("."), e["kind"], ini, where,
                                          "" if e["landed"] else " (not on main yet)")


def changelog_md(root, st, commits=None, now_t=None):  # noqa: ARG001 (now_t: only when there are no entries)
    """.wheel/CHANGELOG.md: one line per change, newest on top. The details live on the lug (`lug history ID`); the
    same entries come as JSON from `lug changelog --json` (B-171)."""
    entries = changelog_entries(root, st, commits)
    name = os.path.basename(os.path.abspath(root))
    lines = ["# Changelog: %s" % name, "",
             "What reached this project, newest on top: one line per change (kind · initiative · lug). The details, "
             "proof and commits live on the lug: `lug history B-NNN`. JSON for other tools: `lug changelog --json`. "
             "Generated from the lugs; do not edit by hand.", ""]
    last = any_secs(entries[0]["day"] + "T12:00:00+00:00") if entries else (now_t or time.time())
    since = time.strftime("%Y-%m-%d", time.gmtime(last - GLANCE_DAYS * 86400))
    recent = [e for e in entries if e["day"] > since]
    lines += ["## The latest week at a glance (%d days to %s)" % (GLANCE_DAYS, entries[0]["day"] if entries else "today"), ""]
    if recent:
        kinds = {}
        for e in recent:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        lines.append("- %d change%s: %s" % (len(recent), "" if len(recent) == 1 else "s",
                                             ", ".join("%d %s" % (kinds[k], {"New": "new", "Fix": "fix", "Upkeep": "upkeep"}[k] + ("es" if k == "Fix" and kinds[k] > 1 else ""))
                                                       for k in ("New", "Fix", "Upkeep") if kinds.get(k))))
        per = {}
        for e in recent:
            key = ("%s %s" % (e["initiative"], e["initiative_title"] or "")).strip() if e["initiative"] else "no initiative"
            per[key] = per.get(key, 0) + 1
        for key, n in sorted(per.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append("- %s: %d" % (key, n))
    else:
        lines.append("- Nothing has reached main yet.")
    day = None
    for e in entries:
        if e["day"] != day:
            day = e["day"]
            lines += ["", "## %s" % day, ""]
        lines.append(entry_line(e))
    if not entries:
        lines += ["", "Nothing finished yet."]
    return "\n".join(lines) + "\n"


def do_statement(root, a):
    """Set a lug's changelog statement: one plain sentence saying what is now true for the person who uses the project.
    Open or closed lugs alike (the closer writes it at done, or later)."""
    text = " ".join((a.text or "").split())
    need(text, "a statement needs text")
    need(len(text) <= 200, "keep a statement to one sentence (200 characters at most)")
    with Locked(root) as lk:
        st = load(root)
        it = st["items"].get(a.id)
        need(it is not None, "no lug %s" % a.id)
        if it.get("statement") == text:
            return "%s already says that" % a.id
        lk.append({"event": "edit", "id": a.id, "changes": {"statement": text}, "by": a.by,
                   "reason": a.reason or "changelog statement"})
    return "%s statement set" % a.id


def do_changelog(root, a):
    st = load(root)
    entries = changelog_entries(root, st)
    if getattr(a, "since", None):
        entries = [e for e in entries if e["day"] >= a.since]
    if a.json:
        return json.dumps(entries, ensure_ascii=False, indent=1)
    return changelog_md(root, st)


LUG_FILES = (".wheel/backlog.jsonl", ".wheel/BACKLOG.md", ".wheel/ROADMAP.md", ".wheel/CHANGELOG.md")


def _git(root, *args):
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    return subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True, env=env)


def row_line(ev):
    what = ev.get("event", "?")
    if what == "status":
        what = "status %s" % ev.get("status", "?")
    words_ = ev.get("title") or ev.get("reason") or ""
    words_ = words_ if len(words_) <= 90 else words_[:87].rstrip() + "..."
    return "%s %s (by %s)%s" % (ev.get("id", "?"), what, ev.get("by", "?"), ": " + words_ if words_ else "")


def commit_lug_rows(root):
    """B-297: commit the work-item log and its views on the live checkout's main branch, alone, so the rows never ride in
    someone else's commit. Returns None when committed or nothing to do, else one line saying why the rows stay uncommitted
    (the next lug write, or the turn save, carries them). Call it holding the backlog lock."""
    if os.environ.get("WHEEL_LUG_NOCOMMIT") == "1":
        return None
    gd, cd = _git(root, "rev-parse", "--absolute-git-dir"), _git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if gd.returncode or cd.returncode:
        return None  # not a git repository: nothing to commit into
    gdir = gd.stdout.strip()
    if os.path.realpath(gdir) != os.path.realpath(cd.stdout.strip()):
        return "the log's checkout is a linked worktree, not the main checkout"
    if os.path.realpath(_git(root, "rev-parse", "--show-toplevel").stdout.strip() or root) != os.path.realpath(root):
        return None  # the log is not at the top of a repository (a nested folder): leave git alone
    branch = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    if branch not in ("main", "master"):
        return "the main checkout is on %s, not main" % (branch or "a detached HEAD")
    for busy in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        if os.path.exists(os.path.join(gdir, busy)):
            return "a merge or rebase is in progress in the main checkout"
    tracked = set(_git(root, "ls-files", "--", *LUG_FILES).stdout.split())
    paths = [f for f in LUG_FILES if f in tracked or os.path.isfile(os.path.join(root, f))]
    fresh = [f for f in paths if f not in tracked]
    if fresh and _git(root, "add", "--", *fresh).returncode:
        paths = [f for f in paths if f in tracked]  # ignored files stay out
    if not paths or (_git(root, "diff", "--quiet", "HEAD", "--", *paths).returncode == 0 and not fresh):
        return None
    rows = []
    for line in _git(root, "diff", "--no-color", "-U0", "HEAD", "--", LUG_FILES[0]).stdout.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            try:
                rows.append(json.loads(line[1:]))
            except ValueError:
                pass
    ids = list(dict.fromkeys(str(r.get("id", "?")) for r in rows))
    subject = "Lug rows: " + (", ".join(ids[:4]) + (" and %d more" % (len(ids) - 4) if len(ids) > 4 else "") if ids else "views re-rendered")
    body = "\n".join("- " + row_line(r) for r in rows[:40]) + ("\n- ... %d more rows" % (len(rows) - 40) if len(rows) > 40 else "")
    msg = subject + "\n\nCommitted by lug.py on its own (B-297), touching only the work-item log and its views.\n" + (("\n" + body + "\n") if body else "")
    for attempt in range(6):
        c = _git(root, "commit", "-q", "-m", msg, "--", *paths)
        if c.returncode == 0:
            return None
        err = (c.stderr or c.stdout).strip()
        if "index.lock" not in err:
            break
        time.sleep(0.3)
    return "git commit failed: %s" % (err.splitlines()[-1] if err else "no message")


def write_views(root):
    st = load(root)
    os.makedirs(os.path.join(root, ".wheel"), exist_ok=True)
    for name, text in (("BACKLOG.md", render_md(st)), ("ROADMAP.md", roadmap_md(root, st)),
                       ("CHANGELOG.md", changelog_md(root, st))):
        with open(os.path.join(root, ".wheel", name), "w", encoding="utf-8") as f:
            f.write(text)
    return st


def do_render(root):
    st = write_views(root)
    return "wrote .wheel/BACKLOG.md, .wheel/ROADMAP.md and .wheel/CHANGELOG.md in %s (%d open lugs, %d initiatives)" % (root, len(st["order"]), len(st["inits"]))


def do_roadmap(root, a):
    st = write_views(root)
    if a.json:
        return json.dumps(roadmap_data(root, st), ensure_ascii=False, indent=1)
    return roadmap_md(root, st)


def brief(it, st=None):
    d = {k: it.get(k) for k in ("rank", "id", "title", "kind", "status", "value", "effort", "goal", "initiative", "check", "source", "reason")}
    d["urgency"] = urgency_of(it)
    d["after"] = list(it.get("after") or [])
    d["class"] = class_of(st, it)
    c = live_claim(it)
    d["claimed_by"] = c["by"] if c else None
    d["branch"] = it.get("branch")
    if it["status"] in CLOSED:
        d.update(closed=it.get("closed"), closed_by=it.get("status_by"))
    return d


def do_show(root, a):
    st = load(root)
    rows = open_items(st)
    if a.all:
        rows = rows + sorted([i for i in st["items"].values() if i["rank"] is None], key=lambda i: i["id"])
    if a.json:
        return json.dumps([brief(i, st) for i in rows], ensure_ascii=False, indent=1)
    if not rows:
        return "Nothing open."
    return "\n".join("%s %-6s %-9s %-10s v%d/e%d %-6s %s%s" % (("#%d" % i["rank"]) if i["rank"] else "-", i["id"], i["kind"], i["status"], i["value"], i["effort"], i.get("initiative") or "-", i["title"], "  [next session]" if urgency_of(i) == "next_session" else "") for i in rows)


def pickable(st, it, need_check=True):
    """Ready, unclaimed autopilot work under a signed-off initiative whose check holds a backticked command (B-131;
    need_check=False leaves that last test out, to list what only a missing command holds back)."""
    ini = st["inits"].get(it.get("initiative"))
    return (it["kind"] == "autopilot" and it["status"] == "ready" and not live_claim(it)
            and ini is not None and ini["owner_signoff"].get("status") == "yes" and not ini["closed"]
            and (not need_check or bool(check_command(it.get("check")))))


def do_top(root, a):
    st = load(root)
    klass = getattr(a, "klass", None)
    rows = [i for i in open_items(st) if i["status"] != "blocked" and (not a.kind or i["kind"] == a.kind) and (not a.pickable or pickable(st, i)) and (not getattr(a, "needs_check", False) or (pickable(st, i, False) and not check_command(i.get("check"))))
            and (not klass or class_of(st, i) == klass)]
    if getattr(a, "split", False):   # the prioritised backlog as two parts, each in rank order (-n applies to each part)
        parts = {c: [i for i in rows if class_of(st, i) == c][: a.n] for c in CLASSES}
        if a.json:
            return json.dumps({c: [brief(i, st) for i in parts[c]] for c in CLASSES}, ensure_ascii=False, indent=1)
        out = []
        for c in CLASSES:
            out.append("%s work (%d):" % (c.capitalize(), len(parts[c])))
            out += ["  #%d %s [%s, %s] %s" % (i["rank"], i["id"], i["kind"], i["status"], i["title"]) for i in parts[c]] or ["  Nothing open."]
        return "\n".join(out)
    rows = rows[: a.n]
    if a.json:
        return json.dumps([brief(i, st) for i in rows], ensure_ascii=False, indent=1)
    return "\n".join("#%d %s [%s, %s, %s] %s" % (i["rank"], i["id"], i["kind"], class_of(st, i), i["status"], i["title"]) for i in rows) or "Nothing open."


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
    s.add_argument("--urgency", help="next_session | whenever (default)")
    s.add_argument("--class", dest="klass", help="build | maintain (derived from the initiative when not given)")
    s = by(sub.add_parser("status", help="move a lug through the flow"))
    s.add_argument("id")
    s.add_argument("status")
    s.add_argument("--reason", required=True)
    s.add_argument("--proof", help="closing an autopilot lug done: the token tools/verify.py printed on its pass")
    s.add_argument("--repo", help="B-292, closing done in a hub: the registered spoke whose repository holds the lug's work; the proof, landing and on-main checks run there")
    s.add_argument("--no-code", dest="no_code", help="closing done with no code commit: the reason (a state, config or decision change); without it done needs a commit naming the lug")
    s.add_argument("--statement", help="closing done: the changelog line, one plain sentence of what is now true")
    s.add_argument("--branch", help="B-223: the wheel branch holding this lug's built work (required to go back to ready or start a build while one exists)")
    s.add_argument("--superseded", help="B-223: why the lug's unchecked built branches are no longer wanted (lets it go back to ready without them)")
    s = by(sub.add_parser("reopen", help="B-124: a done lug whose work is not on main goes back to ready"))
    s.add_argument("id")
    s.add_argument("--reason", required=True)
    s.add_argument("--branch", help="the wheel branch that still holds the lug's work, if any")
    s = by(sub.add_parser("statement", help="set a lug's changelog line (open or closed lug)"))
    s.add_argument("id")
    s.add_argument("text")
    s.add_argument("--reason")
    s = sub.add_parser("changelog", help="the changelog: .wheel/CHANGELOG.md text, or --json entries")
    s.add_argument("--json", action="store_true")
    s.add_argument("--since", help="YYYY-MM-DD: only entries from that day on")
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
    s.add_argument("--urgency", help="next_session | whenever")
    s.add_argument("--class", dest="klass", help="build | maintain")
    s.add_argument("--reach", help="spokes | project: does the change reach every spoke (B-222: reorder lifts it)")
    s.add_argument("--after", help="B-132: lug ids this lug waits on, comma-separated (an empty value clears it); release-deps lifts the block")
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
    s.add_argument("--class", dest="klass", choices=CLASSES, help="only build or only maintain work")
    s.add_argument("--split", action="store_true", help="two parts: build work and maintain work, each in rank order")
    s.add_argument("--pickable", action="store_true", help="only ready autopilot lugs with budget (initiative signed off), no live claim and a backticked command in the check")
    s.add_argument("--needs-check", dest="needs_check", action="store_true", help="only the ready autopilot lugs that --pickable skips because their check holds no backticked command")
    s.add_argument("-n", type=int, default=3)
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("reorder", help="order the backlog for return on effort (dry run unless --write)")
    s.add_argument("--write", action="store_true", help="apply the order as rank events")
    s.add_argument("--by", help="who is doing this (required with --write)")
    s.add_argument("--keep", type=int, default=KEEP_TOP, help="the promised top N stay in place (default %d)" % KEEP_TOP)
    s.add_argument("--priorities", help="the hub's plans/priorities.json (default: this project's, or $WHEEL_PRIORITIES)")
    s.add_argument("--project", help="this project's name in the priorities file (default: its folder name)")
    s.add_argument("-n", type=int, default=10)
    by(sub.add_parser("release-deps", help="blocked lugs whose --after lugs are all done go back to ready"))
    sub.add_parser("render")
    s = sub.add_parser("roadmap")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("lint")
    s.add_argument("--json", action="store_true")
    sub.add_parser("verify")
    s = sub.add_parser("unlanded", help="report done lugs whose proven commit is not on main after --days (B-227)")
    s.add_argument("--days", type=float, default=1)
    s.add_argument("--json", action="store_true")
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
    if not a.root:  # --root PATH is taken literally; otherwise a worktree reads and writes the live checkout's log
        root = live_root(root)
    code = 0
    try:
        if a.cmd == "add":
            out = do_add(root, a)
        elif a.cmd == "statement":
            out = do_statement(root, a)
        elif a.cmd == "changelog":
            out = do_changelog(root, a)
        elif a.cmd == "status":
            out = do_status(root, a)
        elif a.cmd == "reopen":
            out = do_reopen(root, a)
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
        elif a.cmd == "reorder":
            need(not a.write or (a.by and a.by.strip()), "reorder --write needs --by")
            out = do_reorder(root, a)
        elif a.cmd == "release-deps":
            out = do_release_deps(root, a)
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
        elif a.cmd == "unlanded":
            out = do_unlanded(root, a)
        else:
            out = do_history(root, a.id)
    except Refused as e:
        sys.stderr.write("lug: refused: %s\n" % e)
        return 1
    if (a.cmd in WRITES or (a.cmd == "reorder" and a.write and os.path.isfile(log_path(root)))) and not (a.cmd == "initiative" and a.icmd == "show"):
        try:
            with Locked(root):
                write_views(root)
                why = None if a.root else commit_lug_rows(root)
            if why:
                sys.stderr.write("lug: the rows are written but not committed on main (%s); the next lug write or the turn save carries them\n" % why)
        except OSError:
            pass
    print(out)
    return code


if __name__ == "__main__":
    sys.exit(main())
