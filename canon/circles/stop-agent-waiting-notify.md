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
