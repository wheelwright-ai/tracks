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


def status_line(turn, model, hook, root, gold=None):
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
            "kit v%s" % kv if kv else "kit unknown", "Gold: +%s" % ("{gold}" if gold is None else gold)]
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
    line = status_line(turn, model or last_model(hook.get("transcript_path")), hook, root)
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
        print(json.dumps({"systemMessage": status_line(rec["turns"], model, hook, root, gold if gold is not None else "unknown")}))


if __name__ == "__main__":
    try:
        prompt_hook() if sys.argv[1:2] == ["prompt"] else main()
    except Exception:
        pass
