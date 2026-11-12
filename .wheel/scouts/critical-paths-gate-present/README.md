# Scout: critical-paths-gate-present

Written by the health advisor on 2026-11-12. The closeout gate file must not be deleted or emptied, since a missing gate would let closeout skip the critical-path check

Re-run it with no model: `python3 .wheel/hooks/scouts.py run critical-paths-gate-present --record`. A break opens a maintenance lug in the project's keep-healthy initiative when the wake re-runs it.

## Checks and the outcome each expects

- **c1** (file `tests/critical_paths.sh`): critical_paths.sh exists and still carries its gate header. Expects {"contains": "CRITICAL-PATHS", "exists": true, "min_bytes": 200}.

Severity: normal. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the expectation is out of date) have an advisor update this scout.
