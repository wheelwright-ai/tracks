#!/usr/bin/env python3
"""chain_advantage — does verify-each-step actually beat dispatch-and-hope?

Each autopilot round records what it claimed and what an adversarial verifier
said about those claims. Nothing reads those records ACROSS rounds, so the same
failure class can recur every night and be caught every night without anyone
noticing it is the same failure. That is a detector, not a learning loop.

This closes that gap with three questions, answered in numbers:

  1. SURVIVING-CLAIM RATE  of the claims a round produced, how many survived a
                           verifier whose job was to refute them. Compared
                           chain-mode vs batch-mode, because that comparison is
                           the entire justification for chain mode being slower.
  2. REMEDIATION CONVERSION when a step was refuted and remediation ran, did the
                           retry actually end CONFIRMED. If refusals never
                           convert, chain mode is an expensive detector.
  3. RECURRING FAULT DOMAIN the verifier tags each refusal implementation /
                           criteria / process. The same domain repeating across
                           rounds is the signature of a loop that is not learning.

UNVERIFIABLE is counted as a failure, never as a pass. A claim nobody could
check is not a completed claim, and folding it into the success rate is exactly
how a measured 20% becomes a reported 90%.

Usage:
    python3 chain_advantage.py [--root PATH] [--json]
"""
import argparse
import glob
import json
import os
from collections import Counter

CONFIRM = "CONFIRMED"
REFUTE = "REFUTED"
UNVERIF = "UNVERIFIABLE"


def _rounds_dir(root):
    for rel in ("WAI-Harness/spoke/local/ap-rounds", "WAI-Spoke/ap-rounds"):
        path = os.path.join(root, rel)
        if os.path.isdir(path):
            return path
    return os.path.join(root, "WAI-Harness/spoke/local/ap-rounds")


def claim_verdicts(rec):
    """Every per-claim verdict in a round.

    A batch round records them in verdicts[]; a chain verifies as it goes and
    records them in steps[]. Reading only one of the two under-reports the
    round — the bug that made an earlier chain round print a top-line verdict
    contradicting its own step detail.
    """
    out = []
    for v in rec.get("verdicts") or []:
        out.append(dict(v))
    for st in rec.get("steps") or []:
        verdict = str(st.get("verdict") or "").upper()
        if verdict and verdict != "NO-WORK":
            out.append(dict(st))
    return out


def analyse(root):
    rounds = sorted(glob.glob(os.path.join(_rounds_dir(root), "*.json")))
    per_round = []
    faults = Counter()
    remediated = 0
    remediated_confirmed = 0

    for path in rounds:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                rec = json.load(fh)
        except Exception as exc:
            per_round.append({"round": os.path.basename(path), "error": str(exc)})
            continue

        claims = claim_verdicts(rec)
        counts = Counter(str(c.get("verdict") or "").upper() for c in claims)

        for c in claims:
            verdict = str(c.get("verdict") or "").upper()
            domain = c.get("fault_domain")
            if verdict == REFUTE and domain:
                faults[domain] += 1
            # A step carries remediation detail only when a retry actually ran.
            attempts = c.get("attempts") or []
            ran = c.get("remediation") or any(a.get("remediation") for a in attempts)
            if ran:
                remediated += 1
                if verdict == CONFIRM:
                    remediated_confirmed += 1

        total = len(claims)
        per_round.append({
            "round": rec.get("round_id") or os.path.basename(path)[:-5],
            "mode": rec.get("mode") or "batch",
            "round_verdict": rec.get("verdict"),
            "claims": total,
            "confirmed": counts[CONFIRM],
            "refuted": counts[REFUTE],
            "unverifiable": counts[UNVERIF],
            "surviving_rate": (counts[CONFIRM] / total) if total else None,
        })

    scored = [r for r in per_round if r.get("claims")]

    def rate(mode_test):
        group = [r for r in scored if mode_test(r["mode"])]
        conf = sum(r["confirmed"] for r in group)
        total = sum(r["claims"] for r in group)
        return {"rounds": len(group), "claims": total, "confirmed": conf,
                "rate": (conf / total) if total else None}

    chain = rate(lambda m: m == "chain")
    batch = rate(lambda m: m != "chain")
    delta = None
    if chain["rate"] is not None and batch["rate"] is not None:
        delta = chain["rate"] - batch["rate"]

    all_claims = sum(r["claims"] for r in scored)
    all_unver = sum(r["unverifiable"] for r in scored)

    return {
        "per_round": per_round,
        "chain": chain,
        "batch": batch,
        "delta": delta,
        "unverifiable": {"count": all_unver, "of": all_claims,
                         "rate": (all_unver / all_claims) if all_claims else None},
        "remediation": {"ran": remediated, "converted": remediated_confirmed,
                        "rate": (remediated_confirmed / remediated) if remediated else None},
        "fault_domains": dict(faults.most_common()),
    }


