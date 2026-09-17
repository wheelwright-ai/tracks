# zellij-tab-identity-turn-start

lug zellij-tab-identity-and-gated-toast-are-a-fleet-circle (2026-09-16).
The zellij tab is the operator's at-a-glance state for every live
session: one glyph, the spoke's short name, and a `-n` ordinal when
several tabs share a folder. basher v1 wrote it from four bash hooks
registered in `~/.claude/settings.json` -- a file no `wcl` session reads,
because `wcl` points `CLAUDE_CONFIG_DIR` at the spoke's own cut-generated
config. Measured on basher: no tab renamed since the cut arrived
2026-09-14 23:33. The writer is now `src/basher/zellijTabIdentity.js`,
node only (no jq, no dotfiles), and every spoke gets it with the cut.

This circle is the turn-start half. On every `UserPromptSubmit` it:

- resolves the pane (`ZELLIJ_PANE_ID`, else the pane<->transcript map --
  hook subprocesses have been seen dropping the variable);
- writes `/tmp/claude-sessions/pane-transcript-<pane>` (the map) and
  `last-interaction-<pane>` (the toast gate's input: "the operator just
  typed"), and clears any `pending-question-<pane>.json` from the
  previous turn;
- sets the tab to `⏳ <name><-n>` and the pane title to `⏳ <long name>`.

Glyphs across the family: `⏳` working (this circle, and
`zellij-tab-identity-tool-reset`), `✅` done and `🔵` pending question
(`stop-agent-waiting-notify`), `🔴` permission prompt
(`notification-agent-waiting-notify`), `⛔` failure, `□` idle
(`zellij-tab-identity-session-end`). Label width is budgeted from the
terminal width the idle shell publishes (`~/.cache/basher/term-cols`, else
80) divided by the tab count, clamped to 8, so a full bar never overflows.
A tab carrying a lens sentinel (`« LENS »`, `<<LENS>>`) is never renamed.
