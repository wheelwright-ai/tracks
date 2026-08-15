#!/usr/bin/env python3
"""harness_telemetry.py — the READ-BACK half of the harness feedback loop.

WHY THIS EXISTS
---------------
Collection was never the problem. Measured in basher on 2026-08-01: 444 usage
rows, $170.17 of spend, provider/model/tokens/cost/duration on every row — and
not one line of it had ever been reported to anyone. The same session found the
same shape twice more (landing conditions evaluated and discarded; wai-exit
findings printed to a closing terminal). A measurement that reaches nobody is
indistinguishable from no measurement, and it is worse than none because it
buys false confidence that the thing is instrumented.

So this tool does not collect. It REPORTS, and it reports the four things the
operator asked to be able to weigh:

  1. VERSION TRUTH   which harness is actually running, and whether the
                     surfaces that claim to know agree. They usually do not.
  2. UTILIZATION     provider / model mix, spend, where the tokens went.
  3. ERRORS          failure rate, cheaply. A cost without a denominator is
                     not a utilization number.
  4. EFFICIENCY      cache leverage, output-per-dollar, tier mismatch, rework.
                     These are the addressable inefficiencies, not vanity totals.

CANONICAL, THEREFORE ENFORCEABLE (operator ruling, 2026-08-01)
--------------------------------------------------------------
This lives in managed/ and travels to every spoke, because a reporter that
exists on one spoke measures one spoke. The schema below is the contract; the
accompanying test asserts it. Add a field here and every spoke gains it at the
next cut. Read a field that a spoke's older rows lack and you get None, never a
crash — rows are forward- and backward-compatible on purpose, since a fleet is
never on one version at one time.

DESIGN RULES
------------
  * NEVER invent a number. A field absent from the rows reports as "unknown",
    never as zero. Zero is a measurement; unknown is the absence of one, and
    collapsing them is how a dead instrument reads as a healthy one.
  * Model aliases are normalized for GROUPING only; the raw string is preserved
    in the detail so an alias problem stays visible instead of being tidied away.
  * Read-only. This tool never writes to the logs it reads.
"""

import argparse
import collections
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0.0"

# Required on every model_usage row. The test asserts this list matches what
# model_usage_logger.log_usage actually emits — a schema that drifts from its
# writer is documentation, not a contract.
REQUIRED_FIELDS = [
    "event", "ts", "spoke_id", "harness_version",
    "provider", "model", "task_type",
    "tokens_in", "tokens_out", "cost_estimate", "duration_ms",
]

# Grouping only. The raw model string is always kept alongside.
MODEL_ALIASES = {
    "opus": "claude-opus (unversioned)",
    "sonnet": "claude-sonnet (unversioned)",
    "haiku": "claude-haiku (unversioned)",
}

TIER_ORDER = {"haiku": 0, "sonnet": 1, "opus": 2}


def _tier(model):
    m = (model or "").lower()
    for t in ("haiku", "sonnet", "opus"):
        if t in m:
            return t
    return None


def _norm(model):
    return MODEL_ALIASES.get(model, model or "unknown")


def _read_jsonl(path):
    rows = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # a malformed row is skipped, never fatal
    except OSError:
        return None  # ABSENT is different from EMPTY and must stay different
    return rows


def _base(root):
    for cand in ("WAI-Harness/spoke/local", "WAI-Spoke"):
        p = Path(root) / cand
        if p.is_dir():
            return p
    return Path(root) / "WAI-Harness/spoke/local"


# ── 1. version truth ─────────────────────────────────────────────────────────

