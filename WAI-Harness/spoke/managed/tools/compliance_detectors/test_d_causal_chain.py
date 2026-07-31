"""Tests for d_causal_chain — communication-explicit-causal-chain.

EVERY fixture is VERBATIM assistant text from this repo's own transcripts under
~/.claude/projects/-home-mario-projects-wheelwright-mywheel/, cited by transcript
filename at its definition. Nothing here is invented prose dressed up as a
closing: the preference exists because of what this repo actually shipped, so the
detector has to hold against that and not against text written to please it.

WHY THE NEGATIVE CASES CARRY THE WEIGHT. This detector reports an ABSENCE. Its
cheap error is missing a loop-open closing. Its expensive error is telling the
operator he never named a next step in a report that named one plainly — a
finding he cannot act on and can only learn to distrust. So each clean fixture is
paired with a CONTROL: the same real text with exactly the clause carrying one
element removed, which MUST fire and MUST name that element. Without the control,
a clean-fixture assertion passes just as happily against a detector that has been
broken into permanent silence.

THREE DETECTOR BUGS WERE FOUND BY WRITING THESE TESTS and fixed rather than
enshrined — each one the expensive error, each one found by sweeping all sixty
closings in the corpus instead of the two that came to mind:
  * "Decisions for you, in order: 1. Nothing needed" (073d8ac3) was reported as
    ending WITHOUT what is waiting and on whom.
  * "so you can approve the batch … Shall I proceed?" (ffc05a94) — a message
    that IS the ask — was reported the same way.
  * "Recommended session-closing action: **savepoint**" (d8313da6, twice) was
    reported as ending with no next action named.
The sweep is kept as a live test (`test_corpus_*`) so the next regression of that
class is caught by the suite rather than by the operator.
"""
import glob
import os
import sys

import pytest

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from compliance_detectors.d_causal_chain import (  # noqa: E402
    PREF_ID, CLOSING_ONLY, detect, is_report)

_AUTOMATIC = "what happens AUTOMATICALLY"
_WAITING = "what is WAITING and on WHOM"
_NEXT = "THE single next action"


def missing(text):
    """The elements the detector says are absent. [] when it stays silent."""
    hits = detect(text, {})
    assert len(hits) <= 1, f"one finding per report, got {len(hits)}"
    if not hits:
        return []
    return [e for e in (_AUTOMATIC, _WAITING, _NEXT) if e in hits[0]["note"]]


# --- real corpus fixtures ----------------------------------------------------

# THE VIOLATION, and it is the preference's own example.
# c1e083fb-f9bb-439c-b8ee-b0156115574f.jsonl, final block. Three gaps closed,
# then "Routed to Basher as impl-ap-commit-session-guard-v1" and a full stop.
# Nothing automatic is named, no owner is named, no next action is named — the
# operator is left to work out that the lug now sits in another repo's inbox
# until a basher session happens to wake and read it.
REAL_VIOLATION_CANONICAL = (
    "Done. Here's what was executed:\n"
    "\n"
    "**Gap-2 (validate_canonical.py — stale path):** Fixed in `WAI-Harness/spoke/managed/tools/validate_canonical.py`. The tool now tries `managed/knowledge/spec/active/` first (the canonical Basher distribution location) before falling back to `local/lugs/bytype/spec/`. Also adds `\"status\": \"unverified\"` to JSON output when `checked == 0` so a misconfigured verifier can't silently impersonate a clean pass. Verified: `checked=1630 errors=1221` on mywheel (contract found, real validation ran).\n"
    "\n"
    "**Gap-3 (wai-closeout.md Step 0a bootstrap ambiguity):** Added an explicit **Bootstrap obligation** note to all three copies of wai-closeout.md (template, managed/.claude/commands/, .claude/commands/). The note makes clear: \"Do not block\" at Step 0a is a per-step exemption only — a RED stub is not exempt from Step 10i's convergence re-verification, which re-runs the test gate on the merged HEAD and blocks there just as hard. Real tests must be added before the closeout can complete.\n"
    "\n"
    "**Gap-1 (git race — AP pushes to origin during live sessions):** Routed to Basher as `impl-ap-commit-session-guard-v1` in `/home/mario/projects/basher/WAI-Harness/spoke/local/lugs/incoming/`. The lug specifies three implementation options (recommend: (c) strip all `git push origin` from background scripts immediately + (b) AP commits to its own branch long-term) with concrete file targets.\n"
    "\n"
    "Commit `a688156` on `session/herald-navcap-20260701-2239`, pushed. Completion notice delivered to ezorg-email-website incoming. Notice lug moved to `bytype/notice/completed/`."
)

