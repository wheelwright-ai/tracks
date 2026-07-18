# /wai-converge — CSRP lane convergence

Reconcile other live/idle session lanes' COMMITTED work into one verified tree (CSRP P6),
then report what landed and what's still gated. Run this when the launch briefing shows a
**CONVERGENCE** line, or before integrating to the shared branch.

## What it does

`converge_closeout.py` elects this session as the **lead** (lease-locked, one at a time),
detects competitor lanes, reconciles **idle** lanes' committed work, **re-verifies** the
unified tree with the test gate, and hands back. It never force-merges a **live** peer, and
the git branch merge of worktree lanes only proceeds when **the main worktree is clean and on
`main`** — otherwise it reports that as the remaining manual step (your work is never lost).

## Steps

1. Resolve context:
   - `BASE` = `WAI-Harness/spoke/local` (v4) or `WAI-Spoke` (v3) — resolve via
     `python3 WAI-Harness/spoke/managed/tools/wai_paths.py --root . --json` (see
     `wai-closeout.md` Step -1); never hardcode `WAI-Spoke/`.
   - `SID` = this session's wai-session id (the `sessions/<id>` dir name)
   - `REPO` = the main repo root (strip `/.worktrees/<name>`); `MY_WT` = this checkout
2. Preview (read-only):
   ```
   python3 WAI-Harness/spoke/managed/tools/converge_closeout.py candidates --base "$BASE" --session-id "$SID"
   ```
   Report the idle vs active competitor lanes and which hold unmerged worktree branches.
3. Converge with verification:
   ```
   python3 WAI-Harness/spoke/managed/tools/converge_closeout.py converge \
     --base "$BASE" --session-id "$SID" --repo "$REPO" --my-worktree "$MY_WT"
   ```
   **Do not pass `--test-cmd`.** WHEEL RULE (Mario, 2026-07-01): `converge_closeout.py`'s
   `_detect_test_cmd` already defaults to `bash tests/critical_paths.sh` when that gate is
   present (reference implementation: pathfinder's `tests/critical_paths.sh`, 81 real
   deterministic tests), and falls back to the harness `tests/` pytest dir when it isn't.
   Hardcoding `--test-cmd "bash tests/critical_paths.sh"` here would break convergence on
   any spoke that hasn't adopted the gate yet (bash would fail on the missing file) — let
   the shared default handle both cases honestly.
4. Report the JSON result:
   - `lead` / `verify.status` (must be green)
   - `absorbed_laneonly` (idle lanes reconciled at the lane/state level)
   - `converged[].merge` — for each worktree lane, whether the git merge succeeded or was
     **blocked** (`"the main worktree must be clean and on main"`). If blocked, state the
     remaining manual step: clean + checkout `main` in the main worktree, then re-run, OR
     defer to a deliberate integration/PR.
   - if `verify.status` is `RED` and the spoke HAS `tests/critical_paths.sh`: this is a
     **HARD BLOCK** (WHEEL RULE) — the merge-lock is retained for fix-forward, per
     `converge_closeout.py`'s `lead_must_fix`. Do not force a merge past it.

## Guardrails

- Never blind-merge a **live** peer lane (it's still changing those files).
- The git merge is operator-gated (clean main worktree on `main`); surfacing the blocker is
  correct behavior, not a failure.
- Fail-safe: the merge lease auto-expires, so a crashed lead never deadlocks the fleet.
- Never re-add `--test-cmd "bash tests/critical_paths.sh"` here — that hardcoding is exactly
  the bug the wheel rule fixed (impl-wheel-critical-paths-gate-rule-20260701). The default
  lives in `converge_closeout.py._detect_test_cmd`, not in this skill.
