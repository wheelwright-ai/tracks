# notification-agent-waiting-notify

260901-FBL-062 item 1. Fires on Claude Code's own real `Notification`
event, matcher `permission_prompt|idle_prompt` (confirmed against the
real, current docs at code.claude.com/docs/en/hooks: `permission_prompt`
fires on a real permission prompt, `idle_prompt` when Claude has been
idle waiting for input -- the two `notification_type` values that
genuinely mean "the agent needs you," unlike `auth_success` or the
`elicitation_*`/`quota_*` types this circle does not match). Sends a
real desktop toast using the notification's own real `message` field as
the one line of what it's waiting for. Same shared logic, same posture,
same headless exemption as `stop-agent-waiting-notify` --
`src/basher/agentWaitingNotify.js`.

## Tab first, then the gated toast (lug zellij-tab-identity-and-gated-toast-are-a-fleet-circle, 2026-09-16)

A `permission_prompt` paints the tab `🔴 <name><-n>` and writes
`/tmp/claude-sessions/tab-needs-reset-<pane>`, which
`zellij-tab-identity-tool-reset` consumes on the first tool call after
the operator answers (back to `⏳`). An `idle_prompt` paints `✅` (or `🔵`
with a pending question). The toast then goes through the same gate as
`stop-agent-waiting-notify`: a permission prompt always passes the
quick-turn gate (the session is blocked on a human) but still honours
the 60 s presence gate; body `Needs permission: <message>`, sound
`Reminder`. A bare `idle_prompt` never toasts -- the Stop toast already
said "done" and the tab glyph is the cue (lug
toast-is-one-short-line-per-turn, 2026-09-16); it toasts only when a
pending question or permission prompt makes it more than idle.
