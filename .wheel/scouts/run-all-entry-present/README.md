# Scout: run-all-entry-present

Written by the health advisor on 2026-11-19. Keeps the one-runner test entry point (B-012) in place for the overwatch and closeout gate to find

Re-run it with no model: `python3 .wheel/hooks/scouts.py run run-all-entry-present --record`. A break opens a maintenance lug in the project's keep-healthy initiative when the wake re-runs it.

## Checks and the outcome each expects

- **c1** (file `tests/run_all.sh`): tests/run_all.sh exists and is a real runner. Expects {"contains": "ALL PASS", "exists": true, "min_bytes": 400}.
- **c2** (file `tests/run_all.sh`): the runner still lists the viewer_drop check. Expects {"contains": "viewer_drop.py"}.

Severity: normal. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the expectation is out of date) have an advisor update this scout.
