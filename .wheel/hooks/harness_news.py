#!/usr/bin/env python3
"""Harness news (B-382): running sessions learn capabilities merged after they started.

Usage:
  python3 harness_news.py land --lug ID --title T --usage "when to use it: command" [--files F ...] [--reinstall]
        After a land: if any merged file is under a harness path, append one line to news.jsonl; with
        --reinstall, re-run `basher sync --apply --only claude-command-restart` so restart.md is current.
        --files omitted: read the changed files of HEAD (git diff-tree) in the current directory.
  python3 harness_news.py prompt     UserPromptSubmit hook: JSON on stdin, prints additionalContext with the
        lines this session has not had, for sessions that started BEFORE the line; logs each delivery.
  python3 harness_news.py wake [DAYS]  lines from the last DAYS (default 7): the wake prompt's section for new sessions.
  python3 harness_news.py undelivered   count of lines not yet delivered to a session seen in the last 2 days
  python3 harness_news.py test
State (dir BASHER_NEWS_DIR, default ~/.local/state/basher): news.jsonl (id, ts, lug, text), sessions.json (session ->
start), deliveries.jsonl (news id, session, ts, via). A session started at or after a line's time gets it from the
wake prompt, never from the hook. Wiring: kit part P-026 (UserPromptSubmit, .wheel/hooks/harness_news.py prompt); the land step is basher/src/wcl.py merge_branch."""
import datetime, json, os, subprocess, sys, tempfile

sys.dont_write_bytecode = True
HARNESS_PATHS = ("basher/src/", "basher/desired/", "basher/desired.json", ".wheel/hooks/", "tools/hooks/")


def sdir():
    d = os.environ.get("BASHER_NEWS_DIR") or os.path.expanduser("~/.local/state/basher")
    os.makedirs(d, exist_ok=True)
    return d


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def iso(t):
    return t.isoformat(timespec="seconds")


def rows(name):
    out = []
    try:
        for l in open(os.path.join(sdir(), name)):
            try:
                out.append(json.loads(l))
            except ValueError:
                pass
    except OSError:
        pass
    return out


def append(name, row):
    with open(os.path.join(sdir(), name), "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def is_harness(files):
    return [f for f in files if f.startswith(HARNESS_PATHS)]


def land(lug, title, usage, files, reinstall=False, at=None):
    """Append the news line if the merge touched harness paths. Returns the row or None."""
    hit = is_harness(files)
    if not hit:
        return None
    if any(r.get("lug") == lug for r in rows("news.jsonl")):
        return None  # a lug's line is written once
    row = {"id": "N-%d" % (len(rows("news.jsonl")) + 1), "ts": iso(at or now()), "lug": lug,
           "text": "%s (%s): %s" % (title, lug, usage), "paths": hit[:5]}
    append("news.jsonl", row)
    if reinstall:
        subprocess.run([os.path.expanduser("~/.local/bin/basher"), "sync", "--apply", "--only", "claude-command-restart"],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
    return row


def session_start(sid, transcript=None, at=None):
    """When the session began: the earlier of first sight and its transcript's birth; remembered."""
    p = os.path.join(sdir(), "sessions.json")
    try:
        seen = json.load(open(p))
    except (OSError, ValueError):
        seen = {}
    if sid not in seen:
        seen[sid] = iso(at or now())
        if transcript:
            try:
                b = datetime.datetime.fromtimestamp(os.stat(transcript).st_ctime, datetime.timezone.utc)
                seen[sid] = min(seen[sid], iso(b))
            except OSError:
                pass
        json.dump(seen, open(p, "w"))
    return seen[sid]


def deliver(sid, transcript=None, at=None):
    """The news lines this session has not had and started before. Logs each delivery."""
    start = session_start(sid, transcript, at)
    had = {r["news"] for r in rows("deliveries.jsonl") if r.get("session") == sid}
    out = []
    for n in rows("news.jsonl"):
        if n["id"] in had or n["ts"] <= start:
            continue
        append("deliveries.jsonl", {"news": n["id"], "session": sid, "ts": iso(at or now()), "via": "prompt"})
        out.append(n["text"])
    return out


def wake(days=7, at=None):
    cut = iso((at or now()) - datetime.timedelta(days=days))
    return [n["text"] for n in rows("news.jsonl") if n["ts"] >= cut]


def undelivered(at=None):
    """Lines (last 2 days) that a recently seen session, started before the line, has not had."""
    try:
        seen = json.load(open(os.path.join(sdir(), "sessions.json")))
    except (OSError, ValueError):
        return 0
    cut = iso((at or now()) - datetime.timedelta(days=2))
    had = {(r["news"], r["session"]) for r in rows("deliveries.jsonl")}
    return sum(1 for n in rows("news.jsonl") for s, t in seen.items()
               if t < n["ts"] and n["ts"] >= cut and (n["id"], s) not in had)


def prompt_hook():
    try:
        hook = json.load(sys.stdin)
        lines = deliver(hook.get("session_id") or "unknown", hook.get("transcript_path"))
    except Exception:
        return  # news must never break a prompt
    if lines:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext":
            "Harness news (new since this session started; tell the owner in one line, then carry on): " + " | ".join(lines)}}))


