# Sawyer

Judge raw ideas, then check whether what was agreed ever landed.

## What It Does

Sawyer is the consideration advisor. It takes conversations, articles, and idea dumps,
decides what is worth doing, and then **comes back to verify that the agreed work
actually happened and still works.**

That second loop is the point. This spoke's documented failure mode is
built-but-never-wired: work deployed, reported done, never in service.

## Use It When

- The operator pastes a conversation, article, or argument and wants it evaluated
- A batch of ideas needs adopt / reject decisions on the record
- You need to know whether previously agreed behaviours are actually live
- The same idea keeps resurfacing and you want the prior verdict, not a fresh debate

## The Flow

    S=WAI-Harness/spoke/managed/tools/sawyer.py

    python3 $S intake notes/conversation.md     # split + dedup -> C-20260817-001
    python3 $S brief C-20260817-001             # evidence brief for a cheap model
    # run the brief on kimi-k3 (stage 1, evidence only), read it, then decide:
    python3 $S decide C-20260817-001 --item 3 --verdict adopt \
        --why "<one line>" --landing-check "<command that exits 0 when live>"

    python3 $S land        # LANDED / HOLDING / NOT_LANDED / REGRESSED
    python3 $S status      # counts, oldest NOT_LANDED, seasonings due

## Two Rules

1. **`adopt` and `adapt` are REFUSED without `--landing-check`.** An agreed behaviour
   with no way to prove it landed is how the debt accumulated.
2. **Nothing sits undecided.** Every item ends adopt / adapt / reject / season /
   already_decided. Limbo items get re-reviewed forever.

## Reading `land`

|  | check passes | check fails |
|---|---|---|
| never landed | LANDED | **NOT_LANDED** — agreed, never built |
| landed before | HOLDING | **REGRESSED** — worked, then rotted |

Exits non-zero on any REGRESSED, or any NOT_LANDED older than 14 days.
NOT_LANDED and REGRESSED need different responses — never collapse them.

## Two-Stage Routing

Stage 1 evidence goes to a cheap model (kimi-k3): *does this exist, where, what breaks.*
Stage 2 verdicts stay with the operator and a frontier model. Evidence is cheap and
checkable; judgment is what you are paying for.

## Full Reference

`WAI-Harness/spoke/local/advisors/sawyer/IDENTITY.md`
