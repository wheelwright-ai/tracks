# session-exit-commit

260830-FBL-050, from the v1 behavior harvest's LOST register (Git
Hygiene, ACT arm): v1's session exit committed and pushed. v2's did not.

## The incident this answers

When this circle was written, two live spokes held ~200 uncommitted
changed files across a dozen sessions: nothing lost, nothing attributable,
because none of it was in `git log` -- and all of it on one machine.

## What it does

Fires on SessionEnd, after `session-end-handoff` has closed the track --
load-bearing, since the message is read off the closed track.

For cwd **and every registered, present-on-disk repo** (260829-FBL-034's
cross-repo resolution: a session rooted in one spoke routinely moves
another's lugs):

1. **Posture.** `autonomy_table_defaults.auto_commit_on_exit` in the
   spoke's own `canon/profile.yaml`, defaulting to **true**: this circle
   exists because not-committing caused the incident. A spoke that must
   not self-commit says so explicitly.
2. **Stage** everything real (`git add -A`), then read the staged set.
3. **Pre-flight: never commit a secret.** Rule 13's credential patterns
   (`scanFilesForCredentials`) plus a credential-filename check over the
   staged set. Any finding blocks the commit, unstages so no loaded index
   is left behind, and writes a ledger row naming the file and line --
   never the value.
4. **Pre-flight: never push a red tree.** `runtime/last-test-run.json`,
   written by `scripts/record-test-run.js`, which `npm test` now runs
   *through* so a RED run is recorded too. Red means the work lands on
   `wip/<date>-<callsign>` and is **not** pushed; the mainline is
   untouched and a ledger row says so.
5. **Commit** with the generated message. `-F -`, never `--no-verify`.
6. **Push** to origin, never `--force`. On any failure -- conflict,
   missing remote, a pre-push hook that said no -- the commit stays
   local, a ledger row records the real error, and the next wakeup's
   "what changed" announces it.

## The generated message

Not typed. Read off the session's own closed track and registry row:

```
Session work: some-real-lug

Coordinates: <user>/<machine>/<spoke> - <callsign> - <date> - session <uuid>
Lugs worked:
  some-real-lug: defined -> in_progress
Prompt ids worked: 260830-FBL-050
Committed by: session-exit-commit circle (260830-FBL-050)
```

That is what makes `git log` a ledger view rather than a diary: every
commit joins to a track, and through the prompt ids, to a ruling.

## Not configurable

- **Never `--force`.** A push needing force is a real conflict, and a
  conflict is something to be told about, not overwritten.
- **Never `--no-verify`.** A repo's hooks are its owner's policy.
- **Never commit credential material.**

## Disclosed judgment calls

- **An absent test-run record is not a red one.** Treating "never
  measured" as red would route every aggregator-less repo onto WIP;
  absence is recorded in the row ("pushed on an unknown") instead.
- **A red exit leaves the session on the WIP branch.** Switching back
  would hide from the next session that its predecessor ended red.
- **No track yet?** A session ending inside turn one has none. Coordinates
  fall back to the SessionStart registry row; lugs and prompt ids are
  reported absent, never invented.

## Failure mode

Every path is non-blocking: a session must be able to end even when its
exit commit could not; the work stays in the working tree.

## Exit path, measured (260911)

Lug `session-exit-path-fails-five-ways-and-surfaces-none-of-them`: the hook was
cancelled at the 30s default while a refusal took 121s through three gates, so
`hook_timeout_seconds: 240` (2x measured; re-run 42.7s). A refusal now prints its
verdict to stderr and exits 1, and the ledger row keeps the verdict line. Fixture:
`conformance/fixtures/session-exit-path-fails-five-ways-and-surfaces-none-of-them/`.
