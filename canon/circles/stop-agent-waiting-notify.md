# stop-agent-waiting-notify

260901-FBL-062 item 1, correcting 260831-FBL-056's own earlier
disposition: "notify means 'the agent needs you,' not 'the session
ended.'" The real v1 behavior the operator relied on. Fires on every
real `Stop` (a turn completing), sends a real desktop toast naming the
spoke and callsign with one line of what it's waiting for. Headless
sub-sessions (Proofer, a headless `wcl` launch) never notify.
Per-spoke posture: `autonomy_table_defaults.agent_waiting_notify`,
default `true`. See `src/basher/agentWaitingNotify.js` for the shared
logic this and `notification-agent-waiting-notify` both use.

## Tab first, then the gated toast (lug zellij-tab-identity-and-gated-toast-are-a-fleet-circle, 2026-09-16)

Before the toast, the hook sets this session's zellij tab through
`src/basher/zellijTabIdentity.js`: `✅ <name><-n>` for a finished turn, or
`🔵 <name><-n>` when an AskUserQuestion sidecar
(`/tmp/claude-sessions/pending-question-<pane>.json`) is waiting. The tab
is the cue the operator sees when the toast is rightly suppressed.

The toast now carries basher v1's gate. `notifyAgentWaiting` reads the
age of `last-interaction-<pane>` (written on every prompt by
`zellij-tab-identity-turn-start`): an ordinary Stop within 300 s of the
operator's last prompt is a quick turn (they are still there) and sends
nothing; any toast within 60 s of a keystroke is a focus-steal for a
result already on screen and sends nothing (`BASHER_TOAST_ALWAYS=1`
disables the presence gate). A pending question always passes the
quick-turn gate.

## One short line, at most once per turn (lug toast-is-one-short-line-per-turn, 2026-09-16)

Measured on basher: every turn produced two toasts (Stop, then Claude
Code's `idle_prompt` 60 s later with a looping alarm) and the body was
300 characters of the answer. Now: title `<glyph> <spoke> · <callsign><-n>`;
body a fixed line per reason -- `Done -- waiting for you`,
`Needs permission: <Claude Code's message>`, `Question: <text>`,
`Turn failed -- check the session` (120 chars max, never an excerpt).
Sounds: `Default` for a finished turn or failure, `Reminder` when a human
answer is needed; no `Looping.*` source anywhere. An `idle_prompt` never
toasts on its own (the tab still updates). A sent Stop toast stamps
`last-toast-<pane>`; a second ordinary toast inside the 300 s window is
dropped as a duplicate even when no interaction stamp exists. Permission
and question toasts are never deduplicated. AppId `Claude Code`.

Transport: `src/basher/assets/toast.ps1` launched with `-File`, detached
-- the inline `-Command` form hit the hook's 10 s timeout four times on
2026-09-16 and held the Stop path each time. `ok: true` now means the
launch was handed to the OS.
