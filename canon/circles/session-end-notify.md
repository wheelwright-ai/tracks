# session-end-notify

**CORRECTED 260901-FBL-062 item 1**, against this circle's own earlier
disposition (260831-FBL-056): "notify means 'the agent needs you,' not
'the session ended.'" The real v1 behavior the operator relied on is
`stop-agent-waiting-notify` and `notification-agent-waiting-notify`
(Stop and Notification) -- see those circles. This one, the SessionEnd
exit toast, is real but is not that behavior: it is now posture-gated,
`autonomy_table_defaults.session_end_toast`, **default off**. A spoke
that wants a courtesy toast on exit anyway opts in explicitly.

Best-effort, always: a failed or unavailable toast transport, or the
posture being off, all fall through to a silent no-op.