def version_truth(root):
    """Every surface that claims to know the running version, side by side.

    They disagree in the field. basher 2026-08-01: manifest 4.14.34, VERSION
    4.14.32 (stale since Jul 30), WAI-State 4.1.0 (thirteen minors behind). The
    statusline compared two of them and rendered '4.14.34<4.14.32' — a spoke
    reporting itself behind a version older than the one it was running.
    """
    out = {"sources": {}, "agree": None, "authority": None}

    mf = Path(root) / "WAI-Harness/spoke/managed/MANIFEST.json"
    try:
        m = json.load(open(mf))
        out["sources"]["managed_manifest"] = m.get("harness_version")
        out["is_master"] = bool(m.get("is_master"))
    except Exception:
        out["sources"]["managed_manifest"] = None
        out["is_master"] = None

    vf = Path(root) / "WAI-Harness/VERSION"
    try:
        out["sources"]["version_file"] = vf.read_text().strip() or None
    except Exception:
        out["sources"]["version_file"] = None

    st = _base(root) / "WAI-State.json"
    try:
        h = (json.load(open(st)).get("_harness") or {})
        out["sources"]["wai_state"] = h.get("harness_version_v4") or h.get("base_version")
    except Exception:
        out["sources"]["wai_state"] = None

    # The manifest is authoritative: it is computed from the bytes on disk.
    out["authority"] = out["sources"].get("managed_manifest")
    known = [v for v in out["sources"].values() if v]
    out["agree"] = len(set(known)) <= 1 if known else None
    out["disagreements"] = {k: v for k, v in out["sources"].items()
                            if v and v != out["authority"]}
    return out


# ── 2-4. usage, errors, efficiency ───────────────────────────────────────────

