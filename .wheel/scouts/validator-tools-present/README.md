# Scout: validator-tools-present

Written by the health advisor on 2026-11-12. Track validator and its sample/rule tests must stay present, since they are the only checks the repo has

Re-run it with no model: `python3 .wheel/hooks/scouts.py run validator-tools-present --record`. A break opens a maintenance lug in the project's keep-healthy initiative when the wake re-runs it.

## Checks and the outcome each expects

- **c1** (file `tools/validate_track.py`): track validator exists. Expects {"exists": true, "min_bytes": 100}.
- **c2** (file `tests/validate_samples.sh`): sample validation test exists. Expects {"exists": true, "min_bytes": 20}.

Severity: normal. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the expectation is out of date) have an advisor update this scout.
