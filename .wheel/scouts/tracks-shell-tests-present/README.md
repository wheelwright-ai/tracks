# Scout: tracks-shell-tests-present

Written by the historian advisor on 2026-11-12. Protects the shell test scripts behind the goal-1 format checks (B-003, B-007) and the wake and stranded-ideas checks (B-005, B-006).

Re-run it with no model: `python3 .wheel/hooks/scouts.py run tracks-shell-tests-present --record`. A break opens a maintenance lug in the project's keep-healthy initiative when the wake re-runs it.

## Checks and the outcome each expects

- **c1** (file `tests/validate_samples.sh`): validate_samples.sh exists, has an exit 1 path, and is not a stub. Expects {"contains": "exit 1", "exists": true, "min_bytes": 50}.
- **c2** (file `tests/validate_rules.sh`): validate_rules.sh exists and is not a stub. Expects {"exists": true, "min_bytes": 50}.
- **c3** (file `tests/wake_from_track.sh`): wake_from_track.sh exists. Expects {"exists": true}.
- **c4** (file `tests/stranded_ideas.sh`): stranded_ideas.sh exists. Expects {"exists": true}.

Severity: normal. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the expectation is out of date) have an advisor update this scout.
