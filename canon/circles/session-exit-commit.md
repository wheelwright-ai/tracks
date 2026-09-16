# session-exit-commit

260830-FBL-050, the v1 harvest's LOST register (Git Hygiene, ACT arm):
v1's exit committed and pushed; v2's did not, and two live spokes held
~200 uncommitted files across a dozen sessions, none of it in `git log`.

## What it does

Fires on SessionEnd after `session-end-handoff` closed the track. For cwd
and every registered, present-on-disk repo (260829-FBL-034):

1. **Posture.** `autonomy_table_defaults.auto_commit_on_exit` in
   `canon/profile.yaml`, default **true**.
2. **Stage only this session's files** plus hook-written harness state, by
   pathspec -- see "Whose files".
3. **Never commit a secret.** Rule 13's patterns plus a filename check;
   a finding blocks, unstages, writes a row naming file and line.
4. **Never push a red tree.** `runtime/last-test-run.json`; red lands on
   `wip/<date>-<callsign>`, mainline untouched, row written.
5. **Commit** with the generated message (`-F -`, never `--no-verify`).
6. **Push** is deferred (see "Exit path, measured"); never `--force`; a
   failure stays local with a row the next wakeup announces.

## Whose files (260914)

Never `git add -A` (it swept a peer lane's edit, 5bd3432). Own files
(files-touched record + transcript) and harness state are staged by
pathspec; a live peer's file is contended and left with a row naming
both ids; the rest is left and named. Detail:
`reference/circles/session-files-touched.md`.

## The generated message

Not typed. Read off the session's own closed track and registry row:
subject `Session work: <lug>`, a Coordinates line (triple, callsign,
date, session uuid), `Lugs worked:` with each transition, `Prompt ids
worked:`, and the circle's own trailer. Every commit joins to a track
and, through prompt ids, to a ruling.

## Not configurable

Never `--force` (a conflict is told about, not overwritten); never
`--no-verify` (a repo's hooks are its owner's policy); never commit
credential material.

## Disclosed judgment calls

- **An absent test-run record is not a red one** -- "never measured" is
  recorded in the row ("pushed on an unknown"), never routed to WIP.
- **A red exit leaves the session on the WIP branch**, so the next session
  sees its predecessor ended red.
- **No track yet?** Coordinates fall back to the SessionStart registry
  row; lugs and prompt ids are reported absent, never invented.

## Failure mode

Every path is non-blocking: the session ends even when the commit could not;
the work stays in the working tree.

## Exit path, measured (260911, re-measured 260914)

260911: cancelled at the 30s default while a refusal took 121s ->
refusals print their verdict to stderr, exit 1, keep it in the row.
260914: three real `/exit`'s were cancelled at ~60s whatever was declared
-> `hook_timeout_seconds: 60`; a fixed 12s commit-gate budget
(`EXIT_GATE_BUDGET_MS`, the rest deferred to the push gate by name); no
push at SessionEnd (a "deferred by design" row, announced next wakeup);
45s wall cap on the repo loop. Fixture section H proves it.

## Exit verdict (260916)

Exactly ONE stderr line, last, on every run: `session-exit-commit: <repo>:
committed N file(s) as <sha8>, push deferred (<why>) | clean | REFUSED --
<cause> | push failed -- <cause> | wip <branch> <sha8> (tree was red)`;
the detail lines above stay. The same verdict goes to
`runtime/exit-verdict.json` {session_id, repo, verdict, detail, at,
wall_ms}, which wcl's `closed:` line reads -- the file, not the ledger
tail (its last rows are whatever wrote last; a verdict is a per-session
fact). Record: wheel-hub `docs/exit-prints-one-verdict-line.md`.
