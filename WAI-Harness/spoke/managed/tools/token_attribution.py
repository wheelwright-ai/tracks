#!/usr/bin/env python3
"""Per-pass and per-advisor token attribution — what each phase of a run cost.

WHY THIS EXISTS. The wheel could say what a LUG cost and what a ROUND cost. It
could not say what a PASS cost (scout vs execute vs verify vs remediate) or what
an ADVISOR cost, and `cost_estimate` was null on every event ever written. Three
of the six candidates on the external-pattern slate were arguments about cost,
and none of them could be tested here — they were preferences dressed as
analysis. This is the cheapest thing that changes what we can know.

The immediate case: the verifier was just lifted from sonnet to opus
(autopilot_round.TIER_ORDER). That is a deliberate decision to spend more on
review, made on measured evidence that review pays. Without per-pass attribution
the wheel cannot see the resulting bill, so it can never find out whether it was
right — the check on the change and the change itself land together.

SCHEMA OWNERSHIP. model_usage_logger.py owns the `model_usage` event shape and
keeps owning it; this module adds two dimensions to it (`pass_name`, `actor`)
plus a filled-in `cost_estimate`, and writes through a root-aware path so an
autopilot running from another CWD does not silently write into a tree nobody
reads. Field parity with the owner is pinned by test, not by convention.

TOKENS AND MODEL ARE THE UNIT, NOT DOLLARS (operator ruling, 2026-07-22). This
wheel runs on a Claude subscription, so a dollar figure is notional and reads as
a bill that does not exist. What actually steers a decision is how many tokens a
pass spends and at which model tier — that is what the default report shows, and
it is what the tier arguments on the backlog are really about.

Costing is kept, opt-in behind `--cost`, for the one question it does answer:
comparing tiers on a common scale when tokens alone would understate the gap
between a haiku pass and an opus one. Prices are data, not code — a dated list
table, overridable per spoke via `local/config/model-prices.json`. A cost figure
for an unknown model is reported as unknown rather than as zero; a zero would
read as "free" in exactly the place a decision gets made.

    python3 tools/token_attribution.py report --by pass
    python3 tools/token_attribution.py report --by model --since 7d
    python3 tools/token_attribution.py report --by actor --cost
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# List prices in USD per million tokens. Cache reads bill at 0.1x input and cache
# writes at 1.25x input, so both are derived rather than restated per model.
PRICES_AS_OF = "2026-07-22"
PRICES = {
    "opus": {"in": 15.0, "out": 75.0},
    "sonnet": {"in": 3.0, "out": 15.0},
    "haiku": {"in": 1.0, "out": 5.0},
    "fable": {"in": 15.0, "out": 75.0},
}
CACHE_READ_MULTIPLIER = 0.1
CACHE_WRITE_MULTIPLIER = 1.25

# The passes worth separating. Anything else is recorded verbatim under its own
# name — an unrecognised pass must show up in the report, never be dropped into
# "other", because a phase nobody named is exactly the spend nobody is watching.
KNOWN_PASSES = ("scout", "execute", "verify", "remediate", "opp_scout", "ceremony", "advisor")


def _spoke_base(root="."):
    try:
        from wai_paths import resolve_wai_root
        resolved, mode = resolve_wai_root(str(root))
        if resolved and mode != "none":
            return Path(resolved)
    except Exception:
        pass
    v4 = Path(root) / "WAI-Harness" / "spoke" / "local"
    return v4 if v4.is_dir() else Path(root) / "WAI-Spoke"


def usage_file(root="."):
    return _spoke_base(root) / "model-usage" / "usage.jsonl"


def load_prices(root="."):
    """List table, overlaid by local/config/model-prices.json when present."""
    prices = {k: dict(v) for k, v in PRICES.items()}
    override = _spoke_base(root) / "config" / "model-prices.json"
    try:
        if override.is_file():
            data = json.loads(override.read_text(encoding="utf-8"))
            for family, rates in (data.get("prices") or {}).items():
                if isinstance(rates, dict) and "in" in rates and "out" in rates:
                    prices[family.lower()] = {"in": float(rates["in"]), "out": float(rates["out"])}
    except (OSError, ValueError):
        pass
    return prices


def model_family(model):
    """Map any model id onto a priced family; None when unrecognised."""
    name = (model or "").lower()
    for family in PRICES:
        if family in name:
            return family
    return None


def estimate_cost(model, tokens_in=0, tokens_out=0, cache_read=0, cache_creation=0, root="."):
    """USD for one call. Returns None — never 0.0 — for an unpriced model."""
    family = model_family(model)
    if not family:
        return None
    rates = load_prices(root).get(family)
    if not rates:
        return None
    per_m = 1_000_000.0
    cost = (
        (tokens_in or 0) * rates["in"] / per_m
        + (tokens_out or 0) * rates["out"] / per_m
        + (cache_read or 0) * rates["in"] * CACHE_READ_MULTIPLIER / per_m
        + (cache_creation or 0) * rates["in"] * CACHE_WRITE_MULTIPLIER / per_m
    )
    return round(cost, 6)


def usage_from_cli_json(stdout):
    """Pull the usage block out of `claude --print --output-format json` output.

    Returns {} when the payload is not that shape, so a caller that guessed wrong
    about the output format records nothing rather than recording zeros.
    """
    try:
        payload = json.loads(stdout)
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    usage = payload.get("usage")
    return usage if isinstance(usage, dict) else {}


def attribute(pass_name, actor, model, usage=None, lug_id=None, run_id=None,
              session_id=None, duration_ms=None, spoke_id=None, root=".",
              provider="anthropic"):
    """Record one attributed call. Returns the event written, or None if it wrote nothing.

    A call with no usage numbers is NOT recorded: an event of all zeros is worse
    than a missing one, because it reports as free spend rather than as a gap.
    """
    usage = usage or {}
    tokens_in = int(usage.get("input_tokens") or 0)
    tokens_out = int(usage.get("output_tokens") or 0)
    cache_read = int(usage.get("cache_read_input_tokens") or usage.get("cache_read_tokens") or 0)
    cache_creation = int(
        usage.get("cache_creation_input_tokens") or usage.get("cache_creation_tokens") or 0)
    if not (tokens_in or tokens_out or cache_read or cache_creation):
        return None

    event = {
        "event": "model_usage",
        "ts": datetime.now(timezone.utc).isoformat(),
        "spoke_id": spoke_id or os.path.basename(os.path.abspath(root)),
        "provider": provider,
        "model": model,
        "task_type": pass_name,
        "pass_name": pass_name,
        "actor": actor,
        "lug_id": lug_id,
        "run_id": run_id,
        "complexity": None,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_creation,
        "cost_estimate": estimate_cost(model, tokens_in, tokens_out, cache_read,
                                       cache_creation, root=root),
        "duration_ms": duration_ms,
        "quality_rating": None,
        "rework_required": None,
        "session_id": session_id,
    }
    path = usage_file(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
    except OSError:
        return None
    return event


def attribute_from_proc(pass_name, actor, model, stdout, **kwargs):
    """Convenience for the dispatch sites: parse CLI json, then attribute."""
    return attribute(pass_name, actor, model, usage_from_cli_json(stdout), **kwargs)


def _since_cutoff(spec):
    if not spec:
        return None
    spec = spec.strip().lower()
    units = {"d": "days", "h": "hours", "w": "weeks"}
    if spec[-1] in units and spec[:-1].isdigit():
        return datetime.now(timezone.utc) - timedelta(**{units[spec[-1]]: int(spec[:-1])})
    try:
        parsed = datetime.fromisoformat(spec)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def read_events(root=".", since=None):
    path = usage_file(root)
    cutoff = _since_cutoff(since)
    events = []
    if not path.is_file():
        return events
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("event") != "model_usage":
                continue
            if cutoff:
                try:
                    ts = datetime.fromisoformat(str(event.get("ts", "")).replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue
                except ValueError:
                    continue
            events.append(event)
    return events


def group(events, by="pass", root="."):
    """Aggregate into {key: {calls, tokens, tokens_in, tokens_out, cache, models, cost, unpriced}}.

    `models` is carried per row because tier is half the answer: two passes with
    identical token counts are not comparable spends if one ran at haiku and the
    other at opus, and a report that hides which tier did the work cannot settle
    a single tiering argument.

    `unpriced` is carried separately and printed: a total that silently omits
    calls it could not price is the same false-green this instrument exists to
    remove.
    """
    key_field = {
        "pass": "pass_name", "actor": "actor", "model": "model",
        "lug": "lug_id", "run": "run_id", "spoke": "spoke_id",
    }.get(by, "pass_name")
    out = {}
    for event in events:
        key = event.get(key_field) or event.get("task_type") or "(unattributed)"
        row = out.setdefault(str(key), {"calls": 0, "tokens": 0, "tokens_in": 0,
                                        "tokens_out": 0, "cache": 0, "models": {},
                                        "cost": 0.0, "unpriced": 0})
        row["calls"] += 1
        row["tokens_in"] += int(event.get("tokens_in") or 0)
        row["tokens_out"] += int(event.get("tokens_out") or 0)
        row["cache"] += int(event.get("cache_read_tokens") or 0) + \
            int(event.get("cache_creation_tokens") or 0)
        family = model_family(event.get("model")) or str(event.get("model") or "unknown")
        row["models"][family] = row["models"].get(family, 0) + 1
        row["tokens"] += sum(int(event.get(f) or 0) for f in
                             ("tokens_in", "tokens_out", "cache_read_tokens",
                              "cache_creation_tokens"))
        cost = event.get("cost_estimate")
        if cost is None:
            cost = estimate_cost(event.get("model"),
                                 event.get("tokens_in"), event.get("tokens_out"),
                                 event.get("cache_read_tokens"),
                                 event.get("cache_creation_tokens"), root=root)
        if cost is None:
            row["unpriced"] += 1
        else:
            row["cost"] += float(cost)
    return out


def _fmt_tokens(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def main():
    ap = argparse.ArgumentParser(description="per-pass and per-advisor token attribution")
    sub = ap.add_subparsers(dest="cmd", required=True)

    rep = sub.add_parser("report", help="aggregate recorded usage")
    rep.add_argument("--by", default="pass",
                     choices=["pass", "actor", "model", "lug", "run", "spoke"])
    rep.add_argument("--since", help="7d / 24h / 2w / ISO date")
    rep.add_argument("--root", default=".")
    rep.add_argument("--json", action="store_true")
    rep.add_argument("--cost", action="store_true",
                     help="add a notional list-price column (subscription — not a bill)")

    pr = sub.add_parser("price", help="cost one call, for sanity-checking the table")
    pr.add_argument("--model", required=True)
    pr.add_argument("--in", dest="tin", type=int, default=0)
    pr.add_argument("--out", dest="tout", type=int, default=0)
    pr.add_argument("--cache-read", type=int, default=0)
    pr.add_argument("--root", default=".")

    args = ap.parse_args()

    if args.cmd == "price":
        cost = estimate_cost(args.model, args.tin, args.tout, args.cache_read, root=args.root)
        if cost is None:
            print(f"UNPRICED — no rate for model '{args.model}' "
                  f"(known families: {', '.join(sorted(PRICES))})")
            return 2
        print(f"${cost:.4f}  ({args.model}, list prices as of {PRICES_AS_OF})")
        return 0

    events = read_events(args.root, args.since)
    rows = group(events, args.by, root=args.root)
    if args.json:
        print(json.dumps({"by": args.by, "since": args.since, "rows": rows}, indent=2))
        return 0

    if not rows:
        where = usage_file(args.root)
        print(f"No attributed usage recorded{' since ' + args.since if args.since else ''}.")
        print(f"  ledger: {where}{'' if where.is_file() else '  (does not exist yet)'}")
        return 0

    width = max(max(len(k) for k in rows), 5)
    print(f"TOKEN ATTRIBUTION — by {args.by}"
          f"{' since ' + args.since if args.since else ''}")
    header = (f"{'':<{width}}  {'calls':>6}  {'in':>7}  {'out':>7}  {'cache':>8}  "
              f"{'total':>8}  tiers")
    if args.cost:
        header = header[:-6] + f"{'cost*':>9}  tiers"
    print(header)

    totals = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cache": 0,
              "tokens": 0, "cost": 0.0, "unpriced": 0}
    for key, row in sorted(rows.items(), key=lambda kv: -kv[1]["tokens"]):
        tiers = ",".join(f"{m}x{c}" for m, c in
                         sorted(row["models"].items(), key=lambda kv: -kv[1]))
        line = (f"{key:<{width}}  {row['calls']:>6}  {_fmt_tokens(row['tokens_in']):>7}  "
                f"{_fmt_tokens(row['tokens_out']):>7}  {_fmt_tokens(row['cache']):>8}  "
                f"{_fmt_tokens(row['tokens']):>8}  ")
        if args.cost:
            line += f"{'$' + format(row['cost'], '.2f'):>9}  "
        print(line + tiers)
        for field in ("calls", "tokens_in", "tokens_out", "cache", "tokens", "unpriced"):
            totals[field] += row[field]
        totals["cost"] += row["cost"]

    line = (f"{'TOTAL':<{width}}  {totals['calls']:>6}  {_fmt_tokens(totals['tokens_in']):>7}  "
            f"{_fmt_tokens(totals['tokens_out']):>7}  {_fmt_tokens(totals['cache']):>8}  "
            f"{_fmt_tokens(totals['tokens']):>8}")
    if args.cost:
        line += f"  {'$' + format(totals['cost'], '.2f'):>9}"
    print(line)

    if args.cost:
        print(f"* notional list price ({PRICES_AS_OF}) — this wheel runs on a "
              f"subscription, so it is a comparison scale between tiers, not a bill.")
        if totals["unpriced"]:
            print(f"  {totals['unpriced']} call(s) had no price for their model and are "
                  f"counted in tokens but NOT in cost — that figure is a floor, not a total.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
