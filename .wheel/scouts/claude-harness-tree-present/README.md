# Scout: claude-harness-tree-present

Written by the surveyor advisor on 2026-11-12. Protects the .claude harness config and command manifest that the advisors and wake read

Re-run it with no model: `python3 .wheel/hooks/scouts.py run claude-harness-tree-present --record`. A break opens a maintenance lug in the project's keep-healthy initiative when the wake re-runs it.

## Checks and the outcome each expects

- **c1** (file `.claude/settings.json`): Harness settings file exists. Expects {"exists": true}.
- **c2** (file `.claude/commands/manifest.json`): Command manifest exists and is non-empty. Expects {"exists": true, "min_bytes": 1}.

Severity: normal. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the expectation is out of date) have an advisor update this scout.
