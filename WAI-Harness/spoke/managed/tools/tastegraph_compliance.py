#!/usr/bin/env python3
"""TasteGraph compliance oracle — does a stated preference actually bind?

THE PROBLEM THIS SOLVES. TasteGraph costs ~2,573 tokens on every user turn and
~5,772 at session start (85% of all hook injection), and until now the ONLY
evidence it changed any behaviour was a rubric the agent filled in about itself
(tastegraph-grades/v1.4.8, `"grader": "agent"`, 39 of ~100 preferences covered,
64% self-scored as adhered). Asking a model whether it followed instructions is
not measurement. It is the defendant's testimony, and it is exactly the flaw
this tool must not reproduce.

THE DESIGN RULE, and the whole point: **no model judges anything here.** Every
detector is a deterministic function over the transcript text. A detector either
proves a violation by pointing at the offending characters, or it abstains.

That means most preferences are NOT measurable by this tool, and that is the
honest and intended outcome. "Lead with the answer, not reasoning" and "raise
the altitude" are real preferences that no regex can adjudicate. This tool
reports them as UNMEASURABLE rather than inventing a number — a smaller true
signal beats a large fabricated one. Coverage is deliberately a floor to grow,
not a percentage to maximise; treating it as a target would recreate the exact
Goodhart failure the self-graded rubric already demonstrated.

VERDICTS, per preference, per session:
    compliant     detector ran, found zero violations
    violated      detector ran, found >=1 violation (evidence attached)
    unmeasurable  no deterministic detector exists for this preference

Usage:
    tastegraph_compliance.py check --transcript FILE [--json]
    tastegraph_compliance.py check --session-id ID [--json]
    tastegraph_compliance.py score --transcript FILE     # single float for accounting
    tastegraph_compliance.py detectors                   # what is measurable at all
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from tastegraph_vector import find_spoke_root, resolve_hub_path, _collect_prefs
except ImportError:  # pragma: no cover
    print("[compliance] FATAL: tastegraph_vector.py not importable", file=sys.stderr)
    raise

# Fenced code blocks and the wakeup banner are STRUCTURED OUTPUT, not prose.
# Several detectors must ignore them or they fire on legitimate tool output and
# ASCII banners the operator explicitly asks for.
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
BOX_RE = re.compile(r"^[│┌└├─╭╰|].*$", re.MULTILINE)

# Emoji ranges. The operator's no-emoji rule carries an explicit s138 exemption
# for status indicators and confidence bars, so those code points are excluded
# from the violation set rather than reported and hand-waved away.
EXEMPT_EMOJI = set("🟩🟥🟨⬜⬛🔴🟡🟢🔵⚪⚠✓✗")
EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")


def strip_structured(text):
    """Remove fenced blocks and box-drawing lines — structure, not prose."""
    return BOX_RE.sub("", FENCE_RE.sub("", text))


# ---- detectors --------------------------------------------------------------
# Each returns a list of violations: {"evidence": str, "note": str}.
# A detector MUST NOT guess. If it cannot prove a violation, it returns [].

def d_no_markdown_headings(text, _pref):
    """communication-message-format: no_headings."""
    out = []
    for line in strip_structured(text).splitlines():
        if re.match(r"^#{1,6}\s+\S", line):
            out.append({"evidence": line.strip()[:120], "note": "markdown heading"})
    return out


def d_no_code_blocks(text, _pref):
    """communication-message-format: no_code_blocks_in_user_messages."""
    return [{"evidence": m.group(0)[:80].replace("\n", "\\n"),
             "note": "fenced code block in a user-facing message"}
            for m in FENCE_RE.finditer(text)]


def d_no_bold_markdown(text, _pref):
    """communication-message-format: formatting plain_text_only.

    bold_usage allows 'navigation_anchors_only', so this counts occurrences and
    only reports when bold is clearly being used as general emphasis (>3 in one
    message). A single bolded anchor is compliant by the preference's own terms.
    """
    hits = re.findall(r"\*\*[^*\n]{1,80}\*\*", strip_structured(text))
    if len(hits) > 3:
        return [{"evidence": ", ".join(h[:30] for h in hits[:4]),
                 "note": f"{len(hits)} bold spans — beyond navigation anchors"}]
    return []


def d_no_emoji_in_prose(text, _pref):
    """taste-user-004, honouring the s138 status-indicator exemption."""
    out = []
    for m in EMOJI_RE.finditer(strip_structured(text)):
        if m.group(0) not in EXEMPT_EMOJI:
            out.append({"evidence": m.group(0), "note": "emoji in prose"})
    return out


def d_no_context_estimate(text, _pref):
    """taste-user-009: never estimate context percentage."""
    pat = re.compile(r"(context[^.\n]{0,40}?~?\s*\d{1,3}\s*%"
                     r"|~\s*\d{1,3}\s*%[^.\n]{0,20}?context)", re.IGNORECASE)
    return [{"evidence": m.group(0)[:100], "note": "estimated context percentage"}
            for m in pat.finditer(text)]


def d_paragraph_length(text, _pref):
    """accessibility-dyslexia: max_paragraph_sentences = 3."""
    out = []
    for para in re.split(r"\n\s*\n", strip_structured(text)):
        para = para.strip()
        if not para or para.startswith(("-", "*", "|", ">")) or re.match(r"^\d+\.", para):
            continue
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()]
        if len(sentences) > 3:
            out.append({"evidence": para[:100],
                        "note": f"{len(sentences)} sentences in one paragraph (max 3)"})
    return out


def d_closing_names_exit_action(text, _pref):
    """communication-closing-format-rules: closings name savepoint/closeout/exit.

    Only evaluated on a CLOSING message (the last visible block of a turn), which
    the caller marks. Never fires mid-turn.
    """
    tail = "\n".join(text.strip().splitlines()[-6:]).lower()
    if re.search(r"savepoint|closeout|ready to exit|close out", tail):
        return []
    return [{"evidence": tail[-120:],
             "note": "closing does not name savepoint/closeout/exit"}]


def d_statusline_model_resolved(text, _pref):
    """Statusline must carry the hook-supplied model, never the turn-1 placeholder.

    Caught live in s138: the hook resolved claude-opus-4-8 from turn 2 onward and
    supplied it in the statusline template every turn, but the agent kept copying
    turn 1's rendering — where "unknown" was legitimately correct, because no
    assistant message existed yet to read a model from. Six turns of tracks were
    stamped with a stale value the pipeline had already fixed.

    The failure is invisible to the track writer (the buffer held the RIGHT model
    all along) and only shows in what the operator reads. So it needs a detector
    on the rendered text, not a check on the data.
    """
    out = []
    for line in text.strip().splitlines():
        if not re.match(r"^Turn \d+ \|", line.strip()):
            continue
        if re.search(r"\|\s*unknown\s*\|", line):
            out.append({"evidence": line.strip()[:120],
                        "note": "statusline model is 'unknown' — stale copy of the "
                                "turn-1 render; re-read the hook's line each turn"})
    return out


def d_ask_comes_last(text, _pref):
    """communication-action-then-ask: the ask is the FINAL visible line.

    Provable form only: find the last line ending in a question mark, then
    measure how much SUBSTANTIAL prose follows it. Statuslines, box-drawing,
    confidence bars and short trailing lines are excluded — they are chrome, not
    work output. Anything past ~400 characters of real prose after the ask means
    the operator has to scroll back up to find the question, which is the exact
    failure this preference names.
    """
    lines = strip_structured(text).splitlines()
    last_q = -1
    for i, line in enumerate(lines):
        if line.strip().endswith("?"):
            last_q = i
    if last_q < 0:
        return []
    trailing = 0
    for line in lines[last_q + 1:]:
        s = line.strip()
        if not s or len(s) < 40 or re.match(r"^Turn \d+ \|", s):
            continue
        trailing += len(s)
    if trailing > 400:
        return [{"evidence": lines[last_q].strip()[:100],
                 "note": f"{trailing} chars of prose follow the ask — "
                         "the question is not the last line"}]
    return []


def d_no_windows_code_paths(text, _pref):
    """aesthetic-file-organization: canonical paths, never /mnt/c/code/."""
    return [{"evidence": m.group(0), "note": "non-canonical /mnt/c/code path"}
            for m in re.finditer(r"/mnt/c/code/\S*", text)]


def d_no_macos_tooling(text, _pref):
    """taste-user-006: WSL2 on Windows — never suggest macOS tooling."""
    pat = re.compile(r"\b(brew install|brew tap|pbcopy|pbpaste|"
                     r"defaults write|open -a )\S*", re.IGNORECASE)
    return [{"evidence": m.group(0)[:80], "note": "macOS-only tooling suggested"}
            for m in pat.finditer(strip_structured(text))]


def d_no_typo_flagging(text, _pref):
    """communication-typo-tolerance: never call attention to the operator's typos."""
    pat = re.compile(
        r"(did you mean\b|you (probably |likely )?meant\b|"
        r"(i )?(assume|think|presume) you meant\b|typo in your\b)",
        re.IGNORECASE)
    return [{"evidence": m.group(0)[:80], "note": "flagged an operator typo"}
            for m in pat.finditer(strip_structured(text))]


