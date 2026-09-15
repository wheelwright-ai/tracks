# bash-destructive-command-guard

260830-FBL-041-answers, Q4 (behavior harvest, LOST register): v1's real
`pre-tool-guard.sh` blocked destructive Bash commands broadly, general
scope. v2's `bashLugGuardHook.js` only guards writes into `lugs/` -- a
real, narrower scope than v1 had. A destructive command outside `lugs/`
(an `rm -rf` on a non-trivial path, an uncontrolled `git push --force`,
a `git reset --hard`, a truncating redirect over a real file) currently
passed through unguarded by any canon-declared hook. This circle is the
proactive, general half v1 had and v2 was missing.

## What it is, honestly

A command-string heuristic, not a parser -- same discipline
`bash-lug-guard` already established. It checks each logical line of the
command independently (the same disclosed residual gap: a single line
mixing an unrelated destructive token with something innocuous via
`;`/`&&`/`||`/`|` is not statement-split), and denies a line matching any
of four named, real patterns:

- `rm -rf`/`-fr`/`--recursive --force` (flags immediately adjacent to
  `rm`, not scanned across the whole line) on a path that is not under a
  real scratch/temp convention.
- `git push --force`, `--force-with-lease`, or `-f`.
- `git reset --hard`.
- A truncating redirect (`>`, not `>>`) over a path that is real, already
  exists on disk at deny-time, and is not under a scratch/temp
  convention -- reuses `bash-lug-guard`'s own real, live-tested
  exclusions (a bare fd redirect like `2>`, a fd duplication like `>&1`,
  a prose arrow like `->`), tightened to exclude `>>` specifically since
  the acceptance criterion names truncation, not append.

A path counts as scratch/temp when it starts with `/tmp/` or
`/var/tmp/`, contains a `/scratchpad/` segment, or is a bare relative
`tmp`/`temp`/`scratch` directory -- the same real convention this
codebase's own conformance fixtures and session scratchpads already use.

Posture is profile-configurable
(`autonomy_table_defaults.destructive_command_guard_posture: deny |
warn`, read from `canon/profile.yaml` under the session's own `cwd`),
default `deny`. Unlike `config-custody`'s own default `warn`, these four
patterns are all real, effectively unrecoverable data-loss classes, so
the safe default blocks; an operator who wants the softer behavior says
so explicitly. `warn` posture never blocks, but writes a real, named
ledger row rather than silently allowing the command through unremarked.

## Known, accepted gaps

Same class of gaps `bash-lug-guard` already accepts: a sufficiently
indirect command (an alias, a wrapper script, a variable holding the
dangerous flags) can evade this, and a single line mixing an unrelated
destructive token with an innocuous one via a statement separator other
than a newline is not split apart. This is the proactive half of the
fix, not a guarantee -- it is meant to catch the direct, common cases
that would otherwise have zero guard on them at all, not to replace
careful review of what a Bash command actually does.
