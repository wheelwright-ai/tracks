#!/usr/bin/env bash
# Turn status line. Reads Claude Code's status JSON on stdin.
# When the hub's informative status line is installed (~/.claude/statusline.sh, owned by the hub and put there by
# `basher sync`), run that: it shows the model, project, branch, lugs, overwatch, cost, context and the usage limits,
# and it keeps the usage cache fresh itself. Otherwise fall back to the one plain line below (model, project,
# uncommitted files, last smoke result, track turns, latest checkpoint age), which also keeps the usage cache fresh.
in=$(cat)
if [ -x "$HOME/.claude/statusline.sh" ]; then printf '%s' "$in" | "$HOME/.claude/statusline.sh"; exit $?; fi
model=$(printf '%s' "$in" | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("model") or {}).get("display_name") or "model?")' 2>/dev/null)
cost=$(printf '%s' "$in" | python3 -c 'import json,sys;d=json.load(sys.stdin);c=(d.get("cost") or {}).get("total_cost_usd");print("$%.2f"%c if c is not None else "")' 2>/dev/null)
root=$(printf '%s' "$in" | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("workspace") or {}).get("project_dir") or d.get("cwd") or ".")' 2>/dev/null)
# Usage for the conductor: when Claude Code passes the 5-hour and 7-day figures, keep the latest in
# ~/.local/state/basher/usage.json (read by the hub's tools/conductor.py, stale after 10 minutes). Best effort, silent.
printf '%s' "$in" | python3 -c '
import json, os, sys, tempfile, time
r = json.load(sys.stdin).get("rate_limits") or {}
def w(k):
    x = r.get(k) or {}
    return {"used_pct": x["used_percentage"], "resets_at": x.get("resets_at")} if isinstance(x.get("used_percentage"), (int, float)) else None
f, s = w("five_hour"), w("seven_day")
if f or s:
    d = os.path.expanduser("~/.local/state/basher"); os.makedirs(d, exist_ok=True)
    fd, t = tempfile.mkstemp(dir=d, prefix=".usage-")
    os.write(fd, json.dumps({"written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "statusline", "five_hour": f, "seven_day": s}).encode())
    os.close(fd); os.replace(t, os.path.join(d, "usage.json"))
' 2>/dev/null
cd "${root:-.}" 2>/dev/null || true
dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
smoke=$(cat .wheel/last-smoke.txt 2>/dev/null | tail -1)
turns=$(cat .wheel/tracks/*.jsonl 2>/dev/null | grep -c '"turn"')
cp=$(ls -t .wheel/checkpoints/*.json 2>/dev/null | head -1)
age=""; [ -n "$cp" ] && age=" · checkpoint $(( ($(date +%s) - $(stat -c %Y "$cp")) / 60 ))m ago"
printf '%s · %s · %s uncommitted · smoke %s · track %s turns%s %s\n' "$model" "$(basename "$PWD")" "$dirty" "${smoke:-not run}" "$turns" "$age" "$cost"
