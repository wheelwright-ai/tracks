# Claude Code Instructions

**This project uses Wheelwright (WAI) for AI session continuity.**
Read `AGENTS.md` for universal WAI instructions. This file covers Claude Code specifics.

## Wakeup (MANDATORY — First Turn)

This spoke runs the **v6 kernel**. The kernel IS the wakeup — behaviour is code with
contracts, not instructions you have to carry.

1. Run `WAI-Harness/kernel/bin/wai brief` and print its output verbatim. It is a query
   over state, so it returns the same answer twice.
2. Then respond to the user's message.

`brief` returns mission, session, what was handed forward, and what is next. Nothing else
is required to start a session.

**Older layouts are DETECTED, never assumed.** Tooling expects v6; on meeting an
older spoke it interrogates rather than guessing — `source .claude/hooks/harness_mode.sh
<root>` and read `$HARNESS_ACTIVE`. Only when that resolves to `v4`/`v3` do the pre-v6
surfaces apply. Follow the first that you have CONFIRMED exists on disk — probe with
`test -e`, never assume, and never follow a path you have not just checked:
   - `.claude/commands/wai.md` (v4 — invoke `/wai`)
   - `WAI-Harness/spoke/commands/wai.md` (v3 fallback)
   - `WAI-Harness/spoke/skills/wai/wai.md` (v3 fallback)

On many spokes the two v3 paths no longer exist. That is expected, not an error.

After compaction: invoke `/wai-compact-resume`; live pointers in
`WAI-Harness/spoke/local/runtime/compact-resume.json`.

The hook at `.claude/hooks/user-prompt-submit.sh` injects this directive automatically on session start.

## Commands

| Command | What It Does |
|---------|-------------|
| `/wai` | Wakeup briefing |
| `/wai-closeout` | End session, save state |
| `/wai-time` | Token usage estimate |
| `/wai-status` | Quick health check |
| `/wai-rules` | Project boundaries |

## Session Tracking

After each turn, append a point to: `WAI-Harness/spoke/local/sessions/session-YYYYMMDD-HHMM/track.jsonl`
*(v3 coexist spokes: `WAI-Harness/spoke/session-YYYYMMDD-HHMM/track.jsonl`)*
See the track-encapsulation schema in `/wai-track`.

## Complexity Gate

If task affects 2+ files or requires 6+ steps: propose a plan, wait for approval.

## Stewardship

You are a **responsible partner**:
- Flag scope drift before enabling
- Complete foundation before work
- Prefer "are you sure?" over silent compliance

## Tool Ownership (author vs distribute)

Distributed tool/config — everything under `WAI-Harness/spoke/managed/**` (tools, schemas, templates, `.claude/`) plus `MANIFEST.json`, `.mcp.json`, provider files — splits into two roles:
- **Author** the canonical master source at the hub / canonical home (mywheel).
- **Basher owns distribution** — managed→live redeploy, fleet fan-out, re-cut mechanics.

A spoke does NOT edit the distributed source locally — propose changes via a lug (hub to author, Basher to distribute). Apply directly **only when purely local** (`WAI-Harness/spoke/local/**`). When in doubt, route it.

---

## Session-to-Session TAP (cross-spoke delivery)

Delivery used to be write-and-hope: a lug landed in `incoming/` and waited for someone to start a session. Measured 2026-08-02: three open lugs unread for up to 11 days. `lug_deliver.py` adds a push path so two live sessions can work an initiative together instead of leaving notes.

**SENDING.** Look before you knock, then deliver:

    python3 WAI-Harness/spoke/managed/tools/lug_deliver.py resolve --to <spoke_root>
    python3 .../lug_deliver.py deliver <lug.json> --to <spoke_root> --from <your_wheel_id> [--tap]
    python3 .../lug_deliver.py sweep --from <your_wheel_id> [--tap]

`resolve` reports each live lane with `pane`, `idle_secs`, `mid_turn` and `tappable`. `sweep` delivers everything in `outgoing/`, resolving each destination from the hub registry.

