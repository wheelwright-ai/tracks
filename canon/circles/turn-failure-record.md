# turn-failure-record

Lug `safeguard-stops-are-detected-recorded-and-the-task-resumes-by-a-safer-route`
(initiative `session-record-is-native-lossless-and-rebuildable`).

Claude Code fires `StopFailure`, not `Stop`, when a turn ends in an API
error. In the operator's sessions that happened several times a day
("safeguards flagged this message", "Can't reach the API server"), and each
one dropped the in-flight step and left half-done state: a truncated file,
uncommitted work. The only reaction was an alarm sound.

## What it records

`src/hooks/turnFailureRecordHook.js` appends one row per failed turn to
`runtime/turn-failures.jsonl` (`src/lugTracking/turnFailure.js`):

| field | meaning |
|---|---|
| `session_id`, `ts`, `turn_id` | which turn stopped, and when |
| `class`, `classified_from` | `safeguard_stop`, `network`, `rate_limit` or `other`; `payload` or `transcript` |
| `error_type` | the payload's `error` when it is an enum token, else null |
| `active_lug` | the lug the turn was attributed to, if any |
| `last_tool_class` | `bash`, `read`, `write:lugs`, `bash-write:src`, `agent`, `none` |

The class is read from the payload (`error_type` or `error`, and its message
fields). When the payload alone says `other`, the session log's own API-error
row from the last two minutes classifies instead, and `classified_from` says
which one did.

The tool class comes from records the harness already keeps: the
dispatcher's PreToolUse runlog row (its tool name) and the
session-files-touched record (the top-level directory of a write). The row
holds no prompt, reply, command text or file path. The payload's message
fields are read in memory to classify and are withheld from the live
capture as well.

## How the task resumes

When a session's newest row is unacknowledged, its next prompt
(`turnStartAttributionHook.js`) or session start
(`warmupGoalsReviewHook.js`) carries one block from
`src/lugTracking/turnFailureResume.js`: the class and time, the active lug,
the files written in the stopped turn with their present state (missing,
empty, unparseable JSON, no final newline), the last operator ask from the
turn record, and the sanctioned scripts. The row is then acknowledged by an
appended `turn_failure_ack` row.

The harness does not reword a stopped message and send it again. The block
says to continue the task from the record and not to replay the message.

## Sanctioned scripts

- `node scripts/secrets.js fingerprint [<spoke>]` compares the key stores by
  key name and an 8-character sha256 prefix. No value is printed.
- `node scripts/raw-snapshot.js` handles raw session logs.

## The measure

Session start prints `TURN FAILURES: N in the last 7 days (safeguard S,
network W, other O); last <time>` (`src/lugTracking/turnFailureSection.js`),
silent at zero. When the window has recorded operator turns
(`runtime/turn-records/`), the stop rate per 100 of them follows on the same
line.

## Live safety

Every path exits 0 and writes no stdout. A failure inside the body is
swallowed. Reads are bounded tails (512 KB of the runlog and of the
files-touched record, 4 MB of the failure stream).

## Not built yet

- The supervisor-tick resume for a dispatched run.
- The PreToolUse advisory that points a raw read at the script.
