#!/usr/bin/env bash
# Turn status line: one plain line the user sees every turn. Reads Claude Code's status JSON on stdin.
# Shows the model, the project, uncommitted files, the last smoke result, track turns and the latest checkpoint age.
in=$(cat)
model=$(printf '%s' "$in" | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("model") or {}).get("display_name") or "model?")' 2>/dev/null)
cost=$(printf '%s' "$in" | python3 -c 'import json,sys;d=json.load(sys.stdin);c=(d.get("cost") or {}).get("total_cost_usd");print("$%.2f"%c if c is not None else "")' 2>/dev/null)
root=$(printf '%s' "$in" | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("workspace") or {}).get("project_dir") or d.get("cwd") or ".")' 2>/dev/null)
cd "${root:-.}" 2>/dev/null || true
dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
smoke=$(cat .wheel/last-smoke.txt 2>/dev/null | tail -1)
turns=$(cat .wheel/tracks/*.jsonl 2>/dev/null | grep -c '"turn"')
cp=$(ls -t .wheel/checkpoints/*.json 2>/dev/null | head -1)
age=""; [ -n "$cp" ] && age=" · checkpoint $(( ($(date +%s) - $(stat -c %Y "$cp")) / 60 ))m ago"
printf '%s · %s · %s uncommitted · smoke %s · track %s turns%s %s\n' "$model" "$(basename "$PWD")" "$dirty" "${smoke:-not run}" "$turns" "$age" "$cost"
