#!/usr/bin/env python3
"""
thread_landing.py — the landing machinery.

WHY THIS EXISTS
---------------
The Resident digest carries open_threads, and the closure vector renders the
line "each needs a landing condition CHECKED, then executed or routed." An
adversarial review (s138) called that out precisely: no landing-condition data
existed anywhere in the system, and no mechanism produced one. The sentence was
prose, not machinery. This is the machinery.

THE PROBLEM IT SOLVES
---------------------
Threads accumulate. A session writes "wire the closure vector" into its open
list; three sessions later the work is done but the thread is still there,
because nothing ever checked. The operator then reads a desk that looks full
when it is not, loses trust in the list, and stops reading it — which is how a
continuity system dies. Measured at s138: 497 open lugs, 164 uncompleted
savepoints, 10 of the last 15 sessions ending with no closeout at all.

A thread without a landing condition is chatter. A thread WITH one is
dispatchable work that can prove when it is finished.

LANDING CONDITION KINDS (all mechanically checkable — no LLM judgment)
-----------------------------------------------------------------------
  lug_completed   {"kind":"lug_completed","id":"impl-foo-v1"}
                  Lands when a lug of that id appears anywhere under a
                  completed/, done/, closed/ or resolved/ status directory.
  file_exists     {"kind":"file_exists","path":"tools/foo.py"}
                  Lands when the path exists (repo-relative or absolute).
  file_contains   {"kind":"file_contains","path":"x.sh","needle":"FOO"}
                  Lands when the file exists AND contains the needle.
  commit          {"kind":"commit","sha":"abc1234"}
                  Lands when that commit is an ancestor of HEAD.
  command         {"kind":"command","cmd":"pytest -q tests/x.py"}
                  Lands when the command exits 0. Opt-in via --run-commands;
                  never executed during a wakeup read.
  manual          {"kind":"manual"}  — explicitly needs a human. Never lands.
  (absent)        Unlanded and UNCHECKABLE. Reported separately and loudly:
                  these are the chatter the doctrine warns about.

DESIGN RULES
------------
  * NEVER auto-land on absence of evidence. A missing landing condition means
    UNCHECKABLE, never LANDED. Failing open here would silently erase real work
    from the desk — the exact inverse of the bug this replaces (threads that
    could never clear) and equally dishonest.
  * SEPARATE the three states in output: landed / open / uncheckable. Collapsing
    uncheckable into open hides the chatter; collapsing it into landed loses work.
  * READ-ONLY BY DEFAULT. `check` never mutates. Clearing is an explicit `clear`.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

LANDING_VERSION = "1.0.0"
DONE_DIRS = {"completed", "done", "closed", "resolved"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def find_spoke_root(start=None):
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(cur, "WAI-Harness")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def paths(root):
    local = os.path.join(root, "WAI-Harness", "spoke", "local")
    return {
        "root": root,
        "digest": os.path.join(local, "resident", "digest.json"),
        "lugs": os.path.join(local, "lugs", "bytype"),
        "log": os.path.join(local, "runtime", "thread-landing.jsonl"),
    }


# ── the checks ───────────────────────────────────────────────────────────────

def _check_lug_completed(p, cond):
    lug_id = cond.get("id")
    if not lug_id:
        return False, "landing condition has no lug id"
    for dirpath, _dirs, files in os.walk(p["lugs"]):
        if os.path.basename(dirpath) not in DONE_DIRS:
            continue
        for f in files:
            if f == f"{lug_id}.json" or f.startswith(f"{lug_id}."):
                rel = os.path.relpath(os.path.join(dirpath, f), p["root"])
                return True, f"lug in a done state: {rel}"
    return False, f"no completed lug named {lug_id}"


def _resolve(p, path):
    return path if os.path.isabs(path) else os.path.join(p["root"], path)


def _check_file_exists(p, cond):
    path = cond.get("path")
    if not path:
        return False, "landing condition has no path"
    full = _resolve(p, path)
    return (True, f"exists: {path}") if os.path.exists(full) else (False, f"missing: {path}")


def _check_file_contains(p, cond):
    path, needle = cond.get("path"), cond.get("needle")
    if not path or needle is None:
        return False, "landing condition needs both path and needle"
    full = _resolve(p, path)
    if not os.path.isfile(full):
        return False, f"missing: {path}"
    try:
        with open(full, errors="replace") as fh:
            body = fh.read()
    except OSError as e:
        return False, f"unreadable {path}: {e}"
    return (True, f"{path} contains {needle!r}") if needle in body \
        else (False, f"{path} lacks {needle!r}")


def _check_commit(p, cond):
    sha = cond.get("sha")
    if not sha:
        return False, "landing condition has no sha"
    r = subprocess.run(["git", "-C", p["root"], "merge-base", "--is-ancestor", sha, "HEAD"],
                       capture_output=True, text=True)
    return (True, f"{sha[:8]} is an ancestor of HEAD") if r.returncode == 0 \
        else (False, f"{sha[:8]} not in history")


def _check_command(p, cond, run_commands):
    cmd = cond.get("cmd")
    if not cmd:
        return False, "landing condition has no cmd"
    if not run_commands:
        return False, f"command not run (pass --run-commands): {cmd}"
    r = subprocess.run(cmd, shell=True, cwd=p["root"], capture_output=True, text=True)
    return (r.returncode == 0, f"`{cmd}` exit {r.returncode}")


CHECKS = {
    "lug_completed": _check_lug_completed,
    "file_exists": _check_file_exists,
    "file_contains": _check_file_contains,
    "commit": _check_commit,
}


def evaluate(p, thread, run_commands=False):
    """Returns (state, reason) where state is landed | open | uncheckable."""
    # Guards (s138, second Fable pass): a malformed thread must degrade to
    # uncheckable, never crash the wakeup and never read as landed.
    if not isinstance(thread, dict):
        return "uncheckable", f"malformed thread (not an object): {str(thread)[:60]}"
    cond = thread.get("landing")
    if cond is not None and not isinstance(cond, dict):
        return "uncheckable", f"malformed landing condition (not an object): {str(cond)[:60]}"
    if not cond:
        # NEVER treat absence as landed. This is the load-bearing asymmetry.
        return "uncheckable", "no landing condition — this is chatter, not dispatchable work"
    kind = cond.get("kind")
    if kind == "manual":
        return "open", cond.get("note") or "explicitly manual — needs a human"
    if kind == "command":
        ok, why = _check_command(p, cond, run_commands)
        return ("landed" if ok else "open"), why
    fn = CHECKS.get(kind)
    if not fn:
        return "uncheckable", f"unknown landing kind {kind!r}"
    ok, why = fn(p, cond)
    return ("landed" if ok else "open"), why


def load_digest(p):
    if not os.path.isfile(p["digest"]):
        return None
    try:
        with open(p["digest"]) as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def assess(p, run_commands=False):
    d = load_digest(p)
    if d is None:
        return None, []
    threads = d.get("open_threads")
    if threads is None or not isinstance(threads, list):
        # A null/missing/non-list open_threads used to print a cheerful
        # "0 threads — clear desk". Absence of data is NOT a clear desk.
        return d, None
    out = []
    for t in threads:
        state, why = evaluate(p, t, run_commands)
        # A non-dict thread cannot be **-unpacked; wrap it so a malformed entry
        # degrades to a visible uncheckable row instead of crashing wakeup.
        base = dict(t) if isinstance(t, dict) else {"text": str(t)}
        base.setdefault("text", "(thread has no text field)")
        out.append({**base, "_state": state, "_why": why})
    return d, out


def cmd_check(args, p):
    d, rows = assess(p, args.run_commands)
    if d is None:
        print("thread_landing: DEGRADED — no readable resident digest at "
              f"{p['digest']}. Threads UNKNOWN, not zero.", file=sys.stderr)
        return 3
    if rows is None:
        print("THREAD LANDING: DEGRADED — digest has no usable open_threads list "
              "(null or wrong type). Desk state is UNKNOWN, not clear.", file=sys.stderr)
        print("THREAD LANDING: DEGRADED — open_threads missing or not a list. "
              "Desk state UNKNOWN, not clear.")
        return 3
    landed = [r for r in rows if r["_state"] == "landed"]
    still = [r for r in rows if r["_state"] == "open"]
    unchk = [r for r in rows if r["_state"] == "uncheckable"]

    if args.format == "json":
        print(json.dumps({"version": LANDING_VERSION, "total": len(rows),
                          "landed": landed, "open": still,
                          "uncheckable": unchk}, indent=2, ensure_ascii=False))
        return 0

    print(f"THREAD LANDING — {len(rows)} thread(s): "
          f"{len(landed)} landed, {len(still)} open, {len(unchk)} uncheckable")
    if landed:
        print(f"\nLANDED ({len(landed)}) — provable, clear with `thread_landing.py clear`:")
        for r in landed:
            print(f"  [x] {str(r.get('text',''))[:100]}\n        {r['_why']}")
    if still:
        print(f"\nOPEN ({len(still)}) — landing condition checked and NOT met:")
        for r in still:
            print(f"  [ ] {str(r.get('text',''))[:100]}\n        {r['_why']}")
    if unchk:
        print(f"\nUNCHECKABLE ({len(unchk)}) — no landing condition. Doctrine: an open "
              "thread without one is chatter.\n  Give each a landing condition or route it to a lug:")
        for r in unchk:
            print(f"  [?] {str(r.get('text',''))[:100]}")
    return 0


def cmd_clear(args, p):
    """Remove provably-landed threads from the digest. The only mutating path."""
    d, rows = assess(p, args.run_commands)
    if d is None:
        print("thread_landing: DEGRADED — no readable digest; refusing to clear.",
              file=sys.stderr)
        return 3
    if rows is None:
        print("thread_landing: DEGRADED — unusable open_threads; refusing to clear.",
              file=sys.stderr)
        return 3
    landed = [r for r in rows if r["_state"] == "landed"]
    if not landed:
        print("thread_landing: nothing provably landed — digest unchanged.")
        return 0
    keep = [t for t, r in zip(d.get("open_threads", []), rows) if r["_state"] != "landed"]
    if args.dry_run:
        print(f"thread_landing: DRY RUN — would clear {len(landed)}, keep {len(keep)}")
        for r in landed:
            print(f"  [x] {r['text'][:100]} — {r['_why']}")
        return 0
    d["open_threads"] = keep
    d["landing_last_run"] = _now()
    tmp = p["digest"] + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(d, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, p["digest"])
    os.makedirs(os.path.dirname(p["log"]), exist_ok=True)
    with open(p["log"], "a") as fh:
        for r in landed:
            fh.write(json.dumps({"ts": _now(), "event": "thread_landed",
                                 "text": r["text"], "why": r["_why"],
                                 "session": r.get("session")}, ensure_ascii=False) + "\n")
    print(f"thread_landing: cleared {len(landed)} landed thread(s); {len(keep)} remain.")
    for r in landed:
        print(f"  [x] {r['text'][:100]}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check and clear landed open threads")
    ap.add_argument("--spoke-path", default=None)
    ap.add_argument("--run-commands", action="store_true",
                    help="execute command-kind landing conditions (never during wakeup)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="read-only assessment")
    c.add_argument("--format", choices=["text", "json"], default="text")
    cl = sub.add_parser("clear", help="remove provably-landed threads from the digest")
    cl.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    p = paths(find_spoke_root(args.spoke_path))
    return {"check": cmd_check, "clear": cmd_clear}[args.cmd](args, p)


if __name__ == "__main__":
    sys.exit(main())