# CLEAN, the house form. d8313da6-cd01-415a-a221-5fb24d75d514.jsonl, closing.
# The chain is a named section: "Automatic: nothing running." / "Waiting on you:
# open basher, run `/wai`". Kept whole rather than trimmed to the closing
# section, because trimming would drop the delivery vocabulary that puts the
# block over the report floor — and then the test would be measuring the
# abridgement instead of the block.
REAL_CLEAN_EXPECTATION = (
    "####################################################\n"
    "CLOSED OUT — CLEAR TO EXIT\n"
    "####################################################\n"
    "\n"
    "🟢 1487 tests pass, 0 failures\n"
    "🟢 Working tree clean, 40 commits, all pushed\n"
    "🟢 basher at **4.13.1**, canon clean, retired elements dropped\n"
    "🟢 Closeout savepoint 6/6 machine-verified, 100% checkable\n"
    "🟡 3 legacy stashes still quarantined, untouched\n"
    "\n"
    "####################################################\n"
    "REHEARSING BASHER CAUGHT A PHANTOM UPGRADE\n"
    "####################################################\n"
    "\n"
    "This is the one that matters, and it would have fired **in front of you**.\n"
    "\n"
    "`deploy_commands` reported **\"2 synced\"** while deploying nothing. Two commands were on the retired list *and* still in basher's managed tree — so the sync deployed them and the prune deleted them in the same run. Net zero, announced as success.\n"
    "\n"
    "Distribution copies files **in** but never removes files that should be **gone**, so that contradiction sat on every spoke that ever received them.\n"
    "\n"
    "You'd have run `/wai`, seen a confident sync banner, and nothing would have changed.\n"
    "\n"
    "Fixed: retired files are now removed from **both** trees. That's what makes an upgrade genuinely *drop* deprecated elements — and it's the evidence-based half of the cleanup you approved.\n"
    "\n"
    "####################################################\n"
    "I DID NOT DO THE BULK CLEANUP YOU APPROVED\n"
    "####################################################\n"
    "\n"
    "Your approval was based on my report, and **my report was wrong twice.**\n"
    "\n"
    "The keyword detector flagged `deploy_commands.py` itself — the tool I'd used in production minutes earlier — because the word \"deprecated\" appears in its prose about something else. The orphan detector then flagged `lug_gate`, which runs on **every commit** via `.githooks`, a path my scan didn't cover.\n"
    "\n"
    "Zero high-confidence candidates survived scrutiny. Deleting 32-56 files on evidence that failed twice would have broken the harness, and \"it's reversible from a commit\" isn't a reason to break it.\n"
    "\n"
    "That was the fourth confidently-wrong instrument today. `canon_adherence` was the fifth — it reported retired commands as capabilities basher was *missing*, when they're the opposite.\n"
    "\n"
    "####################################################\n"
    "SETTING YOUR EXPECTATION HONESTLY FOR BASHER\n"
    "####################################################\n"
    "\n"
    "I owe you a correction on what you'll see.\n"
    "\n"
    "**basher is already at 4.13.1 and clean.** The upgrade already happened — through distribution, which is the fleet path. So `/wai` will **confirm state, not perform a visible upgrade.** No sync banner, because there's nothing left to sync.\n"
    "\n"
    "What you should see: **`v4.13.1`** in the statusline (new this session), and a clean canon report.\n"
    "\n"
    "If you want to watch an upgrade actually install, that's a different test — and the honest one is the **bootstrap** path on a fresh wheel, which I proved works but basher hasn't used.\n"
    "\n"
    "Your standing rule is encoded: every cut gets dogfooded on basher first, and dogfood means **run the instruments**, not copy files and count them. That distinction is exactly what caught today's defect.\n"
    "\n"
    "####################################################\n"
    "WHAT HAPPENS NEXT\n"
    "####################################################\n"
    "\n"
    "Automatic: nothing running. Everything committed and pushed.\n"
    "\n"
    "Waiting on you: open basher, run `/wai`, and tell me what it reports. I've deliberately left it untouched so your observation is the evidence — and if something surprises you there, that's the finding, not a failure.\n"
    "\n"
    "**CLEAR TO EXIT.**\n"
    "\n"
    "Turn 23 | Sat, Jul 18, 2026 | 11:31 AM PDT | claude-opus-4-8 | v4.13.1 | Gold: +8"
)

