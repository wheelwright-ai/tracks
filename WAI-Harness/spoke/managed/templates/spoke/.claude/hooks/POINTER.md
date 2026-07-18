# Hooks live at the managed canonical, not here

This directory used to carry its own hand-maintained copy of the active
`.claude/hooks/*` files. It drifted (`session-start.sh` was stuck at
`db4e662f...` while the real canonical had moved on to `8673478d...`), and
nothing ever re-synced it — a classic three-copies-of-the-truth bug
(F8 of `plan-wheel-integrity-v1`, closed by
`impl-integrity-w4-active-hooks-redeploy-v1`).

**The one canonical hook source is now:**

```
WAI-Harness/spoke/managed/.claude/hooks/
```

- `harness_init.py` deploys a brand-new spoke's active `.claude/hooks/` from
  that directory (`_deploy_hooks_from_managed`), not from here.
- `harness_upgrade.py`'s `pull()` re-deploys active hooks from that same
  directory on every pull (`_deploy_active_hooks`), so a canon hook fix
  reaches every spoke's LIVE hooks automatically — not just its `managed/`
  mirror.
- `verify_foundation.py --repair` copies canon over stale/missing active
  hooks for spokes that fell behind anyway.

If you're looking for the hook files themselves, go to
`WAI-Harness/spoke/managed/.claude/hooks/`. Nothing should ever be added
back under this `templates/spoke/.claude/hooks/` directory — edit the
managed canonical instead.