def d_no_reference_by_label(text, _pref):
    """communication-self-contained-restatement: never point at history.

    The preference is explicit that referring to something by label ('decision
    #1', 'as I mentioned earlier') and sending the operator back through history
    is a defect. Those phrasings are literal strings, so this is provable without
    judging whether the surrounding restatement was adequate.
    """
    pat = re.compile(
        r"(as (i )?(mentioned|noted|said|described|explained) (earlier|above|before)"
        r"|as discussed (earlier|above|previously)"
        r"|see above\b|per my (earlier|previous)\b"
        r"|refer back to\b|decision #\d)", re.IGNORECASE)
    return [{"evidence": m.group(0)[:80],
             "note": "reference-by-label — sends the operator into history"}
            for m in pat.finditer(strip_structured(text))]


def d_no_preamble(text, _pref):
    """taste-user-001: lead with the answer — no preamble, no filler.

    Only the OPENING of a block is examined, and only against a closed list of
    pure-filler openers that carry no information. A conservative list keeps this
    honest: an opener that might be substantive is not counted.
    """
    first = strip_structured(text).strip().splitlines()
    if not first:
        return []
    head = first[0].strip()[:60]
    pat = re.compile(
        r"^(great question|good question|great!|sure[,!.]|certainly[,!.]|"
        r"absolutely[,!.]|of course[,!.]|i'd be happy to|happy to help|"
        r"i'll help you|let me start by|let's dive in)", re.IGNORECASE)
    if pat.match(head):
        return [{"evidence": head, "note": "filler preamble before the answer"}]
    return []


