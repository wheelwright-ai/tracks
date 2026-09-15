# live-apply-announce

260828-FBL-024 item 1 / FBL-025. When `applyCut` writes a binding change
(`canon/circles`, `.claude/settings.json`) against a spoke whose profile
opted into live-apply (`autonomy_table_defaults.live_apply_bindings: true`)
while a session is registered active on it, the write proceeds -- but the
active session isn't left to discover the change on its own. `applyCut`
writes a pending-announcement file
(`src/factory/liveApplyAnnounce.js`, `runtime/pending-announcements/<session_id>.json`);
this circle delivers it as `additionalContext` on that session's next real
prompt, then deletes the file. Delivered exactly once.

Default (no live-apply opt-in, or no active session): `applyCut` holds
the write instead and this circle never fires for it -- see
`reference/circles/session-registry.md` and `src/factory/cutUpdate.js`.