# CLEAN by DENIAL. daefed6b-678c-4341-a4a2-8a5c288eccbb.jsonl, closing.
# "Nothing is waiting on the harness. One thing waits on you, and nothing
# automatic will resolve it". The detector's design says a denial closes the
# operator's deduction as well as an assertion does; this is the real text that
# claim has to survive.
REAL_CLEAN_DENIALS = (
    "Savepoint updated and pushed. Everything verified by tool, not asserted.\n"
    "\n"
    "On the model showing unknown — I expected a broken hook and found the opposite. The hook resolved `claude-opus-4-8` from turn 2 onward, the buffer held it correctly, and 5 of your 6 track rows recorded it properly. Turn 1 is genuinely unknown because no assistant message existed yet to read a model from.\n"
    "\n"
    "The fault was mine. I copied turn 1's statusline and re-rendered it for six turns instead of re-reading the hook's updated line each turn. Had I patched the hook, I would have been fixing a healthy component. There is now a deterministic detector for that exact class, so it gets caught rather than noticed by you.\n"
    "\n"
    "On whether tracks can be improved — yes, and I measured your track rather than guessing. The finding that matters: **22 decisions recorded this session, zero ever revisited.** A decision that was later proven wrong looks identical to one that held.\n"
    "\n"
    "This session is the perfect example. I authored a lug, ran it through multi-lens review, passed the gate, committed and pushed it — then an adversarial audit scored it 4 out of 10 and falsified its central claim. Nothing in the track connects that reversal to the original decision. Six more self-corrections happened today and none are recoverable from the record.\n"
    "\n"
    "So the track logs what we did and forgets what we learned. That is exactly what you were asking about. It is lugged as track v2.1, with decision outcomes, thread lifecycle, and a correction-rate figure surfaced at savepoint so you can see the learning signal directly instead of asking for it.\n"
    "\n"
    "One thing I deliberately protected: `assistant_text` is 46% of track bytes and looks like obvious duplication of the Claude Code transcript. It is not. That transcript is machine-local and never committed, so the track is the only copy that survives a machine loss. I recorded that as an explicit non-goal so a future optimiser does not helpfully delete your history.\n"
    "\n"
    "Exit state, all tool-verified: zero uncommitted, zero unpushed, zero branches ahead, HEAD matches origin at 3591c9a2, resume contract validates clean. The savepoint carries 7 work items and 7 honest flags, with 2 lugs completed and 4 opened.\n"
    "\n"
    "Nothing is waiting on the harness. One thing waits on you, and nothing automatic will resolve it: the oracle measured two of your preferences as genuinely not binding — plain-text message format and the three-sentence paragraph limit. Either the delivery mechanism changes, or you rule them aspirational. A machine cannot pick.\n"
    "\n"
    "Next session opens on: raise oracle coverage above 4.6% by adding detectors.\n"
    "\n"
    "**CLEAR TO EXIT.** Ready to exit session.\n"
    "\n"
    "Turn 7 | Sat, Jul 18, 2026 | 3:48 AM PDT | claude-opus-4-8 | Gold: +0"
)

# VIOLATION, one element only. d5f2dd37-5ec1-4ca1-b794-31b1601c04db.jsonl,
# closing. A dense savepoint report with a resume note and a "Next wakeup will"
# — but nothing anywhere about what is waiting or on whom. The single-element
# case is the one that proves the note reports what it found rather than a
# blanket "no chain".
REAL_VIOLATION_NO_OWNER = (
    "## Savepoint — saved, verified, pushed\n"
    "\n"
    "| Check | State |\n"
    "|---|---|\n"
    "| Resume contract | **validated** (`OK — resume contract satisfied`) |\n"
    "| Savepoint | `pending` → `sp-session-20260724-0755-savepoint` |\n"
    "| Git | HEAD = main = origin/main = `c233975e` · **0/0** · **0 uncommitted** |\n"
    "| Version | `4.14.8`, both managed roots recut |\n"
    "| Committed via | `git_hygiene` itself — dogfooded on its own savepoint |\n"
    "\n"
    "**What this session shipped** (all verified from git/tests, not asserted):\n"
    "- Branch reunified (was 64-ahead of a stale local main; clean FF)\n"
    "- `git_hygiene.py` ACT arm — built, 14 tests, adversarially hardened, wired live into session-start\n"
    "- 364 runtime files swept, tree went from 264 dirty → clean\n"
    "- Landed 6 authored hook strands + bumped `4.14.7 → 4.14.8` (answered Basher's version note, acked)\n"
    "- Basher's 3 lugs triaged; fleet-distribution routed to Basher (Basher confirmed done)\n"
    "\n"
    "**Next session resumes here →** the resume note is the load-bearing one:\n"
    "> **Fix `bug-restore-live-hooks-false-current-verdict-v1`** — restore reports \"live hooks current\" while the live hook is stale. Until that's fixed, the git_hygiene ACT-seat can't reliably reach the fleet. Then triage the 30 pending incoming (mostly 4.14.7 PARTIAL upgrade-reports).\n"
    "\n"
    "Everything's pushed and the tree's clean — **safe to walk away.** Next wakeup will drop you straight back on the deploy-verdict bug."
)

