# ready-gate-stub

Split out from `readiness-gate` on ruling 2026-08-26. Design doc section 7:
a lug becomes `ready` when a fresh-context agent has actually checked it --
the stranger test. That agent-invocation path doesn't exist yet; it's
increment 7 work, once the Proofer's agent-invocation path exists.

Building nothing here and just letting lugs pass into `ready` unchecked was
the wrong call -- it's exactly the kind of thing that looks done and isn't,
the failure mode this whole design exists to remove. So instead: this
circle is the honest stand-in.

## What it does

- A proposed transition to `ready` is **denied** unless the lug's
  `readiness` field is exactly `stubbed`. Writing `readiness: passed`
  through this path is refused outright -- nothing in this build can make
  that claim honestly yet.
- Every transition that does go through (`readiness: stubbed`) still writes
  an unconditional ledger row saying so: which lug, that it was a stub, and
  that no fresh-context check ran. There is no code path that reaches
  `ready` without a visible trace that it wasn't really checked.

## What replaces it

Increment 7 supplies the real fresh-context check. When it does, this
circle's *contract* (trigger, consumers, failure_routing) doesn't need to
change -- only `src/hooks/readyGateStubHook.js`'s body does, the same way
`definition-complete-gate`'s mechanical check was always built to be
upgradable without changing its contract.
