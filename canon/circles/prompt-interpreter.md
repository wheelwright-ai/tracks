# prompt-interpreter

Code: `src/hooks/promptInterpreterHook.js`, `src/hooks/lib/promptInterpreter.js`,
`canon/prompt-interpreter.yaml`. Lug:
`every-prompt-gets-a-shadow-interpretation-for-three-days`.

## Why

Operator 2026-11-02: "this is how you help me optimally communicate with
you." Six UserPromptSubmit bodies each match the prompt on their own. This
one reads each prompt once into an interpretation -- intent, the actions that
would help, their class and risk, what is missing -- so the operator can later
see "I read this as ...". Shadow first, three days.

## What a row holds

`runtime/prompt-interpretations.jsonl`, one row per prompt: `ts`,
`session_id`, `mode`, `status` (ok | error), `intent` (status, question,
build, ship, proceed, answer, closeout, review, direction, other), `actions`
(`verb`, `class`, `risk`), `effectful`, `missing`, `enhancement_score`
(referents + requirements + paste + action verb, minus specificity),
`normalized` (typo map from canon), `reading`, `duration_ms`.

## Shadow

The hook injects nothing and exits 0 on every path. The window is canon:
`shadow_days` from the first row; `readShadowWindow(instanceRoot)` returns
`shadow_until` for the scorer. No provider call, rules only, under 100 ms.