def _window(rows, days):
    if not days:
        return rows
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept = []
    for r in rows:
        try:
            ts = datetime.fromisoformat(str(r.get("ts", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if ts >= cutoff:
            kept.append(r)
    return kept


def analyze(rows):
    usage = [r for r in rows if r.get("event") == "model_usage"]
    n = len(usage)
    rep = {"rows": n, "schema_version": SCHEMA_VERSION}
    if not n:
        return rep

    def _s(key):
        return sum(r.get(key) or 0 for r in usage)

    cost = _s("cost_estimate")
    t_in, t_out = _s("tokens_in"), _s("tokens_out")
    c_read, c_make = _s("cache_read_tokens"), _s("cache_creation_tokens")
    dur = _s("duration_ms")

    rep["cost_total"] = round(cost, 2)
    rep["tokens"] = {"in": t_in, "out": t_out,
                     "cache_read": c_read, "cache_creation": c_make}
    rep["duration_hours"] = round(dur / 3_600_000, 2)

    by_model = collections.Counter()
    cost_by_model = collections.Counter()
    for r in usage:
        by_model[_norm(r.get("model"))] += 1
        cost_by_model[_norm(r.get("model"))] += r.get("cost_estimate") or 0
    rep["by_model"] = [{"model": m, "runs": c, "cost": round(cost_by_model[m], 2)}
                       for m, c in by_model.most_common()]
    rep["by_provider"] = collections.Counter(
        r.get("provider") or "unknown" for r in usage).most_common()

    # Version coverage: rows written before harness_version existed cannot be
    # attributed to a cut. Reported as unknown, never folded into the newest.
    vers = collections.Counter(r.get("harness_version") or "unknown" for r in usage)
    rep["by_harness_version"] = vers.most_common()
    rep["version_unattributed"] = vers.get("unknown", 0)

    # ERRORS. Rows predating the error field are unattributable, not successes.
    has_field = [r for r in usage if "error" in r]
    errs = [r for r in has_field if r.get("error")]
    rep["errors"] = {
        "observable_rows": len(has_field),
        "unobservable_rows": n - len(has_field),
        "failures": len(errs),
        "rate": (round(len(errs) / len(has_field), 4) if has_field else None),
        "by_kind": collections.Counter(
            r.get("error_kind") or "unclassified" for r in errs).most_common(),
    }

    # EFFICIENCY — each one is an addressable lever, not a vanity total.
    ineff = []
    billed_in = t_in + c_make
    if c_read or billed_in:
        ratio = c_read / (c_read + billed_in) if (c_read + billed_in) else 0
        rep["cache_hit_ratio"] = round(ratio, 4)
        if ratio < 0.5 and (c_read + billed_in) > 100_000:
            ineff.append({
                "lever": "cache",
                "finding": f"cache serves only {ratio:.0%} of input tokens",
                "why": "uncached input is billed at full rate every call; a low "
                       "ratio usually means prompt prefixes are being rebuilt "
                       "rather than reused",
            })
    if t_out:
        rep["cost_per_1k_output"] = round(cost / (t_out / 1000), 4)

    # COST COVERAGE — the finding that makes every spend number above a floor
    # rather than a total. Measured in basher 2026-08-01: 351 of 445 rows carried
    # 20.1M output tokens and cost_estimate 0, all from the track backfill path.
    # The $170 headline was the dispatch spend only; interactive spend was
    # entirely unpriced, so "total cost" was off by an unknown multiple.
    priced = [r for r in usage if (r.get("cost_estimate") or 0) > 0]
    unpriced = [r for r in usage
                if not (r.get("cost_estimate") or 0) and (r.get("tokens_out") or 0) > 0]
    rep["cost_coverage"] = {
        "priced_rows": len(priced), "unpriced_rows_with_tokens": len(unpriced),
        "unpriced_output_tokens": sum(r.get("tokens_out") or 0 for r in unpriced),
    }
    if unpriced:
        srcs = collections.Counter(
            r.get("source") or r.get("actor") or "unattributed" for r in unpriced)
        ineff.append({
            "lever": "cost coverage",
            "finding": f"{len(unpriced)} run(s) carrying "
                       f"{rep['cost_coverage']['unpriced_output_tokens']:,} output "
                       f"tokens have no cost_estimate "
                       f"(source: {', '.join(f'{s} x{c}' for s, c in srcs.most_common(3))})",
            "why": "the reported spend is a FLOOR, not a total. Any utilization "
                   "judgment made against it understates the real cost by an "
                   "unknown multiple, which is worse than having no number",
        })

    alias_rows = [r for r in usage if r.get("model") in MODEL_ALIASES]
    if alias_rows:
        ineff.append({
            "lever": "attribution",
            "finding": f"{len(alias_rows)} row(s) log an unversioned model alias "
                       f"({', '.join(sorted({r['model'] for r in alias_rows}))})",
            "why": "an alias cannot be priced or compared across cuts, so those "
                   "rows silently drop out of any per-model efficiency question",
        })

    top = _tier_spend(usage)
    if top:
        ineff.append(top)

    rework = [r for r in usage if r.get("rework_required")]
    if rework:
        ineff.append({
            "lever": "rework",
            "finding": f"{len(rework)} run(s) flagged rework_required",
            "why": "rework is paid twice; these are the runs where a cheaper "
                   "tier or a better-specified lug would have paid for itself",
        })
    rated = [r for r in usage if r.get("quality_rating") is not None]
    rep["quality_coverage"] = {
        "rated": len(rated), "unrated": n - len(rated),
        "mean": (round(sum(r["quality_rating"] for r in rated) / len(rated), 2)
                 if rated else None),
    }
    if not rated:
        ineff.append({
            "lever": "quality signal",
            "finding": "no run carries a quality_rating",
            "why": "without it, spend can be compared across models but VALUE "
                   "cannot — the log can say which model cost more, never which "
                   "was worth it",
        })

    rep["inefficiencies"] = ineff
    return rep


def _tier_spend(usage):
    """Flag spend concentrated in the top tier on cheap task types."""
    spend = collections.Counter()
    for r in usage:
        t = _tier(r.get("model"))
        if t:
            spend[t] += r.get("cost_estimate") or 0
    total = sum(spend.values())
    if not total:
        return None
    opus_share = spend.get("opus", 0) / total
    if opus_share > 0.7:
        return {
            "lever": "model tier",
            "finding": f"{opus_share:.0%} of spend is top-tier (opus)",
            "why": "tier is the largest single cost lever; the question to ask "
                   "of each lug is whether its verify step is deterministic "
                   "enough for a cheaper tier",
        }
    return None


# ── render ───────────────────────────────────────────────────────────────────

def render(vt, rep, days):
    L = []
    L.append(f"HARNESS TELEMETRY — schema {SCHEMA_VERSION}"
             + (f" — last {days}d" if days else " — all time"))
    L.append("")
    L.append("VERSION TRUTH")
    auth = vt.get("authority") or "UNKNOWN"
    L.append(f"  running (managed manifest, byte-derived): {auth}")
    for k, v in vt["sources"].items():
        if k == "managed_manifest":
            continue
        mark = "  ok" if v == vt.get("authority") else "  DISAGREES"
        L.append(f"    {k:22} {v or 'absent':<12}{mark}")
    if vt.get("disagreements"):
        L.append("  -> a spoke that cannot name its own version cannot attribute "
                 "any measurement to a cut.")
    L.append("")

    if not rep.get("rows"):
        L.append("USAGE: no model_usage rows found. Instrumentation is ABSENT, not clean.")
        return "\n".join(L)

    cc = rep.get("cost_coverage") or {}
    floor = " (FLOOR — see cost coverage)" if cc.get("unpriced_rows_with_tokens") else ""
    L.append(f"UTILIZATION — {rep['rows']} run(s), ${rep['cost_total']}{floor}, "
             f"{rep['duration_hours']}h of model time")
    for row in rep["by_model"][:8]:
        L.append(f"    {row['model']:32} {row['runs']:4} runs   ${row['cost']:.2f}")
    L.append(f"    providers: {', '.join(f'{p} x{c}' for p, c in rep['by_provider'])}")
    L.append("")
    L.append("VERSION ATTRIBUTION")
    for v, c in rep["by_harness_version"]:
        L.append(f"    {v:20} {c} run(s)")
    if rep["version_unattributed"]:
        L.append(f"    -> {rep['version_unattributed']} run(s) predate the "
                 "harness_version field and cannot be attributed to a cut")
    L.append("")
    e = rep["errors"]
    L.append("ERRORS")
    if e["observable_rows"]:
        L.append(f"    {e['failures']} failure(s) in {e['observable_rows']} "
                 f"observable run(s) — rate {e['rate']:.1%}")
        for k, c in e["by_kind"]:
            L.append(f"      {k}: {c}")
    else:
        L.append("    UNOBSERVABLE — no run carries an error field yet.")
    if e["unobservable_rows"]:
        L.append(f"    {e['unobservable_rows']} older run(s) have no error field; "
                 "they are unknown, NOT successes.")
    L.append("")
    L.append("EFFICIENCY")
    if "cache_hit_ratio" in rep:
        L.append(f"    cache serves {rep['cache_hit_ratio']:.0%} of input tokens")
    if "cost_per_1k_output" in rep:
        L.append(f"    ${rep['cost_per_1k_output']:.4f} per 1k output tokens")
    q = rep["quality_coverage"]
    L.append(f"    quality signal: {q['rated']}/{q['rated'] + q['unrated']} runs rated"
             + (f", mean {q['mean']}" if q["mean"] is not None else ""))
    L.append("")
    if rep["inefficiencies"]:
        L.append(f"ADDRESSABLE ({len(rep['inefficiencies'])}) — ranked by lever")
        for i in rep["inefficiencies"]:
            L.append(f"  [{i['lever']}] {i['finding']}")
            L.append(f"      {i['why']}")
    else:
        L.append("ADDRESSABLE: none found in this window.")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Report harness version truth, utilization, errors and efficiency")
    ap.add_argument("--root", default=".")
    ap.add_argument("--days", type=int, default=0,
                    help="restrict to the last N days (0 = all time)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    vt = version_truth(root)
    rows = _read_jsonl(_base(root) / "model-usage" / "usage.jsonl")
    if rows is None:
        if args.json:
            print(json.dumps({"version_truth": vt, "usage": None,
                              "status": "usage log ABSENT"}, indent=2))
        else:
            print(render(vt, {}, args.days))
            print("\nUSAGE LOG ABSENT — this spoke is not instrumented. "
                  "That is a finding, not a clean bill.")
        return 2
    rep = analyze(_window(rows, args.days))
    if args.json:
        print(json.dumps({"version_truth": vt, "usage": rep}, indent=2))
    else:
        print(render(vt, rep, args.days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
