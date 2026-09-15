# hook-binding-drift

260830-FBL-041-answers, Q3 (behavior harvest, LOST register): v1's real
"Hook Self-Heal" (`mywheel session-start.sh:225-261`) re-asserted
declared hooks into the live `settings.json` when a non-additive writer
displaced one -- a fix for a real v1 incident ("this is exactly how
notify-reset.sh got dropped off UserPromptSubmit"). v2's
`compileSelf.js`/`generate.js` write `settings.json` but never checked
it afterward: any later writer that overwrites `.claude/settings.json`
wholesale, not additively, could silently drop a real hook binding with
no signal until whatever depended on it just stopped firing. Found live,
exactly this way, before this circle existed: a session's own isolated
`CLAUDE_CONFIG_DIR/settings.json` was missing a real, declared hook
binding, discovered only by manually checking.

## What it is, honestly

Detection, not repair -- the same "detect, never silently auto-repair"
discipline `session-upkeep-manifest.policy.yaml` already established for
a different asset class. v1 actually rewrote `settings.json` live; this
circle's deliberately narrower scope is naming the drift so a session
can decide what to do about it (relaunch, recompile-self, or a real,
separately-reviewed repair lug), never silently patching the file
itself.

At every real `SessionStart`, it reads every live, `hook_event` circle
this instance's own canon declares (`canon/circles/*.yaml` for an
adopted spoke, `reference/circles/*.yaml` for this framework's own
self-hosted set -- `loadCanon` doesn't care which, so one function
covers both) and the real `.claude/settings.json` on disk, and reports
any declared circle with no matching real binding -- named by circle and
event, never just a count. The expected shape is generated with the SAME
`generateHookBinding` function `compileSelf.js` itself uses to write
`settings.json`, so "what canon declares" and "what a fresh compile
would produce" can never silently diverge into two different
definitions of "expected."

A finding is never silent: one real, named ledger row per missing
circle+event (`row_kind: "hook-binding-drift"`), and the same finding
surfaced in the session's own `additionalContext` at wakeup.

## Known, accepted gaps

This finds a MISSING binding, not a WRONG one carrying a stale script
path or matcher that happens to still be present -- the match is exact
(matcher + full command string), so a real drift that happens to collide
with an unrelated, coincidentally-identical binding would not be caught
by this alone. It also only ever runs at `SessionStart` -- a binding
dropped mid-session by a writer other than this session's own compile-
self call is not caught until the NEXT session's own wakeup, same
timing gap every other SessionStart-only check in this build already
accepts.
