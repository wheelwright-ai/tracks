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
import json, os, re, sys, datetime

sys.dont_write_bytecode = True


def wheel_root(cwd):
    """The project the session works in: the nearest folder at or above cwd that holds .wheel/config.json or
    .wheel/hooks. A session that cds into a subfolder must not grow a stray .wheel/ there (it was then committed
    by the turn save, with absolute paths in it). Falls back to cwd when no wheel is found."""
    d = os.path.abspath(cwd)
    while True:
        if os.path.isfile(os.path.join(d, ".wheel", "config.json")) or os.path.isdir(os.path.join(d, ".wheel", "hooks")):
            return d
        up = os.path.dirname(d)
        if up == d:
            return os.path.abspath(cwd)
        d = up


def model_name(m):
    """claude-opus-5-5 -> Opus 5.5; claude-fable-5-2 -> Fable 5.2; anything unexpected is shown as it is."""
    if not m or m.startswith("<"):
        return None
    parts = [p for p in m.replace("claude-", "", 1).split("-") if not (p.isdigit() and len(p) == 8)]
    name = [p for p in parts if not p.isdigit()]
    ver = [p for p in parts if p.isdigit()]
    return (" ".join(w.capitalize() for w in name) + (" " + ".".join(ver) if ver else "")).strip() or m


def session_record(sid):
    """The status line's live record for this session (~/.local/state/basher/sessions/<sid>.json): Claude Code's own
    model and effort for it, which the hook payloads lack. {} when there is none."""
    try:
        d = json.load(open(os.path.join(os.path.expanduser("~/.local/state/basher/sessions"), os.path.basename(str(sid)) + ".json")))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def routed(sid, max_age=60):
    """B-531: the turn router's decision for this turn (~/.config/wheel/turn-router/current-<sid>.json, written when the
    prompt is submitted): (effort, class), or (None, None) when there is none from the last max_age seconds. The router
    sets each turn's effort from the prompt, over the session's own setting."""
    try:
        p = os.path.join(os.path.expanduser("~/.config/wheel/turn-router"), "current-%s.json" % re.sub(r"[^A-Za-z0-9_-]", "_", str(sid)))
        d = json.load(open(p))
        t = datetime.datetime.fromisoformat(str(d.get("time")).replace("Z", "+00:00")).timestamp()
        if datetime.datetime.now().timestamp() - t <= max_age and d.get("effort"):
            return d["effort"], d.get("class")
    except Exception:
        pass
    return None, None


def effort_letter(hook, root):
    """B-531: the router's effort for this turn first, then Claude Code's live effort for this session (the status line's
    record); the owner saw H in the footer while the status line said M, because the hook payload has no effort and the
    settings file's default won."""
    e = hook.get("effort") or routed(hook.get("session_id") or "")[0] or session_record(hook.get("session_id") or "").get("effort")
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


