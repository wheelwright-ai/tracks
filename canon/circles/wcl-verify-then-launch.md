# wcl-verify-then-launch

260831-FBL-056: "the operator was just told to relaunch with two exported
lines and `command claude`. That is the reviewer papering over a gap:
basher v2's `wcl` verb already composes the environment... but it is not
installed as the operator's shell command." This circle is that
installation: one real, installed executable (`bin/wcl`, symlinked to
`~/.local/bin/wcl`) that composes the environment, verifies before it
launches, and hands the operator a tracked, custody-clean, correctly-
modeled interactive session -- nobody has to know what
`CLAUDE_CONFIG_DIR` is.

## What it is, honestly

Six real, sequential checks, each one line of output, a named fix on any
refusal: sync-on-wake (git fetch, fast-forward-only pull when behind,
refuse on a dirty tree rather than force anything), the stale-instance
check (a self-hosting spoke -- one with its own `src/cli.js` -- checks
itself the same way `conformance:circles` does, a real compile of its
own canon; an adopted spoke uses the real recompile-and-diff check,
`checkSpokeDrift`), pending-cut application per the spoke's own declared
posture (never a hard launch-blocker -- a held cut is reported, not
refused), the custody check (composes the standing config dir, then
diffs it against canon), secrets resolution and a real, zero-cost
credential pre-flight, then launch -- with `--model` set from the
spoke's own declared `model_lane`, falling back to the operator's own
global default so an isolated config dir never silently drops it.

Real, verified finding before this was written (260901-FBL-056): no v1
`wcl`/`claude()`/`_claude_clean_env` shell functions exist anywhere on
this machine -- confirmed with a real interactive-shell `type` check.
`~/.local/bin` was already on `PATH`, so installing `wcl` needed no
`.bashrc` edit at all -- a lower-risk action than the shadow-and-rename
plan FBL-056 described, not a shortcut around it.

Shadow-aware delegation for minder: checked before any other step, read
fresh from the real deploy lug's own `state` field on every single
launch (never cached) -- `wcl minder` delegates to a plain, unwrapped
`claude` launch (no composed environment at all) while
`deploy-minder-minder-v2-tooling-*`'s own lug is anything but `done`,
and switches to a full v2, composed launch the moment it reaches `done`
-- no further edit to this circle required.

## Known, accepted gaps

The stale-instance check is a real, sometimes-inconvenient gate: a spoke
that IS genuinely behind current canon (an adopted spoke that hasn't
absorbed a newer framework cut yet) is refused, on purpose -- remediation
is a separate, explicit action (apply the pending cut), not something
this circle silently does on the operator's behalf just to get a launch
unblocked. Minder delegation is gated on the literal spoke name
`"minder"`, not a general "any unpromoted deployment" mechanism -- real
and sufficient for this build's one real shadow window, not yet
generalized to a second one.

## Hook resolution (260911)

Found live: regenerating an adopting spoke's settings.json through
compile-self (no frameworkRoot) emitted `node src/hooks/...` into a spoke with
no src/. Step 3b (`checkHookBindingResolution`, src/factory/hookBindingDrift.js)
now runs after the cut in both `wcl <spoke>` and `launchSpoke`, and refuses a
hook whose path does not exist -- named per hook. An adopting spoke regenerates
only through scaffold/applyCut with frameworkRoot.