def d_no_permission_ask_for_safe_ops(text, _pref):
    """communication-register: never ask permission for safe operations.

    Narrow on purpose. Asking before a destructive action is CORRECT, so this
    fires only when permission is sought for a read-only verb — where the
    preference admits no exception and the violation is unambiguous.
    """
    pat = re.compile(
        r"\b(want me to|should i|shall i|would you like me to)\s+"
        r"(check|look|read|show|list|inspect|search|grep|find|display|survey)\b",
        re.IGNORECASE)
    return [{"evidence": m.group(0)[:80],
             "note": "asked permission for a read-only operation"}
            for m in pat.finditer(strip_structured(text))]


# pref_id -> (detector, closing_only)
DETECTORS = {
    "wai-track-statusline-fidelity": (d_statusline_model_resolved, False),
    "communication-message-format": (d_no_markdown_headings, False),
    "taste-user-004": (d_no_emoji_in_prose, False),
    "taste-user-009": (d_no_context_estimate, False),
    "accessibility-dyslexia": (d_paragraph_length, False),
    "communication-closing-format-rules": (d_closing_names_exit_action, True),
    "communication-action-then-ask": (d_ask_comes_last, False),
    "aesthetic-file-organization": (d_no_windows_code_paths, False),
    "taste-user-006": (d_no_macos_tooling, False),
    "communication-typo-tolerance": (d_no_typo_flagging, False),
    "communication-self-contained-restatement": (d_no_reference_by_label, False),
    "taste-user-001": (d_no_preamble, False),
    "communication-register": (d_no_permission_ask_for_safe_ops, False),
}

# Sub-detectors that share the message-format preference id.
EXTRA_FORMAT_DETECTORS = [d_no_code_blocks, d_no_bold_markdown]


# ---- transcript -------------------------------------------------------------