# REGRESSION FIXTURE 1 — the false positive that made this suite worth writing.
# 073d8ac3-93bf-42a5-9ea7-09d00c384510.jsonl, closing. "Decisions for you, in
# order: 1. **Nothing needed**" names the owner and then closes the question in
# one breath. The shipped detector required the literal word "open" in front of
# "decisions for you", so it graded the clearest statement of the element in the
# whole corpus as that element's absence.
REAL_CLEAN_DECISIONS_FOR_YOU = (
    "```\n"
    "###############################################################\n"
    "# LOOP CLOSED — 4.11.0, verified end to end\n"
    "###############################################################\n"
    "```\n"
    "\n"
    "It's whole. The missing piece was never the checker — it was that nothing *produced* the conditions. Threads are now born checkable.\n"
    "\n"
    "**Three changes made it work.** The track's `open` field accepts objects carrying a landing condition, so the condition travels with the thread from the moment it's written. Every thread gets a **stable identity** — a normalised hash, not raw text. And I found the other half of the clearing bug: 4.10.1 fixed `fold()` and left the identical defect one layer up in synthesis, where the authoritative turn was the last with a *non-empty* list. So a turn saying \"everything landed\" contributed nothing and the old list survived.\n"
    "\n"
    "That last one is the night's lesson in miniature. **Fixing only the visible half of a defect is how it survives its own fix.**\n"
    "\n"
    "```\n"
    "  FOUR ORACLES — all green\n"
    "  [PASS]  A  landing + id survive synthesis from a track\n"
    "  [PASS]  B  reworded thread KEEPS its condition   (the 4.10.1 failure)\n"
    "  [PASS]  C  a final open:[] genuinely clears       (4.9.2 preserved)\n"
    "  [PASS]  D  other sessions' threads never erased   (4.10.1 preserved)\n"
    "\n"
    "  END-TO-END on your real digest\n"
    "  8 threads | 8 with conditions | 8 with stable ids | 0 uncheckable\n"
    "```\n"
    "\n"
    "**Why B matters most:** an hour ago I reworded threads mid-session, text matching failed silently, and six conditions detached without a sound. I proved that failure, then fixed it, then proved the fix.\n"
    "\n"
    "**What your next wakeup will actually show you** — not a claim, this is the live output:\n"
    "\n"
    "```\n"
    "  [ ] Wire the CLOSURE vector into savepoint/closeout\n"
    "        stop-savepoint-guard.sh lacks '--vector closure'\n"
    "  [ ] Ship the tools to the fleet — mywheel-only today\n"
    "        missing: basher/.../thread_landing.py\n"
    "  [ ] Build the compliance oracle\n"
    "        missing: tools/tastegraph_compliance.py\n"
    "  [ ] Merge the three commit-mine lugs before Wave 2\n"
    "        no completed lug named bug-savepoint-git-scope-...\n"
    "```\n"
    "\n"
    "Eight threads, each with a concrete machine-checked reason it hasn't landed. When you finish one, the condition flips and it clears itself. **That is the desk-clearing intention you asked for, and it is mechanical rather than asserted.**\n"
    "\n"
    "I also wrote the scar into the hook instruction: a condition must be false *now* and become true only on genuine completion, and prefer `manual` over an invented passing check. I authored three Goodhart oracles tonight inside the tool built to prevent them, so the instruction shouldn't assume future-me is more careful.\n"
    "\n"
    "```\n"
    "  [GREEN]  1203 tests pass, 2 fail (both pre-existing, verified)\n"
    "  [GREEN]  MANIFEST recut, tree clean, pushed at 4.11.0\n"
    "  [AMBER]  2 of 6 vectors wired (presentation, awareness)\n"
    "  [AMBER]  mywheel-only — the fleet has none of this\n"
    "  [AMBER]  binding still unproven without the compliance oracle\n"
    "```\n"
    "\n"
    "Those three ambers are now *threads with landing conditions*, so they'll self-report every wakeup until they're done. They can't quietly rot.\n"
    "\n"
    "Decisions for you, in order:\n"
    "\n"
    "1. **Nothing needed — this is a good stopping point.** The mechanism is whole and adversarially verified. Next session opens with a checked desk instead of a guessed one.\n"
    "2. When you want the fleet to have it, say **\"ship it to the fleet\"** — the tools and hooks must go together, and that thread will keep reminding us until they do.\n"
    "3. The 497-lug deck is untouched by your instruction and is its own campaign.\n"
    "\n"
    "**What happens automatically:** your next `/wai` runs the landing check and shows you the eight threads with their real status. Nothing to remember, nothing to invoke.\n"
    "\n"
    "Everything is committed and pushed. Savepoint holds. **Ready to exit.**\n"
    "\n"
    "Turn 17 | Sat, Jul 18, 2026 | 2:43 AM PDT | claude-opus-4-8 | Gold: +0"
)

