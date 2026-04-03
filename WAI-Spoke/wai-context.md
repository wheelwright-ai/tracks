<!-- Generated artifact. Updated at teaching adoption via Context Doc Patch. Build: tracks / fw / Sessions: 0 | series_version: 3.20260403 | series_weight: 10 -->

# WAI Context — Tracks Spoke

This file tracks teaching adoption fingerprints and framework context for the tracks spoke.

## Series Version

- **series_version:** 3.20260403
- **series_weight:** 10
- **fingerprints:** 07d

## Core Object: Teaching

Teachings are packaged framework updates distributed from hub to all wheels. Format: `.md.teaching` files.

Every teaching has a `safe_to_auto_adopt` flag:
- `true` → AI presents a summary, adopts after user sees it
- `false` → requires explicit user approval

Every teaching also carries:
- `weight` — complexity score (1/5/10/25). Contributes to series closure at 100 accumulated points.
- `fingerprint` — 3-char alphanumeric, derived from `MD5(teaching-id:weight)[:3]`. Appended to spoke version string on adoption.

On adoption, the spoke updates `wai-context.md` header: appends fingerprint, accumulates weight, applies any Context Doc Patch sections.

Teaching lifecycle:
```
Pattern discovered in wheel
  → captured as signal lug
  → delivered to hub
  → hub packages as .teaching file (with weight + fingerprint + optional Context Doc Patch)
  → Gardener distributes to all wheels
  → wheels adopt at next wakeup → wai-context.md updated
```