def load_transcript(path):
    """Return the ordered list of assistant-visible text blocks.

    Tool calls, tool results, thinking and user turns are all excluded — the
    preference set governs what the OPERATOR reads, so grading anything else
    would measure the wrong surface.
    """
    blocks = []
    with open(path) as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "assistant":
                continue
            content = (d.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for blk in content:
                if blk.get("type") == "text" and blk.get("text", "").strip():
                    blocks.append(blk["text"])
    return blocks


def find_transcript(session_id, spoke_root):
    """Locate a transcript by session id under the Claude projects dir."""
    home = os.path.expanduser("~/.claude/projects")
    for path in glob.glob(os.path.join(home, "*", f"{session_id}*.jsonl")):
        return path
    return None


def graph_path(spoke_root):
    local = os.path.join(spoke_root, "WAI-Harness", "spoke", "local")
    return os.path.join(resolve_hub_path(spoke_root, local), "local",
                        "tastegraph-org.json")


def evaluate(blocks, prefs):
    """Run every detector over every block. Deterministic; no model involved."""
    results = {}
    # A "closing" is the last SUBSTANTIAL block. Mid-turn narration ("Running
    # the suite now.") is the last block whenever a transcript is read live, and
    # grading it as a closing would manufacture a violation from an artifact of
    # when the tool happened to run. Short trailing blocks are skipped.
    closing_idx = -1
    for i in range(len(blocks) - 1, -1, -1):
        if len(blocks[i].strip()) >= 400:
            closing_idx = i
            break

    for pref in prefs:
        pid = pref.get("id")
        entry = DETECTORS.get(pid)
        if not entry:
            results[pid] = {"verdict": "unmeasurable", "violations": [],
                            "reason": "no deterministic detector exists"}
            continue

        fn, closing_only = entry
        violations = []
        for i, text in enumerate(blocks):
            if closing_only and i != closing_idx:
                continue
            for v in fn(text, pref):
                violations.append({**v, "block": i})
            if pid == "communication-message-format":
                for extra in EXTRA_FORMAT_DETECTORS:
                    for v in extra(text, pref):
                        violations.append({**v, "block": i})

        results[pid] = {
            "verdict": "violated" if violations else "compliant",
            "violations": violations[:20],
            "violation_count": len(violations),
        }
    return results


def summarise(results):
    counts = {"compliant": 0, "violated": 0, "unmeasurable": 0}
    for r in results.values():
        counts[r["verdict"]] += 1
    measured = counts["compliant"] + counts["violated"]
    return {
        "counts": counts,
        "measured": measured,
        "total": len(results),
        # Score is over MEASURED preferences only. Averaging in unmeasurable
        # ones as passes would manufacture a flattering number out of silence.
        "score": round(counts["compliant"] / measured, 4) if measured else None,
        "coverage": round(measured / len(results), 4) if results else 0.0,
    }


# ---- commands ---------------------------------------------------------------

def resolve_blocks(args, spoke_root):
    path = args.transcript
    if not path and args.session_id:
        path = find_transcript(args.session_id, spoke_root)
    if not path or not os.path.isfile(path):
        print(f"[compliance] transcript not found: {path or args.session_id}",
              file=sys.stderr)
        return None, None
    return load_transcript(path), path


def cmd_check(args, spoke_root):
    blocks, path = resolve_blocks(args, spoke_root)
    if blocks is None:
        return 2
    prefs = _collect_prefs(json.load(open(graph_path(spoke_root))), [])
    results = evaluate(blocks, prefs)
    summary = summarise(results)

    if args.json:
        print(json.dumps({"transcript": path, "blocks": len(blocks),
                          "summary": summary, "results": results},
                         indent=2, ensure_ascii=False))
        return 0

    c = summary["counts"]
    print(f"TasteGraph compliance — {os.path.basename(path)} ({len(blocks)} blocks)")
    print(f"  compliant {c['compliant']}  violated {c['violated']}  "
          f"unmeasurable {c['unmeasurable']}")
    score = summary["score"]
    print(f"  score {score if score is not None else 'n/a'} "
          f"(over {summary['measured']} measured of {summary['total']})")
    print(f"  coverage {summary['coverage']:.0%} — the rest carry NO deterministic")
    print("           detector and are reported unmeasurable, never assumed passing")
    for pid, r in sorted(results.items()):
        if r["verdict"] == "violated":
            print(f"\n  VIOLATED {pid} ({r['violation_count']})")
            for v in r["violations"][:3]:
                print(f"    - {v['note']}: {v['evidence'][:90]}")
    return 1 if c["violated"] else 0


def cmd_score(args, spoke_root):
    """Single float for tastegraph_accounting.py to consume. None if unmeasured."""
    blocks, _ = resolve_blocks(args, spoke_root)
    if blocks is None:
        return 2
    prefs = _collect_prefs(json.load(open(graph_path(spoke_root))), [])
    summary = summarise(evaluate(blocks, prefs))
    print(json.dumps({"score": summary["score"], "coverage": summary["coverage"],
                      "measured": summary["measured"]}))
    return 0


def cmd_detectors(args, spoke_root):
    print(f"Deterministic detectors: {len(DETECTORS)}")
    for pid, (fn, closing_only) in sorted(DETECTORS.items()):
        scope = "closing only" if closing_only else "every message"
        print(f"  {pid:42s} {scope:14s} {fn.__doc__.splitlines()[0]}")
    print("\nEvery other preference is UNMEASURABLE by this tool and is reported")
    print("as such. Coverage is a floor to raise by writing detectors, never a")
    print("target to optimise — a fabricated score is worse than an honest gap.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="TasteGraph compliance oracle")
    ap.add_argument("--spoke-path")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("check", "score"):
        s = sub.add_parser(name)
        s.add_argument("--transcript")
        s.add_argument("--session-id")
        if name == "check":
            s.add_argument("--json", action="store_true")

    sub.add_parser("detectors")

    args = ap.parse_args(argv)
    spoke_root = find_spoke_root(args.spoke_path)
    return {"check": cmd_check, "score": cmd_score,
            "detectors": cmd_detectors}[args.cmd](args, spoke_root)


if __name__ == "__main__":
    sys.exit(main())
