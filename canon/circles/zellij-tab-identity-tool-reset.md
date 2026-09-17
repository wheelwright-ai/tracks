# zellij-tab-identity-tool-reset

lug zellij-tab-identity-and-gated-toast-are-a-fleet-circle (2026-09-16).
A permission prompt paints the tab `🔴` and leaves
`/tmp/claude-sessions/tab-needs-reset-<pane>` (written by
`notification-agent-waiting-notify`). The operator answers in the pane,
Claude's next tool call fires this `PreToolUse` hook, which consumes the
flag and paints the tab back to `⏳` -- basher v1's
`pre-tool-tab-reset.sh`.

It binds to every tool call (matcher `""`), so the common path is one
`stat` of the flag and `exit 0` with nothing on stdout: a PreToolUse
hook that prints on allow is a hook error on every tool call. Only a
present flag reaches zellij. Headless sub-sessions never rename.
