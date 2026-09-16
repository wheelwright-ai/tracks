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
refused), the custody check (the spoke's own local settings against
canon -- see below), secrets resolution and a zero-cost credential
pre-flight, then launch with `--model` from the spoke's `model_lane`.

Verified before writing (260901-FBL-056): no v1 shell functions shadowed
`wcl`/`claude` (a real `type` check); `~/.local/bin` was already on `PATH`.

Shadow-aware delegation for minder: read fresh from the deploy lug's own
`state` on every launch (never cached) -- `wcl minder` delegates to a
plain `claude` launch while `deploy-minder-minder-v2-tooling-*` is
anything but `done`, and composes the moment it is.

## Known, accepted gaps

The stale-instance check is a real gate: a spoke genuinely behind canon
is refused on purpose -- applying the pending cut is a separate, explicit
action. Minder delegation is gated on the literal name `"minder"`, not a
general "any unpromoted deployment" mechanism.

## Hook resolution (260911)

Found live: regenerating an adopting spoke's settings.json through
compile-self (no frameworkRoot) emitted `node src/hooks/...` into a spoke with
no src/. Step 3b (`checkHookBindingResolution`, src/factory/hookBindingDrift.js)
now runs after the cut in both `wcl <spoke>` and `launchSpoke`, and refuses a
hook whose path does not exist -- named per hook. An adopting spoke regenerates
only through scaffold/applyCut with frameworkRoot.

## The closed: line (260916)

After `spawnSync` returns, `composeClosedLine` (wclEntry.js) reads
`runtime/last-handoff.json`, the session's track, `git status
--porcelain` and `runtime/exit-verdict.json` (the exit hook's file, not
the ledger tail) and prints one line: `closed: track ok, handoff ok, tree
clean, exit <repo>: committed 3 file(s) as <sha8>, push deferred (...),
took 812s`. A file is this session's by id (ozi/resume) or, on a raw
launch, by being written after the launch; older reads as missing. 4 ms
on a scratch spoke, 103 ms on a 221-file-dirty hub. Record: wheel-hub
`docs/exit-prints-one-verdict-line.md`.

## The global sign-in (260916)

Operator ruling 2026-09-14 (lug wcl-launches-on-the-global-sign-in-
spokes-hold-only-local-settings): every interactive entry runs on the
operator's own `~/.claude` -- no `CLAUDE_CONFIG_DIR`, no per-spoke store,
no credential copy, no fleet token. The spoke contributes its
`.claude/settings.json` (+ `settings.local.json`): step 4 is
`checkLocalSettingsCustody` on those; the Sign-in row is
`globalAuthPreflight` on `~/.claude`, fixed by `claude auth login` before
the launch. Headless `launchSpoke` keeps the isolated store. Record:
`docs/config-custody-manifest.md`.
