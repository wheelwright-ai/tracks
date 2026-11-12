# Scout: dev-launcher-present

Written by the health advisor on 2026-11-12. The dev launcher and its server must stay in place so the viewer can be started

Re-run it with no model: `python3 .wheel/hooks/scouts.py run dev-launcher-present --record`. A break opens a maintenance lug in the project's keep-healthy initiative when the wake re-runs it.

## Checks and the outcome each expects

- **c1** (file `dev`): dev launcher exists. Expects {"contains": "serve.py", "exists": true, "min_bytes": 100}.
- **c2** (file `serve.py`): serve.py exists. Expects {"exists": true, "min_bytes": 200}.

Severity: normal. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the expectation is out of date) have an advisor update this scout.
