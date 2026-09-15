#!/usr/bin/env python3
"""alignment_advisor.py — what does a session COST before any work happens?

Basher's advisor for session-boundary overhead: the tokens the harness injects
and the seconds it spends starting and ending a session. Measure + report + lug;
it changes nothing itself, for the same reason the other advisors don't — an
advisor that edits the hooks it measures can hide its own regressions.

WHY THIS EXISTS (measured 2026-08-21, basher session-20260821-1724, 10 turns):

    SessionStart wai-session-init   88,556 B   ~22,139 tok   once
    per-turn tastegraph-vector      20,750 B    ~5,187 tok   EVERY TURN
    per-turn wai-track-turn            937 B      ~234 tok   every turn
    per-turn wai-voice-contract        727 B      ~181 tok   every turn
                                               ~78,000 tok   session total

Turn 1 and turn 10 payloads were 99.9% byte-identical (22,398 of 22,416 bytes).
~56,000 tokens were spent re-sending text that was already in context. Nothing
was broken and nothing errored, which is precisely why it ran for months: cost
has no failure mode, so only a measurement finds it.

BUDGETS ARE DERIVED, NOT DECLARED. The baseline is the median of prior recorded
sessions; a breach is a regression against what this spoke actually achieves,
not against a constant someone typed once. A hardcoded "known-good" number
eventually asserts the bug (see the zjstatus gate that defended an OOM build
through three recurrences). The absolute ceilings below are a backstop for the
cold-start case where there is no history yet, and they are deliberately loose.

USAGE
    alignment_advisor.py measure [--session ID] [--json]   # record one session
    alignment_advisor.py report  [--json]                  # baseline vs latest
    alignment_advisor.py check   [--lug]                   # breach -> exit 1 (+ file a lug)
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

def _repo_root() -> Path:
    """Walk up to the spoke root, don't assume a fixed depth.

    This tool ships in TWO places: tools/ in the spoke root, and
    WAI-Harness/spoke/managed/tools/ once it travels through the harness. A fixed
    parent.parent resolved to .../spoke/managed from the managed copy, so BASE and
    the ledger pointed nowhere and `report` printed "no measurements yet" while a
    populated ledger sat on disk. A tool that reports absence when the data exists
    is worse than one that crashes -- it looks like a clean bill of health. Anchor
    on something real instead of on depth."""
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "WAI-Harness" / "spoke" / "local").is_dir():
            return p
        if (p / ".git").exists() and (p / "WAI-Harness").is_dir():
            return p
    return here.parent.parent


REPO = _repo_root()
BASE = REPO / "WAI-Harness" / "spoke" / "local"
LEDGER = BASE / "runtime" / "alignment-ledger.jsonl"

# Cold-start backstops only. Once >=3 sessions are recorded the derived baseline
# governs and these stop mattering. Loose on purpose: a tight constant here would
# fire on healthy variation and train everyone to ignore the advisor.
CEILING_SESSION_TOKENS = 120_000
CEILING_PER_TURN_TOKENS = 6_000
CEILING_EXIT_MS = 12_000

REGRESSION_PCT = 20  # % worse than baseline before it counts as a breach
MIN_HISTORY = 3      # sessions needed before the derived baseline is trusted


# ─────────────────────────────── measurement ────────────────────────────────

def _tok(nbytes: int) -> int:
    """Byte->token estimate. Deliberately crude and deliberately STATED as an
    estimate everywhere it surfaces: a precise-looking number nobody can verify
    is worse than an honest approximation."""
    return nbytes // 4


def _transcript_dir(session_uuid: str | None) -> Path | None:
    slug = str(REPO).replace("/", "-").replace(".", "-")
    root = Path.home() / ".claude" / "projects" / slug
    if not root.is_dir():
        return None
    if session_uuid:
        d = root / session_uuid / "tool-results"
        return d if d.is_dir() else None
    cands = [p for p in root.glob("*/tool-results") if p.is_dir()]
    return max(cands, key=lambda p: p.stat().st_mtime) if cands else None


def measure_payloads(session_uuid: str | None) -> dict:
    """Hook payloads big enough that Claude Code spilled them to disk.

    This UNDERCOUNTS: small payloads are inlined and never persisted, so they are
    invisible here. Reported as `floor`, never as `total`, so nobody reads it as
    the whole story."""
    d = _transcript_dir(session_uuid)
    out = {"payload_dir": str(d) if d else None, "session_start_bytes": 0,
           "per_turn_bytes": [], "measured": False}
    if not d:
        return out
    files = sorted(glob.glob(str(d / "hook-*-stdout.txt")), key=os.path.getmtime)
    if not files:
        return out
    sizes = [(f, os.path.getsize(f)) for f in files]
    # SessionStart is the one carrying wai-session-init; everything else is per-turn.
    for f, n in sizes:
        try:
            head = open(f, encoding="utf-8", errors="replace").read(4096)
        except OSError:
            continue
        if "wai-session-init" in head or "WAI Track v" in head and "session-start-once" in head:
            out["session_start_bytes"] = max(out["session_start_bytes"], n)
        else:
            out["per_turn_bytes"].append(n)
    if not out["session_start_bytes"] and sizes:
        biggest = max(sizes, key=lambda t: t[1])
        out["session_start_bytes"] = biggest[1]
        out["per_turn_bytes"] = [n for f, n in sizes if f != biggest[0]]
    out["measured"] = True
    return out


def measure_redundancy(session_uuid: str | None) -> dict:
    """How much of a per-turn payload is the SAME as the previous one.

    This is the number that matters. Payload size alone is not waste -- text the
    model has not seen is worth its tokens. Text it saw last turn is not."""
    d = _transcript_dir(session_uuid)
    res = {"comparable": False, "identical_pct": None, "static_tokens_resent": 0}
    if not d:
        return res
    files = sorted(
        [f for f in glob.glob(str(d / "hook-*-stdout.txt")) if os.path.getsize(f) < 60_000],
        key=os.path.getmtime,
    )
    if len(files) < 2:
        return res
    import difflib
    a = open(files[0], encoding="utf-8", errors="replace").read()
    b = open(files[-1], encoding="utf-8", errors="replace").read()
    if not a:
        return res
    sm = difflib.SequenceMatcher(None, a, b)
    same = sum(bl.size for bl in sm.get_matching_blocks())
    pct = 100.0 * same / len(a)
    total = sum(os.path.getsize(f) for f in files)
    res.update(comparable=True, identical_pct=round(pct, 1),
               static_tokens_resent=_tok(int(total * pct / 100)), turns=len(files))
    return res


def measure_exit_ms() -> dict:
    """Mean exit wall-clock from the timing ledger wai-exit already writes."""
    p = BASE / "runtime" / "exit-timing.jsonl"
    res = {"recorded_exits": 0, "mean_exit_ms": None, "slowest_step": None}
    if not p.exists():
        return res
    agg: dict[str, list[int]] = {}
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        step, ms = r.get("step"), r.get("ms")
        if step and isinstance(ms, (int, float)):
            agg.setdefault(step, []).append(ms)
    if not agg:
        return res
    means = {k: statistics.mean(v) for k, v in agg.items()}
    slow = max(means.items(), key=lambda kv: kv[1])
    res.update(recorded_exits=len(agg.get("PUSH", [])) or len(next(iter(agg.values()))),
               mean_exit_ms=round(sum(means.values())),
               slowest_step={"step": slow[0], "mean_ms": round(slow[1])},
               steps={k: round(v) for k, v in sorted(means.items(), key=lambda kv: -kv[1])})
    return res


def measure_startup_shape() -> dict:
    """Fork count in the wakeup hook. A proxy for startup latency that costs
    nothing to compute and does not require running the hook (running it would
    mutate live session state -- never measure by side effect)."""
    hook = REPO / ".claude" / "hooks" / "wakeup-canonical.sh"
    res = {"hook_present": hook.exists()}
    if not hook.exists():
        return res
    s = hook.read_text(encoding="utf-8", errors="replace")
    res.update(lines=s.count("\n") + 1,
               subshells=len(re.findall(r"\$\(", s)),
               jq_calls=len(re.findall(r"\bjq\b", s)),
               python_calls=len(re.findall(r"python3 ", s)))
    return res


def measure(session_uuid: str | None) -> dict:
    pay = measure_payloads(session_uuid)
    red = measure_redundancy(session_uuid)
    turns = len(pay["per_turn_bytes"])
    per_turn_mean = statistics.mean(pay["per_turn_bytes"]) if pay["per_turn_bytes"] else 0
    floor_bytes = pay["session_start_bytes"] + sum(pay["per_turn_bytes"])
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session_uuid": session_uuid,
        "turns_measured": turns,
        "session_start_tokens": _tok(pay["session_start_bytes"]),
        "per_turn_tokens_mean": _tok(int(per_turn_mean)),
        "session_tokens_floor": _tok(floor_bytes),
        "redundancy": red,
        "exit": measure_exit_ms(),
        "startup": measure_startup_shape(),
        "_note": "token counts are byte/4 ESTIMATES; session_tokens_floor undercounts "
                 "(payloads small enough to be inlined are never persisted to disk)",
    }


# ──────────────────────────────── baseline ──────────────────────────────────

def _history() -> list[dict]:
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def baseline(hist: list[dict]) -> dict | None:
    """Median of prior sessions. Median not mean: one pathological session must
    not move the bar it is being judged against."""
    usable = [h for h in hist if h.get("per_turn_tokens_mean")]
    if len(usable) < MIN_HISTORY:
        return None
    pick = lambda k: [h[k] for h in usable if isinstance(h.get(k), (int, float))]
    return {
        "n": len(usable),
        "per_turn_tokens_mean": statistics.median(pick("per_turn_tokens_mean")),
        "session_start_tokens": statistics.median(pick("session_start_tokens")),
        "mean_exit_ms": statistics.median(
            [h["exit"]["mean_exit_ms"] for h in usable
             if isinstance(h.get("exit", {}).get("mean_exit_ms"), (int, float))] or [0]),
    }


def evaluate(latest: dict, base: dict | None) -> list[dict]:
    """Findings, worst first. Empty list = within budget."""
    f = []
    pt = latest.get("per_turn_tokens_mean") or 0
    ss = latest.get("session_start_tokens") or 0
    ex = (latest.get("exit") or {}).get("mean_exit_ms") or 0
    red = latest.get("redundancy") or {}

    def cmp(name, got, base_key, ceiling, unit):
        if base and base.get(base_key):
            b = base[base_key]
            if b and got > b * (1 + REGRESSION_PCT / 100):
                f.append({"what": name, "got": got, "baseline": b, "unit": unit,
                          "why": f"{round(100 * (got / b - 1))}% worse than the median of "
                                 f"{base['n']} recorded sessions"})
                return
        if ceiling and got > ceiling:
            f.append({"what": name, "got": got, "ceiling": ceiling, "unit": unit,
                      "why": f"over the cold-start ceiling ({ceiling} {unit}); no derived "
                             f"baseline yet ({len(_history())} session(s) recorded, need {MIN_HISTORY})"})

    cmp("per-turn injected tokens", pt, "per_turn_tokens_mean", CEILING_PER_TURN_TOKENS, "tok")
    cmp("SessionStart injected tokens", ss, "session_start_tokens", None, "tok")
    cmp("mean exit wall-clock", ex, "mean_exit_ms", CEILING_EXIT_MS, "ms")

    # The redundancy finding is the one with a cheap fix, so it is stated even
    # when the absolute numbers are within budget.
    if red.get("comparable") and (red.get("identical_pct") or 0) >= 90:
        f.append({"what": "per-turn payload redundancy", "got": red["identical_pct"], "unit": "%",
                  "why": f"first and last turn payloads are {red['identical_pct']}% identical; "
                         f"~{red['static_tokens_resent']:,} tok re-sent across "
                         f"{red.get('turns', '?')} turns. Text already in context is not worth "
                         f"its tokens twice."})
    return f


# ───────────────────────────────── lugging ──────────────────────────────────

def file_lug(findings: list[dict], latest: dict) -> str | None:
    """A breach that nobody can dispatch is a number in a file. Land it."""
    if not findings:
        return None
    lug_id = "impl-basher-alignment-session-overhead-breach-v1"
    d = BASE / "lugs" / "bytype" / "impl" / "open"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{lug_id}.json"
    if path.exists():          # already open; refresh the evidence, don't duplicate
        try:
            lug = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            lug = {}
    else:
        lug = {}
    lines = [f"- {x['what']}: {x['got']}{x.get('unit', '')} — {x['why']}" for x in findings]
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lug.update({
        "id": lug_id, "type": "impl", "status": lug.get("status", "open"), "priority": "P2",
        "impact": 7, "effort_score": 4, "model": "sonnet", "model_fit": "sonnet",
        "routed_to": "LOCAL", "destination_wheel_id": "basher", "from_wheel": "basher",
        "authored_by": "alignment_advisor", "created_at": lug.get("created_at", now),
        "updated_at": now,
        "title": "Session-boundary overhead breached its budget",
        "target_files": [".claude/hooks/user-prompt-submit.sh",
                         ".claude/hooks/wakeup-canonical.sh", "wai-exit.sh"],
        "file_targets": [".claude/hooks/user-prompt-submit.sh",
                         ".claude/hooks/wakeup-canonical.sh", "wai-exit.sh"],
        "perceive": ("alignment_advisor measured this spoke's session-boundary cost and it is "
                     "outside budget. Findings, worst first:\n" + "\n".join(lines) +
                     "\n\nBudgets are DERIVED from the median of prior recorded sessions where "
                     "history allows, so a finding here means this spoke got worse than it has "
                     "actually been -- not worse than a constant someone typed once."),
        "execute": ["Read the finding above and locate which injected block grew, or which exit "
                    "step slowed. runtime/alignment-ledger.jsonl holds the history.",
                    "Fix the cause, not the measurement. If a budget is genuinely wrong, change "
                    "the budget deliberately and say why in the commit -- do not widen it to "
                    "silence a real regression.",
                    "Re-run: python3 tools/alignment_advisor.py measure && "
                    "python3 tools/alignment_advisor.py report"],
        "verify": ["python3 tools/alignment_advisor.py check  # exits 0"],
        "acceptance_criteria": ["The advisor reports within budget against the derived baseline.",
                                "The ledger shows the improvement, not just a changed budget."],
        "evidence": {"measured_at": now, "findings": findings, "latest": latest},
        "notes": "Auto-filed by alignment_advisor. Refreshed in place on re-breach, never duplicated.",
    })
    path.write_text(json.dumps(lug, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(path)


# ────────────────────────────────── render ──────────────────────────────────

def render(latest: dict, base: dict | None, findings: list[dict]) -> str:
    L = []
    A = L.append
    A("ALIGNMENT — session-boundary cost")
    ss, pt = latest.get("session_start_tokens", 0), latest.get("per_turn_tokens_mean", 0)
    turns = latest.get("turns_measured", 0)
    A(f"  SessionStart   ~{ss:,} tok (once)")
    A(f"  Per turn       ~{pt:,} tok  x {turns} turn(s) measured")
    A(f"  Session floor  ~{latest.get('session_tokens_floor', 0):,} tok  (undercounts; see note)")
    red = latest.get("redundancy") or {}
    if red.get("comparable"):
        A(f"  Redundancy     {red['identical_pct']}% of a per-turn payload repeats "
          f"(~{red['static_tokens_resent']:,} tok re-sent)")
    ex = latest.get("exit") or {}
    if ex.get("mean_exit_ms"):
        s = ex.get("slowest_step") or {}
        A(f"  Mean exit      {ex['mean_exit_ms']:,} ms over {ex.get('recorded_exits', '?')} exits"
          f"   slowest: {s.get('step', '?')} {s.get('mean_ms', 0):,} ms")
    st = latest.get("startup") or {}
    if st.get("hook_present"):
        A(f"  Wakeup shape   {st.get('lines', 0)} lines, {st.get('subshells', 0)} subshells, "
          f"{st.get('jq_calls', 0)} jq, {st.get('python_calls', 0)} python")
    A(f"  Baseline       " + (f"median of {base['n']} session(s)" if base
                              else f"none yet ({len(_history())}/{MIN_HISTORY} recorded) — "
                                   f"cold-start ceilings apply"))
    if findings:
        A("  VERDICT: OVER BUDGET")
        for x in findings:
            A(f"    - {x['what']}: {x['got']}{x.get('unit', '')} — {x['why']}")
    else:
        A("  VERDICT: within budget")
    return "\n".join(L)


# ─────────────────────────── fleet eligibility ──────────────────────────────
#
# OPERATOR RULING 2026-08-21: "We don't have to update every spoke. Perhaps only
# updating spokes with the current harness iteration is a good check. Otherwise the
# spoke is idle and pushing files into the folder is not valuable to us."
#
# He was right and it corrected a wrong finding of mine. I had surveyed this hook by
# content hash alone, found 16 of 34 spokes a month behind, and called the
# distribution pipe unreliable. Correlating against registry status and harness
# version showed the opposite: ZERO active spokes ran a stale hook. Every stale one
# was archived / deprecated / idle / inactive, all pinned at harness 4.14.7, idle
# 51-72 days. The pipe was working; staleness on a dormant spoke is the CORRECT
# resting state, not a defect.
#
# So currency is the ELIGIBILITY FILTER, never the alarm. A dormant spoke frozen at
# the cut it was last worked on is a feature: it stays reproducible, and writing
# files into it buys nothing because nothing there will ever read them.

CURRENCY_STATUSES = {"active", "dogfood"}


def _registry_path() -> Path:
    env = os.environ.get("BASHER_HUB_REGISTRY")
    if env and Path(env).is_file():
        return Path(env)
    return Path("/home/mario/projects/wheelwright/mywheel/WAI-Harness/hub/local/hub-registry.json")


def _harness_version(spoke: Path) -> str | None:
    m = spoke / "WAI-Harness" / "spoke" / "managed" / "MANIFEST.json"
    if not m.is_file():
        return None
    try:
        return json.loads(m.read_text(encoding="utf-8")).get("harness_version")
    except (ValueError, OSError):
        return None


def _vtuple(v: str | None):
    if not v:
        return ()
    return tuple(int(x) if x.isdigit() else -1 for x in str(v).split("."))


def fleet(current: str | None = None) -> dict:
    """Which spokes should receive a harness change, and which are deliberately skipped.

    Eligible = registry status in CURRENCY_STATUSES AND harness_version >= the cut
    this spoke is on. Everything else is reported as SKIPPED WITH A REASON -- never
    silently dropped. A distribution that quietly covers 18 of 34 and prints "done"
    is the failure this function exists to prevent; the skips are part of the result."""
    reg = _registry_path()
    out = {"registry": str(reg), "current_cut": current or _harness_version(REPO),
           "eligible": [], "skipped": []}
    if not reg.is_file():
        out["error"] = f"hub registry not readable at {reg}"
        return out
    try:
        wheels = json.loads(reg.read_text(encoding="utf-8")).get("wheels", [])
    except (ValueError, OSError) as e:
        out["error"] = f"hub registry unparseable: {e}"
        return out
    cut = _vtuple(out["current_cut"])
    for w in wheels:
        wid, p = w.get("wheel_id"), w.get("path")
        status = w.get("status", "?")
        if not p or not Path(p).is_dir():
            out["skipped"].append({"spoke": wid, "why": "path not on disk", "status": status})
            continue
        ver = _harness_version(Path(p))
        row = {"spoke": wid, "path": p, "status": status, "harness": ver}
        if status not in CURRENCY_STATUSES:
            out["skipped"].append({**row, "why": f"status={status} — idle; files pushed here are never read"})
            continue
        if not ver:
            out["skipped"].append({**row, "why": "no MANIFEST — not a managed spoke"})
            continue
        if cut and _vtuple(ver) < cut:
            out["skipped"].append({**row, "why": f"harness {ver} < {out['current_cut']} — behind the cut"})
            continue
        out["eligible"].append(row)
    return out


def render_fleet(f: dict) -> str:
    L = [f"FLEET — distribution eligibility (cut {f.get('current_cut')})"]
    if f.get("error"):
        L.append(f"  ERROR: {f['error']}")
        return "\n".join(L)
    L.append(f"  ELIGIBLE ({len(f['eligible'])}):")
    for r in sorted(f["eligible"], key=lambda r: r["spoke"] or ""):
        L.append(f"    {r['spoke']:34} {r['status']:9} {r['harness']}")
    L.append(f"  SKIPPED ({len(f['skipped'])}) — stated, never silent:")
    for r in sorted(f["skipped"], key=lambda r: (r.get("why") or "", r.get("spoke") or "")):
        L.append(f"    {r.get('spoke') or '?':34} {r['why']}")
    return "\n".join(L)


# ─────────────────────────────────── cli ────────────────────────────────────

def _session_uuid(arg: str | None) -> str | None:
    if arg:
        return arg
    for env in ("CLAUDE_SESSION_ID", "WAI_CC_SESSION_ID"):
        if os.environ.get(env):
            return os.environ[env]
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure"); m.add_argument("--session"); m.add_argument("--json", action="store_true")
    r = sub.add_parser("report");  r.add_argument("--json", action="store_true")
    c = sub.add_parser("check");   c.add_argument("--lug", action="store_true"); c.add_argument("--json", action="store_true")
    fl = sub.add_parser("fleet");  fl.add_argument("--cut"); fl.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.cmd == "fleet":
        f = fleet(a.cut)
        print(json.dumps(f, indent=2, ensure_ascii=False) if a.json else render_fleet(f))
        return 0

    if a.cmd == "measure":
        latest = measure(_session_uuid(a.session))
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(latest, ensure_ascii=False) + "\n")
        hist = _history()[:-1]
        print(json.dumps(latest, indent=2, ensure_ascii=False) if a.json
              else render(latest, baseline(hist), evaluate(latest, baseline(hist))))
        return 0

    hist = _history()
    if not hist:
        print("alignment: no measurements yet — run: alignment_advisor.py measure")
        return 0
    latest, base = hist[-1], baseline(hist[:-1])
    findings = evaluate(latest, base)

    if a.cmd == "report":
        print(json.dumps({"latest": latest, "baseline": base, "findings": findings},
                         indent=2, ensure_ascii=False) if a.json else render(latest, base, findings))
        return 0

    # check
    if a.json:
        print(json.dumps({"ok": not findings, "findings": findings}, indent=2, ensure_ascii=False))
    else:
        print(render(latest, base, findings))
    if findings and a.lug:
        p = file_lug(findings, latest)
        print(f"  lugged: {p}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
