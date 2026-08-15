# WAI Closeout

Run these three, in order. Print their output. Then commit and push.

```bash
WAI-Harness/kernel/bin/wai save   <session> "<what you were doing>" --next "<what comes next>"
WAI-Harness/kernel/bin/wai close  <session>
WAI-Harness/kernel/bin/wai check
```

`save` writes the resume contract that the NEXT session's `wai brief` will CLAIM — not
display, claim. `close` reports what the session actually did, derived from the track, and
names what it left open. `check` is the gate: nonzero means the kernel is not healthy and the
session should not be reported clean.

## Two things closeout may never do

1. **Report work as done.** `close` reads; it never writes a completion. Completion has
   exactly one path and it is `wai work --done <id> --check ... --saw ...`, which refuses
   without evidence. 1,449 unrecheckable completions in the old corpus are what happens when
   closeout can mark things finished.
2. **Claim the mission.** `wai mission --land` needs a check and an observation, same as work.
   A mission cleared by saying so is a mission that gets cleared by saying so.

## What LANDED means, and why closeout is where it is checked

**LANDED = the commit is an ancestor of `origin/main`.** Not committed. Not pushed to a
session lane. Present on the branch everyone else reads. The shared definition lives in
`WAI-Harness/spoke/managed/tools/landing.py` and in `kernel/provenance.py`; both answer with
the same three values and neither may be second-guessed by a ceremony:

| | |
|---|---|
| `LANDED` | ancestor of canon |
| `NOT_LANDED` | done here, absent there |
| `UNKNOWN` | git could not answer -- no repo, no canon ref, or a commit that no longer exists |

`UNKNOWN` is never read as landed. That is the whole reason it is a third value rather than a
`False`: "we could not tell" and "it is not there" are different facts, and collapsing them is
how a closeout comes to report a clean desk over work nobody can find. `wai close` reports work that is done
but not landed as DEBT, separately from work that is landed, because "done here, absent there"
is the difference between a landing rate and a dream rate.

```bash
WAI-Harness/kernel/bin/wai work --landing        # done-but-not-on-canon, named
python3 WAI-Harness/spoke/managed/tools/work_split.py --write-handoff
```

`work_split.py --write-handoff` is still the v4 tool and is NOT yet ported to the kernel. It
writes the handoff the next session reads, so skipping it loses the split of what was finished
against what was carried. Run it until `wai save` covers the same ground.

The handoff ranks what remains by **unblock leverage** -- how much other work each item frees
-- not by age and not by how nearly finished it is. A handoff sorted by anything else hands the
next session a list instead of a starting point.

**`behind_canon` blocks; ahead is only debt.** The two are not symmetrical and the ceremony
must not report them the same way. Being AHEAD of canon is work owed -- legitimately owed while
other lanes are live, and it lands with a push. Being BEHIND canon means this tree is missing
work that already exists somewhere else, so anything built on top of it is built on a stale
base. Ahead is a debt to pay; behind is a stop.

## Why this file is short

The previous version was 1,390 lines. Length was not the defect — the defect was that it was
a procedure a model had to remember and follow, so parts of it were skipped silently and no
two runs matched. A savepoint that was written, a version that was bumped, telemetry that was
recorded: all of them were prose steps, and prose steps fail quietly.

`save` / `close` / `check` are functions with contracts and tests. They ran or they did not.

## Still owned by v4 — run these, they are not gone

These four steps were dropped when this file was rewritten, which is how a 1,390-line ceremony
loses behaviour: the mechanics were never the problem, the instruction to run them was. Each
already has a working tool, so porting would duplicate code rather than improve it. They stay
v4-owned until the kernel has a reason to absorb them.

```bash
WAI-Harness/spoke/managed/tools/closeout.sh          # version bump, session_count, lug archival
python3 WAI-Harness/spoke/managed/tools/harness_telemetry.py       # spoke telemetry
python3 WAI-Harness/spoke/managed/tools/write_change_receipt.py    # hub receipt
python3 WAI-Harness/spoke/managed/tools/registry_version_stamp.py --apply   # registry truth
```

The changelog is appended per resolved lug to `spoke/local/runtime/spoke-changelog.jsonl`;
framework-internal changes belong in `CHANGELOG.md`, never in the spoke changelog.

## What is NOT yet ported

The old closeout also did: version bump and changelog, spoke telemetry, hub receipt delivery,
and the fleet-wide push gate. Those are UNPORTED, not covered, and the prose is preserved at
`.claude/commands/wai-closeout-prose-v4.md` while they are. Run it when you need one of them.

## Rollback

`cp .claude/commands/wai-closeout-prose-v4.md .claude/commands/wai-closeout.md`
