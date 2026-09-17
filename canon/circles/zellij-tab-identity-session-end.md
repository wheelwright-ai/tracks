# zellij-tab-identity-session-end

lug zellij-tab-identity-and-gated-toast-are-a-fleet-circle (2026-09-16).
On `SessionEnd` the tab goes back to the idle box `□ <name><-n>` and the
pane title to `□ <long name>` -- basher v1's `tab-clear.sh`.

The one rule that matters: a tab still showing an attention glyph
(`✅` `🔴` `⛔` `🔵`) has not been looked at yet, and a session that
exits under it (a `/exit` typed blind, a crash, a headless close) must
not erase the cue. `applyTabState` reads the current tab name and
refuses to paint over one of those; it reports the skip in the hook
capture. A lens-sentinel tab is never renamed.
