# Scout: repo-pack-size-bounded

Written by the surveyor advisor on 2026-11-19. Catches the object store growing toward 100 MiB, a negative indicator of repository growth (today 8.45 MiB packed)

Re-run it with no model: `python3 .wheel/hooks/scouts.py run repo-pack-size-bounded --record`. A break opens a maintenance lug in the project's keep-healthy initiative when the wake re-runs it.

## Checks and the outcome each expects

- **c1** (`git count-objects -vH`): packed object size stays under 100 MiB. Expects {"number": {"max": 100, "regex": "size-pack: ([0-9.]+) MiB"}}.

Severity: normal. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the expectation is out of date) have an advisor update this scout.
