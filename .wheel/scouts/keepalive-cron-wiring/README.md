# Scout: keepalive-cron-wiring

Written by the health advisor on 2026-11-12. The keepalive cron must keep pointing at the api route that exists, or the database keepalive silently stops

Re-run it with no model: `python3 .wheel/hooks/scouts.py run keepalive-cron-wiring --record`. A break opens a maintenance lug in the project's keep-healthy initiative when the wake re-runs it.

## Checks and the outcome each expects

- **c1** (file `tools/vercel-db-keepalive/vercel.json`): vercel.json still schedules /api/keepalive. Expects {"contains": "/api/keepalive", "exists": true}.
- **c2** (file `tools/vercel-db-keepalive/api/keepalive.js`): the keepalive api handler exists. Expects {"exists": true, "min_bytes": 20}.

Severity: normal. If a check breaks, read its line above, confirm it by hand, then fix the project or (if the expectation is out of date) have an advisor update this scout.
