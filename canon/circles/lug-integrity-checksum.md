# lug-integrity-checksum

Ruling 2026-08-26, second of two changes closing the Bash-tool bypass:
`bash-lug-guard` is proactive and heuristic; this is the backstop that
isn't. Every `Stop`, it checksums every lug file against the baseline the
kernel verb (`src/lugTracking/lugVerb.js`) maintains after every authorized
write. A mismatch means something wrote to a lug file without going
through the verb -- whatever it was, however it got past
`bash-lug-guard`.

## Forgery vs. content (2026-09-12)

`integrity-backstop-demotes-lugs-whose-work-really-landed`: the baseline
records the lifecycle fields (`state`, `readiness` -- what readyWork.js,
the Planner and the Conductor key off) at every authorized write, not just
a checksum. On a mismatch, `classifyViolation` compares them: a change to
either is a forgery and is healed below; a change to anything else on an
unchanged-lifecycle lug (intent, pointers, tests, a pickup block) is a
content edit -- adopted as the new baseline, state untouched, ledger row
`integrity_disposition: adopted_content_edit`. Measured before: 110 heals
in 7 days on wheel-hub, 45 from review/in_progress. Legacy checksum-only
entries are upgraded in place when their bytes still match; one that has
already drifted is healed conservatively and the row says why.

## What it does on a forgery

- Forces that lug's `state` back to its own type's reset state -- not a full
  content revert, specifically the state, since state is what every gate
  downstream keys off of. For `work` that is `defined`, exactly as it always
  was. Since `implement-lug-type-field-and-conditional-requirements` the
  target is resolved per type (`resetStateForLug`,
  `src/lugTracking/lugType.js`): a pebble goes to `captured`, because
  `defined` is a work state a pebble cannot legally hold and writing it there
  produced a schema-invalid lug; a notice goes to `posted` and a remember to
  `active` (the entry state of each lifecycle). Only for a type this build
  does not know is the state left alone rather than guessed at, and the
  ledger row says so.
- Writes a ledger row naming the lug, its state before the fix, and the
  tool that made the unauthorized change -- attributed best-effort from the
  real session transcript (`src/lugTracking/attributeViolation`): the last
  tool call in the transcript whose input mentions the lug's path. This can
  be wrong if two tool calls touched the same file in one turn; it is never
  fabricated when nothing matches (returns `"unknown"` rather than a guess).
- Resets the baseline to the lug's current (now-healed) state, so the next
  `Stop` doesn't re-flag the fix itself.

## What it does NOT treat as a mismatch worth healing

Added 2026-09-02 (`lug-integrity-heal-clobbers-legitimate-git-merges`,
found live three times): "changed outside the kernel verb" covers two very
different things. Landing a dispatched session's real work with
`git checkout <branch> -- <lug>` also bypasses this session's verb calls,
so it never registered a baseline -- and this circle was silently reverting
real, authorized transitions back to `defined`.

Before healing, it asks git for evidence (`hasGitProvenance`): is the
file's current content a blob git has committed for that same path, on any
ref? Only a real git operation produces that. When git vouches for it, the
content is adopted as the new baseline, the state is left alone, and a
ledger row says so. When git cannot vouch -- including "not a git work
tree", where the answer is unprovable -- the heal runs. Accepted blind
spot: an operator deliberately checking out an older committed version of
a lug to move its state.

## What it doesn't do

It never touches a lug with no baseline entry yet -- that's a lug the verb
has never written, and definition-complete-gate's job, not this one's. It
never mutates a lug that matches its baseline. It runs once per turn, on
every lug, whether or not anything is active -- cheap, and the only way to
catch a change that happened entirely outside any hook's view.
