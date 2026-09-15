# secrets-template-migration

Operator direction 2026-09-14 (wheel-hub lug
secrets-manifest-migrates-from-env-template-and-spreads-by-cut, design
docs/basher-secrets-design.md section 8): the 1Password-backed secrets
manifest must carry a migration path from the `.env.template`
`#@`-annotation convention, not land as a break, and every spoke must pick
it up organically through the cut.

## What it is, honestly

Four mechanisms, one module (`src/basher/secretsManifest.js`):

1. **migrate** -- `node scripts/secrets.js migrate [<spoke>]` parses the
   spoke's `.env.template` and writes `canon/secrets.manifest.yaml`
   (kind `secrets_manifest`, schema `schemas/secrets-manifest.schema.json`).
   Every `#@secret` or `#@optional` line becomes a key; `#@plain` lines
   stay in `.env`. The 1Password location comes from the line's own
   `op://vault/item/field` reference (basher v1's `secrets restore`
   convention -- measured 2026-09-14: every basher and minder value line
   but one carries it) or from a `#@seed-from=` annotation, which wins
   when both are present. A key with neither gets B3's convention
   (`item: <spoke>`, `field: <KEY>`) and `needs_op_item: true`. A manifest
   that already exists is never overwritten: a changed template yields
   `secrets.manifest.yaml.v2-proposed`; the same template (sha256) yields
   nothing. The template is never written -- `migrate` asserts its
   sha256 before and after.
2. **wcl step 5** -- a spoke with a template and no manifest gets the
   migration at launch (one line: the file written, the key count, how
   many keys resolved from 1Password into the spoke's `.local/secrets.json`,
   every unresolved path named). A spoke with neither gets one line
   saying so. A spoke with a manifest takes the unchanged path: no
   migration, no `op` call, no write.
3. **dual-read** -- `getSecret(configDir, name)` reads the resolved
   cache first; on a miss it resolves through the template's own
   reference and appends ONE ledger decision row (attribution
   `secrets-template-fallback`, naming the key and the path, never the
   value). `node scripts/secrets.js fallbacks <spoke>` counts them per
   key. The count is the migration's own measure.
4. **retirement** -- on every `applyCut`, a spoke whose fallback rows
   have been zero for `max_age x 7` since its manifest's `migrated_at`
   has `.env.template` renamed `.env.template.migrated-<cut>` and the
   sha256 recorded in the manifest's `migrated_from`. A spoke with
   fallbacks, no manifest, or a window not yet observed keeps its
   template, and `.cut-status.json` carries the reason. Never deleted.

## What it refuses

- To invent a vault: a template with no `op://` reference and no
  `--vault=` flag is refused with the flag named.
- To write a value anywhere but `.local/secrets.json` (mode 600).
- To retire on an unobserved window: `migrated_at` missing means no
  measured start and no retirement.
- To refuse a launch: an unresolved key at step 5 is named, not fatal --
  the refuse-on-missing-required posture belongs to the implement lug.

## Conformance

`conformance/fixtures/secrets-template-migration/` parses basher's and
minder's REAL templates read-only, runs a scratch spoke through step 5
with a fake `op`, counts dual-read rows per key, proves the retirement
window both ways, applies a cut to a scratch spoke and finds the circle
and a compiling manifest there, and runs the credential scan over every
file it produced.
