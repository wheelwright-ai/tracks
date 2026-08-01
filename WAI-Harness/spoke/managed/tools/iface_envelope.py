#!/usr/bin/env python3
"""iface_envelope.py — WAI Interface Contract v1: the seam every agent interface implements.

WHY THIS EXISTS
---------------
Hook bodies used to parse interface-NATIVE stdin directly:

    json.load(sys.stdin).get("session_id")
    json.load(sys.stdin).get("transcript_path")

Two calls, repeated across eight hooks. That is the whole of the Claude coupling on
the hook path — measured on basher 2026-07-31: each 200-500 line hook body carries
only 3-8 Claude-specific references, and exactly 3 files parse Claude's message
schema. Narrow as it is, it is load-bearing: a second interface either reimplements
every hook body in its own language (dual-source drift, which has already cost this
repo real defects) or it translates at this one seam.

This module IS that seam. An adapter translates native input into ONE envelope
shape; hook bodies read the envelope and never learn which interface they are under.

CONTRACT v1 (spec-wai-interface-contract-v1, ratified by mywheel session 140 with
amendments A1/A2/A3 — all three are enforced HERE, not by convention):

  EVENTS   wai.session.start  wai.turn.begin  wai.turn.end
           wai.tool.before    wai.tool.after
           wai.compact.before wai.session.end

  ENVELOPE {schema, event, interface, session_id, cwd, transcript_ref,
            model:{provider,id}, tool:{name,input}?, outcome?, extra:{}}

  transcript_ref is OPAQUE. It is a handle the adapter resolves, never a path a
  hook body parses. Hook bodies that need turns call read_transcript(), which is
  data contract 1 and lives in the adapter.

AMENDMENT A1 — turn.end fires on ABORT, carrying an outcome.
  An interrupted turn never fired turn.end, so the track buffer never flushed and
  the turn's record was lost. Not hypothetical: this repo's resident digest carries
  a standing "10-of-15 interrupted sessions" thread, and session 140 launched from
  an INTERRUPTED predecessor. A contract describing only the happy path would have
  standardised our worst existing behaviour across every future interface.

AMENDMENT A2 — unknown schema major or unknown event FAILS CLOSED and LOUD.
  Undefined forward-compat resolves in practice to "proceed on partially understood
  input", which is how a silent failure is born. Failures in this wheel are
  SILENCES, not errors; this one refuses to be.

AMENDMENT A3 — the CONTRACT owns what UNSUPPORTED costs, not the adapter.
  An adapter DECLARES an event unsupported; it does not get to define the
  consequence. Otherwise the conformance suite asserts whatever the adapter claimed,
  which is self-certification wearing a gate's clothes. See UNSUPPORTED_COST.
"""
import json
import os
import sys

SCHEMA = "wai.iface/1"
SCHEMA_MAJOR = 1

SESSION_START = "wai.session.start"
TURN_BEGIN = "wai.turn.begin"
TURN_END = "wai.turn.end"
TOOL_BEFORE = "wai.tool.before"
TOOL_AFTER = "wai.tool.after"
COMPACT_BEFORE = "wai.compact.before"
SESSION_END = "wai.session.end"

EVENTS = (SESSION_START, TURN_BEGIN, TURN_END, TOOL_BEFORE, TOOL_AFTER,
          COMPACT_BEFORE, SESSION_END)

# A1: the outcomes turn.end may carry. "aborted" is the whole point of the amendment.
OUTCOMES = ("completed", "aborted", "error")

# A3: what losing each event COSTS, owned by the contract. `hard` means an adapter
# declaring it unsupported may not be registered at all — the harness cannot do its
# job without it. Anything softer states what is lost and what compensates, so the
# degradation is asserted rather than discovered.
UNSUPPORTED_COST = {
    SESSION_START:  {"severity": "hard",
                     "lost": "no wakeup brief, no lane reservation, no hygiene heal",
                     "compensation": None},
    TURN_BEGIN:     {"severity": "warn",
                     "lost": "per-turn obligations and the TasteGraph vector are not injected",
                     "compensation": "session-start injection only; preferences go stale within a session"},
    TURN_END:       {"severity": "hard",
                     "lost": "track buffer never flushes; the turn's record is lost",
                     "compensation": None},
    TOOL_BEFORE:    {"severity": "hard",
                     "lost": "destructive-op guard and write guard never fire",
                     "compensation": None},
    TOOL_AFTER:     {"severity": "warn",
                     "lost": "post-write reminders and decide-prompt clearing",
                     "compensation": "next turn.begin re-derives state; prompts may linger one turn"},
    COMPACT_BEFORE: {"severity": "warn",
                     "lost": "state is not persisted before context compaction",
                     "compensation": "session-start compact-resume path recovers, with the gap unrecorded"},
    SESSION_END:    {"severity": "warn",
                     "lost": "the lane is not released on exit",
                     "compensation": "stale-lane TTL reclaims it, so a concurrent session may be blocked meanwhile"},
}