# REGRESSION FIXTURE 2. ffc05a94-cb5b-41e3-899b-4589fcd87acd.jsonl, closing.
# The whole message is the ask — "so you can approve the batch" … "Shall I
# proceed?" — and it was reported as ending without what is waiting and on whom.
# A message whose last line is a question to the operator cannot coherently be
# accused of leaving him to deduce who is holding the work.
REAL_CLEAN_APPROVAL_REQUEST = (
    "I'm hitting permission prompts on each write — let me lay out the full plan so you can approve the batch:\n"
    "\n"
    "---\n"
    "\n"
    "## Incoming Lug Triage — 10 lugs\n"
    "\n"
    "### Route to bytype (7 lugs — no processing needed, just classification)\n"
    "\n"
    "| Lug | Destination | Notes |\n"
    "|-----|-------------|-------|\n"
    "| `impl-harness-ceremonies-idempotent-nonblocking-v1` | `bytype/implementation/open/` | P2, effort 5 — cross-ceremony idempotency |\n"
    "| `impl-mywheel-adopt-mid-session-notify-block-v1` | `bytype/implementation/open/` | P2, effort 3 — wai-inbox-notify block to master managed |\n"
    "| `impl-mywheel-adopt-wai-deploy-command-v1` | `bytype/implementation/open/` | P2, effort 3 — /wai-deploy fleet distribution |\n"
    "| `impl-recut-hub-managed-mirror-4.3.3-v1` | `bytype/implementation/open/` | P3, effort 5 — hub managed mirror recut |\n"
    "| `change-mywheel-hygiene-pebble-grooming-v1` | `bytype/change/open/` | P2 — pebble grooming step in 05-hygiene.md |\n"
    "| `direction-mywheel-run-ap-basher-harness-spine-v1` | `bytype/task/open/` | Direction lug — steer AP toward spine |\n"
    "| `feedback-autopilot-stall-teaching-authoring-v1` | `bytype/task/open/` | P3, Jun 9 — may be absorbed but can't verify; queue it |\n"
    "\n"
    "### Process and close (3 notice lugs)\n"
    "\n"
    "**8. `resp-basher-ceremony-opt-disposition-v1`** — Two decisions requested:\n"
    "- **#1 tool homes:** Confirm `managed/tools/` for `gather_teaching_status.py` + `check_track_integrity.sh` — YES, that's the right home\n"
    "- **#4 session-start self-heal:** Upstream it (agree with basher's recommendation — generally useful)\n"
    "- Action: write coord-reply lug to basher's incoming/, move notice → `bytype/notation/completed/`\n"
    "\n"
    "**9. `resp-basher-mywheel-hooks-bounce-stale-precondition-v1`** — Bounce: precondition false + live sessions.\n"
    "- Basher correctly bounced it. Tree can't quiesce this session (CSRP).\n"
    "- Action: create `impl-mywheel-reconcile-hooks-canonical-sync-v1` in `bytype/implementation/needs_attention/` (blocked: tree must quiesce first), move notice → `bytype/notation/completed/`\n"
    "\n"
    "**10. `resp-basher-notify-toast-ps1-fix-shipped-v1`** — Basher shipped canonical notify-toast fix.\n"
    "- This touches `.claude/hooks/notify.sh` + new `basher-toast.ps1`. CSRP blocks execution now.\n"
    "- Action: create `impl-mywheel-adopt-notify-toast-ps1-canon-v1` in `bytype/implementation/needs_attention/`, move notice → `bytype/notation/completed/`\n"
    "\n"
    "After routing, the 10 incoming files get removed from `incoming/` and committed with `commit-mine.sh` scoped to only the lug files.\n"
    "\n"
    "**Shall I proceed?** (All writes stay under `WAI-Harness/spoke/local/lugs/`)\n"
    "\n"
    "Turn 1 | Thu, Jun 25, 2026 | 1:33 AM PDT | claude-sonnet-4-6 | Gold: +0"
)

# REGRESSION FIXTURE 3, verbatim clause. d8313da6, blocks 147 and 160 both close
# on this construction. "Recommended session-closing action:" is the house form
# and the shipped pattern only admitted the exact strings "recommended action"
# and "recommended next", so the house form read as no action named.
REAL_RECOMMENDED_ACTION = (
    "Recommended session-closing action: **stay here and keep discussing**.")

# NOT A REPORT, mid-work. 571381c1-9b3d-4f2f-992a-e25ac4b39d8d.jsonl. The agent
# is mid-investigation and says so — "Let me check the cron schedule … before
# killing:". Grading a sentence that ends in a colon against a reporting rule
# manufactures a finding out of when the transcript was read.
REAL_NOT_A_REPORT_MIDWORK = (
    "**Major reveal:** the AP workers writing basher aren't a stray session — they're a **`conductor_cron.sh`** automated run (PID 377011→conductor.py 377021). The cron has been firing all along doing nothing (the trigger-source crash); now that I *fixed* the conductor, the cron is running a real fleet pass — which validates the fix, but it's actively writing basher mid-migration. I need to quiesce both the interactive session and this cron run. Let me check the cron schedule (re-fire risk) before killing:"
)

# NOT A REPORT, a plan. 82e1feb7-625e-44da-8b42-e7e1a9204ac6.jsonl. Ten routing
# destinations and zero claims of work reaching a state. It would be graded as
# missing all three elements if the scope gate let it through.
REAL_NOT_A_REPORT_PLAN = (
    "Basher's incoming is at `/home/mario/projects/basher/WAI-Harness/spoke/local/lugs/incoming/`. No duplicates in bytype. Now executing the full triage in one sweep.\n"
    "\n"
    "**Triage plan:**\n"
    "- 5 impl lugs → `bytype/implementation/open/`\n"
    "- `change-*hygiene-pebble*` → `bytype/change/open/`\n"
    "- `direction-*` → `bytype/task/open/`\n"
    "- `feedback-*` → `bytype/fix/open/`\n"
    "- 3 `resp-basher-*` notices → `incoming/processed/`\n"
    "- receipt → `incoming/completed/`\n"
    "- pebble seed → stays (no grooming pipeline yet)\n"
    "- create + deliver basher response for ceremony-opt confirmations"
)

# A real fenced evidence block, lifted from REAL_CLEAN_DECISIONS_FOR_YOU. On its
# own it carries three distinct delivery markers (verified / pushed / tests
# pass), which is exactly the report floor — so it is the proof that stripping
# structure before the GATE is load-bearing and not decoration.
REAL_FENCED_EVIDENCE = (
    "```\n"
    "  [GREEN]  1203 tests pass, 2 fail (both pre-existing, verified)\n"
    "  [GREEN]  MANIFEST recut, tree clean, pushed at 4.11.0\n"
    "```\n"
)

ALL_VIOLATING = [REAL_VIOLATION_CANONICAL, REAL_VIOLATION_NO_OWNER]
ALL_CLEAN = [REAL_CLEAN_EXPECTATION, REAL_CLEAN_DENIALS,
             REAL_CLEAN_DECISIONS_FOR_YOU, REAL_CLEAN_APPROVAL_REQUEST]


# --- the two required cases --------------------------------------------------

