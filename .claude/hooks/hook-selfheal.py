#!/usr/bin/env python3
"""Re-assert basher-declared hooks into a live Claude Code settings.json.

WHY THIS EXISTS
---------------
basher owns a set of GLOBAL hooks (the zellij tab glyphs, the Windows toasts, the
per-turn track flush, the savepoint guard). They are declared in
WAI-Harness/spoke/basher.json and registered into ~/.claude/settings.json. Other
writers -- the WAI managed-settings deploy, `basher restore --hooks`, hand edits --
rewrite that file, and a NON-ADDITIVE writer silently drops whatever it did not
author.

Measured 2026-08-14: four registrations were gone from BOTH ~/.claude/settings.json
and basher's project settings.json -- notify.sh on Stop, notify-reset.sh on
UserPromptSubmit, pre-tool-tab-reset.sh on PreToolUse, tab-clear.sh on SessionEnd.
Nothing errored. The two symptoms the operator actually saw:

  * "zj icons broken"  -- notify-reset.sh writes the working glyph. With it gone,
    nothing ever set a tab back to the hourglass, so every tab froze on the checkmark
    from its last completed turn.
  * "toasts delayed"   -- the turn-done toast fires from Stop. With Stop gone, the
    only surviving toast was the Notification (idle_prompt) hook, which Claude Code
    fires about a minute AFTER the turn ends. The toasts were not slow; a different,
    later event was doing the notifying.

WHAT THE PREVIOUS SELF-HEAL GOT WRONG
-------------------------------------
It lived as an inline heredoc in session-start.sh and compared commands by EXACT
STRING. basher.json declares a bare path ("/…/notify.sh"); settings.json stores the
guarded wrapper (F="/…/notify.sh"; [ -x "$F" ] && exec "$F"; true); other entries use
${CLAUDE_PROJECT_DIR} for the same file. No two of those spellings compare equal, so
every declared hook read as "missing" on every session start -- a duplicate machine,
not a repair. SessionStart had reached THREE registrations of session-start.sh under
three overlapping matchers, i.e. three full runs of the wakeup on every `startup`.
And the invocation ended in `>/dev/null 2>&1`, so neither the duplication nor the
four real gaps left a trace anywhere.

Hence the three rules below: identify a hook by its script BASENAME (the one thing
every spelling agrees on), respect matcher COVERAGE rather than matcher equality, and
report on stdout as JSON so the caller can log what it repaired.

Usage:  hook-selfheal.py <basher.json> <settings.json> [--dry-run]
Exit 0 always (a self-heal must never break session start). Prints one JSON object.
"""
import json
import os
import re
import sys
from pathlib import Path

UNIVERSAL = ".*"


def wrap(cmd: str) -> str:
    """The guarded form every other entry in settings.json uses.

    Guarded, not bare: a hook whose file is missing (mid-deploy, or a spoke that never
    installed it) must be a no-op, not a 'hook error' banner on every tool call for the
    rest of the session.
    """
    return f'F="{cmd}"; [ -x "$F" ] && exec "$F"; true'


def key_of(command: str) -> str:
    """Identify the hook a command runs, independent of how the path is spelled.

    The same hook appears as a bare path, wrapped in the `F=…` guard, and rooted at
    either ${CLAUDE_PROJECT_DIR} or /home/mario/projects/basher. The basename is the
    only stable identity across all three. Returns '' for a command that names no
    script -- an inline shell command is not a registration we can reason about.
    """
    m = re.search(r'([^\s"\']+\.(?:sh|py))', command or "")
    return os.path.basename(m.group(1)) if m else ""


def alts(matcher: str) -> set:
    """Matcher as a set of alternatives. `.*` (or empty) means 'everything'."""
    m = (matcher or "").strip()
    if m in ("", UNIVERSAL, "*"):
        return {UNIVERSAL}
    return {a.strip() for a in m.split("|") if a.strip()}


def covers(existing: str, declared: str) -> bool:
    """Does an existing registration's matcher already fire for the declared one?"""
    e, d = alts(existing), alts(declared)
    return UNIVERSAL in e or d.issubset(e)


def merge_matchers(matchers) -> str:
    """Union of several matchers, order-preserving. Any universal wins."""
    out = []
    for m in matchers:
        a = alts(m)
        if UNIVERSAL in a:
            return UNIVERSAL
        for x in (m or "").split("|"):
            x = x.strip()
            if x and x not in out:
                out.append(x)
    return "|".join(out) if out else UNIVERSAL


