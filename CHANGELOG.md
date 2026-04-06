# Changelog

## [0.1.1] — 2026-04-06

### Changed
- Updated all three prompt variants to **WAI Track v0.24** schema
  - `active-collection.md`: full live-ledger protocol with RUNTIME CONTRACT, proof block, per-turn meta capture, `artifact_manifest`, `provenance_manifest`, `state_snapshot`, codename generation, `exchange` record type with `user.raw`/`assistant.raw`
  - `prep-and-request.md`: passive-tracking variant — ledger deferred to export trigger, all records `capture_mode="reconstructed"`, simplified activation greeting
  - `closing-request.md`: retroactive-extraction variant — executes immediately on paste, no activation/collaboration sections, all records `reconstructed`
- All variants gain: `SESSION METADATA RULES`, per-turn meta fields (`awareness_items`, `identified_todos`, `candidate_ideas`, `open_loops`), v0.24 filename format with session codename, package summary block

### Infrastructure
- `pre-compact.sh`: now writes `compacted: true` to session guard before context compaction
- `user-prompt-submit.sh`: detects `compacted` flag on next prompt, injects one-shot `<wai-post-compact>` block, clears flag

### Notes
- Breaking change: v0.24 exchange records use a different schema than pre-v0.24 prompts
- Prompt files contain no personal identifiers — safe for public distribution

## [0.1.0] — 2026-03-17

### Added
- Initial release
- `spec/track-format.md` — WAI Point schema, phases, file naming, continuity rules
- `prompts/closing-request.md` — retroactive extraction from any existing chat
- `prompts/prep-and-request.md` — prime agent at start, generate on demand
- `prompts/active-collection.md` — per-turn recording, WAI-native approach
- `samples/coding-session.jsonl` — JWT auth refactor, 10 points
- `samples/strategy-session.jsonl` — GTM positioning, 10 points
- `samples/learning-session.jsonl` — Raft consensus, 10 points
- `README.md` — portability manifesto, use cases, Wheelwright funnel
- MIT license