def test_the_preferences_own_example_fires():
    """The closing the preference was written about, verbatim."""
    hits = detect(REAL_VIOLATION_CANONICAL, {})
    assert len(hits) == 1
    assert missing(REAL_VIOLATION_CANONICAL) == [_AUTOMATIC, _WAITING, _NEXT]
    assert "left to deduce the next step" in hits[0]["note"]
    # The evidence is the report's TAIL — the reader needs to see where the
    # message stopped, not where it started.
    assert "bytype/notice/completed/" in hits[0]["evidence"]


def test_real_clean_closing_is_silent():
    """A closing that names all three elements. Must not fire."""
    assert detect(REAL_CLEAN_EXPECTATION, {}) == []


# --- control pairs: one clause out of real passing text ----------------------

def test_control_without_the_automatic_clause_fires():
    """Proves the AUTOMATIC element — not luck — kept the fixture silent.

    "Automatic: nothing running." is the only carrier in that whole block, so
    removing the one word is a clean single-clause mutation of real text.
    """
    mutated = REAL_CLEAN_EXPECTATION.replace(
        "Automatic: nothing running. Everything committed and pushed.",
        "Nothing running. Everything committed and pushed.")
    assert mutated != REAL_CLEAN_EXPECTATION
    assert missing(mutated) == [_AUTOMATIC]


def test_control_without_the_waiting_clause_fires():
    """Proves the WAITING element in the denial fixture.

    Both carriers ("Nothing is waiting on the harness", "One thing waits on
    you") live in one sentence, so this stays a single-clause mutation.
    """
    assert detect(REAL_CLEAN_DENIALS, {}) == []
    mutated = REAL_CLEAN_DENIALS.replace(
        "Nothing is waiting on the harness. One thing waits on you, and nothing "
        "automatic will resolve it: the oracle",
        "The oracle")
    assert mutated != REAL_CLEAN_DENIALS
    assert missing(mutated) == [_WAITING]


def test_control_without_the_next_action_clause_fires():
    """Proves the NEXT ACTION element. One carrier, one line removed."""
    mutated = REAL_CLEAN_DENIALS.replace(
        "Next session opens on: raise oracle coverage above 4.6% by adding "
        "detectors.\n\n", "")
    assert mutated != REAL_CLEAN_DENIALS
    assert missing(mutated) == [_NEXT]


def test_control_splicing_a_real_chain_into_the_canonical_violation_silences_it():
    """The inverse control, and the one that proves the finding is repairable.

    The preference's own violating closing plus the three clauses it was missing,
    each lifted verbatim from a real compliant closing. If the detector still
    fired here it would be reporting something other than the named elements.
    """
    assert len(detect(REAL_VIOLATION_CANONICAL, {})) == 1
    repaired = REAL_VIOLATION_CANONICAL + (
        "\n\nAutomatic: nothing running. Everything committed and pushed.\n\n"
        "Waiting on you: open basher, run `/wai`, and tell me what it reports.")
    assert detect(repaired, {}) == []


# --- the dead-detector guard -------------------------------------------------

def test_dead_detector_guard():
    """Fails outright if `detect` were replaced by `return []`.

    Every negative assertion in this file is satisfied by permanent silence.
    This one is not, and it is stated as its own test so that intent is on the
    record rather than implied by the positive cases.
    """
    for text in ALL_VIOLATING:
        assert detect(text, {}), "detector is silent on a proven violation"


def test_always_firing_detector_guard():
    """The opposite failure: a detector that reports every report.

    Silence and noise are the two ways a lexical detector dies, and only one of
    them is caught by the guard above.
    """
    for text in ALL_CLEAN:
        assert detect(text, {}) == []


# --- one finding, naming what it found ---------------------------------------

def test_one_finding_per_report_however_many_elements_are_missing():
    """Three missing elements are one finding, not three.

    Three findings for one loop-open closing would treble this preference's
    violation count in the ledger while adding no fact the reader did not have
    from the first.
    """
    assert len(detect(REAL_VIOLATION_CANONICAL, {})) == 1


def test_the_note_names_only_the_element_that_is_missing():
    """A real single-element violation. The note is a list, not a verdict."""
    hits = detect(REAL_VIOLATION_NO_OWNER, {})
    assert len(hits) == 1
    assert missing(REAL_VIOLATION_NO_OWNER) == [_WAITING]
    assert _AUTOMATIC not in hits[0]["note"]
    assert _NEXT not in hits[0]["note"]


def test_evidence_is_the_tail_and_carries_no_structure():
    """Evidence points at where the report stopped, in prose, on one line."""
    ev = detect(REAL_VIOLATION_NO_OWNER, {})[0]["evidence"]
    assert "deploy-verdict bug" in ev
    assert "\n" not in ev and "|---|" not in ev
    assert len(ev) <= 110


# --- the scope gate: abstain unless the block asserts work state -------------

def test_mid_work_narration_is_not_a_report():
    """Real mid-investigation text. Abstain, do not grade."""
    assert not is_report(REAL_NOT_A_REPORT_MIDWORK)
    assert detect(REAL_NOT_A_REPORT_MIDWORK, {}) == []