class ContractError(Exception):
    """A2: raised instead of proceeding on input we do not fully understand."""


def _schema_major(schema):
    """Major from 'wai.iface/N'. Raises ContractError on anything else (A2)."""
    if not isinstance(schema, str) or not schema.startswith("wai.iface/"):
        raise ContractError(
            f"unrecognised envelope schema {schema!r} — expected 'wai.iface/<major>'. "
            "Refusing to run the hook body on input of unknown shape (contract A2)."
        )
    try:
        return int(schema.split("/", 1)[1].split(".", 1)[0])
    except (ValueError, IndexError):
        raise ContractError(
            f"unparseable schema major in {schema!r} (contract A2)."
        )


def validate(env):
    """Validate an envelope. Returns it unchanged, or raises ContractError (A2).

    Fails CLOSED: an unknown schema major or an unknown event name means the hook
    body must not execute. Silently skipping either is the failure mode A2 exists
    to remove.
    """
    if not isinstance(env, dict):
        raise ContractError(f"envelope must be a JSON object, got {type(env).__name__}")

    major = _schema_major(env.get("schema"))
    if major != SCHEMA_MAJOR:
        raise ContractError(
            f"envelope schema major {major} is not implemented by this harness "
            f"(implements {SCHEMA_MAJOR}). Refusing to run the hook body (contract A2)."
        )

    event = env.get("event")
    if event not in EVENTS:
        raise ContractError(
            f"unrecognised event {event!r}. Known: {', '.join(EVENTS)}. "
            "Refusing to run the hook body (contract A2)."
        )

    outcome = env.get("outcome")
    if outcome is not None and outcome not in OUTCOMES:
        raise ContractError(
            f"outcome {outcome!r} is not one of {OUTCOMES} (contract A1)."
        )
    return env


def build(event, *, interface="claude", session_id="", cwd=None, transcript_ref="",
          model=None, tool=None, outcome=None, extra=None):
    """Construct a contract envelope. Validated before it is returned."""
    env = {
        "schema": SCHEMA,
        "event": event,
        "interface": interface,
        "session_id": session_id or "",
        "cwd": cwd if cwd is not None else os.getcwd(),
        "transcript_ref": transcript_ref or "",
        "model": model or {"provider": "", "id": ""},
        "extra": extra or {},
    }
    if tool is not None:
        env["tool"] = tool
    if outcome is not None:
        env["outcome"] = outcome
    return validate(env)


# ── Adapters: native payload -> envelope ────────────────────────────────────────
#
# NON-NEGOTIABLE (ratified without qualification): an adapter TRANSLATES and SHELLS
# OUT. It never reimplements a hook body. Everything below is field mapping — if an
# adapter ever needs logic here, the logic belongs in the hook body instead.

def _from_claude(event, native, outcome=None):
    """Claude Code's hook payload -> envelope.

    Claude supplies session_id and transcript_path. transcript_path becomes the
    OPAQUE transcript_ref: hook bodies must not parse it, only hand it back to
    read_transcript(). Preserving it verbatim is what keeps the claude path
    byte-identical in behaviour while the seam is introduced.
    """
    model = native.get("model") or {}
    if isinstance(model, str):
        model = {"provider": "anthropic", "id": model}
    return build(
        event,
        interface="claude",
        session_id=native.get("session_id", ""),
        cwd=native.get("cwd") or os.getcwd(),
        transcript_ref=native.get("transcript_path", ""),
        model={"provider": model.get("provider") or "anthropic",
               "id": model.get("id") or model.get("model") or ""},
        tool=({"name": native["tool_name"], "input": native.get("tool_input") or {}}
              if native.get("tool_name") else None),
        outcome=outcome,
        extra={k: v for k, v in native.items()
               if k not in ("session_id", "transcript_path", "cwd", "model",
                            "tool_name", "tool_input")},
    )