**RECEIVING.** A tap arrives as a user message beginning `[wai-tap from <spoke>]`. Read the named lug immediately, action or counter it, and **reply by writing a lug back to the sender's `incoming/`**. That reply is what turns a broadcast into a conversation and lets a multi-session initiative stay coherent. A tap you silently absorb is a dropped thread.

**THE THREE TIERS**, chosen from live state, never guessed:

| Tier | When | What happens |
|------|------|--------------|
| TAP | live + between turns + priority P0 | typed into its pane now |
| QUEUE | live but mid-turn | `<wai-inbox-notify>` catches it next turn |
| COLD | no live session | it waits; Herald may spawn one |

The lug is copied to `incoming/` **before** any terminal is touched, so a failed tap can never mean a lost delivery.

**THE LIMITS MATTER MORE THAN THE FEATURE.** Only `priority: P0` may tap — if everything can interrupt, the tap becomes the noise it replaced. Every tap is attributed to its sender, idle-gated, deduplicated by lug id, and cooldown-limited **at the mechanism rather than at the call sites**. That last point is not style: unguarded `write-chars` once spawned 64 tabs here, each auto-entering a resume command, until zjstatus OOM-crash-looped. No ceremony may hand-roll the raw zellij primitive to reach a session.

**BOUNDARY.** The tap reaches only sessions in zellij panes on the same machine. Herald's `claude -p` spawn remains correct for cold spokes, and an opencode session cannot be tapped at all because it registers no lane. Adoption does not imply otherwise.

**LIVENESS IS READ FROM THE TRANSCRIPT FIRST.** `last-interaction-<pane>` marks turn START and can freeze — measured on a live session whose stamp stuck 90 minutes behind while it worked, reporting `tappable: true` the whole time. The transcript's mtime is written by the session itself, so it vetoes: recent writes mean mid-turn no matter what the stamp implies.

---

## Multiple-Choice Confidence Bars

Before ANY multiple-choice question (inline options in chat or an AskUserQuestion call),
show a per-option confidence read as green ASCII bars — what the model believes is the
right choice, as a quick visual pre-read. Format (10-slot bar + percent, one line per option,
recommended option first):

    🟩🟩🟩🟩🟩🟩🟩🟩⬜⬜ 80%  (A) <option — Recommended>
    🟩🟩🟩⬜⬜⬜⬜⬜⬜⬜ 30%  (B) <option>

(Indented, NOT fenced. `communication-message-format` sets
`no_code_blocks_in_user_messages: yes` and `hash_border_blocks_plain: yes`, so a
fenced block in a reply to the operator is itself a violation. This file used to
demonstrate the format inside a fence, i.e. it taught the violation it was trying
to prevent — measured 17 times in one session before anyone noticed.)

- Percentages are the model's confidence each option is the right choice (need not sum to 100).
- Plain-block fallback where emoji don't render: `████████░░ 80%`.
- Never skip the bars because the question "seems obvious" — the visual IS the point.

---

*Wheelwright Harness — Claude Code Integration*

## Canonical record (OPERATOR RULING, s141)

> "Canonical record should reflect the harness today not backwards relevant."

**The v6 kernel store is canonical.** `WAI-Spoke/work/` is the record that DECIDES.
The v4 lug tree (`WAI-Harness/spoke/local/lugs/bytype/`) is **history** -- readable,
still read by ~34 managed tools, and not authoritative. Where the two disagree, v6 wins
and the v4 copy is stale.

A field enters `kernel.work.FIELDS` only with a **named live reader** or a **named
operator ruling**. "v4 had it" is not a justification. The prose fields --
`acceptance_criteria`, `execute`, `perceive` -- deliberately do NOT come across: v6
replaced them with `intent` + `verify`, and porting them re-imports what the rebuild
exists to shed.

Measured the day the ruling landed: `executor_model` had ZERO readers in the kernel,
managed tools or hooks, so 17 lugs had recorded a model-routing decision the dispatcher
could not see. Use `model_fit`. Check for readers before writing a field, not after.