def test_a_plan_is_not_a_report():
    """Real triage plan: ten destinations, zero claims of work reaching state."""
    assert not is_report(REAL_NOT_A_REPORT_PLAN)
    assert detect(REAL_NOT_A_REPORT_PLAN, {}) == []


def test_control_the_report_floor_is_what_silenced_the_plan():
    """Proves the FLOOR — not the elements — kept the plan fixture quiet.

    The real plan text is unchanged; a real delivery sentence from another
    transcript is appended. Nothing about the missing chain changed, so a
    detector that stays silent here is gating on something else.
    """
    promoted = REAL_NOT_A_REPORT_PLAN + (
        "\n\nCommitted and pushed; 14 tests pass, all verified.")
    assert is_report(promoted)
    assert missing(promoted) == [_AUTOMATIC, _WAITING, _NEXT]


def test_delivery_markers_inside_a_fence_do_not_make_a_report():
    """A quoted tool dump is evidence, not the agent asserting work.

    The fenced block alone clears the three-marker floor; wrapped in a fence
    behind one line of narration it must not, or every message that pastes a
    test summary becomes gradeable as a closing.
    """
    assert is_report(REAL_FENCED_EVIDENCE.replace("```\n", "")), \
        "setup: the same lines unfenced must clear the floor"
    assert not is_report("Here is what the run printed.\n\n" + REAL_FENCED_EVIDENCE)


def test_one_marker_repeated_does_not_reach_the_floor():
    """DISTINCT markers are counted, so repetition cannot promote chatter.

    Synthetic: no real message repeats one delivery word three times with no
    other, precisely because real reports are varied. The guard is still
    load-bearing — a total-hits count would let any enthusiastic paragraph in.
    """
    assert not is_report("Pushed. Then pushed again, and pushed once more, "
                         "and I will keep pushing until it is pushed.")


def test_blockquoted_operator_words_do_not_promote_a_block():
    """Quoting the operator's own delivery vocabulary is not the agent's claim.

    Built from the operator's real words in this repo's memory
    (feedback-say-do-verified-completion), blockquoted the way ratification
    messages in these transcripts quote him.
    """
    quoted = ("Restating your rule so it is on the record.\n\n"
              "> Nothing is done until it is VERIFIED by a deterministic "
              "oracle, committed, and pushed.\n")
    assert not is_report(quoted)
    assert detect(quoted, {}) == []


# --- the three fixed detector bugs, kept as regressions ----------------------

def test_regression_decisions_for_you_names_the_owner():
    """073d8ac3: "Decisions for you, in order: 1. Nothing needed"."""
    assert detect(REAL_CLEAN_DECISIONS_FOR_YOU, {}) == []


def test_control_without_the_decisions_clause_fires():
    """The paired control for the fix above — both carriers, one region."""
    mutated = (REAL_CLEAN_DECISIONS_FOR_YOU
               .replace("Decisions for you, in order:", "In order:")
               .replace("1. **Nothing needed — this is a good stopping point.**",
                        "1. **This is a good stopping point.**"))
    assert mutated != REAL_CLEAN_DECISIONS_FOR_YOU
    assert missing(mutated) == [_WAITING]


def test_regression_an_approval_request_states_what_waits():
    """ffc05a94: a message whose last line is "Shall I proceed?"."""
    assert detect(REAL_CLEAN_APPROVAL_REQUEST, {}) == []


def test_control_without_the_approval_clauses_fires():
    """Paired control. Removing both asks also removes the named action.

    That coupling is real rather than sloppy: in this message the action and the
    thing being waited on are the same sentence, so the control asserts both go
    missing instead of pretending they can be separated.
    """
    mutated = (REAL_CLEAN_APPROVAL_REQUEST
               .replace("let me lay out the full plan so you can approve the batch:",
                        "here is the full plan:")
               .replace("**Shall I proceed?**", "**Proceeding now.**"))
    assert mutated != REAL_CLEAN_APPROVAL_REQUEST
    assert missing(mutated) == [_WAITING, _NEXT]


def test_regression_a_named_recommendation_is_a_named_action():
    """d8313da6: "Recommended session-closing action: …" is an action.

    Spliced onto the canonical violation so the assertion is about detect()'s
    verdict and not about a regex read in isolation.
    """
    spliced = REAL_VIOLATION_CANONICAL + "\n\n" + REAL_RECOMMENDED_ACTION
    assert _NEXT not in missing(spliced)
    assert missing(spliced) == [_AUTOMATIC, _WAITING]


# --- CLOSING_ONLY: the contract lives in the oracle, so test it there --------

def test_plugin_contract():
    assert PREF_ID == "communication-explicit-causal-chain"
    assert CLOSING_ONLY is True
    assert detect("", {}) == []


def test_registered_with_the_oracle():
    """The detector is worthless if `load()` cannot see it."""
    from compliance_detectors import load
    found = load()
    assert PREF_ID in found, load.errors
    fn, closing_only = found[PREF_ID]
    assert fn is detect and closing_only is True


