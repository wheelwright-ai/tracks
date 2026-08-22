#!/usr/bin/env python3
"""Retrospective intelligence: find the patterns nobody asked about.

OPERATOR DIRECTIVE 2026-08-17:

    "I expect you to find these patterns and best practices not me and thats really
     got to be a fundamental job of Ozi and Otto - see the patterns, understand their
     impact, evolve - repeat. Retrospective intelligence should be a thing we can
     leverage here to look back and learn lessons from our tracked session and data."

WHY THIS EXISTS. On 2026-08-17 a human asked whether a design made sense, and the
answer came from measuring 1,849 tracked turns by hand: fields a MECHANISM writes
land at 85%, fields an AGENT is asked to write land at 47%, and in 1,849 turns there
was not one where agent discipline succeeded without the mechanism having already
fired. That single number reshaped the design.

Nothing found it. A person asked, and someone went and looked. Every insight in that
session arrived the same way, which means the rate of learning is bounded by how
often the operator thinks to ask -- and he has said plainly that this is not his job.

WHAT A LENS MUST DO, and these are refusals, not preferences:

  1. ANSWER A QUESTION NOBODY ASKED. A lens that reports "3182 tests pass" is a
     dashboard. A lens that reports "24 of those tests stopped existing and the count
     still went green" is intelligence. Report the thing that would not have been
     noticed.

  2. CARRY ITS OWN REPRODUCTION. Every finding ships the exact command that
     regenerates its number. A claim a human cannot re-run is a claim they must take
     on faith, and this harness has spent a night learning what unverified green is
     worth.

  3. SAY UNKNOWN. A lens with insufficient data returns UNKNOWN, never a reassuring
     zero. Tonight's most expensive bug was a gate answering "all 0 verify step(s)
     observed to hold" -- a sentence that reads like a pass and means the opposite.

  4. NAME THE IMPACT, NOT THE METRIC. "47% compliance" is a number. "Anything built
     on agent discipline will run at 47%" is a finding. The second one changes a
     decision.

WHAT IT DOES NOT DO. It does not fix anything, file anything, or decide anything. It
reports. Acting on a finding is a lug, authored deliberately, because a tool that
both diagnoses and treats will eventually treat something it misdiagnosed.

USAGE
  retro_scan.py                      # every lens, human-readable
  retro_scan.py --json               # machine-readable, for Ozi/Otto
  retro_scan.py --lens contract      # one lens
  retro_scan.py --list               # what lenses exist and what each asks
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SPOKE_ROOT = TOOLS.parents[3]

# Severity is about what the finding CHANGES, not how bad it sounds.
CRITICAL = "CRITICAL"   # a belief the wheel currently holds is false
HIGH = "HIGH"           # a decision would change if you knew this
MEDIUM = "MEDIUM"       # worth knowing, does not redirect work today
INFO = "INFO"
UNKNOWN = "UNKNOWN"     # not enough data. NEVER a zero dressed as health.

_LENSES = {}


def lens(name, question):
    def deco(fn):
        fn.lens_name = name
        fn.question = question
        _LENSES[name] = fn
        return fn
    return deco


def finding(lens_name, severity, headline, detail, evidence_cmd, value=None):
    return {"lens": lens_name, "severity": severity, "headline": headline,
            "detail": detail, "reproduce": evidence_cmd, "value": value}


def _git(root, *args):
    try:
        p = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                           text=True, timeout=120)
        return p.stdout if p.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _track_turns(root):
    """Every tracked turn on this spoke. Malformed lines are skipped, not fatal."""
    out = []
    for f in glob.glob(str(Path(root) / "WAI-Harness/spoke/local/sessions/*/track.jsonl")):
        for line in open(f, encoding="utf-8", errors="replace"):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict) and "turn" in d:
                out.append(d)
    return out


def _lugs(root):
    out = []
    for base in ("WAI-Harness/spoke/local/lugs/bytype", "WAI-Spoke/work"):
        p = Path(root) / base
        if not p.is_dir():
            continue
        for f in p.rglob("*.json"):
            if ".worktrees" in str(f):
                continue
            try:
                d = json.load(open(f, encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if isinstance(d, dict) and d.get("id"):
                out.append(d)
    return out


# --------------------------------------------------------------------------- lenses

@lens("contract", "Which per-turn obligations actually land, and which are decoration?")
def lens_contract(root):
    turns = _track_turns(root)
    if len(turns) < 50:
        return [finding("contract", UNKNOWN,
                        f"only {len(turns)} tracked turns — too few to characterise",
                        "Compliance rates over a small sample say more about the sample "
                        "than the contract.",
                        "count lines across sessions/*/track.jsonl")]
    fields = ["user_msg", "user_intent", "action", "outcome", "thinking", "focus", "phase"]
    have = collections.Counter()
    for t in turns:
        for k in fields:
            if t.get(k) not in (None, "", [], {}):
                have[k] += 1
    n = len(turns)
    pct = {k: 100 * have[k] / n for k in fields}

    # The split that matters: a field a hook computes vs a field an agent is asked for.
    mech = pct.get("user_intent", 0)
    agent = sorted(v for k, v in pct.items() if k != "user_intent")
    median_agent = agent[len(agent) // 2] if agent else 0
    gap = mech - median_agent

    both = sum(1 for t in turns if t.get("user_intent") and t.get("thinking"))
    agent_only = sum(1 for t in turns if t.get("thinking") and not t.get("user_intent"))

    out = []
    if gap >= 20:
        out.append(finding(
            "contract", CRITICAL,
            f"instructed behaviour runs at {median_agent:.0f}%, computed behaviour at {mech:.0f}%",
            f"Across {n} turns, the one field a hook writes (user_intent) lands at "
            f"{mech:.0f}%. Every field the AGENT is asked to write clusters at "
            f"{median_agent:.0f}%. Same contract, same injection, every turn.\n"
            f"    Turns where agent discipline succeeded WITHOUT the mechanism: {agent_only}.\n"
            f"    IMPACT: anything designed as an instruction should be costed at "
            f"~{median_agent:.0f}% adoption, not 100%. Anything that must be reliable "
            f"has to be computed, or has to ride an artifact the agent already produces.",
            "retro_scan.py --lens contract",
            {"mechanism_pct": round(mech), "agent_pct": round(median_agent),
             "turns": n, "agent_only_turns": agent_only, "both": both}))
    return out


@lens("provenance", "Can we prove what is in the product, or only that it changed?")
def lens_provenance(root):
    gate = Path(root) / "WAI-Harness/spoke/managed/tools/lug_provenance_gate.py"
    if not gate.is_file():
        return [finding("provenance", UNKNOWN, "provenance gate not present",
                        "Cannot assess traceability without it.", "ls " + str(gate))]
    base_f = Path(root) / "WAI-Harness/spoke/local/runtime/provenance-baseline.json"
    debt = None
    if base_f.is_file():
        try:
            debt = (json.load(open(base_f, encoding="utf-8")) or {}).get("accepted_debt")
        except (ValueError, OSError):
            debt = None
    p = subprocess.run([sys.executable, str(gate), "--repo-root", str(root),
                        "--since-baseline"], capture_output=True, text=True, timeout=300)
    out = []
    if p.returncode != 0:
        n = p.stdout.count("\n  ")
        out.append(finding(
            "provenance", HIGH,
            f"{n} commit(s) since the baseline changed distributed source with no lug",
            "These changes exist only as commit messages. No dispatch surface can see "
            "them, the PathGraph does not index them, and 'what is in the product' "
            "becomes an archaeology dig rather than a query.",
            "lug_provenance_gate.py --repo-root . --since-baseline", {"new_violations": n}))
    if debt:
        out.append(finding(
            "provenance", MEDIUM,
            f"{debt} pre-existing commits are accepted debt, not clean",
            "Recorded in the baseline because clearing them means rewriting commit "
            "messages, which destroys history to satisfy a lint. They are invisible to "
            "every dispatch surface until somebody pays them down.",
            "cat WAI-Harness/spoke/local/runtime/provenance-baseline.json",
            {"accepted_debt": debt}))
    return out


@lens("vacuity", "How much of what we believe is done was actually checked?")
def lens_vacuity(root):
    lugs = _lugs(root)
    if not lugs:
        return [finding("vacuity", UNKNOWN, "no lugs found", "", "ls lugs/bytype")]
    done = {"completed", "resolved", "implemented", "published"}
    finished = [l for l in lugs if l.get("status") in done]
    unevidenced = [l for l in finished if not (l.get("verify") or [])]
    if not finished:
        return [finding("vacuity", UNKNOWN, "no finished lugs to assess", "",
                        "retro_scan.py --lens vacuity")]
    pct = 100 * len(unevidenced) / len(finished)
    sev = CRITICAL if pct >= 40 else HIGH if pct >= 15 else MEDIUM
    return [finding(
        "vacuity", sev,
        f"{len(unevidenced)} of {len(finished)} finished lugs ({pct:.0f}%) carry no verify steps",
        "A lug with no verify steps cannot be certified by anything. Its completion "
        "rests entirely on an agent's say-so, which is the claim the certifier exists "
        "to refuse. These are not failures -- they are unfalsifiable.",
        "retro_scan.py --lens vacuity",
        {"finished": len(finished), "unevidenced": len(unevidenced), "pct": round(pct)})]


@lens("landing", "Do we finish what we start, or accumulate?")
def lens_landing(root):
    lugs = _lugs(root)
    if len(lugs) < 20:
        return [finding("landing", UNKNOWN, f"only {len(lugs)} lugs", "",
                        "retro_scan.py --lens landing")]
    st = collections.Counter(l.get("status", "?") for l in lugs)
    done = sum(v for k, v in st.items()
               if k in ("completed", "resolved", "implemented", "published"))
    openish = sum(v for k, v in st.items()
                  if k in ("open", "ready", "draft", "in_progress", "ready_for_recheck",
                           "needs_attention", "blocked"))
    if not openish:
        return []
    ratio = done / openish
    sev = HIGH if ratio < 0.5 else MEDIUM
    return [finding(
        "landing", sev,
        f"{done} landed against {openish} still open — {ratio:.2f} finished per open",
        "The operator's standing complaint is that work is generated faster than it "
        "lands. This is that ratio. It is a backlog measurement, not a judgement about "
        "generation rate.\n    Top states: "
        + ", ".join(f"{k}={v}" for k, v in st.most_common(5)),
        "retro_scan.py --lens landing",
        {"done": done, "open": openish, "ratio": round(ratio, 2)})]


@lens("silent", "Did anything succeed loudly while failing quietly?")
def lens_silent(root):
    """Green states that were not earned. The hardest class to see, so the lens is
    narrow on purpose: it looks for reverts of test files, which is the specific way a
    suite can go green by having fewer tests rather than more passing ones."""
    log = _git(root, "log", "--format=%H|%s", "-400")
    hits = []
    for line in log.splitlines():
        if "|" not in line:
            continue
        sha, subj = line.split("|", 1)
        if not any(w in subj.lower() for w in ("revert", "restore", "out-of-lane")):
            continue
        # --diff-filter=D, NOT --name-only. The first cut of this lens listed every
        # test file a revert-ish commit TOUCHED, and scored 1 real hit in 5: two of
        # the flagged commits ADDED tests (they were the fixes), and two touched no
        # tests at all and matched only on the word "revert" in the subject.
        #
        # A lens at 20% precision is worse than no lens. It trains the reader to skim
        # the CRITICAL line, which is exactly the habit that let a real 24-test
        # deletion pass for health.
        stat = _git(root, "show", "--diff-filter=D", "--name-only", "--format=", sha)
        deleted_tests = [p for p in stat.splitlines()
                         if p.strip().endswith(".py") and "/tests/" in p]
        if deleted_tests:
            hits.append((sha[:9], subj[:70], len(deleted_tests)))
    if not hits:
        return []
    return [finding(
        "silent", CRITICAL,
        f"{len(hits)} revert commit(s) touched test files",
        "A revert that removes tests makes the suite go green by shrinking it. The pass "
        "count rises or holds while coverage falls, and nothing reports an error. "
        "Measured on this spoke 2026-08-17: a lane-guard revert deleted 24 tests and "
        "the suite reported 3182 passing, which looked like health.\n    "
        + "\n    ".join(f"{s} ({n} test file(s)) {m}" for s, m, n in hits[:5]),
        "retro_scan.py --lens silent", {"revert_commits_touching_tests": len(hits)})]


@lens("threads", "Do open questions get resolved, or do they just stop being mentioned?")
def lens_threads(root):
    turns = _track_turns(root)
    withopen = [t for t in turns if t.get("open")]
    if len(turns) < 50:
        return [finding("threads", UNKNOWN, f"only {len(turns)} turns", "",
                        "retro_scan.py --lens threads")]
    pct = 100 * len(withopen) / len(turns)
    return [finding(
        "threads", MEDIUM if pct >= 40 else HIGH,
        f"{len(withopen)} of {len(turns)} turns ({pct:.0f}%) recorded an open thread",
        "An open item that stops being written is indistinguishable from one that was "
        "resolved. Every turn without this field is a turn whose loose ends left no "
        "trace for the next session -- the gap between a savepoint that is insurance "
        "and one that is a filing cabinet.",
        "retro_scan.py --lens threads",
        {"turns": len(turns), "with_open": len(withopen), "pct": round(pct)})]


# ----------------------------------------------------------------------------- main

def run(root, only=None):
    out = []
    for name, fn in _LENSES.items():
        if only and name != only:
            continue
        try:
            out.extend(fn(root) or [])
        except Exception as exc:                       # a broken lens is a finding
            out.append(finding(name, UNKNOWN, f"lens '{name}' failed: {exc}",
                               "A lens that cannot run is not a clean result.",
                               f"retro_scan.py --lens {name}"))
    order = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, INFO: 3, UNKNOWN: 4}
    out.sort(key=lambda f: order.get(f["severity"], 9))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(SPOKE_ROOT))
    ap.add_argument("--lens")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        for n, fn in _LENSES.items():
            print(f"  {n:12s} {fn.question}")
        return 0

    findings = run(Path(args.root).resolve(), args.lens)
    if args.json:
        print(json.dumps({"findings": findings, "count": len(findings)}, indent=1))
        return 0

    if not findings:
        print("retro: no findings. That is a result about the LENSES as much as the "
              "spoke -- add a lens before reading it as health.")
        return 0

    print(f"\nRETROSPECTIVE SCAN — {len(findings)} finding(s)\n")
    for f in findings:
        print(f"[{f['severity']}] {f['headline']}")
        for line in f["detail"].splitlines():
            print(f"    {line}")
        print(f"    reproduce: {f['reproduce']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
