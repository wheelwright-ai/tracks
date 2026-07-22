# Wheelwright Harness — Adopt/Init Flow

Stand up the Wheelwright harness on a new or existing repository.

---

## Overview

The harness is a general AI session-continuity layer for any codebase. It provides:
- Session tracking (WAI-Harness/spoke/sessions/)
- Work queue (lugs/bytype/)
- Teaching distribution from hub
- Agent behavior contracts (CLAUDE.md + hooks)

Adoption takes under 5 minutes for an existing repo.

---

## Prerequisites

- Wheelwright framework cloned at a known path (needed for templates)
- Python 3.8+ available
- Target repo exists on disk (can be empty, can have existing code)
- (Optional) Hub repo path — enables teaching distribution

---

## Step 1 — Run the init script

```bash
python3 /path/to/wheelwright/framework/tools/harness_init.py \
  --target /path/to/your/repo \
  --name "Your Project Name" \
  --hub-path /path/to/wheelwright/hub  # optional
```

Use `--dry-run` first to preview what will be created without writing files:

```bash
python3 tools/harness_init.py --target /path/to/repo --name "Name" --dry-run
```

Use `--force` to overwrite existing files (reinitialize):

```bash
python3 tools/harness_init.py --target /path/to/repo --name "Name" --force
```

### What the script creates

| Path | Contents |
|------|----------|
| `CLAUDE.md` | Minimal harness instructions for Claude Code |
| `AGENTS.md` | Universal wakeup instructions for all AI tools |
| `WAI-Harness/spoke/WAI-State.json` | Project state, session history, work queue |
| `WAI-Harness/spoke/sessions/` | Per-session track journals |
| `WAI-Harness/spoke/lugs/bytype/` | Work item store (epic/task/impl/spec/bug/...) |
| `WAI-Harness/spoke/teachings/` | Local teaching cache |
| `WAI-Harness/spoke/seed/ingest/processed/` | Teaching adoption tracker |
| `WAI-Harness/spoke/runtime/` | Hook runtime state |
| `WAI-Harness/spoke/savepoints/` | Session savepoints |
| `.claude/hooks/` | Session-start, prompt-submit, pre-compact, pre-tool-guard, stop hooks |
| `.claude/settings.json` | Hook wiring + default permissions |
| `.claude/commands/` | Core skills: wai, wai-closeout, wai-lug-schema, and ~40 others |

---

## Step 2 — Post-init checklist

After the script runs:

1. **Review CLAUDE.md** — the template is generic. Add project-specific rules:
   - Stack and environment (language, runtime, test commands)
   - Anti-patterns specific to this codebase
   - Any standing rules (e.g., never delete X, always lint before commit)

2. **Check the hub path** — if you passed `--hub-path`, open `WAI-Harness/spoke/WAI-State.json`
   and confirm `wheel.hub_path` is set correctly.

3. **Git status** — all new files are untracked. Commit the harness skeleton:
   ```bash
   git add WAI-Harness/spoke/ CLAUDE.md AGENTS.md .claude/
   git commit -m "chore: add Wheelwright harness"
   ```

4. **Open in Claude Code** and run `/wai` — confirm you get a WAI Point briefing.

---

## Step 3 — Optional: Hub registration

To receive hub-distributed teachings in this spoke:

1. Open `hub/hub-registry.json`
2. Add an entry under `wheels[]`:
   ```json
   {
     "wheel_id": "your-project-slug",
     "name": "Your Project Name",
     "path": "/absolute/path/to/your/repo",
     "node_type": "spoke",
     "status": "active"
   }
   ```
3. Commit to hub.

Once registered, the hub gardener will deliver teachings to your spoke's
`WAI-Harness/spoke/lugs/incoming/` and the session-start hook will surface them.

---

## Verification

After init, confirm:

```bash
# WAI-State.json exists and has the right project name
cat /path/to/repo/WAI-Harness/spoke/WAI-State.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['wheel']['name'])"

# Hooks are executable
ls -la /path/to/repo/.claude/hooks/*.sh

# Core skill present
ls /path/to/repo/.claude/commands/wai.md

# Lug structure created (spot check)
ls /path/to/repo/WAI-Harness/spoke/lugs/bytype/epic/open/
```

Open the repo in Claude Code and run `/wai`. You should see a WAI Point briefing with:
- Session count: 0
- Work queue: empty
- No pending teachings (unless hub is registered and has pending items)

---

## Step 4 — The upgrade report (produced by the engine, not by hand)

Nothing to copy-paste here. `harness_upgrade.py` writes the upgrade report
itself, on the spoke that took the upgrade, every time it applies one.

Two reasons this is no longer a manual step:

- **It never fired.** This section used to carry a JSON template addressed to
  the old v3 outgoing folder and delivered to the deprecated framework repo.
  On a v4 spoke that folder does not exist and that repo is not the master, so
  the intake ceremony on the other end waited months for input that could not
  arrive.
- **A human cannot answer the question it asks.** The report now carries a
  VALIDATION result — does the spoke still compile, do its entrypoints import,
  is its health verdict RED, did its own tests pass — measured at the moment of
  the upgrade and compared against a baseline taken immediately before it.

What the engine does on every `pull` / `upgrade`:

```bash
# validation runs automatically; --no-validate opts out (bytes-only, pre-4.14.4)
python3 tools/harness_upgrade.py pull --spoke-root .

# or ask the question on its own, any time:
python3 tools/harness_upgrade.py validate --spoke-root .
```

- writes `WAI-Harness/spoke/local/lugs/bytype/upgrade-report/open/upgrade-report-<spoke>-<ts>-v1.json`
- delivers a copy into the master's `WAI-Harness/spoke/local/lugs/incoming/`
- `outcome: fail` reports route as SIGNAL at impact 9, so master learns a spoke
  broke without having to ask

**Outcome grades what the UPGRADE did, not the spoke's absolute health:**

- `pass` — nothing failed
- `partial` — failures exist but they were failing BEFORE this upgrade too. The
  upgrade is not answerable for damage it did not cause; the failures are still
  listed in the report.
- `fail` — a check that passed before the upgrade fails after it. The upgrade is
  reported as failed and `ok` is false.

---

## Updating an existing spoke

The script is idempotent by default (skips existing files). To pull in updated
template files from a newer framework version:

```bash
python3 tools/harness_init.py --target /path/to/repo --name "Name" --force
```

This overwrites template-managed files. Your CLAUDE.md customizations will be overwritten —
back them up first or merge manually.

---

## Shared tools (harness migration)

From harness v1.4+, the bootstrap snapshot carries a `tools/` subdirectory alongside the
skills — the curated set of framework-owned **shared spoke-local tools** (e.g. `lug_utils.py`
with `resolve_attribution`, and `write_change_receipt.py`). A harness-migration lug copies these
into the spoke's repo-local `tools/` directory.

**These install into `<spoke-root>/tools/` — the spoke's OWN version-controlled folder. This is
NOT `~/tools/`.** `~/tools/` is Basher's HOME toolbox (external CLIs like `gastown`/`gitnexus`) and
is off-limits to spoke migration. The curated list + rationale ship as
`bootstrap/v{version}/tools/shared-tools.json` (source: `framework/templates/harness-base/shared-tools.json`).

---

## Troubleshooting

**Hook not firing on session start**
- Check `.claude/settings.json` hooks block is wired correctly
- Verify the hook scripts are executable: `chmod +x .claude/hooks/*.sh`
- Run the hook manually: `bash .claude/hooks/session-start.sh`

**WAI-State.json not populating teaching count**
- Confirm `wheel.hub_path` points to a valid hub repo
- Check `hub/teachings_repo/spoke/current/` exists and has `.teaching` files

**Skills missing from /wai**
- Check `.claude/commands/wai.md` exists
- If Claude Code uses a different commands dir, copy the skills there

---

*Wheelwright harness — general AI continuity layer over any codebase.*
