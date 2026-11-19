# Scout: worktree-count-bounded

Written by the surveyor advisor on 2026-11-19. Catches worktrees piling up beyond the three now present (main, wheel/2026-11-15-45c344, wheel/2026-11-19-f23d19), which signals stranded wake work

Re-run it with no model: `python3 .wheel/hooks/scouts.py run worktree-count-bounded --record`. A break opens a maintenance lug in the project's keep-healthy initiative when the wake re-runs it.

## Checks and the outcome each expects

- **c1** (`git worktree list`): worktree list has at most four lines. Expects {"lines": {"max": 4}}.

Severity: normal. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the expectation is out of date) have an advisor update this scout.