def _from_opencode(event, native, outcome=None):
    """opencode's plugin payload -> envelope.

    Field names per opencode 1.18.4. Kept deliberately thin: this is the shape the
    adapter shim passes in after calling the plugin API, and it exists so the
    conformance suite has a second interface to run the SAME assertions against.
    """
    model = native.get("model") or {}
    if isinstance(model, str):
        model = {"provider": "", "id": model}
    return build(
        event,
        interface="opencode",
        session_id=native.get("sessionID") or native.get("session_id", ""),
        cwd=native.get("directory") or native.get("cwd") or os.getcwd(),
        transcript_ref=native.get("sessionID") or "",
        model={"provider": model.get("providerID") or model.get("provider") or "",
               "id": model.get("modelID") or model.get("id") or ""},
        tool=({"name": native["tool"], "input": native.get("args") or {}}
              if native.get("tool") else None),
        outcome=outcome,
        extra={k: v for k, v in native.items()
               if k not in ("sessionID", "session_id", "directory", "cwd",
                            "model", "tool", "args")},
    )


ADAPTERS = {"claude": _from_claude, "opencode": _from_opencode}


def normalise(event, native, interface=None, outcome=None):
    """Native payload -> envelope, dispatching on the interface discriminator.

    interface defaults to $WAI_IFACE then 'claude', so every existing deployment
    keeps its current behaviour with no configuration. That default is the entire
    reason this can be introduced without a migration.
    """
    iface = interface or os.environ.get("WAI_IFACE") or "claude"
    adapter = ADAPTERS.get(iface)
    if adapter is None:
        raise ContractError(
            f"no adapter registered for interface {iface!r}. "
            f"Registered: {', '.join(sorted(ADAPTERS))} (contract A2)."
        )
    return adapter(event, native if isinstance(native, dict) else {}, outcome=outcome)


def read_native(stream=None):
    """Read a native payload from stdin, tolerating empty/!json input.

    Empty stdin is NOT a contract violation — several hooks are invoked with stdin
    closed by design (session-start spawns with </dev/null so a spawn can never hang
    startup). An empty payload yields {}, and the envelope is still well-formed.
    Malformed non-empty JSON is also tolerated here rather than raised: the hook
    bodies' long-standing behaviour is to degrade to empty fields, and A2 governs
    envelope shape, not native input we were handed by someone else.
    """
    stream = stream if stream is not None else sys.stdin
    try:
        raw = stream.read()
    except Exception:
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        val = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return val if isinstance(val, dict) else {}


def main(argv=None):
    """CLI: emit an envelope on stdout from native stdin.

    Hook bodies call this instead of parsing native stdin themselves:

        ENV=$(printf '%s' "$INPUT" | python3 .../iface_envelope.py --event wai.turn.begin)
        SID=$(printf '%s' "$ENV" | python3 -c 'import json,sys;print(json.load(sys.stdin)["session_id"])')

    Exit 2 on a contract violation (A2) so a caller can distinguish "refused" from
    "crashed", and so `set -e` callers stop rather than continuing on empty output.
    """
    import argparse
    ap = argparse.ArgumentParser(description="WAI Interface Contract v1 envelope emitter")
    ap.add_argument("--event", required=True, help=f"one of: {', '.join(EVENTS)}")
    ap.add_argument("--interface", default=None, help="override $WAI_IFACE (default: claude)")
    ap.add_argument("--outcome", default=None, choices=OUTCOMES,
                    help="for wai.turn.end: completed|aborted|error (contract A1)")
    ap.add_argument("--unsupported-cost", action="store_true",
                    help="print the A3 cost table as JSON and exit")
    args = ap.parse_args(argv)

    if args.unsupported_cost:
        print(json.dumps(UNSUPPORTED_COST, indent=2))
        return 0
    try:
        env = normalise(args.event, read_native(), interface=args.interface,
                        outcome=args.outcome)
    except ContractError as e:
        print(f"iface_envelope: REFUSED — {e}", file=sys.stderr)
        return 2
    print(json.dumps(env))
    return 0


if __name__ == "__main__":
    sys.exit(main())
