# wcl-verify-then-launch

260831-FBL-056: "basher v2's `wcl` verb already composes the
environment... but it is not installed as the operator's shell command."
This circle is that installation: one installed executable (`bin/wcl` ->
`~/.local/bin/wcl`) that verifies before it launches and hands the
operator a tracked, custody-clean, correctly-modeled session.

## What it is, honestly

Sequential checks, one line each, a named fix on any refusal:
sync-on-wake (fetch, ff-only pull when behind, refuse a dirty tree), the
stale-instance check (self-hosting = a real compile of its own canon;
adopted = `checkSpokeDrift`), pending-cut application per the spoke's
posture (a held cut is reported, not refused), the custody check (local
settings against canon), secrets, a zero-cost credential pre-flight, then
launch with `--model` from `model_lane` and `--permission-mode` from the
wheel's one `permission_mode` (below).

Shadow-aware delegation for minder: read fresh from the deploy lug's
`state` on every launch -- `wcl minder` delegates to a plain `claude`
launch until `deploy-minder-minder-v2-tooling-*` is `done`.

## The freshness gate and its remedy (260916)

Scaffold-rule drift is not local drift: `pendingCutVerdict` compares each
candidate to the recorded cut's own source (`cutProducedFiles`); only
`editedFiles` refuses. At a terminal the refusal is a chip menu
(`runFreshnessRemedy`): `a` reverts canon/circles to the recorded cut
behind a confirm naming every file (Enter is not a yes), then step 3
applies the current cut; `d` diffs; `q` exits 1. Record:
docs/wcl-freshness-refusal-offers-the-remedy.md.

## Hook resolution (260911)

Found live: compile-self (no frameworkRoot) emitted `node src/hooks/...`
into an adopting spoke with no src/. Step 3b (`checkHookBindingResolution`,
src/factory/hookBindingDrift.js) runs after the cut in `wcl <spoke>` and
`launchSpoke` and refuses a hook whose path does not exist, named per hook.

## The closed: line (260916)

After `spawnSync` returns, `composeClosedLine` (wclEntry.js) reads
`runtime/last-handoff.json`, the session's track, `git status
--porcelain` and `runtime/exit-verdict.json` (the exit hook's file, not
the ledger tail) and prints one line: `closed: track ok, handoff ok, tree
clean, exit <repo>: committed 3 file(s) as <sha8>, push deferred (...),
took 812s`. A file is this session's by id (ozi/resume) or, on a raw
launch, by being written after the launch. Record: wheel-hub
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

## One permission mode wheel-wide (260916)

Operator 260914: "Cross-session message expired without approval" -- two
sessions in different permission classes hold every cross-session message
for approval. `canon/profile.yaml`'s `permission_mode` (enum = the
installed `claude --help`) is read by `resolvePermissionMode` beside the
lane: hub profile = the wheel-wide value, a spoke must declare the same
(mismatch refuses naming both; omission refuses naming the field -- never
a default); every interactive launch spawns `--permission-mode <mode>`;
headless keeps `bypassPermissions`. Record:
`docs/wcl-one-permission-mode-wheel-wide.md`.