def test_closing_only_does_not_grade_a_mid_turn_report():
    """The load-bearing half of CLOSING_ONLY, proven through `evaluate()`.

    `detect` itself has no idea where it is in a transcript — the scoping is the
    oracle's. So the only honest test of "must not fire mid-turn" runs a whole
    transcript: a firing report first, a compliant closing last. A verdict of
    `violated` here would mean every long session got marked non-compliant for a
    turn the operator was never meant to be graded on.
    """
    import tastegraph_compliance as TC
    pref = {"id": PREF_ID, "category": "communication"}
    blocks = [REAL_VIOLATION_CANONICAL, REAL_CLEAN_EXPECTATION]
    assert len(REAL_VIOLATION_CANONICAL.strip()) >= 400, "setup: must be substantial"
    assert detect(blocks[0], {}), "setup: block 0 must fire when graded alone"

    result = TC.evaluate(blocks, [pref])[PREF_ID]
    assert result["verdict"] == "compliant", result["violations"]


def test_closing_only_still_grades_the_closing():
    """The other direction, or the test above passes on a disabled detector."""
    import tastegraph_compliance as TC
    pref = {"id": PREF_ID, "category": "communication"}
    blocks = [REAL_CLEAN_EXPECTATION, REAL_VIOLATION_CANONICAL]
    result = TC.evaluate(blocks, [pref])[PREF_ID]
    assert result["verdict"] == "violated"
    assert result["violations"][0]["block"] == 1


def test_a_short_trailing_block_does_not_become_the_closing():
    """"Running the suite now." is not a report and must not be graded as one.

    `evaluate` picks the last SUBSTANTIAL block, which is what stops a live
    transcript read mid-turn from grading whatever the agent happened to say
    last. Asserted here because this detector is one of the ones that would
    manufacture a finding from it.
    """
    import tastegraph_compliance as TC
    pref = {"id": PREF_ID, "category": "communication"}
    blocks = [REAL_CLEAN_EXPECTATION, "Running the suite now."]
    assert TC.evaluate(blocks, [pref])[PREF_ID]["verdict"] == "compliant"


# --- the corpus sweep --------------------------------------------------------

_CORPUS = os.path.expanduser(
    "~/.claude/projects/-home-mario-projects-wheelwright-mywheel")


def _real_closings():
    """Every transcript's closing block, the way `evaluate` chooses it."""
    from tastegraph_compliance import load_transcript
    out = []
    for path in sorted(glob.glob(os.path.join(_CORPUS, "*.jsonl"))):
        try:
            blocks = load_transcript(path)
        except (OSError, ValueError):  # pragma: no cover - unreadable transcript
            continue
        closing = next((b for b in reversed(blocks)
                        if len(b.strip()) >= 400), None)
        if closing is not None:
            out.append((os.path.basename(path), closing))
    return out


def test_corpus_discriminates_rather_than_answering_one_way():
    """The guard that found all three bugs, kept live.

    Counts are asserted as proportions with wide margins, never as exact
    numbers: the corpus grows every session, including from the session running
    this test, so an exact count would be a test that fails on Tuesday for
    reasons that have nothing to do with the detector.
    """
    closings = _real_closings()
    if len(closings) < 20:
        pytest.skip(f"corpus not present on this machine: {_CORPUS}")

    reports = [(n, t) for n, t in closings if is_report(t)]
    assert len(reports) >= 10, "scope gate rejects nearly every real closing"

    fired = [n for n, t in reports if detect(t, {})]
    clean = [n for n, t in reports if not detect(t, {})]
    assert len(fired) >= 5, f"detector near-silent across {len(reports)} reports"
    assert len(clean) >= 5, f"detector fires on nearly every report: {len(fired)}"


def test_corpus_never_fires_on_a_block_it_declined_to_call_a_report():
    """The abstention contract holds over every real closing, not just fixtures."""
    closings = _real_closings()
    if len(closings) < 20:
        pytest.skip("corpus not present on this machine")
    for name, text in closings:
        if not is_report(text):
            assert detect(text, {}) == [], name


def test_corpus_known_verdicts_have_not_moved():
    """Named real closings, pinned by verdict.

    These are the specific blocks whose verdicts were established by reading
    them. Pinning them by name is what turns a future regex loosening from a
    silent behaviour change into a failing test.
    """
    closings = dict(_real_closings())
    if len(closings) < 20:
        pytest.skip("corpus not present on this machine")

    expected_clean = ["d8313da6-cd01-415a-a221-5fb24d75d514.jsonl",
                      "daefed6b-678c-4341-a4a2-8a5c288eccbb.jsonl",
                      "073d8ac3-93bf-42a5-9ea7-09d00c384510.jsonl",
                      "ffc05a94-cb5b-41e3-899b-4589fcd87acd.jsonl"]
    expected_violating = ["d5f2dd37-5ec1-4ca1-b794-31b1601c04db.jsonl",
                          "46c0d087-fd23-4c67-ba9f-d6fd26285a4f.jsonl"]

    for name in expected_clean:
        if name in closings:
            assert detect(closings[name], {}) == [], name
    for name in expected_violating:
        if name in closings:
            assert detect(closings[name], {}), name


# --- purity ------------------------------------------------------------------

@pytest.mark.parametrize("text", ALL_CLEAN + ALL_VIOLATING + [
    REAL_NOT_A_REPORT_MIDWORK,
    REAL_NOT_A_REPORT_PLAN,
])
def test_determinism(text):
    """Same input, same output, twice. No hidden state, no model, no clock."""
    assert detect(text, {}) == detect(text, {})
