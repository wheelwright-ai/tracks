# falsifiability-gate

lug `verify-commands-have-no-falsifiability-gate`: a check that reports
green regardless of the real state of the thing it claims to verify is
worse than no check, because it looks like coverage. This circle asks, of
a real verify command, whether it CAN be made to go red.

Ported from `WAI-Harness/kernel/harvest.py` (`falsifiable`,
`_mutation_for`, `_mirror`, `_target_in_command`, `prove`), read as
reference and rebuilt in JS. **The full design disclosure -- what was
kept, what changed and why -- is the header comment of
`src/assayer/falsifiable.js`.** The honest ledger of what was proven and
what remains unverified is `wheel-hub/docs/falsifiability-gate.md`.

## The defect it exists for

From that project's own docstring, in production:
`sh -c "! grep -n X /wrong/path.sh | grep -q Y"` exits 0, because grep on
a file that is not there finds nothing. The check decides, confidently,
about a file it never opened. Deciding and being correct are different
properties and only one of them was gated.

## How it works

1. Run the command against the real tree; record the exit code.
2. Mirror the tree to scratch: only directories along the artifact's own
   path are materialised, every sibling is a symlink to the real thing.
   Cost scales with depth, not repo size, and `.git` still answers.
3. Mutate: `remove` for an existence claim, `create` for an absence
   assertion, `empty` for content and parity.
4. Re-run the same command with cwd at the scratch root.
5. Certify `falsifiable` only if the exit code genuinely moved.

Nothing under the real root is written, moved or removed -- the same
observe-only rule it enforces on the checks it accepts.

## Three verdicts

`falsifiable` (the answer moved), `unfalsifiable` (it did not, or the
command opens a path that is not there -- the false green), and
`unproven` (the gate cannot honestly say). Unproven is never rounded up
to a pass; it is counted and printed separately.

## Refusals to slander

Each was earned by the source project getting it wrong first on a real
corpus: a whole-suite or behavioural claim, a command that does not
decide, a check that already fails today, a command reading outside the
tree the mirror reaches, a negative-content claim that emptying cannot
break, and a content claim about an artifact that is not there -- all
return `unproven` with the reason. A command opening a relative path that
does not exist is condemned `unfalsifiable` statically, with the
deliberate exemption for `test ! -e x`.

## Running it

    node scripts/falsifiability-gate.js                  # declared target set
    node scripts/falsifiability-gate.js --root=../wheel-hub
    node scripts/falsifiability-gate.js --command='...' --artifact=src/x.js --class=content

Exit 0 when nothing was shown unfalsifiable, 1 when something was, 2 when
the gate itself could not run. Target sets:
`conformance/falsifiability-targets.json` here and in the spoke,
deliberately small. **Every check not in them is unverified.**

## Deliberately not in this cut

Not wired into the `done` transition or the Assayer coverage ledger (lug
acceptance 2 and 4). Filed as
`falsifiability-gate-not-wired-into-done-transition-or-coverage-ledger`
rather than half-built here.
