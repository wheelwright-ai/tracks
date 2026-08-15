# WAI Wakeup

Run this. Print its output verbatim. Then respond to the user.

```bash
for _k in WAI-Harness/kernel/bin/wai WAI-Spoke/kernel/bin/wai; do
  [ -x "$_k" ] && exec "$_k" brief
done
echo "[wai] NO KERNEL on this spoke. Run 'wai install .' from the master (mywheel) to"
echo "      vendor one. Until then this spoke has no wakeup -- do not improvise a brief."
exit 127
```

That is the whole ceremony.

**Why the loop instead of one path.** This file is distributed to every spoke, and the
kernel does not live in the same place on all of them. On the master it is the source tree
at `WAI-Harness/kernel/`; on a spoke it is the copy `wai install` vendors to
`WAI-Spoke/kernel/`. A single hardcoded path was correct on the master and wrong
everywhere else, and because the wrong branch printed nothing, pathfinder's `/wai` exited
127 at every wakeup from the cutover until 2026-08-14 and nobody saw it. The loud `exit
127` is the other half of that lesson: a spoke with no kernel must say so, because the
alternative is an agent quietly inventing a briefing.

## Why this file is nine lines and not 633

The previous version was a program written in English and executed by an LLM, and it failed
the way that always fails:

- A savepoint was DISPLAYED at wakeup and left unclaimed, because "display it" and "claim it"
  were the same paragraph and two different acts. The operator had to ask whether his work had
  been picked up.
- Steps were skipped under context pressure, silently, because compliance depended on the
  model still remembering step 14 after reading step 633.
- Two spokes running "the same" ceremony did different things and nothing could tell.

`wai brief` is a query over state. It either ran or it did not. It returns the same answer
twice. The step that claims a savepoint cannot be skipped, because it is not a step — it is a
function call with a return value, covered by `kernel/tests/test_brief.py`.

## What it gives you, in this order

1. **MISSION** — what the operator asked for. Nothing outranks it. It survives session end and
   is cleared only by `wai mission --land` with evidence, or by him replacing it.
2. **SESSION** — which session this is, and how sure the kernel is.
3. **RESUMED** — what the last session handed forward, already CLAIMED.
4. **GOAL / SPEED / DRAG** — where the spoke is and how fast it is moving. Generation and
   landing are separate numbers on purpose.
5. **NEXT** — one action, by a ladder written down in `kernel/ozi.py` so you can argue with it.

## The rest of the surface

| Command | Answers |
|---|---|
| `wai forward` | goal, speed, drag, next action |
| `wai mission --set "..."` | leave the operator's intent for the next session |
| `wai work --new / --start / --done` | a unit of work; completion is refused without evidence |
| `wai canary` | rollouts in flight; nothing widens without canary evidence |
| `wai check` | contracts and refusal conventions; the gate verb |
| `wai save / close` | hand work forward, end the session |

## Rollback

The prose ceremony is preserved at `.claude/commands/wai-prose-v4.md`. Restoring it is a copy,
and cutover 4's canary rollback does exactly that.
