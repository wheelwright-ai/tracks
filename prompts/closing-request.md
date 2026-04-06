# WAI Track Generator — Closing Request
v0.24

> Part of Wheelwright AI Tracks
> Generate a portable, replayable, and continuable record of any AI conversation — retroactively.

## What is this?

A **WAI Track** is a rich JSONL ledger that:

1. Lets any future agent continue the conversation exactly where it left off.
2. Gives a complete intellectual history — verbatim voice, decisions, fossils, artifacts.
3. Carries turn-level meta: todos, open loops, candidate ideas, awareness.

Paste this prompt into any existing conversation. The agent reviews the full history and produces the export package immediately.

## How to use

1. Copy everything below the line into your existing conversation.
2. The agent analyzes the full history and produces the track package.
3. Download and save the `.jsonl` file.

For priming at session start, see `prep-and-request.md`.
For real-time per-turn capture, see `active-collection.md`.

---

WAI Track v0.24 — closing-request mode

You are generating a WAI Track file — a rich, continuable, retroactive record of this conversation.
Review the entire conversation history and produce the export package immediately.
All records are reconstructed from transcript. Mark capture_mode="reconstructed" on every exchange record.


GOAL

Capture the full conversation into a deterministic JSONL ledger.
Preserve continuity, provenance, artifact lifecycle, decisions, awareness, unresolved opportunities, and file references for high-fidelity handoffs.
Produce the track file and all session artifacts as a single downloadable package.
No gold left behind.


LEDGER RECORD TYPES

session_header — mandatory first record
Fields:
- type="session_header"
- version
- session_codename
- started
- project
- goal
- prompt_version
- persistence_mode
- ledger_filename
- ledger_created
- ledger_verified
- append_supported
- mode="closing-request"
- confidence (low if memory-only)

Optional:
- line_id
- station_id
- governance_mode
- topic_label
- communication_preferences

state_snapshot — emit at export (and optionally every 10 turns if the session was long)
Fields:
- type="state_snapshot"
- active_goals
- current_phase
- locked_decisions
- blocked_tasks
- open_loops
- dominant_themes
- next_focus

exchange — one per turn
Fields:
- type="exchange"
- id={codename}-t{N}
- user.raw
- assistant.raw
- events[]
- focus
- status
- artifacts_referenced[]
- continuity_sources[]
- capture_mode="reconstructed"

Per-turn meta capture fields on exchange:
- awareness_items[]
- identified_todos[]
- candidate_ideas[]
- open_loops[]
- recommendations_made[]
- recommendation_status
- theme_tags[]
- importance
- confidence

If the turn produced artifacts, include artifacts_produced[] on assistant with filename and description.

artifact_manifest — included in every export
Lists all files produced this session.

Each entry:
- id
- filename
- size_bytes
- lifecycle
- status
- description

provenance_manifest — included in every export
Sources consulted:
- memory
- web_search
- tool_call
- uploaded_file
- pasted_track
- live_session
- reconstructed_transcript

Optional:
- notes

line_manifest / station_manifest — include if applicable


TURN-LEVEL META CAPTURE RULES

Reconstruct these fields retrospectively for each turn from conversation history.

awareness_items[]:
Notable observations, risks, tensions, drift signals, hidden assumptions, opportunities, or strategic awareness that emerged during the turn.

identified_todos[]:
Actionable follow-up work revealed during the turn, even if not formally approved.

candidate_ideas[]:
Ideas, concepts, proposals, or directions surfaced that may have value later, including ideas not incorporated into the final design.

open_loops[]:
Unresolved questions, tensions, dependencies, or missing information that still matter.

recommendations_made[]:
Explicit assistant recommendations offered in the turn.

recommendation_status:
Use one of:
- accepted_by_default
- challenged
- deferred
- rejected
- mixed

theme_tags[]:
Lightweight theme tags for later clustering and Historian analysis.

importance:
Use one of: low | medium | high

confidence:
Use one of: low | medium | high

Priority rule:
- raw turn capture is mandatory for any recorded turn
- awareness/meta fields are secondary and may be partial if necessary
- never omit raw_capture in favor of richer interpretation


ARTIFACT FIELDS

Status:
- materialized
- uploaded
- referenced
- described_only

Lifecycle:
- proposed
- approved
- blocked
- deprecated
- superseded
- active

Record only the final landing version of any generated artifact.
Never record intermediate drafts.
Include excerpt (first ~400 chars) and canonical_version=true on files_out entries.

Epic:
When the session locked a concept for later work, emit an epic event and register it in the artifact_manifest with lifecycle=proposed.


TRACK-AWARENESS RULE

Capture not only the explicit question, but also:
- refined framing
- clarified goal
- key constraints
- accepted recommendations
- challenged recommendations
- important pivots
- latent ideas not incorporated
- recurring themes

These are valuable but secondary to raw turn fidelity.
Raw turn fidelity always wins if there is a tradeoff.


EXPORT CONTRACT

Execute immediately. No trigger needed — pasting this prompt IS the trigger.

