# hf-deploy

Lug: `max-deploys-updates-through-its-fleet-fold-push-cut-relaunch-as-one-verb`
(wheel-hub). Operator, 260911 21:30, verbatim: "Make it so Max can deploy
updates via its fleet of agents." Full build record and measurements:
`docs/hf-deploy.md` in harness-factory.

## Why a verb

On 260911 the orchestrator deployed by hand eleven times: fold each landed
dispatch/* branch onto main, push through the 6.5-minute pooled gate with
ssh keepalives, apply the cut to wheel-hub, basher and minder, regenerate
docs, relaunch what wcl had refused as stale, clean worktrees. None of it
was a verb, so the non-authoring session spent its turns on git plumbing,
and a restart lost the ordering.

## The verb

```
hf deploy [--spokes=a,b] [--stage=fold,push,cut,relaunch,clean]
          [--root=<hub>] [--framework-root=<harness-factory>] [--fresh] [--status]
```

Stages run in that order; the run stops at the first stage that is not
`completed` and the next bare `hf deploy` resumes there. `--stage` runs
exactly the named stages inside the open run. `--status` prints the open
run, its lock and the last five stage rows.

| stage    | does                                                                  | refuses when                                          |
|----------|-----------------------------------------------------------------------|-------------------------------------------------------|
| fold     | cherry-pick review/done dispatch/* branches on an integrate worktree, ff main | conflict (branch named), main will not fast-forward |
| push     | harness-factory then each spoke, own pre-push gate, keepalive ssh     | gate red (quoted), behind origin, timeout             |
| cut      | applyCut per registered spoke, commit cut-owned paths, `wcl --dry-run` | applyCut failure, spoke pre-commit gate red          |
| relaunch | re-queue dispatches refused for "spoke is stale"                      | queueDispatch throws                                  |
| clean    | remove worktree + branch of fully folded branches                     | git refuses the removal                               |

A hold (upgrade posture, active session without live-apply, unclassifiable
arrival) is recorded per spoke and the stage still completes: it is a real
reason, not a failure, and the operator reads it in the record.

## Records

- `<hub>/runtime/deploy-runs.jsonl`: `deploy_run_stage` rows (started, then
  terminal with `per_spoke` / `branches` / `dispatches`), `deploy_run_closed`.
- `<hub>/ledger/ledger.jsonl`: one `decision` row per stage, `source_type: deploy`.
- `<hub>/runtime/deploy.lock`: pid + run id while a deploy runs; a dead pid is stale.

## The wheel-clock job

`deploy_fleet` (canon/otto.advisor.yaml, every 6 ticks) -> `deployFleet` ->
`runScheduledDeploy`. Declines by name on: stop flag, a running or
half-finished deploy, framework not on main, dirty tracked tree, nothing
foldable and main == origin, main not proven green (no pre-push proof for
this tree and no zero-red oracle sweep at this sha). Otherwise launches
`hf deploy --stage=fold,push,cut` detached, log at `runtime/deploy-runs.log`.

## Boundaries

Never `WHEEL_SKIP_TEST_GATE` (scrubbed from git's env), never `--no-verify`,
never `--force`, never a rewrite of origin. Never a code edit: conflicts and
red gates come back as words.
