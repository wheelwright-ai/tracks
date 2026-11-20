#!/usr/bin/env python3
"""Stop hook: every turn leaves one point in a portable Track file (the tracks project's format).

Reads the hook's JSON on stdin (session_id, transcript_path), reads this turn from the transcript, and appends one
point to .wheel/tracks/WAI_Track-<date>-<time>-Claude-<model>.jsonl (a session_start line first). Tokens are
summed from the transcript's usage, or left out when unreadable: never a guessed number. Never blocks the turn.

It also answers with the turn status line the owner reads at the end of every turn (a Stop hook systemMessage):
"Track turn 7 · Opus 5.5 H · 12:41 PM PST" (no token figure: the transcript sums re-read context per
tool call, which would overstate the turn). The effort letter comes from the Stop payload when Claude
Code sends one, else CLAUDE_EFFORT, else effortLevel in the project's then the global settings; left out when unknown.

`track_write.py prompt` (a UserPromptSubmit hook) hands the same line to the model as context, to end its reply with:
a Stop hook's systemMessage is not shown in every view (focus mode shows only the final message), and the owner
reads this line every turn. The turn number is the one this turn's Stop point will carry."""
import json, os, sys, datetime

sys.dont_write_bytecode = True


def model_name(m):
    """claude-opus-5-5 -> Opus 5.5; claude-fable-5-2 -> Fable 5.2; anything unexpected is shown as it is."""
    if not m or m.startswith("<"):
        return None
    parts = [p for p in m.replace("claude-", "", 1).split("-") if not (p.isdigit() and len(p) == 8)]
    name = [p for p in parts if not p.isdigit()]
    ver = [p for p in parts if p.isdigit()]
    return (" ".join(w.capitalize() for w in name) + (" " + ".".join(ver) if ver else "")).strip() or m


def effort_letter(hook, root):
    e = hook.get("effort")
    if isinstance(e, dict):
        e = e.get("level") or e.get("name")
    e = e or os.environ.get("CLAUDE_EFFORT")
    if not e:
        for f in (os.path.join(root, ".claude", "settings.local.json"), os.path.join(root, ".claude", "settings.json"),
                  os.path.join(os.path.expanduser("~"), ".claude", "settings.json")):
            try:
                e = json.load(open(f)).get("effortLevel")
            except Exception:
                e = None
            if e:
                break
    return str(e)[:1].upper() if e else ""


def first_ts(path):
    try:
        with open(path) as f:
            for _ in range(20):
                line = f.readline()
                if not line:
                    break
                t = json.loads(line).get("timestamp")
                if t:
                    return t
    except Exception:
        pass
    return None


