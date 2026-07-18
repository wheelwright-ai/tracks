#!/usr/bin/env python3
"""
Model profile builder — Navigator's per-model competence profiles.

Deterministic aggregation (no LLM calls) of local evidence into
model-interface/<model_id>.json per spec-model-interface-profiles-v1:

  evidence sources (Tier 0, all free):
    - model-usage/usage.jsonl            (economics: turns, tokens, sessions)
    - lugs/bytype/*/completed/*.json     (oracle joins: gb model + verified PASS)
    - model-interface/baseline-runs.jsonl (delta_vs_bare_baseline — wave 3; null until then)

  invariants (spec): every field carries provenance; unknown = null + confidence
  'none' (NEVER a 0.5 default); expired profiles serve confidence 'stale' with
  routing_weight 0; priors never mix into evidence.

  --scan: standing gap detection + worth-it gate (energy model): a model seen in
  usage with no/expired profile earns an evidence-seeding lug ONLY if
  volume share >= 5% AND >=2 provider alternatives AND budget-guard allows.
  Missing/blocked budget-guard FAILS SAFE (no active spend).

Usage:
    python3 tools/model_profile_build.py                # build/refresh all profiles
    python3 tools/model_profile_build.py --scan         # gap detection + seeding
    python3 tools/model_profile_build.py --read MODEL   # serving view (staleness-safe)

Lug: impl-navigator-profile-builder-v1.  Spec: spec-model-interface-profiles-v1.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VALIDITY_DAYS = 7
VOLUME_SHARE_MIN = 0.05
ALTERNATIVES_MIN = 2

TASK_CLASS_RULES = [
    (re.compile(r"impl|build|fix|code|migrat", re.I), "implementation"),
    (re.compile(r"spec|design|author|plan", re.I), "spec-authoring"),
    (re.compile(r"review|assess|audit|verif", re.I), "review"),
    (re.compile(r"triage|rout|dispatch|inbox", re.I), "triage-routing"),
]


def resolve_base(spoke_root="."):
    try:
        from wai_paths import resolve_wai_root

        root, mode = resolve_wai_root(str(spoke_root))
        if root and mode != "none":
            return Path(root)
    except Exception:
        pass
    return Path(spoke_root) / "WAI-Spoke"


def now_utc(now_iso=None):
    return datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)


def task_class_for(task_type):
    for rx, cls in TASK_CLASS_RULES:
        if task_type and rx.search(str(task_type)):
            return cls
    return "general"


def safe_name(model_id):
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(model_id))


# Non-values that must never become a model: prompt placeholders (any "<...>" template
# token) and explicit unknowns. NOT a vendor whitelist -- an unfamiliar-but-real model id
# from a new provider must still profile, or telemetry silently loses new models.
_NON_MODEL_LITERALS = {"unknown", "none", "null", "n/a", "-", "?"}


def is_non_model_id(raw):
    """True when raw is a placeholder/unknown rather than a model id.

    The track hook writes '<your-model-id>' (a prompt template token the model is told to
    substitute) when it cannot resolve a model; that leaked into usage.jsonl and minted a
    phantom model-interface profile the Navigator could route against (2026-07-14). The
    hook now writes 'unknown' instead, but this log is append-only and other spokes' hooks
    lag until their next pull, so the read side must stay defensive."""
    if not raw or not isinstance(raw, str):
        return True
    v = raw.strip()
    return (not v) or v.startswith("<") or v.lower() in _NON_MODEL_LITERALS


def load_usage(base):
    """Usage events, with junk model ids dropped rather than profiled.

    usage.jsonl is telemetry, not a curated list: the track hook writes whatever
    model id it could resolve, and when it can resolve none it historically wrote
    the literal PROMPT placeholder '<your-model-id>' -- which minted a phantom
    model-interface/_your-model-id_.json profile the Navigator could route against
    (observed 2026-07-14: 1 of 348 events). The hook's fallback is now the honest
    data value 'unknown', but old events persist in this append-only log and other
    spokes' hooks lag until their next pull, so validate at the READ side too.

    Deliberately NARROWER than sanitize_model_id(): that helper enforces a known-vendor
    whitelist (MODEL_ID_RX), which is right for historical lug gb junk but WRONG here --
    on telemetry it would silently discard a real model from an unlisted provider, which
    is the same silent-data-loss failure in the opposite direction. So drop only
    NON-VALUES (prompt placeholders, 'unknown'), never merely-unfamiliar ids.
    Drops are announced on stderr, never swallowed."""
    f = base / "model-usage" / "usage.jsonl"
    if not f.exists():
        return []
    out, dropped = [], {}
    for line in f.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("event") != "model_usage" or not e.get("model"):
            continue
        if is_non_model_id(e["model"]):
            dropped[e["model"]] = dropped.get(e["model"], 0) + 1
            continue
        out.append(e)
    if dropped:
        print("  [usage] dropped %d event(s) with non-model ids (no profile minted): %s"
              % (sum(dropped.values()), ", ".join(sorted(dropped))), file=sys.stderr)
    return out


MODEL_ID_RX = re.compile(r"^(claude|gpt|gemini|glm|deepseek|kimi|codex|o[0-9]|llama|mistral|qwen)[a-z0-9.-]*$")


def sanitize_model_id(raw):
    """Historical lugs put display names, session ids, and advisor names in gb
    (schema violation). Accept only real model ids: take the first token and
    require the lowercase model-id shape. Returns None for junk — a dropped
    join beats a junk profile."""
    if not raw or not isinstance(raw, str) or raw.startswith("<"):
        return None
    token = re.split(r"[\s(\[]", raw.strip())[0]
    return token if MODEL_ID_RX.match(token) else None


def load_completed_lug_oracles(base):
    """Deterministic oracle joins: completed lugs record gb (authoring model) and
    verification_results whose cmd oracles ran. PASS iff a signatures[] verdict
    or verification_results exists. Self-reported prose is never consulted."""
    joins = []
    root = base / "lugs" / "bytype"
    if not root.is_dir():
        return joins
    for f in root.glob("*/completed/*.json"):
        try:
            lug = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        model = sanitize_model_id(lug.get("gb"))
        if not model:
            continue
        # Only lugs with an oracle verdict join. A completed lug WITHOUT
        # verification metadata is absence of evidence, not a failure —
        # counting it as fail would punish pre-verification-era lugs.
        # Discriminative pass/fail arrives with wave-3 baseline runs.
        has_verdict = bool(lug.get("verification_results")) or any(
            isinstance(s, dict) and s.get("verdict") in ("PASS", "FAIL")
            for s in lug.get("signatures", [])
        )
        if not has_verdict:
            continue
        passed = bool(lug.get("verification_results")) or any(
            isinstance(s, dict) and s.get("verdict") == "PASS"
            for s in lug.get("signatures", [])
        )
        joins.append({
            "model": model,
            "task_class": task_class_for(lug.get("type")),
            "passed": passed,
            "evidence_ref": str(f),
        })
    return joins


def load_baseline_deltas(base):
    """Wave-3 substrate; absent -> {} and every delta stays null."""
    f = base / "model-interface" / "baseline-verdicts.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except json.JSONDecodeError:
        return {}


def provenance(refs, n, now, baseline_ref=None):
    return {"evidence_refs": refs, "baseline_ref": baseline_ref, "n": n, "computed_at": now.isoformat()}


def build_profiles(base, now=None):
    now = now or now_utc()
    usage = load_usage(base)
    oracles = load_completed_lug_oracles(base)
    deltas = load_baseline_deltas(base)
    out_dir = base / "model-interface"
    out_dir.mkdir(parents=True, exist_ok=True)
    usage_ref = str(base / "model-usage" / "usage.jsonl")

    models = sorted({e["model"] for e in usage} | {o["model"] for o in oracles})
    written = []
    for model in models:
        ev = [e for e in usage if e["model"] == model]
        oj = [o for o in oracles if o["model"] == model]

        econ_n = len(ev)
        tokens_in = [e["tokens_in"] for e in ev if isinstance(e.get("tokens_in"), (int, float))]
        tokens_out = [e["tokens_out"] for e in ev if isinstance(e.get("tokens_out"), (int, float))]
        sessions = sorted({e.get("session_id") for e in ev if e.get("session_id")})
        economics = {
            "turns": econ_n,
            "sessions": len(sessions),
            "tokens_in_avg": round(sum(tokens_in) / len(tokens_in), 1) if tokens_in else None,
            "tokens_out_avg": round(sum(tokens_out) / len(tokens_out), 1) if tokens_out else None,
            "first_seen": min((e.get("ts") for e in ev), default=None),
            "last_seen": max((e.get("ts") for e in ev), default=None),
            "confidence": "evidenced" if econ_n else "none",
            "provenance": provenance([usage_ref], econ_n, now),
        }

        competence = {}
        for cls in sorted({o["task_class"] for o in oj} | {task_class_for(e.get("task_type")) for e in ev}):
            cls_oj = [o for o in oj if o["task_class"] == cls]
            n = len(cls_oj)
            model_deltas = deltas.get(model, {}) if isinstance(deltas.get(model, {}), dict) else {}
            competence[cls] = {
                "oracle_pass_rate": round(sum(1 for o in cls_oj if o["passed"]) / n, 3) if n else None,
                "rework_rate": None,
                "n": n,
                "delta_vs_bare_baseline": model_deltas.get(cls, {}).get("pp_delta") if isinstance(model_deltas.get(cls), dict) else None,
                "confidence": "evidenced" if n else "none",
                "provenance": provenance([o["evidence_ref"] for o in cls_oj][:20], n, now),
            }

        profile = {
            "schema": "model-interface-profile/1.0",
            "spec_id": "spec-model-interface-profiles-v1",
            "model_id": model,
            "provider": "anthropic" if model.startswith("claude") else "unknown",
            "version_fingerprint": model,
            "competence": competence,
            "economics": economics,
            "failure_signatures": [],
            "unscaffoldable": [],
            "staleness": {
                "computed_at": now.isoformat(),
                "valid_through": (now + timedelta(days=VALIDITY_DAYS)).isoformat(),
                "invalidation_triggers": [
                    "model_id/version fingerprint change -> reset to prior",
                    "K consecutive oracle results outside predicted band -> invalidate field",
                    "valid_through lapse -> confidence stale, routing_weight 0",
                ],
            },
        }
        path = out_dir / f"{safe_name(model)}.json"
        path.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n")
        with open(out_dir / "profile-history.jsonl", "a") as h:
            h.write(json.dumps({"model_id": model, "computed_at": now.isoformat(),
                                "turns": econ_n, "oracle_joins": len(oj)}) + "\n")
        written.append(str(path))
    return written


def read_profile(base, model, now=None):
    """The single serving door: staleness semantics live here and only here."""
    now = now or now_utc()
    path = base / "model-interface" / f"{safe_name(model)}.json"
    if not path.exists():
        return {"model_id": model, "serving": {"confidence": "none", "routing_weight": 0.0,
                                               "reason": "no profile — serve labeled priors only"}}
    profile = json.loads(path.read_text())
    valid_through = profile.get("staleness", {}).get("valid_through")
    stale = bool(valid_through) and now > datetime.fromisoformat(valid_through)
    if stale:
        profile["serving"] = {"confidence": "stale", "routing_weight": 0.0,
                              "reason": f"expired {valid_through} — recompute before use"}
    else:
        has_evidence = any(v.get("confidence") == "evidenced" for v in profile.get("competence", {}).values()) \
            or profile.get("economics", {}).get("confidence") == "evidenced"
        profile["serving"] = {"confidence": "evidenced" if has_evidence else "none",
                              "routing_weight": 1.0 if has_evidence else 0.0}
    return profile


def budget_allows(repo_root="."):
    """Fail-safe: missing or blocking guard -> no active (Tier-1) spend."""
    guard_path = Path(repo_root) / "WAI-Harness" / "hub" / "local" / "model-routing" / "budget-guard.json"
    if not guard_path.exists():
        return False, "budget-guard.json missing — fail safe, no active spend"
    try:
        g = json.loads(guard_path.read_text())
    except json.JSONDecodeError:
        return False, "budget-guard.json unreadable — fail safe"
    if g.get("navigator_allowed") is False:
        return False, "navigator_allowed:false (operator gate)"
    if (g.get("five_day_limit_pct") or 100) > (g.get("threshold_pct") or 80):
        return False, f"window {g.get('five_day_limit_pct')}% > threshold {g.get('threshold_pct')}%"
    return True, "budget window open"


def count_alternatives(repo_root="."):
    matrix = Path(repo_root) / "WAI-Harness" / "spoke" / "advisors" / "navigator" / "provider-matrix.json"
    if not matrix.exists():
        return 0
    try:
        providers = json.loads(matrix.read_text()).get("providers", {})
        return len(providers) if isinstance(providers, dict) else len(providers or [])
    except json.JSONDecodeError:
        return 0


def scan_gaps(base, now=None, repo_root=".", emit=True):
    """Standing duty: find profile-less/expired models; seed evidence lugs when worth it."""
    now = now or now_utc()
    usage = load_usage(base)
    total = len(usage)
    results = []
    for model in sorted({e["model"] for e in usage}):
        prof = read_profile(base, model, now)
        gap = prof["serving"]["confidence"] in ("none", "stale")
        if not gap:
            continue
        share = sum(1 for e in usage if e["model"] == model) / total if total else 0.0
        alts = count_alternatives(repo_root)
        budget_ok, budget_reason = budget_allows(repo_root)
        worth_it = share >= VOLUME_SHARE_MIN and alts >= ALTERNATIVES_MIN and budget_ok
        verdict = {"model": model, "gap": prof["serving"]["confidence"], "volume_share": round(share, 3),
                   "alternatives": alts, "budget": budget_reason, "worth_it": worth_it}
        if worth_it and emit:
            verdict["seeding_lug"] = emit_seeding_lug(base, model, verdict, now)
        results.append(verdict)
    return results


def emit_seeding_lug(base, model, verdict, now):
    lug_dir = base / "lugs" / "bytype" / "task" / "open"
    lug_dir.mkdir(parents=True, exist_ok=True)
    lug_id = f"task-evidence-seed-{safe_name(model)}-v1"
    path = lug_dir / f"{lug_id}.json"
    if path.exists():
        return str(path)
    lug = {
        "id": lug_id, "type": "task", "status": "open", "routed_to": "LOCAL",
        "spec_id": "spec-model-interface-profiles-v1",
        "created_at": now.isoformat(), "gb": "model_profile_build.py --scan (deterministic)",
        "title": f"Seed oracle evidence for model {model}: route it oracle-checkable low-stakes lugs",
        "one_liner": f"Profile gap ({verdict['gap']}) with volume share {verdict['volume_share']} and open budget — run ~20 oracle-checked turns per spec cold-start policy.",
        "urgency": 3, "impact": 5, "effort": "S", "effort_score": 2, "roi": 5,
        "model_fit": "haiku", "model_fit_reason": "Dispatch bookkeeping; the evidence itself comes from routed work.",
        "execute_when": "next AP round with oracle-checkable backlog available",
        "verify_mode": "mechanical",
        "perceive": ["Read spec-model-interface-profiles-v1 cold_start_and_staleness.",
                     f"Read WAI-Harness/spoke/local/model-interface/{safe_name(model)}.json serving block."],
        "execute": [f"Route the next ~20 oracle-checkable low-stakes lugs to {model}.",
                    "Rerun model_profile_build.py after they complete."],
        "verify": [f"cmd: python3 WAI-Harness/spoke/managed/tools/model_profile_build.py --read {model} | grep -v '\"confidence\": \"none\"' | grep -q '\"confidence\"'"],
        "acceptance_criteria": [f"{model} profile reaches evidenced confidence on >=1 competence class."],
        "file_targets": [f"WAI-Harness/spoke/local/model-interface/{safe_name(model)}.json"],
        "_behavior_directive": {
            "what_this_is": "Auto-seeded by Navigator's standing gap-detection (contract T1 self-heal).",
            "what_this_is_NOT": "Not a bench-run authorization (Tier-1 spend has its own gate), not hand-authored competence data."},
    }
    path.write_text(json.dumps(lug, indent=2, ensure_ascii=False) + "\n")
    return str(path)


def main():
    ap = argparse.ArgumentParser(description="Build/serve/scan per-model competence profiles")
    ap.add_argument("--spoke-root", default=".")
    ap.add_argument("--now", help="ISO timestamp override (tests)")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--no-emit", action="store_true", help="scan without writing seeding lugs")
    ap.add_argument("--read", metavar="MODEL")
    args = ap.parse_args()

    base = resolve_base(args.spoke_root)
    now = now_utc(args.now)

    if args.read:
        print(json.dumps(read_profile(base, args.read, now), indent=2, ensure_ascii=False))
        return
    if args.scan:
        for r in scan_gaps(base, now, args.spoke_root, emit=not args.no_emit):
            print(json.dumps(r))
        return
    written = build_profiles(base, now)
    print(f"model_profile_build: {len(written)} profile(s) written")
    for w in written:
        print(f"  {w}")


if __name__ == "__main__":
    main()
