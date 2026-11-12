# Scout: critical-paths-stays-red-until-real

Written by the expediter advisor on 2026-11-12. Stops the critical-paths gate being flipped to a fake pass before real tests exist

Re-run it with no model: `python3 .wheel/hooks/scouts.py run critical-paths-stays-red-until-real --record`. A break opens a maintenance lug in the project's keep-healthy initiative when the wake re-runs it.

## Checks and the outcome each expects

- **c1** (file `tests/critical_paths.sh`): the stub still exits 1 and says it is not implemented. Expects {"contains": "exit 1"}.

Severity: blocker. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the expectation is out of date) have an advisor update this scout.
