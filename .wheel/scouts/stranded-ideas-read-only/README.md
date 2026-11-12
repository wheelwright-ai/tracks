# Scout: stranded-ideas-read-only

Written by the historian advisor on 2026-11-12. Protects B-006's promise that the stranded-ideas script writes nothing and runs no subprocesses.

Re-run it with no model: `python3 .wheel/hooks/scouts.py run stranded-ideas-read-only --record`. A break opens a maintenance lug in the project's keep-healthy initiative when the wake re-runs it.

## Checks and the outcome each expects

- **c1** (`grep -cE subprocess|os\.remove|shutil|os\.system tools/stranded_ideas.py`): tools/stranded_ideas.py contains no subprocess, remove, shutil or system calls (grep finds none, exit 1). Expects {"exit": 1}.

Severity: normal. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the expectation is out of date) have an advisor update this scout.
