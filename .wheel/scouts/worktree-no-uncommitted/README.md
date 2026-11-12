# Scout: worktree-no-uncommitted

Written by the expediter advisor on 2026-11-12. Catches work left uncommitted in the spoke worktree, the condition overwatch flagged for 34h

Re-run it with no model: `python3 .wheel/hooks/scouts.py run worktree-no-uncommitted --record`. A break opens a maintenance lug in the project's keep-healthy initiative when the wake re-runs it.

## Checks and the outcome each expects

- **c1** (`git status --porcelain`): git status shows no changed or untracked files. Expects {"lines": {"max": 0}}.

Severity: normal. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the expectation is out of date) have an advisor update this scout.
