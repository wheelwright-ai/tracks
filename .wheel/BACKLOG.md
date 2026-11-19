# Lugs

Force-ranked, one unique rank per open lug. Generated from .wheel/backlog.jsonl by backlog.py render; do not edit by hand. The roadmap (goal, initiative, lugs, history) is in .wheel/ROADMAP.md.

| rank | id | title | kind | status | value/effort | initiative |
|---:|---|---|---|---|---|---|
| 1 | B-015 | Tracks MCP server (stdio, Python stdlib only) with a validate_track tool | autopilot | proposed | 5/3 | - |
| 2 | B-018 | Owner decision: the shape of the claude.ai connector (hosted remote MCP or local only), and whether the keepalive and db-schema leftovers stay | owner | proposed | 4/1 | - |
| 3 | B-016 | MCP server serves the format itself: get_spec, get_prompt and track_open_items tools | autopilot | proposed | 4/2 | - |
| 4 | B-009 | Triage the uncommitted file in the main checkout that has been open since 2026-11-11 | owner | blocked | 3/1 | I-004 |
| 5 | B-019 | Remove the GitNexus block (<!-- gitnexus:start --> to <!-- gitnexus:end -->) from CLAUDE.md and AGENTS.md | autopilot | blocked | 3/2 | I-001 |
| 6 | B-020 | Scout worktree-no-uncommitted broke: git status shows no changed or untracked files | owner | blocked | 3/2 | I-004 |
| 7 | B-021 | Land ac69187 on main: untrack and gitignore scout status.json files | autopilot | blocked | 2/2 | I-004 |

## Recently done

- B-022 Have the overwatch run tests/run_all.sh so the test line stops reading 'none' (2026-11-19)
- B-017 Stop scout runs from dirtying the tree: untrack and gitignore .wheel/scouts/*/status.json (2026-11-15)
- B-014 Scout worktree-no-uncommitted broke: git status shows no changed or untracked files (2026-11-13)
- B-013 Scout critical-paths-stays-red-until-real broke: the stub still exits 1 and says it is not implemented (2026-11-13)
- B-011 Replace the red tests/critical_paths.sh stub with real deterministic tests over the viewer, track validator an (2026-11-12)
- B-012 Add one runner that executes every tests/ check and exits non-zero on any failure (2026-11-12)
- B-008 Scout worktree-no-uncommitted broke: git status shows no changed or untracked files (2026-11-12)
- B-010 Decide the fate of .claude/.deploy-quarantine/hooks (9 hook files, not gitignored) (2026-11-12)
- B-006 Find stranded ideas in old tracks and offer them as backlog candidates (2026-11-09)
- B-005 A new session in a project opens from the last session's track (2026-11-09)
