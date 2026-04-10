# WAI Wakeup Protocol

Execute wakeup to initialize the spoke.

---

## Check: Is Session Data Fresh?

Look for `<wai-session-init>` in context and check if it contains `Wakeup brief: FRESH`.

---

## FAST PATH — 0 tool calls (FRESH brief)

Pre-conditions met: hook pre-computed all data, track entry already written by session-start.sh.

**DO NOT make any tool calls.** Display the briefing immediately.

**Steps:**

**1. Interrupted session check.** If `Prev session: INTERRUPTED` in session-init CONTEXT HEALTH:
- Surface in briefing: `⚠ INTERRUPTED — [G]reen Light / [R]ed Light / [S]kip / [N]ew Project`

**2. Display banner** using session-init sections:

```
┌─ WAI WAKEUP Session-{N} [{session_name}] {today_date}
│  Project: {name} v{version}               ← STATIC DATA
│  Active: {epics_open} open, {epics_ip} ip | {other_open} other | {signals} signals
│  Queue: {ready} ready | {refinement} refinement     ← Expediter line
│  Vibe: none  |  Context: unknown — run /context
│  {If TEACHINGS New > 0: Teachings: N pending (Path A/B)}
│  {If HUB SIGNALS > 0: Hub signals: N framework}
│  {If TOOL ADVISOR audit due: ⚠ Tool audit due}
│  {If context feeds stale: Context feeds: N stale}
│  {If HISTORIAN ADVICE present: Historian: {first bullet}}
│  Next: {first item from NEXT ACTIONS}
└─ Ready to work.
```

**3. Ask:** `Vibe? (build / fix / think / grind / ship / refine) [skip]`

Done. Zero tool calls.

---

## FULL PROTOCOL (STALE brief or no session-init)

Use `Read` to load `templates/commands/wai-full.md`, then execute all steps in that document.

---

*Fast path: 0 tool calls, ~15s. Full protocol in wai-full.md (loaded on demand).*
