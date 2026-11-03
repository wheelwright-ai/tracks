# build-load-warning

Policy: `canon/policies/in-session-builds-yield-to-autopilot-under-load.policy.yaml`.
Code: `src/hooks/buildLoadWarningHook.js`, `src/factory/boxHygieneReader.js`.

## Why

Operator, 2026-11-02: do not build in session when the box is loaded; prefer
autopilot, and warn when a build is asked for. Sessions ran pools and gates at
load 13-27 on 2026-11-01 with nothing putting the box state in front of them.

## What it does

On a prompt that asks for a build, if the box is loaded (verdict degrade/hold,
load1 > 0.8 x cores, swap > 75%) it injects one line with the numbers, the
standing order and the autopilot route (`hf conduct`). Otherwise nothing.
The reader is shared with `hf conduct`'s gate; a verdict file older than 15
minutes falls back to the hub box-load sample.

## What it does not do

It does not block the prompt, stop a running build, or call a provider.
