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


def status_line(turn, model, hook, root):
    """The one line shown to the owner at the end of the turn."""
    bits = ["Track turn %d" % turn]
    m = model_name(model)
    if m:
        letter = effort_letter(hook, root)
        bits.append(m + (" " + letter if letter else ""))
    bits.append(datetime.datetime.now().astimezone().strftime("%-I:%M %p %Z"))
    return " \u00b7 ".join(bits)


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
    turn = int((idx.get(hook.get("session_id") or "unknown") or {}).get("turns") or 0) + 1
    model = hook.get("model") if isinstance(hook.get("model"), str) else None
    line = status_line(turn, model or last_model(hook.get("transcript_path")), hook, root)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext":
        "Track line for this turn (the owner reads it every turn): end your final message with this line, alone, in backticks: `%s`" % line}}))


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
        print(json.dumps({"systemMessage": status_line(rec["turns"], model, hook, root)}))


if __name__ == "__main__":
    try:
        prompt_hook() if sys.argv[1:2] == ["prompt"] else main()
    except Exception:
        pass
