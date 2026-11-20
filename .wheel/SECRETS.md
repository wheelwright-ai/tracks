# Secrets in this project

The file `.env.template` holds only the mapping: for each key, a reference into the vault, a few annotations,
grouped by vendor section. It never holds a value you must keep secret. Real values live in the vault; `render`
writes them into your local env file.

## Two vaults
- The **shared vault** holds keys many projects use (an AI provider key, for example). Point to it, never copy it.
- The **project vault** has one item per project, with a section per vendor section of the template.

## Add a key
1. Add the line in its vendor section of `.env.template` (create the section banner if it is new):
   `KEY="op://Vault/Item/Section/field"  #@secret #@target=local`
2. Run `basher secrets learn` (adds the vault field when it holds nothing yet), then `basher secrets render`
   (writes your local env file).

## Annotations (after the reference, on the same line)
- `#@secret` the value is sensitive; `#@plain` a literal that may be shown; `#@optional` the project runs without it.
- `#@target=a,b` where the key is used: local, vercel, github, supabase.
- `#@description="..."` one line on what it is for; `#@source="..."` where the owner gets it.
- `#@tool=x` the tool that reads it; `#@seed-from=op://...` a reference to copy from when the vault has nothing.
- A header line `# @output-local: .env.local` names the local env file `render` writes.

## Rules
- The vault is never overwritten. A field is added only when the vault holds nothing for it.
- A local value that differs from the vault's is left as it is and reported; nobody picks a winner silently.
- Never print, log or commit a value. Reports name keys only.
- Pushing a key outward (Vercel, GitHub, Supabase) and any vault delete need the owner's yes.
- Local backups (`.env*.bak-*`) and temporary files (`.env*.tmp-secrets`) stay out of git; the kit adds them to `.gitignore`.

## Who may do what
- Only the owner deletes vault items.
- Hub sessions may create items and copy fields between vaults.
- Project sessions edit only their own mapping (`.env.template`).