Codename:
Generate a session codename: {dayOfYear}-{dayWord}-{themeWord}
Infer the session goal from conversation history.

Pre-export reconciliation:
1. count turns from conversation history
2. write one exchange record per turn, capture_mode="reconstructed"
3. if any turn data is uncertain, omit fields rather than invent them
4. write latest state_snapshot
5. finalize artifact_manifest
6. finalize provenance_manifest
7. include line_manifest / station_manifest if applicable

Full session export:

Filename:
  WAI_Track-{YYYYMMDD}-{HHMM}-{Provider}-{Model}_{codename}_full.jsonl

Record order in file:
1. session_header
2. artifact_manifest
3. provenance_manifest
4. line_manifest / station_manifest if applicable
5. latest state_snapshot
6. exchange records in turn order

The JSONL itself is listed last in artifact_manifest with lifecycle=active.

Include an export note in the session_header stating:
- capture_mode=reconstructed for all exchange records
- source=conversation_transcript

Present:
- track JSONL first
- then active artifacts
- then superseded artifacts

Summary:
Print this block only, no other text before the save instructions:

  Session package — {codename}
  ---
  {filename:<45}  {size_bytes:>8} bytes  [{lifecycle}]
  ... one line per file
  ---
  TOTAL  {n} files  {total_bytes} bytes

Do not claim complete export unless reconstruction is labeled.

After the package summary, always add this exact save instructions block (do not modify it):

---

**Wheelwright Track Collected ✓**

Conversation successfully exported as a portable WAI Track file.

**Suggested filename:** `WAI_Track-{YYYYMMDD}-{HHMM}-{Provider}-{Model}_{codename}_full.jsonl`

**How to save it (takes 10 seconds):**
1. Click anywhere inside the gray code block above
2. Press Ctrl+A (Windows) or Cmd+A (Mac) to select everything
3. Press Ctrl+C / Cmd+C to copy
4. Open a text editor (Notepad, VS Code, TextEdit, etc.)
5. Paste and save the file with the suggested name above (make sure it ends in .jsonl)

You can now:
- Feed this file to another agent to continue exactly where we left off
- Archive it as a structured record of decisions, reasoning, and final artifacts
- Use it later to rebuild context without re-reading the whole chat

Happy building!


FALLBACK — NO FILESYSTEM AVAILABLE

Embed file contents directly in the artifact_manifest records.

Text files (.md .txt .json .ts .py .sql):
- content_text field
- UTF-8
- never truncate

Binary/HTML files (.html .pdf .png):
- content_b64 field
- base64-encoded
- add encoding="base64"

Set confidence=low on session_header.

Recovery script (include as a comment block in the JSONL):

  import json, base64
  with open("WAI_Track-*.jsonl") as f:
      for line in f:
          rec = json.loads(line)
          if rec.get("type") == "artifact_manifest":
              for a in rec["artifacts"]:
                  if "content_text" in a:
                      open(a["filename"], "w").write(a["content_text"])
                  elif "content_b64" in a:
                      open(a["filename"], "wb").write(base64.b64decode(a["content_b64"]))
                  print(f"Recovered: {a['filename']}")


LINE AND STATION DEFINITIONS

Track:
  session-level record

Line:
  shared continuity channel across agents, tools, and humans

Station:
  local collection point and control boundary

Source rules:
- live_session — content generated in this conversation
- pasted_track — content pasted in from another session; never treat as materialized until verified
- uploaded_file — user-provided file; record as uploaded, not materialized
- reconstructed_transcript — export content assembled from conversation transcript


OPERATIONAL STYLE

Low ceremony:
No wrapper text on exports.
Package summary only.

High fidelity:
Verbatim capture of user and assistant turns.

Package complete:
Every file produced is in the download list.

Self-contained:
The package must be usable by a cold agent with no prior context.

Cold handoff test:
Before presenting export success, ask:
- could a cold agent reconstruct the session decisions, artifacts, and next actions from this package alone?
If no, the export is not complete.


WAI DOMAIN VOCABULARY

This session may use Wheelwright (WAI) terms.
Treat these as precise domain language.

Lug:
A typed JSON work item.
The persistent memory unit of a WAI project.
Every lug has: id, type, status, and PEV fields.
Lugs must be self-contained and readable cold with zero conversation history.

Lug types:
- epic
- task
- bug
- feature
- signal
- implementation
- session-summary

PEV (required on all actionable lugs):
- perceive   what to read or examine before starting
- execute    concrete steps to take
- verify     how to confirm it is done correctly

Lifecycle:
open → in_progress → completed

Quality bar before sharing a lug:

Dogfood test:
Send just the PEV to a sub-agent with zero context.
Can they implement it without a single clarifying question?
Gaps mean the lug is not ready.

Misinterpretation test:
Could this be read as "execute immediately" instead of "track for later"?
If yes, add:
  _behavior_directive: { what_this_is: "...", what_this_is_NOT: "..." }

Cold-read test:
No implicit references such as "see above" or "as discussed".
Every file path, field name, and dependency must be explicit.
