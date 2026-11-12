# Scout: gitignore-keeps-spoke-out

Written by the surveyor advisor on 2026-11-12. Protects the rule that keeps the local WAI-Spoke folder out of git

Re-run it with no model: `python3 .wheel/hooks/scouts.py run gitignore-keeps-spoke-out --record`. A break opens a maintenance lug in the project's keep-healthy initiative when the wake re-runs it.

## Checks and the outcome each expects

- **c1** (file `.gitignore`): .gitignore still lists WAI-Spoke/. Expects {"contains": "WAI-Spoke/", "exists": true}.

Severity: normal. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the expectation is out of date) have an advisor update this scout.