def _pct(value):
    return "n/a" if value is None else f"{value:.0%}"


def render(result):
    lines = []
    lines.append("ROUND-BY-ROUND")
    lines.append(f"  {'round':30} {'mode':7} {'claims':>6} {'conf':>5} "
                 f"{'refu':>5} {'unver':>5}  surviving")
    for r in result["per_round"]:
        if r.get("error"):
            lines.append(f"  {r['round']:30} unreadable: {r['error']}")
            continue
        lines.append(f"  {r['round'][:30]:30} {r['mode']:7} {r['claims']:>6} "
                     f"{r['confirmed']:>5} {r['refuted']:>5} {r['unverifiable']:>5}"
                     f"  {_pct(r['surviving_rate'])}")

    chain, batch, delta = result["chain"], result["batch"], result["delta"]
    lines.append("")
    lines.append("ADVANTAGE — verify-each-step vs dispatch-and-check-later")
    lines.append(f"  chain  {chain['confirmed']}/{chain['claims']} claims survived "
                 f"refutation ({_pct(chain['rate'])}) over {chain['rounds']} round(s)")
    lines.append(f"  batch  {batch['confirmed']}/{batch['claims']} claims survived "
                 f"refutation ({_pct(batch['rate'])}) over {batch['rounds']} round(s)")
    if delta is not None:
        favours = "chain" if delta > 0 else "batch"
        lines.append(f"  delta  {delta:+.0%} in favour of {favours}")
        if chain["claims"] + batch["claims"] < 20:
            lines.append("         (small sample — directional, not settled)")
    else:
        lines.append("  delta  not computable — need at least one round of each mode")

    unv = result["unverifiable"]
    lines.append("")
    lines.append("UNVERIFIABLE — claims nobody could check. These are not successes.")
    lines.append(f"  {unv['count']}/{unv['of']} ({_pct(unv['rate'])})")
    if unv["rate"] and unv["rate"] > 0.2:
        lines.append("  WARNING: a fifth or more of claims cannot be checked at all.")
        lines.append("  That is a measurement failure, not a completion rate — the lugs")
        lines.append("  are not landing evidence a verifier can act on.")

    rem = result["remediation"]
    lines.append("")
    lines.append("REMEDIATION — when a refused step was retried, did the retry fix it?")
    if rem["ran"]:
        lines.append(f"  {rem['converted']}/{rem['ran']} retried steps ended CONFIRMED "
                     f"({_pct(rem['rate'])})")
        if rem["converted"] == 0:
            lines.append("  Remediation is not converting. The chain is catching refusals")
            lines.append("  but not repairing them — a detector, not a fixer.")
    else:
        lines.append("  no remediation attempts recorded yet")

    lines.append("")
    lines.append("RECURRING FAULT DOMAINS — the same domain repeating means no learning")
    if result["fault_domains"]:
        for domain, count in result["fault_domains"].items():
            lines.append(f"  {count:>3}x  {domain}")
    else:
        lines.append("  none recorded — either no refusals, or the verifier's")
        lines.append("  fault_domain is not reaching the round record.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    result = analyse(args.root)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render(result))


if __name__ == "__main__":
    main()
