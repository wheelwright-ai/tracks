# WAI Fork

Branch this session into separately attributable threads — one topic each.

---

## Purpose

The operator moves between topics inside a single session (`work-style-operator-multithreads-topics`).
Without forking, one session yields ONE track and ONE savepoint chain, so several topics blur into a
record no resume can attribute. Forking gives each topic its own track, savepoint chain and focus lock
while **inheriting the parent's wakeup** — that inheritance is the point, because a fork that costs a
full wakeup is just a restart with extra steps.

Forking is about ATTRIBUTION. Isolation is already handled by lanes (`worktree_guard.py`); this does
not duplicate it.

## Verbs

```bash
T=WAI-Harness/spoke/managed/tools/session_fork.py
python3 $T --base {BASE} fork --label "oracle coverage" --parent {SESSION_ID}
python3 $T --base {BASE} list --parent {SESSION_ID}
python3 $T --base {BASE} join --fork {FORK_ID} --outcome "what came of it"
python3 $T --base {BASE} active
```

## Rules

- **A fork always carries a topic label.** An unlabelled thread cannot be attributed later, which
  defeats the feature; the tool refuses one.
- **Re-forking a topic returns the existing thread.** It does not split the record a second time.
- **`join` closes the RECORD only.** It is not a git merge and not an absorption. Reconciling branches
  is a separate, explicit step in `converge_closeout.py`, behind `--confirm-absorb`.
- **An open thread is PARKED WORK, never litter.** Nothing may reclaim, absorb or reap it without the
  operator naming it (`risk-tolerance-never-absorb-a-fork-silently`). This is the defect he reported in
  s138; do not reintroduce it.
- **Punctuate before switching.** Savepoint the finished topic, then fork or switch — a savepoint is
  punctuation, not an exit (`work-style-savepoint-is-punctuation-not-exit`).

## When to fork vs. just continue

Fork when the new topic has its own resumable state worth attributing separately. Do NOT fork for a
quick question or a one-off check — a thread with two entries is noise in the list, and the list is the
surface the operator reads to find parked work.
