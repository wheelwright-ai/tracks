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