def dedupe_event(rules, event, deduped):
    """Collapse repeat registrations of one script within an event.

    Not a plain 'drop the later copy': the three SessionStart entries carried
    DIFFERENT matchers (`startup|resume|clear`, `startup|resume|clear|compact`,
    `startup`), so keeping the first would have silently dropped `compact` and broken
    post-compaction resume. Union the matchers instead, then keep exactly one entry
    under the union -- no coverage is lost and the hook runs once.
    """
    # Index by IDENTITY, not by position. The previous implementation recorded
    # (rule_index, hook_index) for EVERY key up front and then deleted through those
    # positions. Collapsing the first key shifts every later key's hook_index within
    # the same rule, and appending the merged rule shifts rule_index -- so the second
    # key deleted the wrong entry, or raised IndexError once the list had shrunk past
    # the recorded position. Measured 2026-08-14: `del rules[ri]["hooks"][hi]` ->
    # IndexError: list assignment index out of range, which left ~/.claude/settings.json
    # permanently un-healed with duplicate tab/toast hook registrations. Holding the
    # objects themselves makes the collapse order-independent.
    occurrences = {}
    for rule in rules:
        for h in rule.get("hooks", []):
            k = key_of(h.get("command", ""))
            if k:
                occurrences.setdefault(k, []).append((rule, h))

    for k, spots in occurrences.items():
        if len(spots) < 2:
            continue
        matchers = [rule.get("matcher", UNIVERSAL) for rule, _ in spots]
        merged = merge_matchers(matchers)
        entry = dict(spots[0][1])
        doomed = {id(h) for _, h in spots}
        for rule in rules:
            if "hooks" in rule:
                rule["hooks"] = [h for h in rule["hooks"] if id(h) not in doomed]
        target = next((r for r in rules if r.get("matcher") == merged), None)
        if target is None:
            target = {"matcher": merged, "hooks": []}
            rules.append(target)
        target["hooks"].append(entry)
        deduped.append({"event": event, "script": k, "copies": len(spots),
                        "merged_matcher": merged})

    # Drop rules left empty by the collapse.
    rules[:] = [r for r in rules if r.get("hooks")]


def main() -> int:
    if len(sys.argv) < 3:
        print(json.dumps({"ok": False, "error": "usage: hook-selfheal.py <basher.json> <settings.json> [--dry-run]"}))
        return 0
    dry = "--dry-run" in sys.argv[3:]
    try:
        declared = json.loads(Path(sys.argv[1]).read_text()).get("hooks", [])
        cfgp = Path(sys.argv[2])
        cfg = json.loads(cfgp.read_text())
    except Exception as e:  # unreadable / absent / corrupt -> nothing to heal, say so
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        return 0

    hooks = cfg.setdefault("hooks", {})
    restored, deduped = [], []

    for event, rules in hooks.items():
        if isinstance(rules, list):
            dedupe_event(rules, event, deduped)

    for dh in declared:
        event, cmd = dh.get("event"), dh.get("command")
        if not event or not cmd:
            continue
        want = key_of(cmd)
        if not want:
            continue
        declared_matcher = dh.get("matcher", UNIVERSAL)
        present = any(
            key_of(h.get("command", "")) == want
            and covers(rule.get("matcher", UNIVERSAL), declared_matcher)
            for rule in hooks.get(event, [])
            for h in rule.get("hooks", [])
        )
        if present:
            continue
        rules = hooks.setdefault(event, [])
        rule = next((r for r in rules if r.get("matcher") == declared_matcher), None)
        if rule is None:
            rule = {"matcher": declared_matcher, "hooks": []}
            rules.append(rule)
        rule["hooks"].append(
            {"type": "command", "command": wrap(cmd), "timeout": dh.get("timeout", 10)}
        )
        restored.append({"event": event, "id": dh.get("id", ""), "script": want,
                         "matcher": declared_matcher})

    changed = bool(restored or deduped)
    if changed and not dry:
        try:
            cfgp.write_text(json.dumps(cfg, indent=2) + "\n")
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"write failed: {e}",
                              "restored": restored, "deduped": deduped}))
            return 0
    print(json.dumps({"ok": True, "changed": changed, "dry_run": dry,
                      "restored": restored, "deduped": deduped}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
