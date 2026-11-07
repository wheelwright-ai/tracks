#!/usr/bin/env python3
"""Stop hook: every turn leaves one point in a portable Track file (the tracks project's format).

Reads the hook's JSON on stdin (session_id, transcript_path), reads this turn from the transcript, and appends one
point to .wheel/tracks/WAI_Track-<date>-<time>-Claude-<model>.jsonl (a session_start line first). Tokens are
summed from the transcript's usage, or left out when unreadable: never a guessed number. Never blocks the turn."""
import json, os, sys, datetime

sys.dont_write_bytecode = True


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
    rec = idx.get(sid)
    if not rec:
        name = "WAI_Track-%s-Claude-%s.jsonl" % (now.strftime("%Y%m%d-%H%M"), model.replace("/", "-"))
        rec = idx[sid] = {"file": name, "turns": 0}
        with open(os.path.join(tdir, name), "a") as f:
            f.write(json.dumps({"event": "session_start", "ts": now.isoformat(timespec="seconds"), "session_id": sid,
                                "provider": "Claude", "model": model, "mode": "active-collection", "continues": None}) + "\n")
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


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