def session_number(root, transcript):
    """This session's number among all Claude sessions of the project, its worktrees included (the old footer's s119):
    the count of the project's transcripts that began no later than this one. None when unknown."""
    if not transcript or not os.path.exists(transcript):
        return None
    import glob, subprocess
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True, timeout=5)
        main = os.path.dirname(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else root
    except Exception:
        main = root
    key = main.replace("/", "-").replace(".", "-")
    base = os.path.dirname(os.path.dirname(transcript))
    mine = first_ts(transcript)
    if not mine:
        return None
    n = 0
    for d in glob.glob(os.path.join(base, key + "*")):
        for f in glob.glob(os.path.join(d, "*.jsonl")):
            t = first_ts(f) if f != transcript else mine
            if t and t <= mine:
                n += 1
    return n or None


def session_number_cached(root, transcript):
    """B-057: the session's number never changes once known (a later session starts later, so it cannot move this one), so
    the footer keeps it in .wheel/tracks/.session-numbers.json instead of globbing every transcript each turn. A number
    that could not be found (None) is never cached, so the next turn tries again."""
    path = os.path.join(root, ".wheel", "tracks", ".session-numbers.json")
    key = transcript or ""
    try:
        cache = json.load(open(path))
        if not isinstance(cache, dict):
            cache = {}
    except Exception:
        cache = {}
    if key and isinstance(cache.get(key), int):
        return cache[key]
    n = session_number(root, transcript)
    if n and key:
        cache[key] = n
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp%d" % os.getpid()
            with open(tmp, "w") as f:
                json.dump(cache, f)
            os.replace(tmp, path)
        except Exception:
            pass
    return n


def head_sha(root):
    import subprocess
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "--short=8", "HEAD"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or None
    except Exception:
        return None


def kit_version(root):
    """The project's installed kit version; in the hub, the kit it releases."""
    for f in (os.path.join(root, "tools", "kit", "MANIFEST.json"), os.path.join(root, ".wheel", "kit.json")):
        try:
            return json.load(open(f)).get("version")
        except Exception:
            continue
    return None


def gold_since(root, since_iso):
    """Proven work since a moment: hub verdict rows that passed, plus lugs closed done with a proof (W-184)."""
    n = 0
    for name, ok in (("ledger.jsonl", lambda e: e.get("kind") == "verdict" and e.get("result") == "pass"),
                     (os.path.join(".wheel", "backlog.jsonl"), lambda e: e.get("event") == "status" and e.get("status") == "done" and e.get("proof"))):
        try:
            for line in open(os.path.join(root, name)):
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                at = e.get("at") or ""
                if ok(e) and at and parse_any(at) and parse_any(at) >= since_iso:
                    n += 1
        except Exception:
            pass
    return n


def parse_any(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(datetime.timezone.utc)
    except Exception:
        return None


# Turn weight (the owner, 2026-11-19: "help me gauge the target price per turn and as it grows indicate the multiple of
# that expected pace"; 2026-11-20: "we have limits [...] we need a diff way to express if this is running efficiently or
# unnecessarily heavy (which means I should restart asap)"). The owner's sessions run on a subscription with 5-hour and
# weekly limits, so the footer shows no dollars: it shows
#   - the verdict, from the context size against a fresh start (every step re-reads the whole context, so a long
#     session makes every turn heavier, and only a restart clears it);
#   - the last turn's weight against this project's normal turn (median, 7 days), a unitless multiple;
#   - the subscription's 5-hour limit used, and how far it moved (from the status line's usage.json; other sessions
#     and wakes share the limit, so the move is not this session's alone).
# Weights are worked out at Claude API list prices so a cache read counts for less than fresh input and output for
# more; the prices only set the mix, never a shown figure. claude-api table cached 2026-11-03, read 2026-11-20; Haiku's
# cache read from tools/coding_bench.py (2026-11-09). Cache writes: 1-hour 2x input, 5-minute 1.25x. Fast mode 2x.
PRICES_SET = "2026-11-03"
PRICES = {"fable": (8.0, 40.0, 0.20), "opus": (4.0, 20.0, 0.20), "sonnet": (2.0, 10.0, 0.10), "haiku": (0.10, 0.50, 0.01)}
PROMPT_SKIP = ("<bash-stdout>", "<bash-stderr>", "<local-command-stdout>", "<local-command-caveat>", "<system-reminder>")
NORMAL_DAYS, NORMAL_MIN_TURNS = 7, 10
FRESH_DEFAULT = 47000          # tokens a fresh hub session starts with (median first call, 14 sessions, 2026-11-20)
HEAVY, TOO_HEAVY = 2.5, 4.0    # context as a multiple of a fresh start: restart at the next stop / restart now
USAGE = os.path.join(os.path.expanduser("~"), ".local", "state", "basher", "usage.json")
USAGE_FRESH_S = 1800           # an older usage.json is left out: never a stale figure


def message_cost(model, u):
    """Weight of one API call at list price (dollars, used only as a relative measure), or None for a model with no price."""
    if not u:
        return 0.0
    fam = next((f for f in PRICES if f in (model or "").lower()), None)
    if not fam:
        return None
    i, o, cr = PRICES[fam]
    cc = u.get("cache_creation") or {}
    w1h, w5m = cc.get("ephemeral_1h_input_tokens"), cc.get("ephemeral_5m_input_tokens")
    if w1h is None and w5m is None:
        w1h, w5m = 0, u.get("cache_creation_input_tokens") or 0
    usd = ((u.get("input_tokens") or 0) * i + (u.get("output_tokens") or 0) * o
           + (u.get("cache_read_input_tokens") or 0) * cr + (w1h or 0) * 2 * i + (w5m or 0) * 1.25 * i) / 1e6
    return usd * 2 if u.get("speed") == "fast" else usd


def context_of(u):
    """Tokens one call read: its whole context."""
    u = u or {}
    return (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)


def _is_prompt(e):
    """A transcript entry that starts a turn: the owner's own words (or a relayed message), not a tool result."""
    if e.get("type") != "user":
        return False
    c = (e.get("message") or {}).get("content")
    return isinstance(c, str) and bool(c.strip()) and not c.strip().startswith(PROMPT_SKIP)


def read_turns(path):
    """(weight per turn oldest first, first call's context, last call's context) for one transcript. Claude Code writes
    one line per content block with the same message id and usage, so each call counts once (by id, last line wins).
    Subagent transcripts are not added."""
    turns, calls = [], {}
    try:
        for line in open(path or ""):
            try:
                e = json.loads(line)
            except Exception:
                continue
            if _is_prompt(e):
                turns.append(0.0)
            elif e.get("type") == "assistant":
                m = e.get("message") or {}
                key = m.get("id") or "anon-%d" % len(calls)
                if key not in calls and m.get("usage"):
                    calls[key] = None   # keeps first-seen order
                if m.get("usage"):
                    calls[key] = (max(len(turns) - 1, 0), m.get("model"), m.get("usage"))
    except Exception:
        return [], 0, 0
    turns = turns or [0.0]
    for t, model, u in calls.values():
        c = message_cost(model, u)
        if c:
            turns[t] += c
    seq = [c for c in calls.values() if c]
    return turns, (context_of(seq[0][2]) if seq else 0), (context_of(seq[-1][2]) if seq else 0)


def turn_costs(path):
    return read_turns(path)[0]


def _interactive(path):
    """True for an owner session (entrypoint cli), False for headless wakes, builders and checkers."""
    try:
        with open(path) as f:
            for _, line in zip(range(40), f):
                if '"entrypoint"' in line:
                    return json.loads(line).get("entrypoint") == "cli"
    except Exception:
        pass
    return False


def baseline(root, transcript):
    """{normal: median interactive turn weight, fresh: median first-call context} over the last 7 days of this project
    (main checkout and its worktrees), worked out once a day and cached in .wheel/tracks/.cost-target.json. normal is
    None until there are 10 turns to go on; fresh falls back to FRESH_DEFAULT."""
    import glob, statistics, time
    today = datetime.date.today().isoformat()
    cache = os.path.join(root, ".wheel", "tracks", ".cost-target.json")
    try:
        c = json.load(open(cache))
        if c.get("day") == today and c.get("prices") == PRICES_SET and "fresh" in c:
            return c
    except Exception:
        pass
    weights, firsts = [], []
    try:
        here = os.path.dirname(os.path.abspath(transcript or ""))
        base = os.path.basename(here).split("--worktrees-")[0]
        cutoff = time.time() - NORMAL_DAYS * 86400
        for d in glob.glob(os.path.join(os.path.dirname(here), glob.escape(base) + "*")):
            name = os.path.basename(d)
            if name != base and not name.startswith(base + "--worktrees-"):
                continue
            for f in glob.glob(os.path.join(d, "*.jsonl")):
                if os.path.getmtime(f) >= cutoff and _interactive(f):
                    t, first, _ = read_turns(f)
                    weights += [x for x in t if x > 0]
                    if first:
                        firsts.append(first)
    except Exception:
        pass
    c = {"day": today, "prices": PRICES_SET, "turns": len(weights), "sessions": len(firsts),
         "normal": round(statistics.median(weights), 4) if len(weights) >= NORMAL_MIN_TURNS else None,
         "fresh": int(statistics.median(firsts)) if len(firsts) >= 3 else FRESH_DEFAULT}
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        json.dump(c, open(cache, "w"))
    except Exception:
        pass
    return c


def usage_now(path=None):
    """(5-hour percent used, reset time) from the status line's usage.json, or None when missing or stale."""
    import time
    try:
        d = json.load(open(path or USAGE))
        at = parse_any(d.get("written_at"))
        if not at or time.time() - at.timestamp() > USAGE_FRESH_S:
            return None
        f = d.get("five_hour") or {}
        return (int(f["used_pct"]), f.get("resets_at")) if f.get("used_pct") is not None else None
    except Exception:
        return None


def gauge(label, weight, normal, ctx, fresh, pct=None, moved=None):
    """The verdict-first gauge, ASCII, no pipes:
    'Heavy, restart at the next stop: context 150K is 3.2x a fresh start; last turn 2.6x a normal turn. 5-hour limit 32% used (+3%).'"""
    if not ctx:
        return ""
    r = ctx / float(fresh or FRESH_DEFAULT)
    verdict = "Too heavy, restart now" if r >= TOO_HEAVY else "Heavy, restart at the next stop" if r >= HEAVY else "Light"
    out = "%s: context %dK is %.1fx a fresh start" % (verdict, round(ctx / 1000.0), r)
    if weight and normal:
        out += "; %s %.1fx a normal turn" % (label, weight / normal)
    out += "."
    if pct is not None:
        out += " 5-hour limit %d%% used%s." % (pct, " (+%d%%)" % moved if moved else "")
    return out


def footer_cost(root, transcript, stop, sid="unknown"):
    """The gauge for the footer. At the prompt the turn about to run has not happened, so it weighs the last finished
    turn and the limit's move since the last prompt; at Stop, the turn that just ended and the move during it. Never raises."""
    try:
        weights, _, ctx = read_turns(transcript)
        if not stop and weights and weights[-1] == 0:
            weights = weights[:-1]   # this prompt is already written but nothing has run for it
        b = baseline(root, transcript)
        u = usage_now()
        moved = None
        mark = os.path.join(root, ".wheel", "tracks", ".turn-limit-%s" % sid[:36])
        if u:
            try:
                was = json.load(open(mark))
                if was.get("resets_at") == u[1]:
                    moved = u[0] - int(was.get("pct"))
            except Exception:
                pass
            if not stop:
                try:
                    json.dump({"pct": u[0], "resets_at": u[1]}, open(mark, "w"))
                except Exception:
                    pass
        return gauge("this turn" if stop else "last turn", weights[-1] if weights else 0, b.get("normal"), ctx,
                     b.get("fresh"), u[0] if u else None, moved)
    except Exception:
        return ""


def status_line(turn, model, hook, root, gold=None, cost=""):
    """The turn footer the owner reads every turn, in the track prompt's harness shape (track-prompt-lab v4.0.0,
    turn_footer.cc.harness_format), ASCII pipes only:
    s{session} | Turn {n} | {day}, {month} {d}, {year} | {time} {tz} | {model effort} | {commit} | kit v{N} | Gold: +{count}
    A value the harness does not have is the word unknown, never a guess. gold=None leaves {gold} for the model."""
    now = datetime.datetime.now().astimezone()
    sn = session_number_cached(root, hook.get("transcript_path"))
    m = model_name(model)
    letter = effort_letter(hook, root) if m else ""
    kv = kit_version(root)
    bits = ["s%s" % (sn if sn else "unknown"), "Turn %d" % turn, now.strftime("%a, %b %-d, %Y"), now.strftime("%-I:%M %p %Z"),
            (m + (" " + letter if letter else "")) if m else "unknown", head_sha(root) or "unknown",
            "kit v%s" % kv if kv else "kit unknown"] + ([cost] if cost else []) + \
           ["Gold: +%s" % ("{gold}" if gold is None else gold)]
    return " | ".join(bits)


def last_model(path):
    """The model of the last assistant message in the transcript, or None."""
    model = None
    try:
        for line in open(path or ""):
            if '"assistant"' in line:
                try:
                    m = (json.loads(line).get("message") or {}).get("model")
                    model = m or model
                except Exception:
                    pass
    except Exception:
        pass
    return model


def prompt_hook():
    """UserPromptSubmit: give the model the turn line to end its final message with."""
    if os.environ.get("WHEEL_NO_TRACK") == "1":
        return
    try:
        hook = json.load(sys.stdin)
    except Exception:
        return
    root = hook.get("cwd") or os.getcwd()
    try:
        idx = json.load(open(os.path.join(root, ".wheel", "tracks", ".index.json")))
    except Exception:
        idx = {}
    sid = hook.get("session_id") or "unknown"
    turn = int((idx.get(sid) or {}).get("turns") or 0) + 1
    model = hook.get("model") if isinstance(hook.get("model"), str) else None
    line = status_line(turn, model or last_model(hook.get("transcript_path")), hook, root,
                       cost=footer_cost(root, hook.get("transcript_path"), stop=False, sid=sid))
    try:   # when this turn began, so the Stop hook can count the proven work done in it
        tdir = os.path.join(root, ".wheel", "tracks")
        os.makedirs(tdir, exist_ok=True)
        with open(os.path.join(tdir, ".turn-start-%s" % sid[:36]), "w") as f:
            f.write(datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
    except Exception:
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext":
        "Track footer for this turn (the owner reads it every turn; the track prompt's turn_footer): end your final message "
        "with this line, alone, in backticks, replacing {gold} with the number of verdicts that passed and lugs closed done "
        "with a proof during this turn (0 if none), every other value exactly as given: `%s`" % line}}))


