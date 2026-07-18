# WAI Deploy — Harness + Tools Fleet Deploy (basher-only)

Deploy a harness update (ALWAYS paired with the tools/config layer) to the wheel/fleet.

This command **only executes from the basher spoke** — basher is the deploy source and
owner of the harness+tools distribution. Invoked from any other spoke, it does NOT
deploy: it routes a deploy-request lug to basher and stops.

---

## Step 0 — Spoke gate (MANDATORY FIRST — do this before anything else)

Determine whether the current repo is **basher**. basher is the repo whose root holds the
deploy machinery:

```bash
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
if [[ -f "$ROOT/bin/basher" && -f "$ROOT/scripts/sync.sh" && -f "$ROOT/scripts/tools.sh" && -f "$ROOT/toolbox.json" ]]; then
  echo "BASHER"
else
  echo "NOT_BASHER"
fi
```

- **If `NOT_BASHER`** → DO NOT run any deploy step. Instead **route a deploy request to basher**:
  1. Resolve basher's incoming. Read the hub registry (`wheel.hub_path` in this spoke's
     `WAI-Harness/spoke/local/WAI-State.json`, else
     `/home/mario/projects/wheelwright/mywheel/WAI-Harness/hub/local/hub-registry.json`),
     find the wheel with `wheel_id == "basher"`, take its `path`, and target
     `<path>/WAI-Harness/spoke/local/lugs/incoming/`.
  2. Compose a complete lug (use `json.dumps` — never bash string-building for JSON):
     ```json
     {
       "id": "directive-basher-deploy-fleet-<YYYYMMDD-HHMM>-v1",
       "type": "directive",
       "status": "open",
       "priority": "P2",
       "routed_to": "SPOKE/basher",
       "destination_wheel_id": "basher",
       "from": "<this spoke wheel_id>",
       "source_wheel_id": "<this spoke wheel_id>",
       "model": "opus",
       "model_rationale": "Fleet deploy is a multi-spoke, CSRP-sensitive operation requiring judgment.",
       "effort_score": 6,
       "impact": 7,
       "title": "Deploy harness + tools update to the fleet",
       "perceive": "<what update / why — fill from the operator's request>",
       "execute": ["Run /wai-deploy from basher (the runbook below)."],
       "verify": "Every target spoke green on the deploy-relevant checks (harness version, hooks executable, A5, paired tool config).",
       "acceptance_criteria": ["Target active spokes deployed paired at the target harness version", "Final verify sweep green"],
       "target_files": ["(fleet — per-spoke harness + tool config)"],
       "origin": "/wai-deploy invoked from <this spoke> (non-basher) — routed to basher",
       "created_at": "<iso8601>",
       "delivered_at": "<iso8601>"
     }
     ```
  3. Write a copy to this spoke's `WAI-Harness/spoke/local/lugs/outgoing/` AND deliver
     (cp) to basher's incoming. Run the pre-delivery checklist (PEV non-empty,
     `destination_wheel_id` resolvable, acceptance_criteria non-empty, effort+model present).
  4. Tell the operator: *"Deploy must run from basher — routed a request lug to basher (`<id>`). basher's next session will execute it."* Then **STOP** — do not deploy.

- **If `BASHER`** → proceed to Step 1.

---

## The deploy runbook (basher only)

A harness deploy ALWAYS includes the tools/config layer — **paired**, never harness-only.
The mechanism is basher's own sync engine: `sync_main --spoke <path>` (one spoke) or
`basher tools fleet` (= `sync_main --fleet`) for all. Canon source is the mywheel master
(`spoke/managed`); spokes pull from it. `basher tools fleet --dry-run` is the safe preview.

### Step 1 — CSRP reconcile
Survey lanes (`python3 WAI-Harness/spoke/managed/tools/worktree_guard.py lanes --base WAI-Harness/spoke/local`).
Absorb peers' **committed** work into the target branch. Never `git add -A` / blind git on a
shared tree; scope every commit to your own paths.

### Step 2 — Target set
Active registry spokes MINUS {`basher` (source), `mywheel` (master), `wheelwright-framework` +
`wheelwright-hub` (deprecated), anything already done}. Resolve from the hub registry
(`status == "active"`, path exists). Typically ~19–20 of the ~32.

### Step 3 — READ-ONLY VERIFY SWEEP FIRST (do not skip)
For each target: `EXPECT_VERSION=<ver> bash scripts/verify_update.sh <spoke_path>`. Collect the
**deploy-relevant** checks: harness version, hooks executable, A5 (no v3 phantom), paired tool
config. This finds the real gap set without touching anything — the fleet is often already
mostly current, so this turns "roll 20" into "remediate the few that drifted."

### Step 4 — Gate on the deploy-relevant subset, NOT literal "7/7"
verify_update's `track generation` + `wakeup brief` checks are **session-runtime** — they
cannot pass for an idle spoke (no live session/track), so a literal 7/7 gate falsely halts
every idle spoke. Pass = the 4 deploy-relevant checks green.

### Step 5 — Remediate ONLY the gaps — scoped commits only (CSRP)
Confirm no live lane on a target before committing in it (Step 1 lanes). Then per gap:
- **harness stale / tool config missing** → paired `sync_main --spoke <path>`
  (`source scripts/sync.sh && sync_main --spoke <path>` = restore --live-hooks + tools update).
- **hooks tracked 100644** (worktrees Permission-deny; on-disk +x is NOT enough — the git index
  mode must be 100755) → `git -C <spoke> add --chmod=+x -- .claude/hooks/*.sh .claude/hooks/*.py`
  then commit **scoped to `.claude/hooks` only**.
- **settings.json missing** → `sync_main --spoke` now CREATES it (cc_advisor); commit the single
  file scoped.
- Never sweep a spoke's larger uncommitted pull — commit only your scoped paths; leave the rest
  for that spoke's own session.

### Step 6 — Final verify sweep + report
Re-sweep all targets; confirm every one green on the 4 deploy-relevant checks. Report the
green count, what was remediated, and any spoke left for its own session. Deliver any
follow-up lugs (e.g. KPI progress to mywheel) per the operator's directive.

---

## Notes
- Mechanism details + the gotchas this runbook prevents (fleet `--dry-run` once ran live; the
  shared `wai-enter.sh` launcher crashing on a concurrent mid-run edit; the tools layer never
  creating `settings.json` for a bare spoke) are fixed in-repo with tests in `tests/run.sh`.
- The mywheel hub/managed **mirror** being stale does NOT affect the fleet — spokes pull the
  `spoke/managed` master, not the hub mirror.