def test():
    import io
    os.environ["BASHER_NEWS_DIR"] = tempfile.mkdtemp(prefix="news-test-")
    t0 = now()
    mins = lambda m: t0 + datetime.timedelta(minutes=m)
    ok = []

    def check(name, cond):
        ok.append(bool(cond))
        print(("ok   " if cond else "FAIL ") + name)

    session_start("old", at=mins(-10))
    check("no news yet: nothing delivered", deliver("old", at=t0) == [])
    check("land outside harness paths writes nothing", land("B-1", "x", "u", ["tools/foo.py"], at=t0) is None)
    row = land("B-382", "Harness news", "when a land changes the harness: tools/harness_news.py",
               ["basher/src/wcl.py", "README.md"], at=t0)
    check("land under a harness path writes one line", row is not None and len(rows("news.jsonl")) == 1)
    check("the same lug is not written twice", land("B-382", "t", "u", [".wheel/hooks/guard.py"], at=t0) is None)
    session_start("new", at=mins(5))
    first = deliver("old", at=mins(6))
    check("old session gets the line on its next turn", len(first) == 1 and "Harness news" in first[0])
    check("old session gets it exactly once", deliver("old", at=mins(6)) == [] and deliver("old", at=mins(7)) == [])
    check("new session gets nothing from the hook", deliver("new", at=mins(6)) == [])
    check("new session gets it from the wake prompt", wake(at=mins(6)) == first)
    check("the delivery is logged once", [(r["news"], r["session"]) for r in rows("deliveries.jsonl")] == [("N-1", "old")])
    check("nothing left undelivered", undelivered(at=mins(6)) == 0)
    session_start("mid", at=mins(7))
    land("B-9", "Another", "use it", ["tools/hooks/x.py"], at=mins(8))
    check("three sessions are waiting for line 2", undelivered(at=mins(9)) == 3)
    check("each gets line 2 once", len(deliver("old", at=mins(9))) == 1 and len(deliver("mid", at=mins(9))) == 1
          and len(deliver("new", at=mins(9))) == 1 and deliver("old", at=mins(9)) == [])
    check("undelivered back to 0", undelivered(at=mins(9)) == 0)
    session_start("hooked", at=mins(-1440))
    sin, sout, buf = sys.stdin, sys.stdout, io.StringIO()
    sys.stdin, sys.stdout = io.StringIO(json.dumps({"session_id": "hooked"})), buf
    try:
        prompt_hook()
    finally:
        sys.stdin, sys.stdout = sin, sout
    out = json.loads(buf.getvalue()) if buf.getvalue() else {}
    check("hook prints additionalContext for a session started before",
          "Harness news" in out.get("hookSpecificOutput", {}).get("additionalContext", ""))
    check("hook delivery logged", any(r["session"] == "hooked" for r in rows("deliveries.jsonl")))
    print("PASS" if all(ok) else "FAIL")
    return 0 if all(ok) else 1


def main(a):
    if not a:
        print(__doc__)
        return 2
    c = a[0]
    if c == "test":
        return test()
    if c == "prompt":
        prompt_hook()
        return 0
    if c == "wake":
        for l in wake(int(a[1]) if len(a) > 1 else 7):
            print("- " + l)
        return 0
    if c == "undelivered":
        print(undelivered())
        return 0
    if c == "land":
        g, k = {"files": []}, None
        for x in a[1:]:
            if x.startswith("--"):
                k = x[2:]
                g[k] = [] if k == "files" else True
            elif k == "files":
                g["files"].append(x)
            elif k:
                g[k] = x
        files = g["files"] or subprocess.run(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "-m", "HEAD"],
                                             capture_output=True, text=True).stdout.split()
        r = land(g.get("lug", "?"), g.get("title", "harness change"), g.get("usage", ""), files, bool(g.get("reinstall")))
        print(r["text"] if r else "no harness paths touched: no news")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