def main():
    if os.environ.get("WHEEL_NO_TRACK") == "1":
        return  # checker sessions leave no track
    try:
        hook = json.load(sys.stdin)
    except Exception:
        return
    root = hook.get("cwd") or os.getcwd()
    tdir = os.path.join(root, ".wheel", "tracks")
    os.makedirs(tdir, exist_ok=True)
    idx_p = os.path.join(tdir, ".index.json")
    try:
        idx = json.load(open(idx_p))
    except Exception:
        idx = {}
    sid = hook.get("session_id") or "unknown"
    SKIP = ("<bash-stdout>", "<bash-stderr>", "<local-command-stdout>", "<local-command-caveat>", "<system-reminder>")

    def prompt_of(e):
        """The user's own words for a transcript entry, or None for tool results and echoed command output."""
        if e.get("type") != "user":
            return None
        c = (e.get("message") or {}).get("content")
        if not isinstance(c, str) or not c.strip():
            return None
        t = c.strip()
        if t.startswith(SKIP):
            return None
        if t.startswith("<bash-input>"):
            return "Ran in the shell: " + t.replace("<bash-input>", "").replace("</bash-input>", "").strip()
        if t.startswith("<command-name>"):
            return "Ran the command " + t.split("</command-name>")[0].replace("<command-name>", "").strip()
        return t

    def read():
        out = []
        try:
            for line in open(hook.get("transcript_path") or ""):
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
        except Exception:
            pass
        lu = max([i for i, e in enumerate(out) if prompt_of(e)] or [-1])
        return out, lu

    # The Stop event carries the reply itself (last_assistant_message); the transcript may not hold it yet.
    entries, last_user = read()
    if not hook.get("last_assistant_message"):
        import time
        for _ in range(5):
            if any(e.get("type") == "assistant" for e in entries[last_user + 1:]):
                break
            time.sleep(0.3)
            entries, last_user = read()
    turn = entries[last_user + 1:] if last_user >= 0 else entries
    prompt = prompt_of(entries[last_user]) if last_user >= 0 else ""
    model, text, tools, files, tokens = "unknown", "", [], [], 0
    for e in turn:
        m = e.get("message") or {}
        if e.get("type") != "assistant":
            continue
        model = m.get("model") or model
        u = m.get("usage") or {}
        tokens += sum(u.get(k) or 0 for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        for c in m.get("content") or []:
            if c.get("type") == "text" and c.get("text", "").strip():
                text = c["text"].strip()
            if c.get("type") == "tool_use":
                inp = c.get("input") or {}
                tools.append("%s %s" % (c.get("name"), (inp.get("file_path") or inp.get("command") or inp.get("description") or "")[:80]))
                if c.get("name") in ("Edit", "Write", "NotebookEdit") and inp.get("file_path"):
                    files.append({"name": os.path.basename(inp["file_path"]), "type": "file", "summary": "edited this turn", "path": os.path.relpath(inp["file_path"], root)})
    reply = (hook.get("last_assistant_message") or text or "").strip()
    reply = "\n".join(l for l in reply.splitlines() if l.strip() and not l.startswith("Rules loaded from"))
    focus = (prompt.strip().splitlines() or ["(no prompt text)"])[0][:100] or "(no prompt text)"
    relayed = prompt.lstrip().startswith("Another Claude session sent a message") or "<task-notification>" in prompt
    if relayed:
        focus = ("relayed: " + (prompt.strip().splitlines() or [""])[0])[:100]
    now = datetime.datetime.now(datetime.timezone.utc)
    env = os.environ.get("WHEEL_ENV_ID") or None
    if not env:  # optional: the id the hub's environment refresh left for this machine (W-123)
        try:
            env = open(os.path.join(os.path.expanduser("~"), ".config", "wheel", "environment-id")).read().strip() or None
        except Exception:
            env = None
    rec = idx.get(sid)
    if not rec:
        name = "WAI_Track-%s-Claude-%s.jsonl" % (now.strftime("%Y%m%d-%H%M"), model.replace("/", "-"))
        rec = idx[sid] = {"file": name, "turns": 0}
        start = {"event": "session_start", "ts": now.isoformat(timespec="seconds"), "session_id": sid,
                 "provider": "Claude", "model": model, "mode": "active-collection", "continues": None}
        if env:
            start["env"] = env
        with open(os.path.join(tdir, name), "a") as f:
            f.write(json.dumps(start) + "\n")
    rec["turns"] += 1
    point = {"turn": rec["turns"], "ts": now.isoformat(timespec="seconds"),
             "phase": "execution" if files else ("review" if tools else "orientation"),
             "focus": focus,
             "action": (reply.splitlines() or ["(no reply text)"])[0][:240] or "(no reply text)",
             "thinking": "Recorded by the Stop hook from the session transcript, not written by the agent. The agent's reasoning is not stored in the transcript, so this point records what was asked, what tools ran and what was produced. Read the transcript for the full reasoning.",
             "activity": tools[:20] or ["conversational response"]}
    if relayed:
        point["relayed"] = True
    if files:
        point["files_out"] = files[:20]
    if tokens:
        point["tokens"] = tokens
    with open(os.path.join(tdir, rec["file"]), "a") as f:
        f.write(json.dumps(point) + "\n")
    json.dump(idx, open(idx_p, "w"))
    if not hook.get("stop_hook_active"):
        gold = None
        try:
            with open(os.path.join(tdir, ".turn-start-%s" % sid[:36])) as f:
                since = parse_any(f.read().strip())
            gold = gold_since(root, since) if since else None
        except Exception:
            gold = None
        print(json.dumps({"systemMessage": status_line(rec["turns"], model, hook, root, gold if gold is not None else "unknown",
                                                       cost=footer_cost(root, hook.get("transcript_path"), stop=True, sid=sid))}))


if __name__ == "__main__":
    try:
        prompt_hook() if sys.argv[1:2] == ["prompt"] else main()
    except Exception:
        pass