def worktree_id(root):
    """The six hex characters of a wheel worktree branch (wheel/<date>-<hex6>[-B-n]), as the status line shows them, or
    None."""
    try:
        import subprocess
        b = subprocess.run(["git", "-C", root, "branch", "--show-current"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return None
    m = re.match(r"^wheel/.*-([0-9a-f]{6})(-B-[0-9]+)?$", b)
    return (m.group(1) + (m.group(2) or "")) if m else None


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
#   - the Claude plan's pace advice (basher's pace_advice.py), never a raw limit percentage (the owner, 2026-11-22).
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
    """(5-hour percent used, its reset, week percent used, its reset) from the status line's usage.json, or None when
    missing or stale."""
    import time
    try:
        d = json.load(open(path or USAGE))
        at = parse_any(d.get("written_at"))
        if not at or time.time() - at.timestamp() > USAGE_FRESH_S:
            return None
        f, w = d.get("five_hour") or {}, d.get("seven_day") or {}
        if f.get("used_pct") is None:
            return None
        return (int(f["used_pct"]), f.get("resets_at"), int(w.get("used_pct") or 0), w.get("resets_at"))
    except Exception:
        return None


PACE_ADVICE = os.path.join(os.path.expanduser("~"), ".claude", "pace_advice.py")   # basher installs it beside the status line


def plan_advice(u, path=None, model=""):
    """The Claude plan's pace advice for usage u (five_pct, five_ts, week_pct, week_ts): one short sentence from basher's
    pace_advice.py, or "" when either is missing. Advice, not readings (the owner, 2026-11-22: "11% into our 5hr limit
    ... isn't as useful as just knowing the advice on pacing")."""
    if not u:
        return ""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("wheel_pace_advice", path or PACE_ADVICE)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        args = (int(u[0] or 0), int(u[1] or 0), int(u[2] or 0), int(u[3] or 0))
        try:   # B-310: the model lets it name a gifted Fable reset at the cap; an older pace_advice.py takes no model
            return m.advise(*args, model=model or "") or ""
        except TypeError:
            return m.advise(*args) or ""
    except Exception:
        return ""


def gauge(label, weight, normal, ctx, fresh, plan=""):
    """Context first, then the Claude plan's pacing, as separate sentences, ASCII, no pipes (the owner, 2026-11-22:
    "Separate Context from Budget"; no raw limit percentages):
    'Context heavy, restart at the next stop: 3.2x a fresh start; last turn 2.6x a normal turn. Claude plan: Week on track: 3d 4h until reset.'
    The plan sentence covers the Claude subscription only (spend order tier 3), so it is labelled that way."""
    if not ctx:
        return ""
    r = ctx / float(fresh or FRESH_DEFAULT)
    verdict = ("Context too heavy, restart now" if r >= TOO_HEAVY else
               "Context heavy, restart at the next stop" if r >= HEAVY else "Context light")
    out = "%s: %.1fx a fresh start" % (verdict, r)
    if weight and normal:
        out += "; %s %.1fx a normal turn" % (label, weight / normal)
    out += "."
    if plan:
        out += " Claude plan: %s" % plan
    return out


def footer_cost(root, transcript, stop, sid="unknown"):
    """The gauge for the footer. At the prompt the turn about to run has not happened, so it weighs the last finished
    turn; at Stop, the turn that just ended. Never raises."""
    try:
        weights, _, ctx = read_turns(transcript)
        if not stop and weights and weights[-1] == 0:
            weights = weights[:-1]   # this prompt is already written but nothing has run for it
        b = baseline(root, transcript)
        return gauge("this turn" if stop else "last turn", weights[-1] if weights else 0, b.get("normal"), ctx,
                     b.get("fresh"), plan_advice(usage_now(), model=last_model(transcript) or ""))
    except Exception:
        return ""


def _turns_cached(root, transcript):
    """(weights, last call's context) for the live gauge, cached by the transcript's size and modified time in
    .wheel/tracks/.gauge-turns.json so a status line refresh re-reads the transcript only after it grew. Never creates
    .wheel/tracks: a project without one is read every time."""
    if not isinstance(transcript, str):
        return [], 0
    try:
        st = os.stat(transcript)
    except Exception:
        return [], 0
    key = [transcript, st.st_size, int(st.st_mtime)]
    path = os.path.join(root, ".wheel", "tracks", ".gauge-turns.json")
    try:
        c = json.load(open(path))
        if c.get("key") == key:
            return c["weights"], c["ctx"]
    except Exception:
        pass
    weights, _, ctx = read_turns(transcript)
    weights = weights[-2:]   # the gauge needs the last finished turn only
    if os.path.isdir(os.path.dirname(path)):
        try:
            tmp = path + ".tmp%d" % os.getpid()
            with open(tmp, "w") as f:
                json.dump({"key": key, "weights": weights, "ctx": ctx}, f)
            os.replace(tmp, path)
        except Exception:
            pass
    return weights, ctx


def gauge_parts(weight, normal, ctx, fresh, plan=""):
    """B-531: gauge()'s numbers as indicators for the status line's second line (the owner, 2026-11-24: "it can run off
    the page can it be expressed with indicators not narratives?"): the context as a multiple of a fresh start and its
    level (light, heavy: restart at the next stop, too_heavy: restart now), the last turn as a multiple of a normal turn
    (None when unknown) and the Claude plan advice sentence, which the status line shortens. {} when there is no context."""
    if not ctx:
        return {}
    r = ctx / float(fresh or FRESH_DEFAULT)
    return {"ctx": float("%.1f" % r), "level": "too_heavy" if r >= TOO_HEAVY else "heavy" if r >= HEAVY else "light",
            "turn": float("%.1f" % (weight / normal)) if weight and normal else None, "plan": plan or ""}


def _live_inputs(status, root, usage_path=None):
    """(weight, normal, ctx, fresh, plan) for the live gauge, from the status line's JSON (transcript_path, session_id,
    rate_limits). The numbers are the footer's: the last finished turn's weight against this project's normal turn and
    the context against a fresh start, both from the transcript and the footer's own baseline cache; the Claude plan pace
    advice from the limits Claude Code reports live (else usage.json). May raise."""
    tr = status.get("transcript_path")
    weights, ctx = _turns_cached(root, tr) if tr else ([], 0)
    if weights and weights[-1] == 0:
        weights = weights[:-1]   # a prompt is written but nothing has run for it yet
    if not ctx:
        ctx = context_of((status.get("context_window") or {}).get("current_usage"))
    try:   # the footer refreshes this once a day; the status line only reads it unless it is missing
        b = json.load(open(os.path.join(root, ".wheel", "tracks", ".cost-target.json")))
        if b.get("prices") != PRICES_SET or "fresh" not in b:
            raise ValueError
    except Exception:
        b = baseline(root, tr)
    rl = status.get("rate_limits") or {}
    f, w = rl.get("five_hour") or {}, rl.get("seven_day") or {}
    if isinstance(f.get("used_percentage"), (int, float)):
        u = (int(f["used_percentage"]), f.get("resets_at"), int(w.get("used_percentage") or 0), w.get("resets_at"))
    else:
        u = usage_now(usage_path)
    return (weights[-1] if weights else 0, b.get("normal"), ctx, b.get("fresh"),
            plan_advice(u, model=str((status.get("model") or {}).get("id") or "")))


def live_gauge(status, root, usage_path=None):
    """B-293: the same gauge() sentence the track footer prints, from the status line's JSON. Never raises; empty when
    there is nothing to gauge."""
    try:
        return gauge("last turn", *_live_inputs(status, root, usage_path))
    except Exception:
        return ""


def live_parts(status, root, usage_path=None):
    """B-531: the live gauge as gauge_parts() for the status line's indicators. Never raises; {} when nothing to gauge."""
    try:
        return gauge_parts(*_live_inputs(status, root, usage_path))
    except Exception:
        return {}


def gauge_cli(argv):
    """`track_write.py gauge ROOT [--json]` with the status line's JSON on stdin: prints the live gauge sentence, or with
    --json the gauge_parts() indicators as one JSON object ({} when nothing to gauge); nothing on bad input."""
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    try:
        status = json.load(sys.stdin)
    except Exception:
        return
    root = (argv[0] if argv else None) or status.get("cwd") or os.getcwd()
    print(json.dumps(live_parts(status, root)) if as_json else live_gauge(status, root))


def route_note(hook):
    """' (routed: normal)' when the turn router set this turn's effort (the owner, 2026-11-24: the router's call belongs
    in the track turn, not the Claude status line), else ''."""
    _, cls = routed(hook.get("session_id") or "")
    return " (routed: %s)" % cls if cls else ""


def status_line(turn, model, hook, root, gold=None, cost=""):
    """The turn footer the owner reads every turn, in the track prompt's harness shape (track-prompt-lab v4.0.0,
    turn_footer.cc.harness_format), ASCII pipes only:
    s{session} | Turn {n} | {day}, {month} {d}, {year} | {time} {tz} | {model effort} | {commit} | kit v{N} | Gold: +{count}
    A value the harness does not have is the word unknown, never a guess. gold=None leaves {gold} for the model."""
    now = datetime.datetime.now().astimezone()
    # B-531 (the owner, 2026-11-24: "session id is wrong"): the session is named by the same id the status line shows,
    # the worktree's six hex characters; a session with no worktree id keeps its number among the project's sessions.
    wid = worktree_id(root)
    sn = None if wid else session_number_cached(root, hook.get("transcript_path"))
    m = model_name(model)
    letter = effort_letter(hook, root) if m else ""
    kv = kit_version(root)
    bits = [wid or "s%s" % (sn if sn else "unknown"), "Turn %d" % turn, now.strftime("%a, %b %-d, %Y"), now.strftime("%-I:%M %p %Z"),
            (m + (" " + letter if letter else "") + route_note(hook)) if m else "unknown", head_sha(root) or "unknown",
            "kit v%s" % kv if kv else "kit unknown"] + ([cost] if cost else []) + \
           ["Gold: +%s" % ("{gold}" if gold is None else gold)]
    return " | ".join(bits)


def recorded_model(sid):
    """B-531: the model the status line last saw for this session, so the first turn's footer names it before the
    transcript holds an assistant message. None when there is no record."""
    m = session_record(sid).get("model")
    return m if isinstance(m, str) else None


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
    root = wheel_root(hook.get("cwd") or os.getcwd())
    try:
        idx = json.load(open(os.path.join(root, ".wheel", "tracks", ".index.json")))
    except Exception:
        idx = {}
    sid = hook.get("session_id") or "unknown"
    turn = int((idx.get(sid) or {}).get("turns") or 0) + 1
    model = hook.get("model") if isinstance(hook.get("model"), str) else None
    line = status_line(turn, model or last_model(hook.get("transcript_path")) or recorded_model(sid), hook, root,
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
    root = wheel_root(hook.get("cwd") or os.getcwd())
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
                tools.append("%s %s" % (c.get("name"), inp.get("file_path") or inp.get("command") or inp.get("description") or inp.get("prompt") or inp.get("query") or ""))
                if c.get("name") in ("Edit", "Write", "NotebookEdit") and inp.get("file_path"):
                    files.append({"name": os.path.basename(inp["file_path"]), "type": "file", "summary": "edited this turn", "path": os.path.relpath(inp["file_path"], root)})
    reply = (hook.get("last_assistant_message") or text or "").strip()
    reply = "\n".join(l for l in reply.splitlines() if l.strip() and not l.startswith("Rules loaded from"))
    # Nothing is clipped (the owner, 2026-11-22: "Do not clip entries, we want and need the entirety"): the track is for
    # rewarming, and a cut prompt, reply or command loses exactly what a later session needs.
    focus = (prompt.strip().splitlines() or ["(no prompt text)"])[0] or "(no prompt text)"
    relayed = prompt.lstrip().startswith("Another Claude session sent a message") or "<task-notification>" in prompt
    if relayed:
        focus = "relayed: " + (prompt.strip().splitlines() or [""])[0]
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
             "prompt": prompt.strip() or "(no prompt text)",
             "action": reply or "(no reply text)",
             "thinking": "Recorded by the Stop hook from the session transcript, not written by the agent. The agent's reasoning is not stored in the transcript, so this point records what was asked, what tools ran and what was produced. Read the transcript for the full reasoning.",
             "activity": tools or ["conversational response"]}
    if relayed:
        point["relayed"] = True
    if files:
        point["files_out"] = files
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
        cost = footer_cost(root, hook.get("transcript_path"), stop=True, sid=sid)
        try:   # the status bar shows the same gauge without reading transcripts every refresh (the owner, 2026-11-22)
            with open(os.path.join(tdir, ".gauge-%s" % sid[:36]), "w") as f:
                f.write(cost.split(" Claude plan:")[0].strip() if cost else "")
        except Exception:
            pass
        print(json.dumps({"systemMessage": status_line(rec["turns"], model, hook, root, gold if gold is not None else "unknown",
                                                       cost=cost)}))


if __name__ == "__main__":
    try:
        if sys.argv[1:2] == ["gauge"]:
            gauge_cli(sys.argv[2:])
        elif sys.argv[1:2] == ["prompt"]:
            prompt_hook()
        else:
            main()
    except Exception:
        pass
