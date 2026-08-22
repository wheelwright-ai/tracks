#!/usr/bin/env python3
"""Run selected lugs on a NON-ANTHROPIC provider, bypassing the live-AP stall.

WHY THIS EXISTS. The operator hit 76% of a 7-day Anthropic limit with the reset three
days out: "how can we manage to be productive using non-anthropic models... this way
every spoke can make progress vs having to stifle myself."

The provider work landed and is proven -- deepseek and kimi both complete real
lug-shaped prompts through the exact subprocess AP builds, returning the exact usage
shape AP parses. What does NOT work is a LIVE autopilot round: it stalls after phase
0b and never reaches dispatch (bug-ap-live-stalls-after-phase0b-never-reaches-dispatch-v1,
reproduced twice, killed at 1500s and 400s). A --dry-run of the same spoke completes
the entire pipeline in seconds.

So this uses the half that works to drive the half that works, and skips the half that
hangs.

REINVENTS NOTHING, DELIBERATELY. Every piece of judgement here is borrowed:

  selection   `ozi_autopilot.py --dry-run` -- AP's real scoring, real filters, real
              tier ceiling. Its [dry-run] lines ARE the candidate list, and the model
              tier printed there is post-clamp.
  prompt      OziDispatch.create_implementation_prompt -- the same prompt a live
              round would send.
  routing     OziAutopilot._resolve_provider_cmd -- the same model-id -> command
              mapping, so a fix there reaches here for free.

A forked selector or a hand-rolled prompt would be a second source of truth, and this
repo already carries 66 divergent duplicate groups. The only thing this file owns is
the loop.

WHAT IT WILL NOT DO. It does not mark lugs complete. A model answering a prompt is not
evidence that work landed -- that conflation is the failure the whole harness exists to
prevent. Output goes to a run record for a human or a verifier to judge.

USAGE
  offload_run.py --provider deepseek --budget 3
  offload_run.py --provider kimi --budget 5 --dry-run     # show the plan, call nothing
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SPOKE_ROOT = TOOLS.parents[3]
DRY_LINE = re.compile(r"^\[dry-run\]\s+(\S+)\s+model=(\S+)")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def select(root: Path, budget: int, provider: str, timeout: int) -> list:
    """AP's own selection, via the path that completes. Returns [(lug_id, tier)].

    --dry-run is used as an ORACLE, not as a convenience: it exercises the real
    scorer, the real filters and the real tier ceiling, and prints the post-clamp
    model for each candidate.
    """
    cmd = [sys.executable, str(TOOLS / "ozi_autopilot.py"),
           "--spoke-path", str(root), "--budget", str(budget),
           "--provider", provider, "--dry-run", "--trigger-source", "manual"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"offload: selection timed out after {timeout}s -- the dry-run path is "
              "supposed to finish in seconds; something changed", file=sys.stderr)
        return []
    out = []
    for line in (p.stdout + p.stderr).splitlines():
        m = DRY_LINE.match(line.strip())
        if m:
            out.append((m.group(1), m.group(2)))
    return out[:budget]


def find_lug(root: Path, lug_id: str):
    for base in (root / "WAI-Spoke" / "work",
                 root / "WAI-Harness" / "spoke" / "local" / "lugs" / "bytype"):
        if not base.exists():
            continue
        for path in base.rglob(f"{lug_id}.json"):
            try:
                return json.loads(path.read_text(encoding="utf-8")), path
            except (OSError, json.JSONDecodeError):
                continue
    return None, None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", choices=["deepseek", "kimi"], required=True)
    ap.add_argument("--budget", type=int, default=3)
    ap.add_argument("--root", default=str(SPOKE_ROOT))
    # RAISED 2026-08-17 BY MEASUREMENT. A budget-8 run on each of deepseek and kimi
    # produced 9 timeouts out of 16 calls, every one an impl-* lug -- and the ceiling
    # in force was BELOW ozi_autopilot's own DEFAULT_TIMEOUT_SECS of 900. The runner
    # was cutting off work the autopilot would have let finish.
    ap.add_argument("--select-timeout", type=int, default=600,
                    help="seconds for the AP dry-run that picks candidates; it walks "
                         "the whole lug tree (3825 on this spoke)")
    ap.add_argument("--call-timeout", type=int, default=2700,
                    help="ceiling per lug. Only a ceiling: --min-call-timeout and the "
                         "lug's own estimated_seconds set the real budget")
    ap.add_argument("--min-call-timeout", type=int, default=900,
                    help="floor per lug, matching ozi_autopilot.DEFAULT_TIMEOUT_SECS")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan and the resolved command; call no provider")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    key = {"deepseek": "DEEPSEEK_API_KEY", "kimi": "MOONSHOT_API_KEY"}[args.provider]
    if not args.dry_run and not os.environ.get(key):
        # Fail loudly and EARLY. A missing key discovered mid-loop would leave half a
        # run recorded; and this exact key was reported "absent" for three sessions
        # while sitting in .env.local unread.
        print(f"offload: {key} not set. It lives in <spoke>/.env.local; the launcher "
              "loads it, so either relaunch or `set -a; . ./.env.local; set +a`.",
              file=sys.stderr)
        return 2

    ozi = _load("_offload_ozi", TOOLS / "ozi_autopilot.py")
    cls = next(v for v in vars(ozi).values()
               if isinstance(v, type) and hasattr(v, "DEEPSEEK_TIER_MAP"))
    tier_map = cls.DEEPSEEK_TIER_MAP if args.provider == "deepseek" else cls.KIMI_TIER_MAP
    router = cls.__new__(cls)
    router._provider = args.provider      # provider_env() reads this; __new__ skips __init__
    hub = root / "WAI-Harness" / "hub"

    _log = _load("_offload_usage_log", TOOLS / "model_usage_logger.py")
    _ta = _load("_offload_token_attr", TOOLS / "token_attribution.py")

    dispatch_mod = _load("_offload_dispatch", TOOLS / "wai_ozi_dispatch.py")
    config = dispatch_mod.OziConfig(spoke_path=str(root / "WAI-Spoke"))
    prompter = dispatch_mod.OziDispatch(config)

    print(f"offload: selecting up to {args.budget} via AP dry-run…", file=sys.stderr)
    picked = select(root, args.budget, args.provider, args.select_timeout)
    if not picked:
        print("offload: nothing selected -- AP's dry-run offered no candidates.",
              file=sys.stderr)
        return 1
    print(f"offload: {len(picked)} candidate(s) on {args.provider}", file=sys.stderr)

    runs, started = [], time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for lug_id, tier in picked:
        info = tier_map.get(tier) or tier_map["sonnet"]
        cmd = router._resolve_provider_cmd(info["model_id"], hub)
        # REFUSE ON THE REDIRECT, NOT ON THE BINARY. This guard used to read
        # `cmd[0] == "claude"` because at the time claude-the-binary meant
        # Anthropic-the-account. Under the cli transport that is no longer true:
        # every provider keeps the claude binary and only ANTHROPIC_BASE_URL moves.
        # The stale form refused 4 of 4 candidates as "resolved to claude" while the
        # routing underneath was correct -- a false refusal that made a working
        # offload path look dead.
        #
        # The real question is the only one that costs money: does this child talk to
        # Anthropic? It does exactly when there is no redirect in its env.
        penv = router.provider_env()
        if cmd and cmd[0] == "claude" and not penv.get("ANTHROPIC_BASE_URL"):
            print(f"  SKIP {lug_id}: {info['model_id']} would spend Anthropic "
                  f"(no {args.provider} redirect -- key missing or transport not cli)",
                  file=sys.stderr)
            runs.append({"lug": lug_id, "tier": tier, "status": "refused_would_spend_anthropic"})
            continue

        lug, path = find_lug(root, lug_id)
        if lug is None:
            print(f"  SKIP {lug_id}: lug file not found", file=sys.stderr)
            runs.append({"lug": lug_id, "tier": tier, "status": "not_found"})
            continue

        prompt = prompter.create_implementation_prompt(lug_id, lug)
        if args.dry_run:
            print(f"  [plan] {lug_id}  tier={tier}  model={info['model_id']}  "
                  f"prompt={len(prompt)}c  cmd={' '.join(str(c) for c in cmd[:3])}…")
            runs.append({"lug": lug_id, "tier": tier, "model": info["model_id"],
                         "status": "planned", "prompt_chars": len(prompt)})
            continue

        # HONOUR THE LUG'S OWN ESTIMATE, like the autopilot does.
        # ozi_autopilot reads estimated_seconds per lug and falls back to a default;
        # this runner ignored it and applied one flat number to a 5-minute doc edit
        # and a fleet-wide refactor alike. NOTE, measured the day this landed: not one
        # of the lugs that timed out carried estimated_seconds, effort OR model_fit --
        # the same dead-input disease as verify_kinds. The clamp is live for the lugs
        # that do set it; the rest get the floor, which is the real fix for tonight.
        try:
            _est = int(lug.get("estimated_seconds") or 0)
        except (TypeError, ValueError):
            _est = 0
        lug_timeout = max(args.min_call_timeout, min(_est or 0, args.call_timeout)) \
            if _est else args.min_call_timeout
        lug_timeout = min(max(lug_timeout, args.min_call_timeout), args.call_timeout)

        t0 = time.monotonic()
        try:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                               timeout=lug_timeout,
                               env={**os.environ, **penv} if penv else None)
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT {lug_id} after {lug_timeout}s "
                  f"(est={_est or 'unset'})", file=sys.stderr)
            runs.append({"lug": lug_id, "tier": tier, "model": info["model_id"],
                         "status": "timeout", "timeout_s": lug_timeout,
                         "estimated_seconds": _est or None})
            continue
        el = round(time.monotonic() - t0, 1)

        rec = {"lug": lug_id, "tier": tier, "model": info["model_id"],
               "elapsed_s": el, "rc": p.returncode}
        if p.returncode == 0:
            try:
                body = json.loads(p.stdout)
                rec["usage"] = body.get("usage")
                # Two shapes, one parser. The chat helpers return {"content": ...};
                # the claude CLI under --output-format json returns {"result": ...}.
                # Reading only "content" against a cli-transport run scored every
                # answer as empty_answer.
                rec["content"] = body.get("content") or body.get("result") or ""
                rec["transport"] = "cli" if penv else "chat"
                # An empty answer is NOT a success. A reasoning model whose budget went
                # entirely to reasoning_content returns "" with rc=0, and recording that
                # as done is exactly the false-green this harness keeps producing.
                rec["status"] = "answered" if rec["content"].strip() else "empty_answer"
            except (json.JSONDecodeError, TypeError) as exc:
                rec["status"] = "unparseable"
                rec["error"] = f"{exc}"
        else:
            rec["status"] = "error"
            rec["error"] = (p.stderr or "")[:400]
        # LOG THE SPEND WHERE SPEND IS READ. The run record below is a per-run file
        # nothing aggregates; model-usage/usage.jsonl is what burn_panel, the model
        # profiles and harness_telemetry actually read. Without this the offload work
        # -- whose entire purpose is to move spend OFF the Anthropic account -- was
        # invisible to every cost surface in the harness, and the operator asking
        # "how much did that cost" got zero.
        #
        # Failures are logged too, deliberately. A call that errored after burning
        # 400s of tokens costs the same as one that worked; a ledger of successes
        # only reports a cost with no denominator.
        try:
            _u = rec.get("usage") or {}
            _ti = _u.get("input_tokens") or _u.get("prompt_tokens") or 0
            _to = _u.get("output_tokens") or _u.get("completion_tokens") or 0
            _log.log_usage(
                provider=args.provider, model=info["model_id"], task_type="execute",
                tokens_in=_ti, tokens_out=_to,
                cost_estimate=_ta.estimate_cost(info["model_id"], _ti, _to, root=str(root)),
                duration_ms=int(el * 1000),
                error=None if rec["status"] == "answered" else rec["status"],
                error_kind=None if rec["status"] == "answered" else "offload_run",
            )
        except Exception as exc:                      # never let telemetry kill a run
            print(f"  (usage not logged for {lug_id}: {exc})", file=sys.stderr)

        runs.append(rec)
        mark = {"answered": "ok", "empty_answer": "EMPTY", "error": "ERR"}.get(rec["status"], "?")
        print(f"  {mark:5s} {lug_id}  {info['model_id']}  {el}s  "
              f"{len(rec.get('content','') or '')}c", file=sys.stderr)

    out_dir = root / "WAI-Harness" / "spoke" / "local" / "runtime" / "offload-runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    record = {"started_at": started, "provider": args.provider, "budget": args.budget,
              "dry_run": args.dry_run, "runs": runs,
              "_note": ("A model answering a prompt is NOT evidence that work landed. "
                        "Nothing here marks a lug complete; judge these before acting.")}
    dest = out_dir / f"offload-{args.provider}-{stamp}.json"
    dest.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")

    answered = sum(1 for r in runs if r.get("status") == "answered")
    print(f"offload: {answered}/{len(runs)} answered -> {dest}", file=sys.stderr)
    return 0 if answered or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
