# agent-tool-scope-guard

260901-FBL-072 ruling 3, re-ruled 260902-FBL-084 item 3: "Agent-tool
forks are platform infrastructure outside the env gating -- the wheel does
not use them for scoped work: research-only and write-within-paths
dispatch goes through the wheel's own headless path (providerContract /
wcl), where scope is enforceable. The Agent tool is permitted only for
full-scope work on the parent's own thread, and every such use is a ledger
row naming the fork's purpose."

## Why this exists

An Agent-tool fork's real tool access is not narrowed by prose in its own
prompt -- "research only, do not write files" is a claim, not an
enforcement mechanism. The wheel's own headless path (`providerContract` /
`wcl`) is scope-aware and can genuinely restrict a dispatched process.

## What it is, honestly

A prompt/description heuristic, not a parser -- same discipline every
other bash-\*-guard circle documents. It checks the call's own
`description` and `prompt` for restricted-scope language: "research only,"
"read-only," "don't write," "write only within \<paths\>," "never
modify/edit," and near variants. A match denies the call, redirecting to
the enforceable alternative. No match is an honest, full-scope dispatch --
the only use the ruling permits -- and is logged as a real ledger row
(`row_kind: decision`) naming the fork's purpose.

## The second check: declaration, then write (fbl-065-followup)

Matching the dispatch is not enough. 260902-FBL-085 disclosed a real fork
writing `wheel-hub/ledger/ledger.jsonl` despite its own prompt saying "Do
NOT write anything": a PreToolUse match on the *dispatch* cannot stop the
sub-agent from reaching a write tool later in its own turn.

So the same hook also matches `Write|Edit|NotebookEdit|Bash`. At dispatch
it records what the call declared (`src/lugTracking/scopeDeclarations.js`,
`runtime/scope-declarations.jsonl`) before the fork exists, so a fork can
never author, widen or clear what binds it. At a fork's write it looks that
up and refuses -- phrase quoted verbatim, the **parent** told in band
(`systemMessage`), a permanent ledger row appended. A fork later
self-correcting or reporting success (FBL-085's own did) cannot clear it.

Two tiers, one canon file (`canon/scope-declaration-phrases.yaml`), both
retunable by a future lug without touching hook logic:

- `redirect_phrases` -- narrow; a match refuses the dispatch outright, so
  a false positive costs a blocked dispatch.
- `declaration_phrases` -- broad ("audit only," an opening "Analyze...,"
  "just check..."), read as the union of both lists. A match blocks
  nothing at dispatch; that fork just hands its writes back to the parent.

Tying a fork to its dispatch is a correlation, not an identity, and is
measured: across 2058 real captured fork tool calls and 12 real dispatch
calls, the dispatch carries `session_id` + `prompt_id` and no `agent_id`;
the fork's calls carry the same two plus `agent_id`/`agent_type`; and
`agent_id` never equals the dispatch's `tool_use_id`. Key: (`session_id`,
`prompt_id`), falling back to `agent_type`. Two forks of one type in one
turn, one restricted and one not, are indistinguishable, and the
restrictive one binds both.

## Known, accepted gaps

Same class of gap every heuristic guard here accepts: indirect phrasing
("keep changes minimal") can evade the pattern. It catches the direct,
common claimed-restriction phrasing, not every way of asking an agent to
behave narrowly in prose.

Second check: the correlation limit above is real; the Bash write-shape
test is `dispatchScope.writeTargetsForTool`'s heuristic, so a write hidden
inside `node -e` or a called script is not caught; and a fork dispatched
with no declaration is untouched by design -- the ruling's own definition
of an honest Agent-tool use, where `agent-target-scope-guard` takes over.
