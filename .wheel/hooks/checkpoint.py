#!/usr/bin/env python3
"""Compaction succession protection.

  checkpoint.py precompact     PreCompact hook: write .wheel/checkpoints/<time>.json before the context is compacted
  checkpoint.py sessionstart   SessionStart hook: after a compaction or resume, hand the latest checkpoint back to the agent

A checkpoint holds what a successor needs to carry on: the last few things the user asked, the files touched
recently, uncommitted work, and (in a wheel) the open cut and its last tick. Never blocks a compaction."""
import json, os, subprocess, sys, datetime, glob

sys.dont_write_bytecode = True


def git(root, *a):
    try:
        return subprocess.run(["git", "-C", root] + list(a), capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def precompact(hook, root):
    prompts, files = [], []
    try:
        for line in open(hook.get("transcript_path") or ""):
            try:
                e = json.loads(line)
            except Exception:
                continue
            m = e.get("message") or {}
            if e.get("type") == "user" and isinstance(m.get("content"), str) and m["content"].strip():
                prompts.append(m["content"].strip()[:300])
            if e.get("type") == "assistant":
                for c in m.get("content") or []:
                    if c.get("type") == "tool_use" and c.get("name") in ("Edit", "Write") and (c.get("input") or {}).get("file_path"):
                        files.append(os.path.relpath(c["input"]["file_path"], root))
    except Exception:
        pass
    cp = {"at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "session_id": hook.get("session_id"),
          "trigger": hook.get("trigger"), "last_asks": prompts[-5:], "files_touched": list(dict.fromkeys(reversed(files)))[:15],
          "uncommitted": git(root, "status", "--porcelain").splitlines()[:20], "last_commit": git(root, "log", "-1", "--format=%h %s")}
    led = os.path.join(root, "ledger.jsonl")
    if os.path.exists(led):
        rows = [json.loads(x) for x in open(led) if x.strip()]
        cuts = [r for r in rows if r.get("kind") == "cut"]
        ticks = [r for r in rows if r.get("step")]
        cp["wheel"] = {"last_cut_row": cuts[-1] if cuts else None, "last_tick": {k: ticks[-1].get(k) for k in ("id", "step", "kind")} if ticks else None}
    d = os.path.join(root, ".wheel", "checkpoints")
    os.makedirs(d, exist_ok=True)
    json.dump(cp, open(os.path.join(d, cp["at"].replace(":", "") + ".json"), "w"), indent=1)


def inbox_lines(root):
    """Message lugs waiting in this project's inbox (kit part P-022), [] when none or msg.py is not installed."""
    try:
        import importlib.util
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "msg.py")
        if not os.path.exists(p):
            return []
        spec = importlib.util.spec_from_file_location("wheel_msg_ss", p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m.unread_lines(root)
    except Exception:  # noqa: BLE001  (a session start never fails on the inbox)
        return []


def sessionstart(hook, root):
    inbox = inbox_lines(root)
    files = sorted(glob.glob(os.path.join(root, ".wheel", "checkpoints", "*.json"))) if hook.get("source") in ("compact", "resume") else []
    if not files:
        if inbox:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(inbox)}}))
        return
    cp = json.load(open(files[-1]))
    lines = inbox + ["Checkpoint from before the last compaction (%s):" % cp.get("at")]
    if cp.get("wheel"):
        c = (cp["wheel"].get("last_cut_row") or {})
        lines.append("Cut %s, phase %s; last tick: %s." % (c.get("cut"), c.get("phase"), cp["wheel"].get("last_tick")))
    lines.append("The user's last asks, oldest first: " + " | ".join(cp.get("last_asks") or ["none recorded"]))
    lines.append("Files touched: " + (", ".join(cp.get("files_touched") or []) or "none"))
    lines.append("Uncommitted: %d files. Last commit: %s." % (len(cp.get("uncommitted") or []), cp.get("last_commit")))
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}}))


if __name__ == "__main__":
    try:
        hook = json.load(sys.stdin)
        root = hook.get("cwd") or os.getcwd()
        {"precompact": precompact, "sessionstart": sessionstart}[sys.argv[1]](hook, root)
    except Exception:
        pass
