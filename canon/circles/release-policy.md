# release-policy

lug `exit-asks-the-operator-to-release-under-a-per-spoke-release-policy`.
Release to origin is the operator's deliberate choice, per spoke. The spoke
declares its policy in `canon/policies/release.policy.yaml`:

```yaml
release_policy: ask            # or push_every_exit
smoke_suites:                  # repo-relative test files; the spoke maintains it
  - conformance/runner/run.js
```

## Under `ask`

`node scripts/closeout.js` prints, when the home spoke is ahead of
`origin/main`:

```
RELEASE <spoke>: N commit(s) ahead of origin/main, policy ask -- release now? smoke / full / not now
        smoke:   node scripts/release.js '<root>' --level=smoke
        full:    node scripts/release.js '<root>' --level=full
        not now: node scripts/release.js '<root>' --level=not-now
```

- **smoke** runs exactly `smoke_suites`; all green folds the session branch
  into main (fast-forward only) and pushes with `WHEEL_SKIP_TEST_GATE`
  naming the policy, level, smoke counts and sha. An empty list is refused.
- **full** folds the same way and pushes plainly: the pre-push full gate runs.
- **not now** pushes nothing and records the choice.

## Under `push_every_exit`

The SessionEnd exit commit, once it lands, launches
`scripts/release.js <root> --level=exit-push` detached. It folds and pushes
with the bypass reason `push_every_exit policy: dev-time tests only`. No
suite is run at exit. The closeout line says exit will push.

## Ledger

Every outcome writes one `row_kind: release` row with a `release` field:
`{policy, level, suite: {result, ran, passed, failed, timed_out,
not_reached}, pushed, sha, reason}`.

A smoke release reaches origin only. A framework cut still needs a full green
run (hf deploy's cut stage).
